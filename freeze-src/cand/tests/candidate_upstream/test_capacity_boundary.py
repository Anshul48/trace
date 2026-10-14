#!/usr/bin/env python3
"""Capacity-boundary correctness test (S-01 P9 contract).

Setup (scaffolding, disclosed): bulk-SQL 99,999 commits rows under the
fence's birth/epoch (U-02 triggers keep the ledger exact — asserted),
then the REAL commit_op path for:
  op A (100000th commit) -> must COMMIT (boundary near side);
  op B (extra op at delta==100000) -> must raise Retryable
      REJECT_CAPACITY(deadline) with the 5 s deadline honored;
  op B same-id retry -> same Retryable (not MISMATCH/success);
  committed set unchanged by B (no dedup row, COUNT still 100000).

Contract: handoffs/S-01-FOLLOWUP-SPEC.md P9 — reserve GRANT|WAIT|
REJECT_CAPACITY before the txn; WAIT outside txn to deadline, then
REJECT_CAPACITY; "explicit retryable capacity error; nothing
committed, no effect" (I9.2, F9.1). F9.1 intake-tombstone applies to
spooled ops; this workload drives commit_op directly (intake empty).

  op C (batch at durable cap) -> commit_batch([fresh EDIT]) must show
      SERIAL PARITY with op B: pre-commit-abort, retryable
      REJECT_CAPACITY(deadline) with the 5 s deadline honored (the
      immediate (staged) qualifier is honest only when the staged term
      is what pushes over: durable < max <= durable+staged).

Usage: python3 test_capacity_boundary.py --sut <dir> --store-root <dir>
Exit 0 PASS, 1 FAIL, 2 BLOCKED. Stdlib only. Zero harness imports.
"""
import argparse, os, random, sqlite3, sys, time

sys.dont_write_bytecode = True

def mint_v7(ts_ms, ra, rb):
    v = ((ts_ms & 0xFFFFFFFFFFFF) << 80) | (7 << 76) | ((ra & 0xFFF) << 64) | (2 << 62) | (rb & 0x3FFFFFFFFFFFFFFF)
    h = "%032x" % v
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sut", required=True)
    ap.add_argument("--store-root", required=True)
    args = ap.parse_args()
    sut = os.path.abspath(args.sut)
    for m in ("store.py", "committer.py", "intake.py", "replay.py"):
        if not os.path.isfile(os.path.join(sut, m)):
            print("BLOCKED: SUT missing", m)
            return 2
    sys.path.insert(0, sut)
    from store import Store, Fence
    from committer import Committer
    from common import Reject, Retryable

    import random as _r, time as _t
    root = os.path.join(os.path.abspath(args.store_root),
                        "cap-bound-%d-%d-%04x" % (os.getpid(), int(_t.time()), _r.randrange(65536)))
    os.makedirs(root, exist_ok=False)

    def has_counters(con):
        return con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                           "AND name='counters'").fetchone()[0] == 1

    def delta_count(con):
        n = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        if has_counters(con):
            cnt = dict(con.execute("SELECT k,v FROM counters").fetchall())
            assert cnt.get("delta_entries") == n, (cnt, n)
        return n
    store = Store.create(root)
    fence = Fence(store)
    birth, epoch = fence.acquire()
    fails = []
    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {detail}"))
        if not cond:
            fails.append(name)

    # scaffolding: 99,999 commits rows (one txn) under fence birth/epoch
    con = store.open_db()
    rows = [(s, birth, epoch, "scaf-%06d" % s, "EDIT", "00" * 32,
             '{"committed": true}', '{"leg": "scaffold"}', None, time.time())
            for s in range(1, 100000)]
    con.execute("BEGIN IMMEDIATE;")
    con.executemany("INSERT INTO commits(seq,birth,epoch,op_id,kind,payload_hash,"
                    "outcome,disclosure,approval_ref,decided_at) VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
    con.execute("COMMIT;")
    scaf_n = delta_count(con)
    check("scaffold-count-exact", scaf_n == 99999, scaf_n)
    con.close()

    cm = Committer(store, fence)
    rng = random.Random(20260928111)
    now = time.time()
    oid_a = mint_v7(int(now * 1000), rng.getrandbits(12), rng.getrandbits(62))
    out_a, triple_a = cm.commit_op(oid_a, "EDIT", {"body": "cap-boundary-A"},
                                   {"leg": "cap-test"}, None, [])
    check("opA-100000th-commits", '"committed": true' in out_a and triple_a.endswith(":100000"),
          f"{out_a[:60]} {triple_a}")

    now = time.time()
    oid_b = mint_v7(int(now * 1000), rng.getrandbits(12), rng.getrandbits(62))
    t0 = time.time()
    got = None
    try:
        cm.commit_op(oid_b, "EDIT", {"body": "cap-boundary-B"}, {"leg": "cap-test"}, None, [])
    except Retryable as r:
        got = str(r)
    except Reject as r:
        got = f"REJECT:{r.code}"
    dt = time.time() - t0
    check("opB-retryable-capacity", got is not None and got.startswith("REJECT_CAPACITY(deadline)"), repr(got)[:90])
    check("opB-deadline-honored", dt >= 4.5, f"{dt:.2f}s")

    con = store.open_db()
    try:
        row = con.execute("SELECT * FROM dedup WHERE op_id=?", (oid_b,)).fetchone()
        n = delta_count(con)
    finally:
        con.close()
    check("opB-nothing-committed", n == 100000 and row is None, f"n={n} row={row is not None}")

    t0 = time.time()
    got2 = None
    try:
        cm.commit_op(oid_b, "EDIT", {"body": "cap-boundary-B"}, {"leg": "cap-test"}, None, [])
    except Retryable as r:
        got2 = str(r)
    except Reject as r:
        got2 = f"REJECT:{r.code}"
    check("opB-retry-same-outcome", got2 is not None and got2.startswith("REJECT_CAPACITY(deadline)"), repr(got2)[:90])

    # (c) batch serial-parity at durable cap (red-team Finding A): durable
    # alone at cap (staged==0) must take reserve()'s honest P9 path --
    # WAIT-to-deadline then REJECT_CAPACITY(deadline) -- exactly like
    # commit_op above. Immediate (staged) is only honest when the STAGED
    # term is what pushes over (durable < max <= durable+staged).
    oid_c = mint_v7(int(time.time() * 1000), rng.getrandbits(12), rng.getrandbits(62))
    t0 = time.time()
    try:
        rc, ic = cm.commit_batch([{"op_id": oid_c, "kind": "EDIT",
                                   "payload": {"body": "cap-boundary-C"},
                                   "disclosure": {"leg": "cap-test"},
                                   "approval_ref": None, "artifacts": ()}])
        call_c = True
    except Exception as e:
        check("opC-batch-call-ok", False, f"{type(e).__name__}: {e}")
        rc, ic, call_c = None, None, False
    dt_c = time.time() - t0
    if call_c:
        check("opC-batch-call-ok", True)
        msg_c = str(rc[0].get("message", ""))
        # Batch per-op messages carry the "Retryable: " type prefix by
        # design (same convention as T5a); assert the (deadline) flavor.
        check("opC-retryable-deadline", rc[0].get("status") == "retryable"
              and "REJECT_CAPACITY(deadline)" in msg_c
              and "(staged)" not in msg_c,
              f"{str(rc[0])[:120]} path={ic.get('path')}")
        check("opC-deadline-honored", dt_c >= 4.5, f"{dt_c:.2f}s")
        check("opC-precommit-no-fallback", ic.get("path") == "pre-commit-abort",
              f"path={ic.get('path')}")
    con = store.open_db()
    try:
        row_c = con.execute("SELECT * FROM dedup WHERE op_id=?", (oid_c,)).fetchone()
        n_c = delta_count(con)
    finally:
        con.close()
    check("opC-nothing-committed", n_c == 100000 and row_c is None,
          f"n={n_c} row={row_c is not None}")
    fence.release()
    print("RESULT:", "PASS" if not fails else f"FAIL {fails}")
    return 1 if fails else 0

if __name__ == "__main__":
    raise SystemExit(main())
