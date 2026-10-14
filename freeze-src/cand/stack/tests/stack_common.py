"""Shared paths + synthetic fixtures for stack-fork tests (no corpus)."""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STACK = HERE.parent
CAND = STACK.parent

sys.path.insert(0, str(CAND / 'tools'))
sys.path.insert(0, str(CAND / 'fork' / 'tl-sys'))
sys.path.insert(0, str(CAND / 'fork' / 'tl-candidate-batch' / 'candidate'))
sys.path.insert(0, str(CAND / 'fork' / 'tl-sys' / 'tlsys' / 'serving' / 'tests'))


def batch(n, seed, prefix):
    from fixture import make_docs
    return [(f'{prefix}-{i}', t) for i, (_d, t) in
            enumerate(make_docs(n, seed=seed))]


def make_pool_store(n_docs=6, seed=7, prefix='s', serving_subdir='serving',
                    pool_config=None):
    """Scratch TLStore + organized docs + ViewPool. Returns namespace dict."""
    from fixture import emb_votes, make_store
    from tlsys.serving.view import ViewPool
    tl, tmp, pin = make_store(batch(n_docs, seed, prefix), emb_votes,
                              organize=True)
    sdir = os.path.join(tmp, serving_subdir)
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config=dict(pool_config or {}))
    return {'tl': tl, 'tmp': tmp, 'pin': pin, 'pool': pool, 'sdir': sdir,
            'birth': pin[0], 'epoch': pin[1]}


def ingest_batch(ctx, n_docs, seed, prefix):
    from fixture import emb_votes
    from tlsys.ingest import ingest_docs
    from tlsys.maint import organize_segments
    ingest_docs(ctx['tl'], batch(n_docs, seed, prefix), emb_votes)
    organize_segments(ctx['tl'])
    return ctx['tl'].pin()


def seal(pool, view):
    with pool.guarded():
        return pool.seal_locked(view)
