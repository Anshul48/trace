"""Minimal local demo: guided vs flat recall on a synthetic store (no corpus).

Builds a tiny two-level store with random FP32 vectors, runs one guided
(hierarchy-routed) and one flat (brute-force) top-10 query per probe with an
exact float64 oracle, and prints recall + work. This exercises the routing
*shape* only — it is not the 10M qualification and claims nothing about it.

Run:  python3 demo/synthetic_recall.py [--probes 20 --atoms 2000 --seed 7]
"""
import argparse
import numpy as np

P50_P95_NOTE = "timing here is illustrative, not a benchmark"


def build_store(rng, n_atoms, n_parents, dim=64):
    vecs = rng.normal(size=(n_atoms, dim)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-12
    parent_id = np.arange(n_atoms) % n_parents
    centroids = np.stack([
        vecs[parent_id == p].mean(axis=0) for p in range(n_parents)
    ]).astype(np.float64)
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True) + 1e-12
    return vecs, parent_id, centroids


def guided_topk(q, vecs, parent_id, centroids, k=10, beam=4):
    order = np.argsort(-(centroids @ q))[:beam]
    cand = np.flatnonzero(np.isin(parent_id, order))
    scores = vecs[cand].astype(np.float64) @ q
    top = np.argsort(-scores, kind="stable")[:k]
    return set(cand[top].tolist()), len(cand)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probes", type=int, default=20)
    ap.add_argument("--atoms", type=int, default=2000)
    ap.add_argument("--parents", type=int, default=32)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    vecs, parent_id, centroids = build_store(rng, args.atoms, args.parents)
    rec_sum, work = 0.0, 0
    for _ in range(args.probes):
        q = rng.normal(size=vecs.shape[1])
        q /= np.linalg.norm(q) + 1e-12
        oracle = set(np.argsort(-(vecs.astype(np.float64) @ q),
                                kind="stable")[:10].tolist())
        got, w = guided_topk(q.astype(np.float64), vecs, parent_id,
                             centroids)
        rec_sum += len(oracle & got) / 10.0
        work += w
    print(f"probes={args.probes} atoms={args.atoms} "
          f"guided_recall10={rec_sum / args.probes:.3f} "
          f"mean_parents_scored={args.parents} mean_atoms_rescored={work / args.probes:.0f}")
    print(f"note: {P50_P95_NOTE}; see docs/BENCHMARKS.md for the measured 10M receipt")


if __name__ == "__main__":
    main()
