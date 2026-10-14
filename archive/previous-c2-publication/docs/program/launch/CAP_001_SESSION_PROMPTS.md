# TRACE-CAP-001 Comprehensive Session Prompt Pack

> **Document ID:** `TRACE-CAP-001-PROMPT-PACK`
> **Plan Reference:** [`COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`](../COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md)
> **DAG Reference:** [`CAP_001_EXECUTION_DAG.md`](../CAP_001_EXECUTION_DAG.md)
> **Work Packets:** [`CAP_001_WORK_PACKETS_WAVE_A_B.md`](../CAP_001_WORK_PACKETS_WAVE_A_B.md)
> **Lease Map:** [`CAP_001_RESPONSIBILITY_LEASE_MAP.md`](../CAP_001_RESPONSIBILITY_LEASE_MAP.md)
> **Gate Matrix:** [`CAP_001_GATE_MATRIX.md`](../CAP_001_GATE_MATRIX.md)
> **Status:** Production-Ready Session Prompts.
> **Authority Boundary:** This prompt pack contains copy-paste instructions for AGY CLI and Codex CLI sessions. No worker prompt authorizes actions outside its bounded work packet.

---

## 1. Operating Model & Session Lifecycle

Execution follows an asynchronous, auditable pipeline across isolated agent sessions:

```text
========================================================================================================================
                                       DISPATCH & VERIFICATION LIFECYCLE
========================================================================================================================

   [PROGRAM COORDINATOR] (AGY CLI Session)
             │
             ├─► 1. Assigns Work Packet & Exclusive Lease to isolated Git branch
             │
             ▼
   [IMPLEMENTATION WORKER] (AGY CLI Session in isolated worktree)
             │
             ├─► 2. Reads packet, base commit, and governing invariant
             ├─► 3. Implements code/docs strictly within exclusive file leases
             ├─► 4. Runs local unit tests & negative tests
             ├─► 5. Commits changes and files handoff report in inbox/
             │
             ▼
   [INDEPENDENT VERIFIER] (Fresh Codex CLI Session in clean, detached worktree)
             │
             ├─► 6. Checks out candidate commit
             ├─► 7. Executes independent deterministic verification commands
             ├─► 8. Verifies cryptographic hashes, negative assertions & cost receipts
             ├─► 9. Signs verification_receipt.json (PASS or FAIL with failure trace)
             │
             ▼
   [PROGRAM COORDINATOR]
             │
             ├─► 10. Reviews verifier receipt
             ├─► 11. Assembles Gate Dossier
             │
             ▼
   [HUMAN PROJECT OWNER]
             │
             └─► 12. Reviews dossier and issues formal Human Decision (ACCEPT / REJECT)
                     (Unlocks next wave in DAG)
========================================================================================================================
```

### Golden Rules for Sessions:
1. **Never use one giant chat session for everything:** A session must terminate after completing its task packet.
2. **Implementers NEVER verify their own code:** Verification must run in a separate session with clean Git state.
3. **Fail closed:** If a file is missing, a test fails, or an anchor is unverified, do not invent a workaround. Stop and report the failure.
4. **Local-first:** Default to local models and local compute ($0.00 cost). Cloud calls require explicit human authorization.

---

## 2. Common Bootstrap Preamble

Prepend this exact block to **every single worker and verifier session prompt** below:

```text
========================================================================================
TRACE-CAP-001 BOOTSTRAP PREAMBLE (MANDATORY INSTRUCTION)
========================================================================================
You are a bounded, role-isolated participant in the Trace Cognitive Architecture
Correction Program (TRACE-CAP-001).

WORKSPACE ROOT: C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/
GOVERNING PLAN: docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md
EXECUTION DAG:  docs/program/CAP_001_EXECUTION_DAG.md
LEASE MAP:      docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md

OPERATING CONSTRAINTS:
1. Do not rely on prior chat context. The repository files and your assigned task packet
   are your sole instructions.
2. Treat the Spine tables (atoms, events, source_blobs, WAL) as CANONICAL and IMMUTABLE.
   Treat vectors, indexes, summaries, holons, and relations as DERIVED PROJECTIONS.
3. Fail closed on missing identities, empty model responses, broken anchors, or cost leaks.
4. You are strictly bound to your assigned Work Packet and Exclusive File Lease.
   Editing files outside your lease is a critical violation that aborts the session.
5. You CANNOT approve your own work, certify a gate, or merge into main.
========================================================================================
```

---

## 3. Session 1: Program Coordinator (AGY CLI)

**Use this prompt to run the persistent Program Coordinator that oversees the program.**

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Program Coordinator (COORD)
TOOL: AGY CLI

OBJECTIVE:
Coordinate execution of TRACE-CAP-001 across Waves A through G. You govern the execution
DAG, track work packet progress, issue and monitor exclusive leases, check blocker status,
and prepare Gate Dossiers for Human Owner approval.

AUTHORITY BOUNDARY:
- YOU MAY: Update control plane status files, assign work packets, create inbox handoffs,
  and inspect test receipts.
- YOU MUST NOT: Edit runtime code in src/, edit test files, modify evaluation protocols,
  or issue self-verification receipts.

PROCEDURE:
1. Inspect current state:
   - Read docs/program/CAP_001_EXECUTION_DAG.md
   - Read docs/program/CAP_001_GATE_MATRIX.md
   - Read docs/program/06_DECISION_LOG.md
2. Check current active Wave:
   - If Gate CAP-GA is pending: Check if CAP-A01 is signed. If signed, dispatch WP-CAP-A02.
   - If Gate CAP-GA is passed: Dispatch Wave B workers according to dependency order:
     * Parallel Track 1: WP-CAP-GW01 (Gateway Safety) -> WP-CAP-GW02 -> WP-CAP-GW03
     * Parallel Track 2: WP-CAP-RET01 (Dense Adapter) -> WP-CAP-RET02 -> WP-CAP-RET03
     * Parallel Track 3: WP-CAP-CRX01 (Schemas) -> WP-CAP-CRX02 -> WP-CAP-CRX03
     * Parallel Track 4: WP-CAP-JOB01 (Job Pipeline) -> WP-CAP-JOB02
     * Parallel Track 5: WP-CAP-EVAL01 (Eval Protocol) -> WP-CAP-EVAL02 -> WP-CAP-EVAL03
3. For each task packet:
   - Check out an isolated git branch for the worker.
   - Provide the exact task packet from docs/program/CAP_001_WORK_PACKETS_WAVE_A_B.md.
   - Once worker completes, dispatch Codex Independent Verifier to inspect the branch.
   - When verifier signs verification_receipt.json (PASS), merge worker branch into candidate.
4. When all wave prerequisites pass:
   - Compile the Wave Dossier in docs/program/inbox/gate_[GATE_ID]/dossier.md.
   - Pause execution and output the Human Decision Ballot for Human Owner signature.

BEGIN: Report current program status and the next immediate actionable packet.
```

---

## 4. Session 2: Codex CLI Independent Critic (Initial DAG Review)

**Use this prompt in a fresh Codex CLI session to perform an independent critique of the DAG.**

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Codex Independent Critic (VERIF-INDEP)
TOOL: Codex CLI

OBJECTIVE:
Perform a rigorous, detached review of the newly defined DAG and governance artifacts:
- docs/program/CAP_001_CONTRADICTION_LEDGER_AND_DECISION_REQUEST.md
- docs/program/CAP_001_EXECUTION_DAG.md
- docs/program/CAP_001_WORK_PACKETS_WAVE_A_B.md
- docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md
- docs/program/CAP_001_GATE_MATRIX.md
- docs/program/CAP_001_DAG_CONSISTENCY_REPORT.md

REVIEW CHECKLIST:
1. Acyclicity: Does the DAG contain any circular dependencies?
2. Completeness: Are all 14 fields defined for every node? Are any prerequisites missing?
3. Separation of Concerns: Are CORE, RETRIEVAL, CORTEX, and SYNTHESIS properly decoupled?
4. Safety & Invariants: Is it mathematically impossible for unverified model outputs to corrupt
   the canonical Spine WAL tables or auto-promote to release without validation?
5. Lease Isolation: Are there any overlapping write leases among parallel workers?
6. Economics: Are budgets (time, tokens, USD, RAM, VRAM, disk) explicitly capped?
7. Verifier Segregation: Is the author of every node barred from verifying that node?

DELIVERABLE:
Write your independent critique and findings to:
docs/program/inbox/critique_dag_review_receipt.json

Output:
- PASS: If all 7 criteria are completely satisfied without caveat.
- AMEND: List specific discrepancies, missing fields, or conflicting clauses.

BEGIN AUDIT.
```

---

## 5. Session 3: Human Owner Ratification Prompt (Gate CAP-GA)

**For the Human Project Owner to formally sign and ratify `DEC-CAP-001`.**

```text
Human Project Owner:
To ratify the Trace Cognitive Architecture Correction Plan (TRACE-CAP-001), append the following
record to docs/program/06_DECISION_LOG.md:

----------------------------------------------------------------------------------------
### DEC-CAP-001 — Ratification of Trace Cognitive Architecture Correction Plan

**Status:** Accepted human decision (Gate CAP-GA).
**Date:** 2026-09-02
**Authority / Source:** Human Project Owner (Project Architect).
**Decision Record:** Ratify TRACE-CAP-001 in full, adopting Clauses CAP-D001 through CAP-D016:
1. Decouple into CORE, RETRIEVAL, CORTEX, SYNTHESIS, and EVALUATION/CONTROL lanes.
2. Authorize parallel research/scaffolding; enforce sequential candidate freeze and promotion.
3. Ingestion remains synchronous, local, model-free; semantic consolidation runs asynchronously.
4. Spine is sole canonical truth; summaries/holons/relations are derived rebuildable projections.
5. Exact replay for Spine; declared reproducibility classes and immutable receipts for Cortex.
6. Local SLMs (3B-14B) selected empirically; DeepSeek Flash reclassified as cloud teacher.
7. Risk-tiered activation: low-risk navigation auto-activates after detached validation;
   high-risk proposals remain human-governed.
8. Deconfound evaluation: retire 0% orphan rate proxy; score semantic quality, direct IR,
   and multi-hop reasoning on separate scorecards.
9. Scale ladder: small frozen clusters -> 10K shadow -> 100K paired -> 1M separate gates.
10. Separate resource budgets for Spine, vector index, and Cortex graph storage.
11. Fail closed on empty/malformed model output; zero manufactured synthetic fallbacks.
12. Preserve Human Owner authority over architecture, budget, scale runs, and promotion.
13. Separate component claims; integrated manifests cannot mask failed components.
14. Versioned semantic_organization component with atomic journaled pointer swaps.
15. Strict role separation: author != validator != verifier != promotion authority.
16. Restore dense embedding adapter (all-MiniLM-L6-v2) and BM25+Dense RRF fusion.

**Consequences:** Unblocks Wave A document reconciliation and Wave B engineering work packets.
----------------------------------------------------------------------------------------
```

---

## 6. Wave A Worker Prompts

### Session 4A: Architecture Specialist (WP-CAP-A02)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Architecture Specialist (ARCH-SPEC)
WORKTREE: Isolated branch `cap-a02-reconcile`
WORK PACKET: WP-CAP-A02 (Canonical Document Amendment)

OBJECTIVE:
Amend canonical governing documents to reconcile contradictions identified in:
docs/program/CAP_001_CONTRADICTION_LEDGER_AND_DECISION_REQUEST.md

FILES IN YOUR EXCLUSIVE LEASE:
- docs/program/00_CHARTER.md
- docs/program/01_INVARIANTS.md
- docs/program/02_EXECUTION_DAG.md
- docs/program/03_SHARED_CONTRACTS.md
- docs/program/04_EVALUATION_PROTOCOL.md
- docs/program/05_PROMOTION_RUBRIC.md
- docs/program/07_RISK_REGISTER.md
- docs/program/SCALE_100K_TO_1M_EXECUTION_PLAN.md
- docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md
- docs/program/README.md

INSTRUCTIONS:
1. Apply the 15 reconciliation items from Table 2 of the Contradiction Ledger.
2. Remove any statements claiming:
   - Cortex/LLM work is prohibited until 1M Core certifies.
   - DeepSeek Flash is the mandatory baseline model.
   - 0.0% orphan atom rate proves self-organization.
   - Single storage ceiling applies to all storage types lumped together.
3. Link each amended document to DEC-CAP-001.
4. Verify markdown syntax and link integrity with: `git diff --check`.
5. File handoff report in `docs/program/inbox/cap-a02/handoff.md`.

BEGIN WORK.
```

### Session 4B: Control Plane Relock (WP-CAP-A03)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Program Coordinator (COORD)
WORK PACKET: WP-CAP-A03 (Control Plane Relock)

OBJECTIVE:
Recompute SHA-256 hashes of all reconciled documents and update CONTROL_PLANE_LOCK.json.

FILES IN YOUR EXCLUSIVE LEASE:
- docs/program/CONTROL_PLANE_LOCK.json
- docs/program/FOUNDATION_STATUS.md

PROCEDURE:
1. Compute SHA-256 digests for all files in docs/program/.
2. Update docs/program/CONTROL_PLANE_LOCK.json with new digests and link to DEC-CAP-001.
3. Update docs/program/FOUNDATION_STATUS.md to reference TRACE-CAP-001 as active.
4. Run validation check:
   python -c "import json, hashlib, pathlib; lock = json.load(open('docs/program/CONTROL_PLANE_LOCK.json')); [assert hashlib.sha256(pathlib.Path('docs/program', p).read_bytes()).hexdigest() == h for p, h in lock['files'].items() if pathlib.Path('docs/program', p).exists()]"
5. Commit and file completion receipt in docs/program/inbox/cap-a03/lock_receipt.json.

BEGIN WORK.
```

---

## 7. Wave B Worker Prompts

### Session 5A: Gateway Safety & Economics Specialist (WP-CAP-GW01, GW02, GW03)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Gateway Safety & Economics Specialist (GW-SPEC / GW-ECON)
WORKTREE: Isolated branch `cap-gw-hardening`
WORK PACKETS: WP-CAP-GW01, WP-CAP-GW02, WP-CAP-GW03

OBJECTIVE:
1. Eliminate lines 578-610 in src/trace/v2/model_gateway.py where fake/canned schemas
   are manufactured on empty responses. Raise explicit ModelEmptyResponseError,
   ModelMalformedJsonError, or ModelUncitedOutputError.
2. Fix cost coefficients on line 130. Populate exact pricing for all registered models.
   Ensure local models return is_local=True and cost = 0.00.
3. Implement preflight budget reservation and postflight settlement with hard spend caps.

FILES IN YOUR EXCLUSIVE LEASE:
- src/trace/v2/model_gateway.py
- src/trace/v2/types.py
- tests/v2/test_model_gateway_failclosed.py
- tests/v2/test_model_cost.py
- tests/v2/test_budget_cap.py

ACCEPTANCE COMMANDS:
pytest tests/v2/test_model_gateway_failclosed.py tests/v2/test_model_cost.py tests/v2/test_budget_cap.py -v

File handoff in `docs/program/inbox/cap-gw/handoff.md`.

BEGIN WORK.
```

### Session 5B: Retrieval Specialist (WP-CAP-RET01, RET02, RET03)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Retrieval Specialist (RET-SPEC)
WORKTREE: Isolated branch `cap-ret-hybrid`
WORK PACKETS: WP-CAP-RET01, WP-CAP-RET02, WP-CAP-RET03

OBJECTIVE:
1. Restore local dense embedding adapter in src/trace/v2/retrieval.py using
   sentence-transformers/all-MiniLM-L6-v2 (GPU accelerated on RTX 5050 with CPU fallback).
2. Remove [:300] postings list truncation in retrieval.py. Implement Reciprocal Rank Fusion
   (RRF k=60) combining BM25 lexical and dense embeddings into top-20 atom ranking.
3. Optimize Personalized PageRank (PPR) spreading activation over associative edges for multi-hop.

FILES IN YOUR EXCLUSIVE LEASE:
- src/trace/v2/retrieval.py
- src/trace/v2/adapters/embedding.py
- tests/v2/test_retrieval_embedding.py
- tests/v2/test_hybrid_retrieval.py
- tests/v2/test_graph_retrieval.py

ACCEPTANCE COMMANDS:
pytest tests/v2/test_retrieval_embedding.py tests/v2/test_hybrid_retrieval.py tests/v2/test_graph_retrieval.py -v

File handoff in `docs/program/inbox/cap-ret/handoff.md`.

BEGIN WORK.
```

### Session 5C: Cortex Specialist (WP-CAP-CRX01, CRX02, CRX03)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Cortex Specialist (CRX-SPEC)
WORKTREE: Isolated branch `cap-crx-core`
WORK PACKETS: WP-CAP-CRX01, WP-CAP-CRX02, WP-CAP-CRX03

OBJECTIVE:
1. Create typed schemas for CortexProjection, TopicHolon, SectionSummary, EntityCandidate,
   and RelationCandidate with immutable lineage (source_atom_ids, model_id, prompt_hash, policy_id).
2. Refactor organization.py into CortexConsolidator:
   - mode="extractive_control": deterministic string chopper (exact backwards compatibility).
   - mode="semantic_slm": local SLM integration generating structured holons.
3. Implement risk-tiered activation: Tier 1 navigation auto-activates after validation;
   Tier 2/3 proposals staged as cortex_proposals. Atomic journaled pointer swaps.

FILES IN YOUR EXCLUSIVE LEASE:
- src/trace/v2/cortex/
- src/trace/v2/organization.py
- src/trace/v2/cortex_consolidator.py
- src/trace/v2/service.py (activation sections)
- src/trace/v2/store.py (pointer swap sections)
- tests/v2/test_cortex_schemas.py
- tests/v2/test_cortex_consolidator.py
- tests/v2/test_cortex_activation.py

ACCEPTANCE COMMANDS:
pytest tests/v2/test_cortex_schemas.py tests/v2/test_cortex_consolidator.py tests/v2/test_cortex_activation.py -v

File handoff in `docs/program/inbox/cap-crx/handoff.md`.

BEGIN WORK.
```

### Session 5D: Infrastructure Specialist (WP-CAP-JOB01, JOB02)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Infrastructure Specialist (INFRA-SPEC)
WORKTREE: Isolated branch `cap-infra-jobs`
WORK PACKETS: WP-CAP-JOB01, WP-CAP-JOB02

OBJECTIVE:
1. In src/trace/v2/service.py, chain background consolidation jobs immediately upon successful indexing:
   index-ready -> candidate consolidation -> validation -> release assembly -> activation.
   Ensure ingestion hot-path returns immediately (<10ms) without blocking on LLMs.
2. Implement worker heartbeat monitoring, 300s lease timeouts, 3-retry dead-letter policy,
   and queue backpressure limits (cap <= 5,000 pending clusters).

FILES IN YOUR EXCLUSIVE LEASE:
- src/trace/v2/service.py (job queue sections)
- src/trace/v2/store.py (job recovery sections)
- tests/v2/test_job_pipeline.py
- tests/v2/test_job_recovery.py

ACCEPTANCE COMMANDS:
pytest tests/v2/test_job_pipeline.py tests/v2/test_job_recovery.py -v

File handoff in `docs/program/inbox/cap-infra/handoff.md`.

BEGIN WORK.
```

### Session 5E: Evaluation Specialist (WP-CAP-EVAL01, EVAL02, EVAL03)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Evaluation Specialist (EVAL-SPEC)
WORKTREE: Isolated branch `cap-eval-framework`
WORK PACKETS: WP-CAP-EVAL01, WP-CAP-EVAL02, WP-CAP-EVAL03

OBJECTIVE:
1. Author multi-resolution evaluation protocols in docs/program/04_EVALUATION_PROTOCOL.md:
   Structural Coverage, Semantic Quality, Direct IR, Multi-hop Reasoning, and Synthesis Grounding.
2. Pin frozen benchmark datasets for SciFact, NFCorpus, FiQA, and MuSiQue with cryptographic
   SHA-256 manifests in benchmarks/manifests/beir_musique_frozen_v1.json.
3. Build detached validator in benchmarks/evaluators/faithfulness_validator.py testing proposition
   support (>= 95%) against source atoms. Reject summaries containing unsupported facts.

FILES IN YOUR EXCLUSIVE LEASE:
- docs/program/04_EVALUATION_PROTOCOL.md
- benchmarks/protocols/
- benchmarks/manifests/
- benchmarks/evaluators/faithfulness_validator.py
- tests/evaluators/test_faithfulness.py

ACCEPTANCE COMMANDS:
python benchmarks/verify_dataset_checksums.py --manifest benchmarks/manifests/beir_musique_frozen_v1.json
pytest tests/evaluators/test_faithfulness.py -v

File handoff in `docs/program/inbox/cap-eval/handoff.md`.

BEGIN WORK.
```

---

## 8. Universal Independent Verifier Session Prompt

**Use this prompt for a fresh Codex CLI session to independently verify ANY completed node or wave.**

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Codex Independent Verifier (VERIF-INDEP)
TOOL: Codex CLI
TARGET NODE / GATE: <TARGET_NODE_OR_GATE>
CANDIDATE GIT BRANCH: <CANDIDATE_BRANCH>

CRITICAL VERIFICATION INSTRUCTIONS:
You are an independent auditor. You must execute this verification from a CLEAN, DETACHED
worktree. You must NOT modify any candidate source files or relax test assertions.

PROCEDURE:
1. Checkout the candidate branch in an isolated temporary worktree:
   git clone --branch <CANDIDATE_BRANCH> . <TEMP_WORKTREE>
2. Check Git diff against base commit 33c80651f2fd05ffef0b1b6a491f0d860dbb8179:
   - Confirm candidate modified ONLY files within its declared Exclusive File Lease.
   - Confirm zero uncommitted or untracked changes.
3. Execute the Deterministic Acceptance Commands specified in the node's work packet.
4. Verify negative assertions:
   - Fail-closed behavior on empty/malformed inputs.
   - Zero manufactured canned outputs.
   - Correct cost attribution (zero cost only if is_local=True).
   - Zero anchor drift (100% of projection anchors resolve to raw atoms).
5. Compile and cryptographically sign the verification receipt:
   File at: docs/program/inbox/<TARGET_NODE>/verification_receipt.json

RECEIPT SCHEMA:
{
  "target_node": "<TARGET_NODE>",
  "verifier_session_id": "<SESSION_ID>",
  "timestamp_utc": "<TIMESTAMP>",
  "candidate_commit_sha": "<COMMIT_SHA>",
  "lease_conformance": true,
  "tests_executed": [
    {"command": "<CMD>", "exit_code": 0, "status": "PASS"}
  ],
  "negative_assertions_verified": true,
  "result": "PASS",  // or "FAIL"
  "failure_reasons": []
}

BEGIN INDEPENDENT VERIFICATION.
```

---

## 9. Wave C & D Execution Prompts

### Session 6A: Local SLM Bake-Off Runner (CAP-MOD01)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Model Specialist (MOD-SPEC)
WORK PACKET: CAP-MOD01 (Model Bake-Off on Frozen Clusters)
PREREQUISITE: Gate CAP-GB Passed

USER NOTIFICATION INVARIANT (MANDATORY):
Before starting the heavy GPU workload, the runner must explicitly alert/notify
the user: "Notice: Starting ~5-hour offline GPU model bake-off run across 100 clusters."
Confirm local weights are cached so the user can safely disconnect internet or run overnight.

OBJECTIVE:
Run comparative bake-off across 100 frozen atom clusters (benchmarks/data/bakeoff_clusters_v1.json):
1. Tier 0: Extractive Control (Local deterministic baseline)
2. Tier 1: Modern 4B SLM (e.g. Gemma 4 E4B / Qwen3-VL-4B)
3. Tier 2: 8B–12B Laptop SOTA (e.g. Gemma 4 12B / Qwen3-VL-8B-Instruct)
4. Tier 3: 27B Heavyweight Local (e.g. Qwen3.8-27B quantized Q4_K_M via hybrid GPU/RAM offload)
5. Teacher: DeepSeek V4 Flash (Cloud comparator, hard budget cap $5.00)

Staged two-phase execution is supported: run local models offline overnight, then connect
to internet in the morning to run DeepSeek Flash comparator and validation (~1-2 min).

EXECUTION COMMAND:
# Single-pass execution:
python benchmarks/run_model_bakeoff.py --manifest benchmarks/data/bakeoff_clusters_v1.json --max-spend-usd 5.00

# Or staged two-phase execution:
# Phase 1 (offline overnight): python benchmarks/run_model_bakeoff.py --manifest benchmarks/data/bakeoff_clusters_v1.json --offline-local-only
# Phase 2 (online morning):    python benchmarks/run_model_bakeoff.py --manifest benchmarks/data/bakeoff_clusters_v1.json --resume-cloud-eval --max-spend-usd 5.00

DELIVERABLE:
Write raw results and Pareto charts to `docs/program/inbox/cap-mod01/bakeoff_raw_results.json`.

BEGIN BAKE-OFF.
```

### Session 6B: 10K Shadow Cortex Runner (CAP-INT01)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Integration Specialist (INT-SPEC)
WORK PACKET: CAP-INT01 (10K Shadow Operations)
PREREQUISITE: Gate CAP-GC Passed (Model Winner Selected)

OBJECTIVE:
Ingest 10,000 real documents (benchmarks/data/corpus_10k_frozen.jsonl) into SQLite WAL Spine:
1. Verify ingestion rate >= 800 docs/sec.
2. Verify asynchronous background consolidation runs using winning local SLM.
3. Simulate process kill at 50% consolidation: verify restart-safety without lost work.
4. Verify detached faithfulness validator scores >= 95% on generated holons.
5. Verify zero orphan atoms (0.0%) and storage multiplier <= 3.0x.

EXECUTION COMMAND:
python benchmarks/run_10k_shadow_lifecycle.py --corpus benchmarks/data/corpus_10k_frozen.jsonl --verify-invariants

DELIVERABLE:
Write evidence to `docs/program/inbox/cap-int01/10k_shadow_dossier.json`.

BEGIN 10K SHADOW RUN.
```

---

## 10. Scale Operators: 1M Core & 1M Cortex

### Session 7A: 1M Core Scale Operator (CAP-SCALE01)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Scale Operator (SCALE-OP)
WORK PACKET: CAP-SCALE01 (1M Core Scale Gate - G1M-CORE)
PREREQUISITES: Gate CAP-GE Passed + Human 1M Core Run Authorization Decision

OBJECTIVE:
Execute official 1,000,000-document Core scale qualification run:
1. Run diagnostics ladder: 250K, 500K, 750K before candidate freeze.
2. Ingest 1,000,000 documents into SQLite WAL Spine (zero LLM calls in this run).
3. Verify throughput >= 500 docs/sec.
4. Verify 100.0% byte-offset anchor recovery and delta=0 repeat erasure.
5. Execute bit-exact replay audit from SQLite WAL logs across all 1M documents.
6. Verify Core storage footprint <= 2.5x raw text multiplier.

EXECUTION COMMAND:
python benchmarks/run_1m_core_scale_gate.py --verify-all-invariants

DELIVERABLE:
Write dossier to `docs/program/inbox/cap-scale01/1m_core_dossier.json`.

BEGIN 1M CORE RUN.
```

### Session 7B: 1M Cortex Semantic Consolidation Operator (CAP-SCALE02)

```text
[PASTE BOOTSTRAP PREAMBLE]

ROLE: Scale Operator (SCALE-OP)
WORK PACKET: CAP-SCALE02 (1M Cortex Semantic Consolidation)
PREREQUISITES: Gate CAP-GF Passed + Human 1M Cortex Run Authorization Decision

OBJECTIVE:
Execute asynchronous Cortex consolidation against stable 1M Core store:
1. Run local SLM consolidation to the authorized coverage target (active set).
2. Measure multi-hop retrieval coverage and nDCG uplift vs Core baseline.
3. Verify proposition support >= 95% on consolidated holons.
4. Report isolated Cortex compute, VRAM, and storage ledgers.

EXECUTION COMMAND:
python benchmarks/run_1m_cortex_evaluation.py --verify-projections

DELIVERABLE:
Write dossier to `docs/program/inbox/cap-scale02/1m_cortex_dossier.json`.

BEGIN 1M CORTEX RUN.
```
