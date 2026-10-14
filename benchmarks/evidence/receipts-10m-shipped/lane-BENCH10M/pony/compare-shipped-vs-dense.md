# Benchmark Comparison: run_20261009_012143_577818 vs run_20261009_012143_577818

- **Dataset**: bright-pony (v1.0.0)
- **Comparison mode**: static
- **Execution Mode**: Current=`regression`, Baseline=`regression`
- **Cases**: 112
- **Current Date**: 2026-10-09T01:21:43.586331+00:00
- **Baseline Date**: 2026-10-09T01:21:43.586331+00:00

## Overall Metrics Comparison & Statistical Significance (Stable Query Pairing)

| Baseline | Metric | Baseline Run | Current Run | Delta | 95% CI | p-value | Significant (p<0.05)? |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | MAP@10 | 0.006 | 0.012 | +0.006 | [0.000, 0.012] | 0.0499 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | P@5 | 0.036 | 0.062 | +0.027 | [-0.004, 0.055] | 0.0625 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Recall@5 | 0.009 | 0.017 | +0.008 | [-0.001, 0.017] | 0.0736 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Recall@20 | 0.034 | 0.066 | +0.032 | [0.015, 0.048] | 0.0002 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | nDCG@10 | 0.033 | 0.064 | +0.031 | [0.009, 0.053] | 0.0055 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Complete Coverage@10 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Returned relevance@5 | 0.036 | 0.062 | +0.027 | [-0.004, 0.055] | 0.0625 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | MRR | 0.108 | 0.174 | +0.066 | [0.005, 0.125] | 0.0357 | **YES** |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.