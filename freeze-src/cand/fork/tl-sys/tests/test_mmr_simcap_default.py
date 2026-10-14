"""Maintained CAP03 test: MMR similarity-cap repair is the product default.

Covers the validated MMR-only repair (PROBE §§D/N: SIM_CAP=0.3
rescues exactly the 24 MMR-convicted contradiction units, 16/16
lane-metric cells hold-or-improve): the module default, the
capped-MMR pair mechanism, and the end-to-end seating of a
near-duplicate pair under default config on a small synthetic
fixture (no encoder weights needed).

Run: tl-sys/.venv/bin/python tl-sys/tests/test_mmr_simcap_default.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.fuse import mmr_order_matrix  # noqa: E402
from tlsys.query import MMR_SIM_CAP  # noqa: E402
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


def test_default():
    check("simcap-default-is-0.3", MMR_SIM_CAP == 0.3,
          f"MMR_SIM_CAP={MMR_SIM_CAP!r}")


def test_mechanism():
    # Near-duplicate pair (a,b; sim 0.999) + mid distractor c.
    cands = [("a", 1.0), ("b", 0.99), ("c", 0.97)]
    sims = {("a", "b"): 0.999, ("a", "c"): 0.3, ("b", "c"): 0.3}

    def sim(x, y):
        if x == y:
            return 1.0
        return sims.get((x, y), sims.get((y, x), 0.0))

    uncapped = mmr_order_matrix(cands, sim, 0.8, 3)
    check("simcap-uncapped-splits-pair", uncapped == ["a", "c", "b"],
          f"{uncapped}")
    capped = mmr_order_matrix(cands, sim, 0.8, 3, sim_cap=0.3)
    check("simcap-capped-keeps-pair", capped == ["a", "b", "c"],
          f"{capped}")


def pad(v):
    return [float(x) for x in v] + [0.0] * (8 - len(v))


DOCS = [
    ("docA", "apple banana harvest season", pad([1.0, 0.0])),
    ("docB", "apple banana harvest grove", pad([0.999, 0.0447])),
    ("doc0", "fruit banana", pad([0.30, 0.9539])),
    ("doc1", "banana grove", pad([0.27, 0.9628])),
]
QVEC = pad([1.0, 0.0])
VECS = {d[0]: d[2] for d in DOCS}
TEXT2ID = {d[1]: d[0] for d in DOCS}


def emb(texts):
    return [list(VECS[TEXT2ID[t]]) for t in texts]


def emb1(q):
    return list(QVEC)


def run_order(cfg_extra):
    tmp = tempfile.mkdtemp(prefix="tl-simcap-test-")
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="simcap-test")
    try:
        ingest_docs(tl, [(d[0], d[1]) for d in DOCS], emb,
                    store_id="simcap-test")
        idx = NarrowIndex(tl, tl.pin())
        cfg = {"EMIT_DENSE_ATOMS": True, "REGION_DENSE_ATOMS": False,
               "DISCLOSE_TOP1_CUT": None, "M_REGIONS": 80,
               "PRUNE_CAP": 100, "MAX_ENTRIES": 40}
        cfg.update(cfg_extra)
        nq = NarrowQuery(tl, idx, emb1, cfg=cfg)
        dos, _rec = nq.run("apple banana")
        return [e["doc_id"] for e in dos["entries"]]
    finally:
        tl.close()


def test_product_path():
    default_order = run_order({})
    check("simcap-default-seats-pair-jointly",
          default_order == ["docA", "docB", "doc0", "doc1"],
          f"{default_order}")
    none_order = run_order({"MMR_SIM_CAP": None})
    check("simcap-explicit-none-splits-pair",
          none_order == ["docA", "doc0", "docB", "doc1"],
          f"{none_order}")


def main():
    test_default()
    test_mechanism()
    test_product_path()
    print("RESULT:", "FAIL " + str(FAILS) if FAILS else "PASS")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
