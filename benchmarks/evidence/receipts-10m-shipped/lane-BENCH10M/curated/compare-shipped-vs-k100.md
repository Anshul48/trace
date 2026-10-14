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
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | MAP@10 | 0.555 | 0.555 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | P@5 | 0.195 | 0.195 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Recall@5 | 0.622 | 0.622 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Recall@20 | 0.703 | 0.703 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | nDCG@10 | 0.621 | 0.621 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Complete Coverage@10 | 0.475 | 0.475 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Returned relevance@5 | 0.195 | 0.195 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | MRR | 0.722 | 0.722 | -0.000 | [-0.001, -0.000] | 0.0255 | **YES** |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Abstention Accuracy | 0.875 | 0.875 | 0.000 | [0.000, 0.000] | 1.0000 | No |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.