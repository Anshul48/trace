"""Fix-2 tests: suffix chain, periodic/recovery full, fallback, orphan.

Synthetic ViewPool chain (no corpus): seal-aligned publishes engage
suffix; every Kth + post-quarantine publish is full; straddles fall
back receipted; scripted pointer moves produce receipted orphans with
no swap and no tmpdir leak. Independent from-zero re-verifies must
match suffix op_hash/tombstones on every swapped root (canary rule).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_common as C  # noqa: E402

from tlsys.serving import generation as gen_mod  # noqa: E402
from tlsys.serving.view import ViewPool  # noqa: E402

LEGACY5 = ('source_rows', 'source_retired', 'ranges', 'op_hash', 'op_hash_ok')


def live_root(sdir):
    return gen_mod.read_root(os.path.join(sdir, 'generation'))


def retained_root(sdir, frontier):
    return gen_mod.read_root(
        os.path.join(sdir, 'generations', f'gen-{frontier}'))


def check_full_shape(receipt, selected):
    for key in LEGACY5:
        assert key in receipt, receipt
    assert receipt['verify_mode'] == 'full'
    if selected:
        assert receipt['chain_ok'] is True
        assert 'fallback' not in receipt, receipt
    else:
        assert receipt['chain_ok'] is False
        assert receipt.get('fallback'), receipt


def check_suffix_shape(receipt):
    for key in LEGACY5 + ('verify_mode', 'chain_ok', 'prev_frontier',
                          'prev_digest', 'prefix_ranges', 'suffix_ranges',
                          'tombstone_union_ms'):
        assert key in receipt, receipt
    assert receipt['verify_mode'] == 'suffix'
    assert receipt['chain_ok'] is True
    assert isinstance(receipt['tombstone_union_ms'], float)


def independent_match(ctx, receipt):
    """Canary rule: from-zero re-verify reproduces op_hash + tombstones."""
    root = live_root(ctx['sdir'])
    indep = gen_mod.verify_against_source(
        root, ctx['tl'], ctx['birth'], ctx['epoch'], ctx['pool']._scan)
    assert indep['verify_mode'] == 'full'
    assert indep['op_hash'] == receipt['op_hash']
    assert indep['op_hash'] == root['range_summary']['op_hash']
    assert indep['source_retired'] == receipt['source_retired']


def main():
    ctx = C.make_pool_store(n_docs=6, seed=7, prefix='f2a')
    tl, pool, sdir = ctx['tl'], ctx['pool'], ctx['sdir']
    assert pool._needs_full_verify is True  # fresh pool re-anchors

    views = []
    v1 = pool.acquire(ctx['pin'])
    views.append(v1)
    C.seal(pool, v1)
    out1 = pool.publish_generation(v1)
    check_full_shape(out1['verify'], selected=True)
    assert pool._needs_full_verify is False and pool._suffix_streak == 0
    independent_match(ctx, out1['verify'])
    f1 = out1['publish']['frontier']

    pin2 = C.ingest_batch(ctx, 4, 23, 'f2b')
    v2 = pool.advance(v1, pin2)
    views.append(v2)
    C.seal(pool, v2)
    out2 = pool.publish_generation(v2)
    check_suffix_shape(out2['verify'])
    assert out2['verify']['prev_frontier'] == f1
    assert pool._suffix_streak == 1
    independent_match(ctx, out2['verify'])
    f2 = out2['publish']['frontier']

    pin3 = C.ingest_batch(ctx, 3, 31, 'f2c')
    v3 = pool.advance(v2, pin3)
    views.append(v3)
    out3 = pool.publish_generation(v3)  # aligned delta, no seal needed
    check_suffix_shape(out3['verify'])
    assert out3['verify']['prev_frontier'] == f2
    assert pool._suffix_streak == 2
    independent_match(ctx, out3['verify'])

    # Periodic full: streak 2 >= K-1 (K=3) forces full, selected.
    pin4 = C.ingest_batch(ctx, 3, 37, 'f2d')
    v4 = pool.advance(v3, pin4)
    views.append(v4)
    C.seal(pool, v4)
    out4 = pool.publish_generation(v4)
    check_full_shape(out4['verify'], selected=True)
    assert pool._suffix_streak == 0
    independent_match(ctx, out4['verify'])
    f4 = out4['publish']['frontier']

    pin5 = C.ingest_batch(ctx, 2, 41, 'f2e')
    v5 = pool.advance(v4, pin5)
    views.append(v5)
    C.seal(pool, v5)
    out5 = pool.publish_generation(v5)
    check_suffix_shape(out5['verify'])
    assert pool._suffix_streak == 1
    independent_match(ctx, out5['verify'])
    # Chain link: pub5's prev digest == pub4's retained root digest.
    assert out5['verify']['prev_digest'] == retained_root(sdir, f4)['digest']
    modes = [o['verify']['verify_mode'] for o in
             (out1, out2, out3, out4, out5)]
    assert modes == ['full', 'suffix', 'suffix', 'full', 'suffix'], modes

    # Suffix-bound proof: suffix scanned strictly fewer source rows than
    # from-zero, while ranges/op_hash/retired agree exactly.
    direct = gen_mod.verify_against_source(
        live_root(sdir), tl, ctx['birth'], ctx['epoch'], pool._scan)
    for key in ('ranges', 'op_hash', 'op_hash_ok', 'source_retired'):
        assert direct[key] == out5['verify'][key], key
    assert out5['verify']['source_rows'] < direct['source_rows'], (
        out5['verify']['source_rows'], direct['source_rows'])

    # Genuine straddle: seals that skip F_prev -> fallback full.
    f5 = out5['publish']['frontier']
    pin6 = C.ingest_batch(ctx, 3, 43, 'f2f')
    poolB = ViewPool(tl, ctx['birth'], ctx['epoch'], serving_dir=sdir)
    poolB._needs_full_verify = False  # steady state; test the fallback
    vB = poolB.cold_build(pin6, ranges=[(0, f5 - 10), (f5 - 10, pin6[2])])
    views.append(vB)
    outB = poolB.publish_generation(vB)
    check_full_shape(outB['verify'], selected=False)
    assert 'prefix ranges' in outB['verify']['fallback'] or \
        'boundary' in outB['verify']['fallback'], outB['verify']['fallback']
    independent_match(ctx, outB['verify'])
    fB = outB['publish']['frontier']

    # Quarantine: corrupt live root -> attach quarantines -> next publish
    # is a selected full (flag consumed); live regenerates.
    with open(os.path.join(sdir, 'generation', 'generation.json'),
              'w') as fh:
        fh.write('{corrupt')
    poolC = ViewPool(tl, ctx['birth'], ctx['epoch'], serving_dir=sdir)
    vC = poolC.acquire(pin6)
    views.append(vC)
    assert poolC._needs_full_verify is True
    quar = os.path.join(sdir, 'quarantined')
    assert os.path.isdir(quar) and os.listdir(quar), 'no quarantine dir'
    outC = poolC.publish_generation(vC)
    check_full_shape(outC['verify'], selected=True)
    assert poolC._needs_full_verify is False
    assert live_root(sdir)['frontier'] == fB
    independent_match(ctx, outC['verify'])

    # Orphan paths: scripted pointer moves (read_root interposed).
    live_now = live_root(sdir)
    kept = sorted(n for n in os.listdir(os.path.join(sdir, 'generations'))
                  if n.startswith('gen-') and n[len('gen-'):].isdigit())
    assert len(kept) >= 2, kept  # two distinct retained frontiers
    root_lo = retained_root(sdir, int(kept[-2][len('gen-'):]))
    root_hi = retained_root(sdir, int(kept[-1][len('gen-'):]))
    assert int(root_lo['frontier']) != int(root_hi['frontier'])
    before_digest = live_now['digest']
    streak_before = poolC._suffix_streak
    real_read_root = gen_mod.read_root
    try:
        # (a) persistent moves, advancing frontiers.
        script = [live_now, root_lo, root_lo, root_hi]
        gen_mod.read_root = lambda _p: script.pop(0)
        poolC._needs_full_verify = True  # force reusable full receipt
        orphan = poolC.publish_generation(vC)
        assert orphan.get('orphan') is True, orphan
        assert orphan['reason'] == 'pointer-moved-persistently', orphan
        assert real_read_root(
            os.path.join(sdir, 'generation'))['digest'] == before_digest
        assert poolC._suffix_streak == streak_before
        # (b) same frontier twice -> no-progress orphan.
        b_prime = dict(root_lo, digest='sha256:' + '0' * 64)
        script = [live_now, root_lo, root_lo, b_prime]
        gen_mod.read_root = lambda _p: script.pop(0)
        orphan2 = poolC.publish_generation(vC)
        assert orphan2.get('orphan') is True, orphan2
        assert orphan2['reason'] == \
            'pointer-moved-twice-without-frontier-advance', orphan2
        assert real_read_root(
            os.path.join(sdir, 'generation'))['digest'] == before_digest
    finally:
        gen_mod.read_root = real_read_root
    leftovers = [n for n in os.listdir(sdir)
                 if n.startswith(gen_mod.GEN_TMP_PREFIX)]
    assert leftovers == [], leftovers  # own tmpdir cleaned on orphan

    # K=1 pool: every publication is full.
    ctx1 = C.make_pool_store(n_docs=4, seed=5, prefix='f2k',
                             serving_subdir='serving-k1',
                             pool_config={'retained_generations_K': 1})
    w1 = ctx1['pool'].acquire(ctx1['pin'])
    C.seal(ctx1['pool'], w1)
    k1 = ctx1['pool'].publish_generation(w1)
    assert k1['verify']['verify_mode'] == 'full'
    pin_k2 = C.ingest_batch(ctx1, 2, 6, 'f2k2')
    w2 = ctx1['pool'].advance(w1, pin_k2)
    C.seal(ctx1['pool'], w2)
    k2 = ctx1['pool'].publish_generation(w2)
    assert k2['verify']['verify_mode'] == 'full'
    for w in (w1, w2):
        ctx1['pool'].release(w)
    ctx1['tl'].close()

    for v in views:
        try:
            pool.release(v)
        except Exception:
            pass
    try:
        poolB.release(vB)
    except Exception:
        pass
    try:
        poolC.release(vC)
    except Exception:
        pass
    tl.close()
    print('fix2: chain F/S/S/F/S, indep re-verify 7/7, straddle+quarantine '
          'full, orphan x2 (no swap, tmpdir clean), K=1 always-full')
    print('PASS test_fix2_suffix')
    return 0


if __name__ == '__main__':
    sys.exit(main())
