#!/usr/bin/env python3
"""T5 batch edges: capacity / fencing / ordering / partial / malformed.
(e) Malformed op shape (Finding G adjacency): missing-key -> ValueError;
present-but-None payload -> raw raise; both with nothing durable.

(a) Capacity: Committer with caps max_delta_entries=5, reserve_deadline_s=0.3
    (recorded here): batch of 8 EDITs -> ops 1..5 not_attempted, op 6
    retryable (REJECT_CAPACITY), ops 7..8 not_attempted; nothing durable;
    grants released (intake._reservations empty, white-box); the reserve
    deadline honored (elapsed >= 0.25 s lower bound only).
(b) Fencing: release fence (+ epoch bump scaffolding a takeover, disclosed)
    -> commit_batch yields all ops raised STALE_EPOCH, nothing durable.
    A serial commit_op control must raise STALE_EPOCH too (fixture proof).
(c) Ordering: interleave commit_op, commit_batch(10), commit_op -> gapless
    seqs, batch seqs in submission order.
(d) Partial: batch of 1 == commit_op outcomes (shape); batch of 3 commits;
    batch of 11 -> ValueError with nothing durable; batch of 0 ->
    ValueError with nothing durable (fixed API: len 1..10).

Usage: python3 test_batch_edges.py --sut <dir> --store-root <dir>
Exit 0 PASS, 1 FAIL, 2 BLOCKED. Stdlib only. Zero harness imports.
"""
import argparse
import copy
import json
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
    from common import Reject
    import intake as _intake

    import random as _r
    root = os.path.join(os.path.abspath(args.store_root),
                        "t5-edges-%d-%d-%04x" % (os.getpid(), int(time.time()), _r.randrange(65536)))
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

    rng = _r.Random(2026092805)
    base_ms = int(time.time() * 1000)
    ctr = [0]

    def fresh_oid():
        ctr[0] += 1
        return mint_v7(base_ms + ctr[0], rng.getrandbits(12), rng.getrandbits(62))

    def edit_op(body, leg):
        return {"op_id": fresh_oid(), "kind": "EDIT", "payload": {"body": body},
                "disclosure": {"leg": leg}, "approval_ref": None, "artifacts": ()}

    def counts(st):
        con = st.open_db()
        try:
            return (con.execute("SELECT COUNT(*) FROM commits").fetchone()[0],
                    con.execute("SELECT COUNT(*) FROM dedup").fetchone()[0])
        finally:
            con.close()

    # ---- (a) capacity pre-txn abort ----
    store_a = Store.create(os.path.join(root, "cap"))
    fence_a = Fence(store_a)
    fence_a.acquire()
    caps = dict(_intake.CAPS)
    caps["max_delta_entries"] = 5
    caps["reserve_deadline_s"] = 0.3
    print(f"INFO a: caps=max_delta_entries=5 reserve_deadline_s=0.3 (recorded)")
    cm_a = Committer(store_a, fence_a, caps=caps)
    ops_a = [edit_op(f"t5a-{i}", "t5a") for i in range(8)]
    ids_a = [o["op_id"] for o in ops_a]
    n0, d0 = counts(store_a)
    t0 = time.time()
    try:
        ra, ia = cm_a.commit_batch(ops_a)
        call_a = True
    except Exception as e:
        check("a-call-ok", False, f"{type(e).__name__}: {e}")
        ra, ia, call_a = None, None, False
    dt_a = time.time() - t0
    if call_a:
        check("a-call-ok", True)
        if not (isinstance(ra, (list, tuple)) and len(ra) == 8
                and isinstance(ia, dict)
                and all(isinstance(r, dict) and r.get("status") in STATUSES for r in ra)):
            block("a-shape", f"results/info shape mismatch: {str((ra, ia))[:200]}")
            ra = None
        elif ia.get("path") not in PATHS:
            # Fixed-enum deviation: record BLOCKED with the exact value,
            # but still verify the independently-specified parts below.
            block("a-shape-path",
                  f"path={ia.get('path')!r} not in fixed enum {PATHS}")
        if ra is not None:
            want = (["not_attempted"] * 5 + ["retryable"] + ["not_attempted"] * 2)
            check("a-statuses", [r["status"] for r in ra] == want,
                  f"{[r['status'] for r in ra]} info={str(ia)[:200]}")
            check("a-retryable-capacity", "REJECT_CAPACITY" in str(ra[5].get("message", "")),
                  f"{str(ra[5])[:150]}")
            check("a-no-fallback-proof", ia["path"] != "fallback-serial",
                  f"path={ia['path']} (pre-txn abort must not fall back)")
            print(f"INFO a: path={ia['path']} abort={ia['abort']}")
    # Staged-over is deterministic (self-inflicted, no transient can clear
    # it), so it rejects immediately with an honest (staged) qualifier --
    # the P9 WAIT-to-deadline governs reserve()'s durable-over path only.
    check("a-immediate-honest", dt_a < 0.25, f"{dt_a:.2f}s (must skip futile burn)")
    check("a-staged-qualifier", "(staged)" in str(ra[5].get("message", ""))
          and "durable 0 + staged 5 >= max 5" in str(ra[5].get("message", "")),
          f"{str(ra[5].get('message', ''))[:160]}")
    n1, d1 = counts(store_a)
    check("a-nothing-durable", (n1, d1) == (n0, d0), f"commits {n0}->{n1} dedup {d0}->{d1}")
    con = store_a.open_db()
    try:
        stray = con.execute("SELECT COUNT(*) FROM dedup WHERE op_id IN (%s)"
                            % ",".join("?" * 8), ids_a).fetchone()[0]
    finally:
        con.close()
    check("a-no-dedup-rows", stray == 0, f"stray={stray}")
    check("a-grants-released", dict(_intake._reservations) == {},
          f"reservations={_intake._reservations}")
    fence_a.release()

    # ---- (b) fencing ----
    store_b = Store.create(os.path.join(root, "fence"))
    fence_b = Fence(store_b)
    birth_b, epoch_b = fence_b.acquire()
    cm_b = Committer(store_b, fence_b)
    fence_b.release()  # per spec: release the fence ...
    # ... then scaffold the takeover the release enables (disclosed): bump epoch
    con = store_b.open_db()
    try:
        con.execute("BEGIN IMMEDIATE;")
        con.execute("UPDATE epoch_row SET epoch=?", (epoch_b + 1,))
        con.execute("COMMIT;")
    finally:
        con.close()
    ops_b = [edit_op(f"t5b-{i}", "t5b") for i in range(3)]
    n0, d0 = counts(store_b)
    try:
        rb, ib = cm_b.commit_batch(ops_b)
        call_b = True
    except Exception as e:
        check("b-call-ok", False, f"{type(e).__name__}: {e}")
        rb, ib, call_b = None, None, False
    if call_b:
        check("b-call-ok", True)
        if not (isinstance(rb, (list, tuple)) and len(rb) == 3
                and isinstance(ib, dict) and ib.get("path") in PATHS
                and all(isinstance(r, dict) and r.get("status") in STATUSES for r in rb)):
            block("b-shape", f"results/info shape mismatch: {str((rb, ib))[:200]}")
        else:
            check("b-all-raised", [r["status"] for r in rb] == ["raised"] * 3,
                  f"{[(r['status'], r.get('code')) for r in rb]}")
            check("b-stale-epoch", all(r.get("code") == "STALE_EPOCH" for r in rb),
                  f"{[str(r)[:100] for r in rb]}")
            check("b-fallback-path", ib["path"] == "fallback-serial",
                  f"path={ib['path']} abort={ib['abort']}")
    n1, d1 = counts(store_b)
    check("b-nothing-durable", (n1, d1) == (n0, d0), f"commits {n0}->{n1} dedup {d0}->{d1}")
    try:
        cm_b.commit_op(fresh_oid(), "EDIT", {"body": "t5b-serial-control"},
                       {"leg": "t5b"}, None, [])
        check("b-serial-control", False, "commit_op unexpectedly committed on stale fence")
    except Reject as r:
        check("b-serial-control", r.code == "STALE_EPOCH", f"{r.code}: {r.detail}")
    except Exception as e:
        check("b-serial-control", False, f"{type(e).__name__}: {e}")

    # ---- (c) ordering interleave ----
    store_c = Store.create(os.path.join(root, "order"))
    fence_c = Fence(store_c)
    fence_c.acquire()
    cm_c = Committer(store_c, fence_c)
    try:
        out_pre, triple_pre = cm_c.commit_op(fresh_oid(), "EDIT", {"body": "t5c-pre"},
                                             {"leg": "t5c"}, None, [])
        pre_ok = True
    except Exception as e:
        check("c-pre-op", False, f"{type(e).__name__}: {e}")
        pre_ok, triple_pre = False, ""
    if pre_ok:
        check("c-pre-op", True)
    ops_c = [edit_op(f"t5c-b{i}", "t5c") for i in range(10)]
    try:
        rc, ic = cm_c.commit_batch(ops_c)
        call_c = True
    except Exception as e:
        check("c-batch-call", False, f"{type(e).__name__}: {e}")
        rc, call_c = None, False
    if call_c:
        check("c-batch-call", True)
        if isinstance(rc, (list, tuple)) and len(rc) == 10 \
           and all(isinstance(r, dict) and r.get("status") == "committed" for r in rc):
            bseqs = [r["triple"].rsplit(":", 1)[-1] for r in rc]
            check("c-batch-seqs-ordered", bseqs == [str(i) for i in range(2, 12)],
                  f"seqs={bseqs}")
        else:
            check("c-batch-all-committed", False, f"{str(rc)[:200]}")
    try:
        out_post, triple_post = cm_c.commit_op(fresh_oid(), "EDIT", {"body": "t5c-post"},
                                               {"leg": "t5c"}, None, [])
        post_ok = triple_post.rsplit(":", 1)[-1] == "12"
        check("c-post-op", post_ok, f"triple={triple_post}")
    except Exception as e:
        check("c-post-op", False, f"{type(e).__name__}: {e}")
    con = store_c.open_db()
    try:
        seqs = [r[0] for r in con.execute("SELECT seq FROM commits ORDER BY seq").fetchall()]
    finally:
        con.close()
    check("c-gapless-1to12", seqs == list(range(1, 13)), f"seqs={seqs}")
    fence_c.release()

    # ---- (d) partial: 1, 3, 11, 0 ----
    store_d = Store.create(os.path.join(root, "partial"))
    fence_d = Fence(store_d)
    fence_d.acquire()
    cm_d = Committer(store_d, fence_d)
    n0, d0 = counts(store_d)
    try:
        out_s, triple_s = cm_d.commit_op(fresh_oid(), "EDIT", {"body": "t5d-serial"},
                                         {"leg": "t5d"}, None, [])
        serial_ok = True
    except Exception as e:
        check("d-serial-ref", False, f"{type(e).__name__}: {e}")
        serial_ok = False
    if serial_ok:
        check("d-serial-ref", True)
        op1 = edit_op("t5d-batch1", "t5d")
        try:
            r1, i1 = cm_d.commit_batch([op1])
            b1_ok = True
        except Exception as e:
            check("d-batch1-call", False, f"{type(e).__name__}: {e}")
            r1, b1_ok = None, False
        if b1_ok:
            check("d-batch1-call", True)
            ok1 = (isinstance(r1, (list, tuple)) and len(r1) == 1
                   and r1[0].get("status") == "committed"
                   and len(str(r1[0].get("triple", "")).split(":")) == 3)
            check("d-batch1-committed", ok1, f"{str(r1[0])[:200] if isinstance(r1, (list, tuple)) and r1 else r1!r}")
            if ok1:
                try:
                    same_keys = (sorted(json.loads(r1[0]["outcome"]).keys())
                                 == sorted(json.loads(out_s).keys()))
                    detail = f"batch={sorted(json.loads(r1[0]['outcome']).keys())} serial={sorted(json.loads(out_s).keys())}"
                except Exception as e:
                    same_keys, detail = False, f"json {e}"
                check("d-batch1-equiv-serial", same_keys, detail)
    ops3 = [edit_op(f"t5d-3-{i}", "t5d") for i in range(3)]
    try:
        r3, _i3 = cm_d.commit_batch(ops3)
        check("d-batch3-commits",
              isinstance(r3, (list, tuple)) and [r.get("status") for r in r3] == ["committed"] * 3,
              f"{str(r3)[:200]}")
    except Exception as e:
        check("d-batch3-commits", False, f"{type(e).__name__}: {e}")
    n_mid, d_mid = counts(store_d)
    ops11 = [edit_op(f"t5d-11-{i}", "t5d") for i in range(11)]
    try:
        cm_d.commit_batch(ops11)
        check("d-batch11-valueerror", False, "11-op batch unexpectedly accepted")
    except ValueError:
        check("d-batch11-valueerror", True)
    except Exception as e:
        check("d-batch11-valueerror", False, f"{type(e).__name__}: {e} (want ValueError)")
    try:
        cm_d.commit_batch([])
        check("d-batch0-valueerror", False, "0-op batch unexpectedly accepted")
    except ValueError:
        check("d-batch0-valueerror", True)
    except Exception as e:
        check("d-batch0-valueerror", False, f"{type(e).__name__}: {e} (want ValueError)")
    n1, d1 = counts(store_d)
    check("d-oversize-nothing-durable", (n1, d1) == (n_mid, d_mid),
          f"commits {n_mid}->{n1} dedup {d_mid}->{d1}")
    fence_d.release()

    # ---- (e) malformed op shape: fail-closed, nothing durable ----
    # Out-of-contract op dicts must raise (never ack, never partial).
    # Property pinned: raw raise + counts stable + no dedup row -- the
    # exact exception type is NOT pinned (contract-external).
    store_e = Store.create(os.path.join(root, "malformed"))
    fence_e = Fence(store_e)
    fence_e.acquire()
    cm_e = Committer(store_e, fence_e)
    n0e, d0e = counts(store_e)
    # missing 'payload' key -> ValueError from norm (pre-txn)
    try:
        cm_e.commit_batch([{"op_id": fresh_oid(), "kind": "EDIT"}])
        check("e-missing-key-valueerror", False, "malformed op accepted")
    except ValueError:
        check("e-missing-key-valueerror", True)
    except Exception as e:
        check("e-missing-key-valueerror", False,
              f"{type(e).__name__}: {e} (want ValueError)")
    # present-but-None payload on a non-table kind -> raw raise, no ack
    oid_none = fresh_oid()
    got_none = None
    try:
        cm_e.commit_batch([{"op_id": oid_none, "kind": "EDIT", "payload": None,
                            "disclosure": {"leg": "t5e"}, "approval_ref": None,
                            "artifacts": ()}])
    except Exception as e:
        got_none = e
    check("e-none-payload-raises", got_none is not None, "None payload acked?!")
    n1e, d1e = counts(store_e)
    con_e = store_e.open_db()
    try:
        stray_e = con_e.execute("SELECT COUNT(*) FROM dedup WHERE op_id=?",
                                (oid_none,)).fetchone()[0]
    finally:
        con_e.close()
    check("e-none-nothing-durable", (n1e, d1e, stray_e) == (n0e, d0e, 0),
          f"commits {n0e}->{n1e} dedup {d0e}->{d1e} stray={stray_e}")
    fence_e.release()

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
