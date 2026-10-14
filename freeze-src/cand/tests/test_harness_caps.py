"""Harness-writer own tests: 2M qualification caps plumbing (synthetic only).

Covers, against the read-only V8 core plus this lease's product_pilot.py:
  T1  core intake.CAPS globals unchanged by qualification_caps()
  T2  all construction/recovery sites enforce the 2M clone
      (main-style create, child_writer default + explicit caps incl.
      spawn-arg pickle round-trip, restart-style reopen)
  T3  qual caps admit past the old 100k default ceiling, while the old
      default still rejects there; the configured 2M limit itself rejects
  T4  the injected 0-delta/.01-deadline fault still rejects and the
      snapshot restore brings back the 2M caps (not bypassed)

No real cache data; scratch stores under the lease tmp dir only.
Run: nice -n 19 <venv-cpu>/python tests/test_harness_caps.py
"""
import inspect
import os
import pickle
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LEASE = os.path.normpath(os.path.join(HERE, "..", "tools"))
V8_TLSYS = os.path.normpath(os.path.join(HERE, '..', 'fork', 'tl-sys'))
if V8_TLSYS not in sys.path:
    sys.path.insert(0, V8_TLSYS)
if LEASE not in sys.path:
    sys.path.insert(0, LEASE)

from tlsys.store_if import TLStore  # noqa: E402 (adds candidate dir)
from tlsys.store_if import uuidv7 as _uuidv7  # noqa: E402
from common import Retryable  # noqa: E402
import intake  # noqa: E402
import product_pilot as pilot  # noqa: E402 (this lease's harness)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def _mkstore(caps=None):
    tmp = tempfile.mkdtemp(prefix="harness-caps-")
    kw = {"lease_owner": "harness-caps-test"}
    if caps is not None:
        kw["caps"] = caps
    return TLStore(tmp, create=True, **kw), tmp


def _op(i):
    return {"op_id": _uuidv7(), "kind": "ACCEPT_ATOMS",
            "payload": {"atom": "a%d" % i, "doc_id": "d",
                        "meta_artifact": "none"},
            "disclosure": {"leg": "ingest", "doc_id": "d", "chunk_ix": i},
            "approval_ref": None, "artifacts": ()}


def _set_ledger(tmp, delta):
    con = sqlite3.connect(os.path.join(tmp, "commit.db"))
    try:
        con.execute("UPDATE counters SET v=? WHERE k='delta_entries'",
                    (delta,))
        con.commit()
    finally:
        con.close()


def _reserve_once(tl, caps, kind="UPSERT_ATOMS"):
    import time
    con = tl.store.open_db()
    try:
        return intake.reserve(con, 10, caps, time.time(), kind)
    finally:
        con.close()


def main():
    frozen_global = dict(intake.CAPS)

    # -- T1: global defaults unchanged; clone carries only the 2M pair --
    q1 = pilot.qualification_caps()
    q2 = pilot.qualification_caps()
    check("global-values-untouched", intake.CAPS == frozen_global
          and intake.CAPS["max_delta_entries"] == 100000
          and intake.CAPS["max_dedup_rows"] == 1000000
          and intake.CAPS["reserve_deadline_s"] == 5.0,
          f"{intake.CAPS}")
    check("clone-only-two-knobs",
          q1["max_delta_entries"] == 2000000
          and q1["max_dedup_rows"] == 2000000
          and all(q1[k] == intake.CAPS[k] for k in intake.CAPS
                  if k not in ("max_delta_entries", "max_dedup_rows")),
          f"{q1}")
    check("clone-fresh-objects", q1 is not q2 and q1 == q2
          and q1 is not intake.CAPS, "aliasing")
    q1["max_delta_entries"] = 7
    check("clone-mutation-isolated",
          intake.CAPS["max_delta_entries"] == 100000
          and pilot.qualification_caps()["max_delta_entries"] == 2000000,
          f"{intake.CAPS}")

    # -- T2a: main-style construction plumbs + copies the 2M dict --
    qual = pilot.qualification_caps()
    tl, tmp = _mkstore(caps=qual)
    try:
        check("main-caps-2M",
              tl.cm.caps.get("max_delta_entries") == 2000000
              and tl.cm.caps.get("max_dedup_rows") == 2000000
              and tl.cm.caps.get("reserve_deadline_s")
              == intake.CAPS["reserve_deadline_s"]
              and tl.cm.caps.get("max_intake_backlog")
              == intake.CAPS["max_intake_backlog"]
              and tl.cm.caps.get("max_reservations")
              == intake.CAPS["max_reservations"], f"{tl.cm.caps}")
        qual["max_delta_entries"] = 7
        check("main-caps-copied", tl.cm.caps["max_delta_entries"] == 2000000,
              f"{tl.cm.caps}")
    finally:
        tl.close()

    # -- T2b: defaults path untouched when caps=None --
    tl, tmp = _mkstore()
    try:
        check("none-keeps-defaults", tl.cm.caps == intake.CAPS
              and tl.cm.caps is not intake.CAPS, f"{tl.cm.caps}")
    finally:
        tl.close()

    # -- T2c: child_writer optional caps param; default builds 2M clone --
    sig = inspect.signature(pilot.child_writer)
    check("child-signature",
          list(sig.parameters) == ["root", "marker", "caps"]
          and sig.parameters["caps"].default is None, f"{sig}")
    import tlsys.store_if as store_if
    real_store = store_if.TLStore
    seen = {}

    class RecStore(real_store):
        def __init__(self, *a, **k):
            seen["caps"] = dict(k.get("caps") or {})
            super().__init__(*a, **k)

    store_if.TLStore = RecStore
    try:
        ctmp = tempfile.mkdtemp(prefix="harness-child-")
        seed = real_store(ctmp, create=True,
                          lease_owner="harness-caps-test")
        seed.close()  # real flow: main creates, child opens existing
        pilot.child_writer(ctmp, os.path.join(ctmp, "kill-marker"))
        check("child-default-2M",
              seen.get("caps", {}).get("max_delta_entries") == 2000000
              and seen.get("caps", {}).get("max_dedup_rows") == 2000000
              and not os.path.exists(os.path.join(ctmp, "kill-marker")),
              f"{seen.get('caps')}")
        check("child-no-global-mutation", intake.CAPS == frozen_global,
              f"{intake.CAPS}")
        # explicit spawn-arg dict (pickle round-trip, as mp spawn does)
        seen.clear()
        spawn_caps = pickle.loads(pickle.dumps(pilot.qualification_caps()))
        ctmp2 = tempfile.mkdtemp(prefix="harness-child2-")
        seed2 = real_store(ctmp2, create=True,
                           lease_owner="harness-caps-test")
        seed2.close()
        pilot.child_writer(ctmp2, os.path.join(ctmp2, "kill-marker"),
                           spawn_caps)
        check("child-spawnargs-inherit",
              seen.get("caps") == spawn_caps
              and seen["caps"]["max_delta_entries"] == 2000000,
              f"{seen.get('caps')}")
    finally:
        store_if.TLStore = real_store

    # -- T2d: restart-style reopen enforces caps (recovery plumbing) --
    rtmp = tempfile.mkdtemp(prefix="harness-restart-")
    tl = TLStore(rtmp, create=True, lease_owner="harness-caps-test",
                 caps=pilot.qualification_caps())
    tl.close()
    tl = TLStore(rtmp, lease_owner="product-pilot-resumed",
                 caps=pilot.qualification_caps())
    try:
        check("restart-caps-2M",
              tl.cm.caps.get("max_delta_entries") == 2000000
              and tl.cm.caps.get("max_dedup_rows") == 2000000,
              f"{tl.cm.caps}")
    finally:
        tl.close()

    # -- T3a: qual caps admit past the old 100k ceiling; default rejects --
    tl, tmp = _mkstore(caps=pilot.qualification_caps())
    try:
        _set_ledger(tmp, 150000)
        try:
            granted, tok = _reserve_once(tl, tl.cm.caps)
            ok = granted == "GRANT"
            intake.release(tok)
        except Retryable:
            ok = False
        check("qual-admits-past-100k", ok, "rejected at 150k ledger")
    finally:
        tl.close()
    tl, tmp = _mkstore()
    try:
        _set_ledger(tmp, 150000)
        try:
            _reserve_once(tl, dict(intake.CAPS, reserve_deadline_s=0.05))
            rejected = False
        except Retryable as e:
            rejected = "REJECT_CAPACITY" in str(e)
        check("default-100k-rejects-150k", rejected, "granted at 150k")
    finally:
        tl.close()

    # -- T3b: the configured 2M limit itself rejects (fast deadline) --
    tl, tmp = _mkstore(caps=pilot.qualification_caps())
    try:
        _set_ledger(tmp, 2000000)
        fast = dict(tl.cm.caps, reserve_deadline_s=0.05)
        try:
            _reserve_once(tl, fast)
            rejected = False
        except Retryable as e:
            rejected = "REJECT_CAPACITY" in str(e)
        check("configured-2M-rejects", rejected, "granted at 2M ledger")
    finally:
        tl.close()

    # -- T4: injected 0-delta/.01-deadline fault rejects, restore keeps 2M --
    tl, tmp = _mkstore(caps=pilot.qualification_caps())
    try:
        snap = dict(tl.cm.caps)
        tl.cm.caps["max_delta_entries"] = 0
        tl.cm.caps["reserve_deadline_s"] = 0.01
        try:
            res, _info = tl.commit_batch([_op(9001)])
            fault_rejected = ([r.get("status") for r in res] == ["retryable"]
                              and "REJECT_CAPACITY"
                              in (res[0].get("message") or ""))
        except Retryable as e:
            fault_rejected = "REJECT_CAPACITY" in str(e)
        check("injected-fault-rejects", fault_rejected,
              "0-delta fault bypassed")
        tl.cm.caps = snap  # pilot's finally-restore, verbatim
        res, _info = tl.commit_batch([_op(9002)])
        check("restore-keeps-2M-admitting",
              [r.get("status") for r in res] == ["committed"]
              and tl.cm.caps["max_delta_entries"] == 2000000
              and tl.cm.caps["max_dedup_rows"] == 2000000, f"{res}")
        check("restore-no-global-mutation", intake.CAPS == frozen_global,
              f"{intake.CAPS}")
    finally:
        tl.close()

    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
