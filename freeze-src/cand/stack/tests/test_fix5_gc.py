"""Fix-5 tests: GC units on synthetic dirs + ViewPool integration.

(a) collect() units: newest-K kept, oldest-first, pinned skip (even over
K), gen-broken + non-gen immunity, noop, pinned-over-cap, determinism,
idempotence. (b) Integration: 6-publish ViewPool chain with a held
straggler pin: pinned dir survives, over-cap receipted, release +
publish collects. No corpus.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_common as C  # noqa: E402

from tlsys.serving import gen_gc  # noqa: E402
from tlsys.serving import generation as gen_mod  # noqa: E402


def make_retained(base, names):
    retained = os.path.join(base, gen_mod.GEN_RETAINED_DIRNAME)
    os.makedirs(retained, exist_ok=True)
    for name in names:
        d = os.path.join(retained, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'generation.json'), 'w') as fh:
            fh.write('{"frontier": 0}')
    return retained


def listing(base):
    retained = os.path.join(base, gen_mod.GEN_RETAINED_DIRNAME)
    return sorted(os.listdir(retained))


def main():
    import tempfile
    base = tempfile.mkdtemp(prefix='fix5-gc-')

    # (a) units.
    make_retained(base, ['gen-10', 'gen-20', 'gen-30', 'gen-40', 'gen-50',
                         'gen-broken-1', 'gen-x'])
    with open(os.path.join(base, 'generations', 'notes.txt'), 'w') as fh:
        fh.write('not a dir')
    r = gen_gc.collect(base, 2, pinned=())
    assert r['gc_deleted'] == ['gen-10', 'gen-20', 'gen-30'], r
    assert r['gc_skipped_pinned'] == []
    assert 'gc_noop' not in r and 'gc_pinned_over_cap' not in r
    assert listing(base) == ['gen-40', 'gen-50', 'gen-broken-1', 'gen-x',
                             'notes.txt'], listing(base)

    # Pinned skip wins over the window, even over K.
    r = gen_gc.collect(base, 1, pinned=(40,))
    assert r['gc_deleted'] == ['gen-50'], r
    assert r['gc_skipped_pinned'] == ['gen-40'], r
    assert listing(base) == ['gen-40', 'gen-broken-1', 'gen-x',
                             'notes.txt'], listing(base)

    # Over-cap with every excess dir pinned: delete nothing, receipt it.
    make_retained(base, ['gen-60', 'gen-70'])
    r = gen_gc.collect(base, 1, pinned=(40, 60, 70))
    assert r['gc_deleted'] == []
    assert r['gc_pinned_over_cap'] is True
    assert r['gc_pinned_frontiers'] == [40, 60, 70]
    assert len(listing(base)) == 6  # nothing deleted

    # Noop at/below K (one listdir, no deletes).
    r = gen_gc.collect(base, 99, pinned=())
    assert r.get('gc_noop') is True and r['gc_deleted'] == []

    # Determinism: same inputs -> same victims on a twin tree.
    import shutil
    twin = tempfile.mkdtemp(prefix='fix5-twin-')
    shutil.rmtree(twin)
    shutil.copytree(base, twin)
    r1 = gen_gc.collect(base, 1, pinned=(60,))
    r2 = gen_gc.collect(twin, 1, pinned=(60,))
    assert r1['gc_deleted'] == r2['gc_deleted'], (r1, r2)
    assert listing(base) == listing(twin)
    # Idempotence: second pass is stable (eligible is [60] now).
    again = gen_gc.collect(base, 1, pinned=(60,))
    assert again['gc_deleted'] == [] and again.get('gc_noop') is True

    print('fix5 units: window/pinned/broken/noop/overcap/determinism ok')

    # (b) integration: 6 publishes, K=3, one straggler pin held throughout.
    # Intermediate views are released after advancing (only the current
    # view + the straggler stay held), so _retained mirrors live pins.
    ctx = C.make_pool_store(n_docs=5, seed=11, prefix='f5a')
    tl, pool, sdir = ctx['tl'], ctx['pool'], ctx['sdir']
    v = pool.acquire(ctx['pin'])
    C.seal(pool, v)
    outs = [pool.publish_generation(v)]
    f_old = outs[0]['publish']['frontier']
    straggler = pool.acquire(ctx['pin'])  # pins the first frontier
    assert f_old in set(pool._retained)
    cur = v
    for (n, seed, pre) in ((3, 12, 'f5b'), (3, 13, 'f5c'), (3, 14, 'f5d'),
                           (3, 15, 'f5e'), (3, 16, 'f5f')):
        pin = C.ingest_batch(ctx, n, seed, pre)
        nxt = pool.advance(cur, pin)
        pool.release(cur)
        cur = nxt
        C.seal(pool, cur)
        outs.append(pool.publish_generation(cur))
    modes = [o['verify']['verify_mode'] for o in outs]
    assert modes == ['full', 'suffix', 'suffix', 'full', 'suffix',
                     'suffix'], modes
    retained = listing(sdir)
    assert f'gen-{f_old}' in retained, retained  # straggler survived
    assert len([n for n in retained if n.startswith('gen-')]) <= 3, retained
    assert all('gc_deleted' in o['publish'] for o in outs)
    # Release the straggler (refs drop to 0; the mirror keeps F1 while it
    # is within the K window), advance once (evicts F1 from _retained as
    # oldest-unref'd over cap), then publish: F1 is beyond-K + unpinned,
    # so this pass collects it (retire-when-unpinned at the next pass).
    pool.release(straggler)
    assert straggler._refs == 0
    pin = C.ingest_batch(ctx, 2, 17, 'f5g')
    nxt = pool.advance(cur, pin)
    pool.release(cur)
    cur = nxt
    assert f_old not in set(pool._retained)
    C.seal(pool, cur)
    last = pool.publish_generation(cur)
    retained = listing(sdir)
    assert f'gen-{f_old}' not in retained, retained
    assert len([n for n in retained if n.startswith('gen-')]) <= 3, retained
    assert last['publish']['gc_deleted'] == [f'gen-{f_old}'], \
        last['publish']
    pool.release(cur)
    tl.close()
    print('fix5 integration: chain %s, straggler survived then collected, '
          'retained<=K' % (modes,))
    print('PASS test_fix5_gc')
    return 0


if __name__ == '__main__':
    sys.exit(main())
