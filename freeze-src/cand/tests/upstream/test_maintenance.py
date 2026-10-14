"""Maintained maintenance test: deferred-placement backlog (S-03 1b).

Ingest foreground budget -> manifest backlog -> explicit bounded drain.
Covers: budget overflow defers (atoms still ACKed), acknowledged
evidence retrievable while unplaced, drain publishes compatible
memberships/descriptors (allclose to exact member mean), bounded
drain + recovery across restart, outlier singletons (never forced),
measured maintenance cost, explicit-doc drain, and sync-vs-drain
identical math.

Deterministic fake encoder; scratch store under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_maintenance.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

import numpy as np  # noqa: E402

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys.place import read_xholons  # noqa: E402
from tlsys.maint import (drain_placement_backlog,  # noqa: E402
                         reconcile_manifest)

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


V_A = pad([1.0, 0.0, 0.0])
V_B = pad([0.9, 0.4359, 0.0])  # cos ~0.9 with V_A: joins
V_OUT = pad([0.0, 0.0, 1.0])  # far from both: singleton


def emb(texts):
    out = []
    for t in texts:
        if t.startswith("alpha one"):
            out.append(list(V_A))
        elif t.startswith("alpha two"):
            out.append(list(V_B))
        else:
            out.append(list(V_OUT))
    return out


def emb1(q):
    return list(V_A)


def main():
    tmp = tempfile.mkdtemp(prefix="tlsys-maint-")
    sp = os.path.join(tmp, "store")
    tl = TLStore(sp, create=True, lease_owner="test-maint")
    docs = [("d1", "alpha one"), ("d2", "alpha two"),
            ("d3", "zzz outlier")]

    # -- foreground budget binds: 1 placed, 2 deferred ----------------
    rep = ingest_docs(tl, docs, emb, store_id="maint-test",
                      place_budget=1)
    check("budget-defers",
          rep["n_deferred"] == 2
          and rep["pending_placement"] == ["d2", "d3"]
          and rep["n_atoms"] == 3 and rep["n_holons"] == 3, f"{rep}")

    # -- acknowledged evidence retrievable while unplaced -------------
    idx = NarrowIndex(tl, tl.pin())
    nq = NarrowQuery(tl, idx, emb1)
    dos, _rec = nq.run("zzz outlier")
    ids = [e["doc_id"] for e in dos["entries"]]
    check("retrievable-while-pending", "d3" in ids, f"{ids}")

    # -- bounded drain: one doc per call ------------------------------
    r1 = drain_placement_backlog(tl, store_id="maint-test", budget=1)
    check("drain-bounded",
          r1["drained"] == ["d2"] and r1["remaining"] == ["d3"]
          and r1["failed"] == {} and r1["n_commits"] == 1, f"{r1}")

    # -- restart: backlog survives close/reopen -----------------------
    tl.close()
    tl = TLStore(sp, create=False, lease_owner="test-maint")
    r2 = drain_placement_backlog(tl, store_id="maint-test")
    check("drain-after-restart",
          r2["drained"] == ["d3"] and r2["remaining"] == []
          and r2["failed"] == {}, f"{r2}")

    # -- compatible publish: joins + singleton, exact-mean desks ------
    xh = read_xholons(tl, tl.pin())
    joined = [h for h, v in xh.items() if len(v["members"]) == 2]
    single = [h for h, v in xh.items() if len(v["members"]) == 1]
    check("drain-join-and-singleton",
          len(joined) == 1 and len(single) == 1, f"{xh.keys()}")
    idx2 = NarrowIndex(tl, tl.pin())
    ok = True
    for _h, v in xh.items():
        vecs = [idx2.atoms[a]["descriptor"] for a in v["members"]]
        want = np.asarray(vecs, dtype=np.float64).mean(axis=0)
        if not np.allclose(v["descriptor"], want, atol=1e-9):
            ok = False
    check("drain-compatible-descriptors", ok,
          "xdoc descriptor drifted from member mean")
    # outlier never forced into the alpha holon
    jh = xh[joined[0]]
    jdocs = sorted(idx2.atoms[a]["doc_id"] for a in jh["members"])
    check("outlier-not-forced", jdocs == ["d1", "d2"], f"{jdocs}")

    # -- cost measured -------------------------------------------------
    check("drain-cost",
          r1["n_xholon_ops"] == 1 and r2["n_xholon_ops"] == 1
          and r1["n_commits"] == 1 and r2["n_commits"] == 1,
          f"{r1} {r2}")

    # -- explicit-doc drain (never attempted at ingest) ----------------
    sp2 = os.path.join(tmp, "store2")
    tl2 = TLStore(sp2, create=True, lease_owner="test-maint")
    rep2 = ingest_docs(tl2, [("e1", "alpha one")], emb,
                       store_id="maint-test", place_xdoc=False)
    check("opt-out-no-backlog",
          rep2["n_deferred"] == 0
          and rep2["pending_placement"] == [], f"{rep2}")
    r3 = drain_placement_backlog(tl2, store_id="maint-test",
                                 doc_ids=["e1"])
    xh2 = read_xholons(tl2, tl2.pin())
    check("explicit-drain",
          r3["drained"] == ["e1"] and r3["remaining"] == []
          and sorted(xh2) == ["xdoc-e1"], f"{r3} {sorted(xh2)}")
    try:
        drain_placement_backlog(tl2, doc_ids=["nope"])
        check("explicit-unknown-refused", False, "no error")
    except ValueError:
        check("explicit-unknown-refused", True)

    # -- sync vs drain: identical memberships + descriptors ------------
    def build(place_budget, drain):
        p = os.path.join(tmp, f"store-{place_budget}-{drain}")
        t = TLStore(p, create=True, lease_owner="test-maint")
        ingest_docs(t, docs, emb, store_id="maint-test",
                    place_budget=place_budget)
        if drain:
            drain_placement_backlog(t, store_id="maint-test")
        x = read_xholons(t, t.pin())
        i2 = NarrowIndex(t, t.pin())
        snap = {h: (sorted(i2.atoms[a]["doc_id"]
                           for a in v["members"]),
                    [float(z) for z in v["descriptor"]])
                for h, v in x.items()}
        t.close()
        return snap
    sync = build(100000, False)
    deferred = build(0, True)
    same = sorted(sync) == sorted(deferred) and all(
        sync[h][0] == deferred[h][0]
        and np.allclose(sync[h][1], deferred[h][1], atol=1e-12)
        for h in sync)
    check("sync-drain-identical", same, f"{sync} vs {deferred}")

    # -- crash recovery: manifest deleted -> reconcile rebuilds ------
    man_path = os.path.join(sp, "ingest_manifest.json")
    pin_before = tl.pin()[3]
    os.remove(man_path)
    rrec = reconcile_manifest(tl, store_id="maint-test")
    check("reconcile-recovers",
          sorted(rrec["recovered_docs"]) == ["d1", "d2", "d3"]
          and rrec["repaired_ops"] >= 6
          and rrec["pending_placement"] == [], f"{rrec}")
    check("reconcile-idempotent",
          reconcile_manifest(tl)["repaired_ops"] == 0,
          "second reconcile must be a no-op")
    rep_re = ingest_docs(tl, docs, emb, store_id="maint-test")
    check("reconcile-reingest-skips",
          rep_re["n_atoms"] == 0 and rep_re["n_holons"] == 0
          and sorted(rep_re["skipped"]) == ["d1", "d2", "d3"]
          and tl.pin()[3] == pin_before, f"{rep_re}")
    idx_re = NarrowIndex(tl, tl.pin())
    dos_re, _ = NarrowQuery(tl, idx_re, emb1).run("zzz outlier")
    check("reconcile-retrievable",
          "d3" in [e["doc_id"] for e in dos_re["entries"]],
          "recovered store must serve")
    # -- re-drain is a commit-free no-op -------------------------------
    r_already = drain_placement_backlog(tl, store_id="maint-test",
                                        doc_ids=["d1", "d2", "d3"])
    check("drain-idempotent",
          r_already["drained"] == []
          and sorted(r_already["already_placed"]) == ["d1", "d2", "d3"]
          and r_already["n_commits"] == 0
          and tl.pin()[3] == pin_before, f"{r_already}")

    tl.close()
    tl2.close()
    print("store-root:", tmp)
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
