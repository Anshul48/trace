#!/usr/bin/env python3
"""Group tightness: mean cosine of each stored passage vector to the (re-normalised) mean of its own group,
for (1) the real k-means groups, (2) shuffled group labels (same sizes), (3) input-order blocks (same count).
Cross-check: the real-groups value should match 'mean_cos_last' in kmeans-shardS.json.
Read-only. Run with the build venv python, nice -n 10.
"""
import json
import sys

import numpy as np

B = "/home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build"
rng = np.random.default_rng(20261104 + 2)


def tight(X, lab):
    order = np.argsort(lab, kind="stable")
    sl = lab[order]
    starts = np.flatnonzero(np.r_[True, sl[1:] != sl[:-1]])
    sums = np.add.reduceat(X[order], starts, axis=0)
    cen = sums / np.linalg.norm(sums, axis=1, keepdims=True)
    gid = np.repeat(np.arange(len(starts)), np.diff(np.r_[starts, len(sl)]))
    cos = (X[order] * cen[gid]).sum(axis=1)
    return float(cos.mean()), float(np.median(cos))


for s in range(4):
    a = np.load("%s/shard%d-build/assign-shard%d.int32.npy" % (B, s, s)).reshape(-1)
    X = np.array(np.load("%s/shard%d-build/rows-shard%d.f32.npy" % (B, s, s), mmap_mode="r"), dtype=np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    n = len(a)
    K = int(a.max()) + 1
    km = json.load(open("%s/shard%d-build/kmeans-shard%d.json" % (B, s, s)))
    logged = km["epochs"][-1]["mean_cos"]
    obs = tight(X, a)
    blk = tight(X, (np.arange(n) * K // n).astype(np.int64))
    sh = [tight(X, rng.permutation(a))[0] for _ in range(3)]
    print("part %d: tightness (mean cosine to own group centre)  real groups %.4f (median %.4f) | k-means log last pass %.4f | "
          "input-order blocks %.4f (median %.4f) | shuffled labels %.4f %.4f %.4f"
          % (s, obs[0], obs[1], logged, blk[0], blk[1], sh[0], sh[1], sh[2]))
    sys.stdout.flush()
km = json.load(open("%s/shard0-build/kmeans-shard0.json" % B))
print("part 0 k-means log, per pass: " + ", ".join(
    "pass %d: mean_cos %.4f, passages that changed group %.2f%%" % (e["epoch"], e["mean_cos"], 100 * e["moves_frac"]) for e in km["epochs"]))
print("DONE")
