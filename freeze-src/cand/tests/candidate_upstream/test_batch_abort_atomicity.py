#!/usr/bin/env python3
"""T2 batch abort atomicity: mid-batch abort, no partial commit.

(a) Batch [EDIT, EDIT, RETRACT+stage1ref, EDIT, EDIT] where the RETRACT
    carries approval_ref={"stage": 1, "policy_version": "v0"}: the gate
    takes the table path (not early-terminal) and raises
    STAGE1_NOT_ALLOWLISTED (F6.1; allowlist v0 admits nothing). Expect
    path=fallback-serial, abort recorded at index 2; final per-op
    outcomes: EDITs committed (seqs gapless), RETRACT terminal
    STAGE1_NOT_ALLOWLISTED.
    NOTE (spec friction, coded deliberately): the spec text wrote
    {"stage": 1}; under the frozen gate _pinned_policy_ok runs first,
    so that literal ref yields POLICY_STALE, not STAGE1_NOT_ALLOWLISTED.
    The pinned policy_version above is what deterministically yields the
    spec's expected code; T6 pins gate identity old-vs-new.
(b) No-partial proof: snapshot commits COUNT + max_seq + dedup rows for
    the batch ids BEFORE, run the batch, then verify the ONLY durable
    delta vs before is exactly the fallback's serial effects, recomputed
    by running the same 5 ops pure-serially on a TWIN store from
    identical pre-state. Committed sets + outcomes must MATCH exactly
    (triples normalized to seq: births differ across stores).
(c) Mid-batch Retryable (Finding E): [ok EDIT, future-ts EDIT] ->
    fallback-serial, [committed, retryable REJECT_CLOCK], no WAIT burn,
    serial-twin shape match.
(d) Reservation release before fallback (Finding C):
    max_reservations=1 + aborting single-op batch -> fallback must GRANT
    (batch token released first), yielding terminal STAGE1_NOT_ALLOWLISTED,
    not a WAIT-burned REJECT_CAPACITY(deadline).

Usage: python3 test_batch_abort_atomicity.py --sut <dir> --store-root <dir>
Exit 0 PASS, 1 FAIL, 2 BLOCKED. Stdlib only. Zero harness imports.
"""
import argparse
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
    from common import Reject, Retryable

    import random as _r
    root = os.path.join(os.path.abspath(args.store_root),
                        "t2-abort-%d-%d-%04x" % (os.getpid(), int(time.time()), _r.randrange(65536)))
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

    rng = _r.Random(2026092802)
    now = time.time()
    oids = [mint_v7(int(now * 1000) + i, rng.getrandbits(12), rng.getrandbits(62)) for i in range(5)]
    stage1ref = {"stage": 1, "policy_version": "v0"}
    ops = [
        {"op_id": oids[0], "kind": "EDIT", "payload": {"body": "t2e0"},
         "disclosure": {"leg": "t2"}, "approval_ref": None, "artifacts": ()},
        {"op_id": oids[1], "kind": "EDIT", "payload": {"body": "t2e1"},
         "disclosure": {"leg": "t2"}, "approval_ref": None, "artifacts": ()},
        {"op_id": oids[2], "kind": "RETRACT", "payload": {"body": "t2retract"},
         "disclosure": {"leg": "t2"}, "approval_ref": dict(stage1ref), "artifacts": ()},
        {"op_id": oids[3], "kind": "EDIT", "payload": {"body": "t2e3"},
         "disclosure": {"leg": "t2"}, "approval_ref": None, "artifacts": ()},
        {"op_id": oids[4], "kind": "EDIT", "payload": {"body": "t2e4"},
         "disclosure": {"leg": "t2"}, "approval_ref": None, "artifacts": ()},
    ]

    store = Store.create(os.path.join(root, "main"))
    fence = Fence(store)
    fence.acquire()
    cm = Committer(store, fence)

    def snapshot(st):
        con = st.open_db()
        try:
            n = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
            mx = con.execute("SELECT COALESCE(MAX(seq),0) FROM commits").fetchone()[0]
            dd = con.execute("SELECT op_id,state FROM dedup WHERE op_id IN (%s)"
                             % ",".join("?" * len(oids)), oids).fetchall()
            return (n, int(mx), sorted((r[0], r[1]) for r in dd))
        finally:
            con.close()

    before = snapshot(store)
    try:
        results, info = cm.commit_batch(ops)
        call_ok = True
    except Exception as e:
        check("a-batch-call-ok", False, f"{type(e).__name__}: {e}")
        results, info, call_ok = None, None, False
    if not call_ok:
        fence.release()
        print("RESULT:", f"FAIL {fails}")
        return 1

    # structural shape (spec-fixed); mismatch -> BLOCKED, not adapted
    shape_ok = True
    if not (isinstance(results, (list, tuple)) and len(results) == 5):
        block("a-shape-results", f"len={getattr(results, '__len__', lambda: '?')()}")
        shape_ok = False
    if not isinstance(info, dict) or any(k not in info for k in ("path", "batch_size", "abort", "reserve_outcomes")):
        block("a-shape-batchinfo", f"{type(info)} {sorted(info) if isinstance(info, dict) else ''}")
        shape_ok = False
    elif info["path"] not in PATHS:
        block("a-shape-path", f"path={info['path']!r}")
        shape_ok = False
    if shape_ok:
        for i, res in enumerate(results):
            if not isinstance(res, dict) or res.get("status") not in STATUSES:
                block("a-shape-result", f"idx={i} res={str(res)[:120]}")
                shape_ok = False
                break
    if not shape_ok:
        fence.release()
        print("RESULT:", "BLOCKED" if not fails else f"FAIL {fails}", blocked)
        return 2 if not fails else 1

    check("a-path-fallback", info["path"] == "fallback-serial",
          f"path={info['path']} abort={info['abort']}")
    abort = info["abort"] or {}
    check("a-abort-index2", abort.get("op_index") == 2 and abort.get("op_id") == oids[2],
          f"abort={info['abort']}")
    got_status = [r["status"] for r in results]
    check("a-statuses", got_status == ["committed", "committed", "terminal", "committed", "committed"],
          f"{got_status} {str(results[2])[:150]}")
    check("a-retract-code", results[2].get("code") == "STAGE1_NOT_ALLOWLISTED",
          f"{str(results[2])[:150]}")
    cseqs = [r.get("triple", "").rsplit(":", 1)[-1] for i, r in enumerate(results) if i != 2]
    check("a-edit-seqs-gapless", cseqs == ["1", "2", "3", "4"], f"seqs={cseqs}")

    # ---- (b) twin-store equivalence ----
    tstore = Store.create(os.path.join(root, "twin"))
    tfence = Fence(tstore)
    tfence.acquire()
    tcm = Committer(tstore, tfence)
    twin_before = snapshot(tstore)
    check("b-twin-prestate-match", twin_before == before,
          f"main-before={before} twin-before={twin_before}")
    twin_outcomes = []
    twin_ok = True
    for op in ops:
        try:
            out, triple = tcm.commit_op(op["op_id"], op["kind"], op["payload"],
                                        op["disclosure"], op["approval_ref"], [])
            twin_outcomes.append(("committed", triple.rsplit(":", 1)[-1], out))
        except Reject as r:
            twin_outcomes.append(("reject", r.code, r.detail))
        except Retryable as r:
            twin_outcomes.append(("retryable", str(r), ""))
            twin_ok = False
        except Exception as e:
            check("b-twin-serial-call", False, f"{op['op_id'][:8]} {type(e).__name__}: {e}")
            twin_ok = False
            twin_outcomes.append(("error", type(e).__name__, str(e)))
    if twin_ok:
        check("b-twin-serial-call", True)
    # normalize batch run to the same shape: (kind, seq-or-code, outcome-or-detail)
    batch_norm = []
    for r in results:
        if r["status"] == "committed":
            batch_norm.append(("committed", r.get("triple", "").rsplit(":", 1)[-1], r.get("outcome", "")))
        elif r["status"] == "terminal":
            batch_norm.append(("reject", r.get("code", ""), r.get("detail", "")))
        else:
            batch_norm.append((r["status"], "", ""))
    # compare committed sets + codes + seqs (outcome JSON embeds birth: compare seq field)
    batch_cmp = [(k, v) for (k, v, _o) in batch_norm]
    twin_cmp = [(k, v) for (k, v, _o) in twin_outcomes]
    check("b-outcomes-match", batch_cmp == twin_cmp,
          f"batch={batch_cmp} twin={twin_cmp}")
    for (bk, bv, bo), (tk, tv, to) in zip(batch_norm, twin_outcomes):
        if bk == "committed" == tk:
            try:
                bj, tj = json.loads(bo), json.loads(to)
                if not (bj.get("seq") == tj.get("seq") and bj.get("kind") == tj.get("kind")):
                    check("b-outcome-bodies-match", False, f"{bo[:100]} vs {to[:100]}")
                    break
            except Exception as e:
                check("b-outcome-bodies-match", False, f"json {e}")
                break
    else:
        check("b-outcome-bodies-match", True)
    # durable-delta equality: main delta vs before == twin delta vs before
    after_main, after_twin = snapshot(store), snapshot(tstore)
    def delta(aft, bef):
        return (aft[0] - bef[0], aft[1] - bef[1],
                sorted(set(aft[2]) - set([x for x in bef[2]])))
    check("b-delta-match", delta(after_main, before) == delta(after_twin, twin_before),
          f"main-delta={delta(after_main, before)} twin-delta={delta(after_twin, twin_before)}")
    # only-delta check: twin committed set == main committed set (op_ids)
    con = store.open_db()
    try:
        main_committed = sorted(r[0] for r in con.execute("SELECT op_id FROM commits").fetchall())
    finally:
        con.close()
    tcon = tstore.open_db()
    try:
        twin_committed = sorted(r[0] for r in tcon.execute("SELECT op_id FROM commits").fetchall())
    finally:
        tcon.close()
    check("b-committed-sets-match", main_committed == twin_committed,
          f"main={len(main_committed)} twin={len(twin_committed)}")

    # ---- (c) mid-batch Retryable -> fallback-serial (Finding E) ----
    # Batch [ok EDIT, future-ts EDIT]: the second op raises REJECT_CLOCK
    # in-txn (id.ts > now + skew); the batch must ROLLBACK and fall back,
    # yielding [committed, retryable REJECT_CLOCK]. No WAIT burn: the
    # clock reject is immediate in both paths.
    store_c = Store.create(os.path.join(root, "clock"))
    fence_c = Fence(store_c)
    fence_c.acquire()
    cm_c = Committer(store_c, fence_c)
    now_c = time.time()
    oid_ok = mint_v7(int(now_c * 1000), rng.getrandbits(12), rng.getrandbits(62))
    oid_future = mint_v7(int(now_c * 1000) + 600000, rng.getrandbits(12),
                         rng.getrandbits(62))
    ops_c = [
        {"op_id": oid_ok, "kind": "EDIT", "payload": {"body": "t2c-ok"},
         "disclosure": {"leg": "t2c"}, "approval_ref": None, "artifacts": ()},
        {"op_id": oid_future, "kind": "EDIT", "payload": {"body": "t2c-future"},
         "disclosure": {"leg": "t2c"}, "approval_ref": None, "artifacts": ()},
    ]
    t0 = time.time()
    try:
        res_c, info_c = cm_c.commit_batch(ops_c)
        call_c = True
    except Exception as e:
        check("c-batch-call-ok", False, f"{type(e).__name__}: {e}")
        res_c, info_c, call_c = None, None, False
    dt_c = time.time() - t0
    if call_c:
        check("c-batch-call-ok", True)
        check("c-path-fallback", info_c["path"] == "fallback-serial",
              f"path={info_c['path']} abort={info_c['abort']}")
        check("c-abort-index1", (info_c["abort"] or {}).get("op_index") == 1,
              f"abort={info_c['abort']}")
        got_c = [r["status"] for r in res_c]
        check("c-statuses", got_c == ["committed", "retryable"], str(res_c)[:200])
        check("c-retryable-clock", "REJECT_CLOCK" in str(res_c[1].get("message", "")),
              str(res_c[1])[:150])
        # serial twin: same two ops pure-serially must show the same shape
        tstore_c = Store.create(os.path.join(root, "clock-twin"))
        tfence_c = Fence(tstore_c)
        tfence_c.acquire()
        tcm_c = Committer(tstore_c, tfence_c)
        twin_c = []
        for op in ops_c:
            try:
                tcm_c.commit_op(op["op_id"], op["kind"], op["payload"],
                                op["disclosure"], op["approval_ref"], [])
                twin_c.append("committed")
            except Retryable as r:
                twin_c.append("retryable:" + str(r).split(":")[0])
            except Reject as r:
                twin_c.append("reject:" + r.code)
        check("c-twin-shape", twin_c == ["committed", "retryable:REJECT_CLOCK"],
              twin_c)
        tfence_c.release()
    check("c-no-wait-burn", dt_c < 4.0, f"{dt_c:.2f}s")
    fence_c.release()

    # ---- (d) fallback must not see batch-held reservations (Finding C)
    # max_reservations=1 + single-op batch that aborts in-txn: the batch
    # token must be released BEFORE fallback-serial runs, else every
    # fallback reserve() WAIT-burns to REJECT_CAPACITY(deadline) where
    # the serial twin commits/marks-terminal.
    import intake as _intake_c
    store_d = Store.create(os.path.join(root, "rsv"))
    fence_d = Fence(store_d)
    fence_d.acquire()
    caps_d = dict(_intake_c.CAPS)
    caps_d["max_reservations"] = 1
    caps_d["reserve_deadline_s"] = 0.5
    cm_d = Committer(store_d, fence_d, caps=caps_d)
    oid_d = mint_v7(int(time.time() * 1000), rng.getrandbits(12),
                    rng.getrandbits(62))
    ops_d = [{"op_id": oid_d, "kind": "RETRACT", "payload": {"body": "t2d"},
              "disclosure": {"leg": "t2d"},
              "approval_ref": {"stage": 1, "policy_version": "v0"},
              "artifacts": ()}]
    assert dict(_intake_c._reservations) == {}, _intake_c._reservations
    try:
        res_d, info_d = cm_d.commit_batch(ops_d)
        call_d = True
    except Exception as e:
        check("d-batch-call-ok", False, f"{type(e).__name__}: {e}")
        res_d, info_d, call_d = None, None, False
    if call_d:
        check("d-batch-call-ok", True)
        check("d-path-fallback", info_d["path"] == "fallback-serial",
              f"path={info_d['path']} abort={info_d['abort']}")
        check("d-fallback-terminal", res_d[0].get("status") == "terminal"
              and res_d[0].get("code") == "STAGE1_NOT_ALLOWLISTED",
              str(res_d[0])[:150])
    check("d-grants-released", dict(_intake_c._reservations) == {},
          f"{_intake_c._reservations}")
    fence_d.release()

    fence.release()
    tfence.release()
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
