#!/usr/bin/env python3
"""T7: reconcile branch coverage (white-box, fault-injected).

(a) Mixed verdicts -> FailClosed with evidence (defensive branch;
    genuinely unreachable under atomic COMMIT -- proven by forcing).
(b) Absent verdicts -> fallback-serial path with commit_error recorded.
(c) Match verdicts -> reconciled-committed returns in-memory results.
(d) _reconcile_batch read shapes: bare op_id strings + full dicts +
    terminal/mismatch/absent verdicts; never writes (COUNT stable).
(e) COMMIT-except wiring end-to-end (Finding F): injected COMMIT
    failure -> reconciled-absent + fallback commits + commit_error;
    injected commit-then-raise -> reconciled-committed, no fallback;
    all-read-only + COMMIT error -> reconciled-readonly.
(f) Shadowed-id terminal + COMMIT error (Finding B): resubmitting a
    COMMITTED/TERMINAL id under a terminal kind is a durable no-op, so
    reconcile must return the outcome (reconciled-readonly), never
    FailClosed("mixed... impossible") on consistent state.
"""
import argparse, os, sys, time
sys.dont_write_bytecode = True

def mint(ts_ms, i):
    v = ((ts_ms & 0xFFFFFFFFFFFF) << 80) | (7 << 76) | ((i & 0xFFF) << 64) | (2 << 62) | (i & 0x3FFFFFFFFFFFFFFF)
    h = "%032x" % v
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sut", required=True)
    ap.add_argument("--store-root", required=True)
    args = ap.parse_args()
    sys.path.insert(0, os.path.abspath(args.sut))
    from store import Store, Fence
    from committer import Committer
    from common import FailClosed
    import sqlite3
    fails = []
    def check(n, c, d=""):
        print(("PASS " if c else "FAIL ") + n + ("" if c else f" :: {d}"))
        if not c: fails.append(n)
    import random as _r
    root = os.path.join(os.path.abspath(args.store_root),
                        "t7-%d-%d-%04x" % (os.getpid(), int(time.time()),
                                           _r.randrange(65536)))
    os.makedirs(root, exist_ok=False)
    store = Store.create(root)
    fence = Fence(store)
    fence.acquire()
    cm = Committer(store, fence)
    now = time.time()
    ids = [mint(int(now * 1000), 9000 + i) for i in range(4)]
    ops = [{"op_id": i, "kind": "EDIT", "payload": {"n": i},
            "disclosure": {"t": 7}} for i in ids]
    res, info = cm.commit_batch(ops)
    assert info["path"] == "batch" and all(r["status"] == "committed" for r in res)
    con = store.open_db()
    try:
        # (d) read shapes
        v1 = cm._reconcile_batch(con, ids[:2])
        check("d-bare-strings", all(v1[i]["status"] == "match" for i in ids[:2]), v1)
        v2 = cm._reconcile_batch(con, [{"op_id": ids[2],
                                        "payload_s": '{"n": "wrong-payload"}',
                                        "expect": "committed"}])
        check("d-hash-mismatch", v2[ids[2]]["status"] == "mismatch", v2)
        ghost = "00000000-0000-7000-8000-000000000000"
        v3 = cm._reconcile_batch(con, [ghost])
        check("d-absent", v3[ghost]["status"] == "absent", v3)
        n0 = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        check("d-no-writes", n0 == 4, n0)
        # (c) match -> reconciled-committed (forced COMMIT error post-write)
        res_c = [{"op_id": ids[0], "status": "committed", "outcome": "o", "triple": "t"}]
        out_c, info_c = cm._reconcile_commit(
            [ops[0]], ['{"n": "%s"}' % ids[0]], res_c, [True],
            [], RuntimeError("forced"))
        check("c-path", info_c["path"] == "reconciled-committed", info_c["path"])
        check("c-results-preserved", out_c == res_c)
        # (b) absent -> fallback-serial
        fresh = mint(int(time.time() * 1000), 9999)
        ops_b = [{"op_id": fresh, "kind": "EDIT", "payload": {"n": "b"},
                  "disclosure": {"t": 7}, "approval_ref": None,
                  "artifacts": ()}]
        res_b = [{"op_id": fresh, "status": "committed", "outcome": "o", "triple": "t"}]
        out_b, info_b = cm._reconcile_commit(
            ops_b, ['{"n": "b"}'], res_b, [True], [], RuntimeError("forced"))
        check("b-path", info_b["path"] == "reconciled-absent", info_b["path"])
        check("b-fallback-committed", out_b[0]["status"] == "committed", out_b)
        check("b-error-recorded", "forced" in info_b.get("commit_error", ""), info_b.get("commit_error"))
        # (a) mixed -> FailClosed
        orig = cm._reconcile_batch
        cm._reconcile_batch = lambda c, items: {ids[0]: {"status": "match"},
                                                fresh + "x": {"status": "absent"}}
        try:
            cm._reconcile_commit(
                [{"op_id": ops[0]["op_id"], "kind": "EDIT",
                  "payload": {"n": "x0"}, "disclosure": {},
                  "approval_ref": None, "artifacts": ()},
                 {"op_id": fresh + "x", "kind": "EDIT",
                  "payload": {"n": "x"}, "disclosure": {},
                  "approval_ref": None, "artifacts": ()}],
                ["{}", "{}"],
                [{"op_id": ids[0], "status": "committed"},
                 {"op_id": fresh + "x", "status": "committed"}],
                [True, True], [], RuntimeError("forced"))
            check("a-failclosed", False, "no raise")
        except FailClosed as e:
            check("a-failclosed", "mixed" in str(e), str(e)[:80])
        finally:
            cm._reconcile_batch = orig
            assert cm._reconcile_batch is orig
    finally:
        con.close()

    # ---- (e/f) COMMIT-except wiring end-to-end (red-team Finding F) ----
    # T7a-d call _reconcile_commit directly; these drive commit_batch with
    # a fault-injecting first connection: mode 'failed' = COMMIT raises
    # with nothing applied (ROLLBACK, like EIO during fsync); mode
    # 'applied' = COMMIT applies, then the ack is lost (raise).
    class _FlakyConn:
        def __init__(self, c, mode):
            self._con = c
            self._mode = mode
        def execute(self, sql, *a, **k):
            if (self._mode and isinstance(sql, str)
                    and sql.strip().upper() == "COMMIT;"):
                mode, self._mode = self._mode, None
                if mode == "applied":
                    out = self._con.execute(sql, *a, **k)
                    raise sqlite3.OperationalError(
                        "injected: COMMIT applied, ack lost")
                self._con.execute("ROLLBACK;")
                raise sqlite3.OperationalError(
                    "injected: COMMIT failed, nothing applied")
            return self._con.execute(sql, *a, **k)
        def __getattr__(self, name):
            return getattr(self._con, name)

    def flaky_case(tag, mode):
        st = Store.create(os.path.join(root, "t7-" + tag))
        fe = Fence(st)
        fe.acquire()
        cmx = Committer(st, fe)
        real_open = st.open_db
        state = {"n": 0}
        def flaky_open():
            c = real_open()
            state["n"] += 1
            return _FlakyConn(c, mode) if state["n"] == 1 else c
        st.open_db = flaky_open
        calls = {"fallback": 0}
        orig_fb = cmx._batch_fallback_serial
        def spy_fb(norm):
            calls["fallback"] += 1
            return orig_fb(norm)
        cmx._batch_fallback_serial = spy_fb
        return st, fe, cmx, calls

    def n_commits(st):
        c2 = st.open_db()
        try:
            return c2.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        finally:
            c2.close()

    # F1: COMMIT fails, nothing applied -> reconciled-absent + fallback
    st1, fe1, cm1, calls1 = flaky_case("f1", "failed")
    f1ids = [mint(int(time.time() * 1000), 9100 + i) for i in range(2)]
    f1ops = [{"op_id": i, "kind": "EDIT", "payload": {"n": "f1"},
              "disclosure": {"t": 7}, "approval_ref": None, "artifacts": ()}
             for i in f1ids]
    out1, info1 = cm1.commit_batch(f1ops)
    check("eF1-path-absent", info1["path"] == "reconciled-absent", info1["path"])
    check("eF1-fallback-ran", calls1["fallback"] == 1, calls1)
    check("eF1-all-committed", [r["status"] for r in out1] == ["committed"] * 2,
          str(out1)[:200])
    check("eF1-error-recorded", "injected" in info1.get("commit_error", ""),
          info1.get("commit_error"))
    check("eF1-exactly-once", n_commits(st1) == 2, n_commits(st1))
    fe1.release()

    # F2: COMMIT applied, ack lost -> reconciled-committed, no fallback
    st2, fe2, cm2, calls2 = flaky_case("f2", "applied")
    f2ids = [mint(int(time.time() * 1000), 9200 + i) for i in range(2)]
    f2ops = [{"op_id": i, "kind": "EDIT", "payload": {"n": "f2"},
              "disclosure": {"t": 7}, "approval_ref": None, "artifacts": ()}
             for i in f2ids]
    out2, info2 = cm2.commit_batch(f2ops)
    check("eF2-path-committed", info2["path"] == "reconciled-committed", info2["path"])
    check("eF2-no-fallback", calls2["fallback"] == 0, calls2)
    check("eF2-results-preserved", [r["status"] for r in out2] == ["committed"] * 2
          and [r.get("triple", "").rsplit(":", 1)[-1] for r in out2] == ["1", "2"],
          str(out2)[:200])
    check("eF2-exactly-once", n_commits(st2) == 2, n_commits(st2))
    fe2.release()

    # F3: all-read-only batch + COMMIT error -> reconciled-readonly
    st3, fe3 = Store.create(os.path.join(root, "t7-f3")), None
    fe3 = Fence(st3)
    fe3.acquire()
    cm3 = Committer(st3, fe3)
    f3ids = [mint(int(time.time() * 1000), 9300 + i) for i in range(2)]
    for i in f3ids:
        cm3.commit_op(i, "EDIT", {"n": "f3"}, {"t": 7}, None, [])
    real3 = st3.open_db
    state3 = {"n": 0}
    def flaky3():
        c = real3()
        state3["n"] += 1
        return _FlakyConn(c, "failed") if state3["n"] == 1 else c
    st3.open_db = flaky3
    f3ops = [{"op_id": i, "kind": "EDIT", "payload": {"n": "f3"},
              "disclosure": {"t": 7}, "approval_ref": None, "artifacts": ()}
             for i in f3ids]
    out3, info3 = cm3.commit_batch(f3ops)
    check("eF3-path-readonly", info3["path"] == "reconciled-readonly", info3["path"])
    check("eF3-results-preserved", [r["status"] for r in out3] == ["committed"] * 2,
          str(out3)[:200])
    check("eF3-no-new-rows", n_commits(st3) == 2, n_commits(st3))
    fe3.release()

    # ---- (g) shadowed-id terminal + COMMIT error: outcome, not FailClosed
    # (red-team Finding B). _mark_terminal_row is a no-op over a
    # pre-existing COMMITTED/TERMINAL row, so wrote must be False and
    # reconcile must classify these read-only -- durable state is
    # consistent; FailClosed("mixed... impossible") is a false diagnosis.
    # B1: X committed as EDIT, batch resubmits X as ref-less BOGUS_KIND
    stB, feB = Store.create(os.path.join(root, "t7-b1")), None
    feB = Fence(stB)
    feB.acquire()
    cmB = Committer(stB, feB)
    x1 = mint(int(time.time() * 1000), 9400)
    out_x1, _t = cmB.commit_op(x1, "EDIT", {"n": "b1"}, {"t": 7}, None, [])
    realB = stB.open_db
    stateB = {"n": 0}
    def flakyB():
        c = realB()
        stateB["n"] += 1
        return _FlakyConn(c, "applied") if stateB["n"] == 1 else c
    stB.open_db = flakyB
    raisedB1 = None
    try:
        outB1, infoB1 = cmB.commit_batch(
            [{"op_id": x1, "kind": "BOGUS_KIND", "payload": {"n": "b1x"},
              "disclosure": {"t": 7}, "approval_ref": None, "artifacts": ()}])
    except FailClosed as e:
        raisedB1 = e
        outB1, infoB1 = None, None
    check("gB1-no-failclosed", raisedB1 is None, str(raisedB1)[:120])
    if raisedB1 is None:
        check("gB1-path-readonly", infoB1["path"] == "reconciled-readonly",
              infoB1["path"])
        check("gB1-terminal-shadow", outB1[0]["status"] == "terminal"
              and outB1[0].get("code") == "APPROVAL_MISSING", str(outB1)[:150])
    cB = realB()
    try:
        rowB1 = cB.execute("SELECT state,outcome FROM dedup WHERE op_id=?",
                           (x1,)).fetchone()
    finally:
        cB.close()
    check("gB1-durable-untouched", rowB1 is not None and rowB1[0] == "COMMITTED"
          and rowB1[1] == out_x1, str(rowB1)[:120])
    feB.release()

    # B2: X terminal as STAGE1_NOT_ALLOWLISTED, resubmit as FOLD_PHYSICAL
    stC, feC = Store.create(os.path.join(root, "t7-b2")), None
    feC = Fence(stC)
    feC.acquire()
    cmC = Committer(stC, feC)
    x2 = mint(int(time.time() * 1000), 9410)
    from common import Reject as _Rej
    try:
        cmC.commit_op(x2, "RETRACT", {"body": "b2"}, {"t": 7},
                      {"stage": 1, "policy_version": "v0"}, [])
        check("gB2-setup-terminal", False, "RETRACT unexpectedly committed")
    except _Rej as r:
        check("gB2-setup-terminal", r.code == "STAGE1_NOT_ALLOWLISTED",
              f"{r.code}: {r.detail}")
    realC = stC.open_db
    stateC = {"n": 0}
    def flakyC():
        c = realC()
        stateC["n"] += 1
        return _FlakyConn(c, "applied") if stateC["n"] == 1 else c
    stC.open_db = flakyC
    raisedB2 = None
    try:
        outB2, infoB2 = cmC.commit_batch(
            [{"op_id": x2, "kind": "FOLD_PHYSICAL", "payload": {"n": "b2x"},
              "disclosure": {"t": 7}, "approval_ref": None, "artifacts": ()}])
    except FailClosed as e:
        raisedB2 = e
        outB2, infoB2 = None, None
    check("gB2-no-failclosed", raisedB2 is None, str(raisedB2)[:120])
    if raisedB2 is None:
        check("gB2-path-readonly", infoB2["path"] == "reconciled-readonly",
              infoB2["path"])
        check("gB2-terminal-shadow", outB2[0]["status"] == "terminal"
              and outB2[0].get("code") == "ENTRY1_MISSING_PA", str(outB2)[:150])
    cC = realC()
    try:
        rowB2 = cC.execute("SELECT state,outcome FROM dedup WHERE op_id=?",
                           (x2,)).fetchone()
    finally:
        cC.close()
    check("gB2-durable-untouched", rowB2 is not None
          and rowB2[0] == "TERMINAL_REJECTED"
          and rowB2[1] == "STAGE1_NOT_ALLOWLISTED", str(rowB2)[:120])
    feC.release()

    # ---- (h) reconcile fallback must not see dead batch tokens ----
    # Finding-C sibling: COMMIT fails (nothing applied) with tight
    # max_reservations -> all-absent reconcile -> fallback-serial.
    # The batch txn is over, so its admission tokens are dead and must
    # be released BEFORE reconcile; else fallback reserve() WAIT-burns
    # against our own dead tokens and reports REJECT_CAPACITY(deadline)
    # though durable capacity is available (P9 letter violation: the
    # error must reflect real capacity, not dead tokens).
    import intake as _intake_h
    stH = Store.create(os.path.join(root, "t7-h"))
    feH = Fence(stH)
    feH.acquire()
    caps_h = dict(_intake_h.CAPS)
    caps_h["max_reservations"] = 1
    caps_h["reserve_deadline_s"] = 0.5
    cmH = Committer(stH, feH, caps=caps_h)
    realH = stH.open_db
    stateH = {"n": 0}
    def flakyH():
        c = realH()
        stateH["n"] += 1
        return _FlakyConn(c, "failed") if stateH["n"] == 1 else c
    stH.open_db = flakyH
    xH = mint(int(time.time() * 1000), 9500)
    assert dict(_intake_h._reservations) == {}, _intake_h._reservations
    try:
        outH, infoH = cmH.commit_batch(
            [{"op_id": xH, "kind": "EDIT", "payload": {"n": "h"},
              "disclosure": {"t": 7}, "approval_ref": None,
              "artifacts": ()}])
        callH = True
    except Exception as e:
        check("h-batch-call-ok", False, f"{type(e).__name__}: {e}")
        outH, infoH, callH = None, None, False
    if callH:
        check("h-batch-call-ok", True)
        check("h-path-absent", infoH["path"] == "reconciled-absent",
              infoH["path"])
        check("h-fallback-committed", outH[0].get("status") == "committed",
              str(outH[0])[:150])
    check("h-grants-released", dict(_intake_h._reservations) == {},
          f"{_intake_h._reservations}")
    cH = realH()
    try:
        nH = cH.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
    finally:
        cH.close()
    check("h-exactly-once", nH == 1, nH)
    feH.release()
    fence.release()
    print("RESULT:", "PASS" if not fails else f"FAIL {fails}")
    return 1 if fails else 0

if __name__ == "__main__":
    raise SystemExit(main())
