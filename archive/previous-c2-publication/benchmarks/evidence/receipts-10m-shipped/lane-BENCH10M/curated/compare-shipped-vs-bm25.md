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
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | MAP@10 | 0.585 | 0.555 | -0.029 | [-0.055, -0.007] | 0.0165 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | P@5 | 0.191 | 0.195 | +0.004 | [-0.004, 0.012] | 0.2741 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Recall@5 | 0.613 | 0.622 | +0.010 | [-0.008, 0.027] | 0.2922 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Recall@20 | 0.771 | 0.703 | -0.068 | [-0.095, -0.044] | 0.0000 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | nDCG@10 | 0.639 | 0.621 | -0.018 | [-0.037, -0.000] | 0.0565 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Complete Coverage@10 | 0.496 | 0.475 | -0.021 | [-0.039, -0.007] | 0.0140 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Returned relevance@5 | 0.191 | 0.195 | +0.004 | [-0.004, 0.012] | 0.2741 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | MRR | 0.747 | 0.722 | -0.025 | [-0.050, -0.001] | 0.0501 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `bm25` | Abstention Accuracy | 0.875 | 0.875 | 0.000 | [0.000, 0.000] | 1.0000 | No |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.