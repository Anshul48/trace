# Benchmark Comparison: run_20261008_192345_041319 vs run_20261008_192345_041319

- **Dataset**: beir-nfcorpus (v1.0.0)
- **Comparison mode**: static
- **Execution Mode**: Current=`regression`, Baseline=`regression`
- **Cases**: 323
- **Current Date**: 2026-10-08T19:23:45.053028+00:00
- **Baseline Date**: 2026-10-08T19:23:45.053028+00:00

## Overall Metrics Comparison & Statistical Significance (Stable Query Pairing)

| Baseline | Metric | Baseline Run | Current Run | Delta | 95% CI | p-value | Significant (p<0.05)? |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | MAP@10 | 0.106 | 0.106 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | P@5 | 0.280 | 0.280 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Recall@5 | 0.112 | 0.112 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Recall@20 | 0.170 | 0.170 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | nDCG@10 | 0.295 | 0.295 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Complete Coverage@10 | 0.037 | 0.037 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | Returned relevance@5 | 0.280 | 0.280 | 0.000 | [0.000, 0.000] | 1.0000 | No |
| `python:c2_bench10m:C2Bench10MShipped` vs `python:c2_bench10m:C2Bench10MK100` | MRR | 0.528 | 0.526 | -0.001 | [-0.002, -0.001] | 0.0001 | **YES** |

95% CIs: paired percentile bootstrap (2,000 samples, seed 42).
p-values: two-sided paired Student-t test; no multiple-comparison correction.
Retrieval rows use positive queries, including failures at zero. Abstention uses all queries.