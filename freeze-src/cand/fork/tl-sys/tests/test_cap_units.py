"""Track R7-C: xholon cap-units conformance (cap-exempt singletons).

RULING (coordinator): MAX_XHOLON_MEMBERS=25 constrains JOINS only.
New-group creation (sync place_doc miss path + drain singleton path)
commits the whole atom list uncapped. This codifies observed identical
behavior; it changes NOTHING.

Asserts BOTH paths exhibit cap-exempt creation + capped joins
identically, incl. the 30-chunk case from R6-B D1 and join-inertness
of over-cap groups (R6-B D2).

Authority: R6-B proposal D (REPRO-REPAIR.md section 4) + arch
section 7 units rule (handoffs/TL-INGEST-NAVIGATION-ARCHITECTURE-
2026-10-05.md:127: do not carry these constants into higher-level
branching without defining units).

Deterministic fake encoder; scratch stores under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_cap_units.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

import numpy as np  # noqa: E402

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import chunk_text, ingest_docs  # noqa: E402
from tlsys.maint import drain_placement_backlog  # noqa: E402
from tlsys.place import MAX_XHOLON_MEMBERS, decide, read_xholons  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 8


def pad(v):
    return [float(x) for x in v] + [0.0] * (DIM - len(v))


V_SAME = pad([1.0, 0.0, 0.0])


def emb(texts):
    return [list(V_SAME) for _ in texts]


def words(n):
    return " ".join(f"w{i}" for i in range(n))


T30 = words(4500)  # 30 chunks (same geometry as R6-B D1)
T1 = "same words here"


def sizes(tl):
    xh = read_xholons(tl, tl.pin())
    return {h: len(v["members"]) for h, v in xh.items()}


def descs(tl):
    xh = read_xholons(tl, tl.pin())
    return {h: list(v["descriptor"]) for h, v in xh.items()}


def main():
    tmp = tempfile.mkdtemp(prefix="tlsys-capunits-")
    check("geom-30-chunks", len(chunk_text(T30)) == 30,
          f"{len(chunk_text(T30))}")
    check("cap-is-25", MAX_XHOLON_MEMBERS == 25,
          f"{MAX_XHOLON_MEMBERS}")

    # -- cap-exempt creation: sync (place_doc miss path) ---------------
    sps = os.path.join(tmp, "sync-create")
    tls = TLStore(sps, create=True, lease_owner="test-capunits")
    reps = ingest_docs(tls, [("docH", T30)], emb, store_id="capunits")
    ssync = sizes(tls)
    check("sync-creation-exempt",
          ssync == {"xdoc-docH": 30}
          and reps["n_xholon_ops"] == 1, f"{ssync} {reps}")
    dsync = descs(tls)
    tls.close()

    # -- cap-exempt creation: drain (maint singleton path) -------------
    spd = os.path.join(tmp, "drain-create")
    tld = TLStore(spd, create=True, lease_owner="test-capunits")
    repd = ingest_docs(tld, [("docH", T30)], emb, store_id="capunits",
                       place_budget=0)
    check("drain-defers-30chunk",
          repd["pending_placement"] == ["docH"]
          and repd["n_deferred"] == 1, f"{repd}")
    rd = drain_placement_backlog(tld, store_id="capunits")
    sdrain = sizes(tld)
    check("drain-creation-exempt",
          sdrain == {"xdoc-docH": 30}
          and rd["n_xholon_ops"] == 1 and rd["n_commits"] == 1,
          f"{sdrain} {rd}")
    ddrain = descs(tld)
    tld.close()

    # -- creation identical across paths -------------------------------
    check("creation-sync-drain-identical",
          ssync == sdrain
          and sorted(dsync) == sorted(ddrain)
          and all(np.allclose(dsync[h], ddrain[h], atol=1e-12)
                  for h in dsync),
          f"{ssync} vs {sdrain}")

    # -- join-inertness of over-cap groups: decide() level (R6-B D2) ----
    xh_over = {"xdoc-docH": {"members": [f"a{i}" for i in range(30)],
                             "descriptor": list(V_SAME)}}
    check("decide-refuses-overcap-even-negative-t",
          decide(list(V_SAME), xh_over, t_place=-2.0) == [],
          "over-cap groups are join-inert at any threshold")
    check("decide-refuses-overcap-at-zero-t",
          decide(list(V_SAME), xh_over, t_place=0.0) == [],
          "over-cap groups are join-inert at t=0")

    # -- join-inertness end-to-end: both paths refuse to join the
    # -- 30-member group and mint a singleton for the similar doc ----
    for mode in ("sync", "drain"):
        spp = os.path.join(tmp, f"inert-{mode}")
        tl = TLStore(spp, create=True, lease_owner="test-capunits")
        if mode == "sync":
            ingest_docs(tl, [("docH", T30)], emb, store_id="capunits")
            ingest_docs(tl, [("docNext", T1)], emb, store_id="capunits")
        else:
            ingest_docs(tl, [("docH", T30)], emb, store_id="capunits",
                        place_budget=0)
            drain_placement_backlog(tl, store_id="capunits")
            ingest_docs(tl, [("docNext", T1)], emb, store_id="capunits",
                        place_budget=0)
            drain_placement_backlog(tl, store_id="capunits")
        got = sizes(tl)
        check(f"{mode}-overcap-join-inert",
              got == {"xdoc-docH": 30, "xdoc-docNext": 1}, f"{got}")
        tl.close()

    # -- capped joins: exact-cap overflow skipped identically ---------
    # 24 single-atom docs fill one group; a 2-atom similar doc would
    # push it to 26 > 25, so both paths must skip the join and mint
    # a new 2-member group (no overshoot, no split of the joiner).
    join_shapes = {}
    for mode in ("sync", "drain"):
        spp = os.path.join(tmp, f"capjoin-{mode}")
        tl = TLStore(spp, create=True, lease_owner="test-capunits")
        docs = [(f"doc{i}", T1) for i in range(24)]
        # 210 tokens -> 2 atoms (same geometry as the placement
        # exact-cap case); 24 + 2 would overshoot the 25 cap.
        docs.append(("docBig", "same words here " * 70))
        n_big = len(chunk_text(docs[-1][1]))
        if mode == "sync":
            ingest_docs(tl, docs, emb, store_id="capunits")
        else:
            ingest_docs(tl, docs, emb, store_id="capunits",
                        place_budget=0)
            drain_placement_backlog(tl, store_id="capunits")
        got = sizes(tl)
        check(f"{mode}-exact-cap-overflow-skipped",
              sorted(got.values(), reverse=True) == [24, n_big]
              and "xdoc-docBig" in got, f"{got} n_big={n_big}")
        join_shapes[mode] = got
        tl.close()
    check("capjoin-sync-drain-identical",
          join_shapes["sync"] == join_shapes["drain"],
          f"{join_shapes}")

    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
