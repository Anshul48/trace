"""Focused maintained test: posting-indexed BM25 (Track B scale repair).

Behavior contract (re-scoped per TRACKB-REPORT §1: scores <=1e-9 +
ranking equal up to exact ties):
- NarrowIndex.bm25 (posting-indexed) matches bm25_fullscan (the kept
  full-scan oracle) on keys and scores (<=1e-9 abs). Rankings must
  agree up to exact ties: each ranking is non-increasing in the OTHER
  leg's scores, so any inversion is confined to exactly-tied atoms.
  (Multi-term queries sum per-term contributions in different orders —
  doc-token order vs sorted-term postings order — so fp summation
  order (~1e-14) breaks exact ties differently at 10M scale. Neither
  leg has a privileged tie-break; both are correct readings.)
- bm25 is deterministic across repeated calls (sorted query terms:
  PYTHONHASHSEED-independent) and handles edge queries (empty,
  unknown terms, repeated terms) identically to the oracle.

Deterministic fake encoder through the documented embed seam, so no
model weights are needed. Needs the venv for blake3. Scratch store
under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_bm25_index.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex, toks  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 4
DOCS = [
    ("d-cat", "The domestic cat is a small carnivorous mammal Cats purr"),
    ("d-dog", "The domestic dog is a loyal companion Dogs bark loudly"),
    ("d-dup", "The domestic cat is a small carnivorous mammal Cats purr"),
    ("d-fuse", "An electrical fuse protects circuits from overcurrent"),
    ("d-empty-ish", "zxqy alone"),
]
QUERIES = [
    "which animal purrs when content",
    "the domestic cat",
    "the the the",  # repeated + stopword-heavy
    "zxqy unknownword wobble",  # mixed known/unknown
    "nosuchterm anywhere",  # all unknown
    "",  # empty
    "FUSE circuits fuse",  # case folding + repeats
]


def emb(texts):
    return [[float(len(t) % 7)] * DIM for t in texts]


def rank(d):
    return [a for a, _s in sorted(d.items(), key=lambda kv: -kv[1])]


def respects(order, scores):
    """True iff `order` is non-increasing in `scores`.

    A ranking that only permutes exactly-tied atoms still respects the
    other leg's scores; any inversion across a strict score gap fails.
    """
    return all(scores[order[i]] >= scores[order[i + 1]]
               for i in range(len(order) - 1))


def main():
    tmp = tempfile.mkdtemp(prefix="tl-bm25idx-test-")
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="bm25idx-test")
    rep = ingest_docs(tl, DOCS, emb, store_id="bm25idx-test")
    check("ingest-5-atoms", rep["n_atoms"] == 5, repr(rep))
    idx = NarrowIndex(tl, tl.pin())

    # Postings cover every (term, doc) pair exactly once.
    expect_pairs = set()
    for aid, text in idx.atom_text.items():
        for t in set(toks(text)):
            expect_pairs.add((t, aid))
    got_pairs = {(t, aid) for t, pl in idx.postings.items()
                 for aid, _f in pl}
    check("postings-cover-all-pairs", got_pairs == expect_pairs,
          f"missing={len(expect_pairs - got_pairs)} "
          f"extra={len(got_pairs - expect_pairs)}")
    tf_ok = True
    for t, pl in idx.postings.items():
        for aid, f in pl:
            if toks(idx.atom_text[aid]).count(t) != f:
                tf_ok = False
    check("postings-tf-exact", tf_ok)

    worst = 0.0
    order_ok = True
    for q in QUERIES:
        ref = idx.bm25_fullscan(q)
        new = idx.bm25(q)
        if set(ref) != set(new):
            order_ok = False
            print(f"key mismatch q={q!r}: {len(ref)} vs {len(new)}")
            continue
        for a, s in ref.items():
            worst = max(worst, abs(s - new[a]))
        # Ranking equality up to exact ties: each leg's ranking must be
        # non-increasing in the other leg's scores. Inversions are then
        # confined to exactly-tied atoms by construction.
        if not respects(rank(new), ref) or not respects(rank(ref), new):
            order_ok = False
            print(f"order mismatch (beyond ties) q={q!r}")
    check("indexed-matches-fullscan-keys-scores", worst <= 1e-9,
          f"worst_abs_diff={worst:.3e}")
    check("indexed-matches-fullscan-order-up-to-ties", order_ok)

    # Determinism: repeated calls incl. duplicate-text ties identical.
    r1 = [idx.bm25(q) for q in QUERIES]
    r2 = [idx.bm25(q) for q in QUERIES]
    check("indexed-deterministic",
          all(a == b for a, b in zip(r1, r2)))
    r_dup = rank(idx.bm25("domestic cat"))
    ia = [r_dup.index(a) for a in idx.atoms
          if idx.atoms[a]["doc_id"] in ("d-cat", "d-dup")]
    check("duplicate-docs-adjacent-tie",
          len(ia) == 2 and abs(ia[0] - ia[1]) == 1, repr(ia))
    dup_scores = idx.bm25("domestic cat")
    aids = [a for a in idx.atoms
            if idx.atoms[a]["doc_id"] in ("d-cat", "d-dup")]
    check("duplicate-docs-equal-scores",
          len(aids) == 2 and dup_scores[aids[0]] == dup_scores[aids[1]],
          repr({a[:8]: dup_scores[a] for a in aids}))

    tl.close()
    print("store-root:", tmp)
    print("RESULT:", "FAIL " + str(FAILS) if FAILS else "PASS")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
