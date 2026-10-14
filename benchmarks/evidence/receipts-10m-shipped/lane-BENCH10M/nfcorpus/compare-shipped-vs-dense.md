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
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | MAP@10 | 0.110 | 0.106 | -0.005 | [-0.015, 0.006] | 0.3943 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | P@5 | 0.303 | 0.280 | -0.022 | [-0.045, -0.000] | 0.0453 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Recall@5 | 0.120 | 0.112 | -0.007 | [-0.022, 0.006] | 0.3021 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Recall@20 | 0.189 | 0.170 | -0.018 | [-0.035, -0.001] | 0.0377 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | nDCG@10 | 0.316 | 0.295 | -0.021 | [-0.040, -0.002] | 0.0283 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Complete Coverage@10 | 0.037 | 0.037 | 0.000 | [-0.015, 0.015] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Returned relevance@5 | 0.303 | 0.280 | -0.022 | [-0.045, -0.000] | 0.0453 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | MRR | 0.510 | 0.526 | +0.016 | [-0.016, 0.049] | 0.3235 | No |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.