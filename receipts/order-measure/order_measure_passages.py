#!/usr/bin/env python3
"""Robustness check for (a): passage-as-query, using ONLY stored vectors (no embedding run).

For 2,000 random passages of a part, find each passage's exact top-10 neighbours among the other rows of the
part (float32 brute force over the stored 384-d vectors, the passage itself excluded), then measure how many
distinct groups those ten fall into (same N / H / MAX as order_measure.py) against shuffled group labels and
against input-order blocks. Also: share of the ten that sit in the passage's OWN group.
Read-only. Run with the build venv python, nice -n 10, OMP_NUM_THREADS=2.
"""
import math
import sys
from collections import Counter

import numpy as np

B = "/home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build"
SEED = 20261104
N_Q = 2000
N_SHUF = 200
PARTS = [int(x) for x in sys.argv[1:]] or [0]
rng = np.random.default_rng(SEED + 1)


def hbits(c):
    n = float(sum(c))
    return -sum((x / n) * math.log2(x / n) for x in c if x)


def stats(a, top, qidx):
    G = a[top]
    N, H, M, own = [], [], [], []
    for r, qi in zip(G.tolist(), qidx.tolist()):
        c = Counter(r)
        v = list(c.values())
        N.append(len(v)); H.append(hbits(v)); M.append(max(v)); own.append(c.get(int(a[qi]), 0) / 10.0)
    return np.array(N, float), np.array(H, float), np.array(M, float), np.array(own, float)


def summ(x):
    return "mean %.3f  sd %.3f  min %.3f  median %.3f  max %.3f" % (x.mean(), x.std(ddof=1), x.min(), np.median(x), x.max())


for s in PARTS:
    a = np.load("%s/shard%d-build/assign-shard%d.int32.npy" % (B, s, s)).reshape(-1)
    X = np.array(np.load("%s/shard%d-build/rows-shard%d.f32.npy" % (B, s, s), mmap_mode="r"), dtype=np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    n = len(a)
    K = int(a.max()) + 1
    qidx = np.sort(rng.choice(n, N_Q, replace=False))
    tops = []
    for lo in range(0, N_Q, 250):
        ids = qidx[lo:lo + 250]
        S = X[ids] @ X.T
        S[np.arange(len(ids)), ids] = -np.inf
        t = np.argpartition(-S, 10, axis=1)[:, :10]
        tops.append(t)
    top = np.concatenate(tops)
    oN, oH, oM, oOwn = stats(a, top, qidx)
    ba = (np.arange(n) * K // n).astype(np.int64)
    bN, bH, bM, bOwn = stats(ba, top, qidx)
    sN, sH, sM, sOwn = [], [], [], []
    for _ in range(N_SHUF):
        pa = rng.permutation(a)
        N_, H_, M_, O_ = stats(pa, top, qidx)
        sN.append(N_.mean()); sH.append(H_.mean()); sM.append(M_.mean()); sOwn.append(O_.mean())
    sN, sH, sM, sOwn = map(np.array, (sN, sH, sM, sOwn))
    print("== part %d: %d random passages used as queries (exact top-10 among the other %d rows, float32) ==" % (s, N_Q, n - 1))
    print("OBSERVED   N groups: " + summ(oN))
    print("OBSERVED   H bits  : " + summ(oH))
    print("OBSERVED   MAX in one group: " + summ(oM))
    print("OBSERVED   share of the ten in the passage's own group: mean %.3f" % oOwn.mean())
    print("INPUT-ORDER BLOCKS N: mean %.3f  H: mean %.3f  MAX: mean %.3f  own-group share: mean %.3f" % (bN.mean(), bH.mean(), bM.mean(), bOwn.mean()))
    print("SHUFFLED LABELS (%d shuffles; mean over the %d queries per shuffle): N %.4f (%.4f..%.4f)  H %.4f (%.4f..%.4f)  MAX %.4f  own-group share %.5f"
          % (N_SHUF, N_Q, sN.mean(), np.percentile(sN, 2.5), np.percentile(sN, 97.5), sH.mean(), np.percentile(sH, 2.5), np.percentile(sH, 97.5), sM.mean(), sOwn.mean()))
    print("observed N histogram:", " ".join("N=%d:%d" % (k, v) for k, v in sorted(Counter(oN.astype(int).tolist()).items())))
    print()
    sys.stdout.flush()
print("DONE")
