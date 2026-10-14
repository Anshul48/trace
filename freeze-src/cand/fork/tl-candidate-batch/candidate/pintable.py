"""W5 attach-and-pin per the S-04 Q1.1-Q1.4 accepted baseline (integration only).
Fixed-slot POSIX shm table; reader-side claim; bounded retries then explicit
retryable error; table setup separate from attach; outside DB files/lock domain.
CAS realization (Linux reference): compare-and-swap of a slot under a
table-internal OFD byte-range critical section on the shm object itself.
Q1.4 holds by construction: that lock domain ({shm object}) is disjoint from
commit (commit.db + committer.lock), fold, checkpoint, and scan paths.
Pointer publication uses a guard-word torn-read check; full pointer-atomicity
qualification stays retained at S-04/C2 (queued sub-item), not asserted here.
"""
import fcntl
import os
import struct
import time
import uuid as _uuid
from multiprocessing import shared_memory

from common import Retryable, FailClosed

MAGIC = b"TLPT10\0\0"
HDR_FMT = "<8s16sIIQQ"      # magic, table_id, slots, pad, counter, rsv
HDR_LEN = 64
PTR_FMT = "<Q16sQQQ"        # guard, birth, epoch, seq, guard2
PTR_LEN = 64
SLOT_FMT = "<IIQ16sQQ16s"   # state, pad, incarn, birth, epoch, seq, owner
SLOT_LEN = 64
FREE, CLAIMED = 0, 1
PTR_OFF = 64
SLOT_OFF = 128

F_WRLCK = fcntl.F_WRLCK
F_UNLCK = fcntl.F_UNLCK


def _lk(typ, start, length):
    return struct.pack("hhqqih", typ, 0, start, length, 0, 0)


class PinTable:
    def __init__(self, name, slots=None, create=False):
        self.name = name
        if create:
            if slots is None:
                raise FailClosed("slot count [E] must be configured at setup")
            size = SLOT_OFF + SLOT_LEN * slots
            try:
                old = shared_memory.SharedMemory(name=name)
                old.close()
                old.unlink()
            except FileNotFoundError:
                pass
            self.shm = shared_memory.SharedMemory(name=name, create=True, size=size)
            self._fd = os.open("/dev/shm/" + name, os.O_RDWR | os.O_CLOEXEC)
            self._init(slots)
        else:
            try:
                self.shm = shared_memory.SharedMemory(name=name)
            except FileNotFoundError:
                raise Retryable(f"pin table {name} absent (crash-cleared?)")
            self._fd = os.open("/dev/shm/" + name, os.O_RDWR | os.O_CLOEXEC)
            if self.shm.buf[0:8] != MAGIC:
                raise Retryable(f"pin table {name} magic bad: treat as fresh")
        hdr = struct.unpack_from(HDR_FMT, self.shm.buf, 0)
        self.table_id = hdr[1]
        self.slots = hdr[2]

    def _init(self, slots):
        tid = _uuid.uuid4().bytes
        struct.pack_into(HDR_FMT, self.shm.buf, 0, MAGIC, tid, slots, 0, 1, 0)
        struct.pack_into(PTR_FMT, self.shm.buf, PTR_OFF, 2, b"\0" * 16, 0, 0, 2)
        for i in range(slots):
            struct.pack_into(SLOT_FMT, self.shm.buf, SLOT_OFF + i * SLOT_LEN,
                             FREE, 0, 0, b"\0" * 16, 0, 0, b"\0" * 16)

    # -- internal range locking (table domain only) --
    def _try_range(self, off, ln):
        try:
            fcntl.fcntl(self._fd, fcntl.F_OFD_SETLK, _lk(F_WRLCK, off, ln))
            return True
        except OSError:
            return False

    def _un_range(self, off, ln):
        try:
            fcntl.fcntl(self._fd, fcntl.F_OFD_SETLK, _lk(F_UNLCK, off, ln))
        except OSError:
            pass

    def _mint_incarnation(self):
        if not self._try_range(0, HDR_LEN):
            return None
        try:
            hdr = struct.unpack_from(HDR_FMT, self.shm.buf, 0)
            c = hdr[4]
            struct.pack_into(HDR_FMT, self.shm.buf, 0, hdr[0], hdr[1], hdr[2],
                             hdr[3], c + 1, hdr[5])
            return c
        finally:
            self._un_range(0, HDR_LEN)

    def close(self):
        try:
            os.close(self._fd)
        except OSError:
            pass
        self.shm.close()

    def destroy(self):
        self.close()
        try:
            self.shm.unlink()
        except FileNotFoundError:
            pass

    # -- pointer (single writer: committer) --
    def publish(self, birth, epoch, seq):
        b = _uuid.UUID(birth).bytes if isinstance(birth, str) else birth
        g0 = struct.unpack_from("<Q", self.shm.buf, PTR_OFF)[0]
        g = g0 + 1 if g0 % 2 == 0 else g0 + 2
        struct.pack_into("<Q", self.shm.buf, PTR_OFF, g)  # odd: writing
        struct.pack_into("<16sQQ", self.shm.buf, PTR_OFF + 8, b, epoch, seq)
        struct.pack_into("<Q", self.shm.buf, PTR_OFF + 8 + 32, g + 1)
        struct.pack_into("<Q", self.shm.buf, PTR_OFF, g + 1)

    def read_pointer(self, tries=100):
        for _ in range(tries):
            g1, b, e, s, g2 = struct.unpack_from(PTR_FMT, self.shm.buf, PTR_OFF)
            if g1 % 2 == 0 and g1 == g2 and g1 != 0:
                return (str(_uuid.UUID(bytes=b)) if b != b"\0" * 16 else None, e, s)
        raise Retryable("pointer torn/unstable: retryable")

    # -- slot claim (reader side) --
    def claim(self, gen, max_retries=50, deadline_s=None):
        """Claim a slot recording gen=(birth,epoch,seq). Bounded retries, then
        explicit retryable error. Optional bounded wait holds nothing.
        Returns (slot, incarnation, owner, attempts, claim_cost_s)."""
        t_start = time.perf_counter()
        attempts = 0
        deadline = (time.perf_counter() + deadline_s) if deadline_s else None
        while True:
            for i in range(self.slots):
                attempts += 1
                off = SLOT_OFF + i * SLOT_LEN
                if not self._try_range(off, SLOT_LEN):
                    continue  # contention on this slot: counted, move on
                try:
                    st = struct.unpack_from(SLOT_FMT, self.shm.buf, off)
                    if st[0] != FREE:
                        continue
                    inc = self._mint_incarnation()
                    if inc is None:
                        continue
                    b = _uuid.UUID(gen[0]).bytes if gen[0] else b"\0" * 16
                    owner = _uuid.uuid4().bytes
                    struct.pack_into(SLOT_FMT, self.shm.buf, off, CLAIMED, 0,
                                     inc, b, gen[1], gen[2], owner)
                    return (i, inc, owner, attempts, time.perf_counter() - t_start)
                finally:
                    self._un_range(off, SLOT_LEN)
            # full sweep with no claim
            if deadline is not None:
                if time.perf_counter() >= deadline:
                    raise Retryable("bounded wait deadline: same retryable error; "
                                    "wait held no slot/lock/txn")
                time.sleep(0.001)  # wait holds no slot/lock/txn
                continue
            if attempts >= max_retries:
                raise Retryable(f"slot-claim failed after {attempts} bounded "
                                f"retries (explicit retryable error)")

    def release(self, slot, incarnation):
        off = SLOT_OFF + slot * SLOT_LEN
        if not self._try_range(off, SLOT_LEN):
            raise Retryable("release contention: retryable")
        try:
            st = struct.unpack_from(SLOT_FMT, self.shm.buf, off)
            if st[0] != CLAIMED or st[2] != incarnation:
                return False  # not ours (already released/reused): no-reuse holds
            struct.pack_into(SLOT_FMT, self.shm.buf, off, FREE, 0, st[2],
                             b"\0" * 16, 0, 0, b"\0" * 16)
            return True
        finally:
            self._un_range(off, SLOT_LEN)

    def validate(self, table_id, slot, incarnation):
        """Reclamation-side check: slot's recorded generation is honored.
        Released incarnations never validate again (state FREE or incarn moved)."""
        if table_id != self.table_id:
            return None  # stale table (crash-cleared => fresh table id)
        st = struct.unpack_from(SLOT_FMT, self.shm.buf, SLOT_OFF + slot * SLOT_LEN)
        if st[0] != CLAIMED or st[2] != incarnation:
            return None
        b = str(_uuid.UUID(bytes=st[3])) if st[3] != b"\0" * 16 else None
        return (b, st[4], st[5])

    # -- seqlock acquire (Q1.3) --
    def acquire(self, max_rounds=20, claim_retries=50):
        """read pointer, CAS slot, re-read; stable => pin. Mismatch => release
        (fresh incarnation next claim) + bounded retry. Returns pin dict."""
        last = None
        for rnd in range(max_rounds):
            g1 = self.read_pointer()
            if g1[0] is None:
                raise Retryable("no publication yet: retryable")
            slot, inc, owner, attempts, cost = self.claim(g1, max_retries=claim_retries)
            g2 = self.read_pointer()
            if g1 == g2:
                return {"table": self.table_id.hex(), "slot": slot,
                        "incarnation": inc, "gen": g1, "rounds": rnd + 1,
                        "claim_attempts": attempts, "claim_cost_s": cost}
            self.release(slot, inc)  # mismatch: no-reuse next claim
            last = (g1, g2)
        raise Retryable(f"sustained churn: {max_rounds} bounded rounds exhausted; "
                        f"starvation as error, never stale attach (last={last})")
