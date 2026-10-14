# Benchmark Comparison: run_20261008_183840_882679 vs run_20261008_183840_882679

- **Dataset**: trace-engineering-curated (v1.0.0)
- **Comparison mode**: static
- **Execution Mode**: Current=`regression`, Baseline=`regression`
- **Cases**: 320
- **Current Date**: 2026-10-08T18:38:40.888068+00:00
- **Baseline Date**: 2026-10-08T18:38:40.888068+00:00

## Overall Metrics Comparison & Statistical Significance (Stable Query Pairing)

| Baseline | Metric | Baseline Run | Current Run | Delta | 95% CI | p-value | Significant (p<0.05)? |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | MAP@10 | 0.586 | 0.555 | -0.030 | [-0.070, 0.009] | 0.1291 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | P@5 | 0.211 | 0.195 | -0.016 | [-0.030, -0.004] | 0.0156 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Recall@5 | 0.647 | 0.622 | -0.025 | [-0.062, 0.013] | 0.1916 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Recall@20 | 0.798 | 0.703 | -0.095 | [-0.124, -0.064] | 0.0000 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | nDCG@10 | 0.651 | 0.621 | -0.030 | [-0.063, 0.001] | 0.0648 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Complete Coverage@10 | 0.621 | 0.475 | -0.146 | [-0.204, -0.089] | 0.0000 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Returned relevance@5 | 0.211 | 0.195 | -0.016 | [-0.030, -0.004] | 0.0156 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | MRR | 0.698 | 0.722 | +0.024 | [-0.007, 0.054] | 0.1208 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Abstention Accuracy | 0.875 | 0.875 | 0.000 | [0.000, 0.000] | 1.0000 | No |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.