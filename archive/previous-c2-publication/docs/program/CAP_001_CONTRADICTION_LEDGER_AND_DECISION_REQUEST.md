# TRACE-CAP-001 Contradiction Ledger & Human Owner Decision Request

> **Document ID:** `TRACE-CAP-001-LEDGER`
> **Plan Reference:** [`COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`](COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md)
> **Status:** Proposed Governance Amendment pending Human Owner Ratification (`CAP-GA`).
> **Date:** 2026-09-02
> **Governing Boundary:** Pure documentation and governance control plane. Authorizes zero code execution, zero provider spend, zero model downloads, zero scale runs.

---

## 1. Executive Summary & Purpose

During scale qualification at 100K and preparation for 1M documents, Trace experienced severe benchmark stalls and engineering deadlocks. The root cause was an AI-driven over-correction following forensic quarantine:
1. **Certification Order Confounded with Engineering Order:** The program dictated that no model-assisted organization or Cortex research could begin until the unassisted 1M Core completely qualified. This halted all cognitive research and forced engineers to spend months tuning low-level data plane mechanics without exercising the intended cognitive layer.
2. **Cognitive Amputation:** Self-organization in `src/trace/v2/organization.py` was reduced to concatenating truncated string excerpts with pipe characters (`|`), while passing "0.0% orphan atoms" and "87% routing purity" was falsely treated as proof that self-organization was solved.
3. **Monolithic Release Coupling:** Retrieval quality across disparate tasks (direct passage IR vs multi-hop reasoning), storage economics, sub-20ms interactive latency, and generative synthesis were lumped into a single unpassable release gate (`DEC-P-005`).

Plan [`TRACE-CAP-001`](COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md) resolves these deadlocks by establishing four distinct capability and claim lanes:
- **CORE:** Append-only WAL Spine, exact byte offsets, immutable event history, deterministic rebuildability, and recovery.
- **RETRIEVAL:** Pinned dense neural embeddings (e.g. `all-MiniLM-L6-v2`), BM25 lexical search, Reciprocal Rank Fusion (RRF), and graph traversal (PPR) returning raw source atoms in under 20ms.
- **CORTEX:** Asynchronous background semantic consolidation ("sleep phase"), local SLM topic holon synthesis, entity extraction, and relational edge proposals stored strictly in derived, revisioned, rebuildable projections.
- **SYNTHESIS:** Query-time answer generation grounded strictly in retrieved source atoms with byte-exact citations.

This document identifies every active document clause contradicting this corrected architecture and presents the formal Human Owner Decision Request to ratify Decisions `CAP-D001` through `CAP-D016`.

---

## 2. Contradiction Ledger

The following active governing documents contain clauses that conflict with `TRACE-CAP-001`. Each entry details the file, location, existing clause, failure mode, and approved prospective correction.

| Ref | Document & Location | Current Stale / Contradictory Clause | Hazard & Failure Mode | Corrected Governing Clause |
|---|---|---|---|---|
| **C-01** | `docs/program/00_CHARTER.md`<br>Lines 14–28 | Defines Trace solely as an append-only event-sourced database with deterministic graph indexing; omits semantic condensation and cognitive architecture from mission. | Prevents engineers from allocating effort to semantic consolidation; justifies reducing summarization to string clipping. | Amend charter to define Trace as a dual-system cognitive memory database: a fast, model-free Hippocampal Spine coupled with an asynchronous, model-assisted Neocortex for multi-resolution semantic organization. |
| **C-02** | `docs/program/01_INVARIANTS.md`<br>Lines 8–24 | Requires byte-exact replay parity across all system projections without distinguishing deterministic indices from generative projections. | Impossible for language model outputs across differing hardware, runtimes, or quantization, forcing either total prohibition of LLMs or faked deterministic fallbacks. | Spine and deterministic indices require 100% bit-exact replay. Generative projections require immutable input/prompt/model receipts, declared reproducibility classes, and permanent lineage anchors. |
| **C-03** | `docs/program/02_EXECUTION_DAG.md`<br>Lines 9–16, 94–104 | Stage 3 blocks all broad architecture research, cognitive models, and speculative retrieval until full Foundation Complete certification. | Freezes Cortex engineering until Core certifies, preventing parallel development of the cognitive consolidation pipeline. | Scaffolding, safety hardening, model bake-offs, and 10K/100K shadow Cortex research may proceed in parallel; only the promoted combined 1M release claim remains sequential. |
| **C-04** | `docs/program/03_SHARED_CONTRACTS.md`<br>Lines 122–160 | Lacks typed candidate projection contracts, model/prompt lineage schemas, validation receipt structures, and asynchronous consolidation job error stages. | Workers manufacture ad-hoc JSON structures or invent pass metadata, allowing unvalidated model outputs to bypass verification. | Establish first-class schemas for `CandidateProjection`, `SemanticOrganizationManifest`, `ModelInvocationReceipt`, `ValidationReceipt`, and `PromotionReceipt`. |
| **C-05** | `docs/program/04_EVALUATION_PROTOCOL.md`<br>Lines 45–82 | Evaluates self-organization exclusively through topological proxies (orphan atom rate = 0.0%, routing purity $\ge 85\%$). | Measures assignment hygiene only; permits meaningless pipe-concatenated strings to pass as "CANDIDATE_COMPLETE". | Introduce semantic organization scorecards: semantic coherence, proposition support / faithfulness ($\ge 95\%$), relation precision/recall, and navigation utility. |
| **C-06** | `docs/program/05_PROMOTION_RUBRIC.md`<br>Lines 30–65 | Requires manual human review of every proposal before activation; lacks risk-tiered activation policies. | Human review bottleneck breaks at 100K/1M scale, choking the system or leading to blanket unreviewed auto-approvals. | Establish risk-tiered activation: low-risk derived navigation summaries can auto-activate following detached validation; high-risk factual/schema proposals require explicit approval. |
| **C-07** | `docs/program/06_DECISION_LOG.md`<br>DEC-003, Lines 34–40 | Mandates DeepSeek Flash as the canonical baseline model for all model tasks. | Imposes cloud API dependency, high costs ($200–$1500 per 1M run), network latency, and privacy leakage; blocks local SLMs (3B–14B). | DeepSeek Flash is reclassified as a cloud teacher and upper-bound comparator. Production models are chosen empirically via a frozen local SLM bake-off. |
| **C-08** | `docs/program/06_DECISION_LOG.md`<br>DEC-P-005, Lines 248–264 | Release Gate 2 uses only structural proxies; Release Gate 3 & 4 lump direct IR, multi-hop, sub-20ms latency, and $\le 3.0\times$ storage into a single release gate. | Conflates passage retrieval failure with model failure; treats storage ratio without separating Spine, retrieval vectors, and Cortex graphs. | Decompose into lane-specific gates: Gate 1 (Spine), Gate 2 (Retrieval: BM25+Dense RRF), Gate 3 (Cortex: Semantic Consolidation), Gate 4 (Synthesis), with separate storage and latency budgets. |
| **C-09** | `docs/program/07_RISK_REGISTER.md`<br>Lines 25–70 | Contains zero entries for model hallucination, semantic drift, provider drift, consolidation debt, or evaluation leakage. | Project operates without mitigation runbooks or stop conditions for generative cognitive failure modes. | Add material risks R-COG-01 through R-COG-06 with explicit stop conditions and rollbacks (Section 16 of `TRACE-CAP-001`). |
| **C-10** | `docs/program/SCALE_100K_TO_1M_EXECUTION_PLAN.md`<br>Lines 20–32, 443–464 | Establishes strictly sequential G1M-CORE -> G1M-HYBRID and treats all LLM work as downstream answer synthesis after 1M Core qualification. | Bans Cortex consolidation from being developed, measured, or integrated on 10K/100K corpora prior to 1M Core completion. | Scope sequentiality strictly to final combined marketing/release claims. Authorize parallel Core and Cortex tracks through 10K/100K. |
| **C-11** | `docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md`<br>Lines 210–215, 332–354 | Quarantines all hybrid runners under R0-02 without providing an authorized path for local SLM consolidation or hybrid retrieval adapters. | Prevents enabling dense embeddings in the 100K runner, causing artificial failures on BEIR SciFact/NFCorpus/FiQA. | Clarify R0-02 to quarantine only unanchored in-memory synthetic loops. Authorize persistent dense embedding adapters (MiniLM) and local SLM consolidation. |
| **C-12** | `docs/program/FOUNDATION_STATUS.md`<br>Lines 14–54 | Stale status claiming Foundation Gate pass based on proxy metrics; conflicts with subsequent Wave R2.1–R2.6 findings. | Confuses agents regarding active program baseline and foundation status. | Supersede with accurate status pointer to `TRACE-CAP-001` and current control plane state. |
| **C-13** | `docs/program/CONTROL_PLANE_LOCK.json`<br>Lines 3–14, 79 | Lockfile has stale SHA-256 digests for `06_DECISION_LOG.md`, `README.md`, etc., and cites unrecorded "Human Gate D". | Automated preflight validation fails or references non-existent authority. | Relock control plane with fresh SHA-256 digests following acceptance of this decision request. |
| **C-14** | `src/trace/v2/organization.py`<br>Lines 22–29, 58–70 | Implementation truncates text to 180 chars and pipes them together; validator accepts 5% token overlap as complete pass. | Generates nonsensical hierarchies; validation passes invalid text and rejects legitimate semantic paraphrases. | Replace string chopper with asynchronous local SLM consolidator; replace 5% overlap check with proposition support and anchor verification. |
| **C-15** | `src/trace/v2/model_gateway.py`<br>Lines 130, 578–610 | Manufactures fake schemas/renderings on empty model response; cost coefficients default to zero. | Fails to fail-closed on model errors; budget enforcement cannot be trusted for scale runs. | Implement strict fail-closed semantics on empty/malformed responses; require non-zero cost coefficients and explicit local vs cloud attribution. |

---

## 3. Human Owner Decision Request (`DEC-CAP-001`)

```text
========================================================================================
FORMAL HUMAN OWNER DECISION REQUEST: TRACE-CAP-001 RATIFICATION
========================================================================================
ID:           DEC-CAP-001
Date:         2026-09-02
Authority:    Human Project Owner (Project Architect)
Subject:      Adoption of Trace Cognitive Architecture Correction Plan (TRACE-CAP-001)
Status:       PENDING HUMAN RATIFICATION (Gate CAP-GA)
========================================================================================
```

### Proposed Decision Clauses for Immediate Ratification

By approving this decision request, the Human Owner formally ratifies the following 16 binding architectural decisions (`CAP-D001` through `CAP-D016`):

1. **`CAP-D001` (Capability & Claim Lanes):** Formally decouple system architecture into five distinct lanes:
   - `CORE`: Append-only Spine, event sourcing, byte anchors, replayability.
   - `RETRIEVAL`: Multi-modal search (BM25, dense embeddings, RRF, PPR graph walk) returning raw source atoms.
   - `CORTEX`: Asynchronous semantic consolidation, topic holons, schema induction, relational edge proposals.
   - `SYNTHESIS`: Grounded answer generation from retrieved evidence atoms.
   - `EVALUATION & CONTROL`: Frozen benchmarks, independent verification, and human promotion gates.
2. **`CAP-D002` (Parallel Construction vs. Sequential Claims):** Authorize parallel research, scaffolding, safety repairs, and evaluators across all lanes. Enforce sequential candidate freeze, verification, and promotion. Prohibit a Cortex result from repairing a failed Core result.
3. **`CAP-D003` (Decoupled Asynchronous Consolidation):** Ingestion remains strictly synchronous, local, model-free, and high-throughput ($\ge 800\text{ docs/sec}$). Generative semantic consolidation runs asynchronously in the background ("sleep phase") over bounded changed neighborhoods.
4. **`CAP-D004` (Spine vs. Projection Boundary):** The Spine is the sole canonical source of truth. All summaries, entities, claims, topics, and relations generated by language models are strictly derived, revisioned, rebuildable projections stored in `derived_nodes` and `cortex_projections`. Dropping projections never corrupts the Spine.
5. **`CAP-D005` (Replay & Reproducibility):** Exact bit-for-bit replay is mandatory for Spine data and deterministic indexes. Generative projections require declared reproducibility classes, immutable prompt/model/runtime receipts, and permanent lineage anchors.
6. **`CAP-D006` (Empirical Model Selection):** Revoke DeepSeek Flash as the mandatory baseline. Model selection is empirical via frozen bake-offs among local SLMs (3B–14B) running locally at $0 API cost. Cloud models serve strictly as teachers and upper-bound comparators.
7. **`CAP-D007` (Risk-Tiered Activation):** Projections are classified into risk tiers. Low-risk derived navigation summaries auto-activate inside approved profiles after detached validation. High-risk factual assertions and schema modifications remain explicit proposals requiring review.
8. **`CAP-D008` (Deconfounded Evaluation Protocols):** Retire topological proxies (0% orphan rate) as proof of semantic organization. Evaluate structural coverage, semantic condensation faithfulness ($\ge 95\%$), direct IR, multi-hop reasoning, and answer synthesis on separate scorecards.
9. **`CAP-D009` (Scale Ladder Admission):** Prohibit using 1M document runs as an inner tuning loop. Cognitive mechanisms must earn admission through small frozen clusters $\to$ 10K shadow runs $\to$ 100K paired qualifications before 1M eligibility.
10. **`CAP-D010` (Separate Resource Budgets):** Resource budgets and storage amplification ceilings must be accounted separately for Spine storage, retrieval vector/lexical indices, and Cortex semantic graphs, alongside total-system footprint.
11. **`CAP-D011` (Fail-Closed Execution):** Model gateways, schema parsers, and projection validators must fail closed on missing models, empty responses, malformed JSON, missing anchors, or unrecorded costs. Manufacturing synthetic responses is strictly prohibited.
12. **`CAP-D012` (Human Authority Boundary):** Explicit Human Owner approval is mandatory for architectural changes, threshold modifications, provider spend, credentials, scale run launches, and release promotions. Readiness never grants authority by itself.
13. **`CAP-D013` (Component Claims Integrity):** Component releases are issued and certified separately. An integrated manifest cannot mask or upgrade a failed component claim.
14. **`CAP-D014` (Semantic Organization Component):** Establish a versioned `semantic_organization` release component binding topic holons, section summaries, entity graphs, and schema proposals into a coherent release manifest with atomic activation and rollback.
15. **`CAP-D015` (Separation of Roles):** Candidate authorship, validator authority, activation authority, independent verification, and promotion authority must be held by separate agents/sessions. Implementers are strictly barred from verifying their own outputs.
16. **`CAP-D016` (Retrieval Baseline Restoration):** Restore dense neural embedding adapters (`all-MiniLM-L6-v2`) and BM25+Dense Reciprocal Rank Fusion (RRF) in the retrieval engine; eliminate arbitrary postings truncation (`[:300]`).

---

### Human Ratification Ballot

To ratify this decision, please indicate your choice below:

```text
[ ] ACCEPT: Ratify DEC-CAP-001 (Clauses CAP-D001 through CAP-D016) in full.
            Authorizes Wave A execution (reconciliation of canonical docs & control plane relock).
            Blocks all code implementation, provider spend, or scale runs until Wave B packets are ready.

[ ] AMEND:  Accept with explicit modifications noted below.

[ ] REJECT: Maintain legacy foundation / recovery plan and reject Cortex architectural correction.

Human Owner Signature / Confirmation: ___________________________
Date: 2026-09-02
```
