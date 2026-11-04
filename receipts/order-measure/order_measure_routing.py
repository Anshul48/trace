#!/usr/bin/env python3
"""Ablation (NOT TRACE's engine): does the grouping matter for scoring few rows?

Same 2,000 random passages of part 0 as order_measure_passages.py, used as HELD-OUT queries (stored vectors only, no embedding):
those 2,000 rows are removed from the library, so they take no part in the groups' centres, sizes or neighbours.
Truth = each held-out passage's exact top-10 among the remaining 201,137 rows (float32 brute force).
Simplest possible sparse search: rank the group centres by cosine to the query, take the best groups until about
BUDGET rows are collected, assume perfect re-scoring inside them, and count how many of the exact top-10 were collected.
Same procedure for (1) the real k-means groups, (2) input-order blocks (same group count), (3) shuffled labels (same sizes).
Centres are recomputed from each labelling (normalised group mean). Read-only; nice -n 10.
"""
import sys

import numpy as np

B = "/home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build"
SEED = 20261104
N_Q = 2000
BUDGETS = [1600, 4000, 10000, 20000]
s = 0
rng = np.random.default_rng(SEED + 1)
a = np.load("%s/shard%d-build/assign-shard%d.int32.npy" % (B, s, s)).reshape(-1)
X = np.array(np.load("%s/shard%d-build/rows-shard%d.f32.npy" % (B, s, s), mmap_mode="r"), dtype=np.float32)
X /= np.linalg.norm(X, axis=1, keepdims=True)
n_all = len(a)
K = int(a.max()) + 1
qidx = np.sort(rng.choice(n_all, N_Q, replace=False))
keep = np.ones(n_all, dtype=bool); keep[qidx] = False
Lidx = np.flatnonzero(keep)
XQ = X[qidx]
XL = X[Lidx]
aL = a[Lidx]
n = len(Lidx)
tops = []
for lo in range(0, N_Q, 250):
    S = XQ[lo:lo + 250] @ XL.T
    tops.append(np.argpartition(-S, 10, axis=1)[:, :10])
top = np.concatenate(tops)
print("part 0: %d library rows (the %d query passages removed), %d groups, %d held-out passage-queries" % (n, N_Q, K, N_Q), flush=True)

labelings = {
    "real k-means groups": aL.astype(np.int64),
    "input-order blocks": ((Lidx * K) // n_all).astype(np.int64),
    "shuffled labels": rng.permutation(aL).astype(np.int64),
}
print("rows budget -> mean rows actually collected | mean share of the exact top-10 collected")
for name, lab in labelings.items():
    order = np.argsort(lab, kind="stable")
    sl = lab[order]
    starts = np.flatnonzero(np.r_[True, sl[1:] != sl[:-1]])
    sums = np.add.reduceat(XL[order], starts, axis=0)
    cen = (sums / np.linalg.norm(sums, axis=1, keepdims=True)).astype(np.float32)
    gl = np.zeros(n, dtype=np.int64)          # row -> dense group index 0..Kd-1
    gid_sorted = np.repeat(np.arange(len(starts)), np.diff(np.r_[starts, n]))
    gl[order] = gid_sorted
    sizes = np.diff(np.r_[starts, n])
    res = {b: ([], []) for b in BUDGETS}
    for lo in range(0, N_Q, 250):
        ids = qidx[lo:lo + 250]
        C = XQ[lo:lo + 250] @ cen.T              # (250, Kd)
        og = np.argsort(-C, axis=1)              # best group first
        rank = np.empty_like(og)
        np.put_along_axis(rank, og, np.arange(og.shape[1])[None, :].repeat(og.shape[0], 0), axis=1)
        cs = np.cumsum(sizes[og], axis=1)
        nb = gl[top[lo:lo + 250]]                # (250,10) neighbour group
        nr = np.take_along_axis(rank, nb, axis=1)
        for b in BUDGETS:
            g = (cs < b).sum(axis=1) + 1         # groups taken until >= b rows
            g = np.minimum(g, cs.shape[1])
            rows = cs[np.arange(len(ids)), g - 1]
            got = (nr < g[:, None]).mean(axis=1)
            res[b][0].append(rows); res[b][1].append(got)
    print("\n%s (centres recomputed from these labels)" % name)
    for b in BUDGETS:
        rows = np.concatenate(res[b][0]); got = np.concatenate(res[b][1])
        print("  budget %5d rows (%.2f%% of the part) -> collected %.0f rows on average | %.4f of the exact top-10 (sd %.3f)"
              % (b, 100.0 * b / n, rows.mean(), got.mean(), got.std(ddof=1)))
    sys.stdout.flush()
print("\nDONE")
