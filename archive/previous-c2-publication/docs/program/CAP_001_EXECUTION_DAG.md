# TRACE-CAP-001 Exhaustive Execution DAG

> **Document ID:** `TRACE-CAP-001-DAG`
> **Plan Reference:** [`COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`](COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md)
> **Status:** Proposed Execution DAG. Governed by Decision `DEC-CAP-001`.
> **Observed Base Commit:** `33c80651f2fd05ffef0b1b6a491f0d860dbb8179`
> **Authority Boundary:** This DAG specifies dependency order, input/output schemas, budgets, and verification boundaries. Nodes are eligible for dispatch only after their prerequisites and required Human Decisions are recorded.

---

## 1. Execution Topology & Lane Separation

```text
========================================================================================================================
                                         TRACE-CAP-001 EXECUTION TOPOLOGY
========================================================================================================================

   [LANE 1: GOVERNANCE]      [LANE 2: RETRIEVAL]      [LANE 3: CORTEX]         [LANE 4: SYNTHESIS]      [LANE 5: EVAL/VERIF]
   ────────────────────      ───────────────────      ────────────────         ───────────────────      ────────────────────
   CAP-A01 (Ratify)
          │
          ▼
   CAP-A02 (Docs Reconcile)
          │
          ▼
   CAP-A03 (Relock) ─────────────────────────────────────────────────────────────────────────────► CAP-VER-GA (Gate CAP-GA)
          │                                                                                                    │
          ├──────────────────────────┬────────────────────────┬─────────────────────────┐                      ▼
          ▼                          ▼                        ▼                         ▼               HUMAN GATE CAP-GA
   CAP-GW01 (Gateway)         CAP-RET01 (MiniLM)       CAP-CRX01 (Schemas)       CAP-EVAL01 (Protocol)         │
   CAP-GW02 (Cost Telemetry)  CAP-RET02 (RRF Fusion)   CAP-CRX02 (Consolidator)  CAP-EVAL02 (Datasets)         │
   CAP-GW03 (Budget Cap)      CAP-RET03 (Graph Walk)   CAP-CRX03 (Activation)    CAP-EVAL03 (Faithfulness)     │
          │                          │                        │                         │                      │
          └──────────────────────────┼────────────────────────┼─────────────────────────┴───────────────► CAP-VER-GB
                                     │                        │                                                │
                                     │                        │                                                ▼
                                     │                        ▼                                         HUMAN GATE CAP-GB
                                     │                 CAP-JOB01 (Pipeline)                                    │
                                     │                 CAP-JOB02 (Recovery)                                    │
                                     │                        │                                                │
                                     │                        ▼                                                │
                                     │                 CAP-MOD01 (Bake-Off)                                    │
                                     │                 CAP-MOD02 (Selection) ───────────────────────────► CAP-VER-GC
                                     │                        │                                                │
                                     │                        ▼                                                ▼
                                     │                 CAP-INT01 (10K Shadow) ──────────────────────────► CAP-VER-GD
                                     │                        │                                                │
                                     │                        ▼                                                ▼
                                     └───────────────► CAP-INT02 (100K Paired) ─► CAP-INT03 (Synthesis) ─► CAP-VER-GE
                                                              │                                                │
                                                              ├─────────────────────────┐                      ▼
                                                              ▼                         ▼               HUMAN GATE CAP-GE
                                                       CAP-SCALE01 (1M Core)     CAP-SCALE02 (1M Cortex)       │
                                                              │                         │                      │
                                                              ▼                         ▼                      ▼
                                                       CAP-VER-GF                CAP-VER-GG             HUMAN PROMOTION
                                                       (Gate CAP-GF)             (Gate CAP-GG)          (Combined Release)
========================================================================================================================
```

---

## 2. Global Execution Rules & Authority Boundaries

1. **Acyclic Invariant:** The DAG is strictly a Directed Acyclic Graph. Research loops create new numbered wave revisions; completed nodes never accept back-mutations.
2. **Implementer-Verifier Segregation:** No agent or session that authored a candidate may verify, audit, or certify that candidate. Independent verifiers must run from clean, detached worktrees against frozen receipts.
3. **Readiness $\ne$ Authority:** Completing a prerequisite renders a downstream task *eligible* for authorization. Scale runs ($\ge 10\text{K}$ documents), cloud provider spending, model downloads, and release activations require an explicit Human Decision node.
4. **Lane Independence:** CORE, RETRIEVAL, CORTEX, and SYNTHESIS produce separate component dossiers and claims. A Cortex improvement cannot excuse a Core storage/durability failure; a Core qualification cannot claim semantic self-organization.
5. **Fail-Closed Principle:** Any missing checksum, empty model generation, unverified citation, unrecorded cost, or failed validation assertion halts the pipeline with an auditable error receipt. Manufacturing synthetic outputs is prohibited.

---

## 3. Exhaustive Node Specifications

### Wave A: Governance & Architecture Reconciliation

---

#### Node `CAP-A01`: Human Owner Ratification of TRACE-CAP-001

- **Lane / Workstream:** Governance / Architecture (`GOV-ARCH`)
- **Objective:** Secure formal, auditable Human Owner ratification of `TRACE-CAP-001` (Clauses `CAP-D001` through `CAP-D016`) recorded in `docs/program/06_DECISION_LOG.md`.
- **Explicit Non-goals:** Modifying code; running benchmarks; making prospective technical changes prior to human signature.
- **Governing Decisions & Invariants:** `01_INVARIANTS.md` (Human Authority Boundary); `CAP-D012`.
- **Prerequisites & Typed Dependency Reason:** None (Root Node). Requires Human Owner execution.
- **Pinned Identities:** Base commit `33c80651f2fd05ffef0b1b6a491f0d860dbb8179`; Plan `COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` SHA-256 `ffcd024ea2c7d013c011bea70145ba70fc2f68a90c1154ee9599a4f80efa9c00`.
- **Allowed Mutation Paths & Mutation Authority:** `docs/program/06_DECISION_LOG.md` (append-only). Authority: Human Project Owner.
- **Named Owner Role & Verifier Role:** Owner: Human Owner. Verifier: Codex Independent Critic (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Inputs:* `docs/program/CAP_001_CONTRADICTION_LEDGER_AND_DECISION_REQUEST.md`.
  - *Outputs:* Appended entry `DEC-CAP-001` in `docs/program/06_DECISION_LOG.md` with explicit ratification ballot.
- **Deterministic Acceptance Commands:**
  ```powershell
  git diff docs/program/06_DECISION_LOG.md | Select-String "DEC-CAP-001"
  python -c "assert 'DEC-CAP-001' in open('docs/program/06_DECISION_LOG.md', encoding='utf-8').read()"
  ```
- **Raw Evidence & Receipt Requirements:** Signed decision entry with UTC timestamp and Human Owner identity.
- **Budgets:** Time: 24 hours. Tokens: 0. Provider spend: $0.00. Storage: < 5 KB. Compute: Local.
- **Fallback / Degraded Behavior:** If rejected, the program halts and reverts to legacy `SCALE_CERTIFICATION_RECOVERY_PLAN.md`.
- **Stop Conditions & Escalation Owner:** Ambiguity in decision clauses $\to$ Escalate to Human Project Owner.
- **Rollback / Recovery Obligations:** Revert `06_DECISION_LOG.md` to clean HEAD.
- **Claim Ceiling:** Governance authorization only (`C0`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-A02`.
  - *On Human Promotion:* Establishes Program Milestone `CAP-GA`.

---

#### Node `CAP-A02`: Canonical Document Amendment & Contradiction Reconciliation

- **Lane / Workstream:** Governance / Architecture (`GOV-ARCH`)
- **Objective:** Amend active governing documents (`00_CHARTER.md`, `01_INVARIANTS.md`, `02_EXECUTION_DAG.md`, `03_SHARED_CONTRACTS.md`, `04_EVALUATION_PROTOCOL.md`, `05_PROMOTION_RUBRIC.md`, `07_RISK_REGISTER.md`, `SCALE_100K_TO_1M_EXECUTION_PLAN.md`, `SCALE_CERTIFICATION_RECOVERY_PLAN.md`) to align with ratified `DEC-CAP-001`.
- **Explicit Non-goals:** Editing runtime code in `src/`; modifying historical run dossiers; altering completed gate records.
- **Governing Decisions & Invariants:** `CAP-D001`, `CAP-D002`, `CAP-D003`, `CAP-D004`, `CAP-D005`, `CAP-D006`, `CAP-D007`, `CAP-D008`, `CAP-D010`, `CAP-D012`.
- **Prerequisites & Typed Dependency Reason:** `CAP-A01` (`HARD_GOVERNANCE`: documents cannot be reconciled before formal human ratification).
- **Pinned Identities:** `docs/program/06_DECISION_LOG.md` containing ratified `DEC-CAP-001`.
- **Allowed Mutation Paths & Mutation Authority:**
  `docs/program/00_CHARTER.md`, `docs/program/01_INVARIANTS.md`, `docs/program/02_EXECUTION_DAG.md`, `docs/program/03_SHARED_CONTRACTS.md`, `docs/program/04_EVALUATION_PROTOCOL.md`, `docs/program/05_PROMOTION_RUBRIC.md`, `docs/program/07_RISK_REGISTER.md`, `docs/program/SCALE_100K_TO_1M_EXECUTION_PLAN.md`, `docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md`, `docs/program/README.md`.
- **Named Owner Role & Verifier Role:** Owner: Architecture Specialist (`ARCH-SPEC`). Verifier: Codex Independent Critic (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Inputs:* `docs/program/CAP_001_CONTRADICTION_LEDGER_AND_DECISION_REQUEST.md`.
  - *Outputs:* Clean Git diff applying all 15 reconciliation items from Contradiction Ledger.
- **Deterministic Acceptance Commands:**
  ```powershell
  git diff --check
  python -c "
  for doc in ['00_CHARTER.md', '01_INVARIANTS.md', '03_SHARED_CONTRACTS.md', '04_EVALUATION_PROTOCOL.md', '07_RISK_REGISTER.md']:
      content = open(f'docs/program/{doc}', encoding='utf-8').read()
      assert 'DEC-CAP-001' in content or 'TRACE-CAP-001' in content, f'Missing pointer in {doc}'
  print('Reconciliation Verified.')
  "
  ```
- **Raw Evidence & Receipt Requirements:** Patch manifest detailing modified lines per document and cross-reference table.
- **Budgets:** Time: 4 hours. Tokens: 100K. Provider spend: $0.00. Storage: < 50 KB. Compute: Local.
- **Fallback / Degraded Behavior:** Stop and revert uncommitted edits if any file has unresolvable merge conflicts.
- **Stop Conditions & Escalation Owner:** Contradiction not covered by `DEC-CAP-001` $\to$ Escalate to Human Owner.
- **Rollback / Recovery Obligations:** `git checkout -- docs/program/`
- **Claim Ceiling:** Program Documentation (`C0`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-A03`.

---

#### Node `CAP-A03`: Control Plane Relock & Active Precedence Pointer

- **Lane / Workstream:** Governance / Control Plane (`GOV-CTRL`)
- **Objective:** Compute fresh SHA-256 digests of all reconciled governing documents, update `docs/program/CONTROL_PLANE_LOCK.json`, and set the active pointer to `TRACE-CAP-001`.
- **Explicit Non-goals:** Code changes; benchmark execution.
- **Governing Decisions & Invariants:** `CAP-D012`, `CAP-D015`.
- **Prerequisites & Typed Dependency Reason:** `CAP-A02` (`HARD_DATA`: lockfile can only be hashed after all document amendments are committed).
- **Pinned Identities:** Reconciled Git tree state following `CAP-A02`.
- **Allowed Mutation Paths & Mutation Authority:** `docs/program/CONTROL_PLANE_LOCK.json`, `docs/program/FOUNDATION_STATUS.md`. Authority: Program Coordinator.
- **Named Owner Role & Verifier Role:** Owner: Program Coordinator (`COORD`). Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Inputs:* Working tree files in `docs/program/`.
  - *Outputs:* Validated `docs/program/CONTROL_PLANE_LOCK.json` with matching SHA-256 hashes for all control plane files.
- **Deterministic Acceptance Commands:**
  ```powershell
  python -c "
  import json, hashlib, pathlib
  lock = json.load(open('docs/program/CONTROL_PLANE_LOCK.json', encoding='utf-8'))
  for rel_path, expected_hash in lock.get('files', {}).items():
      p = pathlib.Path('docs/program') / rel_path
      if p.exists():
          actual = hashlib.sha256(p.read_bytes()).hexdigest()
          assert actual == expected_hash, f'Mismatch in {rel_path}: expected {expected_hash}, got {actual}'
  print('Control Plane Lock Validated 100%.')
  "
  ```
- **Raw Evidence & Receipt Requirements:** Hash receipt JSON filed at `docs/program/inbox/cap-a03/lock_receipt.json`.
- **Budgets:** Time: 1 hour. Tokens: 20K. Provider spend: $0.00. Storage: < 10 KB. Compute: Local.
- **Fallback / Degraded Behavior:** Recompute hashes if clean commit changed.
- **Stop Conditions & Escalation Owner:** Mismatch between working tree and lock schema $\to$ Coordinator.
- **Rollback / Recovery Obligations:** Restore previous `CONTROL_PLANE_LOCK.json`.
- **Claim Ceiling:** Control Plane Integrity (`C0`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Triggers `CAP-VER-GA` (Gate `CAP-GA`).
  - *Following Human Approval of Gate CAP-GA:* Unlocks Wave B nodes: `CAP-GW01`, `CAP-RET01`, `CAP-CRX01`, `CAP-JOB01`, `CAP-EVAL01`.

---

### Wave B: Contracts, Safety Repairs, and Baseline Evaluators

---

#### Node `CAP-GW01`: Fail-Closed Gateway Hardening & Malformed Response Defense

- **Lane / Workstream:** Core / Gateway Safety (`GW-SAFE`)
- **Objective:** Eliminate synthetic/canned output generation in `src/trace/v2/model_gateway.py:578-610`. Enforce strict fail-closed exceptions when model responses are empty, malformed, or uncited. Distinguish local vs cloud provider execution explicitly.
- **Explicit Non-goals:** Connecting new external cloud providers; altering existing embedding logic.
- **Governing Decisions & Invariants:** `CAP-D011` (Fail-Closed Execution), `CAP-D006`.
- **Prerequisites & Typed Dependency Reason:** `CAP-A03` / Human Gate `CAP-GA` (`HARD_GOVERNANCE`: code safety modifications require ratified governance).
- **Pinned Identities:** `src/trace/v2/model_gateway.py`.
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/model_gateway.py`, `tests/v2/test_model_gateway.py`. Authority: Gateway Safety Specialist (`GW-SPEC`).
- **Named Owner Role & Verifier Role:** Owner: Gateway Safety Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Inputs:* `src/trace/v2/model_gateway.py`.
  - *Outputs:* Modified gateway failing closed with typed exceptions (`ModelEmptyResponseError`, `ModelMalformedJsonError`, `ModelUncitedOutputError`); comprehensive unit test suite in `tests/v2/test_model_gateway_failclosed.py`.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_model_gateway.py tests/v2/test_model_gateway_failclosed.py -v
  ```
- **Raw Evidence & Receipt Requirements:** Test execution receipt and negative assertion logs demonstrating zero synthetic/canned JSON fallbacks.
- **Budgets:** Time: 4 hours. Tokens: 50K. Provider spend: $0.00. Storage: < 20 KB. Compute: Local CPU.
- **Fallback / Degraded Behavior:** Explicit exception raised; calling task marks projection candidate as `FAILED_VALIDATION`.
- **Stop Conditions & Escalation Owner:** Gateway regressions breaking existing unit tests $\to$ Escalate to Coordinator.
- **Rollback / Recovery Obligations:** `git checkout -- src/trace/v2/model_gateway.py`
- **Claim Ceiling:** Component Safety Conformance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-GW02`, `CAP-MOD01`.

---

#### Node `CAP-GW02`: Model Registry, Non-Zero Cost Telemetry & Local/Cloud Isolation

- **Lane / Workstream:** Core / Economics Telemetry (`GW-ECON`)
- **Objective:** Fix `src/trace/v2/model_gateway.py:130` cost coefficients. Ensure all registered models have verified non-zero input/output pricing ($/M tokens) or are explicitly marked as local ($0.00 API cost). Implement token and cost audit logging for every call.
- **Explicit Non-goals:** Spending live funds; executing unbudgeted API calls.
- **Governing Decisions & Invariants:** `CAP-D006`, `CAP-D010`, `CAP-D011`.
- **Prerequisites & Typed Dependency Reason:** `CAP-GW01` (`HARD_CODE`: cost accounting builds upon hardened invocation gateway).
- **Pinned Identities:** DeepSeek Flash pricing ($0.27/M in, $1.10/M out); local SLM specs (0.0 cost).
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/model_gateway.py`, `src/trace/v2/types.py`, `tests/v2/test_model_cost.py`. Authority: Economics Specialist.
- **Named Owner Role & Verifier Role:** Owner: Economics Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Inputs:* Model pricing tables from `COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` Section 9.
  - *Outputs:* Updated `ModelPricing` dataclass; `call_with_audit()` returning `ModelInvocationReceipt` with input/output tokens, wall time, and exact USD cost.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_model_cost.py -v
  python -c "
  from trace.v2.model_gateway import get_model_pricing
  assert get_model_pricing('deepseek-chat').input_cost_per_m > 0
  assert get_model_pricing('qwen2.5-1.5b-local').input_cost_per_m == 0.0
  print('Pricing Registry Verified.')
  "
  ```
- **Raw Evidence & Receipt Requirements:** Receipt test logs proving no cost is reported as zero unless model is explicitly flagged `is_local=True`.
- **Budgets:** Time: 3 hours. Tokens: 40K. Provider spend: $0.00. Storage: < 15 KB. Compute: Local CPU.
- **Fallback / Degraded Behavior:** Unregistered model ID raises `UnregisteredModelPricingError`.
- **Stop Conditions & Escalation Owner:** Cost discrepancy $> 5\%$ vs official docs $\to$ Coordinator.
- **Rollback / Recovery Obligations:** Revert modified files to clean base.
- **Claim Ceiling:** Component Safety Conformance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-GW03`.

---

#### Node `CAP-GW03`: Token Budget Reservation, Settlement & Hard Spend Caps

- **Lane / Workstream:** Core / Economics Telemetry (`GW-ECON`)
- **Objective:** Implement preflight budget reservation and post-call settlement in `TraceModelGateway`. Ensure calls abort if session or global budget is exceeded.
- **Explicit Non-goals:** Modifying storage layer; creating external payment hooks.
- **Governing Decisions & Invariants:** `CAP-D010`, `CAP-D011`, `CAP-D012`.
- **Prerequisites & Typed Dependency Reason:** `CAP-GW02` (`HARD_CODE`: reservation requires cost coefficients).
- **Pinned Identities:** Session budget limits defined in task packets.
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/model_gateway.py`. Authority: Economics Specialist.
- **Named Owner Role & Verifier Role:** Owner: Economics Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:** Preflight reservation interface `reserve_budget(max_tokens, max_usd)`.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_budget_cap.py -v
  ```
- **Raw Evidence & Receipt Requirements:** Negative test log proving call rejection when reservation exceeds budget cap.
- **Budgets:** Time: 2 hours. Tokens: 30K. Provider spend: $0.00. Storage: < 10 KB. Compute: Local.
- **Fallback / Degraded Behavior:** Abort with `BudgetExceededError`.
- **Stop Conditions & Escalation Owner:** Overspend leak $\to$ Immediate stop.
- **Rollback / Recovery Obligations:** Git revert.
- **Claim Ceiling:** Safety Conformance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks hosted execution in `CAP-MOD01`.

---

#### Node `CAP-RET01`: Dense Embedding Adapter Restoration & Local Model Pinning

- **Lane / Workstream:** Retrieval (`RET-ADAPT`)
- **Objective:** Reconnect the local dense neural embedding adapter in `src/trace/v2/retrieval.py` using `sentence-transformers/all-MiniLM-L6-v2` (or local ONNX equivalent). Verify local GPU acceleration (RTX 5050) with CPU fallback.
- **Explicit Non-goals:** Altering lexical BM25 tokenizers; changing graph schema.
- **Governing Decisions & Invariants:** `CAP-D016` (Retrieval Baseline Restoration), `CAP-D001`.
- **Prerequisites & Typed Dependency Reason:** `CAP-A03` / Human Gate `CAP-GA` (`HARD_GOVERNANCE`).
- **Pinned Identities:** `all-MiniLM-L6-v2` (revision `e4ce9877abf3ed5223c6a46944e9514f7b60a2d2`).
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/retrieval.py`, `src/trace/v2/adapters/embedding.py`, `tests/v2/test_retrieval_embedding.py`. Authority: Retrieval Specialist (`RET-SPEC`).
- **Named Owner Role & Verifier Role:** Owner: Retrieval Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Inputs:* `src/trace/v2/retrieval.py:107-150`.
  - *Outputs:* Functional `LocalEmbeddingAdapter` producing 384-dimensional float32 dense vectors at $> 1,000\text{ sentences/sec}$ on GPU.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_retrieval_embedding.py -v
  python -c "
  from trace.v2.retrieval import get_embedding_adapter
  adapter = get_embedding_adapter('all-MiniLM-L6-v2')
  vec = adapter.embed('Test query')
  assert len(vec) == 384
  print('Dense Adapter Verified.')
  "
  ```
- **Raw Evidence & Receipt Requirements:** Embedding speed benchmark receipt showing throughput and vector dimension verification.
- **Budgets:** Time: 4 hours. Tokens: 20K. Provider spend: $0.00. Storage: < 100 MB (local weights). Compute: Local GPU.
- **Fallback / Degraded Behavior:** Fallback to CPU multi-threading if CUDA/DirectML unavailable.
- **Stop Conditions & Escalation Owner:** Vector dimension mismatch or CUDA crash $\to$ Retrieval Specialist.
- **Rollback / Recovery Obligations:** Revert modified files.
- **Claim Ceiling:** Component Performance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-RET02`.

---

#### Node `CAP-RET02`: Hybrid BM25 + Dense RRF Fusion & Truncation Removal

- **Lane / Workstream:** Retrieval (`RET-FUSION`)
- **Objective:** Remove artificial postings truncation (`[:300]`) in `src/trace/v2/retrieval.py:350-420` and `run_100k_scale_gate.py:1801-1860`. Implement Reciprocal Rank Fusion (RRF with $k=60$) combining BM25 and dense vector results into a unified candidate ranking.
- **Explicit Non-goals:** LLM reranking; altering raw atom storage.
- **Governing Decisions & Invariants:** `CAP-D016`, `CAP-D008`.
- **Prerequisites & Typed Dependency Reason:** `CAP-RET01` (`HARD_CODE`: fusion requires functional dense embedding adapter).
- **Pinned Identities:** RRF parameter $k=60$; candidate pool $K=100$.
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/retrieval.py`, `tests/v2/test_hybrid_retrieval.py`. Authority: Retrieval Specialist.
- **Named Owner Role & Verifier Role:** Owner: Retrieval Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Outputs:* Functional `retrieve_hybrid(query, top_k=20)` achieving P95 latency $\le 15\text{ ms}$.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_hybrid_retrieval.py -v
  ```
- **Raw Evidence & Receipt Requirements:** Unit test execution log proving reciprocal rank fusion runs without truncation and returns expected document IDs.
- **Budgets:** Time: 3 hours. Tokens: 30K. Provider spend: $0.00. Storage: < 15 KB. Compute: Local GPU/CPU.
- **Fallback / Degraded Behavior:** Lexical BM25 fallback if dense vectors are unpopulated, with explicit telemetry flag.
- **Stop Conditions & Escalation Owner:** Latency exceeds 25ms on 10K test index $\to$ Retrieval Specialist.
- **Rollback / Recovery Obligations:** Git revert.
- **Claim Ceiling:** Component Performance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-RET03`, `CAP-RET04`.

---

#### Node `CAP-RET03`: Graph Walk Spreading Activation & Personalized PageRank (PPR)

- **Lane / Workstream:** Retrieval (`RET-GRAPH`)
- **Objective:** Optimize Personalized PageRank (PPR) graph spreading activation in `src/trace/v2/retrieval.py:981-1050`. Traverse associative edges (`CONTAINS`, `DEPENDS_ON`, `ASSOCIATED_WITH`) for multi-hop queries with max out-degree $\le 50$, walk depth $\le 15$, and latency $\le 10\text{ ms}$.
- **Explicit Non-goals:** Unbounded graph expansion; dynamic graph mutation during query.
- **Governing Decisions & Invariants:** `CAP-D001`, `CAP-D008`.
- **Prerequisites & Typed Dependency Reason:** `CAP-RET02` (`HARD_CODE`: graph seeds are provided by hybrid top-k candidates).
- **Pinned Identities:** Teleport probability $\alpha = 0.15$; max iterations = 20.
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/retrieval.py`, `tests/v2/test_graph_retrieval.py`. Authority: Retrieval Specialist.
- **Named Owner Role & Verifier Role:** Owner: Retrieval Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:** `retrieve_multihop(query, top_k=20)`.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_graph_retrieval.py -v
  ```
- **Raw Evidence & Receipt Requirements:** Graph traversal latency receipt and multi-hop node resolution receipt.
- **Budgets:** Time: 3 hours. Tokens: 30K. Provider spend: $0.00. Storage: < 10 KB. Compute: Local.
- **Fallback / Degraded Behavior:** Return hybrid candidates without graph expansion if graph is empty.
- **Stop Conditions & Escalation Owner:** Graph cycle or runaway walk $> 35\text{ ms}$ $\to$ Retrieval Specialist.
- **Rollback / Recovery Obligations:** Git revert.
- **Claim Ceiling:** Component Performance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-RET04`.

---

#### Node `CAP-RET04`: Frozen Retrieval Baseline Verification (Gate CAP-GB-RET)

- **Lane / Workstream:** Retrieval / Verification (`RET-VERIF`)
- **Objective:** Execute independent verification of the restored hybrid retrieval engine on SciFact, NFCorpus, and FiQA held-out splits. Prove that retrieval floors are met without calling an LLM.
- **Explicit Non-goals:** Testing generative synthesis; running 1M scale test.
- **Governing Decisions & Invariants:** `CAP-D016`, `CAP-D008`, `CAP-D015`.
- **Prerequisites & Typed Dependency Reason:** `CAP-RET02`, `CAP-RET03`, `CAP-EVAL02` (`HARD_DATA`: verification requires frozen evaluation corpora).
- **Pinned Identities:** BEIR SciFact (nDCG@10 $\ge 0.65$), NFCorpus (nDCG@10 $\ge 0.32$), FiQA (nDCG@10 $\ge 0.38$).
- **Allowed Mutation Paths & Mutation Authority:** Read-only test execution. Output: `docs/program/inbox/cap-ret04/retrieval_baseline_dossier.json`. Authority: Codex Independent Verifier (`VERIF-INDEP`).
- **Named Owner Role & Verifier Role:** Owner & Verifier: Codex Independent Verifier (`VERIF-INDEP`). (Implementer barred).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Outputs:* `RetrievalBaselineReceipt` documenting nDCG@10, Recall@20, P95 latency, and zero model calls.
- **Deterministic Acceptance Commands:**
  ```powershell
  python benchmarks/run_frozen_retrieval_baseline.py --verify-receipt
  ```
- **Raw Evidence & Receipt Requirements:** JSON receipt containing per-query rankings and cryptographic dataset checksums.
- **Budgets:** Time: 2 hours. Tokens: 20K. Provider spend: $0.00. Storage: < 5 MB. Compute: Local GPU/CPU.
- **Fallback / Degraded Behavior:** Gate failure if nDCG floors are breached.
- **Stop Conditions & Escalation Owner:** Score floor failure $\to$ Retrieval Specialist.
- **Rollback / Recovery Obligations:** None (read-only verification).
- **Claim Ceiling:** Component Performance Baseline (`C2`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks Gate `CAP-GB` retrieval clearance.

---

#### Node `CAP-CRX01`: Cortex Projections Schema, Revision Lineage & Evidence Anchors

- **Lane / Workstream:** Cortex (`CRX-SCHEMA`)
- **Objective:** Create typed Pydantic/SQL schemas for `CortexProjection`, `TopicHolon`, `SectionSummary`, `EntityCandidate`, and `RelationCandidate` in `src/trace/v2/cortex/`. Enforce immutable lineage: every projection must record `source_atom_ids`, `model_id`, `prompt_hash`, `runtime_hash`, `policy_id`, and `created_at`.
- **Explicit Non-goals:** Modifying canonical Spine tables; generating text.
- **Governing Decisions & Invariants:** `CAP-D004` (Spine vs Projection), `CAP-D005`, `CAP-D014`.
- **Prerequisites & Typed Dependency Reason:** `CAP-A03` / Human Gate `CAP-GA` (`HARD_GOVERNANCE`).
- **Pinned Identities:** Schema revision `v2.cortex.20260902`.
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/cortex/`, `src/trace/v2/types.py`, `tests/v2/test_cortex_schemas.py`. Authority: Cortex Specialist (`CRX-SPEC`).
- **Named Owner Role & Verifier Role:** Owner: Cortex Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Outputs:* Pydantic schemas validating byte-offset anchors back to canonical atoms; rejection of unanchored projections.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_cortex_schemas.py -v
  ```
- **Raw Evidence & Receipt Requirements:** Schema validation test receipt verifying 100% anchor resolution to raw atoms.
- **Budgets:** Time: 4 hours. Tokens: 40K. Provider spend: $0.00. Storage: < 20 KB. Compute: Local.
- **Fallback / Degraded Behavior:** Raise `UnanchoredProjectionError`.
- **Stop Conditions & Escalation Owner:** Anchor drift $\to$ Cortex Specialist.
- **Rollback / Recovery Obligations:** Git revert.
- **Claim Ceiling:** Schema Conformance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-CRX02`, `CAP-CRX03`.

---

#### Node `CAP-CRX02`: Consolidator Engine Interface, Extractive Control & Local SLM Adapter

- **Lane / Workstream:** Cortex (`CRX-CONSOL`)
- **Objective:** Refactor `src/trace/v2/organization.py` into a unified `CortexConsolidator` class. Retain deterministic string clipping as the explicit baseline control (`mode="extractive_control"`). Implement the model-driven consolidation interface (`mode="semantic_slm"`) consuming atom clusters and producing structured holons via `TraceModelGateway`.
- **Explicit Non-goals:** Calling unvetted cloud models; running 100K batch.
- **Governing Decisions & Invariants:** `CAP-D003` (Decoupled Consolidation), `CAP-D004`, `CAP-D006`.
- **Prerequisites & Typed Dependency Reason:** `CAP-CRX01`, `CAP-GW01` (`HARD_CODE`: consolidator requires schemas and fail-closed gateway).
- **Pinned Identities:** `organization.py` refactored into `cortex_consolidator.py`.
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/organization.py`, `src/trace/v2/cortex_consolidator.py`, `tests/v2/test_cortex_consolidator.py`. Authority: Cortex Specialist.
- **Named Owner Role & Verifier Role:** Owner: Cortex Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:** `CortexConsolidator.consolidate_cluster(atoms, mode) -> CandidateProjection`.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_cortex_consolidator.py -v
  ```
- **Raw Evidence & Receipt Requirements:** Test receipts proving exact deterministic output for `mode="extractive_control"` and structured holon extraction for mock model outputs.
- **Budgets:** Time: 5 hours. Tokens: 60K. Provider spend: $0.00. Storage: < 30 KB. Compute: Local.
- **Fallback / Degraded Behavior:** Automatic degradation to `extractive_control` if model is unavailable, with explicit warning receipt.
- **Stop Conditions & Escalation Owner:** Broken extractive parity with legacy tests $\to$ Cortex Specialist.
- **Rollback / Recovery Obligations:** Git revert.
- **Claim Ceiling:** Component Conformance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-JOB01`, `CAP-MOD01`.

---

#### Node `CAP-CRX03`: Risk-Tiered Projection Activation & Atomic Journaling Handover

- **Lane / Workstream:** Cortex (`CRX-ACTIVATE`)
- **Objective:** Implement risk-tiered activation in `src/trace/v2/service.py` and `store.py`. Low-risk navigation summaries auto-activate following detached validation; high-risk factual/schema proposals remain in `cortex_proposals` table until human approval. Implement journaled pointer swaps across SQLite/Postgres and external aliases.
- **Explicit Non-goals:** Auto-approving high-risk schema deletions; mutating Spine tables.
- **Governing Decisions & Invariants:** `CAP-D007` (Risk-Tiered Activation), `CAP-D014`, `CAP-D015`.
- **Prerequisites & Typed Dependency Reason:** `CAP-CRX01`, `CAP-EVAL03` (`HARD_CODE`: activation requires schemas and detached validator).
- **Pinned Identities:** Risk tiers: `TIER_1_LOW_RISK_NAV`, `TIER_2_MED_RISK_RELATION`, `TIER_3_HIGH_RISK_SCHEMA`.
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/service.py`, `src/trace/v2/store.py`, `tests/v2/test_cortex_activation.py`. Authority: Cortex Specialist.
- **Named Owner Role & Verifier Role:** Owner: Cortex Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:** `activate_projection(projection_id, validation_receipt) -> ActivationReceipt`.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_cortex_activation.py -v
  ```
- **Raw Evidence & Receipt Requirements:** Crash-simulation test logs demonstrating zero dangling aliases or corrupted pointers during simulated process kill.
- **Budgets:** Time: 4 hours. Tokens: 40K. Provider spend: $0.00. Storage: < 25 KB. Compute: Local.
- **Fallback / Degraded Behavior:** Immediate transaction rollback to previous active release pointer.
- **Stop Conditions & Escalation Owner:** Corrupted pointer or unlogged activation $\to$ Coordinator.
- **Rollback / Recovery Obligations:** Git revert.
- **Claim Ceiling:** Component Safety Conformance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-INT01`.

---

#### Node `CAP-JOB01`: Ingestion-to-Consolidation Asynchronous Pipeline Chaining

- **Lane / Workstream:** Infrastructure / Job System (`INFRA-JOB`)
- **Objective:** Modify `src/trace/v2/service.py:571-599` and `3442-3461`. Chain background consolidation jobs immediately upon successful indexing: `index-ready -> candidate consolidation -> validation -> release assembly -> activation`. Ensure ingestion returns immediately without blocking.
- **Explicit Non-goals:** Replacing existing SQLite WAL job queue; introducing Celery/RabbitMQ.
- **Governing Decisions & Invariants:** `CAP-D003` (Decoupled Ingestion), `CAP-D010`.
- **Prerequisites & Typed Dependency Reason:** `CAP-CRX02` (`HARD_CODE`: job worker invokes `CortexConsolidator`).
- **Pinned Identities:** Job types: `job.index.atoms`, `job.cortex.consolidate`, `job.cortex.validate`.
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/service.py`, `tests/v2/test_job_pipeline.py`. Authority: Infrastructure Specialist (`INFRA-SPEC`).
- **Named Owner Role & Verifier Role:** Owner: Infrastructure Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:** Asynchronous event queue transition verified via SQLite WAL inspect.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_job_pipeline.py -v
  ```
- **Raw Evidence & Receipt Requirements:** End-to-end trace receipt showing ingestion completing in $< 10\text{ ms}$ while consolidation executes in worker thread.
- **Budgets:** Time: 3 hours. Tokens: 30K. Provider spend: $0.00. Storage: < 15 KB. Compute: Local.
- **Fallback / Degraded Behavior:** Jobs remain queued in SQLite WAL table if worker is stopped; resume on restart.
- **Stop Conditions & Escalation Owner:** Ingestion latency degradation $> 15\%$ $\to$ Infrastructure Specialist.
- **Rollback / Recovery Obligations:** Git revert.
- **Claim Ceiling:** Component Conformance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-JOB02`, `CAP-INT01`.

---

#### Node `CAP-JOB02`: Job Lease Expiry, Heartbeat, Backpressure & Crash Recovery

- **Lane / Workstream:** Infrastructure / Job System (`INFRA-JOB`)
- **Objective:** Implement heartbeat monitoring, lease timeouts (default 300s), job retry limits (max 3 retries), and backpressure limits (queue depth cap $\le 5,000$ pending clusters) in the job engine.
- **Explicit Non-goals:** Distributed cluster consensus.
- **Governing Decisions & Invariants:** `CAP-D003`, `CAP-D010`.
- **Prerequisites & Typed Dependency Reason:** `CAP-JOB01` (`HARD_CODE`: lease engine wraps pipeline jobs).
- **Pinned Identities:** Default heartbeat interval = 10s; lease timeout = 300s.
- **Allowed Mutation Paths & Mutation Authority:** `src/trace/v2/service.py`, `src/trace/v2/store.py`, `tests/v2/test_job_recovery.py`. Authority: Infrastructure Specialist.
- **Named Owner Role & Verifier Role:** Owner: Infrastructure Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:** Job recovery test suite simulating crash-after-consolidation and lease re-acquisition.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/v2/test_job_recovery.py -v
  ```
- **Raw Evidence & Receipt Requirements:** Test logs demonstrating zero orphaned jobs or double-activations after worker crash.
- **Budgets:** Time: 3 hours. Tokens: 30K. Provider spend: $0.00. Storage: < 15 KB. Compute: Local.
- **Fallback / Degraded Behavior:** Job moved to `DEAD_LETTER` queue after 3 retries with failure receipt.
- **Stop Conditions & Escalation Owner:** Job starvation or dead-lock $\to$ Infrastructure Specialist.
- **Rollback / Recovery Obligations:** Git revert.
- **Claim Ceiling:** Component Safety Conformance (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-INT01`.

---

#### Node `CAP-EVAL01`: Semantic Evaluation Protocol & Multi-Resolution Scorecards

- **Lane / Workstream:** Evaluation / Contracts (`EVAL-PROTO`)
- **Objective:** Author `docs/program/04_EVALUATION_PROTOCOL.md` amendment and evaluation harness scripts. Define explicit scorecards:
  1. Structural Coverage (orphan rate = 0.0%, routing purity $\ge 85\%$).
  2. Semantic Quality (faithfulness / proposition support $\ge 95\%$, coherence $\ge 0.85$).
  3. Direct IR (SciFact/NFCorpus/FiQA nDCG@10).
  4. Multi-hop Reasoning (MuSiQue / MultiHop-RAG coverage@20 $\ge 0.75$).
  5. Synthesis Grounding (zero hallucination on unsupported queries).
- **Explicit Non-goals:** Executing model calls; altering code.
- **Governing Decisions & Invariants:** `CAP-D008` (Scorecards), `CAP-D001`.
- **Prerequisites & Typed Dependency Reason:** `CAP-A03` / Human Gate `CAP-GA` (`HARD_GOVERNANCE`).
- **Pinned Identities:** Evaluation protocol `v2.eval.20260902`.
- **Allowed Mutation Paths & Mutation Authority:** `docs/program/04_EVALUATION_PROTOCOL.md`, `benchmarks/protocols/`. Authority: Evaluation Specialist (`EVAL-SPEC`).
- **Named Owner Role & Verifier Role:** Owner: Evaluation Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:** `docs/program/04_EVALUATION_PROTOCOL.md` updated with mathematical definitions and schemas.
- **Deterministic Acceptance Commands:**
  ```powershell
  python -c "
  proto = open('docs/program/04_EVALUATION_PROTOCOL.md', encoding='utf-8').read()
  assert 'Proposition Support' in proto
  assert 'Paired Ablation' in proto
  print('Protocol Verified.')
  "
  ```
- **Raw Evidence & Receipt Requirements:** Markdown protocol diff with signed review receipt.
- **Budgets:** Time: 3 hours. Tokens: 40K. Provider spend: $0.00. Storage: < 20 KB. Compute: Local.
- **Fallback / Degraded Behavior:** None (governance documentation).
- **Stop Conditions & Escalation Owner:** Contradiction with `01_INVARIANTS.md` $\to$ Coordinator.
- **Rollback / Recovery Obligations:** Git revert.
- **Claim Ceiling:** Evaluation Specification (`C0`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-EVAL02`, `CAP-EVAL03`.

---

#### Node `CAP-EVAL02`: Frozen Benchmark Datasets & Ground-Truth Anchor Manifests

- **Lane / Workstream:** Evaluation / Data (`EVAL-DATA`)
- **Objective:** Stage and pin frozen splits for SciFact (1,000 queries), NFCorpus (323 queries), FiQA (648 queries), and MuSiQue (500 multi-hop queries). Compute immutable SHA-256 manifests for corpora, queries, and qrels.
- **Explicit Non-goals:** Modifying corpus texts; downloading unvetted web corpora.
- **Governing Decisions & Invariants:** `CAP-D008`, `CAP-D009`.
- **Prerequisites & Typed Dependency Reason:** `CAP-EVAL01` (`HARD_DATA`: datasets are pinned to match evaluation protocol).
- **Pinned Identities:** Frozen manifest `benchmarks/manifests/beir_musique_frozen_v1.json`.
- **Allowed Mutation Paths & Mutation Authority:** `benchmarks/manifests/`, `docs/program/inbox/cap-eval02/`. Authority: Evaluation Specialist.
- **Named Owner Role & Verifier Role:** Owner: Evaluation Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:** Dataset checksum manifest with query/qrel split identities.
- **Deterministic Acceptance Commands:**
  ```powershell
  python benchmarks/verify_dataset_checksums.py --manifest benchmarks/manifests/beir_musique_frozen_v1.json
  ```
- **Raw Evidence & Receipt Requirements:** Checksum verification log matching canonical external BEIR/MuSiQue hashes.
- **Budgets:** Time: 2 hours. Tokens: 10K. Provider spend: $0.00. Storage: < 500 MB (local test corpora). Compute: Local.
- **Fallback / Degraded Behavior:** Abort if remote download hash mismatches.
- **Stop Conditions & Escalation Owner:** Checksum drift $\to$ Evaluation Specialist.
- **Rollback / Recovery Obligations:** Purge invalid downloads.
- **Claim Ceiling:** Benchmark Manifest (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-RET04`, `CAP-MOD01`, `CAP-INT01`.

---

#### Node `CAP-EVAL03`: Detached Faithfulness, Coherence & Entailment Verifier Suite

- **Lane / Workstream:** Evaluation / Verifier Tooling (`EVAL-TOOL`)
- **Objective:** Build the detached validation harness `benchmarks/evaluators/faithfulness_validator.py`. Implement atomic proposition extraction, source-atom span alignment, and NLI/entailment scoring. Replace the 5% token overlap smoke check with a true $\ge 95\%$ proposition support test.
- **Explicit Non-goals:** Modifying candidate generation code; running scale runs.
- **Governing Decisions & Invariants:** `CAP-D008`, `CAP-D015` (Detached Validator).
- **Prerequisites & Typed Dependency Reason:** `CAP-EVAL01` (`HARD_CODE`: implements scoring protocol).
- **Pinned Identities:** Entailment threshold $\tau = 0.95$; proposition extractor regex/model.
- **Allowed Mutation Paths & Mutation Authority:** `benchmarks/evaluators/`, `tests/evaluators/test_faithfulness.py`. Authority: Evaluation Specialist.
- **Named Owner Role & Verifier Role:** Owner: Evaluation Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:** `verify_faithfulness(summary, source_atoms) -> ValidationReceipt(passed: bool, support_ratio: float)`.
- **Deterministic Acceptance Commands:**
  ```powershell
  pytest tests/evaluators/test_faithfulness.py -v
  ```
- **Raw Evidence & Receipt Requirements:** Negative test suite proving that hallucinated facts (not in source atoms) produce `passed=False`.
- **Budgets:** Time: 4 hours. Tokens: 40K. Provider spend: $0.00. Storage: < 20 KB. Compute: Local CPU/GPU.
- **Fallback / Degraded Behavior:** Reject candidate summary if validator fails or produces unparseable receipts.
- **Stop Conditions & Escalation Owner:** False positive on known hallucination $\to$ Evaluation Specialist.
- **Rollback / Recovery Obligations:** Git revert.
- **Claim Ceiling:** Evaluator Tooling (`C1`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-CRX03`, `CAP-MOD01`.

---

### Wave C: Bounded Model Bake-Off and Cascade Selection

---

#### Node `CAP-MOD01`: Model Bake-Off on Frozen Atom Clusters

- **Lane / Workstream:** Cortex / Model Evaluation (`MOD-BAKE`)
- **Objective:** Execute a frozen bake-off on 100 held-out atom clusters across candidate model tiers:
  - Tier 0: Extractive Control (heuristic zero-LLM baseline control)
  - Tier 1: 4B Modern SLM (e.g. Gemma 4 E4B / Qwen3-VL-4B)
  - Tier 2: 8B–12B Laptop SOTA (e.g. Gemma 4 12B / Qwen3-VL-8B-Instruct)
  - Tier 3: 27B Heavyweight Local (e.g. Qwen3.8-27B quantized Q4_K_M via hybrid GPU/Host RAM offload)
  - Teacher: DeepSeek V4 Flash (Cloud upper-bound comparator)
  Measure: Proposition support ($\ge 95\%$), extractive summary quality, latency (tok/s), VRAM RSS, and cost per 1,000 holons.
  *Execution Staging:* Supports staged two-phase execution: Phase 1 executes local tiers (Tiers 0–3) 100% offline (e.g. overnight on laptop GPU with internet disconnected); Phase 2 executes the DeepSeek Flash teacher comparator and cloud validation upon reconnection (~1–2 min).
- **Explicit Non-goals:** Writing to production Spine; auto-activating outputs; running unbudgeted cloud queries.
- **Governing Decisions & Invariants:** `CAP-D006` (Empirical Selection), `CAP-D009`, `CAP-D010`, `CAP-D011`, `CAP-D012`, `Pre-flight User Notification Invariant` (the system/runner must explicitly notify the user that a ~5-hour offline GPU run is scheduled/about to begin before hitting compute, verifying local weight caches so the user may safely disconnect network or leave it running overnight).
- **Prerequisites & Typed Dependency Reason:** `CAP-GW01`, `CAP-GW02`, `CAP-GW03`, `CAP-CRX02`, `CAP-EVAL02`, `CAP-EVAL03` + Human Provider Authorization (`HARD_EVAL`).
- **Pinned Identities:** 100 frozen atom clusters in `benchmarks/data/bakeoff_clusters_v1.json`.
- **Allowed Mutation Paths & Mutation Authority:** Read-only model execution. Output: `docs/program/inbox/cap-mod01/bakeoff_raw_results.json`. Authority: Model Specialist (`MOD-SPEC`).
- **Named Owner Role & Verifier Role:** Owner: Model Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Outputs:* `BakeOffResultManifest` documenting per-model faithfulness, tokens/sec, VRAM RSS, and cost.
- **Deterministic Acceptance Commands:**
  ```powershell
  python benchmarks/run_model_bakeoff.py --manifest benchmarks/data/bakeoff_clusters_v1.json --verify-receipt
  # Or staged two-phase execution:
  # Phase 1 (offline overnight): python benchmarks/run_model_bakeoff.py --manifest benchmarks/data/bakeoff_clusters_v1.json --offline-local-only
  # Phase 2 (online morning):    python benchmarks/run_model_bakeoff.py --manifest benchmarks/data/bakeoff_clusters_v1.json --resume-cloud-eval --verify-receipt
  ```
- **Raw Evidence & Receipt Requirements:** Cryptographically signed JSON execution receipts containing full prompt hashes, raw outputs, and detached validation scores.
- **Budgets:** Time: 6 hours. Tokens: 500K. Provider spend: $\le \$5.00$ (DeepSeek Flash comparator). Storage: < 50 MB. Compute: Local GPU (RTX 5050).
- **Fallback / Degraded Behavior:** Halt run if cloud provider spend exceeds $5.00 limit.
- **Stop Conditions & Escalation Owner:** Cloud rate limit or GPU OOM $\to$ Model Specialist.
- **Rollback / Recovery Obligations:** Delete unverified intermediate outputs.
- **Claim Ceiling:** Experimental Model Evidence (`C2`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-MOD02`.

---

#### Node `CAP-MOD02`: Model Selection, Cost/Quality Pareto Frontier & Cascade Determination (Gate CAP-GC)

- **Lane / Workstream:** Cortex / Governance (`MOD-GOV`)
- **Objective:** Analyze bake-off evidence, construct the Cost/Quality Pareto Frontier, select the default local SLM (target: 3B–8B meeting $\ge 95\%$ faithfulness at $0 API cost), define escalation rules for harder topics, and assemble the Gate `CAP-GC` dossier.
- **Explicit Non-goals:** Arbitrary selection without raw benchmark receipts; overriding failure metrics.
- **Governing Decisions & Invariants:** `CAP-D006`, `CAP-D010`, `CAP-D013`.
- **Prerequisites & Typed Dependency Reason:** `CAP-MOD01` (`HARD_DATA`: selection requires raw bake-off dossier).
- **Pinned Identities:** `docs/program/inbox/cap-mod01/bakeoff_raw_results.json`.
- **Allowed Mutation Paths & Mutation Authority:** `docs/program/inbox/cap-mod02/cortex_model_selection_dossier.md`. Authority: Model Specialist & Coordinator.
- **Named Owner Role & Verifier Role:** Owner: Model Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Outputs:* `CortexModelSelectionDossier` recommending primary SLM and optional escalation policy.
- **Deterministic Acceptance Commands:**
  ```powershell
  python -c "
  import json
  data = json.load(open('docs/program/inbox/cap-mod01/bakeoff_raw_results.json'))
  assert len(data['models']) >= 3
  print('Bake-off data complete.')
  "
  ```
- **Raw Evidence & Receipt Requirements:** Pareto chart artifact, per-model scorecard table, negative results ledger.
- **Budgets:** Time: 2 hours. Tokens: 30K. Provider spend: $0.00. Storage: < 5 MB. Compute: Local.
- **Fallback / Degraded Behavior:** If no local model passes $\ge 95\%$, default to `extractive_control` with human escalation.
- **Stop Conditions & Escalation Owner:** All candidate models fail faithfulness floor $\to$ Human Owner.
- **Rollback / Recovery Obligations:** None.
- **Claim Ceiling:** Model Selection Decision Dossier (`C2`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Triggers `CAP-VER-GC` (Gate `CAP-GC`).
  - *Following Human Approval of Gate CAP-GC:* Unlocks Wave D (`CAP-INT01`).

---

### Wave D: Integrated 10K Shadow Cortex

---

#### Node `CAP-INT01`: 10K Shadow Cortex Integration & Lifecycle Validation (Gate CAP-GD)

- **Lane / Workstream:** Integration / Operations (`INT-10K`)
- **Objective:** Ingest 10,000 real documents in headless Core mode ($\ge 800\text{ docs/sec}$ to SQLite WAL Spine). Trigger asynchronous background consolidation using the selected local SLM. Verify:
  1. Hot path ingestion throughput is not degraded.
  2. Crash/restart during consolidation recovers without duplicate work or data loss.
  3. Generated projections remain in candidate shadow mode until detached validation passes.
  4. Journaled pointer swap activates low-risk summaries atomically.
  5. Multi-hop retrieval coverage increases vs extractive control.
- **Explicit Non-goals:** Running cloud models on all 10K docs; modifying production releases.
- **Governing Decisions & Invariants:** `CAP-D003`, `CAP-D004`, `CAP-D007`, `CAP-D009`, `CAP-D010`.
- **Prerequisites & Typed Dependency Reason:** `CAP-CRX03`, `CAP-JOB01`, `CAP-JOB02`, `CAP-MOD02` + Human Gate `CAP-GC` (`HARD_INTEGRATION`).
- **Pinned Identities:** 10K document corpus snapshot `benchmarks/data/corpus_10k_frozen.jsonl`.
- **Allowed Mutation Paths & Mutation Authority:** Test database `trace_10k_shadow.db`. Output: `docs/program/inbox/cap-int01/10k_shadow_dossier.json`. Authority: Integration Specialist (`INT-SPEC`).
- **Named Owner Role & Verifier Role:** Owner: Integration Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Outputs:* `10KShadowDossier` recording ingestion rate, background worker latency, storage amplification, orphan atom rate (0.0%), and faithfulness ($\ge 95\%$).
- **Deterministic Acceptance Commands:**
  ```powershell
  python benchmarks/run_10k_shadow_lifecycle.py --verify-invariants
  ```
- **Raw Evidence & Receipt Requirements:** WAL inspection receipt, crash-recovery receipt, detached validation receipt.
- **Budgets:** Time: 4 hours. Tokens: 1M (Local SLM). Provider spend: $0.00 (100% Local). Storage: < 1 GB. Compute: Local GPU.
- **Fallback / Degraded Behavior:** Halt consolidation if queue depth exceeds 5,000; alert coordinator.
- **Stop Conditions & Escalation Owner:** Lost event in WAL or crash failure $\to$ Infrastructure Specialist.
- **Rollback / Recovery Obligations:** Purge test database `trace_10k_shadow.db`.
- **Claim Ceiling:** Operational Lifecycle Conformance (`C3`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Triggers `CAP-VER-GD` (Gate `CAP-GD`).
  - *Following Human Approval of Gate CAP-GD:* Unlocks Wave E (`CAP-INT02`).

---

### Wave E: Real 100K Paired Qualification

---

#### Node `CAP-INT02`: 100K Paired Qualification (Core + Retrieval + Cortex Shadow Profiles) (Gate CAP-GE)

- **Lane / Workstream:** Integration / Scale Qualification (`INT-100K`)
- **Objective:** Execute paired evaluation on a real 100,000-document corpus snapshot under three isolated profiles:
  - Profile 1 (Core + Lexical Baseline): Spine + BM25 only.
  - Profile 2 (Core + Hybrid Retrieval): Spine + BM25 + Dense all-MiniLM-L6-v2 + RRF.
  - Profile 3 (Core + Hybrid + Shadow Cortex): Profile 2 + Asynchronous Local SLM Semantic Projections.
  Produce separate, unconfounded scorecards for Spine Durability, Retrieval Quality (SciFact, NFCorpus, FiQA, MuSiQue), Storage Footprint (Spine vs Vector vs Graph vs Total), and Latency.
- **Explicit Non-goals:** Blending Profile 2 and Profile 3 into a single inseparable number; calling cloud LLMs on all 100K docs.
- **Governing Decisions & Invariants:** `CAP-D001`, `CAP-D008`, `CAP-D009`, `CAP-D010`, `CAP-D013`.
- **Prerequisites & Typed Dependency Reason:** `CAP-INT01` + Human Gate `CAP-GD` (`HARD_SCALE_GATE`).
- **Pinned Identities:** 100K corpus capsule `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json` (Merkle `38d1a1cf980d447edef7bfaa1ebc4d06129386a82bdd2c6f724f45d8624fc530`, prefix-slice policy; legacy reference to `benchmarks/data/corpus_100k_frozen.jsonl` retired).
- **Allowed Mutation Paths & Mutation Authority:** Test databases `trace_100k_profile1.db`, `trace_100k_profile2.db`, `trace_100k_profile3.db`. Output: `docs/program/inbox/cap-int02/100k_qualification_dossier.json`. Authority: Integration Specialist.
- **Named Owner Role & Verifier Role:** Owner: Integration Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Outputs:* `100KQualificationDossier` containing paired Wilcoxon signed-rank significance tests, Cohen's $d$, and bootstrap 95% CIs.
- **Deterministic Acceptance Commands:**
  ```powershell
  python benchmarks/run_100k_qualification.py --compare-profiles --verify-receipts
  ```
- **Raw Evidence & Receipt Requirements:** Cryptographic evidence receipts for each profile; storage ledger separating SQLite WAL, Qdrant vectors, and SQLite derived graphs.
- **Budgets:** Time: 8 hours. Tokens: 5M (Local SLM). Provider spend: $0.00. Storage: < 10 GB. Compute: Local GPU (RTX 5050).
- **Fallback / Degraded Behavior:** If Profile 3 fails quality floors, Profile 2 can still be qualified as the standalone retrieval baseline.
- **Stop Conditions & Escalation Owner:** Profile 2 regression vs baseline or storage multiplier $> 3.5\times$ $\to$ Coordinator.
- **Rollback / Recovery Obligations:** Clean test database directories.
- **Claim Ceiling:** 100K Component Qualification (`C3`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Unlocks `CAP-INT03`, triggers `CAP-VER-GE`.
  - *Following Human Approval of Gate CAP-GE:* Unlocks eligibility for Wave F (`CAP-SCALE01`) and Wave G (`CAP-SCALE02`).

---

#### Node `CAP-INT03`: Synthesis Grounding & Citation Ablation on Retrieved Evidence

- **Lane / Workstream:** Synthesis (`SYN-GROUND`)
- **Objective:** Evaluate answer synthesis on top of frozen retrieved evidence from `CAP-INT02`. Test LLM answer generation across 200 queries (100 answerable, 100 unanswerable/abstention). Verify:
  1. 100% of generated factual claims map to byte-exact source atom offsets.
  2. Abstention accuracy $\ge 90\%$ on unanswerable queries.
  3. Zero writes to the Spine or Cortex knowledge graph during synthesis.
- **Explicit Non-goals:** Calling synthesis on 100K raw documents; treating answer generation as a retrieval substitute.
- **Governing Decisions & Invariants:** `CAP-D001`, `CAP-D004`, `CAP-D008`.
- **Prerequisites & Typed Dependency Reason:** `CAP-INT02` (`HARD_EVAL`: synthesis consumes frozen retrieved candidate atoms).
- **Pinned Identities:** 200 query evaluation pack `benchmarks/data/synthesis_eval_pack_v1.json`.
- **Allowed Mutation Paths & Mutation Authority:** Read-only test execution. Output: `docs/program/inbox/cap-int03/synthesis_grounding_dossier.json`. Authority: Synthesis Specialist (`SYN-SPEC`).
- **Named Owner Role & Verifier Role:** Owner: Synthesis Specialist. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Outputs:* `SynthesisGroundingReceipt` documenting citation precision, citation recall, hallucination rate, and abstention rate.
- **Deterministic Acceptance Commands:**
  ```powershell
  python benchmarks/run_synthesis_eval.py --manifest benchmarks/data/synthesis_eval_pack_v1.json --verify
  ```
- **Raw Evidence & Receipt Requirements:** Verifiable JSON receipt containing full prompt logs, model receipts, and byte-span citation matches.
- **Budgets:** Time: 2 hours. Tokens: 200K. Provider spend: $\le \$2.00$ (or local SLM). Storage: < 10 MB. Compute: Local CPU/GPU.
- **Fallback / Degraded Behavior:** Model abstains from answering if evidence is insufficient.
- **Stop Conditions & Escalation Owner:** Hallucinated fact without citation $\to$ Synthesis Specialist.
- **Rollback / Recovery Obligations:** None (read-only evaluation).
- **Claim Ceiling:** Synthesis Component Evidence (`C2`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Included in Gate `CAP-GE` Synthesis Component decision.

---

### Wave F: Repaired 1M Core Candidate

---

#### Node `CAP-SCALE01`: 1M Core Isolated Candidate & Diagnostics Ladder (Gate CAP-GF)

- **Lane / Workstream:** Scale / Core Platform (`SCALE-CORE`)
- **Objective:** Execute the honest 1,000,000-document Core scale qualification. Run diagnostics ladder (250K, 500K, 750K) before freezing the single 1M candidate. Measure:
  1. Append-only WAL Spine ingestion throughput ($\ge 500\text{ docs/sec}$).
  2. 100.0% byte-offset anchor recovery and $\Delta = 0$ repeat-erasure verification.
  3. Bit-exact replay parity from SQLite WAL logs across all 1M documents.
  4. Core storage amplification ($\le 2.5\times$ raw text).
  5. Zero LLM calls in this run; unconfounded by Cortex background processing.
- **Explicit Non-goals:** Calling language models; claiming semantic self-organization.
- **Governing Decisions & Invariants:** `CAP-D001`, `CAP-D002`, `CAP-D004`, `CAP-D005`, `CAP-D009`, `CAP-D010`, `CAP-D012`.
- **Prerequisites & Typed Dependency Reason:** Verified `CAP-INT02` + Human 1M Core Run Authorization Decision (`HARD_HUMAN_AUTHORITY`).
- **Pinned Identities:** 1M document benchmark corpus; base commit pinned.
- **Allowed Mutation Paths & Mutation Authority:** Production candidate store `trace_1m_core.db`. Output: `docs/program/inbox/cap-scale01/1m_core_dossier.json`. Authority: Scale Operator (`SCALE-OP`).
- **Named Owner Role & Verifier Role:** Owner: Scale Operator. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Outputs:* `1MCoreScaleDossier` containing full WAL custody receipts, replay parity hashes, and storage accounting.
- **Deterministic Acceptance Commands:**
  ```powershell
  python benchmarks/run_1m_core_scale_gate.py --verify-all-invariants
  ```
- **Raw Evidence & Receipt Requirements:** Cryptographic WAL checksum, bit-exact replay attestation, disk space telemetry logs.
- **Budgets:** Time: 24 hours. Tokens: 0. Provider spend: $0.00. Storage: < 150 GB. Compute: Full machine (RTX 5050 + SSD).
- **Fallback / Degraded Behavior:** Abort run immediately if disk usage breaches 200 GB or WAL corruption is detected.
- **Stop Conditions & Escalation Owner:** Non-zero byte drift or crash unrecoverability $\to$ Human Owner.
- **Rollback / Recovery Obligations:** Purge candidate directory on failure.
- **Claim Ceiling:** 1M Core Scale Certification (`C4`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Triggers `CAP-VER-GF` (Gate `CAP-GF`).
  - *Following Human Approval of Gate CAP-GF:* Certifies `G1M-CORE`.

---

### Wave G: Optional 1M Cortex and Combined-System Gate

---

#### Node `CAP-SCALE02`: 1M Cortex Semantic Consolidation & Combined System Gate (Gate CAP-GG)

- **Lane / Workstream:** Scale / Cortex Platform (`SCALE-CORTEX`)
- **Objective:** Measure the cost, scalability, and utility of Cortex semantic organization against the stable 1M Core instance (or an immutable snapshot). Execute asynchronous background consolidation to the authorized coverage target (e.g. active topic set or sampled 100K window). Measure semantic coherence, multi-hop retrieval uplift, and separate Cortex storage/compute costs.
- **Explicit Non-goals:** Blocking Core queries during consolidation; retroactively certifying Core.
- **Governing Decisions & Invariants:** `CAP-D001`, `CAP-D003`, `CAP-D004`, `CAP-D006`, `CAP-D007`, `CAP-D009`, `CAP-D010`, `CAP-D012`.
- **Prerequisites & Typed Dependency Reason:** Verified `CAP-SCALE01` (Gate `CAP-GF` passed) + Human 1M Cortex Run Authorization Decision (`HARD_HUMAN_AUTHORITY`).
- **Pinned Identities:** Immutable 1M Core store from `CAP-SCALE01`; pinned local SLM.
- **Allowed Mutation Paths & Mutation Authority:** Projections database `trace_1m_cortex.db`. Output: `docs/program/inbox/cap-scale02/1m_cortex_dossier.json`. Authority: Scale Operator.
- **Named Owner Role & Verifier Role:** Owner: Scale Operator. Verifier: Codex Independent Verifier (`VERIF-INDEP`).
- **Inputs, Expected Outputs & Artifact Schemas:**
  - *Outputs:* `1MCortexDossier` recording consolidated coverage, holon count, proposition support ($\ge 95\%$), multi-hop nDCG uplift, and total energy/compute cost.
- **Deterministic Acceptance Commands:**
  ```powershell
  python benchmarks/run_1m_cortex_evaluation.py --verify-projections
  ```
- **Raw Evidence & Receipt Requirements:** Full projection manifest, detached validation receipts, and isolated resource telemetry.
- **Budgets:** Time: 48 hours. Tokens: 50M (Local SLM). Provider spend: $\le \$10.00$ (Teacher comparators only). Storage: < 30 GB (projections). Compute: Local GPU.
- **Fallback / Degraded Behavior:** Bounded consolidation pausing on thermal or resource limits; unconsolidated items remain searchable via Core retrieval.
- **Stop Conditions & Escalation Owner:** GPU thermal limit or unanchored projection rate $> 0.01\%$ $\to$ Coordinator.
- **Rollback / Recovery Obligations:** Drop derived projections table without affecting Core Spine.
- **Claim Ceiling:** 1M Cortex Certification (`C4`) & Combined Trace System Release (`C5`).
- **Successor Nodes Unlocked:**
  - *On Verified Completion:* Triggers `CAP-VER-GG` (Gate `CAP-GG`).
  - *Following Human Approval of Gate CAP-GG:* Authorizes Combined Promoted Claim for Project Trace.

---

### Independent Verification Node Family (`CAP-VER-*`)

---

#### Node `CAP-VER-GA`: Independent Verification of Wave A Governance Reconciliation

- **Lane / Workstream:** Verification (`VERIF-INDEP`)
- **Objective:** Independently audit Wave A reconciliation. Verify that `06_DECISION_LOG.md` contains signed `DEC-CAP-001`, that all 15 contradiction ledger entries are faithfully applied in canonical docs, and that `CONTROL_PLANE_LOCK.json` matches working tree digests exactly.
- **Prerequisites:** `CAP-A01`, `CAP-A02`, `CAP-A03`.
- **Allowed Mutation Paths:** Read-only verification. Output: `docs/program/inbox/cap-ver-ga/verification_receipt.json`.
- **Named Role:** Codex Independent Verifier (`VERIF-INDEP`).
- **Acceptance:** 100% hash verification pass; zero broken links.
- **Successor Unlocked:** Human Decision on Gate `CAP-GA`.

---

#### Node `CAP-VER-GB`: Independent Verification of Wave B Infrastructure & Contracts

- **Lane / Workstream:** Verification (`VERIF-INDEP`)
- **Objective:** Independently verify all Wave B code and test deliverables: fail-closed gateway exceptions, cost accounting accuracy, dense retrieval adapter restoration, RRF fusion performance, Cortex schemas, job recovery, and faithfulness validator tests.
- **Prerequisites:** `CAP-GW01`, `CAP-GW02`, `CAP-GW03`, `CAP-RET01`, `CAP-RET02`, `CAP-RET03`, `CAP-RET04`, `CAP-CRX01`, `CAP-CRX02`, `CAP-CRX03`, `CAP-JOB01`, `CAP-JOB02`, `CAP-EVAL01`, `CAP-EVAL02`, `CAP-EVAL03`.
- **Allowed Mutation Paths:** Read-only test execution from clean, detached worktree. Output: `docs/program/inbox/cap-ver-gb/verification_receipt.json`.
- **Named Role:** Codex Independent Verifier (`VERIF-INDEP`).
- **Acceptance:** All unit and integration test suites pass; 100% negative test pass; zero test skips on required assertions.
- **Successor Unlocked:** Human Decision on Gate `CAP-GB`.

---

#### Node `CAP-VER-GC`: Independent Verification of Wave C Model Bake-Off

- **Lane / Workstream:** Verification (`VERIF-INDEP`)
- **Objective:** Independently verify raw bake-off data, check prompt logs, verify detached faithfulness scores, and confirm Pareto frontier calculations.
- **Prerequisites:** `CAP-MOD01`, `CAP-MOD02`.
- **Allowed Mutation Paths:** Read-only audit. Output: `docs/program/inbox/cap-ver-gc/verification_receipt.json`.
- **Named Role:** Codex Independent Verifier (`VERIF-INDEP`).
- **Successor Unlocked:** Human Decision on Gate `CAP-GC`.

---

#### Node `CAP-VER-GD`: Independent Verification of Wave D 10K Shadow Cortex

- **Lane / Workstream:** Verification (`VERIF-INDEP`)
- **Objective:** Independently audit 10K shadow database, verify crash-recovery receipts, test projection rollback, and confirm zero orphan atoms.
- **Prerequisites:** `CAP-INT01`.
- **Allowed Mutation Paths:** Read-only audit. Output: `docs/program/inbox/cap-ver-gd/verification_receipt.json`.
- **Named Role:** Codex Independent Verifier (`VERIF-INDEP`).
- **Successor Unlocked:** Human Decision on Gate `CAP-GD`.

---

#### Node `CAP-VER-GE`: Independent Verification of Wave E 100K Paired Qualification

- **Lane / Workstream:** Verification (`VERIF-INDEP`)
- **Objective:** Independently verify separate scorecards for Core, Retrieval, and Cortex across all 100K evaluation corpora. Check statistical significance calculations and storage accounting.
- **Prerequisites:** `CAP-INT02`, `CAP-INT03`.
- **Allowed Mutation Paths:** Read-only audit. Output: `docs/program/inbox/cap-ver-ge/verification_receipt.json`.
- **Named Role:** Codex Independent Verifier (`VERIF-INDEP`).
- **Successor Unlocked:** Human Decision on Gate `CAP-GE`.

---

#### Node `CAP-VER-GF`: Independent Verification of Wave F 1M Core Scale Gate

- **Lane / Workstream:** Verification (`VERIF-INDEP`)
- **Objective:** Conduct forensic audit of 1M Core database: verify WAL byte custody, execute bit-exact replay audit, confirm $\Delta = 0$ repeat erasure, and verify storage multiplier $\le 2.5\times$.
- **Prerequisites:** `CAP-SCALE01`.
- **Allowed Mutation Paths:** Read-only audit. Output: `docs/program/inbox/cap-ver-gf/verification_receipt.json`.
- **Named Role:** Codex Independent Verifier (`VERIF-INDEP`).
- **Successor Unlocked:** Human Gate `CAP-GF` (G1M-CORE Certification).

---

#### Node `CAP-VER-GG`: Independent Verification of Wave G 1M Cortex & Combined Release

- **Lane / Workstream:** Verification (`VERIF-INDEP`)
- **Objective:** Independently audit 1M Cortex projections, evaluate multi-hop retrieval uplift, verify isolated resource ledgers, and audit synthesis citation grounding.
- **Prerequisites:** `CAP-SCALE02`.
- **Allowed Mutation Paths:** Read-only audit. Output: `docs/program/inbox/cap-ver-gg/verification_receipt.json`.
- **Named Role:** Codex Independent Verifier (`VERIF-INDEP`).
- **Successor Unlocked:** Human Gate `CAP-GG` (Combined System Release).
