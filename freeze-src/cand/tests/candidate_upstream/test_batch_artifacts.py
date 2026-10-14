#!/usr/bin/env python3
"""T9 batch artifacts (red-team Finding D).

(a) Success: prepare_artifact + commit_batch([EDIT with artifacts]) ->
    committed; artifacts + pub_refs rows durable with matching columns.
(b) Missing artifact -> in-txn Reject(ARTIFACT_NOT_DURABLE) ->
    path=fallback-serial, per-op status raised + code (non-F6).
(c) Shared artifact_id across two ops in one batch -> raw
    sqlite3.IntegrityError (not Reject/Retryable) + atomic ROLLBACK:
    nothing durable (specified batch semantic: all-or-nothing; the
    serial twin would partial-commit then raise).

Usage: python3 test_batch_artifacts.py --sut <dir> --store-root <dir>
Exit 0 PASS, 1 FAIL, 2 BLOCKED. Stdlib only. Zero harness imports.
"""
import argparse
import os
import sqlite3
import sys
import time

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
            print("RESULT: BLOCKED [sut-missing]")
            return 2
    sys.path.insert(0, sut)
    from store import Store, Fence
    from committer import Committer, prepare_artifact
    from common import Reject, Retryable

    import random as _r
    root = os.path.join(os.path.abspath(args.store_root),
                        "t9-art-%d-%d-%04x" % (os.getpid(), int(time.time()), _r.randrange(65536)))
    os.makedirs(root, exist_ok=False)

    fails = []

    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {detail}"))
        if not cond:
            fails.append(name)

    if not hasattr(Committer, "commit_batch"):
        print("BLOCKED: Committer has no commit_batch")
        print("RESULT: BLOCKED [api-commit_batch-missing]")
        return 2

    rng = _r.Random(2026092809)

    def fresh_oid():
        return mint_v7(int(time.time() * 1000), rng.getrandbits(12), rng.getrandbits(62))

    # ---- (a) success path ----
    store_a = Store.create(os.path.join(root, "a"))
    fence_a = Fence(store_a)
    fence_a.acquire()
    cm_a = Committer(store_a, fence_a)
    body_a = bytes(range(96))
    meta_a = prepare_artifact(store_a, body_a, "t9")
    oid_a = fresh_oid()
    try:
        ra, ia = cm_a.commit_batch([{"op_id": oid_a, "kind": "EDIT",
                                     "payload": {"body": "t9a"},
                                     "disclosure": {"leg": "t9a"},
                                     "approval_ref": None,
                                     "artifacts": (meta_a,)}])
        call_a = True
    except Exception as e:
        check("a-batch-call-ok", False, f"{type(e).__name__}: {e}")
        ra, ia, call_a = None, None, False
    if call_a:
        check("a-batch-call-ok", True)
        check("a-path-batch", ia["path"] == "batch", f"path={ia['path']}")
        check("a-committed", ra[0]["status"] == "committed", str(ra[0])[:150])
        seq_a = ra[0].get("triple", "").rsplit(":", 1)[-1]
        con = store_a.open_db()
        try:
            arow = con.execute("SELECT artifact_id,store_id,extent,length,digest,"
                               "durable,op_seq FROM artifacts WHERE artifact_id=?",
                               (meta_a["artifact_id"],)).fetchone()
            prow = con.execute("SELECT seq,artifact_id FROM pub_refs WHERE artifact_id=?",
                               (meta_a["artifact_id"],)).fetchone()
        finally:
            con.close()
        check("a-artifact-row", arow is not None and arow[1] == "t9"
              and arow[3] == 96 and arow[4] == meta_a["digest"]
              and arow[5] == 1 and str(arow[6]) == seq_a, str(arow)[:200])
        check("a-pubref-row", prow is not None and str(prow[0]) == seq_a,
              str(prow)[:120])
    fence_a.release()

    # ---- (b) missing artifact -> fallback-serial + raised ----
    store_b = Store.create(os.path.join(root, "b"))
    fence_b = Fence(store_b)
    fence_b.acquire()
    cm_b = Committer(store_b, fence_b)
    fake_meta = {"artifact_id": "a-missing-%s" % rng.getrandbits(32),
                 "store_id": "t9", "extent": "whole-immutable-file",
                 "length": 96,
                 "digest": "sha256:" + "00" * 32}
    oid_b = fresh_oid()
    try:
        rb, ib = cm_b.commit_batch([{"op_id": oid_b, "kind": "EDIT",
                                     "payload": {"body": "t9b"},
                                     "disclosure": {"leg": "t9b"},
                                     "approval_ref": None,
                                     "artifacts": (fake_meta,)}])
        call_b = True
    except Exception as e:
        check("b-batch-call-ok", False, f"{type(e).__name__}: {e}")
        rb, ib, call_b = None, None, False
    if call_b:
        check("b-batch-call-ok", True)
        check("b-path-fallback", ib["path"] == "fallback-serial",
              f"path={ib['path']} abort={ib['abort']}")
        check("b-raised-artifact", rb[0]["status"] == "raised"
              and rb[0].get("code") == "ARTIFACT_NOT_DURABLE",
              str(rb[0])[:150])
        # serial twin must show the same per-op outcome
        tstore = Store.create(os.path.join(root, "b-twin"))
        tfence = Fence(tstore)
        tfence.acquire()
        tcm = Committer(tstore, tfence)
        try:
            tcm.commit_op(oid_b, "EDIT", {"body": "t9b"}, {"leg": "t9b"},
                          None, [fake_meta])
            check("b-twin-raises", False, "twin unexpectedly committed")
        except Reject as r:
            check("b-twin-raises", r.code == "ARTIFACT_NOT_DURABLE",
                  f"{r.code}: {r.detail}")
        except Retryable as r:
            check("b-twin-raises", False, f"Retryable: {r}")
        tfence.release()
    fence_b.release()

    # ---- (c) shared artifact_id -> raw IntegrityError + atomic ROLLBACK --
    store_c = Store.create(os.path.join(root, "c"))
    fence_c = Fence(store_c)
    fence_c.acquire()
    cm_c = Committer(store_c, fence_c)
    meta_c = prepare_artifact(store_c, bytes(range(64, 128)), "t9")
    oids_c = [fresh_oid(), fresh_oid()]
    ops_c = [{"op_id": i, "kind": "EDIT", "payload": {"body": "t9c"},
              "disclosure": {"leg": "t9c"}, "approval_ref": None,
              "artifacts": (meta_c,)} for i in oids_c]
    got_c = None
    try:
        cm_c.commit_batch(ops_c)
    except Exception as e:
        got_c = e
    check("c-raw-integrity-error", isinstance(got_c, sqlite3.IntegrityError),
          f"{type(got_c).__name__}: {str(got_c)[:100]}"
          if got_c else "no raise (committed?!)")
    check("c-not-reject-retryable", not isinstance(got_c, (Reject, Retryable)),
          type(got_c).__name__ if got_c else "none")
    con = store_c.open_db()
    try:
        n_c = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        stray = con.execute("SELECT COUNT(*) FROM dedup WHERE op_id IN (?,?)",
                            oids_c).fetchone()[0]
        arows = con.execute("SELECT COUNT(*) FROM artifacts WHERE artifact_id=?",
                            (meta_c["artifact_id"],)).fetchone()[0]
    finally:
        con.close()
    check("c-nothing-durable", (n_c, stray, arows) == (0, 0, 0),
          f"commits={n_c} stray={stray} artifact_rows={arows}")
    fence_c.release()

    if fails:
        print("RESULT:", f"FAIL {fails}")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
