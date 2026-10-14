"""Stage-A scratch implementation: shared core (W1/W2/W3/W4/W5/P6).
Linux reference. All paths under the scratch root. Zero repo writes.
BI-1: R1(b)/(d) takeover execution (epoch bump, stale-epoch-after-takeover,
second-committer) + PR-FENCE are HELD pending S-01 reconciliation.
Recovery.restore() is code-guarded and refuses without TL_S01_RECONCILED=1.
"""
import errno
import hashlib
import json
import os
import random
try:
    import resource
except ImportError:  # POSIX-only; absent on Windows
    resource = None
import sqlite3
import struct
import time
import uuid

SCRATCH = "/tmp/tl-stage-a-2026-09-19"


class TLException(Exception):
    pass


class Retryable(TLException):
    """Explicit retryable error (capacity, contention, churn, clock)."""


class Reject(TLException):
    """Terminal/explicit rejection with a stable code."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class FailClosed(TLException):
    """Defect/unsupported state: refuse, never proceed."""


class HeldError(TLException):
    """HELD path executed without reconciliation: must never happen."""


def raise_retryable_on_eio(exc, where):
    """F-D error translation (freeze §4 F-D row: EIO on the commit path is
    retryable). Translates ONLY errno EIO; every other OSError (notably
    ENOENT relied upon by F-C fail-closed paths) re-raises untouched."""
    if isinstance(exc, OSError) and exc.errno == errno.EIO:
        raise Retryable("storage EIO at %s: aborted, retryable" % where) from exc
    raise exc


# ---- UUIDv7 (P5) ----
def uuidv7(ts_ms=None):
    ts_ms = int(time.time() * 1000) if ts_ms is None else int(ts_ms)
    # 48-bit ts | 4-bit ver(7) | 12-bit rand | 2-bit var(10) | 62-bit rand
    rand_a = random.getrandbits(12)
    rand_b = random.getrandbits(62)
    val = (((ts_ms & 0xFFFFFFFFFFFF) << 80) | (7 << 76) | (rand_a << 62)
           | (2 << 60) | rand_b)
    return str(uuid.UUID(int=val))


def parse_uuidv7(s):
    try:
        u = uuid.UUID(s)
    except ValueError:
        raise Reject("REJECT_MALFORMED", f"not a uuid: {s}")
    if (u.int >> 76) & 0xF != 7:
        raise Reject("REJECT_MALFORMED", f"not uuidv7: {s}")
    ts_ms = (u.int >> 80) & 0xFFFFFFFFFFFF
    return ts_ms / 1000.0


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---- run records (D-12/D-21) ----
MACHINE = {
    "cpu": "AMD Ryzen 7 250 8C/16T x86_64 (WSL2/Microsoft)",
    "ram": "15GiB",
    "disk_tmp": "ext4 /dev/sdd 1007G (905G free at phase1)",
    "shm": "tmpfs 7.7G",
    "python": "3.12.3",
}


def now():
    return time.time()


def rss_mb():
    if resource is None:
        raise RuntimeError(
            "rss_mb unavailable: 'resource' module missing on this platform")
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def du_bytes(path):
    total = 0
    for dp, _, fns in os.walk(path):
        for f in fns:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return total


class RunRecord:
    """Per-probe-run record: machine + work-per-unit + wall + allowance use."""

    def __init__(self, probe, store_dir):
        self.probe = probe
        self.store_dir = store_dir
        self.t0 = now()
        self.d0 = du_bytes(store_dir) if os.path.isdir(store_dir) else 0
        self.rec = {
            "probe": probe,
            "machine": dict(MACHINE),
            "allowance": {"per_run_wall_s": 600, "suite_wall_s": 7200,
                          "scratch_disk_B": 20 * 1024**3, "shm_B": 1024**3,
                          "per_probe_rss_B": 1024**3, "max_procs": 8},
            "workload": None,
            "work_per_unit": {},
            "events": [],
        }

    def workload(self, w):
        self.rec["workload"] = w
        with open(os.path.join("runs", self.probe, "workload.json"), "w") as f:
            json.dump(w, f, indent=1, sort_keys=True)

    def event(self, **kw):
        kw["t"] = round(now() - self.t0, 4)
        self.rec["events"].append(kw)

    def finish(self, verdict, work_per_unit, note=""):
        wall = now() - self.t0
        self.rec.update({
            "verdict": verdict,
            "note": note,
            "wall_s": round(wall, 3),
            "work_per_unit": work_per_unit,
            "allowance_use": {
                "wall_s": round(wall, 3),
                "wall_within_600": wall <= 600,
                "store_delta_B": du_bytes(self.store_dir) - self.d0,
                "store_total_B": du_bytes(self.store_dir),
                "max_rss_MB_self": round(rss_mb(), 1),
            },
        })
        if wall > 600:
            self.rec["verdict"] = "BOUNDED-INCOMPLETE"
            self.rec["note"] += " | WALL OVERRUN (>600s) fail-closed"
        with open(os.path.join("runs", self.probe, "evidence.json"), "w") as f:
            json.dump(self.rec, f, indent=1, sort_keys=True)
        return self.rec
