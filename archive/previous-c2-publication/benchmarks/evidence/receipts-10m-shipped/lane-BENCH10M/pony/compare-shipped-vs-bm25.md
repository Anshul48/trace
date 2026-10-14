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
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | MAP@10 | 0.011 | 0.012 | +0.001 | [-0.005, 0.006] | 0.7755 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | P@5 | 0.050 | 0.062 | +0.013 | [-0.014, 0.039] | 0.3475 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Recall@5 | 0.014 | 0.017 | +0.003 | [-0.005, 0.011] | 0.4645 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Recall@20 | 0.064 | 0.066 | +0.002 | [-0.013, 0.016] | 0.7869 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | nDCG@10 | 0.055 | 0.064 | +0.009 | [-0.010, 0.028] | 0.3300 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Complete Coverage@10 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Returned relevance@5 | 0.050 | 0.062 | +0.013 | [-0.014, 0.039] | 0.3475 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | MRR | 0.123 | 0.174 | +0.052 | [0.000, 0.100] | 0.0501 | No |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.