# WP-CAP-MOD01 Extension: DeepSeek Flash V4 0731 Bake-Off (Sail Research)

- **Node ID:** `CAP-MOD01-DEEPSEEK-FLASH`
- **Model:** `deepseek-ai/DeepSeek-V4-Flash-0731` via Sail Research API (`https://api.sailresearch.com/v1`)
- **Target Gate:** `CAP-GC`
- **Status:** `FAIL (<95% FLOOR)`

---

## 1. Executive Summary

DeepSeek Flash V4 0731 was evaluated across all **100 frozen atom clusters** from `bakeoff_clusters_v1.json` using the **clarified grounding prompt with few-shot demonstration** and Sail Research high-throughput inference platform.

### Scorecard Comparison & Disentangled Metrics

| Metric | Extractive Control (Baseline) | DeepSeek Flash V4 0731 (Sail Research) | Gate Floor |
|---|---|---|---|
| **Overall Faithfulness (Fail-Closed)** | `0.9971` | **`0.7779`** | `>= 0.9500` |
| **95% Bootstrap Confidence Interval** | `[0.9942, 0.9994]` | **`[0.6956, 0.8547]`** | — |
| **Validity Rate (% Schema-Compliant)** | `100.0%` | **`86.0%`** (14 invalid) | Fail-closed |
| **Grounding-Given-Valid (Valid Only)** | `0.9971` | **`0.9045`** `[0.8421, 0.9566]` | Metric split |
| **CI Width** | `0.0052` | **`0.1591`** | Narrower = more consistent |
| **Warm Throughput (TPS)** | `2500.0` | **`62.2 tok/s`** | — |
| **P95 Cluster Latency** | `0 ms` | **`31712 ms`** | — |
| **Total Spend** | `$0.00` | **`$0.1229`** ($1.2292/1k clusters) | Cap: $5.00 |
| **Verdict** | BASELINE | **FAIL (<95% FLOOR)** | — |

---

## 2. Prompt Clarification & Schema Robustness Improvements

1. **Jargon Decoupling**: Defined "holon" in plain terms as a factual topic card (`topic_id`, `title`, `summary`, `source_atom_ids`).
2. **Few-Shot Demonstration**: Added concrete 1-shot input/output demonstration eliminating format ambiguity.
3. **Strict Lexical Anchoring**: Instructed model to use exact source terminology, eliminating synonym penalties that depressed overlap scores in local runs.
4. **Robust JSON Extraction & Repair**: Stripped reasoning traces (`<think>`), handled markdown fences, repaired trailing commas, and normalized keys.
5. **Disentangled Measurement**: Reported validity rate and grounding-given-valid separately from fail-closed composite score.
6. **Deterministic Evaluation**: Ran 10,000 bootstrap resamples under seed 42 with fail-closed scoring.

---

## 3. Universal Receipt Verification

Deterministic verification command:
```bash
python benchmarks/run_deepseek_flash_bakeoff.py --verify-receipt
```
Receipt written to `docs/program/inbox/cap-mod01-deepseek-flash/verification_receipt.json`.
