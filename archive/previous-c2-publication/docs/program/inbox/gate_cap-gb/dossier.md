# Decision Gate Dossier: Gate CAP-GB (Infrastructure, Contracts & Safety Baseline)

- **Gate ID:** `GATE-CAP-GB`
- **Program:** TRACE-CAP-001 (Trace Cognitive Architecture Correction Program)
- **Role:** Program Coordinator (COORD)
- **Status:** ACCEPTED (Human Gate CAP-GB Ballot Accepted 2026-09-04; clean, all amendments; DEC-CAP-GB)
- **Date (UTC):** 2026-09-04T02:36:00Z
- **Reference Repository:** `C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/`
- **Governing Directives:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§§4-5, §12), `docs/program/launch/CAP_001_WAVEB_DIRECTIVES.md` (Directives D1-D3).

---

## 1. Executive Summary

All 15 prerequisite work packets and verifications across Wave B convergence have been landed, independently verified under clean detached worktree protocols, and attested on disk:
- **Safety & Gateway Baseline:** `CAP-GW01`, `CAP-GW02`, `CAP-GW03` (Fail-closed gateway, pricing telemetry, zero unrecorded LLM calls).
- **Retrieval Engine & Baseline:** `CAP-RET01`, `CAP-RET02`, `CAP-RET03`, `CAP-RET04` (Dense neural embeddings, RRF k=60 bit-exact fusion, Personalized PageRank spreading activation with depth <= 15 and degree <= 50, frozen BEIR baseline clearing nDCG@10 floors on SciFact, NFCorpus, and FiQA with zero LLM calls).
- **Cortex Projections & Lifecycle:** `CAP-CRX01`, `CAP-CRX02`, `CAP-CRX03` (Pydantic schemas with byte-offset Spine anchors, consolidator with nonzero DeepSeek-V4 pricing, journaled pointer-swap activation surviving crashes).
- **Job Pipeline & Distributed Recovery:** `CAP-JOB01`, `CAP-JOB02` (Fail-closed release assembly, 300s lease heartbeat reclaim, 3-strike dead-letter queue, 5,000 backpressure ceiling, zero orphan jobs upon crash-after-consolidation with idempotent activation).
- **Evaluation Infrastructure & Validator:** `CAP-EVAL01`, `CAP-EVAL02`, `CAP-EVAL03` (Standardized protocols, frozen BEIR/MuSiQue datasets with D1 verified query counts 300/323/648, detached faithfulness validator with 100% adversarial rejection and Cohen's $\\kappa = 0.9195$).

Zero merges into `main` or `wave-b-candidate` have been executed; verify-first-merge-never discipline has been strictly upheld.

---

## 2. Master Wave B Receipt Matrix

| Node ID | Packet / Role | Candidate Commit | Tree Hash | Verdict | Key Evidence & Telemetry |
|---|---|---|---|---|---|
| **CAP-GW01** | Model Gateway Safety | `a9255b4` | - | **PASS** | Fail-closed routing, provider error quarantine, policy enforcement. |
| **CAP-GW02** | Pricing & Cost Telemetry | `a9255b4` | - | **PASS** | $0.00 cloud cost prohibited; DeepSeek pricing audited. |
| **CAP-GW03** | Gateway Audit & Mocking | `a9255b4` | - | **PASS** | Zero synthetic fallback leakage; audit logs complete. |
| **CAP-RET01** | Local Dense Embedder | `a9255b4` | - | **PASS** | 384-d normalized unit vectors, provider ID stability. |
| **CAP-RET02** | Dense + RRF Hybrid Fusion | `cd6dfc2` | `0e02502` | **PASS** | MiniLM re-pin (`1110a243`), RRF $k=60$ bit-exact, Windows native re-run 39/39 green (P95 10.0ms). |
| **CAP-RET03** | Graph PPR Spreading Activation | `5b719ca` | `bb5aa59` | **PASS** | PPR spreading activation, max degree $\\le 50$, walk depth $\\le 15$, $\\alpha=0.15$, P95 latency 0.44ms, empty-graph telemetry flag, 11/11 tests. |
| **CAP-RET04** | Frozen Retrieval Baseline | `5b719ca` | `bb5aa59` | **PASS** | SciFact nDCG@10: 0.6651 (floor 0.65), NFCorpus: 0.3524 (floor 0.32), FiQA: 0.4028 (floor 0.38); 10k bootstrap CIs clear floors; zero LLM calls. |
| **CAP-CRX01** | Cortex Schema & Anchors | `a9255b4` | - | **PASS** | Strict byte-offset Spine anchors, rejection of unanchored projections. |
| **CAP-CRX02** | Consolidator & Pricing | `2cfe313` | - | **PASS** | DeepSeek-V4 price telemetry audited; Option B byte-parity approved (`DEC-CAP-GB`). |
| **CAP-CRX03** | Pointer Swap Activation | `97caace` | - | **PASS_WITH_MERGE_RISK** | Predecessor restoration & zero dangling aliases; D3 serialization required. |
| **CAP-JOB01** | Pipeline Chaining | `a7737d6` | - | **PASS** | Missing/ambiguous validation receipt strictly rejected (no default pass). |
| **CAP-JOB02** | Job Recovery & Backpressure | `e9dec78` | - | **PASS_WITH_MERGE_RISK** | Crash-after-consolidation zero orphans, double-activation idempotent; D3 serialization required. |
| **CAP-EVAL01** | Evaluation Protocols | `8f6efe2` | - | **PASS** | Protocol schemas locked, seed stability verified. |
| **CAP-EVAL02** | Frozen Evaluation Datasets | `587aa51` | - | **PASS** | D1 counts verified (SciFact 300, NFCorpus 323, FiQA 648); MD5 cryptographic match 100%. |
| **CAP-EVAL03** | Detached Faithfulness Validator | `d00cd05` | `5faf880` | **PASS** | Detached NLI $\\tau = 0.95$, 100% rejection on frozen hallucinations (15/15), dual-adjudicated sample $N=210$ with Cohen's $\\kappa = 0.9195$, generator independent. |

---

## 3. Statistical Discipline & Benchmark Records

### 3.1 Frozen Retrieval Baseline (`CAP-RET04`)
- **Evaluation Command:** `python benchmarks/run_frozen_retrieval_baseline.py --verify-receipt`
- **Methodology Annex §3 Discipline:** 10,000 bootstrap resamples per dataset, seed 42.

| Dataset | Split | Queries | Observed nDCG@10 | Floor | 95% Bootstrap CI | CI Width | Pass Rule (Point $\\ge$ Floor, Lower CI $\\ge$ Floor - 0.02) |
|---|---|---|---|---|---|---|---|
| **SciFact** | `test` | 300 | **0.6651** | 0.65 | [0.6518, 0.6782] | 0.0264 | **PASS** |
| **NFCorpus** | `test` | 323 | **0.3524** | 0.32 | [0.3422, 0.3625] | 0.0203 ($\\le 0.10$) | **PASS** |
| **FiQA** | `test` | 648 | **0.4028** | 0.38 | [0.3941, 0.4116] | 0.0176 | **PASS** |

- **LLM Audit:** Exactly 0 LLM calls executed ($0.00 spend). Pure deterministic retrieval verified.

### 3.2 Detached Faithfulness Validator Calibration (`CAP-EVAL03`)
- **Adversarial Hallucination Rejection (Annex §4.1):**
  - Unsupported entity hallucinations: 5/5 rejected (0.0 entailment)
  - Invented numbers/quantities: 5/5 rejected (0.0 entailment)
  - Cross-atom false splices: 5/5 rejected (0.0 entailment)
  - Total rejection rate: **15 / 15 (100.0% rejection)**.
- **Dual-Adjudicated Proposition Sample (Annex §4.2):**
  - Sample size: $N = 210$ propositions ($N \\ge 200$ required)
  - Inter-annotator reliability: **Cohen's $\\kappa = 0.9195$** ($\\ge 0.70$ threshold cleared)
  - Exact match against `sklearn.metrics.cohen_kappa_score` verified.
  - Validator agreement with human consensus: $85.71\\%$.
- **Generator Independence (Annex §4.3):**
  - NLI Model: `cross-encoder/nli-deberta-v3-base`
  - Zero weight, revision, or training data overlap with generator under test.

### 3.3 Dataset Cryptographic Integrity (`CAP-EVAL02`)
- **Directive D1 Reconciliation:**
  - SciFact: 300 test queries (MD5: `5f7d1de60b170fc8027bb7898e2efca1`)
  - NFCorpus: 323 test queries (MD5: `a89dba18a62ef92f7d323ec890a0d38d`)
  - FiQA: 648 test queries (MD5: `17918ed23cd04fb15047f73e6c3bd9d9`)
  - MuSiQue: 500 stratified dev queries under seed 42
- Checksum audit: All 8 files matched SHA-256 digests 100%.

---

## 4. Negative-Test & Invariant Enforcement Ledger

1. **Fail-Closed Semantics:**
   - Empty/disconnected graphs return hybrid seed candidates with `graph_applied=False, empty_graph=True` telemetry.
   - Missing or ambiguous validation receipts in release assembly raise `InvariantViolation` (never default pass).
   - Empty summary, ungrounded propositions, or missing source atoms reject immediately with `support_ratio = 0.0, passed = False`.
2. **Zero Synthetic / Deterministic Fallback Leakage:**
   - Production neural embedder qualification requires `is_fallback=False, is_neural=True`.
3. **Cost Integrity:**
   - Zero-cost permitted only on local embedder / local model executions; cloud model calls strictly record price coefficients.
4. **Merge Order Invariant (Directive D3):**
   - `CAP-JOB02` and `CAP-CRX03` both touch `service.py` and `store.py` in non-overlapping regions.
   - `JOB02` merges first into `wave-b-candidate`; `CRX03` rebases onto the updated tip at merge time.

---

## 5. Residual Limitations & Human Decisions (Resolved via DEC-CAP-GB)

> **Status:** All 3 items below were formally resolved and APPROVED / RATIFIED by the Human Project Owner via `DEC-CAP-GB` on 2026-09-04 (see Section 7).

1. **CRX02 Parity Option B Approval:**
   - Extractive control text clipping uses U+2026 ellipsis suffix across implementations. Formally approved as canonical in the specification (no code change required).
2. **Methodology Amendments B1–B6 (Annex §6):**
   - **B1:** SciFact count rule ratified (test/300 queries, MD5 `5f7d1de60b170fc8027bb7898e2efca1`).
   - **B2:** Sub-clearances `GB-SAFE` and `GB-RET` formalization approved.
   - **B3:** Lease serialization standing order (`JOB02` before `CRX03`) approved.
   - **B4:** Monotonic storage profile (3.0x -> 2.5x) and component model mandate approved.
   - **B5:** Gate `CAP-GG` 0.01% sampling plan requirement approved.
   - **B6:** Two-regime latency rule adoption approved.
3. **Wave C Bake-Off Authorization:**
   - Local GPU compute for Model Specialist bake-off + max $5.00 cloud comparator budget for DeepSeek teacher authorized.

---

## 6. Verification Attestation

The Program Coordinator (COORD) certifies that all receipts cited in this dossier are authentic, cryptographically grounded, verified in isolated environments without cross-contamination, and conformant with Program Invariants.

Signed:
**Program Coordinator (COORD)**
Session: `91b2a988-c341-4052-b9c9-a89a1987eaa6`
Timestamp: `2026-09-04T02:36:00Z`

---

## 7. Human Gate CAP-GB Ballot & Final Disposition

- **Decision ID:** `DEC-CAP-GB` (recorded in `docs/program/06_DECISION_LOG.md`)
- **Ballot Verdict:** **ACCEPT (clean, all amendments)**
- **Decided by:** Human Project Owner
- **Date (UTC):** 2026-09-04
- **Authorizations Granted:**
  1. Wave B Baseline Accepted in full (15/15 nodes PASS with margin, zero LLM calls, zero synthetic fallbacks).
  2. Amendments Ratified: CRX02 Option B (U+2026 canonical), B1 (SciFact 300 count rule), B2 (`GB-SAFE` / `GB-RET` sub-clearances), B3 (Lease serialization: `JOB02` before `CRX03`), B4 (Monotonic storage profile $3.0\times \to 3.0\times \to 2.5\times$ + component lower-bound model), B5 (Gate `CAP-GG` 0.01% sampling plan), B6 (Two-regime latency rule).
  3. Wave C Authorized: Local GPU compute for Model Specialist bake-off (`CAP-MOD01`) + max $5.00 cloud budget for DeepSeek teacher comparator.
- **Wave C Status:** **UNLOCKED** (`CAP-MOD01` authorized to begin).

### Itemized Signed Ballot Disposition Table

| Item | Action / Recommendation | Ratified Rationale ("Why") |
|---|---|---|
| **1. Wave B baseline** | **Accept** | 15/15 nodes verified with margin: RET04 floors clear on point and lower CI bounds, EVAL03 κ=0.92, P95 latencies 20–95% under budget, zero LLM calls, zero synthetic fallbacks |
| **CRX02 Option B (U+2026 canonical)** | **Approve** | Already the observed base behavior; no code change, just spec honesty |
| **B1 SciFact 300** | **Ratify** | Already applied at EVAL02; ballot just formalizes it |
| **B2 sub-clearances** | **Approve** | Lets future partial passes (e.g. safety-only) proceed without re-litigating |
| **B3 lease serialization standing order** | **Approve** | D3 worked exactly as designed this wave |
| **B4 monotonic storage (3.0→2.5x)** | **Approve** | Demanding at 1M, but that's the point of a gate — and it binds now, before hardware is committed |
| **B5 GG sampling plan** | **Approve** | Required prerequisite for the unanchored-rate claim anyway |
| **B6 two-regime latency** | **Approve** | Directly encodes the RET02 lesson: perf bars belong to named hardware, not shared VMs |
| **3. GPU + $5 cloud for Wave C** | **Authorize** | Bounded, metered, and your model-choice DEC already covers the DeepSeek side |

> **Human Project Owner Directive:**
> *"No reason for ACCEPT-WITH-AMENDMENTS that I can see — every amendment was drafted for this exact moment, and carving any out just recreates the ambiguity it was written to remove."*

