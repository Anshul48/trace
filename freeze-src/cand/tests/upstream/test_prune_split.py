"""Focused E3b test: support-split prune reserves dense-only seats.

Direct unit tests of the pure `_split_prune` helper with synthetic
rankings (no store), plus a flag-threading no-op check on a small live
fixture (pools under share -> identical to plain prune).

Run: tl-sys/.venv/bin/python tl-sys/tests/test_prune_split.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.fuse import static_prune  # noqa: E402
from tlsys.query import _split_prune  # noqa: E402
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


def test_helper():
    # 51 high lex-supported atoms + 4 low dense-only atoms, cap 50.
    scored = [(f"lex{i:02d}", 0.020 - i * 0.0001, f"text-lex-{i}")
              for i in range(51)]
    scored += [(f"den{i}", 0.0088 - i * 0.00001, f"text-den-{i}")
               for i in range(4)]
    fw = {f"a:lex{i:02d}": 0.020 - i * 0.0001 for i in range(51)}
    darrf = {f"a:den{i}": 0.0088 - i * 0.00001 for i in range(4)}
    plain = static_prune(scored, 50)
    check("plain-prune-evicts-dense-only",
          all(a.startswith("lex") for a, _s, _t in plain),
          repr([a for a, _s, _t in plain][-3:]))
    split = _split_prune(scored, fw, darrf, 50)
    aids = [a for a, _s, _t in split]
    check("split-prune-reserves-dense-only",
          all(f"den{i}" in aids for i in range(4))
          and len(aids) == 29,  # 25 lex share + 4 dense-only
          repr((len(aids), aids[-5:])))
    check("split-prune-score-ordered",
          all(split[i][1] >= split[i + 1][1]
              for i in range(len(split) - 1)),
          repr([round(s, 4) for _a, s, _t in split][:5]))
    # Neither-supported atoms are dropped by the split (they would
    # defer below-tau at admission anyway; no pairs in v1).
    scored2 = scored + [("non1", 0.0, "text-non-1")]
    split2 = _split_prune(scored2, fw, darrf, 50)
    check("split-prune-drops-neither",
          "non1" not in [a for a, _s, _t in split2],
          repr(len(split2)))


def pad(v):
    return [float(x) for x in v] + [0.0] * (8 - len(v))


VECS = {"apple banana": pad([0.0, 1.0]),
        "quantum paradox": pad([0.99, 0.01]),
        "apple": pad([1.0, 0.0])}


def emb(texts):
    return [list(VECS[t]) for t in texts]


def emb1(q):
    return list(VECS[q])


def test_noop():
    tmp = tempfile.mkdtemp(prefix="tl-e3b-test-")
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="e3b-test")
    ingest_docs(tl, [("docA", "apple banana"),
                     ("docB", "quantum paradox")],
                emb, store_id="e3b-test")
    idx = NarrowIndex(tl, tl.pin())
    cfg = {"EMIT_DENSE_ATOMS": True, "REGION_DENSE_ATOMS": False,
           "DISCLOSE_TOP1_CUT": None}
    plain = NarrowQuery(tl, idx, emb1,
                        cfg=dict(cfg, PRUNE_SPLIT=False))
    dos_p, _r = plain.run("apple")
    split = NarrowQuery(tl, idx, emb1,
                        cfg=dict(cfg, PRUNE_SPLIT=True))
    dos_s, _r = split.run("apple")
    check("split-noop-when-pools-under-share",
          [(e["doc_id"], e["emitted_score"])
           for e in dos_s["entries"]] ==
          [(e["doc_id"], e["emitted_score"])
           for e in dos_p["entries"]],
          repr(([e["doc_id"] for e in dos_s["entries"]],
                [e["doc_id"] for e in dos_p["entries"]])))
    tl.close()


def main():
    test_helper()
    test_noop()
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
