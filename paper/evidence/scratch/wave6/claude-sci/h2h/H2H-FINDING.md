# FINDING — same-store head-to-head: standard FAISS vs TRACE guided on the sealed 100M-token store (claude-sci, 2026-11-05 ~13:00Z)
Job trace-100m-faiss-h2h (VM, hand), PREREG sha256 42bc334d3dd26a54e593e585e96eef2773e18e07b0fc82bb4c003052d1cb2ab1 (written before the run). Full tables: VM ~/owner-hub/scratch/wave2/trace-100m-faiss-h2h/RESULT.md (also coord/outbox/trace-100m-faiss-h2h.result.md). Tag BUILT-measured-on-VM. FOR THE OWNER BATCH; NOT public text.
Scope: 812,545 units (99.9M tok_v1 tokens), dim 384, 50 filed probes, one shared 4-vCPU VM. NOT a 100M-vector or 1B claim.

## Result (pre-registered verdicts, literal)
- Q-line met by: exact flat, HNSW M32/efC200 efSearch=128 (recall@10 0.992, hit@10 26/50) and efSearch=256 (0.996). IVF-SQ8 and PQ48+rerank did NOT meet it (best 0.960 / 0.950).
- S-line: best passing config HNSW ef128 p50 0.66 ms (search only, 1 thread) vs live guided service p50 1236 ms: R = 1884 => pre-registered verdict "TRACE guided search is DOMINATED by a standard index on this store". Including measured query embedding (13.76 ms p50): R_end2end ~ 86x (my arithmetic).
- M-line: HNSW ef128 RSS 1.44 GB (index 1.47 GB) <= 1.5 GB pass; TRACE serving 2.279 GB. No memory penalty for the standard index.
- Quality is identical, not better: every dense arm tops out at M-src 0.52 (26/50), the same as TRACE guided and exact; BM25 stays higher at 0.82. The standard index changes the cost, not the answer.
- Integrity: exact flat reproduces the filed exact top-10 50/50 (47/50 same order, 3 swaps are bit-identical float ties); store sha256 x9 unchanged before/after.

## claude-sci independent check (own code, VM)
Store rows sha 4/4 match sha-before; own numpy exact top-10 as ground truth; the hand's saved HNSW index reloaded: recall@10 0.968 / 0.992 / 0.996 at ef 64/128/256 (identical to the hand's), p50 0.389 / 0.684 / 1.222 ms (hand 0.37/0.66/1.20); live guided service 1234.1 ms p50 on 12 queries from my own client. Own batched numpy exact: 25.4 ms/query (batch 50, 4 threads) — also far under TRACE guided.

## Caveats (do not drop)
1. Different jobs: the service returns parents/path/text through hierarchy and routing; the FAISS arms return ids only. The comparison is retrieval-stage cost for the same top-10, not full product latency parity. Anything the service does beyond ids is unmeasured here.
2. Build cost not in the latency: HNSW add 378.6 s (4 threads), IVF-SQ8 ~108 s total; index files 1.47 GB / 322 MB / 49 MB. Persistence/crash-safe publish/append behaviour of FAISS is not tested here; TRACE's sealed store, 2-bit codes and federation story are not evaluated by this test.
3. 812,545 vectors is small: HNSW's RAM (1.47 GB) scales linearly (about 15 GB at ~8M f32 vectors); the earlier 7.13M IVF results (ruling §9) show the cheaper variants. Nothing here transfers to 100M vectors or 1B.
4. Shared VM, 50 probes, one run; load averages recorded 0.5-1.6 (gate 2.0), one arm-L crash and rerun disclosed by the hand.
5. TRACE guided's 0.79%-of-rows scoring (~127x less work, recall 0.9985 vs exact) is real work reduction but did not become wall-time reduction: the exact batched GEMM (87.5 ms filed, 25 ms my batched run) already beats it.

## What this supports (architect decides)
- OBSERVED: for candidate retrieval at this store size, an adopted standard index gives the same top-10 quality at ~1000x lower latency. Per AGENTS.md ("adopt before you build") the candidate stage of compile_workspace should sit behind a narrow index interface with HNSW/IVF as the reference implementation and the sealed guided path as one optional backend; glass-pavo's sieve measurements should use this as the stage-1 baseline.
- NOT supported: any public sentence claiming TRACE beats or matches standard retrieval on speed; the allowed honest framing remains "guided search scores 0.79% of rows at 0.9985 of exact recall" without a latency-win claim.
