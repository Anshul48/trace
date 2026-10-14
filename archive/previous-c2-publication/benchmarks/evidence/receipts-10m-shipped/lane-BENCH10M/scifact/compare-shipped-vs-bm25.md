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
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | MAP@10 | 0.621 | 0.580 | -0.041 | [-0.071, -0.012] | 0.0056 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | P@5 | 0.156 | 0.149 | -0.007 | [-0.016, 0.001] | 0.1087 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Recall@5 | 0.721 | 0.679 | -0.042 | [-0.082, -0.003] | 0.0379 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Recall@20 | 0.823 | 0.765 | -0.058 | [-0.092, -0.026] | 0.0005 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | nDCG@10 | 0.665 | 0.617 | -0.047 | [-0.075, -0.021] | 0.0007 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Complete Coverage@10 | 0.763 | 0.703 | -0.060 | [-0.097, -0.027] | 0.0006 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Returned relevance@5 | 0.156 | 0.149 | -0.007 | [-0.016, 0.001] | 0.1087 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | MRR | 0.638 | 0.594 | -0.044 | [-0.075, -0.015] | 0.0036 | **YES** |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.