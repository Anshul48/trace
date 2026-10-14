"""Focused E3a test: REGION_DENSE_ATOMS region support.

Fixture: 12 docs. docA lex-matches the query; 10 mid docs have
dense-mid holons; docT has a dense-far centroid but one dense-close
atom (two chunks: far + close). Without E3a docT's region ranks last
(12th) and is cut by M_REGIONS (pinned 10 here for mechanism
isolation; product default 20 since 2026-10-04); with E3a its
member-atom support surfaces the region and the close atom is served.

Deterministic fake encoder; scratch store under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_region_dense_atoms.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402

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


V_Q = pad([1.0, 0.0, 0.0])
V_A = pad([0.0, 1.0, 0.0])
V_MID = pad([0.9, 0.4359, 0.0])  # cos ~0.9 with V_Q
V_FAR = pad([0.0, 0.0, 1.0])
V_CLOSE = pad([0.99, 0.01, 0.0])

QUERY = "apple"
DOCA = "apple solo"
DOCT = "far " * 250 + "CLOSE keywords here"


def emb(texts):
    out = []
    for t in texts:
        if "CLOSE" in t:
            out.append(list(V_CLOSE))
        elif t == DOCA:
            out.append(list(V_A))
        elif t.startswith("filler"):
            out.append(list(V_MID))
        else:
            out.append(list(V_FAR))
    return out


def emb1(q):
    assert q == QUERY
    return list(V_Q)


def main():
    tmp = tempfile.mkdtemp(prefix="tl-e3a-test-")
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="e3a-test")
    docs = [("docA", DOCA)]
    for i in range(10):
        docs.append((f"docM{i}", f"filler {i}"))
    docs.append(("docT", DOCT))
    # place_xdoc=False: E3a mechanism isolation (docT would otherwise
    # arrive via xdoc membership); placement interaction is covered in
    # test_placement.py.
    rep = ingest_docs(tl, docs, emb, store_id="e3a-test",
                      place_xdoc=False)
    check("ingest-13-atoms-12-holons",
          rep["n_atoms"] == 13 and rep["n_holons"] == 12, repr(rep))
    idx = NarrowIndex(tl, tl.pin())

    OFF = {"EMIT_DENSE_ATOMS": False, "REGION_DENSE_ATOMS": False,
           "PRUNE_SPLIT": False, "DISCLOSE_TOP1_CUT": None,
           "M_REGIONS": 10}
    base = dict(OFF, EMIT_DENSE_ATOMS=True)
    off = NarrowQuery(tl, idx, emb1, cfg=dict(base))
    dos_off, rec_off = off.run(QUERY)
    # promoted damped default (REGION_DENSE_WEIGHT=0.3, inherited)
    on = NarrowQuery(tl, idx, emb1,
                     cfg=dict(base, REGION_DENSE_ATOMS=True))
    dos_on, rec_on = on.run(QUERY)

    served_off = [e["doc_id"] for e in dos_off["entries"]]
    served_on = [e["doc_id"] for e in dos_on["entries"]]
    check("e3a-off-target-cut",
          "docT" not in served_off, repr(served_off))
    check("e3a-on-target-surfaced",
          "docT" in served_on, repr(served_on))
    check("e3a-region-count-same",
          rec_on["metrics"]["regions_ranked"]
          == rec_off["metrics"]["regions_ranked"] == 12,
          repr((rec_off["metrics"]["regions_ranked"],
                rec_on["metrics"]["regions_ranked"])))
    check("e3a-receipt-diagnostics",
          rec_on["metrics"]["region_dense_atoms"] is True
          and rec_on["metrics"]["region_dense_terms"] == 13
          and rec_off["metrics"]["region_dense_atoms"] is False
          and rec_off["metrics"]["region_dense_terms"] == 0,
          repr({k: rec_on["metrics"].get(k) for k in
                ("region_dense_atoms", "region_dense_terms")}))
    # E3a without the E1 arm has no darrf: no-op on regions.
    noarm = NarrowQuery(tl, idx, emb1,
                        cfg=dict(OFF, REGION_DENSE_ATOMS=True))
    dos_noarm, rec_noarm = noarm.run(QUERY)
    dos_ref, _ = NarrowQuery(tl, idx, emb1,
                             cfg=dict(OFF)).run(QUERY)
    check("e3a-noop-without-e1-arm",
          [e["doc_id"] for e in dos_noarm["entries"]]
          == [e["doc_id"] for e in dos_ref["entries"]]
          and rec_noarm["metrics"]["region_dense_terms"] == 0,
          repr([e["doc_id"] for e in dos_noarm["entries"]]))

    # Damped variant: weight 0 scales region terms to nothing (no flip).
    damp0 = NarrowQuery(tl, idx, emb1,
                        cfg=dict(base, REGION_DENSE_ATOMS=True,
                                 REGION_DENSE_WEIGHT=0.0))
    dos_d0, _rec_d0 = damp0.run(QUERY)
    check("e3a-weight-0-no-flip",
          "docT" not in [e["doc_id"] for e in dos_d0["entries"]],
          repr([e["doc_id"] for e in dos_d0["entries"]]))

    tl.close()
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
