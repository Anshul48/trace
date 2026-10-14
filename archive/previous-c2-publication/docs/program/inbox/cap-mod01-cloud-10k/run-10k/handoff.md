# WP-CAP-MOD01 10K Shard Consolidation: DeepSeek Flash V4 0731 (Sail Research)

- **Node ID:** `CAP-MOD01-DEEPSEEK-FLASH`
- **Model:** `deepseek-ai/DeepSeek-V4-Flash-0731` via Sail Research API (`https://api.sailresearch.com/v1`)
- **Target Gate:** `CAP-GD`
- **Status:** `RESULTS-COMPLETE (0.90 SNAPSHOT FLOOR CLEARED; PROMOTION RESERVED TO BALLOT)`

---

## 1. Executive Summary

DeepSeek Flash V4 0731 was evaluated across **2000 clusters** from the frozen 10K consolidation window (`clusters_10k_v1.json`) using **improved-grounding-fewshot-v2**, `max_tokens` floor 8192, think-metering, 10-worker concurrency, and local serial fallback queue.

### Scorecard Comparison & Disentangled Metrics

| Metric | Extractive Control (Baseline) | DeepSeek Flash V4 0731 (10K Window) | Target Floor |
|---|---|---|---|
| **Grounding-Given-Valid** | `0.9969` | **`0.9550`** `[0.9476, 0.9618]` | `>= 0.9000` (User Accepted) |
| **Overall Faithfulness (Fail-Closed)** | `0.9969` | **`0.7989`** `[0.7818, 0.8152]` | Sensitivity |
| **Validity Rate (% Strict Valid)** | `100.0%` | **`83.7%`** (1673/2000 valid) | `>= 80.0%` |
| **Warm Throughput (TPS)** | `2500.0` | **`55.2 tok/s`** | — |
| **P95 Cluster Latency** | `0 ms` | **`31297 ms`** | — |
| **P95 / P99 Reasoning Chars** | `0` | **`0 / 0 chars`** | Think Metered |
| **10K Evaluation Spend** | `$0.00` | **`$2.9613`** (Cum: `$4.2794`) | Cap: `$25.00` |
| **Verdict** | BASELINE | **RESULTS-COMPLETE** | — |

---

## 2. Serial Fallback & Think-Metering Analysis

- **Concurrency:** 10 workers
- **Fallback Queue / R1 Retries:** 286 clusters retried; 237 rescued (82.9% rescue rate).
- **Reasoning Meters:** Mean reasoning length: 0.0 chars (0.0 words). Max: 0 chars.
- **Finish Reasons:** {'stop': 1862, 'length': 4, 'unknown': 134}

---

## 3. Receipt Verification

Deterministic verification command:
```bash
python benchmarks/run_deepseek_flash_bakeoff.py --verify-receipt --out-dir docs/program/inbox/cap-mod01-cloud-10k/run-10k
```
Receipt written to `docs/program/inbox/cap-mod01-cloud-10k/run-10k/verification_receipt.json`.
