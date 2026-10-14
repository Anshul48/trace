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
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | MAP@10 | 0.580 | 0.580 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | P@5 | 0.149 | 0.149 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Recall@5 | 0.679 | 0.679 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Recall@20 | 0.765 | 0.765 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | nDCG@10 | 0.617 | 0.617 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Complete Coverage@10 | 0.703 | 0.703 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Returned relevance@5 | 0.149 | 0.149 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | MRR | 0.597 | 0.594 | -0.002 | [-0.003, -0.002] | 0.0000 | **YES** |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.