# RESULTS vm-trace-sota-100m-baselines — COMPLETE (2026-11-04 ~07:20Z)

Status: COMPLETE for S0/S1/S1b/S2/S3 on both filed probe types. S4 not run
(HF out of network scope); G5/G6 splits not runnable (see Setup).
Machine-readable: `results.json` (+ `dense_queries.jsonl`, `bm25_queries.jsonl`).

## Setup (same corpus + same probes + same metrics, all systems)

- Corpus: sealed 100M store, 812,545 units (4 shards x ~203k), MiniLM-L6-v2
  384-d; corpus text `build/inputs/units-812545.jsonl`.
- Probes (filed on VM, none invented), reported SEPARATELY per type:
  - s8-probe x10: prefix texts + expect_ordinal (qpool idx 0,20,...,180).
  - authored x40: hand questions + source_ordinal.
  - G5/G6 chunk/noisy/cross + all_sources/leave_source_out: defined on the
    10M qual store whose probes/receipts are NOT on this VM -> not run.
- Metrics: M-fid = recall@10 vs per-shard f64 exact top-10 (receipt
  definition, strict set overlap); M-src = hit@10 + nDCG@10 on merged
  global top-10 with binary relevance (source ordinal = 1).
- Latency: single-thread BLAS + torch-1, nice 10, batch-1 search k=10.

## M-fid: recall@10 vs per-shard f64 exact GT

| system | s8-probe (n=40 shard-q) | authored (n=160) | ALL (n=200) |
|---|---|---|---|
| S1 guided | 1.0000 (sd 0) | 0.9981 (min 0.90, sd 0.0136) | 0.9985 (sd 0.0122) |
| S1b flat | 1.0000 | 1.0000 | 1.0000 |

S1b == GT on all 200 shard-queries (confirms the GT tie-break matches the
engine's exact path). S1 keeps 0.9985.

## M-src: merged top-10 hit@10 / nDCG@10 (binary source)

| system | s8 hit | s8 nDCG | authored hit | authored nDCG | ALL hit | ALL nDCG |
|---|---|---|---|---|---|---|
| S1 guided | 0.5000 | 0.3964 | 0.5250 | 0.4230 | 0.5200 | 0.4177 |
| S1b flat | 0.5000 | 0.3964 | 0.5250 | 0.4230 | 0.5200 | 0.4177 |
| S3 exact dense | 0.5000 | 0.3964 | 0.5250 | 0.4230 | 0.5200 | 0.4177 |
| S2 BM25 | 0.9000 | 0.9000 | 0.8000 | 0.6987 | 0.8200 | 0.7389 |
| S0 random (WEAK) | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Merged top-10 lists are IDENTICAL across S1/S1b/S3 on all 50/50 queries:
on these probes guided retrieval is indistinguishable from exact dense.
S0 = uniform random 10/812545 per query, seed 7 (expected hit ~1.2e-5).

## Latency (ms, single-thread, nice 10) + RAM peak

| stage | p50 | p95 | max |
|---|---|---|---|
| embed (MiniLM CPU, batch-1) | 13.4 | 16.7 | 18.4 |
| S1 search 1-shard (k=10) | 293.6 | 368.6 | 525.4 |
| S1 search 4-shard total | 1217.6 | 1423.4 | 1431.9 |
| S1b search 4-shard total | 1356.0 | 1483.2 | 1555.4 |
| S3 exact GEMM (batch-50 amortized, 4-shard total) | ~87.5 mean | — | — |
| S2 BM25 (batch-1, incl. retrieval only) | 6.1 | 36.9 | 50.5 |

RAM peak: dense leg 2172 MB (backend + one shard f64 rows at a time);
BM25 leg 3751 MB (index build + retrieval).
Honest note: in-process batched f64 GEMM (~88 ms/q total) is faster here
than 4 sequential engine calls (guided p50 1218 ms); TRACE's win at this
scale is scored-rows, not wall latency on this path.

## Work ratio (engine meta, 50/50 qpool queries, shard0, k=10)

- guided: s_effective = 1600 rows scored every query; exact: 203137 rows.
- Ratio: 1600/203137 = 0.7875% (~127x fewer scored rows), parents
  3000 vs 22995. Recall kept: 0.9985 (M-fid ALL).

## Bytes (du -sb, on-disk)

- S3 vectors-only (4x rows f32): 1248069632 B (~1.248 GB).
- S1 TRACE serving: estores ~2.053 GB + parents ~141 MB + assign ~3.3 MB
  + meta-builder ~81.5 MB = ~2.279 GB total (no text).
- Corpus text (shared, needed to serve passages): 810611174 B.
- Encoder (shared S1/S1b/S3): 91632065 B.
- S2 bm25s index (k1=1.2, b=0.75, lucene): 507339884 B (~507 MB);
  build 43.6 s + tokenize 45.7 s + read 5.5 s (wall 89 s total).
- Plain statement: TRACE's serving store (~2.28 GB) is LARGER than the
  exact f32 matrix (~1.25 GB): estore tiers + parents + meta cost bytes
  to save scored rows. No memory win is claimed.

## Key reading (complete)

On 50 filed text probes over the full 812,545-unit store, TRACE guided
keeps 0.9985 recall@10 vs exact dense while scoring 0.79% of rows (~127x
fewer), and its merged top-10 equals exact dense on 50/50 queries: TRACE
loses nothing to exact dense on these probes (M-src 0.52/0.418 both).
Where TRACE loses: (1) to BM25 on source retrieval — BM25 reaches
0.82/0.739 vs dense 0.52/0.418, because these probes (prefix excerpts +
questions authored from the source chunk) share distinctive terms with
their source; single-source binary relevance favours lexical match. This
is NOT a general "BM25 > dense" claim. (2) store bytes: TRACE serving
~2.28 GB vs exact f32 ~1.25 GB vs BM25 index ~0.51 GB. (3) served latency
on this engine path: guided p50 ~1218 ms vs exact batched GEMM ~88 ms vs
BM25 p50 6.1 ms. S4 bge: not run (HF out of this task's network scope).
