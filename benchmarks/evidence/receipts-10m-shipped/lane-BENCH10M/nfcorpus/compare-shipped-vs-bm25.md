# Benchmark Comparison: run_20261008_192345_041319 vs run_20261008_192345_041319

- **Dataset**: beir-nfcorpus (v1.0.0)
- **Comparison mode**: static
- **Execution Mode**: Current=`regression`, Baseline=`regression`
- **Cases**: 323
- **Current Date**: 2026-10-08T19:23:45.053028+00:00
- **Baseline Date**: 2026-10-08T19:23:45.053028+00:00

## Overall Metrics Comparison & Statistical Significance (Stable Query Pairing)

| Baseline | Metric | Baseline Run | Current Run | Delta | 95% CI | p-value | Significant (p<0.05)? |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | MAP@10 | 0.120 | 0.106 | -0.014 | [-0.028, -0.002] | 0.0299 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | P@5 | 0.281 | 0.280 | -0.001 | [-0.018, 0.017] | 0.9439 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Recall@5 | 0.120 | 0.112 | -0.008 | [-0.022, 0.004] | 0.2164 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Recall@20 | 0.177 | 0.170 | -0.006 | [-0.023, 0.010] | 0.4867 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | nDCG@10 | 0.310 | 0.295 | -0.015 | [-0.032, 0.001] | 0.0778 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Complete Coverage@10 | 0.046 | 0.037 | -0.009 | [-0.025, 0.006] | 0.2575 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Returned relevance@5 | 0.326 | 0.280 | -0.045 | [-0.071, -0.021] | 0.0005 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | MRR | 0.521 | 0.526 | +0.005 | [-0.021, 0.033] | 0.7021 | No |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.