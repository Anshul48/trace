#!/usr/bin/env python3
"""T4 batch same-ID matrix.

(a) Same op_id twice in ONE batch (same payload) -> both committed
    outcomes, ONE new row (second is idempotent via fallback).
(b) Same op_id, different payload, one batch -> second yields raised
    REJECT_MISMATCH (contract failure preserved, NOT converted), first
    committed; exactly one new row.
(c) Same op_id resubmitted in a LATER batch after commit -> COMMITTED
    outcome, no new row.
(d) Unknown-kind ref-less op in batch -> terminal APPROVAL_MISSING via
    D12b, no abort (path=batch).

Usage: python3 test_batch_sameid.py --sut <dir> --store-root <dir>
Exit 0 PASS, 1 FAIL, 2 BLOCKED. Stdlib only. Zero harness imports.
"""
import argparse
import os
import sys
import time

sys.dont_write_bytecode = True

STATUSES = ("committed", "terminal", "raised", "retryable", "not_attempted")
PATHS = ("batch", "fallback-serial", "reconciled-committed", "reconciled-absent", "reconciled-readonly", "pre-commit-abort")


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
            print("RESULT: BLOCKED [sut-missing]")
            return 2
    sys.path.insert(0, sut)
    from store import Store, Fence
    from committer import Committer

    import random as _r
    root = os.path.join(os.path.abspath(args.store_root),
                        "t4-sameid-%d-%d-%04x" % (os.getpid(), int(time.time()), _r.randrange(65536)))
    os.makedirs(root, exist_ok=False)

    fails, blocked = [], []

    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {detail}"))
        if not cond:
            fails.append(name)

    def block(name, detail=""):
        print("BLOCKED " + name + ("" if not detail else f" :: {detail}"))
        blocked.append(name)

    if not hasattr(Committer, "commit_batch"):
        block("api-commit_batch-missing",
              "Committer has no attribute commit_batch (SUT=" + sut + ")")
        print("RESULT:", "BLOCKED" if not fails else f"FAIL {fails}", blocked)
        return 2

    rng = _r.Random(2026092804)
    store = Store.create(os.path.join(root, "main"))
    fence = Fence(store)
    fence.acquire()
    cm = Committer(store, fence)

    def counts():
        con = store.open_db()
        try:
            return (con.execute("SELECT COUNT(*) FROM commits").fetchone()[0],
                    con.execute("SELECT COUNT(*) FROM dedup").fetchone()[0])
        finally:
            con.close()

    def run_batch(ops, tag):
        """Call commit_batch; unexpected raise -> FAIL. Returns (results, info)
        or (None, None) after recording the failure / block."""
        try:
            results, info = cm.commit_batch(ops)
        except Exception as e:
            check(f"{tag}-call-ok", False, f"{type(e).__name__}: {e}")
            return None, None
        check(f"{tag}-call-ok", True)
        if not (isinstance(results, (list, tuple)) and len(results) == len(ops)):
            block(f"{tag}-shape-results", f"len={getattr(results, '__len__', lambda: '?')()}")
            return None, None
        if not isinstance(info, dict) or info.get("path") not in PATHS:
            block(f"{tag}-shape-batchinfo", f"{str(info)[:150]}")
            return None, None
        for i, res in enumerate(results):
            if not isinstance(res, dict) or res.get("status") not in STATUSES:
                block(f"{tag}-shape-result-{i}", f"{str(res)[:150]}")
                return None, None
        return results, info

    base_ms = int(time.time() * 1000)

    # ---- (a) same id twice, same payload ----
    oid_a = mint_v7(base_ms, rng.getrandbits(12), rng.getrandbits(62))
    pay_a = {"body": "t4a"}
    n0, d0 = counts()
    ra, ia = run_batch(
        [{"op_id": oid_a, "kind": "EDIT", "payload": dict(pay_a),
          "disclosure": {"leg": "t4a"}, "approval_ref": None, "artifacts": ()},
         {"op_id": oid_a, "kind": "EDIT", "payload": dict(pay_a),
          "disclosure": {"leg": "t4a"}, "approval_ref": None, "artifacts": ()}], "a")
    if ra is not None:
        check("a-both-committed", [r["status"] for r in ra] == ["committed", "committed"],
              f"{[r['status'] for r in ra]}")
        # Same-txn resubmit: op 1 fully completes (incl. mark_committed)
        # before op 2 is processed, so op 2 sees COMMITTED in-txn and
        # returns read-only committed -- no abort, path=batch is CORRECT.
        check("a-path-batch", ia["path"] == "batch",
              f"path={ia['path']} abort={ia['abort']}")
        check("a-same-triple", ra[0].get("triple") == ra[1].get("triple")
              and ra[0].get("outcome") == ra[1].get("outcome"),
              f"{str(ra[0])[:120]} vs {str(ra[1])[:120]}")
    n1, d1 = counts()
    check("a-one-new-row", (n1 - n0, d1 - d0) == (1, 1), f"commits+{n1 - n0} dedup+{d1 - d0}")

    # ---- (b) same id, different payload ----
    oid_b = mint_v7(base_ms + 10, rng.getrandbits(12), rng.getrandbits(62))
    n0, d0 = counts()
    rb, ib = run_batch(
        [{"op_id": oid_b, "kind": "EDIT", "payload": {"body": "t4b-first"},
          "disclosure": {"leg": "t4b"}, "approval_ref": None, "artifacts": ()},
         {"op_id": oid_b, "kind": "EDIT", "payload": {"body": "t4b-SECOND-different"},
          "disclosure": {"leg": "t4b"}, "approval_ref": None, "artifacts": ()}], "b")
    if rb is not None:
        check("b-statuses", [r["status"] for r in rb] == ["committed", "raised"],
              f"{[r['status'] for r in rb]} {str(rb[1])[:150]}")
        check("b-mismatch-code", rb[1].get("code") == "REJECT_MISMATCH",
              f"{str(rb[1])[:150]}")
        check("b-via-fallback", ib["path"] == "fallback-serial",
              f"path={ib['path']} abort={ib['abort']}")
    n1, d1 = counts()
    check("b-one-new-row", (n1 - n0, d1 - d0) == (1, 1), f"commits+{n1 - n0} dedup+{d1 - d0}")
    # first payload stands: commits row for oid_b matches first body hash
    con = store.open_db()
    try:
        row = con.execute("SELECT outcome FROM commits WHERE op_id=?", (oid_b,)).fetchone()
        drow = con.execute("SELECT state FROM dedup WHERE op_id=?", (oid_b,)).fetchone()
    finally:
        con.close()
    check("b-first-stands", row is not None and drow is not None and drow[0] == "COMMITTED",
          f"commit_row={row is not None} dedup={drow}")

    # ---- (c) resubmit committed id in a LATER batch ----
    n0, d0 = counts()
    rc, ic = run_batch(
        [{"op_id": oid_a, "kind": "EDIT", "payload": dict(pay_a),
          "disclosure": {"leg": "t4c"}, "approval_ref": None, "artifacts": ()}], "c")
    if rc is not None:
        check("c-committed", rc[0]["status"] == "committed", f"{rc[0]}")
        if ra is not None:
            check("c-same-outcome", rc[0].get("outcome") == ra[0].get("outcome")
                  and rc[0].get("triple") == ra[0].get("triple"),
                  f"{str(rc[0])[:150]}")
        print(f"INFO c: path={ic['path']}")
    n1, d1 = counts()
    check("c-no-new-row", (n1 - n0, d1 - d0) == (0, 0), f"commits+{n1 - n0} dedup+{d1 - d0}")

    # ---- (d) unknown-kind ref-less op in batch: D12b terminal, no abort ----
    oid_d0 = mint_v7(base_ms + 20, rng.getrandbits(12), rng.getrandbits(62))
    oid_d1 = mint_v7(base_ms + 21, rng.getrandbits(12), rng.getrandbits(62))
    oid_d2 = mint_v7(base_ms + 22, rng.getrandbits(12), rng.getrandbits(62))
    n0, d0 = counts()
    rd, idd = run_batch(
        [{"op_id": oid_d0, "kind": "EDIT", "payload": {"body": "t4d-0"},
          "disclosure": {"leg": "t4d"}, "approval_ref": None, "artifacts": ()},
         {"op_id": oid_d1, "kind": "BOGUS_KIND_X", "payload": {"body": "t4d-bogus"},
          "disclosure": {"leg": "t4d"}, "approval_ref": None, "artifacts": ()},
         {"op_id": oid_d2, "kind": "EDIT", "payload": {"body": "t4d-2"},
          "disclosure": {"leg": "t4d"}, "approval_ref": None, "artifacts": ()}], "d")
    if rd is not None:
        check("d-statuses", [r["status"] for r in rd] == ["committed", "terminal", "committed"],
              f"{[r['status'] for r in rd]} {str(rd[1])[:150]}")
        check("d-code", rd[1].get("code") == "APPROVAL_MISSING",
              f"{str(rd[1])[:150]}")
        check("d-no-abort", idd["path"] == "batch" and idd["abort"] is None,
              f"path={idd['path']} abort={idd['abort']}")
    n1, d1 = counts()
    check("d-delta", (n1 - n0, d1 - d0) == (2, 3), f"commits+{n1 - n0} dedup+{d1 - d0}")
    con = store.open_db()
    try:
        st = con.execute("SELECT state FROM dedup WHERE op_id=?", (oid_d1,)).fetchone()
    finally:
        con.close()
    check("d-terminal-row", st is not None and st[0] == "TERMINAL_REJECTED", f"{st}")

    fence.release()
    if fails:
        print("RESULT:", f"FAIL {fails}")
        return 1
    if blocked:
        print("RESULT:", f"BLOCKED {blocked}")
        return 2
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
