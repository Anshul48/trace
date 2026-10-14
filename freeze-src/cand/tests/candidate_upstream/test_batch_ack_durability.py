#!/usr/bin/env python3
"""T1 batch ack durability: durability-before-ACK + no acked loss + reconcile.

(a) commit_batch of 10 EDITs -> all committed; re-open store on a new
    connection PLUS one subprocess re-open and assert every outcome durable
    (dedup COMMITTED + commits rows + notify() returns each outcome).
(b) Response-lost reconcile: commit a batch's ops serially via commit_op
    (durable), then invoke Committer._reconcile_batch(con, ops) on those same
    op_ids -> committed outcomes reconstructed, no new rows. If the helper is
    missing -> BLOCKED (spec-coded name, do not guess).
(c) Same-ID resubmit of a committed op in a NEW batch -> COMMITTED outcome,
    no new row.

Usage: python3 test_batch_ack_durability.py --sut <dir> --store-root <dir>
Exit 0 PASS, 1 FAIL, 2 BLOCKED. Stdlib only. Zero harness imports.
"""
import argparse
import json
import os
import sqlite3
import subprocess
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
                        "t1-ackdur-%d-%d-%04x" % (os.getpid(), int(time.time()), _r.randrange(65536)))
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

    rng = _r.Random(2026092801)
    store = Store.create(os.path.join(root, "main"))
    fence = Fence(store)
    fence.acquire()
    cm = Committer(store, fence)

    def validate_call(results, batch_info, n, tag):
        """Structural shape check per fixed API. Returns True if shape OK.
        Shape mismatch -> BLOCKED (spec: do not adapt to a guessed API)."""
        if not (isinstance(results, (list, tuple)) and len(results) == n):
            block(f"{tag}-shape-results",
                  f"results len/type mismatch: {type(results)} len={getattr(results, '__len__', lambda: '?')()}")
            return False
        if not isinstance(batch_info, dict):
            block(f"{tag}-shape-batchinfo", f"batch_info not a dict: {type(batch_info)}")
            return False
        for k in ("path", "batch_size", "abort", "reserve_outcomes"):
            if k not in batch_info:
                block(f"{tag}-shape-batchinfo", f"batch_info missing key {k}: {sorted(batch_info)}")
                return False
        if batch_info["path"] not in PATHS:
            block(f"{tag}-shape-path", f"path={batch_info['path']!r} not in {PATHS}")
            return False
        for i, res in enumerate(results):
            if not isinstance(res, dict) or "op_id" not in res or "status" not in res:
                block(f"{tag}-shape-result-{i}", f"result keys={sorted(res) if isinstance(res, dict) else type(res)}")
                return False
            if res["status"] not in STATUSES:
                block(f"{tag}-shape-status-{i}", f"status={res['status']!r} not in {STATUSES}")
                return False
        return True

    # ---- (a) batch of 10 EDITs, all committed ----
    now = time.time()
    oids_a = [mint_v7(int(now * 1000) + i, rng.getrandbits(12), rng.getrandbits(62)) for i in range(10)]
    ops_a = [{"op_id": o, "kind": "EDIT", "payload": {"body": f"t1a-{i}"},
              "disclosure": {"leg": "t1a"}, "approval_ref": None, "artifacts": ()}
             for i, o in enumerate(oids_a)]
    try:
        results_a, info_a = cm.commit_batch(ops_a)
        call_a_ok = True
    except Exception as e:  # unexpected raise from the SUT call is a FAIL
        check("a-batch-call-ok", False, f"{type(e).__name__}: {e}")
        results_a, info_a, call_a_ok = None, None, False
    if call_a_ok:
        shape_ok = validate_call(results_a, info_a, 10, "a")
        if shape_ok:
            check("a-all-committed",
                  all(r["status"] == "committed" for r in results_a),
                  f"{[(r['op_id'][:8], r['status']) for r in results_a]}")
            check("a-path-batch", info_a["path"] == "batch", f"path={info_a['path']}")
            check("a-abort-none", info_a["abort"] is None, f"abort={info_a['abort']}")
            triples = [r.get("triple", "") for r in results_a]
            seqs = [t.rsplit(":", 1)[-1] for t in triples]
            check("a-seqs-1to10", seqs == [str(i) for i in range(1, 11)],
                  f"seqs={seqs}")
            for r in results_a:
                if r["status"] == "committed" and ("outcome" not in r or "triple" not in r):
                    check("a-committed-keys", False, f"keys={sorted(r)}")
                    break
            else:
                check("a-committed-keys", True)

    # durability: new connection in-process
    con = store.open_db()
    try:
        n_commits = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        rows = con.execute("SELECT op_id,state,outcome FROM dedup WHERE op_id IN (%s)"
                           % ",".join("?" * 10), oids_a).fetchall()
    finally:
        con.close()
    check("a-commits-10", n_commits == 10, f"COUNT={n_commits}")
    check("a-dedup-10-committed",
          len(rows) == 10 and all(r[1] == "COMMITTED" for r in rows),
          f"dedup={[(r[0][:8], r[1]) for r in rows]}")

    # durability: subprocess re-open + notify() per outcome
    notify_ok, notify_detail = True, ""
    for o in oids_a:
        try:
            out, triple = cm.notify(o)
            if '"committed": true' not in out:
                notify_ok, notify_detail = False, f"{o[:8]} outcome={out[:50]}"
                break
        except Exception as e:
            notify_ok, notify_detail = False, f"{o[:8]} {type(e).__name__}: {e}"
            break
    check("a-notify-all", notify_ok, notify_detail)
    sub = subprocess.run(
        [sys.executable, "-c",
         "import sys,sqlite3; sys.dont_write_bytecode=True; "
         "con=sqlite3.connect(sys.argv[1],timeout=30.0); "
         "print(con.execute('SELECT COUNT(*) FROM commits').fetchone()[0]); "
         "print(con.execute(\"SELECT COUNT(*) FROM dedup WHERE state='COMMITTED'\").fetchone()[0])",
         os.path.join(store.root, "commit.db")],
        capture_output=True, text=True, timeout=60)
    try:
        c1, c2 = (int(x) for x in sub.stdout.strip().split())
        check("a-subprocess-reopen", (c1, c2) == (10, 10),
              f"stdout={sub.stdout.strip()!r} stderr={sub.stderr.strip()[:100]!r}")
    except Exception as e:
        check("a-subprocess-reopen", False, f"parse {e}: stdout={sub.stdout!r} stderr={sub.stderr[:100]!r}")

    # ---- (b) response-lost reconcile via _reconcile_batch ----
    if not hasattr(Committer, "_reconcile_batch"):
        block("b-reconcile-helper-missing",
              "Committer has no attribute _reconcile_batch (spec-coded name)")
    else:
        now = time.time()
        oids_b = [mint_v7(int(now * 1000) + 100 + i, rng.getrandbits(12), rng.getrandbits(62)) for i in range(4)]
        ops_b = [{"op_id": o, "kind": "EDIT", "payload": {"body": f"t1b-{i}"},
                  "disclosure": {"leg": "t1b"}, "approval_ref": None, "artifacts": ()}
                 for i, o in enumerate(oids_b)]
        serial_ok = True
        try:
            for op in ops_b:
                cm.commit_op(op["op_id"], op["kind"], op["payload"], op["disclosure"], None, [])
        except Exception as e:
            check("b-serial-setup", False, f"{type(e).__name__}: {e}")
            serial_ok = False
        if serial_ok:
            check("b-serial-setup", True)
            con = store.open_db()
            try:
                n_before = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
                d_before = con.execute("SELECT COUNT(*) FROM dedup").fetchone()[0]
            finally:
                con.close()
            # The spec fixes only the helper NAME and the SEMANTICS
            # ("committed outcomes reconstructed"), not the return shape:
            # accept either {op_id: verdict} or [per-op outcomes] and
            # assert the semantic content (committed outcome + triple).
            rcon = store.open_db()
            try:
                rec = cm._reconcile_batch(rcon, list(oids_b))
                rec_ok = True
            except Exception as e:
                check("b-reconcile-call-ok", False, f"{type(e).__name__}: {e}")
                rec, rec_ok = None, False
            finally:
                rcon.close()
            if rec_ok:
                check("b-reconcile-call-ok", True)
                got = {}
                if isinstance(rec, dict):
                    for oid in oids_b:
                        v = rec.get(oid)
                        if isinstance(v, dict) and v.get("status") in ("match", "committed") \
                           and v.get("outcome") and v.get("triple"):
                            got[oid] = (v["outcome"], v["triple"])
                elif isinstance(rec, (list, tuple)):
                    for r in rec:
                        if isinstance(r, dict) and r.get("status") == "committed" \
                           and r.get("op_id") in oids_b and r.get("outcome") \
                           and r.get("triple"):
                            got[r["op_id"]] = (r["outcome"], r["triple"])
                else:
                    check("b-reconcile-shape", False,
                          f"unrecognized return: {type(rec)} {str(rec)[:150]}")
                if isinstance(rec, (dict, list, tuple)):
                    check("b-reconcile-shape", True)
                    check("b-reconcile-committed", len(got) == 4,
                          f"reconstructed={len(got)}/4 :: {str(rec)[:250]}")
                    if len(got) == 4:
                        bodies_ok = all('"committed": true' in o for o, _t in got.values())
                        check("b-reconcile-bodies", bodies_ok,
                              f"{[o[:60] for o, _t in got.values()]}")
            con = store.open_db()
            try:
                n_after = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
                d_after = con.execute("SELECT COUNT(*) FROM dedup").fetchone()[0]
            finally:
                con.close()
            check("b-no-new-rows", (n_after, d_after) == (n_before, d_before),
                  f"commits {n_before}->{n_after} dedup {d_before}->{d_after}")

    # ---- (c) same-ID resubmit of a committed op in a NEW batch ----
    con = store.open_db()
    try:
        n_c0 = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        d_c0 = con.execute("SELECT COUNT(*) FROM dedup").fetchone()[0]
    finally:
        con.close()
    ops_c = [{"op_id": oids_a[0], "kind": "EDIT", "payload": {"body": "t1a-0"},
              "disclosure": {"leg": "t1c"}, "approval_ref": None, "artifacts": ()}]
    try:
        results_c, info_c = cm.commit_batch(ops_c)
        call_c_ok = True
    except Exception as e:
        check("c-resubmit-call-ok", False, f"{type(e).__name__}: {e}")
        results_c, call_c_ok = None, False
    if call_c_ok:
        check("c-resubmit-call-ok", True)
        if validate_call(results_c, info_c, 1, "c"):
            check("c-committed-outcome", results_c[0]["status"] == "committed",
                  f"{results_c[0]}")
            if call_a_ok and shape_ok:
                check("c-same-outcome", results_c[0].get("outcome") == results_a[0].get("outcome")
                      and results_c[0].get("triple") == results_a[0].get("triple"),
                      f"{str(results_c[0])[:160]}")
    con = store.open_db()
    try:
        n_c1 = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        d_c1 = con.execute("SELECT COUNT(*) FROM dedup").fetchone()[0]
    finally:
        con.close()
    check("c-no-new-row", (n_c1, d_c1) == (n_c0, d_c0),
          f"commits {n_c0}->{n_c1} dedup {d_c0}->{d_c1}")

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
