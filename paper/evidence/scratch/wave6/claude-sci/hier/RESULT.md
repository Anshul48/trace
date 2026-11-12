# RESULT — trace-100m-hier-lift: parents/path lift vs flat ids at matched size (+ BM25/HNSW hybrid)

PREREG2 sha256 verified `30bf2aa97c82b9e7c41f344d8f8aa060c33b894e4e2efc596d1a8496a0eafc8c` before any work; PREREG2.md not edited. No ERRATUM-SUGGESTION (no PREREG2 line needed one; the R_tr top-10-only limit is per the task brief). All numbers measured on the VM in this run. Receipt tags: BUILT-measured-on-VM.

Scope: 812,545 units, 50 probes (10 s8-probe literal fragments + 40 authored questions), one shared 4-vCPU Azure VM; owner batch only, no public text; not a claim about other stores or products. No parameter tuning on the 50 probes (all configs fixed by PREREG2). Caveat: 10 probes are literal fragments of the source unit, which advantages BM25; s8 splits are reported separately.

## STEP 1 verification gate: PASS, 500/500

Live service queried sequentially once per probe (k=10, guided). Every returned passage `parents`/`path` equals `(shard, assign[row])` from the read-only assign arrays: agreement **500/500** (gate >= 480). Raw: `raw_step1_verify.jsonl` (per-passage agree flags), `step1_summary.json`.
Equality checks: live top-10 == recorded S1_guided_top10 on **50/50** (set and order); recorded S1 == S3_exact_top10 on **50/50** (set and order). HNSW top-10 (efSearch=256) == S1 on 49/50 (only `s8-40` differs by set and order); E(hnsw) context == E(tr) context on 49/50.

## Headline: expansion vs flat ids at matched context size

Source-hit = source ordinal in context. E(R) = top-10 + parent members ordered by dense f32 cosine, cap 100. Fk(R) = top-K of same R with K = final |C_q| (min 10). exactK = exact flat-f32 top-K. Metrics via filed `metrics.py`.

| arm | hits /50 | rate | nDCG | s8 /10 | auth /40 | raw file |
|---|---|---|---|---|---|---|
| F10(hnsw) | 26 | 0.5200 | 0.4177 | 5 | 21 | raw_F10_hnsw.jsonl |
| E(hnsw) | 31 | 0.6200 | 0.4439 | 5 | 26 | raw_E_hnsw.jsonl |
| Fk(hnsw) matched | 34 | 0.6800 | 0.4558 | 5 | 29 | raw_Fk_hnsw.jsonl |
| exactK (stricter control) | 35 | 0.7000 | 0.4597 | 5 | 30 | raw_exactK_hnsw.jsonl |
| F10(bm25) | 41 | 0.8200 | 0.7389 | 9 | 32 | raw_F10_bm25.jsonl |
| E(bm25) | 44 | 0.8800 | 0.7543 | 9 | 35 | raw_E_bm25.jsonl |
| Fk(bm25) matched | 48 | 0.9600 | 0.7674 | 10 | 38 | raw_Fk_bm25.jsonl |
| F10(tr) recorded | 26 | 0.5200 | 0.4177 | 5 | 21 | raw_F10_tr.jsonl |
| E(tr) | 31 | 0.6200 | 0.4439 | 5 | 26 | raw_E_tr.jsonl |

F10 reproduces the filed baselines exactly (hnsw/tr 0.52/0.418, bm25 0.82/0.739). For R_tr there is no matched Fk beyond 10 (recorded top-10 only; a top-K>10 would need extra service queries beyond the 50-once budget): E(tr) vs F10(tr) discordants are 5 E-only / 0 F10-only (`q01 q07 q22 q30 q37`), counts only, no matched test.

Discordants (exact binomial sign test, `lib_hl.py`, toy-tested in `test_hl.py`):

| comparison | E-only | Fk-only | two-sided p | one-sided p (E>) |
|---|---|---|---|---|
| E(hnsw) vs Fk(hnsw) | 0 | 3 (`q17 q21 q34`) | 0.25 | 1.0 |
| E(hnsw) vs exactK | 0 | 4 (`q12 q17 q21 q34`) | 0.125 | 1.0 |
| E(bm25) vs Fk(bm25) | 0 | 4 (`q04 q16 q23 s8-80`) | 0.125 | 1.0 |

## Verdicts (PREREG2 lines, literally, with numbers)

- H-line (E(hnsw) 31/50 minus matched Fk(hnsw) 34/50 = -3; one-sided p = 1.0): E-hits <= matched-Fk hits, therefore: "NO HIERARCHY LIFT: flat ids at equal budget do as well".
- B-line (does E(hnsw) reach hit >= 0.80?): No — E(hnsw) = 31/50 = 0.62. Also E(bm25) 44/50 vs matched Fk(bm25) 48/50 (diff -4; 0 E-only / 4 Fk-only; two-sided p = 0.125).
- HY-line (hybrid adds value iff hit@10 >= 43/50): H1 RRF = 38/50 = 0.76 and H2 min-max = 40/50 = 0.80, both below BM25 alone (41/50 = 0.82), therefore for both hybrids: "NO HYBRID GAIN OVER BM25".

## Hybrids (fixed configs, no tuning, both reported)

H1 = RRF k=60 over BM25 top-100 + HNSW top-100, top-10. H2 = 0.5/0.5 min-max fusion over the union (dense = exact f32 cosine, per-query min-max; absent-from-list scores 0; all-equal lists map present entries to 1.0; ties by ordinal). Raw: `raw_H1.jsonl`, `raw_H2.jsonl`.

| arm | hits /50 | rate | nDCG | s8 /10 (nDCG) | auth /40 (nDCG) |
|---|---|---|---|---|---|
| BM25 alone (filed: 0.82/0.739) | 41 | 0.8200 | 0.7389 | 9 (0.9000) | 32 (0.6987) |
| HNSW alone (filed: 0.52/0.418) | 26 | 0.5200 | 0.4177 | 5 (0.3964) | 21 (0.4230) |
| H1 RRF k=60 | 38 | 0.7600 | 0.5780 | 8 (0.5564) | 30 (0.5834) |
| H2 0.5/0.5 min-max | 40 | 0.8000 | 0.6642 | 9 (0.6987) | 31 (0.6555) |

BM25 on s8-probes is advantaged (literal fragments); both hybrids lose hits vs BM25 on authored (30/31 vs 32) as well as overall.

## P-diagnostic (reported only, no pass line)

Fraction of probes whose source's parent is among the parents of F10(R): hnsw 31/50 = 0.62, bm25 44/50 = 0.88, tr 31/50 = 0.62.
Chance null: 10 parents drawn i.i.d. uniform over the P_s = 22995 parents of the source's shard (all 4 shards have 22995 per SEAL): chance_q = 1 - ((P_s-1)/P_s)^10 = 0.000435 (without-replacement exact = 10/22995 = 0.000435); mean over probes identical since every P_s is equal. Observed fractions exceed chance by ~3 orders of magnitude on every R, so the diagnostic confirms parents carry signal but does not discriminate the arms (it mechanically upper-bounds E hits: P counts equal E hits on all three Rs, i.e. truncation never cut a source).

## K'_q distribution and truncation

| R | mean | median | min | max | truncated (raw>100) /50 |
|---|---|---|---|---|---|
| hnsw | 81.42 | 92.5 | 36 | 100 | 20 |
| bm25 | 89.38 | 100.0 | 32 | 100 | 34 |
| tr | 80.68 | 91.5 | 36 | 100 | 19 |

Sorted K' values: hnsw `[36 36 37 37 44 49 52 52 54 55 56 56 61 70 72 72 75 76 78 79 85 88 88 91 92 93 93 96 99 99 100x20]`; bm25 `[32 42 44 51 55 57 58 58 70 70 72 87 92 93 94 94 100x34]`; tr `[36 36 37 37 44 49 52 52 54 55 56 56 61 63 70 72 72 75 76 78 79 85 88 88 91 92 93 93 96 99 99 100x19]` (full per-query values in `summary_hl.json` `Kp_*`). Hit flags are evaluated on the truncated context; the matched Fk uses the same final K.

## Methods / fixed choices (no tuning)

- Query vectors: earlier job's `embeds.f64.npy` (read-only), cast to f32 + renormalised; rows: sealed f32 L2-normalised; all cosines are f32 `X @ q`. Exact top-100 by full stable argsort on -scores = (-score, ordinal); verified 50/50 set- and order-identical to filed S3 (`raw_exact_top100.jsonl`).
- R_hnsw: read-only `index_A1_HNSW.faiss`, efSearch=256, threads=1, top-100 (`raw_hnsw_top100.jsonl`; top-10 M-fid vs S3 = 0.9960 as in the earlier job). R_bm25: filed `bm25_index` loaded read-only (mmap), same tokenisation/settings, top-100 (`raw_bm25_top100.jsonl`; top-10 == filed S2_top10 on 50/50).
- Expansion extras ordered by (-cosine, ordinal); parent key (shard, pid); members ascending ordinal. RRF rank 1-based, ties by ordinal. H2 as above.
- Sign tests: two-sided p = 2*P(Bin(n,1/2) <= min(a,b)) capped at 1; one-sided (E>) p = P(X >= a); n = 0 gives 1.0.

## Load averages (1-min gate 2.0; no waits, no flags) and seals

- STEP1: 0.16 -> 0.88; HNSW: 0.58 -> 0.58; BM25: 0.58 -> 0.58; EXPAND: 0.60 -> 0.88 (full triples in `run.log`, `step1_summary.json`, `summary_hl.json`). One heavy process at a time under `nice -n 10`; `free -g` available stayed >= 28 GB (stop line < 4 GB never approached).
- sha-before.txt vs sha-after.txt: all 13 sha256 (4 rows f32 + 4 SEAL json + 4 assign int32 + units-812545.jsonl) UNCHANGED.

## Files (all under /home/anshul/owner-hub/scratch/wave2/trace-100m-hier-lift/, 888 KB)

RESULT.md, PREREG2.md (+ PREREG2.sha256), sha-before.txt, sha-after.txt, run.log, lib_hl.py, test_hl.py (32 tests, OK), sha_hash.py, step1_verify.py, step_hnsw.py, step_bm25.py, step_expand.py, step1_summary.json, summary_hl.json, raw_step1_verify.jsonl, raw_hnsw_top100.jsonl, raw_bm25_top100.jsonl, raw_exact_top100.jsonl, raw_F10/E/Fk/exactK/H1/H2 arm JSONLs (11 files). Every number above traces to a raw-file line via summary_hl.json.
