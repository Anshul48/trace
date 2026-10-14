"""Placement conformance: additive cross-doc xholons at ingest.

- decide(): threshold + budget cap (pure unit).
- ingest(place_xdoc=True): similar docs join (versioned meta, exact-mean
  descriptor), dissimilar docs create singletons (outliers durable),
  per-doc holons untouched, retrieval descends xdoc regions, state
  survives reopen, "xdoc-" doc ids refused.

Deterministic fake encoder; scratch store under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_placement.py
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
from tlsys.place import (  # noqa: E402
    MAX_XMEMBERSHIPS, T_PLACE, decide, read_xholons,
)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def pad(v):
    return [float(x) for x in v] + [0.0] * (8 - len(v))


V_A = pad([1.0, 0.0, 0.0])
V_A2 = pad([0.99, 0.01, 0.0])  # cos ~0.9999 with V_A
V_FAR = pad([0.0, 0.0, 1.0])
V_Q = pad([1.0, 0.0, 0.0])

DOCA = "alpha one"
DOCA2 = "alpha two"
DOCF = "far away tale"
QUERY = "alpha"


def emb(texts):
    out = []
    for t in texts:
        if t == DOCA or t == QUERY:
            out.append(list(V_A if t == DOCA else V_Q))
        elif t == DOCA2:
            out.append(list(V_A2))
        else:
            out.append(list(V_FAR))
    return out


def emb1(q):
    assert q == QUERY
    return list(V_Q)


def test_decide():
    xh = {f"xdoc-{i}": {"members": ["m"],
                        "descriptor": pad([0.9, 0.4359, 0.0]),
                        "seq": i} for i in range(5)}
    got = decide(pad([1.0, 0.0, 0.0]), xh)
    check("decide-caps-memberships",
          len(got) == MAX_XMEMBERSHIPS, repr(got))
    check("decide-threshold-miss",
          decide(pad([0.0, 0.0, 1.0]), xh) == [],
          repr(decide(pad([0.0, 0.0, 1.0]), xh)))
    full = {"xdoc-full": {"members": [f"m{i}" for i in range(25)],
                         "descriptor": pad([1.0, 0.0, 0.0]), "seq": 9}}
    check("decide-skips-full-holon",
          decide(pad([1.0, 0.0, 0.0]), full) == [], repr(full))
    assert T_PLACE == 0.55


def main():
    test_decide()
    tmp = tempfile.mkdtemp(prefix="tl-place-test-")
    root = os.path.join(tmp, "store")
    tl = TLStore(root, create=True, lease_owner="place-test")
    rep = ingest_docs(tl, [("docA", DOCA), ("docA2", DOCA2),
                           ("docF", DOCF)],
                      emb, store_id="place-test", place_xdoc=True)
    check("ingest-places",
          rep["n_atoms"] == 3 and rep["n_holons"] == 3
          and rep["n_xholon_ops"] == 3, repr(rep))
    xh = read_xholons(tl, tl.pin())
    check("similar-join-dissimilar-singleton",
          len(xh) == 2
          and len(xh["xdoc-docA"]["members"]) == 2
          and len(xh["xdoc-docF"]["members"]) == 1,
          repr({k: len(v["members"]) for k, v in xh.items()}))
    import numpy as np
    want = ((np.array(V_A) + np.array(V_A2)) / 2).tolist()
    got = xh["xdoc-docA"]["descriptor"]
    check("join-descriptor-exact-mean",
          all(abs(a - b) < 1e-9 for a, b in zip(got, want)),
          repr(got[:3]))
    # Per-doc holons untouched by placement.
    idx = NarrowIndex(tl, tl.pin())
    check("per-doc-holons-stable",
          all(len(idx.holons[d]["members"]) == 1
              for d in ("docA", "docA2", "docF")),
          repr({d: idx.holons[d]["members"] for d in idx.holons
                if not d.startswith("xdoc-")}))
    check("index-sees-xdoc-regions",
          "xdoc-docA" in idx.holons and "xdoc-docF" in idx.holons
          and len(idx.holons) == 5,
          repr(sorted(idx.holons)))
    # Retrieval descends xdoc regions; unplaced-style direct atoms work.
    nq = NarrowQuery(tl, idx, emb1, cfg={"EMIT_DENSE_ATOMS": True})
    dos, rec = nq.run(QUERY)
    served = [e["doc_id"] for e in dos["entries"]]
    check("retrieval-serves-placed-docs",
          "docA" in served and "docA2" in served, repr(served))
    check("receipt-counts-xdoc-regions",
          rec["metrics"]["regions_ranked"] == 5, repr(rec["metrics"]))
    tl.close()
    # Reopen: placement state durable.
    tl2 = TLStore(root, create=False, lease_owner="place-test")
    idx2 = NarrowIndex(tl2, tl2.pin())
    check("reopen-keeps-xholons",
          "xdoc-docA" in idx2.holons
          and len(idx2.holons["xdoc-docA"]["members"]) == 2,
          repr(sorted(idx2.holons)))
    dos2, _r2 = NarrowQuery(tl2, idx2, emb1,
                            cfg={"EMIT_DENSE_ATOMS": True}).run(QUERY)
    check("reopen-requery-identical",
          [e["doc_id"] for e in dos2["entries"]] == served,
          repr([e["doc_id"] for e in dos2["entries"]]))
    tl2.close()
    # Batch-cap guard: placement ops must never overflow the
    # committer's 10-op batch (pre-fix: ValueError on this shape).
    tl4 = TLStore(os.path.join(tmp, "store4"), create=True,
                  lease_owner="place-test")
    v3 = {"ax": pad([1.0, 0.0, 0.0]), "bx": pad([0.0, 1.0, 0.0]),
          "cx": pad([0.8, 0.6, 0.0])}

    def emb3(texts):
        return [list(v3[t.split()[0]]) for t in texts]

    rep4 = ingest_docs(tl4, [("docA", "ax " * 250),
                             ("docB", "bx"),
                             ("docC", "cx")],
                       emb3, store_id="place-test", place_xdoc=True)
    check("batch-cap-guard-joins-two",
          rep4["n_xholon_ops"] == 4, repr(rep4))
    xh4 = read_xholons(tl4, tl4.pin())
    check("batch-cap-guard-memberships",
          len(xh4) == 2
          and len(xh4["xdoc-docA"]["members"]) == 3
          and len(xh4["xdoc-docB"]["members"]) == 2,
          repr({k: len(v["members"]) for k, v in xh4.items()}))
    tl4.close()
    # Exact cap: a multi-atom doc whose join would push a holon past
    # MAX_XHOLON_MEMBERS is skipped (no overshoot) and creates anew.
    tl5 = TLStore(os.path.join(tmp, "store5"), create=True,
                  lease_owner="place-test")
    same = "same words here"
    docs5 = [(f"doc{i}", same) for i in range(24)]
    docs5.append(("docBig", "same words here " * 70))  # 210 toks, 2 atoms
    v_same = pad([1.0, 0.0, 0.0])

    def emb5(texts):
        return [list(v_same) for t in texts]

    rep5 = ingest_docs(tl5, docs5, emb5, store_id="place-test",
                       place_xdoc=True)
    xh5 = read_xholons(tl5, tl5.pin())
    sizes5 = sorted((len(v["members"]) for v in xh5.values()),
                     reverse=True)
    check("exact-cap-overflow-skipped-creates-anew",
          sizes5 == [24, 2] and "xdoc-docBig" in xh5,
          repr((sizes5, rep5["n_xholon_ops"])))
    tl5.close()
    # Namespace reservation.
    tl3 = TLStore(os.path.join(tmp, "store3"), create=True,
                  lease_owner="place-test")
    try:
        ingest_docs(tl3, [("xdoc-evil", "text")], emb,
                    store_id="place-test", place_xdoc=True)
        check("xdoc-prefix-refused", False, "no raise")
    except ValueError:
        check("xdoc-prefix-refused", True)
    tl3.close()
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
