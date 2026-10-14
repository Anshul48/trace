# Benchmark Comparison: run_20261008_182558_693806 vs run_20261008_182558_693806

- **Dataset**: trace-technical-docs-dev (v1.0.0)
- **Comparison mode**: static
- **Execution Mode**: Current=`regression`, Baseline=`regression`
- **Cases**: 6
- **Current Date**: 2026-10-08T18:25:58.698636+00:00
- **Baseline Date**: 2026-10-08T18:25:58.698636+00:00

## Overall Metrics Comparison & Statistical Significance (Stable Query Pairing)

| Baseline | Metric | Baseline Run | Current Run | Delta | 95% CI | p-value | Significant (p<0.05)? |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | MAP@10 | 0.833 | 0.740 | -0.093 | [-0.297, 0.100] | 0.4721 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | P@5 | 0.320 | 0.320 | -0.000 | [-0.120, 0.120] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Recall@5 | 0.833 | 0.800 | -0.033 | [-0.300, 0.200] | 0.8149 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Recall@20 | 0.933 | 1.000 | +0.067 | [0.000, 0.200] | 0.3739 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | nDCG@10 | 0.903 | 0.851 | -0.052 | [-0.196, 0.088] | 0.5689 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Complete Coverage@10 | 0.800 | 1.000 | +0.200 | [0.000, 0.600] | 0.3739 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Returned relevance@5 | 0.500 | 0.320 | -0.180 | [-0.320, -0.040] | 0.0876 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | MRR | 1.000 | 0.900 | -0.100 | [-0.300, 0.000] | 0.3739 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Abstention Accuracy | 0.833 | 0.833 | 0.000 | [0.000, 0.000] | 1.0000 | No |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.