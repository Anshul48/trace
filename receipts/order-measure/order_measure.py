#!/usr/bin/env python3
"""Read-only order measurement on the sealed 100M TRACE library (VM).

Inputs (all read-only, existing files, nothing rebuilt, no embedding run):
  W/dense_queries.jsonl                     50 test searches x 4 parts: exact (f64) top-10 row ids per part ('gt_ids')
  B/shardS-build/assign-shardS.int32.npy    group id (k-means parent) of every row of part S
  B/shardS-build/rows-shardS.f32.npy        stored 384-d passage vectors of part S (mmap, random rows only)
  B/shardS-build/parents-shardS.f32.npy     group centroids of part S
Run with the build venv python (numpy) and `nice -n 10`; writes nothing.
"""
import json
import math
import sys
from collections import Counter

import numpy as np

B = "/home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build"
W = "/home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines"
SEED = 20261104
N_SHUFFLES = 1000
N_PAIRS = 5000
rng = np.random.default_rng(SEED)


def hbits(counts):
    n = float(sum(counts))
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def row_stats(G):
    """G: list of lists of group ids (10 each). -> (N groups, H bits, max count) arrays."""
    N, H, M = [], [], []
    for r in G:
        c = list(Counter(r).values())
        N.append(len(c))
        H.append(hbits(c))
        M.append(max(c))
    return np.array(N, float), np.array(H, float), np.array(M, float)


def summ(x):
    x = np.asarray(x, float)
    return "mean %.3f  sd %.3f  min %.3f  median %.3f  max %.3f  (n=%d)" % (
        x.mean(), x.std(ddof=1) if len(x) > 1 else 0.0, x.min(), np.median(x), x.max(), len(x))


def pr(*a):
    print(*a)
    sys.stdout.flush()


# ---------------------------------------------------------------- load
assign = [np.load("%s/shard%d-build/assign-shard%d.int32.npy" % (B, s, s)).reshape(-1) for s in range(4)]
Q = [json.loads(l) for l in open(W + "/dense_queries.jsonl")]
kinds = [q["kind"] for q in Q]
pr("== INPUTS ==")
pr("queries:", len(Q), Counter(kinds))
pr("rows per part:", [len(a) for a in assign], " total", sum(len(a) for a in assign))
pr("groups per part (distinct ids):", [len(np.unique(a)) for a in assign])
# sanity: exact top-10 equals flat engine top-10 (S1b == GT)
same = sum(q["shards"][str(s)]["gt_ids"] == q["shards"][str(s)]["flat_ids"] for q in Q for s in range(4))
pr("gt_ids == flat_ids (exact engine) on %d of %d part-queries" % (same, len(Q) * 4))
for s in range(4):
    for q in Q:
        assert len(q["shards"][str(s)]["gt_ids"]) == 10
        assert max(q["shards"][str(s)]["gt_ids"]) < len(assign[s])

# ---------------------------------------------------------------- (a)
pr("\n== (a) exact top-10 neighbours across groups, per part ==")
pr("N = distinct groups holding the ten neighbours (max possible 10); H = Shannon entropy in bits of the")
pr("ten neighbours' spread over groups (max log2(10)=3.3219 bits at 10 groups, 0 bits if all in one group);")
pr("MAX = neighbours in the single most-populated group.")
obs = {}
shuf = {}
blk = {}
for s in range(4):
    a = assign[s]
    n = len(a)
    K = len(np.unique(a))
    gt = np.array([q["shards"][str(s)]["gt_ids"] for q in Q])  # (50,10) row ids local to part
    obs[s] = row_stats(a[gt].tolist())
    # baseline 1: shuffle group labels across rows (group sizes preserved)
    mN, mH, mM, sdN = [], [], [], []
    for _ in range(N_SHUFFLES):
        pa = rng.permutation(a)
        N_, H_, M_ = row_stats(pa[gt].tolist())
        mN.append(N_.mean()); mH.append(H_.mean()); mM.append(M_.mean()); sdN.append(N_.std(ddof=1))
    shuf[s] = (np.array(mN), np.array(mH), np.array(mM), np.array(sdN))
    # baseline 2: groups = consecutive passages in input order, same group count (floor(row*K/n))
    ba = (np.arange(n) * K // n).astype(np.int64)
    blk[s] = row_stats(ba[gt].tolist())


def report_part(label, idx):
    pr("\n-- %s --" % label)
    oN = np.concatenate([obs[s][0][idx] for s in parts])
    oH = np.concatenate([obs[s][1][idx] for s in parts])
    oM = np.concatenate([obs[s][2][idx] for s in parts])
    # shuffled: need per-shuffle mean over the same query set; recompute only for the full-set case from stored means
    pr("OBSERVED  N groups : " + summ(oN))
    pr("OBSERVED  H bits   : " + summ(oH))
    pr("OBSERVED  MAX in one group: " + summ(oM))
    bN = np.concatenate([blk[s][0][idx] for s in parts])
    bH = np.concatenate([blk[s][1][idx] for s in parts])
    bM = np.concatenate([blk[s][2][idx] for s in parts])
    pr("INPUT-ORDER BLOCKS N: " + summ(bN))
    pr("INPUT-ORDER BLOCKS H: " + summ(bH))
    pr("INPUT-ORDER BLOCKS MAX: " + summ(bM))
    return oN, oH, oM


allidx = np.arange(len(Q))
for s in range(4):
    parts = [s]
    report_part("part %d (50 test searches)" % s, allidx)
    mN, mH, mM, sdN = shuf[s]
    pr("SHUFFLED LABELS (%d shuffles, same group sizes), mean over the 50 searches per shuffle:" % N_SHUFFLES)
    pr("   N: mean-of-means %.4f  2.5%%..97.5%% of shuffle means %.4f..%.4f   avg per-search sd %.3f"
       % (mN.mean(), np.percentile(mN, 2.5), np.percentile(mN, 97.5), sdN.mean()))
    pr("   H: mean-of-means %.4f  2.5%%..97.5%% %.4f..%.4f" % (mH.mean(), np.percentile(mH, 2.5), np.percentile(mH, 97.5)))
    pr("   MAX: mean-of-means %.4f  2.5%%..97.5%% %.4f..%.4f" % (mM.mean(), np.percentile(mM, 2.5), np.percentile(mM, 97.5)))
    pr("   shuffles with mean N <= observed mean N: %d of %d" % (int((mN <= obs[s][0].mean()).sum()), N_SHUFFLES))

pr("\n-- POOLED over 4 parts (200 part-queries) --")
oN = np.concatenate([obs[s][0] for s in range(4)])
oH = np.concatenate([obs[s][1] for s in range(4)])
oM = np.concatenate([obs[s][2] for s in range(4)])
pr("OBSERVED  N groups : " + summ(oN))
pr("OBSERVED  H bits   : " + summ(oH))
pr("OBSERVED  MAX in one group: " + summ(oM))
sN = np.mean([shuf[s][0] for s in range(4)], axis=0)  # per-shuffle pooled mean (equal 50 per part)
sH = np.mean([shuf[s][1] for s in range(4)], axis=0)
sM = np.mean([shuf[s][2] for s in range(4)], axis=0)
pr("SHUFFLED  N: mean-of-means %.4f  2.5%%..97.5%% %.4f..%.4f" % (sN.mean(), np.percentile(sN, 2.5), np.percentile(sN, 97.5)))
pr("SHUFFLED  H: mean-of-means %.4f  2.5%%..97.5%% %.4f..%.4f" % (sH.mean(), np.percentile(sH, 2.5), np.percentile(sH, 97.5)))
pr("SHUFFLED  MAX: mean-of-means %.4f  2.5%%..97.5%% %.4f..%.4f" % (sM.mean(), np.percentile(sM, 2.5), np.percentile(sM, 97.5)))
bN = np.concatenate([blk[s][0] for s in range(4)])
bH = np.concatenate([blk[s][1] for s in range(4)])
bM = np.concatenate([blk[s][2] for s in range(4)])
pr("INPUT-ORDER BLOCKS N: " + summ(bN))
pr("INPUT-ORDER BLOCKS H: " + summ(bH))
pr("INPUT-ORDER BLOCKS MAX: " + summ(bM))

pr("\n-- part 0 split by search type --")
for kind in sorted(set(kinds)):
    idx = np.array([i for i, k in enumerate(kinds) if k == kind])
    pr("%s (n=%d): observed N mean %.3f  H mean %.3f  MAX mean %.3f | input-order blocks N mean %.3f"
       % (kind, len(idx), obs[0][0][idx].mean(), obs[0][1][idx].mean(), obs[0][2][idx].mean(), blk[0][0][idx].mean()))

pr("\n-- part 0 histogram of N (observed) --")
h = Counter(obs[0][0].astype(int).tolist())
pr(" ".join("N=%d:%d" % (k, h[k]) for k in sorted(h)))
pr("-- pooled histogram of N (observed) --")
h = Counter(oN.astype(int).tolist())
pr(" ".join("N=%d:%d" % (k, h[k]) for k in sorted(h)))

# ---------------------------------------------------------------- (b)
pr("\n== (b) within-group vs between-group cosine of stored passage vectors ==")
pr("%d pairs per kind per part, seed %d; cosine computed on explicitly re-normalised vectors." % (N_PAIRS, SEED))


def cosrows(R, i, j):
    a = np.asarray(R[i], dtype=np.float64)
    b = np.asarray(R[j], dtype=np.float64)
    a /= np.linalg.norm(a, axis=1, keepdims=True)
    b /= np.linalg.norm(b, axis=1, keepdims=True)
    return (a * b).sum(axis=1)


def mse(x):
    return "mean %.4f (se %.4f)  sd %.4f  median %.4f" % (x.mean(), x.std(ddof=1) / math.sqrt(len(x)), x.std(ddof=1), np.median(x))


bres = {}
for s in range(4):
    a = assign[s]
    n = len(a)
    R = np.load("%s/shard%d-build/rows-shard%d.f32.npy" % (B, s, s), mmap_mode="r")
    C = np.load("%s/shard%d-build/parents-shard%d.f32.npy" % (B, s, s))
    Cn = C / np.linalg.norm(C, axis=1, keepdims=True)
    order = np.argsort(a, kind="stable")
    sa = a[order]
    starts = np.searchsorted(sa, np.arange(sa.max() + 2))
    sizes = np.diff(starts)
    ok = np.where(sizes >= 2)[0]
    # within-group pairs: random groups with >=2 members, two distinct random members
    gsel = rng.choice(ok, N_PAIRS, replace=False)
    wi, wj = [], []
    for g in gsel:
        m = order[starts[g]:starts[g + 1]]
        p, q = rng.choice(len(m), 2, replace=False)
        wi.append(m[p]); wj.append(m[q])
    within = cosrows(R, np.array(wi), np.array(wj))
    # between-group pairs: random rows i, j with different groups
    bi, bj = [], []
    while len(bi) < N_PAIRS:
        i, j = rng.integers(0, n, 2)
        if a[i] != a[j]:
            bi.append(i); bj.append(j)
    between = cosrows(R, np.array(bi), np.array(bj))
    # hard between: a member of group g vs a random member of g's nearest OTHER centroid
    sims = Cn[gsel] @ Cn.T
    sims[np.arange(len(gsel)), gsel] = -2
    near = sims.argmax(axis=1)
    hi, hj = [], []
    for g, g2 in zip(gsel, near):
        m1 = order[starts[g]:starts[g + 1]]
        m2 = order[starts[g2]:starts[g2 + 1]]
        if len(m2) == 0:
            continue
        hi.append(m1[rng.integers(len(m1))]); hj.append(m2[rng.integers(len(m2))])
    hard = cosrows(R, np.array(hi), np.array(hj))
    # control: pairs inside a block of consecutive passages in input order (same K)
    K = int(a.max()) + 1
    ba = (np.arange(n) * K // n)
    bstarts = np.searchsorted(ba, np.arange(K + 1))
    bs = rng.choice(K, N_PAIRS, replace=False)
    ci, cj = [], []
    for g in bs:
        lo, hi_ = bstarts[g], bstarts[g + 1]
        if hi_ - lo < 2:
            continue
        p, q = rng.choice(hi_ - lo, 2, replace=False)
        ci.append(lo + p); cj.append(lo + q)
    ctrl = cosrows(R, np.array(ci), np.array(cj))
    bres[s] = (within, between, hard, ctrl)
    pr("\n-- part %d (groups with >=2 members: %d of %d) --" % (s, len(ok), K))
    pr("same group (k-means)              n=%d: %s" % (len(within), mse(within)))
    pr("different groups, random pair     n=%d: %s" % (len(between), mse(between)))
    pr("different groups, NEAREST rival   n=%d: %s" % (len(hard), mse(hard)))
    pr("control: same input-order block   n=%d: %s" % (len(ctrl), mse(ctrl)))
    pr("ratio of means: same-group / random-different = %.2f ; same-group / nearest-rival = %.2f ; same-group / input-order-block = %.2f"
       % (within.mean() / between.mean(), within.mean() / hard.mean(), within.mean() / ctrl.mean()))
    del R

# ---------------------------------------------------------------- (c)
pr("\n== (c) balance of group sizes ==")
for s in range(4):
    a = assign[s]
    sz = np.bincount(a)
    K = len(sz)
    n = int(sz.sum())
    srt = np.sort(sz)[::-1]
    ent = hbits(sz[sz > 0].tolist())
    pr("\npart %d: %d rows, %d groups (%d empty)" % (s, n, K, int((sz == 0).sum())))
    pr("  size: min %d  p1 %d  median %d  mean %.3f  p99 %d  max %d" % (sz.min(), np.percentile(sz, 1), np.median(sz), sz.mean(), np.percentile(sz, 99), sz.max()))
    pr("  share of the part's rows in the largest 10 groups: %.4f%%  largest 1%% of groups (%d): %.3f%%  largest 10%% of groups: %.3f%%"
       % (100 * srt[:10].sum() / n, int(K * 0.01), 100 * srt[:int(K * 0.01)].sum() / n, 100 * srt[:int(K * 0.1)].sum() / n))
    pr("  Shannon entropy of rows over groups: %.4f bits (maximum if all groups equal: log2(%d) = %.4f bits; ratio %.4f)"
       % (ent, K, math.log2(K), ent / math.log2(K)))
    pr("  groups holding 1 row: %d (%.2f%%)" % (int((sz == 1).sum()), 100 * (sz == 1).sum() / K))
pr("\nDONE")
