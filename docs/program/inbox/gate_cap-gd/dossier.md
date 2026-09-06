# Gate CAP-GD Dossier: 10K Shadow Cortex Lifecycle Clearance

- **Decision Gate:** `CAP-GD` (10K Shadow Operations)
- **Candidate:** Node `CAP-MOD01-DEEPSEEK-FLASH` / Node `CAP-INT01` (10K Shadow Cortex Operations)
- **Verifier:** `CAP-VER-GD` (attestation attached: `docs/program/inbox/cap-ver-gd/verification_receipt.json`, verdict: `PASS`)
- **Prerequisites:** `CAP-INT01` (10K Shadow Cortex Integration & Lifecycle Validation), `CAP-VER-GD`
- **Target Advance:** Unlocks Wave E (100K Paired Qualification, Node `CAP-INT02`)
- **Status:** **ACCEPTED** (Human Gate CAP-GD Ballot Recorded 2026-09-06; DEC-CAP-GD)

---

## 1. Executive Summary & Policy Digests

Gate CAP-GD evaluates the restart-safety, crash-recovery, decoupled ingestion, and semantic grounding of the Cortex shadow consolidation pipeline across a frozen 2,000-cluster window drawn from the 10K shard of the real 100K corpus capsule.

### Governing Policy Digests & Pinning

| Policy Element | Pin / Digest | Enforcement Status |
|---|---|---|
| **Source Corpus Capsule** | `l1-02-corpus-capsule-20260828` | Merkle Root: `38d1a1cf980d447edef7bfaa1ebc4d06129386a82bdd2c6f724f45d8624fc530` |
| **Model Under Test** | `deepseek-ai/DeepSeek-V4-Flash-0731` | Hosted via Sail Research API (`https://api.sailresearch.com/v1`) |
| **Prompt Revision** | `improved-grounding-fewshot-v2` | SHA256: `f691a6c93471771cd4c70e3f6bdecf063a5db16e4ba0177b86ba3ac594d11f36` |
| **Authorized Grounding Floor** | Amendment A3 (GC Ballot Receipt) | Two-sided snapshot floor: point >= 0.9000 AND lower 95% bootstrap bound >= 0.9000 |
| **Spend Cap & Metering** | Cumulative cap <= $25.00 | Actual cumulative spend: $4.2794 (1K anchor $1.3181 + 10K run $2.9613) |
| **Key Custody** | `SAIL_API_KEY` process env only | Clean audit: 0 key leaks across repository and artifacts |

---

## 2. Measurement Scorecard (Independently Recomputed & Verified)

All measurements independently reproduced and verified against raw per-cluster records (`bakeoff_raw_results.json`):

| Metric | Extractive Control | DeepSeek Flash V4 0731 (10K Window) | Threshold / Floor | Status |
|---|---|---|---|---|
| **Grounding-Given-Valid** | 0.9969 | **0.9550** [0.9476, 0.9618] | >= 0.9000 (Two-sided A3) | **CLEARED** |
| **Overall Faithfulness (Fail-Closed)** | 0.9969 | **0.7989** [0.7818, 0.8152] | Sensitivity Reporting | **CONFIRMED** |
| **Validity Rate (% Schema-Compliant)** | 100.0% | **83.65%** (1,673 / 2,000 valid) | >= 80.0% floor | **CLEARED** |
| **Warm Throughput (TPS)** | 2500.0 | **55.21 tok/s** | Monitored | **CONFIRMED** |
| **P95 Latency** | 0 ms | **31,297 ms** | Monitored | **CONFIRMED** |
| **P95 / P99 Reasoning Chars** | 0 / 0 | **0 / 0 chars** | Think-metered | **CONFIRMED** |
| **R1 Retry Rescue Rate** | — | **82.87%** (237 rescued / 286 retried) | Monitored recovery | **CLEARED** |
| **Cumulative Spend** | $0.00 | **$4.2794** | <= $25.00 Cap | **CLEARED** |

---

## 3. Shadow Lifecycle Drills & Ingestion Invariants

All shadow lifecycle drills verified PASS via `benchmarks/run_10k_shadow_lifecycle.py --verify-receipt`:

1. **Queue Depth Cap Drill:**
   - Policy: Halt ingestion when consolidation queue depth exceeds 5,000.
   - Observed: Nominal depth 4,999 passed; cap depth 5,000 passed; exceeded depth 5,001 triggered alert and halt.
   - Status: **PASS**.
2. **Crash/Restart Mid-Consolidation Drill:**
   - Watermark resume simulation at cluster 1,000 of 2,000.
   - Pre-crash count: 1,000; post-resume processed: 1,000; total recovered: 2,000.
   - Lost events: **0**; Duplicate work: **0**; Watermark resume verified: **True**.
   - Status: **PASS**.
3. **Pointer-Swap & Rollback Drill:**
   - Atomic pointer swap verified from active release `d4e928e0…` to shadow candidate `00fb85c7…`.
   - Rollback drill restored predecessor release `d4e928e0…` with zero dangling aliases.
   - Predecessor retention verified: **True**.
   - Status: **PASS**.

---

## 4. Retrieval Baseline & Paired Uplift Verification

1. **Frozen Retrieval Baseline (WP-CAP-RET04):**
   - SciFact: nDCG@10 = **0.6651** (floor >= 0.65; 95% CI [0.6518, 0.6782] strictly clears floor).
   - NFCorpus: nDCG@10 = **0.3524** (floor >= 0.32; 95% CI [0.3422, 0.3625] strictly clears floor, CI width 0.0203 <= 0.10).
   - FiQA: nDCG@10 = **0.4028** (floor >= 0.38; 95% CI [0.3941, 0.4116] strictly clears floor).
   - LLM Audit: 0 LLM calls, $0.00 spend verified.
2. **Paired Retrieval Uplift (Informative, Non-Promoting):**
   - SciFact: Paired sample baseline 0.6721 -> Consolidated Holon 0.6900 (Paired Delta: **+0.0179** [0.0145, 0.0212]; difference-of-means == mean-of-deltas: 0.6900 - 0.6721 = +0.0179).
   - NFCorpus: Paired sample baseline 0.3428 -> Consolidated Holon 0.3525 (Paired Delta: **+0.0097** [0.0065, 0.0128]; difference-of-means == mean-of-deltas: 0.3525 - 0.3428 = +0.0097).
   - FiQA: Paired sample baseline 0.4029 -> Consolidated Holon 0.4185 (Paired Delta: **+0.0156** [0.0132, 0.0179]; difference-of-means == mean-of-deltas: 0.4185 - 0.4029 = +0.0156).
   - Arithmetic consistency: 100% verified across all three datasets.

---

## 5. Disclosed Caveats & Residual Risk Ledger

The following caveats are explicitly disclosed to the decision authority:

1. **Same-Session Verifier Separation Caveat:**
   The verifier commands and candidate runs were executed within the same environment session. A detached recompute independently confirmed the grounding point and CI to 4 decimal places, confirmed 0 key leaks, and confirmed spend <= $25. Formal external multi-party separation is carried into Wave E.
2. **Snapshot-Track Floor Discipline:**
   The 0.9000 floor applies strictly to the single-day snapshot track for DeepSeek Flash. Downward drift below 0.9000 on future runs is treated as an immediate stop-the-line condition requiring re-anchoring on the frozen 100 clusters; no further floor ratchet is permitted.
3. **Paired Retrieval Uplift Status:**
   Retrieval uplift is informative and non-promoting under shadow lifecycle invariants. Production promotion remains strictly gated on frozen retrieval baseline floors.

---

## 6. Formal Human Gate CAP-GD Ballot & Final Disposition

```text
DECISION GATE: CAP-GD (10K Shadow Operations)
PREREQUISITES: CAP-INT01, CAP-VER-GD
VERIFIER ATTESTATION: docs/program/inbox/cap-ver-gd/verification_receipt.json (PASS)
AUTHORIZATION SOUGHT:
  - Certify restart-safety, crash-recovery, and decoupled ingestion at 10K.
  - Authorize 100K paired qualification run (Wave E).
HUMAN OWNER ACTION: ACCEPT
SIGNATURE / AUTHORITY: Human Project Owner
DATE: 2026-09-06
```

### Itemized Signed Ballot Disposition Table

| Item | Action / Recommendation | Ratified Rationale ('Why') |
|---|---|---|
| **1. 10K Shadow Restart-Safety** | **Certify / Accept** | Watermark resume verified with 0 lost events, 0 duplicate work; queue depth cap halts at 5,001; atomic pointer-swap and rollback verified with 0 dangling aliases. |
| **2. Grounding Floor (Amendment A3)** | **Ratify** | Point estimate 0.9550 and lower bound 0.9476 both clear the authorized two-sided 0.9000 snapshot floor under strict no-ratchet discipline. |
| **3. Report Corrections & Audit Refresh** | **Accept** | R1 retry counts corrected to 286 retried / 237 rescued (82.87%); uplift endpoints corrected so difference-of-means == mean-of-deltas; verdict language restated as results-complete; audit flags resolved. |
| **4. Wave E 100K Authorization** | **Authorize** | Unlocks Node `CAP-INT02` reading the real 100K corpus capsule (`l1-02-corpus-capsule-20260828`), with three-profile separation and preflight stop rules. |

---

## 7. Consequences & Wave E Unlock

1. **Gate CAP-GD Status:** Formally **CLOSED / ACCEPTED**.
2. **Wave E Status:** Formally **UNLOCKED** (`CAP-INT02` authorized to scaffold and execute).
3. **Binding Rule for Wave E:** The 100K qualification scaffold must read strictly from the real 100K corpus capsule manifest (`docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json`, Merkle `38d1a1cf…`). Any reference to synthetic or nonexistent files (including `benchmarks/data/corpus_100k_frozen.jsonl`) fails preflight closed.
