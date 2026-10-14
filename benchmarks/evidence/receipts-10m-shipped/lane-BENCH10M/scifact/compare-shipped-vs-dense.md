# Benchmark Comparison: run_20261008_183927_899309 vs run_20261008_183927_899309

- **Dataset**: beir-scifact (v1.0.0)
- **Comparison mode**: static
- **Execution Mode**: Current=`regression`, Baseline=`regression`
- **Cases**: 300
- **Current Date**: 2026-10-08T18:39:27.907910+00:00
- **Baseline Date**: 2026-10-08T18:39:27.907910+00:00

## Overall Metrics Comparison & Statistical Significance (Stable Query Pairing)

| Baseline | Metric | Baseline Run | Current Run | Delta | 95% CI | p-value | Significant (p<0.05)? |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | MAP@10 | 0.596 | 0.580 | -0.016 | [-0.057, 0.023] | 0.4308 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | P@5 | 0.164 | 0.149 | -0.015 | [-0.028, -0.003] | 0.0134 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Recall@5 | 0.738 | 0.679 | -0.059 | [-0.105, -0.013] | 0.0127 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Recall@20 | 0.837 | 0.765 | -0.073 | [-0.120, -0.030] | 0.0016 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | nDCG@10 | 0.645 | 0.617 | -0.028 | [-0.066, 0.009] | 0.1491 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Complete Coverage@10 | 0.773 | 0.703 | -0.070 | [-0.117, -0.023] | 0.0031 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | Returned relevance@5 | 0.164 | 0.149 | -0.015 | [-0.028, -0.003] | 0.0134 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `dense` | MRR | 0.611 | 0.594 | -0.017 | [-0.058, 0.024] | 0.4216 | No |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.