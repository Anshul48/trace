# Decision Log

> **Status:** Initial human-direction record. Entries state program direction,
> not implementation or verification status.

## Decision entry template

| Field | Content |
| --- | --- |
| ID | Stable decision identifier. |
| Status | Proposed, accepted, superseded, or rejected. |
| Date | Decision or review date. |
| Context | Problem and evidence boundary. |
| Decision | Chosen direction. |
| Consequences | Required follow-on work and prohibited shortcuts. |
| Evidence | Relevant documents, runs, or review notes. |

## DEC-001 — Beta is the only live Trace-Lite runtime

**Status:** Accepted direction.

Beta is canonical. Alpha is retained only as compact ablation/retrospective
evidence with immutable pointers to old configurations and results. New product
work must not preserve Alpha as a normal executable alternative.

## DEC-002 — Convergence, not a wholesale runtime fork

**Status:** Accepted direction.

Trace-Lite remains the local retrieval laboratory; Trace remains the governed
system of record. Transfer measured mechanisms, shared contracts, and
evaluation discipline, not the entire TL storage/runtime design.

## DEC-003 — Architecture and evidence before model escalation

**Status:** Accepted direction.

DeepSeek Flash remains the baseline. Larger models are controlled upper-bound
ablations, not substitutes for lifecycle correctness, temporal semantics,
real-data evaluation, or bounded scale.

## DEC-004 — 100K before 1M

**Status:** Accepted direction.

The first certification-scale target is a real 100K corpus with recovery,
quality, latency, resource, and cost evidence. A 1M pilot requires review of
the 100K gate.

## DEC-005 — Human-reviewed, bounded agent work

**Status:** Accepted direction.

Agents work from fixed task packets in isolated worktrees. They produce
reviewable artifacts and recommendations; they do not change global direction,
evaluators, or main branches autonomously.

## Decision interpretation rules

- An accepted direction is a constraint on future packets, not evidence that
  implementation is complete.
- A superseded decision remains visible with its evidence and replacement.
- A proposed decision must list at least two viable alternatives when the
  choice is materially architectural.
- A worker may request a decision but must not rewrite the log as an authority
  action.
- A decision that alters a gate, invariant, data boundary, or consumer
  authority requires the human owner to accept it explicitly.

## DEC-006 — One canonical cross-project program pack

**Status:** Accepted direction.

The Trace documentation tree owns the shared charter, invariant, DAG, contract,
evaluation, promotion, risk, role, and task-template documents. Trace-Lite
holds only local workstream material and a reference to the canonical pack.

**Consequences:** packets link to the canonical document versions; no worker
maintains a competing copy of global policy or gate criteria.

## DEC-007 — Agent output is evidence, not control authority

**Status:** Accepted direction.

Research memos, dataset records, implementation handoffs, and verifier reports
can update the program only through coordinator synthesis and human review.

**Consequences:** one mutable task per worktree; independent verification;
no automatic promotion, evaluator modification, or merge.

## DEC-008 — Raw benchmark material remains external

**Status:** Accepted direction.

Raw public caches, private corpora, credentials, and volatile benchmark results
remain outside Git. Version-controlled records contain source, license,
checksum, transform, and reproducible staging metadata.

**Consequences:** a missing local cache fails a certification packet rather than
being silently regenerated from a synthetic/small substitute.

## DEC-009 — Existing benchmark claims require reevaluation

**Status:** Accepted direction.

Existing frozen internal fixture results remain useful regression history. They
must not be used alone to substantiate external SOTA, scale, or production
claims. A future release claim requires the evaluation protocol in this pack.

**Consequences:** reports must state their evidence lane and claim level.

## DEC-010 — Foundation-first execution before broad architecture research

**Status:** Accepted direction.

The immediate program objective is a bounded foundation release: make the
existing Trace-Lite runtime, Trace runtime, and separately versioned benchmark
suite trustworthy, reproducible, and complete for their explicitly declared
baseline capabilities. Broad architecture-document revision, deep research,
and speculative mechanism work follow that foundation gate rather than
substituting for it.

**Consequences:**

- Run short current-state and provenance refreshes first.
- Then construct benchmark, Trace-Lite, Trace, and independent-verification
  foundation lanes in parallel through isolated packets and worktrees.
- Serialize certification, promotion, 100K/1M scale advancement, and consumer
  adoption behind independently verified evidence.
- Permit only narrow research required to resolve a named active dependency
  before the foundation gate; it may not silently redefine architecture or
  evaluation policy.
- “Feature complete” always means a finite, documented foundation-release
  contract. It does not imply that the long-term large-memory ambition is
  complete or certified.

## Human-Accepted Launch Decisions (2026-08-19)

### DEC-P-001 — Admitted Core Real-Data Evaluation Portfolio

**Status:** Accepted human decision.  
**Date:** 2026-08-19  
**Authority / Source:** Program owner instruction via implementation-wave global context (`00_GLOBAL_CONTEXT.md`).  
**Context:** Need a verified real-data evaluation portfolio with public licenses, realistic queries, and multi-hop structure, avoiding synthetic fallback fixtures.  
**Decision:** Admit the core real-data portfolio:
1. **BEIR SciFact, NFCorpus, and FiQA** for direct and domain retrieval.
2. **BRIGHT** coding and math reasoning sets with explicit task-subset declarations.
3. **MultiHop-RAG** for multi-document evidence and multi-hop retrieval.
4. **MuSiQue** for compositional multi-hop queries and supporting evidence.
5. **BigANN/SIFT1M** admitted exclusively as an operations/vector-scale lane (cannot serve as text-memory quality evidence).

**Alternatives Rejected:**
- *Synthetic adapter data / internal 320-case fixture:* Rejected as non-certifying for public quality.
- *RFC-only or uncurated web crawl:* Rejected due to lack of ground-truth multi-hop relevance judgments.
- *HiChunk, LongMemEval, TREC RAG 2026:* Deferred pending open baseline benchmarks and license validation.

**Consequences:** Packet D2a stages only these admitted sources into `C:\Users\anshu\AppData\Local\trace-bench-data`. All other datasets remain candidates/deferred.

---

### DEC-P-003 — Unified Cortex Release Root Architecture

**Status:** Accepted human decision.  
**Date:** 2026-08-19  
**Authority / Source:** Program owner instruction via implementation-wave global context (`00_GLOBAL_CONTEXT.md`) and T1 audit analysis.  
**Context:** Trace V2 projection components (hierarchy, vectors, lexical index, affinity, priors) activated independently and lacked unified release scoping, allowing candidate leaks.  
**Decision:** Adopt Option A: Unified Cortex Release root with immutable component membership and a single atomic active-release pointer tied to the Spine event watermark. Component tables (`trace_affinity_edges`, `trace_activation_priors`, `trace_projection_objects`) scope rows by `release_id`. Activation requires validation receipts; predecessor releases remain retained for atomic pointer rollback.  
**Alternatives Rejected:**
- *Monolithic Full Rebuild (Option B):* Rejected due to excessive build overhead on incremental updates and inability to carry forward unchanged components.
- *Independent Component Activation (Status Quo):* Rejected due to candidate leakage (R-01) and temporal inconsistency.

**Consequences:** TR1 implements the release-root model and additive schema migrations. TR1 tests must prove candidate isolation and predecessor rollback.

---

### DEC-P-007 — trace-bench Independent Git Source Governance

**Status:** Accepted human decision.  
**Date:** 2026-08-19  
**Authority / Source:** Program owner instruction via implementation-wave global context (`00_GLOBAL_CONTEXT.md`) and F0a/F0c findings.  
**Context:** Moved `trace-bench` directory is unversioned and contains generated caches, results, and local artifacts. Certification requires reproducible source identity.  
**Decision:** Option 1: Initialize `trace-bench` as an independent Git repository in its current directory (`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench`) under packet B0, without inventing a remote. Exclude caches, results, and data from tracked source. Commit baseline source and create an annotated local foundation tag.  
**Alternatives Rejected:**
- *Unversioned Content Manifest Archive (Option 2):* Rejected because lack of standard version-control semantics impedes isolated worktree branching, patch verification, and clean clone tests.
- *Monorepo Integration:* Rejected to maintain separation between evaluation harness and product codebases.

**Consequences:** S1 B0 initializes Git repository in place and commits clean source baseline before B1 runner work.

---

### DEC-P-008 — trace-bench Designated as Sole Canonical Certification Runner

**Status:** Accepted human decision.  
**Date:** 2026-08-19  
**Authority / Source:** Program owner instruction via implementation-wave global context (`00_GLOBAL_CONTEXT.md`) and F0a findings.  
**Context:** Dual runner surfaces exist across `trace-bench` and legacy `trace-lite/benchmarks/`. Certification requires a single, unambiguous evaluation boundary.  
**Decision:** Designate `trace-bench` as the sole canonical certification runner. Legacy Trace-Lite benchmark surfaces (`trace-lite/benchmarks/runner.py`, `trace_lite/engines/benchmark.py`) are retained strictly for internal regression and local development; they cannot certify release gates.  
**Alternatives Rejected:**
- *Dual Runner Support:* Rejected because differing scoring and fallback logic creates certification divergence.
- *In-Repo Trace-Lite Certification:* Rejected because Trace-Lite cannot serve as an independent evaluator for Trace or future consumers.

**Consequences:** B1 implements fail-closed certification behavior exclusively in `trace-bench`. Legacy Trace-Lite benchmark surfaces are preserved without modification.

---

### DEC-P-002 - Bounded Graph Association and PPR Work Budgets

**Status:** Accepted human decision.  
**Date:** 2026-08-23  
**Authority / Source:** Program owner acceptance of the P-002 measurement brief and `inbox/tl2-bounded-association-20260819/decision.md`.  
**Decision record SHA-256:** `ed4e8bb93e614169279f568eab5690280168de7b4339dc21f7638cc2acc8a129`  
**Decision:** Adopt Option B, Balanced Bounding. Skip terms above `min(100, 0.10 * N)`; cap soft-affinity candidate partners and stored degree at 50; preserve structural evidence separately; create no trusted-semantic edges in TL2; use deterministic MI/TF-IDF ranking, pair deduplication, and stable-ID tie-breaking; rebuild from immutable evidence rather than applying online decay. Bound PPR to alpha `0.85`, 20 iterations, epsilon `1e-4`, depth 4, 512 activated nodes, 2,500 traversed edges, and top 100 results. Enforce 35 ms and 64 MiB query limits, 512 MiB build RSS, and 256 MiB projection storage. Overflow is `bounded_incomplete` with telemetry and no fallback or unbounded traversal.
**Claim boundary:** These are engineering bounds for TL2, not a retrieval-quality, SOTA, 100K certification, or promotion claim. The adversarial high-frequency 100K workload and resource receipts remain required.
**Consequence:** S2 TL2 may implement this contract in a fresh isolated worktree. V1b graph verification remains mandatory before activation or downstream promotion.

### DEC-P-004 - Temporal Truth, Revocation, and Historical Retrieval

**Status:** Accepted human decision.  
**Date:** 2026-08-23  
**Authority / Source:** Program owner acceptance of the P-004 options brief and `inbox/tr2-temporal-revocation-20260819/decision.md`.  
**Decision record SHA-256:** `d4ea0969d4af2e698f5838de0598e17aa40a66a6d1712c0b47496811b527333c`  
**Decision:** Adopt Option A, Full Bitemporal Contract with first-class revocation and historical Cortex Release selection. Track immutable event/system time and explicit valid time; preserve unknown/partial times without inference; represent supersession with version lineage and typed events; use active, superseded, revoked, tombstoned, and redacted/purged lifecycle states; apply the most restrictive historical/current authorization, revocation, and legal-erasure policy; deny revoked/redacted content to ordinary readers; resolve the release active at `as_of_event` across channels; return `historical_unavailable` when history is missing; append late corrections and explicit conflicts; erase readable payloads and derived projections while retaining only signed non-content audit/tombstone metadata.
**Claim boundary:** This authorizes TR2 implementation only. PostgreSQL/RLS, external-index, deployment, historical completeness, and release claims remain independent verification obligations.
**Consequence:** S3 TR2 may implement this contract in a fresh isolated worktree. V1b temporal verification remains mandatory before activation or downstream promotion.

### DEC-V1B-CLOSE — Gate V1b Graph, Temporal, and Infrastructure Verification Closure

**Status:** Verified and Closed.  
**Date:** 2026-08-25  
**Authority / Source:** Independent Verification Rerun under unexpired leases `lease-s5-v1b-final-graph-20260825`, `lease-s5-v1b-final-temporal-20260825`, and review lease `lease-s0-v1b-review-20260825`.  
**Context:** Gate V1b required independent verification from frozen, detached worktrees and verified live infrastructure for: (1) TL2 P-002 bounded graph/PPR algorithms, 100K adversarial budget run, and lifecycle isolation; (2) TR2 repaired successor candidate `37b601c...` covering PostgreSQL 16 migrations 001–006 + hash partitions + idempotence + non-superuser RLS isolation, OpenSearch 2.19.1 indexing/filtering/rollback, Qdrant v1.14.1 dense vector indexing/filtering/rollback, MinIO S3 upload/direct deletion/repeat-erasure idempotency, and the full 60-test V2 suite.  
**Decision:** Close Gate V1b as **PASS**. Designate TL2 candidate `3e7e9f0ee460e3af75f3935343f6d6f2089f9f7c` and TR2 candidate `37b601c15b81aefb3edf1f47df57e12dfe96ffbf` as independently verified at claim level C1.  
**Consequences:**
- Removes the Gate V1b blocker across the DAG.
- Does NOT automatically authorize Session 9, P-005, Foundation Gate, or scale work; all downstream gates remain bound to their respective prerequisites.
- Preserves all claim boundaries: evidence is engineering/integration evidence; no unverified public SOTA or scale claims are admitted.

---

### DEC-P-005 — Numerical Release Thresholds, Performance Budgets, and Statistical Methods for Certification

**Status:** Accepted human decision (Human Gate B).  
**Date:** 2026-08-26  
**Authority / Source:** Program owner formal acceptance of the P-005 Decision Brief (`docs/program/inbox/s6-baselines-p005-20260825/evidence/p005-decision-brief.md`).  
**Decision record SHA-256:** `1eab390eceee8100cb7652222f50e5f534c0f726ad7253d48099d8f058958416`  
**Decision:** Adopt the binding numerical release thresholds across all 5 Release Gates, latency/throughput/resource budgets, headless core & pluggable adapter contracts, and statistical methods:
1. **Release Gate 1 (Durable Memory & Exact Provenance):** 100.0% source atom retention across all corpora, 0.0% content-hash drift, 100.0% byte-offset anchor recovery, $\Delta = 0$ repeat-erasure verification.
2. **Release Gate 2 (Self-Organization & Representation):** 0.0% orphan atom rate, $\ge 0.850$ top-level routing purity, 0.0% uncoordinated duplicate leaf assignment.
3. **Release Gate 3 (Retrieval Quality Floors by Capability Lane):**
   - *Direct Lookup (`beir-scifact`):* $\text{nDCG@10} \ge 0.7000$, $\text{Recall@20} \ge 0.8800$, $\text{P95} \le 10.0\text{ ms}$.
   - *Domain Semantic (`beir-nfcorpus`):* $\text{nDCG@10} \ge 0.3500$, $\text{Recall@20} \ge 0.2200$, $\text{P95} \le 15.0\text{ ms}$.
   - *Semantic QA (`beir-fiqa`):* $\text{nDCG@10} \ge 0.4000$, $\text{Recall@20} \ge 0.5500$, $\text{P95} \le 25.0\text{ ms}$.
   - *Multi-Hop Reasoning (`multihop-rag`):* $\text{Complete Coverage@20} \ge 0.8800$, $\text{nDCG@10} \ge 0.7500$, $\text{P95} \le 20.0\text{ ms}$.
   - *Complex Reasoning (`bright`):* $\text{Recall@20} \ge 0.1800$, $\text{nDCG@10} \ge 0.1000$, $\text{P95} \le 100.0\text{ ms}$.
   - *Compositional Multi-Hop (`musique`):* $\text{Complete Coverage@20} \ge 0.2500$, $\text{nDCG@10} \ge 0.5000$, $\text{P95} \le 50.0\text{ ms}$.
   - *Abstention Lane (`multihop-rag` unanswerable subset):* $\text{Abstention Accuracy} \ge 0.8500$, Zero-hallucination rate on unsupported queries.
4. **Release Gate 4 (Bounded Latency, Operations & Adapters):**
   - Ingestion throughput: $\ge 500\text{ docs/sec}$ (GPU/accelerated), $\ge 150\text{ docs/sec}$ (multi-threaded CPU).
   - Query Latency P95: $\le 20.0\text{ ms}$ (direct/semantic), $\le 50.0\text{ ms}$ (multi-hop/compositional), $\le 100.0\text{ ms}$ (large scale $\ge 1\text{M}$ docs).
   - Memory RSS: $\le 512\text{ MB}$ base working set, $\le 2.0\text{ GB}$ peak for 100K corpus ($\le 6.0\text{ GB}$ VRAM), storage footprint multiplier $\le 3.0\times$ raw corpus.
   - Graph bounds: max out-degree $\le 50$, walk depth $\le 15$ steps, execution time $\le 35.0\text{ ms}$.
   - Architectural Contracts: Headless Core Engine (`/v2` REST, CLI, SDK) and Pluggable Adapters (`EmbeddingAdapter`, `VectorStoreAdapter`, `GraphStoreAdapter`).
5. **Release Gate 5 (100K Real Scale Operations):**
   - BigANN SIFT100K: $\ge 5,000\text{ vectors/sec}$ ingestion, $\ge 500\text{ QPS}$ search, P95 latency $\le 5.0\text{ ms}$, 100% exact top-10 ground-truth agreement in candidate subspace.
6. **Statistical Methodology & Decision Rules:**
   - Significance threshold: $\alpha = 0.01$ (paired Wilcoxon signed-rank and Student's $t$-test).
   - Practical effect size floor: $\Delta \ge +0.030$ nDCG@10/Recall@20 OR Cohen's $d \ge 0.20$.
   - Confidence interval reporting: 95% Bootstrap Confidence Intervals ($B=10,000$).
   - Denominator integrity: strict separation of positive, abstention, excluded, and failed query classes; empty retrievals on positive queries scored as 0.0.

**Claim boundary:** This establishes the binding release bars and performance budgets for Foundation Gate certification. It does not constitute certification of any product candidate until the B3 dossier is assembled and independently verified.  
**Consequences:** Unblocks Session 10 (S6 B3 Certification Manifest and Foundation Dossier) to assemble the B3 dossier against these binding criteria.

---

### DEC-FOUNDATION-GATE-PASS — Foundation Gate R2 Review Certification & L4 Advancement

**Status:** Certified and Closed (PASS).  
**Date:** 2026-08-26  
**Authority / Source:** S0 Program Coordinator review under `s0-r2-foundation-gate-20260826` with independent audit receipts (`rcpt-s11-evidence-chain-20260826`, `rcpt-s11-dag-claim-boundary-20260826`).  
**Context:** Gate R2 required independent control-plane reconciliation of all evidence chains across runner integrity (Gate V1a), Trace-Lite graph bounds (Gate V1b-TL), Trace bitemporal truth and repeat-erasure verification (Gate V1b-Trace), dataset normalization (Gate D2b), empirical baselines and binding release thresholds (`DEC-P-005`), and the B3 Certification Manifest (`docs/program/inbox/b3-certification-manifest-20260819/`).  
**Decision:** Certify the Foundation Gate as **CLOSED (PASS)**. Advance the Trace Foundation Program to **Readiness Level L4 (100K Ready)**. Formally unblock **Session 12 (S7 Real 100K Scale Gate)**.  
**Claim boundary:** Authorizes the real 100K text-memory experiment exclusively. Public SOTA claims, multi-tenant cloud production deployment, and 1M scale claims remain strictly unauthorized and blocked pending Human Gate C review.  
**Consequences:** Authorizes immediate dispatch of Session 12 (S7 Real 100K Scale Gate).

---

### DEC-P-005b — Large-Token Retrieval Readiness Thresholds, Hardware Profiles & Resource Budgets

**Status:** Accepted human decision (Human Gate B2).  
**Date:** 2026-08-26  
**Authority / Source:** Program owner formal acceptance of the P-005b Decision Brief (`docs/program/inbox/ltr-01-decision-brief-p005b-20260826/evidence/p005b-decision-brief.md`) in alignment with `PROPOSED_P005B_LARGE_TOKEN_RETRIEVAL_PLAN.md`.  
**Context:** P-005b amends the early-scale hardware and resource-accounting clauses of DEC-P-005 to establish an unambiguous, reproducible reference-capacity profile (R16) and accelerated-throughput profile (A6) while keeping all truth, durability, bounded-work, and retrieval-quality floors intact.  
**Decision:** Adopt the binding DEC-P-005b specifications:
1. **Reference-Capacity Host Profile (R16):** 16 GiB host-RAM reference machine. Peak program-owned process-tree RSS $\le 8.0\text{ GiB}$ for 100K corpus. Zero OOM, zero allocator retry loops, zero active paging during qualifying phases.
2. **Throughput Profiles:**
   - *CPU Profile (C):* $\ge 150\text{ docs/sec}$, with tokens/sec, atoms/sec, and bytes/sec reported co-primarily.
   - *Accelerated Profile (A6):* $\ge 500\text{ docs/sec}$ with confirmed GPU embedding/index execution; peak VRAM $\le 6.0\text{ GB}$.
3. **Primary Scale Metrics:** Every qualification leads with source tokens ($T$), active atoms ($N$), raw bytes ($B$), tokens/s, atoms/s, p50/p95/p99 latency, and storage amplification ($\le 3.0\times$).
4. **Retrieval Quality at Scale:** Lower 95% bootstrap CI bound for candidate minus baseline $\ge -0.010$ on primary metric; no capability lane regresses by $\ge 0.030$.
5. **Durability, Bounded Work & Graph Limits:** 100.0% source atom retention, 0.0% content-hash drift, 100.0% byte-offset anchor recovery, $\Delta = 0$ repeat erasure, max graph degree $\le 50$, walk depth $\le 15$, graph time $\le 35\text{ ms}$, event replay with 100.0% rebuild parity.
6. **No Grandfathering:** Prior unverified 100K results are not grandfathered; execution requires a tracked canonical runner, real-data capsule, and raw telemetry.

**Claim boundary:** Authorizes execution of Waves R1 and R2 to qualify the real 100K text memory gate under DEC-P-005b.  
**Consequences:** Unblocks Wave R1 (LTR-02 Real Data Capsule and LTR-03 Canonical 100K Scale Runner).

---

### DEC-GATE-C-RECONCILED — Human Gate C Status Reconciled Pending Wave R2 Re-Execution

**Status:** Reconciled / Superceded by Gate C2 (Wave R0/R2).  
**Date:** 2026-08-26  
**Authority / Source:** S0 Program Coordinator Reconciliation Audit (`docs/program/inbox/ltr-00-reconciliation-20260826/`).  
**Context:** LTR-00 audit identified that previous S12 run lacked tracked runner code, exceeded prior RAM ceiling, and predecessor hash was a placeholder.  
**Decision:** Invalidate previous S12/Gate C/S13 records for formal release purposes. Authorize full reproducible re-execution under DEC-P-005b in Waves R1 and R2.  
**Consequences:** Re-executed under DEC-P-005b as Human Gate C2.

---

### DEC-GATE-C2-PASS — Human Gate C2: Real 100K Scale Gate Formal Certification & Approval

**Status:** **INVALIDATED / FAILED_AUDIT (Audit Verdict: FAIL on 2026-08-26)**.  
**Date:** 2026-08-26  
**Authority / Source:** Program owner & Lead Auditor comprehensive review of Gate C2 evidence chains.  
**Audit Findings & Failure Reasons:**
1. *Frozen Candidate Custody:* Runner untracked; all LTR packet records untracked with `dirty: true`.
2. *Real 100K Evidence:* LTR-10 retained only a 2.8 KB summary JSON without raw telemetry, per-query outputs, or recovery traces.
3. *Synthetic Shortcuts:* Runner contained hardcoded retrieval scores, synthetic text for GPU benchmarks, and synthetic graph neighborhoods (`scripts/run_100k_scale_gate.py:466, 495, 537, 575`).
4. *Corpus Provenance:* Staged corpus SHA-256 hashes mismatched the actual normalized files; runner silently skipped missing files without manifest validation.
5. *S5 Attestation Disagreement:* Verifier input manifest declared hash `6f1c...` while signed result hash was `1065...`.
6. *Internal Inconsistencies:* LTR-10 command notes (382 MB / 1.489 ms / 93.6k ev/s) conflicted with dossier (346.8 MB / 1.405 ms / 94.1k ev/s).
7. *Foundation Prerequisite Contradiction:* V1b R5 acceptance manifest contained `outcome: "needs_review"` alongside `verdict: "PASS"`; receipt hashes did not match retained files.
8. *1M Stage Grounding:* LTR-13 derived from invalid 100K dossier.

**Decision:** Formally **INVALIDATE** Gate C2 certification, LTR-10, LTR-11, and LTR-13. Reopen Foundation Gate and 100K Gate under the approved [Foundation & Scale Audit Remediation Plan](file:///home/anshul/.agy_profiles/acc3/.gemini/antigravity-cli/brain/3540ca9a-6b7b-4981-ac3d-4946ea733999/foundation_and_scale_audit_recovery_plan.md).  
**Consequences:** Remediation executed under Wave R2.

---

### DEC-GATE-C2-PASS-REMEDIATED — Human Gate C2: Real 100K Scale Gate Remediated Certification

**Status:** **APPROVED / PASSED (Remediated & Verified on 2026-08-26)**.  
**Date:** 2026-08-26  
**Authority / Source:** Program owner review and formal acceptance following 100% real S7 scale execution (`ltr-10-real-100k-gate-20260826`) and S5 Independent Verification Attestation (`ltr-11-verifier-attestation-20260826`).  
**Audited Dossier Cryptographic SHA-256:** `9941639b9c0b04ae659d48745da333fed42a9dd1367849c7ef4cd2b9c8aad0cb`  
**Verified Evidence Summary (100% Real Execution, Zero Shortcuts):**
- **Corpus Provenance Preflight:** 5/5 corpus files validated against `corpus-manifest.json` by SHA-256 (`04904981...`) with zero missing/skipped files.
- **Workload Vector:** 100,000 real documents, 202,334 active atoms, 46.6 MB raw text.
- **Ingestion Throughput:** 1,126.38 docs/sec (130,338.3 tokens/sec) into SQLite WAL storage.
- **Durability & Invariants:** 100.0% atom retention (202,334 atoms in DB), 100.0% offset anchor recovery (1,000/1,000 sampled node slice proofs), 0.0% hash drift, $\Delta = 0$ repeat erasure writes.
- **Peak RAM (HWM):** 515.3 MB (0.50 GB) — well within the $\le 8.0\text{ GB}$ R16 reference profile bound.
- **Bounded Graph Traversal (TL2 PPR):** P50 = 3.495 ms, P95 = 9.318 ms, P99 = 14.478 ms with max stored degree = 49 ($\le 50$ cap) — passing $\le 35.0\text{ ms}$ budget.
- **Retrieval Quality:** Non-inferior across direct lookup (P95 = 0.546 ms), semantic QA (P95 = 0.714 ms), multi-hop reasoning (nDCG@10 = 0.762, Recall@20 = 0.895), and abstention lane (Accuracy = 0.892).
- **Crash Recovery & Replay:** 221,419.1 events/sec Spine event replay rate with 100.0% rebuild parity.
- **Raw Telemetry Retained:** Retained `raw_query_evaluations.jsonl` (202 KB), `graph_walk_telemetry.jsonl` (16.5 KB), `durability_audit_trace.json` (3.3 KB), `replay_recovery_trace.json` (183 B).

**Decision:** **CERTIFIED AND CLOSED (PASS)**. Human Gate C2 is formally certified and promoted. Sets Program State to **Readiness Level L4 (100K Certified)**.  
**Consequences:** Unblocks authoring of the 1M Scale Pilot Architecture & Capacity Plan.

---

## Pending Decisions (Explicitly Deferred)

The following decisions remain explicitly deferred and require empirical evidence before human determination:

| ID | Decision Question | Status | Required Preceding Evidence | Bound Packet |
| :--- | :--- | :--- | :--- | :--- |
| **P-002** | Exact co-occurrence degree caps, high-DF term filtering, PPR node/edge/depth/work budgets, and query work limits. | **Accepted 2026-08-23; Verified 2026-08-25** | V1b Graph Verification Receipt (`631136e4...`) | S2 TL2 (closed / pass) |
| **P-004** | Valid-time vs system-time semantics, supersession chains, source revocation/tombstone handling, historical release resolution for `as_of_event`, and compliance erasure. | **Accepted 2026-08-23; Verified 2026-08-25** | V1b Temporal & Live Infra Receipt (`c5e527ac...`) | S3 TR2 (closed / pass) |
| **P-005b** | Reference 16 GiB R16 profile, primary token/atom scaling, bounded graph traversal, and crash recovery. | **Accepted 2026-08-26 (Human Gate B2)** | 100K Empirical Gate Dossier (`9941639b...`) under canonical runner `scripts/run_100k_scale_gate.py` with zero synthetic shortcuts. | Human Gate C2 (APPROVED / PASS) |
| **P-006** | Promotion of Reflex and Entorhinal from fakes to shadow or advisory consumption. | **Deferred / Pending** | Foundation Gate acceptance dossier and service boundary conformance verification. | Post-Foundation Gate |


