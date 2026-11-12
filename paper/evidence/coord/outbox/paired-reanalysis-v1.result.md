# RESULT — paired-reanalysis-v1 (EXPLORATORY / POST-HOC)

Document-paired reanalysis of the saved c-fuse rankings (J3 rank 5).
No new retrieval. No winner selection. Every table below is
EXPLORATORY/POST-HOC. Intervals are descriptive: each row gives the
point estimate, the 95% interval, and whether the interval includes
zero — nothing more.

- Date: 2026-11-06. Lease: `/home/anshul/owner-hub/scratch/wave2/paired-reanalysis-v1`.
- Evidence files were only read, never modified.

## Inputs (read-only)

| role | path |
|------|------|
| red-team brief | `/home/anshul/owner-hub/scratch/wave6/cx-arch/J3-paper-redteam.md` |
| earlier post-hoc | `/home/anshul/owner-hub/scratch/wave6/paper/evidence-cfuse/c-fuse-5/POSTHOC-OVERLAP.md` |
| shared lib (reused, not redefined) | `.../evidence-cfuse/c-fuse-5/lib_cfuse5.py` (hit_at, mrr_at, style_table, bootstrap_diff, paired_contrast) |
| rankings | `.../evidence-cfuse/{c-fuse-4,c-fuse-5,c-fuse-6}/raw_*_{Dr,Br,MMr,RRFr}.jsonl` |
| filed metrics | `.../evidence-cfuse/c-fuse-{4,5,6}/metrics.json`, `RESULT.md`, `gates.json` |
| queries | `/home/anshul/owner-hub/scratch/wave6/paper/repro-bundle-v1/queries/*.jsonl` |
| overlap def + sources | `/home/anshul/owner-hub/scratch/wave6/paper/repro-bundle-v1/plans/overlap/overlap_report.py`, `plans/{xg,x2,x3}/sources_*.jsonl`, `.../evidence-cfuse/c-fuse-6/overlap_x3.json` |

Query-file shas (bundle `queries/` == `plans/*/queries_*`, verified
identical): xg `ac87309c…0eb6b4`, x2m `77c620cf…9133c`, x2h
`0bba2a98…081b19`, x3l `705bc7e0…2fb81e`, x3h `c2e84d3c…9b3d89`.

## Method and exact commands

New analyses: cluster bootstrap, 5,000 resamples, seed 20261106.
Reproductions of published numbers: 10,000 resamples, seed 20261109
(the filed seed). numpy 2.5.4 via the existing venv (no installs).

```sh
cd /home/anshul/owner-hub/scratch/wave2/paired-reanalysis-v1
nice -n 10 /home/anshul/trace-v5/venv/bin/python reanalyse.py
python3 -W error::ResourceWarning -m unittest
/home/anshul/trace-v5/venv/bin/python -W error::ResourceWarning -m unittest
cat RESULT_head.md tables_gen.md RESULT_tail.md > RESULT.md
```

MATCH/MISMATCH criteria: recomputed-vs-filed float comparison with
tolerance 1e-9 for metrics.json values (sections A, D, E, overlap_x3
per-query); 3-decimal rounded comparison for printed descriptives
(EXPECTED.txt, POSTHOC-OVERLAP.md). Mismatches are reported, never
softened. Full-precision values: `results.json` in the lease.

Notes that apply everywhere: X2M/X2H query-id namespaces collide
(`X2-0000…`), so joins are per set; identity join is query id →
source ordinal (the filed label). 0 resamples were skipped in every
bootstrap in this report (all kept counts equal the requested
resamples). `overlap_x3.json` values are stored in `common_doc_ids`
order (verified: max|diff| = 0 after doc_id alignment).

## A. Sanity join (EXPLORATORY/POST-HOC recomputation)

| set | arm | hit_macro | filed | hit_verdict | mrr_macro | filed | mrr_verdict |
|-----|-----|-----------|-------|-------------|-----------|-------|-------------|
| XG | Dr | 0.678647 | 0.678647 | MATCH | 0.517493 | 0.517493 | MATCH |
| XG | Br | 0.718610 | 0.718610 | MATCH | 0.601802 | 0.601802 | MATCH |
| XG | MMr | 0.766024 | 0.766024 | MATCH | 0.637084 | 0.637084 | MATCH |
| XG | RRFr | 0.765990 | 0.765990 | MATCH | 0.605286 | 0.605286 | MATCH |
| X2M | Dr | 0.553333 | 0.553333 | MATCH | 0.444462 | 0.444462 | MATCH |
| X2M | Br | 0.563333 | 0.563333 | MATCH | 0.451175 | 0.451175 | MATCH |
| X2M | MMr | 0.576667 | 0.576667 | MATCH | 0.504282 | 0.504282 | MATCH |
| X2M | RRFr | 0.566667 | 0.566667 | MATCH | 0.488365 | 0.488365 | MATCH |
| X2H | Dr | 0.646667 | 0.646667 | MATCH | 0.517212 | 0.517212 | MATCH |
| X2H | Br | 0.626667 | 0.626667 | MATCH | 0.538493 | 0.538493 | MATCH |
| X2H | MMr | 0.700000 | 0.700000 | MATCH | 0.592652 | 0.592652 | MATCH |
| X2H | RRFr | 0.683333 | 0.683333 | MATCH | 0.553995 | 0.553995 | MATCH |
| X3L | Dr | 0.493333 | 0.493333 | MATCH | 0.280644 | 0.280644 | MATCH |
| X3L | Br | 0.283333 | 0.283333 | MATCH | 0.156231 | 0.156231 | MATCH |
| X3L | MMr | 0.526667 | 0.526667 | MATCH | 0.283131 | 0.283131 | MATCH |
| X3L | RRFr | 0.503333 | 0.503333 | MATCH | 0.264407 | 0.264407 | MATCH |
| X3H | Dr | 0.956667 | 0.956667 | MATCH | 0.817851 | 0.817851 | MATCH |
| X3H | Br | 0.990000 | 0.990000 | MATCH | 0.943028 | 0.943028 | MATCH |
| X3H | MMr | 0.990000 | 0.990000 | MATCH | 0.943056 | 0.943056 | MATCH |
| X3H | RRFr | 0.986667 | 0.986667 | MATCH | 0.906767 | 0.906767 | MATCH |

Join integrity: X2M/X2H doc_id sets identical: True; X3L/X3H identical: True; XG queries sharing a doc with X2: 0; X2M/X2H query-id namespaces collide (joined per set): True.
Kill criterion: NOT triggered (all 40 cells MATCH).

## B. All pairwise arm differences (EXPLORATORY/POST-HOC)

Cluster bootstrap over doc_id, 5000 resamples, seed 20261106, style-macro. No significance marking; 'zero_in' = whether the 95% interval includes zero.

### XG (n=297)

| pair | d_hit | hit_95 | zero_in | d_mrr | mrr_95 | zero_in | kept | skipped |
|------|-------|--------|---------|-------|--------|---------|------|---------|
| MMr-Dr | +0.087 | [+0.051,+0.125] | no | +0.120 | [+0.084,+0.156] | no | 5000 | 0 |
| MMr-Br | +0.047 | [+0.017,+0.080] | no | +0.035 | [+0.005,+0.067] | no | 5000 | 0 |
| RRFr-Dr | +0.087 | [+0.048,+0.128] | no | +0.088 | [+0.054,+0.122] | no | 5000 | 0 |
| RRFr-Br | +0.047 | [+0.016,+0.081] | no | +0.003 | [-0.034,+0.041] | yes | 5000 | 0 |
| MMr-RRFr | +0.000 | [-0.028,+0.028] | yes | +0.032 | [+0.012,+0.052] | no | 5000 | 0 |
| Br-Dr | +0.040 | [-0.010,+0.089] | yes | +0.084 | [+0.035,+0.133] | no | 5000 | 0 |

### X2M (n=300)

| pair | d_hit | hit_95 | zero_in | d_mrr | mrr_95 | zero_in | kept | skipped |
|------|-------|--------|---------|-------|--------|---------|------|---------|
| MMr-Dr | +0.023 | [+0.003,+0.045] | no | +0.060 | [+0.035,+0.085] | no | 5000 | 0 |
| MMr-Br | +0.013 | [-0.004,+0.033] | yes | +0.053 | [+0.031,+0.076] | no | 5000 | 0 |
| RRFr-Dr | +0.013 | [-0.009,+0.036] | yes | +0.044 | [+0.019,+0.070] | no | 5000 | 0 |
| RRFr-Br | +0.003 | [-0.014,+0.021] | yes | +0.037 | [+0.013,+0.061] | no | 5000 | 0 |
| MMr-RRFr | +0.010 | [+0.000,+0.023] | yes | +0.016 | [+0.005,+0.027] | no | 5000 | 0 |
| Br-Dr | +0.010 | [-0.018,+0.038] | yes | +0.007 | [-0.029,+0.041] | yes | 5000 | 0 |

### X2H (n=300)

| pair | d_hit | hit_95 | zero_in | d_mrr | mrr_95 | zero_in | kept | skipped |
|------|-------|--------|---------|-------|--------|---------|------|---------|
| MMr-Dr | +0.053 | [+0.019,+0.090] | no | +0.075 | [+0.046,+0.108] | no | 5000 | 0 |
| MMr-Br | +0.073 | [+0.043,+0.106] | no | +0.054 | [+0.026,+0.082] | no | 5000 | 0 |
| RRFr-Dr | +0.037 | [+0.002,+0.074] | no | +0.037 | [+0.007,+0.067] | no | 5000 | 0 |
| RRFr-Br | +0.057 | [+0.025,+0.088] | no | +0.016 | [-0.016,+0.045] | yes | 5000 | 0 |
| MMr-RRFr | +0.017 | [+0.000,+0.035] | yes | +0.039 | [+0.022,+0.057] | no | 5000 | 0 |
| Br-Dr | -0.020 | [-0.067,+0.028] | yes | +0.021 | [-0.024,+0.068] | yes | 5000 | 0 |

### X3L (n=300)

| pair | d_hit | hit_95 | zero_in | d_mrr | mrr_95 | zero_in | kept | skipped |
|------|-------|--------|---------|-------|--------|---------|------|---------|
| MMr-Dr | +0.033 | [-0.010,+0.079] | yes | +0.002 | [-0.035,+0.042] | yes | 5000 | 0 |
| MMr-Br | +0.243 | [+0.190,+0.299] | no | +0.127 | [+0.097,+0.158] | no | 5000 | 0 |
| RRFr-Dr | +0.010 | [-0.047,+0.069] | yes | -0.016 | [-0.063,+0.029] | yes | 5000 | 0 |
| RRFr-Br | +0.220 | [+0.168,+0.274] | no | +0.108 | [+0.080,+0.138] | no | 5000 | 0 |
| MMr-RRFr | +0.023 | [-0.018,+0.066] | yes | +0.019 | [-0.004,+0.042] | yes | 5000 | 0 |
| Br-Dr | -0.210 | [-0.278,-0.142] | no | -0.124 | [-0.174,-0.074] | no | 5000 | 0 |

### X3H (n=300)

| pair | d_hit | hit_95 | zero_in | d_mrr | mrr_95 | zero_in | kept | skipped |
|------|-------|--------|---------|-------|--------|---------|------|---------|
| MMr-Dr | +0.033 | [+0.014,+0.056] | no | +0.125 | [+0.097,+0.155] | no | 5000 | 0 |
| MMr-Br | +0.000 | [+0.000,+0.000] | yes | +0.000 | [-0.020,+0.020] | yes | 5000 | 0 |
| RRFr-Dr | +0.030 | [+0.013,+0.051] | no | +0.089 | [+0.064,+0.114] | no | 5000 | 0 |
| RRFr-Br | -0.003 | [-0.011,+0.000] | yes | -0.036 | [-0.062,-0.012] | no | 5000 | 0 |
| MMr-RRFr | +0.003 | [+0.000,+0.011] | yes | +0.036 | [+0.021,+0.054] | no | 5000 | 0 |
| Br-Dr | +0.033 | [+0.014,+0.056] | no | +0.125 | [+0.088,+0.162] | no | 5000 | 0 |

## C. Pooled overlap, clustered (EXPLORATORY/POST-HOC)

Overlap = bundle plans/overlap/overlap_report.py `ov`: fraction of the query's non-stopword tokens (lowercase [a-z0-9]+, WITH multiplicity) present in the source passage token set; 1.0 if no content tokens. Sources joined by ordinal. Gain = hit@10(MMr) - hit@10(Dr) per query, pooled query means (micro, the POSTHOC estimand). Clusters = doc_id across sets (X2M+X2H queries on one passage = one cluster).

| set | n | mean | filed | median | filed | verdict |
|-----|---|------|-------|--------|-------|---------|
| XG | 297 | 0.506 | 0.506 | 0.500 | 0.500 | MATCH |
| X2M | 300 | 0.355 | 0.355 | 0.444 | 0.444 | MATCH |
| X2H | 300 | 0.444 | 0.444 | 0.483 | 0.483 | MATCH |
| X3L | 300 | 0.216 | 0.216 | 0.200 | 0.200 | MATCH |
| X3H | 300 | 0.777 | 0.777 | 0.778 | 0.778 | MATCH |

overlap_x3.json per-query check (values aligned by common_doc_ids order):

- X3L: max|diff| = 0 -> MATCH
- X3H: max|diff| = 0 -> MATCH

POSTHOC-OVERLAP.md descriptive check (lint def, cut 0.45, micro means):

| set | gain ov<0.45 | filed | gain ov>=0.45 | filed | verdict |
|-----|-------------|-------|----------------|-------|---------|
| XG | +0.052 | +0.052 | +0.110 | +0.110 | MATCH |
| X2M | +0.000 | +0.000 | +0.048 | +0.048 | MATCH |
| X2H | -0.022 | -0.022 | +0.117 | +0.117 | MATCH |

Pooled n=897 queries in 597 doc_id clusters (297 XG singletons + 300 shared X2 pairs).

| cut | n_low | n_high | gain_low | gain_high | diff (high-low) | 95% CI (clustered) | zero_in | kept | skipped |
|-----|-------|--------|----------|-----------|----------------------|----------------------|---------|------|---------|
| 0.35 | 312 | 585 | -0.016 | +0.092 | +0.108 | [+0.075,+0.144] | no | 5000 | 0 |
| 0.40 | 347 | 550 | -0.009 | +0.095 | +0.103 | [+0.069,+0.138] | no | 5000 | 0 |
| 0.45 | 408 | 489 | +0.007 | +0.094 | +0.087 | [+0.051,+0.123] | no | 5000 | 0 |
| 0.50 | 435 | 462 | +0.009 | +0.097 | +0.088 | [+0.052,+0.125] | no | 5000 | 0 |

Continuous (OLS slope of per-query gain on lint overlap, cluster bootstrap): slope +0.199, 95% CI [+0.143,+0.260], zero_in no, kept 5000, skipped 0.

Stratified by lint-overlap tertile (cuts 0.3333 / 0.5882; T0 ov<=t1, T2 ov>t2):

| tertile | n | Dr hit (easiness) | gain (MMr-Dr) | gain 95% CI (clustered) | zero_in | kept | skipped |
|---------|---|-------------------|-----------------|--------------------------|---------|------|---------|
| T0 low | 312 | 0.221 | -0.016 | [-0.039,+0.006] | yes | 5000 | 0 |
| T1 mid | 287 | 0.815 | +0.070 | [+0.035,+0.106] | no | 5000 | 0 |
| T2 high | 298 | 0.869 | +0.114 | [+0.079,+0.152] | no | 5000 | 0 |

## D. Author contrast X2H-X2M (EXPLORATORY/POST-HOC)

Paired by passage (doc_id); the same resampled units weight both sets per resample (lib.paired_contrast scheme).

Common passages: 300 (sets identical: True).

Reproduction (seed 20261109, 10000 resamples): published +0.030 [-0.009,0.071]; recomputed +0.030 [-0.009,+0.071] (dH +0.053, dM +0.023, kept 10000, skipped 0); max|diff| vs filed metrics.json = 0 -> MATCH.

Cross-check paired_level vs lib.paired_contrast with zero baselines (same seed): max|diff| = 2.22e-16.

| contrast | dH | dM | H-M | 95% CI | zero_in | kept | skipped |
|----------|----|----|-----|---------|---------|------|---------|
| Dr hit | 0.647 | 0.553 | +0.093 | [+0.029,+0.156] | no | 5000 | 0 |
| Br hit | 0.627 | 0.563 | +0.063 | [+0.001,+0.127] | no | 5000 | 0 |
| MMr hit | 0.700 | 0.577 | +0.123 | [+0.057,+0.188] | no | 5000 | 0 |
| RRFr hit | 0.683 | 0.567 | +0.117 | [+0.050,+0.182] | no | 5000 | 0 |
| MMr-Dr gain hit (repro seed 20261109) | 0.053 | 0.023 | +0.030 | [-0.009,+0.071] | yes | 10000 | 0 |
| Dr mrr | 0.517 | 0.444 | +0.073 | [+0.015,+0.130] | no | 5000 | 0 |
| Br mrr | 0.538 | 0.451 | +0.087 | [+0.025,+0.152] | no | 5000 | 0 |
| MMr mrr | 0.593 | 0.504 | +0.088 | [+0.029,+0.147] | no | 5000 | 0 |
| RRFr mrr | 0.554 | 0.488 | +0.066 | [+0.007,+0.124] | no | 5000 | 0 |
| MMr-Dr gain mrr | 0.075 | 0.060 | +0.016 | [-0.018,+0.051] | yes | 5000 | 0 |

New-contrast bootstrap: seed 20261106, 5000 resamples.

## E. Stage 6 X3H-X3L (EXPLORATORY/POST-HOC)

Primary reproduction (seed 20261109, 10000 resamples): published +0.000 [-0.050,0.050]; recomputed +0.000 [-0.050,+0.050] (dH +0.033, dL +0.033, kept 10000, skipped 0); max|diff| vs filed = 0 -> MATCH.

MRR reproduction (same seed/resamples): published +0.123 [0.076,0.170]; recomputed +0.123 [+0.076,+0.170] (dH +0.125, dL +0.002, kept 10000, skipped 0); max|diff| vs filed = 0 -> MATCH.

Ceiling cells (X3H arm hit@10 rates; style-macro from section A):

| arm | s0 | s1 | s2 | micro | MACRO |
|-----|----|----|----|-------|-------|
| Dr | 0.960 | 0.950 | 0.960 | 0.957 | 0.957 |
| Br | 0.990 | 0.990 | 0.990 | 0.990 | 0.990 |
| MMr | 0.990 | 0.990 | 0.990 | 0.990 | 0.990 |
| RRFr | 0.980 | 0.990 | 0.990 | 0.987 | 0.987 |

## What each analysis can and cannot show

- A (sanity join) CAN show whether the query-id → source-ordinal join
  reproduces every filed style-macro cell; it does (40/40 MATCH), so
  the kill criterion is not triggered. It CANNOT validate the
  rankings themselves (they are taken as given).
- B (all pairwise diffs) CAN describe, per set, all six arm
  differences with cluster intervals; clusters equal queries within
  each set (one query per doc), so clustering changes nothing here
  versus a query bootstrap. It CANNOT select a winner (post-hoc,
  many comparisons, no decision rule).
- C (pooled overlap) CAN describe how the MMr−Dr hit gain varies
  with lint overlap across 897 queries while respecting the 300
  shared X2 passages (597 clusters); the clustered cut-0.45 interval
  (+0.087 [+0.051,+0.123]) is nearly identical to the published
  query-level interval (+0.087 [0.051,0.124]), so the shared-passage
  dependence barely moves this estimate. The tertile panel CAN show
  that Dr hit-rate rises with overlap (0.221 → 0.815 → 0.869), i.e.
  high-overlap queries are easier for the baseline too. It CANNOT
  establish overlap as the cause of the gain (post-hoc cut, pooled
  authors/sets, ceiling effects, no manipulation); it is not an
  equivalence test, and an interval including zero is not evidence
  of no difference.
- D (X2H−X2M paired) CAN describe per-arm level gaps on the same 300
  passages (every arm scores higher on X2H queries than X2M queries
  with intervals excluding zero) alongside the small MMr−Dr gain
  gap (+0.030 [−0.009,+0.071] hit, +0.016 mrr, both intervals
  including zero). It CANNOT separate author style from query
  easiness: pairing holds the passage fixed, not the query.
- E (X3H−X3L paired) CAN reproduce the published primary (+0.000
  [−0.050,+0.050]) and MRR contrast (+0.123 [+0.076,+0.170])
  exactly, and CAN exhibit the ceiling (X3H arm hit rates
  0.957–0.990), which compresses any hit-rate gap. It CANNOT test
  equivalence (not an equivalence test) and cannot explain the
  five-set pattern.

## Files (lease `/home/anshul/owner-hub/scratch/wave2/paired-reanalysis-v1`)

`RESULT.md` (this file: head + generated tables + tail),
`tables_gen.md` (generated tables), `results.json` (full precision),
`reanalyse.py` (analysis), `pure_paired.py` (stdlib overlap/stats
helpers), `test_paired.py` (hermetic tests), `test.log`,
`RESULT_head.md`, `RESULT_tail.md`.

Tests: `python3 -W error::ResourceWarning -m unittest` → 16 tests OK
(4 numpy-only tests skipped, stdlib interpreter);
venv python → 16 tests OK (0 skipped). See `test.log`.
Outbox copy: `/home/anshul/owner-hub/coord/outbox/paired-reanalysis-v1.result.md`.
