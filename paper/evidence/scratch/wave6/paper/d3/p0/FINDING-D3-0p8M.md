# FINDING — D3 point N=812,545 (PREREG6 sha 24b0d9a9…d4c6; hand d3-0p8m, VM, 1 attempt) — claude-sci, 2026-11-05 ~18:30Z
Hand RESULT: p0/VM-RESULT.md (copy). Tags: OBSERVED = recomputed by me; REPORTED = hand's logged numbers I did not re-time.

## Verified by me (OBSERVED, p0/verify_d3_gt.py on the VM, own loader and permutation)
My seeded permutation (default_rng 20261108) equals the hand's Q and S1 index slices (1000 / 812,545, both True); holding 109 shards = 7,134,906 rows; my dequant+renorm queries match the hand's Q.f32.npy to 3e-8; for a random 200 of the 1000 queries my exact top-10 over S1 equals the hand's gt_top10 in SET and ORDER (0 mismatches, 0 near-ties at the cut). Holding sha before/after: 437/437 identical (hand; my ferry check already matched laptop and VM). NOT re-derived: per-arm recall (the hand kept only means, no per-query retrieval lists, so I cannot recompute them; faiss indexes were deleted), timings, RSS.

## Numbers (REPORTED, from the hand's sweeps) — equal-recall >= 0.95 operating points
H HNSW ef32 recall 0.9628, VmRSS 1.516 GB (anon 1.49 GB), p50 0.234 ms; I IVF-PQ never reaches 0.95 (best 0.6224); I-R nprobe64 0.9538, RSS 723 MB (648 MB file-mapped f16 rows), p50 0.848 ms; T (4 shards) np100/S200 0.9757, summed shard RSS 254 MB, 54.6 ms/query (sum of per-shard batch means). Build wall: H 329 s, I 253 s, T 522 s. Disk served: H 1.47 GB, I-R 0.68 GB, T 2.05 GB.
Prereg lines (this N only): Q-lines as above; M: T/H = 0.1675, T/I-R = 0.351 -> trend verdict needs S2/S3 ("INCONCLUSIVE" until then); L: T SLOWER by 233x vs H, 64x vs I-R; B: T SLOWER by 1.59x vs H. Overall (hand): lowest RSS at equal recall is T (254 MB) < I-R < H.

## What I will NOT let the paper say from this point (read before drafting)
1. The T "memory" is a process-RSS figure for per-shard batch serves. The T process reads its files through the page cache (RssFile only 14.8 MB of a 2.05 GB store); HNSW holds its whole index in process memory. So T/H = 0.17 is a ratio of resident process bytes, NOT of memory needed to serve: T's page-cache working set and its disk-resident store (2.05 GB, larger than HNSW's 1.47 GB) are not in it, and the I-R arm shows what happens when rows are mmapped (648 MB file-resident). A "memory advantage" sentence needs the served-bytes basis too (addendum below), and cold-cache behaviour is untested.
2. T latency is 233x HNSW; the 54.6 ms is a batch mean sum over shards, not a persistent-service p50. Not a speed claim of any kind for TRACE.
3. One N: no slope, no trend claim; INCONCLUSIVE until 3.2M and 7.13M.
4. T uses the ANN path of cand_serve (2-bit scan + S rescore) with CAND_ROUTE=exact, my prereg's "route=ann" was an under-specified phrase the hand interpreted (method note 1); the hand's interpretation is the same invocation shape as the build script's S200 run, but it is an interpretation.
5. IVF-PQ training-sample seed was not in the prereg (hand used 20261108): disclosed, not a verdict input.
