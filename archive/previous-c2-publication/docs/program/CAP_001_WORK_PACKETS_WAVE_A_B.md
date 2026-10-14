# TRACE-CAP-001 Work Packets: Wave A & Wave B

> **Document ID:** `TRACE-CAP-001-WP-AB`
> **Plan Reference:** [`COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`](COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md)
> **DAG Reference:** [`CAP_001_EXECUTION_DAG.md`](CAP_001_EXECUTION_DAG.md)
> **Status:** Prepared Work Packets ready for assignment.
> **Authority Boundary:** Each packet defines bounded scope, isolated worktree requirements, exact input/output artifacts, and acceptance criteria. No packet authorizes work outside its declared mutation boundary.

---

## Index of Packets

### Wave A (Governance Reconciliation)
- [`WP-CAP-A01`](#wp-cap-a01-human-owner-ratification-of-trace-cap-001): Ratification of `TRACE-CAP-001` (Human Owner)
- [`WP-CAP-A02`](#wp-cap-a02-canonical-document-amendment): Canonical Document Amendment & Contradiction Reconciliation
- [`WP-CAP-A03`](#wp-cap-a03-control-plane-relock): Control Plane Relock & Precedence Pointer Update

### Wave B (Infrastructure, Contracts & Safety Hardening)
- [`WP-CAP-GW01`](#wp-cap-gw01-gateway-fail-closed-hardening): Gateway Fail-Closed Hardening
- [`WP-CAP-GW02`](#wp-cap-gw02-model-registry-and-cost-telemetry): Model Registry & Non-Zero Cost Telemetry
- [`WP-CAP-GW03`](#wp-cap-gw03-budget-reservation-and-caps): Token Budget Reservation & Hard Spend Caps
- [`WP-CAP-RET01`](#wp-cap-ret01-dense-embedding-adapter-restoration): Dense Embedding Adapter Restoration
- [`WP-CAP-RET02`](#wp-cap-ret02-hybrid-rrf-fusion): Hybrid BM25 + Dense RRF Fusion
- [`WP-CAP-RET03`](#wp-cap-ret03-graph-walk-activation): Graph Walk Spreading Activation
- [`WP-CAP-RET04`](#wp-cap-ret04-frozen-retrieval-baseline-verification): Frozen Retrieval Baseline Verification (Gate `CAP-GB-RET`)
- [`WP-CAP-CRX01`](#wp-cap-crx01-cortex-schemas-and-lineage): Cortex Projections Schema & Evidence Anchors
- [`WP-CAP-CRX02`](#wp-cap-crx02-cortex-consolidator-engine): Consolidator Engine & Local SLM Adapter
- [`WP-CAP-CRX03`](#wp-cap-crx03-risk-tiered-activation): Risk-Tiered Projection Activation & Atomic Handover
- [`WP-CAP-JOB01`](#wp-cap-job01-async-pipeline-chaining): Ingestion-to-Consolidation Job Chaining
- [`WP-CAP-JOB02`](#wp-cap-job02-job-recovery-and-leases): Job Recovery, Heartbeats & Backpressure
- [`WP-CAP-EVAL01`](#wp-cap-eval01-semantic-evaluation-protocol): Semantic Evaluation Protocol & Scorecards
- [`WP-CAP-EVAL02`](#wp-cap-eval02-frozen-benchmark-datasets): Frozen Benchmark Datasets & Anchor Manifests
- [`WP-CAP-EVAL03`](#wp-cap-eval03-detached-faithfulness-validator): Detached Faithfulness & Entailment Verifier Suite

---

## Wave A Packets

### WP-CAP-A01: Human Owner Ratification of TRACE-CAP-001

- **Packet ID:** `WP-CAP-A01`
- **Assigned Role:** Human Project Owner
- **Worktree:** Main repository
- **Scope of Mutation:** Append entry `DEC-CAP-001` to `docs/program/06_DECISION_LOG.md`.
- **Inputs:** `docs/program/CAP_001_CONTRADICTION_LEDGER_AND_DECISION_REQUEST.md`.
- **Procedure:**
  1. Review Decision Request `DEC-CAP-001` and clauses `CAP-D001` through `CAP-D016`.
  2. Sign and append the decision record to `docs/program/06_DECISION_LOG.md`.
  3. Mark Status as **ACCEPTED**.
- **Deliverables:**
  - Appended `docs/program/06_DECISION_LOG.md` entry.
- **Verification Rule:** `python -c "assert 'DEC-CAP-001' in open('docs/program/06_DECISION_LOG.md', encoding='utf-8').read()"`

---

### WP-CAP-A02: Canonical Document Amendment

- **Packet ID:** `WP-CAP-A02`
- **Assigned Role:** Architecture Specialist (`ARCH-SPEC`)
- **Worktree:** Isolated branch `cap-a02-reconcile`
- **Scope of Mutation:**
  - `docs/program/00_CHARTER.md`
  - `docs/program/01_INVARIANTS.md`
  - `docs/program/02_EXECUTION_DAG.md`
  - `docs/program/03_SHARED_CONTRACTS.md`
  - `docs/program/04_EVALUATION_PROTOCOL.md`
  - `docs/program/05_PROMOTION_RUBRIC.md`
  - `docs/program/07_RISK_REGISTER.md`
  - `docs/program/SCALE_100K_TO_1M_EXECUTION_PLAN.md`
  - `docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md`
  - `docs/program/README.md`
- **Inputs:** `docs/program/CAP_001_CONTRADICTION_LEDGER_AND_DECISION_REQUEST.md` (Table 2: C-01 through C-13).
- **Procedure:**
  1. Patch each document to resolve the exact contradiction listed in the Contradiction Ledger.
  2. Add cross-references to `DEC-CAP-001` and `COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`.
  3. Verify all Markdown links and header formatting.
- **Deliverables:**
  - Clean patch applied across governing documents.
  - Handoff report in `docs/program/inbox/cap-a02/handoff.md`.
- **Verification Rule:** Independent audit by Codex Verifier proving zero remaining references to "G1M-HYBRID blocked until 1M Core pass" or "DeepSeek Flash mandatory baseline".

---

### WP-CAP-A03: Control Plane Relock

- **Packet ID:** `WP-CAP-A03`
- **Assigned Role:** Program Coordinator (`COORD`)
- **Worktree:** Main repository (or coordinator worktree)
- **Scope of Mutation:** `docs/program/CONTROL_PLANE_LOCK.json`, `docs/program/FOUNDATION_STATUS.md`.
- **Inputs:** Reconciled Git tree state from `WP-CAP-A02`.
- **Procedure:**
  1. Compute SHA-256 hashes of all files in `docs/program/`.
  2. Update `docs/program/CONTROL_PLANE_LOCK.json` with new hashes and link to `DEC-CAP-001`.
  3. Update `docs/program/FOUNDATION_STATUS.md` to reference `TRACE-CAP-001` as active.
- **Deliverables:**
  - Validated `CONTROL_PLANE_LOCK.json`.
- **Verification Rule:** `python -c "import json, hashlib, pathlib; lock = json.load(open('docs/program/CONTROL_PLANE_LOCK.json')); [assert hashlib.sha256(pathlib.Path('docs/program', p).read_bytes()).hexdigest() == h for p, h in lock['files'].items() if pathlib.Path('docs/program', p).exists()]"`

---

## Wave B Packets

### WP-CAP-GW01: Gateway Fail-Closed Hardening

- **Packet ID:** `WP-CAP-GW01`
- **Assigned Role:** Gateway Safety Specialist (`GW-SPEC`)
- **Worktree:** Isolated branch `cap-gw01-failclosed`
- **Scope of Mutation:** `src/trace/v2/model_gateway.py`, `tests/v2/test_model_gateway_failclosed.py`.
- **Objective:** Eliminate lines 578–610 where fake schemas/renderings are manufactured on empty/malformed responses. Raise explicit `ModelEmptyResponseError`, `ModelMalformedJsonError`, or `ModelUncitedOutputError`.
- **Deliverables:**
  - Hardened `model_gateway.py`.
  - Comprehensive unit test suite `test_model_gateway_failclosed.py`.
- **Verification Rule:** `pytest tests/v2/test_model_gateway_failclosed.py -v` must pass 100% of negative tests.

---

### WP-CAP-GW02: Model Registry & Cost Telemetry

- **Packet ID:** `WP-CAP-GW02`
- **Assigned Role:** Economics Specialist (`GW-ECON`)
- **Worktree:** Isolated branch `cap-gw02-cost`
- **Scope of Mutation:** `src/trace/v2/model_gateway.py`, `src/trace/v2/types.py`, `tests/v2/test_model_cost.py`.
- **Objective:** Fix line 130 cost coefficients. Populate accurate $/M token pricing for all models. Add `ModelInvocationReceipt` recording input tokens, output tokens, wall time, and USD cost. Ensure local models record $0.00 cost with `is_local=True`.
- **Deliverables:**
  - Pricing registry and telemetry receipts.
  - Test suite `test_model_cost.py`.
- **Verification Rule:** `pytest tests/v2/test_model_cost.py -v`

---

### WP-CAP-GW03: Budget Reservation & Hard Spend Caps

- **Packet ID:** `WP-CAP-GW03`
- **Assigned Role:** Economics Specialist (`GW-ECON`)
- **Worktree:** Isolated branch `cap-gw03-budget`
- **Scope of Mutation:** `src/trace/v2/model_gateway.py`, `tests/v2/test_budget_cap.py`.
- **Objective:** Implement preflight budget check (`reserve_budget`) and postflight settlement (`settle_budget`). Abort execution with `BudgetExceededError` if session cap is breached.
- **Deliverables:**
  - Budget cap engine.
  - Test suite `test_budget_cap.py`.
- **Verification Rule:** `pytest tests/v2/test_budget_cap.py -v`

---

### WP-CAP-RET01: Dense Embedding Adapter Restoration

- **Packet ID:** `WP-CAP-RET01`
- **Assigned Role:** Retrieval Specialist (`RET-SPEC`)
- **Worktree:** Isolated branch `cap-ret01-embedding`
- **Scope of Mutation:** `src/trace/v2/retrieval.py`, `src/trace/v2/adapters/embedding.py`, `tests/v2/test_retrieval_embedding.py`.
- **Objective:** Restore the local dense embedding adapter using `sentence-transformers/all-MiniLM-L6-v2`. Verify CUDA acceleration on RTX 5050 (or DirectML) with CPU fallback. Validate 384-dimensional vector output.
- **Deliverables:**
  - Functional `LocalEmbeddingAdapter`.
  - Unit tests verifying vector dimensions and throughput $> 1,000\text{ sentences/sec}$.
- **Verification Rule:** `pytest tests/v2/test_retrieval_embedding.py -v`

---

### WP-CAP-RET02: Hybrid BM25 + Dense RRF Fusion

- **Packet ID:** `WP-CAP-RET02`
- **Assigned Role:** Retrieval Specialist (`RET-SPEC`)
- **Worktree:** Isolated branch `cap-ret02-fusion`
- **Scope of Mutation:** `src/trace/v2/retrieval.py`, `tests/v2/test_hybrid_retrieval.py`.
- **Objective:** Remove `[:300]` truncation from postings lists. Implement Reciprocal Rank Fusion ($k=60$) combining BM25 lexical search and dense vector search into top-20 atom ranking.
- **Deliverables:**
  - `retrieve_hybrid()` function with P95 latency $\le 15\text{ ms}$.
  - Test suite verifying fusion behavior without truncation.
- **Verification Rule:** `pytest tests/v2/test_hybrid_retrieval.py -v`

---

### WP-CAP-RET03: Graph Walk Spreading Activation

- **Packet ID:** `WP-CAP-RET03`
- **Assigned Role:** Retrieval Specialist (`RET-SPEC`)
- **Worktree:** Isolated branch `cap-ret03-graph`
- **Scope of Mutation:** `src/trace/v2/retrieval.py`, `tests/v2/test_graph_retrieval.py`.
- **Objective:** Optimize Personalized PageRank (PPR) spreading activation over associative graph edges for multi-hop queries. Enforce max out-degree $\le 50$, walk depth $\le 15$, and latency $\le 10\text{ ms}$.
- **Deliverables:**
  - `retrieve_multihop()` function.
  - Test suite `test_graph_retrieval.py`.
- **Verification Rule:** `pytest tests/v2/test_graph_retrieval.py -v`

---

### WP-CAP-RET04: Frozen Retrieval Baseline Verification (Gate CAP-GB-RET)

- **Packet ID:** `WP-CAP-RET04`
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`) (Implementers barred)
- **Worktree:** Clean detached worktree
- **Scope of Mutation:** Read-only test execution. Output: `docs/program/inbox/cap-ret04/retrieval_baseline_dossier.json`.
- **Objective:** Run restored hybrid retrieval on SciFact, NFCorpus, and FiQA held-out splits. Verify nDCG@10 floors:
  - SciFact: $\ge 0.65$
  - NFCorpus: $\ge 0.32$
  - FiQA: $\ge 0.38$
  Confirm zero LLM calls were made during retrieval.
- **Deliverables:**
  - Signed `RetrievalBaselineReceipt`.
- **Verification Rule:** `python benchmarks/run_frozen_retrieval_baseline.py --verify-receipt`

---

### WP-CAP-CRX01: Cortex Projections Schema & Evidence Anchors

- **Packet ID:** `WP-CAP-CRX01`
- **Assigned Role:** Cortex Specialist (`CRX-SPEC`)
- **Worktree:** Isolated branch `cap-crx01-schema`
- **Scope of Mutation:** `src/trace/v2/cortex/`, `src/trace/v2/types.py`, `tests/v2/test_cortex_schemas.py`.
- **Objective:** Define typed schemas for `CortexProjection`, `TopicHolon`, `SectionSummary`, `EntityCandidate`, and `RelationCandidate`. Require explicit lineage: `source_atom_ids`, `model_id`, `prompt_hash`, `policy_id`. Enforce byte-offset anchor validation back to Spine.
- **Deliverables:**
  - Pydantic schema package in `src/trace/v2/cortex/`.
  - Test suite verifying rejection of unanchored projections.
- **Verification Rule:** `pytest tests/v2/test_cortex_schemas.py -v`

---

### WP-CAP-CRX02: Consolidator Engine Refactor & SLM Interface

- **Packet ID:** `WP-CAP-CRX02`
- **Assigned Role:** Cortex Specialist (`CRX-SPEC`)
- **Worktree:** Isolated branch `cap-crx02-consolidator`
- **Scope of Mutation:** `src/trace/v2/organization.py`, `src/trace/v2/cortex_consolidator.py`, `tests/v2/test_cortex_consolidator.py`.
- **Objective:** Refactor `organization.py` into `CortexConsolidator`. Preserve deterministic string clipping as `mode="extractive_control"`. Implement `mode="semantic_slm"` interfacing with `TraceModelGateway` to produce structured holons.
- **Deliverables:**
  - `CortexConsolidator` class.
  - Test suite verifying exact backward compatibility for extractive control and mock-model semantic generation.
- **Verification Rule:** `pytest tests/v2/test_cortex_consolidator.py -v`

---

### WP-CAP-CRX03: Risk-Tiered Projection Activation & Atomic Handover

- **Packet ID:** `WP-CAP-CRX03`
- **Assigned Role:** Cortex Specialist (`CRX-SPEC`)
- **Worktree:** Isolated branch `cap-crx03-activation`
- **Scope of Mutation:** `src/trace/v2/service.py`, `src/trace/v2/store.py`, `tests/v2/test_cortex_activation.py`.
- **Objective:** Implement risk-tiered activation:
  - Tier 1 (Navigation Summaries): auto-activates after detached validation passes.
  - Tier 2/3 (Factual claims, schema proposals): staged as `cortex_proposals` requiring explicit review.
  Implement atomic journaled pointer swaps across SQLite/Postgres and external aliases.
- **Deliverables:**
  - `activate_projection()` method with rollback on crash.
  - Crash-injection test suite `test_cortex_activation.py`.
- **Verification Rule:** `pytest tests/v2/test_cortex_activation.py -v`

---

### WP-CAP-JOB01: Ingestion-to-Consolidation Asynchronous Pipeline Chaining

- **Packet ID:** `WP-CAP-JOB01`
- **Assigned Role:** Infrastructure Specialist (`INFRA-SPEC`)
- **Worktree:** Isolated branch `cap-job01-pipeline`
- **Scope of Mutation:** `src/trace/v2/service.py`, `tests/v2/test_job_pipeline.py`.
- **Objective:** Modify service lifecycle so indexing completion automatically enqueues consolidation: `index-ready -> candidate consolidation -> validation -> release assembly -> activation`. Keep raw ingestion fast and non-blocking.
- **Deliverables:**
  - Chained background job pipeline in `service.py`.
  - Integration tests verifying non-blocking ingestion.
- **Verification Rule:** `pytest tests/v2/test_job_pipeline.py -v`

---

### WP-CAP-JOB02: Job Recovery, Heartbeats & Backpressure

- **Packet ID:** `WP-CAP-JOB02`
- **Assigned Role:** Infrastructure Specialist (`INFRA-SPEC`)
- **Worktree:** Isolated branch `cap-job02-recovery`
- **Scope of Mutation:** `src/trace/v2/service.py`, `src/trace/v2/store.py`, `tests/v2/test_job_recovery.py`.
- **Objective:** Implement worker heartbeat monitoring, 300s lease expiry, retry limit (3 retries before dead-letter queue), and queue depth backpressure cap (5,000 pending items).
- **Deliverables:**
  - Robust job supervisor.
  - Crash and restart recovery test suite.
- **Verification Rule:** `pytest tests/v2/test_job_recovery.py -v`

---

### WP-CAP-EVAL01: Semantic Evaluation Protocol & Scorecards

- **Packet ID:** `WP-CAP-EVAL01`
- **Assigned Role:** Evaluation Specialist (`EVAL-SPEC`)
- **Worktree:** Isolated branch `cap-eval01-protocol`
- **Scope of Mutation:** `docs/program/04_EVALUATION_PROTOCOL.md`, `benchmarks/protocols/`.
- **Objective:** Document and specify the multi-resolution evaluation protocols: Structural Coverage, Semantic Quality (Proposition Support $\ge 95\%$, Coherence $\ge 0.85$), Direct IR, Multi-hop Reasoning, and Synthesis Grounding.
- **Deliverables:**
  - Amended `04_EVALUATION_PROTOCOL.md`.
- **Verification Rule:** Markdown link check and protocol verification script.

---

### WP-CAP-EVAL02: Frozen Benchmark Datasets & Anchor Manifests

- **Packet ID:** `WP-CAP-EVAL02`
- **Assigned Role:** Evaluation Specialist (`EVAL-SPEC`)
- **Worktree:** Isolated branch `cap-eval02-data`
- **Scope of Mutation:** `benchmarks/manifests/`, `docs/program/inbox/cap-eval02/`.
- **Objective:** Pin and hash test splits for SciFact, NFCorpus, FiQA, and MuSiQue. Produce `beir_musique_frozen_v1.json` with cryptographic SHA-256 hashes for all queries and corpus files.
- **Deliverables:**
  - Checksum manifest file.
- **Verification Rule:** `python benchmarks/verify_dataset_checksums.py --manifest benchmarks/manifests/beir_musique_frozen_v1.json`

---

### WP-CAP-EVAL03: Detached Faithfulness & Entailment Verifier Suite

- **Packet ID:** `WP-CAP-EVAL03`
- **Assigned Role:** Evaluation Specialist (`EVAL-SPEC`)
- **Worktree:** Isolated branch `cap-eval03-faithfulness`
- **Scope of Mutation:** `benchmarks/evaluators/faithfulness_validator.py`, `tests/evaluators/test_faithfulness.py`.
- **Objective:** Build detached validator testing proposition support ($\ge 95\%$) against source atoms. Reject summaries containing unsupported/hallucinated assertions.
- **Deliverables:**
  - Detached validator package.
  - Unit test suite demonstrating negative validation on manufactured hallucinations.
- **Verification Rule:** `pytest tests/evaluators/test_faithfulness.py -v`
