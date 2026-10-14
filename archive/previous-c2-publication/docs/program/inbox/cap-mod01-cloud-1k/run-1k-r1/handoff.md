# WP-CAP-MOD01 Extension: DeepSeek Flash V4 0731 Bake-Off (Sail Research)

- **Node ID:** `CAP-MOD01-DEEPSEEK-FLASH`
- **Model:** `deepseek-ai/DeepSeek-V4-Flash-0731` via Sail Research API (`https://api.sailresearch.com/v1`)
- **Target Gate:** `CAP-GC`
- **Status:** `FAIL (<95% FLOOR)`

---

## 1. Executive Summary

DeepSeek Flash V4 0731 was evaluated across all **286 frozen atom clusters** from `clusters_1k_r1.json` using the **clarified grounding prompt with few-shot demonstration**, Metric Amendment M2, and R1 Retry Protocol via Sail Research.

### Scorecard Comparison & Disentangled Metrics

| Metric | Extractive Control (Baseline) | DeepSeek Flash V4 0731 (Sail Research) | Gate Floor |
|---|---|---|---|
| **Overall Faithfulness (Fail-Closed)** | `0.9983` | **`0.7918`** | `>= 0.9500` |
| **95% Bootstrap Confidence Interval** | `[0.9963, 0.9997]` | **`[0.7465, 0.8356]`** | — |
| **Validity Rate (% Schema-Compliant)** | `100.0%` | **`82.9%`** (49 invalid) | Fail-closed |
| **Grounding-Given-Valid (Valid Only)** | `0.9983` | **`0.9555`** `[0.9342, 0.9729]` | Metric split |
| **CI Width** | `0.0033` | **`0.0890`** | Narrower = more consistent |
| **Warm Throughput (TPS)** | `2500.0` | **`62.0 tok/s`** | — |
| **P95 Cluster Latency** | `0 ms` | **`36923 ms`** | — |
| **Total Spend** | `$0.00` | **`$0.4030`** ($1.4090/1k clusters) | Cap: $25.00 |
| **Verdict** | BASELINE | **FAIL (<95% FLOOR)** | — |

---

## 2. R1 Protocol & Rescue Analysis

### Rescue Rate by Prior Failure Class
- **R1a (Truncated >=2048):** 34 / 34 (100.0%)
- **R1b (Empty / 0 props):** 106 / 136 (77.9%)
- **R1c (Unparseable JSON):** 97 / 116 (83.6%)
- **Overall Rescued:** 237 / 286 (82.9%)

---

## 3. Universal Receipt Verification

Deterministic verification command:
```bash
python benchmarks/run_deepseek_flash_bakeoff.py --verify-receipt --out-dir docs/program/inbox/cap-mod01-cloud-1k/run-1k-r1
```
Receipt written to `docs/program/inbox/cap-mod01-cloud-1k/run-1k-r1/verification_receipt.json`.
