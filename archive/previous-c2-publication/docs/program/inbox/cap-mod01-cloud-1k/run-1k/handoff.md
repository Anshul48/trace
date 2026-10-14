# WP-CAP-MOD01 Extension: DeepSeek Flash V4 0731 Bake-Off (Sail Research)

- **Node ID:** `CAP-MOD01-DEEPSEEK-FLASH`
- **Model:** `deepseek-ai/DeepSeek-V4-Flash-0731` via Sail Research API (`https://api.sailresearch.com/v1`)
- **Target Gate:** `CAP-GC`
- **Status:** `FAIL (<95% FLOOR)`

---

## 1. Executive Summary

DeepSeek Flash V4 0731 was evaluated across all **769 frozen atom clusters** from `clusters_1k_v1.json` using the **clarified grounding prompt with few-shot demonstration** and Sail Research high-throughput inference platform.

### Scorecard Comparison & Disentangled Metrics

| Metric | Extractive Control (Baseline) | DeepSeek Flash V4 0731 (Sail Research) | Gate Floor |
|---|---|---|---|
| **Overall Faithfulness (Fail-Closed)** | `0.9967` | **`0.6016`** | `>= 0.9500` |
| **95% Bootstrap CI** | `[0.9952, 0.9980]` | `[0.5681, 0.6351]` | — |
| **Validity Rate (Parseable JSON)** | `100.0%` | **`68.1%`** | `>= 95.0%` |
| **Grounding-Given-Valid** | `0.9967` | **`0.8829`** | `>= 0.9500` |
| **95% CI (Grounding-Given-Valid)** | `[0.9952, 0.9980]` | `[0.8584, 0.9058]` | — |
| **Warm Tokens / Sec (Throughput)** | `—` | **`56.8`** | `>= 15.0` |
| **P95 Latency** | `0.1 ms` | **`28430 ms`** | `<= 60,000 ms` |
| **Total Evaluation Spend** | `$0.0000` | **`$0.7922`** | `<= $25.00` |
