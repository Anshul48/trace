# 10M retrieval rung — Phase-2 query report (coordinator-written)

Date: 2026-10-04. The phase-1 builder's followup session lost execution
tools, so the coordinator ran the exact phase-2 command from BUILD-REPORT
§5 and authors this report. No tuning of any kind; first measurement on
this index sets the baseline.

Corpus: 13,081 docs / 10,003,381 TOK-v1 / 15,412,007 WP / 63,441 atoms
(exact TOK-10M vector; see BUILD-REPORT.md). Pin
`18869b2e-662c-462d-a695-5bf593e48cbf:0:95045` (phase-2 log confirms same
pin). Queries: 809 S1/tuning scifact (golds all in prefix, 565/565).
Candidate: final freeze 4c8c9673 (M_REGIONS=20). Timing: independent-v2
per-system end-to-end, encode cached for all.

## Results (n=809/system, 4045 rows, 0 errors)

| system | ndcg10 | rec5 | rec20 | mrr | p50 ms | p99 ms |
|---|---|---|---|---|---|---|
| bm25 | 0.5642 | 0.6227 | 0.6831 | 0.5343 | 2266 | 5346 |
| dense | 0.6442 | 0.7240 | 0.7616 | 0.6126 | 357 | 2698 |
| hybrid | 0.6563 | 0.7240 | 0.7917 | 0.6203 | 2629 | 5657 |
| **tl** | **0.6311** | **0.7015** | **0.7520** | **0.6011** | **2778** | **5993** |
| tl-unpruned | 0.6309 | 0.6953 | 0.7532 | 0.6006 | 2784 | 5988 |

1M → 10M deltas (same 809 queries, 8.6× harder negatives): tl −0.013
(0.6439 → 0.6311, ABOVE the §4 predicted ≈0.55–0.62 band); dense −0.009;
hybrid −0.007; bm25 −0.019. TL gap-to-dense: −0.010 → −0.013 (tier
unchanged); TL above BM25 by +0.067. Prune neutral (tl ≈ tl-unpruned).

## §4 acceptance (all provisional per D-12)

- (a) Completeness: ingest + index + 809 queries 0 errors; store 1.05 GB
  < 5 GB; peak RSS 1.65 GB < 8 GB. PASS.
- (b) Quality: TL ndcg10 0.6311 reported, no floor — first measurement
  sets the 10M baseline (above prediction). RECORDED.
- (c) Latency: p50 2778 ms vs provisional < 1 s — MISS; p99 5993 ms vs
  < 3 s — MISS. Per §4 this outcome is the specified FINDING
  "superlinear latency regime", not a failure. Signature: dense (no
  BM25 leg) p50 357 ms vs every BM25-touching system 2.3–2.8 s —
  full-scan BM25 over 63,441 atoms dominates. Same shape as the 1M
  confounded tails, now measured cleanly at 10M (no competing jobs in
  phase 2 after ingest).
- (d) Comparability: all 5 systems, same index, same run. PASS.

## Staged verdict: 10M RETRIEVAL EVIDENCED

First measured point of TL retrieval quality + latency + cost at ≥10M
tokens on a laptop. Quality tier preserved (−0.013 on 8.6× negatives);
cost within laptop ceilings (1.05 GB / 1.65 GB).

Binding constraint recorded: at 10M, TL p50 is already 2.8 s
(BM25-scan-dominated); linear projection puts 100M at ~28 s/query —
incompatible with D-13 (seconds-per-dossier @100M) under the current
full-scan architecture. 100M retrieval is NOT evidenced and NOT claimed;
indexed/two-stage BM25 (or equivalent) is the named future obligation
before any 100M rung. Dossier (S2/S3) quality at 10M remains out of scope
(no delta dossier queries).

Artifacts (this dir): metrics.json (sha 679575e4…), rows.jsonl (4045
rows, sha c08b2b77…), trace-scale10m-queries.json, queries.log,
driver_10m.py (measurement tool, import-only over frozen tlsys).
Campaign wall ≈ 2.3 h (11.6 s/query across 5 systems).
