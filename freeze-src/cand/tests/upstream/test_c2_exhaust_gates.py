"""C2 100M recovery (lane-R100M): Codex gates C+D failure paths, proved small.

Gate C (fail-fast on store-wide exhaustion): the keyed organize loop
must stop promptly when every doc burns a REJECT_CAPACITY reserve
deadline -- the 100M p0 leg ground 9,444 x 5.0 s (13 h) before the
phase returned. After ORGANIZE_WALL_TRIP_CONSECUTIVE consecutive
capacity failures the loop raises with the cause preserved instead
of recording another failed[doc].

Gate D (honest checkpoints) is driver-side (refuse_failed_organize,
covered by the lane self-test); this file pins the product half of
the contract: the tripwire threshold, streak reset, cause text, and
that healthy organizes are unaffected.

Deterministic; scratch stores under /tmp; short reserve deadlines
(0.05-1.0 s) keep the suite fast while still exercising the real
WAIT-to-deadline path.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_exhaust_gates.py
"""
import os
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
import intake  # noqa: E402  (candidate dir auto-added by store_if)
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.maint import (CapacityTripwire, ORGANIZE_WALL_TRIP_CONSECUTIVE,  # noqa: E402
                         is_capacity_failure, organize_segments)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 8


def _emb(texts):
    return [[1.0] + [0.0] * (DIM - 1) for _ in texts]


def _mkstore(caps):
    tmp = tempfile.mkdtemp(prefix="exhaust-gates-")
    tl = TLStore(tmp, create=True, lease_owner="test-gates", caps=caps)
    return tl, tmp


def _set_ledger(tmp, delta):
    con = sqlite3.connect(os.path.join(tmp, "commit.db"))
    try:
        con.execute("UPDATE counters SET v=? WHERE k='delta_entries'",
                    (delta,))
        con.commit()
    finally:
        con.close()


def _docs(n, tag="gdoc"):
    return [("%s%d" % (tag, i),
             "alpha beta gamma delta epsilon zeta eta theta %d" % i)
            for i in range(n)]


def main():
    check("trip-threshold-is-3", ORGANIZE_WALL_TRIP_CONSECUTIVE == 3,
          f"{ORGANIZE_WALL_TRIP_CONSECUTIVE}")

    # -- G1: cause classifier --
    check("classifier-capacity",
          is_capacity_failure("organize op x retryable:"
                              "REJECT_CAPACITY(deadline): waited"))
    check("classifier-noncapacity",
          not is_capacity_failure("organize: doc 'd' has no committed "
                                  "atoms")
          and not is_capacity_failure("")
          and not is_capacity_failure(None))

    # -- G2: tripwire unit -- fail,fail,ok,fail,fail never trips; 3x trips.
    tw = CapacityTripwire()
    raised = None
    try:
        tw.note("u0", "REJECT_CAPACITY(deadline)")
        tw.note("u1", "REJECT_CAPACITY(deadline)")
        tw.note("u2", None)
        tw.note("u3", "other failure")
        tw.note("u4", "REJECT_CAPACITY(deadline)")
        tw.note("u5", "REJECT_CAPACITY(deadline)")
    except RuntimeError as e:
        raised = str(e)
    check("tripwire-reset-no-raise", raised is None, f"{raised}")
    check("tripwire-streak-after-reset", tw.streak == 2, f"{tw.streak}")
    tw2 = CapacityTripwire()
    raised2 = None
    try:
        tw2.note("v0", "a REJECT_CAPACITY(staged) b")
        tw2.note("v1", "a REJECT_CAPACITY(staged) b")
        tw2.note("v2", "a REJECT_CAPACITY(staged) b")
    except RuntimeError as e:
        raised2 = str(e)
    check("tripwire-trips-on-3",
          raised2 is not None
          and "REJECT_CAPACITY" in raised2
          and "3 consecutive" in raised2, f"{raised2}")

    # -- G3: small-cap organize trips fast with cause (integration) --
    # Default ceiling (100k) + 1 s deadline: ingest 8 docs healthy,
    # then fake the ledger AT the wall. The old code returns failed x8
    # after ~8 s; the gate raises after 3 with the cause named.
    caps = dict(intake.CAPS, reserve_deadline_s=1.0)
    tl, tmp = _mkstore(caps)
    try:
        docs = _docs(8)
        rep = ingest_docs(tl, docs, _emb, store_id="gates-e2e",
                          place_xdoc=True, keyed_state=True)
        check("trip-setup-committed", rep.get("n_atoms", 0) > 0,
              f"{rep}")
        _set_ledger(tmp, 100000)
        t0 = time.time()
        raised3 = None
        try:
            organize_segments(tl, doc_ids=[d for d, _t in docs],
                              budget=None, store_id="gates-e2e",
                              keyed_state=True)
        except RuntimeError as e:
            raised3 = str(e)
        wall = time.time() - t0
        check("trip-raises",
              raised3 is not None and "REJECT_CAPACITY" in raised3
              and "consecutive" in raised3, f"{raised3}")
        check("trip-names-docs",
              raised3 is not None and "gdoc0" in raised3
              and "gdoc7" not in raised3, f"{raised3}")
        check("trip-fast", wall < 6.0, f"{wall:.2f}s")
    finally:
        tl.close()

    # -- G4: sub-threshold capacity failures still return a report --
    # (2 docs at the wall: no trip; driver Gate D refuses the
    # checkpoint downstream -- the product contract is unchanged).
    tl, tmp = _mkstore(dict(intake.CAPS, reserve_deadline_s=0.05))
    try:
        docs = _docs(2, tag="tdoc")
        ingest_docs(tl, docs, _emb, store_id="gates-e2e",
                    place_xdoc=True, keyed_state=True)
        _set_ledger(tmp, 100000)
        orep = organize_segments(tl, doc_ids=[d for d, _t in docs],
                                 budget=None, store_id="gates-e2e",
                                 keyed_state=True)
        check("subthreshold-returns-report",
              len(orep.get("failed", {})) == 2
              and all("REJECT_CAPACITY" in e
                      for e in orep["failed"].values()),
              f"{orep.get('failed')}")
    finally:
        tl.close()

    # -- G5: healthy organize unaffected (no false trip) --
    tl, tmp = _mkstore(dict(intake.CAPS))
    try:
        docs = _docs(3, tag="hdoc")
        ingest_docs(tl, docs, _emb, store_id="gates-e2e",
                    place_xdoc=True, keyed_state=True)
        orep = organize_segments(tl, doc_ids=[d for d, _t in docs],
                                 budget=None, store_id="gates-e2e",
                                 keyed_state=True)
        check("healthy-no-trip",
              sorted(orep.get("organized", []))
              == ["hdoc0", "hdoc1", "hdoc2"]
              and not orep.get("failed"), f"{orep}")
    finally:
        tl.close()

    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
