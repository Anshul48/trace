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
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | MAP@10 | 0.012 | 0.012 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | P@5 | 0.062 | 0.062 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Recall@5 | 0.017 | 0.017 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Recall@20 | 0.066 | 0.066 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | nDCG@10 | 0.064 | 0.064 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Complete Coverage@10 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Returned relevance@5 | 0.062 | 0.062 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | MRR | 0.176 | 0.174 | -0.001 | [-0.002, -0.000] | 0.0086 | **YES** |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.