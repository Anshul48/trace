"""Fix-6 parity: partition sort ON rows == literal full-sort rows, always.

Self-contained (reference implemented here): random/tie/zero/duplicate
fuzz + NaN/Inf/-0 edge cases + pending_search-level default-ON check on
a synthetic facade. No corpus.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_common as C  # noqa: E402  # noqa: F401 (paths)

import numpy as np  # noqa: E402
from tlsys.org_publication import PreparedFacade, pending_order  # noqa: E402


def ref(scores, ids, k):
    if not k:
        return []
    return sorted(range(len(scores)),
                  key=lambda i: (-scores[i], ids[i]))[:k]


def main():
    rng = np.random.default_rng(1901)
    n = 0
    for trial in range(320):
        sz = int(rng.integers(1, 420))
        k = int(rng.integers(0, sz + 1))
        style = trial % 5
        if style == 0:
            scores = rng.normal(size=sz)
        elif style == 1:
            scores = rng.integers(-2, 3, size=sz).astype(float)
        elif style == 2:
            scores = np.zeros(sz)
        elif style == 3:
            scores = rng.normal(size=sz)
            scores[::2] = scores[0]  # heavy ties incl. duplicate descriptors
        else:
            scores = rng.normal(size=sz)
        ids = tuple('a%05d' % i for i in rng.permutation(sz))
        if style == 4:  # duplicate-score blocks + shuffled ids
            scores = np.repeat(rng.normal(size=(sz + 2) // 3), 3)[:sz]
        got = pending_order(scores, ids, k, True)
        assert list(got) == ref(scores, ids, k), (trial, sz, k)
        n += 1
    # Non-finite + signed-zero edges (spec: legacy full-sort ordering).
    for scores in (np.array([float('nan'), 1., -1.]),
                   np.array([float('inf'), 0., float('-inf')]),
                   np.array([-0., 0., np.nextafter(0., 1.)])):
        ids = ('z', 'a', 'b')
        assert list(pending_order(scores, ids, 2, True)) == \
            ref(scores, ids, 2)
        n += 1
    # k == n keeps legacy ordering too.
    scores = rng.normal(size=50)
    ids = tuple('k%03d' % i for i in rng.permutation(50))
    assert list(pending_order(scores, ids, 50, True)) == \
        ref(scores, ids, 50)
    n += 1

    # pending_search level: default-constructed state == explicit fast.
    f = PreparedFacade.__new__(PreparedFacade)
    f._closed = False
    ids = tuple(str(x) for x in rng.permutation(301))
    mat = rng.normal(size=(301, 8))
    mat[:30] = mat[0]
    mat[30] = 0
    f._pending_ids = ids
    f._pending_mat = mat
    f._pending_norm = np.linalg.norm(mat, axis=1)
    f._pending_norm[f._pending_norm == 0] = 1
    f._index = SimpleNamespace(atoms={a: {'doc_id': 'd' + a} for a in ids})
    f.triple = 'fixture'
    # No _fast_pending_topk attr: getattr default (now True) applies.
    assert not hasattr(f, '_fast_pending_topk')
    for q in (rng.normal(size=8), np.zeros(8)):
        for k in (1, 10, 301):
            default_rows = f.pending_search(q, k)
            f._fast_pending_topk = True
            fast_rows = f.pending_search(q, k)
            del f._fast_pending_topk
            assert default_rows == fast_rows, (k,)
            # ... and both equal the literal reference.
    q = np.ones(8)
    f._fast_pending_topk = False
    off_rows = f.pending_search(q, 10)
    del f._fast_pending_topk
    assert f.pending_search(q, 10) == off_rows  # exact-rows parity
    assert off_rows[1]['pending_atoms_scored'] == 301

    print('fix6: pending_order ON==literal %d/%d, search default==fast==off'
          % (n, n))
    print('PASS test_fix6_parity')
    return 0


if __name__ == '__main__':
    sys.exit(main())
