# DATASETS.md — denominators, units, conditions, provenance, licensing

## Scope truth (read first)

The 1061-query BENCH10M comparisons ran on **fresh Narrow stores built
per lane** (K=100, C=1, MiniLM-L6-v2 rev `1110a243`, CPU) — they are
small-store retrieval-quality measurements, NOT 1061 queries evaluated
over the prebuilt 10M corpus. The actual-10M evidence is: the frozen
scale10m rung (§3), the A3 store probes (§4), and the 10M gate receipts
(ship-record + campaign-186 with its failures). Never substitute
fresh-store scores for 10M measurements.

Units: nDCG@10 / MAP@10 / Recall@20 / MRR (standard TB definitions,
linear nDCG gain); latencies p50/p95 in ms (lanes) or s (rung/probes);
ingest walls in s. Denominators are test-split queries; failures were
zero everywhere (1061 queries × arms).

## 1. BENCH10M lanes (fresh stores; A1 = shipped stack M80-P100-A40)

| lane | corpus (docs / queries) | A1 nDCG@10 | vs bm25 | vs dense | pinned source |
|---|---|---|---|---|---|
| smoke | technical-docs-dev fixture, 6 / 6 | 0.851 | −0.052 ns | — (no dense arm) | bundled TB fixture |
| curated | trace-engineering-curated, 100 / 320 | 0.621 | −0.018 ns | −0.030 ns | TB fixture (`210a20a4…`) |
| scifact | beir-scifact test, 5183 / 300 | 0.617 | −0.047 * | −0.028 ns | BeIR/scifact@`b3b53356` + qrels@`2938d17d` |
| nfcorpus | beir-nfcorpus test, 3633 / 323 | 0.295 | −0.015 ns | −0.021 * | BeIR/nfcorpus@`b5026a0e` + qrels@`a451b3b2` |
| pony | bright-pony test, 7894 / 112 | 0.064 | +0.009 ns | +0.031 * | xlangai/BRIGHT@`3066d29c` |

`*` = p<0.05 (paired t-test, 2000-sample bootstrap CI, original
methodology); `ns` = not significant. A1 trails both references on
four lanes and is the best arm on pony (where all arms score low —
BRIGHT pony is a hard reasoning bench). The A40 emission cutoff costs
nothing measurable vs the A100 diagnostic on any lane. Full per-arm
tables: REPORT.md §0–§1; per-lane statistical compares (ALL arms,
wins and misses): `receipts-10m-shipped/lane-BENCH10M/*/compare-*.md`.

Corpus pull: 8 pinned files, all bytes+sha verified at pull
(`c2-bench10m-source-record.json`, full URLs + revisions + counts);
BEIR parquet→jsonl round-trip identical; UKP cross-check: docs+queries
byte-identical to UKP zips on both BEIR lanes, qrels bytes differ
(ordering; pinned bytes authoritative either way).

## 2. Licensing (bench corpora)

- trace fixtures (smoke `technical_docs_dev`, curated
  `trace_engineering_curated`): Apache-2.0 TB fixtures (curated
  vendored exact bytes in `c10m/data/upstream/`).
- BEIR scifact/nfcorpus parquets + qrels: BEIR Benchmark distribution
  (Apache-2.0) over third-party texts; the underlying SciFact abstracts
  record is ODC-By-1.0 per the original allenai/scifact LICENSE (see
  `c10m/data/DATA-README.md` §5, which also documents the downstream
  label differences). BeIR mirror card labels CC-BY-SA-4.0 (recorded
  downstream label, documented there).
- BRIGHT pony (xlangai/BRIGHT@`3066d29c`): per the upstream dataset
  card at that revision (consult before redistribution; links +
  revision pinned in `c2-bench10m-source-record.json`).
- No corpus bytes are bundled in this tree except the tiny smoke run
  outputs and the TB fixtures noted above; corpora arrive via the
  pinned pull (`harness/adapters/stage_pinned.py`).

## 3. Frozen scale10m rung (actual 10M store, Narrow 4c8c9673)

Corpus: 13081 docs / 10,003,381 TOK-v1 / 63,441 atoms; pin
`18869b2e-…:0:95045`. Queries: 809 S1/tuning scifact (golds in prefix,
565/565). n=809/system, 4045 rows, 0 errors; laptop run, encode cached.

| system | ndcg10 | rec5 | rec20 | mrr | p50 ms | p99 ms |
|---|---|---|---|---|---|---|
| bm25 | 0.5642 | 0.6227 | 0.6831 | 0.5343 | 2266 | 5346 |
| dense | 0.6442 | 0.7240 | 0.7616 | 0.6126 | 357 | 2698 |
| hybrid | 0.6563 | 0.7240 | 0.7917 | 0.6203 | 2629 | 5657 |
| **tl** | **0.6311** | **0.7015** | **0.7520** | **0.6011** | **2778** | **5993** |
| tl-unpruned | 0.6309 | 0.6953 | 0.7532 | 0.6006 | 2784 | 5988 |

1M→10M: tl −0.013 (above the predicted ≈0.55–0.62 band); prune neutral.
Acceptance: completeness PASS (1.05 GB store, 1.65 GB peak RSS);
latency MISS recorded as the specified FINDING "superlinear latency
regime" (BM25 full-scan over 63,441 atoms dominates; dense p50 357 ms
vs 2.3–2.8 s for every BM25-touching system). Binding constraint: 100M
retrieval is NOT evidenced and NOT claimed. Verdict: 10M RETRIEVAL
EVIDENCED. Receipts: `receipts-10m-shipped/scale10m/` (metrics
`679575e4…`, rows `c08b2b77…`, driver, logs; 48 MB queries file by hash
record `5222b2e5…`).

## 4. A3 deployment-condition probes (prebuilt 10M store, pin `:0:95436`)

Two independent runs (same A3 bytes), read-only store copy,
byte-verified then lock-rekeyed (content untouched), query `"take"`:

| run | open | enc load | attach/request (5×) | query (5×) | entries | wall |
|---|---|---|---|---|---|---|
| 156 | 2 ms | 6.4 s | 117–122 s | 0.78–1.41 s | 40/40 | 608 s |
| 162 | 2 ms | 6.3 s | 103–117 s | 0.78–1.09 s | 40/40 | 567 s |

Reading: ~1 s/query on the resident store; ~2 min NarrowIndex
(re)attach dominates every cold-attach request. Warm-cache
observations (no `drop_caches` sample). Outputs:
`store-probe.json` (156), `store-probe-162.json` (162).

## 5. 10M gate evidence

- Qualified shipping record: `receipts-10m-shipped/ship-record/`
  (`c2-10m-SHIPPED.md`: SHIP 2026-10-08, READ10M 7/7 PASS;
  `BUILD-RECEIPT.json`: verdict ok, mode 10m, final pin `:0:95436`,
  1886665268 B / 154074 files; `C2-10M-UPLOAD.json`: PASS, manifest
  `54c64001…`, roundtrip 4/4).
- Later campaign-186: `receipts-186/` — COMPLETE-10M with ORIGINAL F2
  overall FAIL; see `NEGATIVE-RESULTS.md`. Never presented as the build.
