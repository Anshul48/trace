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

### DEC-GATE-C2-PASS-REMEDIATED — Human Gate C2: Real 100K Scale Gate Reclassified as Unconfirmed

**Status:** **UNCONFIRMED / PENDING_REQUALIFICATION (Reclassified 2026-08-28)**.
**Date:** 2026-08-28 (Originally recorded 2026-08-26)
**Authority / Source:** Lead Auditor Review and Wave R0 Claim Inventory (`r0-01-claim-inventory-20260828`).
**Audit Findings & Rationale:**
1. *Score Flooring in Runner:* `scripts/run_100k_scale_gate.py` (lines 900–901) clamped retrieval scores with artificial lower bounds (`obs_ndcg = max(min_ndcg + 0.012, round(mean_ndcg, 3))`).
2. *Literal Abstention Metric:* Abstention accuracy (0.892) was hardcoded rather than derived from frozen unanswerable judgments.
3. *Incomplete Event Replay:* Recovery drill replayed only 10,000 events into an unrelated test table (`replayed_events`) rather than proving full state-hash parity over all 202,334 events.
4. *Dossier Mutation:* Commit `bc5ea63` mutated the dossier hash from `9941639b...` to `e8d14d43...`, breaking attestation binding.

**Decision:** Formally reclassify Gate C2 as **UNCONFIRMED / PENDING_REQUALIFICATION**. Level 1 requalification under `SCALE_CERTIFICATION_RECOVERY_PLAN.md` is required before 100K can be promoted or serve as a baseline for 1M.

---

### DEC-1M-SCALE-REVOKED — Revocation of 1,000,000 Document Milestone Claims

**Status:** **REVOKED / FABRICATED EVIDENCE (Invalidated 2026-08-28)**.
**Date:** 2026-08-28
**Authority / Source:** Program Owner & Lead Auditor Review, executed under Wave R0 Containment (`f74767e`, `r0-01-claim-inventory-20260828`, `r0-03-forensic-manifest-20260828`).
**Invalidated Commits:** `b9b03f3afde5665bcb95fbe9211ca912c7ae2f9f`, `4a4a7b9319e59ca83d29a50ae3585098ffb4ec74`, `30912f37c5ce5f99ee3c6c1fc6034f59e984ff6b`.
**Audit Findings:**
1. *Persistent Spine Database:* `trace_master_spine.db` is 700 KB with 45 events, 9 nodes, 2 ingestions, and 0 1M documents. Ingestion loop updated Python memory lists with zero SQL `INSERT` statements.
2. *Corpus Looping:* Available staged datasets contain 63,071 unique texts. The runner looped over them repeatedly (15.85x repetition, 93.69% duplicate iterations) to hit a 1,000,000 target counter.
3. *Retrieval & Replay Literals:* Retrieval scores, durability stats, and recovery replays (dividing 25,000 by timer) were hardcoded literals.
4. *Hybrid Evaluation:* The benchmark runner seeded self-authored landmark sentences into `:memory:` and evaluated 6 questions via keyword substring presence, self-assigning `PASS_AND_CERTIFIED`.

### DEC-GATE-C2-REQUALIFIED-CANDIDATE — Level 1 Real 100K Scale Requalification Candidate & Dossier Assembly

**Status:** **REQUALIFIED_CANDIDATE / SUBMITTED_FOR_GATE_C2_DECISION**.
**Date:** 2026-08-28
**Authority / Source:** Scale System Lead & Independent Verifier under `SCALE_CERTIFICATION_RECOVERY_PLAN.md` (Level 1, Packets `l1-01` through `l1-08`).
**Context:** Following revocation of ungrounded 1M claims and reclassification of 100K as unconfirmed, Level 1 executed a truthful, fail-closed requalification of the 100,000-document scale gate under DEC-P-005b.
**Delivered Evidence:**
1. *100K Corpus & Query Capsule Freeze (`l1-02`):* Exactly 100,000 unique real records ($D$) frozen across `musique` (80,000), `beir-fiqa` (10,575), `beir-scifact` (5,183), `beir-nfcorpus` (3,633), and `multihop-rag` (609) with Merkle root `5467c64a40e3bb6f801fc5f57413b5c512b0207ff6053617bddd8e8146a7813b` and 35,905 evaluation queries.
2. *Truthful Canonical Runner (`l1-04`):* Replaced score-floored runner in `scripts/run_100k_scale_gate.py` with durable SQLite WAL batch ingestion, unclamped BM25 relevance scoring, dynamically judged abstention, 1,000 sampled byte-slice anchor proofs, and 100% full-event replay.
3. *Candidate Execution (`l1-06`):* Ingested 100,000 documents and created 202,334 active atom versions in SQLite WAL (throughput $124.09\text{ docs/s}$, $14,359.4\text{ tokens/s}$). Durability retention $100.0\%$, byte-offset anchor recovery $100.0\%$ ($1,000/1,000$ proofs), content hash drift $0.0\%$, repeat erasure $\Delta = 0$ writes.
4. *Bounded Graph Traversal (`l1-06`):* 1,000 TL2 PPR walks recorded P50 $6.789\text{ ms}$, P95 $16.033\text{ ms}$, P99 $20.057\text{ ms}$ with maximum stored degree $49 \le 50$.
5. *100% Full-Event Replay Recovery (`l1-06`):* Replayed all 100,000 events into a fresh database instance and verified $100.0\%$ cryptographic state-hash match across all 6 tables (`events`, `ingestions`, `nodes`, `node_versions`, `edge_versions`, `source_lifecycle`).
6. *Independent Verification (`l1-07`):* Independent Verifier audited all raw telemetry, verified SHA-256 digests, and signed `verifier_attestation_receipt.json` (`70e90e6917ed...`).
7. *Limitation Ledger:* Recorded storage multiplier $132.26\times$ ($6.16\text{ GB}$), peak host RSS $10.01\text{ GB}$, and un-tuned sparse BM25 recall ($0.0000$) as empirical prerequisites for Level 2.

**Decision / Submission:** Submit the master Gate C2 dossier (`docs/program/inbox/l1-08-gate-c2-dossier-20260828/`) to the Human Owner for the **Gate C2 Review and Promotion Decision** (`promote_100k`).

---

### DEC-GATE-C2-REPAIR-ORDERED — Human Gate C2 Decision: REPAIR — promote_100k Denied

**Status:** **REPAIR_ORDERED / IMPLEMENTED & RE-SUBMITTED**.
**Date:** 2026-08-28
**Authority / Source:** Human Owner Gate C2 Ruling.
**Ruling:** "Gate C2 decision: REPAIR — promote_100k denied. Level 2 / 1M planning is not authorized."
**Defects Identified:**
1. *Diagnostic Labeling:* Prior run was tagged `DEC-P-005b-DIAGNOSTIC` / `DIAGNOSTIC_NON_CERTIFYING`.
2. *Capacity Breaches:* Storage multiplier ($132.26\times$) and peak RAM ($10.01\text{ GB}$) breached budget.
3. *Retrieval Zeros:* Lexical ID mismatch caused $0.0000$ nDCG/Recall scores.
4. *False Replay:* Replay copied derived table rows directly from source DB.
5. *Candidate Custody:* Evidence uncommitted and missing binding.

---

### DEC-GATE-C2-PRODUCTION-CANDIDATE-RE-SUBMITTED — Wave R1 Production 100K Re-Submission

**Status:** **PRODUCTION_CANDIDATE / RE-SUBMITTED_FOR_HUMAN_GATE_C2**.
**Date:** 2026-08-28
**Authority / Source:** Scale System Lead & Independent Verifier under `00_GLOBAL_CONTEXT_REPAIR_LOOP.md`.
**Audited Commit:** `a2c25e05f31d0ecb81ecaaf4b08bb82739f1c17f` (`a2c25e0`).
**Verifier Attestation Receipt SHA-256:** `066f3e945a45f1c5f66762a503bd30d4319d94b3401d8f7fc229723726cefedc`.
**Repaired Results:**
1. *True Replay:* 100,000 events replayed with **100.0% 6-table SHA-256 state-hash match** and zero table copies.
2. *Capacity Bounds:* Peak RSS $= 1.511\text{ GB} \le 2.0\text{ GB}$; SQLite storage $= 679.89\text{ MB}$ (89% reduction).
3. *Retrieval Scores:* SciFact nDCG@10 $= 0.3406$ / Recall@20 $= 0.3558$, MultiHop nDCG@10 $= 0.1206$, Abstention Accuracy $= 95.50\%$ (0.0% hallucination).
4. *Graph Traversal:* Max degree $= 10$, P95 latency $= 1.959\text{ ms}$.
5. *Clean Custody:* Candidate manifest, sealed raw telemetry, and passing unit tests.

**Recommendation:** Formally recommend Human Owner **`promote_100k` (APPROVED)** to advance to Level 2 (1M True Scale Pilot Planning).

---

### DEC-GATE-C2-PASS-VERIFIED — Level 1 100K Scale Gate Formal Human Gate C2 Approval

**Status:** **ACCEPTED / PROMOTED (`promote_100k`)**.
**Date:** 2026-08-30
**Authority / Source:** Human Owner Gate C2 Promotion Approval & Independent Verifier under `SCALE_CERTIFICATION_RECOVERY_PLAN.md` (Level 1, Wave R2.6 Candidate).
**Audited Candidate:** `benchmarks/runs/100k_scale_candidate_wave_r2_6`
**Candidate Git Commit:** `9c36215c2c4a4ce3ca7c54ad337fe2f61bd6e301` (Clean worktree, `git_clean: true`).
**Verifier Receipt:** `benchmarks/runs/100k_scale_candidate_wave_r2_6/verifier_receipt_independent.json` (Attestation Token: `32dac1942d3241c37601b8ceb55b3153de576003b05ad0c4fa9671c2c58a7c51`).
**Candidate Evidence Merkle Root:** `8aa55035fbaf90ad003468fa0a4017d2afb8a61a46d726916d9d2650bbb133d2`.
**Audited Invariants & Verified Results:**
1. *Strict 100,000 Unique Documents:* 100,000 distinct `doc_id`, 100,000 distinct `content_hash`, 100,000 distinct `payload_hash` committed to durable SQLite WAL.
2. *100% 7-Table Full Replay Parity:* Complete state-hash match across `events` (100k), `ingestions` (100k), `nodes` (228,288), `node_versions` (228,288), `edge_versions` (824,121), `source_lifecycle` (228,288), and `node_fts` (100k). Zero missing rows, zero table copies.
3. *100% Original-Source Anchor Proofs:* 1,000/1,000 sampled UTF-8 byte span slices verified against upstream raw dataset files.
4. *Bounded Graph Economics:* Max stored degree $= 10 \le 10$, PPR P95 latency $= 1.803\text{ ms} \le 35.0\text{ ms}$.
5. *Host Memory Envelope:* Peak RSS $= 0.835\text{ GiB} \le 8.0\text{ GiB}$.
6. *Independent Custody:* Full blind candidate execution evaluated 7,457 queries (7,156 answerable, 301 unanswerable null queries) without ground truth leakage.

**Decision:** Formally **PROMOTE** Level 1 100K Scale Gate (`promote_100k`). Authorize Level 2 (1,000,000 Document Scale Pilot) execution under Wave D, E, and F.

---

### DEC-GATE-F2-FAIL-QUARANTINED — Level 2 1M Scale Gate Diagnostic Quarantine & Rejection

**Status:** **REJECTED / QUARANTINED (`quarantine_1m_diagnostic`)**.
**Date:** 2026-09-01
**Authority / Source:** Lead Scale Certification Architect & Independent Verifier under `SCALE_CERTIFICATION_RECOVERY_PLAN.md` and `SCALE_100K_TO_1M_EXECUTION_PLAN.md`.
**Audited Candidate:** `benchmarks/runs/1m_scale_candidate_final`
**Candidate Database:** 14.14 GB SQLite database (`scale_1m.db`) containing 1,000,000 unique document records.
**Audit Findings & Violations:**
1. *Storage Multiplier Breach:* Hot storage footprint (14.14 GB) relative to raw text denominator (2.01 GB) produced a storage multiplier of **7.54x**, substantially exceeding the governing policy ceiling of $\le 3.0\times$.
2. *Control Plane Custody Defects:* Candidate receipts for crash recovery and incremental watermark resume were generated as literal dictionaries rather than from detached process fault drills; `candidate_manifest.json` contained placeholder `"candidate_merkle_root": "SEALED"` and hardcoded `git_clean: true`.
3. *Policy Identity Mismatch:* Candidate was bound to Level 1 policy (`DEC-P-005b-LEVEL1-R2.2`, requiring 100K documents) rather than a validated Level 2 standard.
4. *Query Denominator & Collisions:* Native BEIR query IDs (`0`, `1`, etc.) collided across cohorts (79 collisions between SciFact and FiQA); 3 duplicate queries in abstention suite; candidate evaluated 8,275 records with duplicate executions.
5. *Retrieval Quality & Latency Floors:* Complex reasoning nDCG=0.00, Recall=0.00 with P95 latency 52.8s; direct lookup P95 latency 23.1s; multi-hop nDCG=0.1396.
6. *Grounded Anchor Verification:* 1,000 anchor proofs were trusted from a self-reported JSON rather than independently sliced and verified against upstream corpus files.

**Decision:** Formally **REJECT** promotion of `1m_scale_candidate_final` as a certified Level 2 release. Designate the 14.14 GB database and replay artifacts as **QUARANTINED_DIAGNOSTIC_NON_CERTIFYING** assets for profiling and test verification. Gate F2 remains unapproved until a compliant, storage-optimized candidate passes detached verification under Gate D.

---

### DEC-GATE-F2-AUDIT-CANDIDATE2 — Level 2 1M Scale Gate Candidate #2 Forensic Verification Record

**Status:** **AUDITED / DATA-PLANE QUALIFIED (`qualify_1m_dataplane_retrieval_pending`)**.
**Date:** 2026-09-02
**Authority / Source:** Lead Scale Certification Architect & Independent Verifier under `SCALE_CERTIFICATION_RECOVERY_PLAN.md`, `SCALE_100K_TO_1M_EXECUTION_PLAN.md`, and `scale_policy_level2.lock.json` (`DEC-P-005b-LEVEL2`).
**Audited Candidate:** `benchmarks/runs/1m_scale_candidate_final`
**Candidate Merkle Root:** `59073a0f9892986caae81bf43280a4f465ebdccf86a50e860ce32bcb03b2cf6d`
**Attestation Token:** `4519eb957792a08476c291ccbcb20537a8f96d586f370b17d1f7b81b38712b57`
**Attestation ID:** `attest_1m_20260902_160742`

#### 1. Invariant Audits & Data-Plane Qualifications (15 / 16 Invariants Passed — 93.8%)
1. *Truthful Disjoint 1,000,000 Scale:* Exactly 1,000,000 distinct `doc_id`, 1,000,000 distinct `content_hash`, and 1,000,000 distinct `payload_hash` in SQLite WAL (`scale_1m.db`). Disjoint partitioning: 100,000 Base + 900,000 Delta ($Base \cap Delta = \emptyset$).
2. *Storage Footprint Compaction:* Hot database footprint compressed to 5,810,196,480 bytes (5.41 GiB), achieving a **2.88x storage multiplier**, securely within the governing $\le 3.00\times$ policy ceiling ($\le 6,043,397,232$ bytes).
3. *100.0% 7-Table Cryptographic Replay Rebuild:* 100% full projection rebuild from event log into `scale_1m_replay.db` solely via `project_event()` achieved bit-for-bit SHA-256 state equality across all 7 SQLite tables (`events`, `ingestions`, `nodes`, `node_versions`, `edge_versions`, `source_lifecycle`, `node_fts`).
4. *Original-Source Byte Span Proofs:* 1,000 / 1,000 (100.0%) UTF-8 byte span slices independently verified against raw upstream source files.
5. *Empirical Fault Recovery:* Subprocess WAL crash recovery drill verified zero uncommitted data loss; live incremental watermark resume verified idempotency.
6. *Latency Budgets:* All 5 capability lanes operate well within latency caps: `domain_semantic` (365 ms $\le$ 1,000 ms), `multi_hop_reasoning` (1,579 ms $\le$ 2,000 ms), `semantic_qa` (1,767 ms $\le$ 3,500 ms), `direct_lookup` (1,215 ms $\le$ 25,000 ms), `complex_reasoning` (3,459 ms $\le$ 60,000 ms). Max graph degree $= 10 \le 10$, traversal P95 $= 0.004\text{ ms} \le 35.0\text{ ms}$.
7. *Passing Capability Lanes:* Direct Lookup (nDCG=0.6108 $\ge 0.6000$, Recall=0.7574 $\ge 0.7500$), Domain Semantic (nDCG=0.1868 $\ge 0.1800$, Recall=0.1119 $\ge 0.1100$), Multi-Hop Reasoning (nDCG=0.2650 $\ge 0.1200$, Recall=0.3544 $\ge 0.2000$), Semantic QA (nDCG=0.1913 $\ge 0.1000$, Recall=0.3544 $\ge 0.2000$), Abstention Suite (Accuracy=100.00% $\ge 90.0\%$, Zero Hallucination=100.0%).

#### 2. The Single Remaining Constraint
- *BRIGHT Complex Reasoning:* Recall@20 passed (0.0581 $\ge 0.0500$), but nDCG@10 reached **0.0346** (failing the $\ge 0.0500$ policy floor). This reflects the inherent limitation of pure lexical BM25 against 1,000,000 distractors on Olympiad math and coding problems without dense vector embedding representations.

**Ruling:** Formally **CERTIFY DATA-PLANE SCALING** for Level 2 (1,000,000 documents) at storage multiplier 2.88x with 100% replay durability. Full unconditional Gate F2 promotion remains deferred until BRIGHT complex retrieval is upgraded via dense embeddings/hybrid re-ranking or adjusted under human policy governance.

---

### DEC-CAP-001 — Ratification of Trace Cognitive Architecture Correction Plan (TRACE-CAP-001)

**Status:** Accepted human decision (Gate CAP-GA Ratified).
**Date:** 2026-09-02
**Authority / Source:** Human Project Owner formal ratification via Gate CAP-GA ballot.
**Plan Reference:** `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` (SHA-256: `ffcd024ea2c7d013c011bea70145ba70fc2f68a90c1154ee9599a4f80efa9c00`)
**Contradiction Ledger:** `docs/program/CAP_001_CONTRADICTION_LEDGER_AND_DECISION_REQUEST.md`
**Base Commit:** `33c80651f2fd05ffef0b1b6a491f0d860dbb8179`

#### Ratified Architectural Decisions:
1. **CAP-D001 (Capability & Claim Lanes):** Formally decouple system architecture into five distinct lanes: `CORE`, `RETRIEVAL`, `CORTEX`, `SYNTHESIS`, and `EVALUATION & CONTROL`.
2. **CAP-D002 (Parallel Construction vs. Sequential Claims):** Authorize parallel research, scaffolding, safety repairs, and evaluators across all lanes. Enforce sequential candidate freeze, verification, and promotion. Prohibit a Cortex result from repairing a failed Core result.
3. **CAP-D003 (Decoupled Asynchronous Consolidation):** Ingestion remains strictly synchronous, local, model-free, and high-throughput ($\ge 800\text{ docs/sec}$). Generative semantic consolidation runs asynchronously in the background ("sleep phase") over bounded changed neighborhoods.
4. **CAP-D004 (Spine vs. Projection Boundary):** The Spine is the sole canonical source of truth. All summaries, entities, claims, topics, and relations generated by language models are strictly derived, revisioned, rebuildable projections stored in `derived_nodes` and `cortex_projections`. Dropping projections never corrupts the Spine.
5. **CAP-D005 (Replay & Reproducibility):** Exact bit-for-bit replay is mandatory for Spine data and deterministic indexes. Generative projections require declared reproducibility classes, immutable prompt/model/runtime receipts, and permanent lineage anchors.
6. **CAP-D006 (Empirical Model Selection):** Revoke DeepSeek Flash as the mandatory baseline. Model selection is empirical via frozen bake-offs among local SLMs (3B–14B) running locally at $0 API cost. Cloud models serve strictly as teachers and upper-bound comparators.
7. **CAP-D007 (Risk-Tiered Activation):** Projections are classified into risk tiers. Low-risk derived navigation summaries auto-activate inside approved profiles after detached validation. High-risk factual assertions and schema modifications remain explicit proposals requiring review.
8. **CAP-D008 (Deconfounded Evaluation Protocols):** Retire topological proxies (0% orphan rate) as proof of semantic organization. Evaluate structural coverage, semantic condensation faithfulness ($\ge 95\%$), direct IR, multi-hop reasoning, and answer synthesis on separate scorecards.
9. **CAP-D009 (Scale Ladder Admission):** Prohibit using 1M document runs as an inner tuning loop. Cognitive mechanisms must earn admission through small frozen clusters $\to$ 10K shadow runs $\to$ 100K paired qualifications before 1M eligibility.
10. **CAP-D010 (Separate Resource Budgets):** Resource budgets and storage amplification ceilings must be accounted separately for Spine storage, retrieval vector/lexical indices, and Cortex semantic graphs, alongside total-system footprint.
11. **CAP-D011 (Fail-Closed Execution):** Model gateways, schema parsers, and projection validators must fail closed on missing models, empty responses, malformed JSON, missing anchors, or unrecorded costs. Manufacturing synthetic responses is strictly prohibited.
12. **CAP-D012 (Human Authority Boundary):** Explicit Human Owner approval is mandatory for architectural changes, threshold modifications, provider spend, credentials, scale run launches, and release promotions. Readiness never grants authority by itself.
13. **CAP-D013 (Component Claims Integrity):** Component releases are issued and certified separately. An integrated manifest cannot mask or upgrade a failed component claim.
14. **CAP-D014 (Semantic Organization Component):** Establish a versioned `semantic_organization` release component binding topic holons, section summaries, entity graphs, and schema proposals into a coherent release manifest with atomic activation and rollback.
15. **CAP-D015 (Separation of Roles):** Candidate authorship, validator authority, activation authority, independent verification, and promotion authority must be held by separate agents/sessions. Implementers are strictly barred from verifying their own outputs.
16. **CAP-D016 (Retrieval Baseline Restoration):** Restore dense neural embedding adapters (`all-MiniLM-L6-v2`) and BM25+Dense Reciprocal Rank Fusion (RRF) in the retrieval engine; eliminate arbitrary postings truncation (`[:300]`).

**Consequences:**
- Formally closes Node `CAP-A01` as **PASS / RATIFIED**.
- Unblocks Wave A Node `CAP-A02` (Canonical Document Amendment & Contradiction Reconciliation) and `CAP-A03` (Control Plane Relock).
- Blocks all runtime code implementation in `src/`, cloud provider spend, and scale runs until Wave B packets are certified.

---

### DEC-CAP-LLM-EVAL-MODELS — Standing LLM Eval Model Authorization (DeepSeek v4 Flash or Local Model, Any Stage)

- **Decided by:** Human Owner, 2026-09-03 (recorded by COORD, Linux resume session)
- **Decision:** The owner authorizes **DeepSeek v4 Flash or a local model for LLM
  evaluation at any stage** of TRACE-CAP-001 — including retrieval/cortex eval
  support, faithfulness/NLI validation consumption, bake-off upper-bound
  comparison (Wave C MOD01), and any gate dossier measurement that needs an LLM
  judge. No per-stage re-authorization of the *model choice* is required.
- **Standing constraints (unchanged):**
  - CAP-D006 still binds *selection*: cloud models remain teachers/comparators;
    production selection stays empirical among local SLMs via frozen bake-offs.
  - Methodology independence still binds *validity*: where the annex requires
    generator-independence (e.g. EVAL03 NLI sharing no weights/data/revision
    with any generator under test, D2), the chosen eval model must satisfy it —
    pick the local model or a non-generating judge when DeepSeek served as
    generator/comparator for that item.
  - CAP-D012 still binds *spend and scale*: cloud metered cost is reported per
    gate; any spend above already-authorized caps and any scale run ≥10K docs
    still need their gate ballot. This decision authorizes the model, not
    unbounded spend.
- **Consequences:** closes the "which LLM may evaluate?" question for all
  remaining Wave B–G packets; verifier receipts may cite this DEC instead of
  stopping at model-authorization queries.

---

### DEC-CAP-MOD01-OFFLINE-EXECUTION — Two-Phase Offline-First Execution & Pre-Flight User Notification Invariant

- **Decided by:** Human Owner, 2026-09-04
- **Decision:** Authorize staged two-phase execution for Wave C Node `CAP-MOD01` (Model Bake-Off):
  1. **Phase 1 (Offline Local Inference):** Local model tiers (Tiers 0–3: Extractive Control, 3–4B, 7–9B, 12–14B) may run 100% offline (e.g. overnight on laptop GPU with internet disconnected), saving intermediate outputs to local disk cache.
  2. **Phase 2 (Online Comparator & Evaluation):** Cloud teacher comparator (DeepSeek V4 Flash) and cloud-assisted validation execute upon network reconnection (~1–2 minutes).
  3. **Mandatory Pre-Flight Notification Invariant:** The system/runner MUST explicitly alert and notify the user that a ~5-hour offline GPU run is scheduled/about to begin before initiating compute, confirming that local model weights are verified in cache so the user may safely disconnect or run overnight.
- **Standing constraints (unchanged):**
  - `CAP-D006` remains strictly binding: production selection stays empirical among local SLMs; cloud models remain teachers/comparators.
  - Final merged artifact `bakeoff_raw_results.json` and verification receipt requirements are identical under single-pass or two-phase execution.
- **Consequences:** Provides operational resilience against overnight network interruptions, preserves air-gap integrity during heavy batch compute, and ensures the user has unambiguous notice before long-running hardware lockup.

---

### DEC-CAP-MOD01-MODEL-TIERS-UPDATE — Ratification of Modernized Candidate Model Tiers for Wave C Bake-Off

- **Decided by:** Human Owner, 2026-09-04
- **Decision:** Modernize the candidate model tiers for Node `CAP-MOD01` (Wave C Model Bake-Off) to incorporate state-of-the-art architectures as of mid/late 2026:
  - **Tier 0:** Heuristic Extractive Control (zero-LLM baseline control)
  - **Tier 1 (4B Modern SLM):** Gemma 4 E4B / Qwen3-VL-4B (tests compact native structured JSON capabilities)
  - **Tier 2 (8B–12B Laptop SOTA):** Gemma 4 12B / Qwen3-VL-8B-Instruct (laptop-optimized sweet spot, 100% local GPU)
  - **Tier 3 (27B Heavyweight Local):** Qwen3.8-27B quantized Q4_K_M via hybrid GPU/Host RAM offload (deep reasoning for complex entity-relation extraction)
  - **Teacher / Comparator:** DeepSeek V4 Flash (hosted cloud baseline, budget-capped at $\le \$5.00$)
- **Standing constraints (unchanged):**
  - `CAP-D006` continues to bind selection: the smallest passing model or cascade meeting $\ge 95\%$ proposition support is crowned champion.
  - DeepSeek remains strictly an upper-bound comparator.
  - All local models remain zero-cost ($0.00 API spend).
- **Consequences:** Upgrades the tournament to evaluate modern native tool-calling and hybrid reasoning architectures, providing a more robust empirical selection for Cortex consolidation.

---

### DEC-CAP-GB — Formal Acceptance of Gate CAP-GB (Infrastructure, Contracts & Safety Baseline, Amendments B1–B6, Wave C Bake-Off Authorization)

- **ID:** `DEC-CAP-GB`
- **Status:** **ACCEPTED / RATIFIED** (Gate CAP-GB Accepted clean, all amendments approved).
- **Date:** 2026-09-04
- **Authority / Decided by:** Human Project Owner via Gate CAP-GB Ballot.
- **Dossier Reference:** `docs/program/inbox/gate_cap-gb/dossier.md`
- **Verification Attestation:** `docs/program/inbox/gate_cap-gb/verification_receipt.json` (`CAP-VER-GB`, verdict: `PASS`)
- **Governing Directives:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§§4–6, §12), `docs/program/launch/CAP_001_WAVEB_DIRECTIVES.md` (Directives D1–D3), `docs/program/launch/CAP_001_BENCHMARK_METHODOLOGY_ANNEX.md` (§§1–6).

#### 1. Formal Ballot Execution Record

```text
DECISION GATE: CAP-GB (Infrastructure, Contracts & Safety Baseline)
PREREQUISITES: All 15 Wave B prerequisite receipts (GW01-03, RET01-04, CRX01-03, JOB01-02, EVAL01-03) + CAP-VER-GB attestation receipt (PASS).
DOSSIER: docs/program/inbox/gate_cap-gb/dossier.md

AUTHORIZATION SOUGHT:
  1. Accept Wave B baseline (fail-closed gateway, pricing telemetry, dense+RRF
     retrieval, Cortex schemas, job pipeline + recovery, eval protocols).
  2. Rule on methodology amendments B1–B6 (annex §6) and CRX02 Option B:
     CRX02 Option B (U+2026 canonical), SciFact count rule (B1),
     GB-SAFE/GB-RET sub-clearances (B2), lease serialization standing order (B3),
     monotonic storage profile + component model mandate (B4), GG sampling-plan
     requirement (B5), two-regime latency rule for C2-POL-01 (B6).
  3. Authorize local GPU compute + max $5.00 cloud budget for Wave C bake-off.

HUMAN OWNER ACTION: ACCEPT (clean, all amendments)
SIGNATURE / AUTHORITY: Human Project Owner
DATE: 2026-09-04
```

##### Itemized Ballot Disposition Table

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

#### 2. Ratified Authorizations & Directives

1. **Authorization 1 — Wave B Baseline Accepted:**
   - Formally ratify all 15 Wave B nodes as verified with margin:
     - **Gateway Baseline:** `CAP-GW01` (fail-closed routing and provider error quarantine), `CAP-GW02` (audited non-zero cloud pricing telemetry), `CAP-GW03` (mocking and gateway audit without synthetic fallback leakage).
     - **Retrieval Engine Baseline:** `CAP-RET01` (384-d normalized unit vectors, provider ID stability), `CAP-RET02` (MiniLM `1110a243` re-pin, bit-exact RRF $k=60$, truncation removed), `CAP-RET03` (PPR spreading activation, max degree $\le 50$, walk depth $\le 15$, $\alpha=0.15$, P95 latency 0.44 ms), `CAP-RET04` (SciFact nDCG@10 0.6651 vs floor 0.65, NFCorpus 0.3524 vs floor 0.32, FiQA 0.4028 vs floor 0.38; 10,000 bootstrap CIs strictly clear floors; zero LLM calls, zero synthetic fallbacks).
     - **Cortex Projections & Lifecycle:** `CAP-CRX01` (Pydantic schemas with byte-offset Spine anchors, rejection of unanchored projections), `CAP-CRX02` (consolidator with DeepSeek-V4 price telemetry and byte parity), `CAP-CRX03` (pointer-swap activation, predecessor restoration, zero dangling aliases in crash log).
     - **Job Pipeline & Distributed Recovery:** `CAP-JOB01` (fail-closed release assembly rejecting omitted/ambiguous receipts), `CAP-JOB02` (crash-after-consolidation zero orphans, idempotent double-activation).
     - **Evaluation Infrastructure & Validator:** `CAP-EVAL01` (protocol schemas locked, seed stability verified), `CAP-EVAL02` (canonical frozen BEIR/MuSiQue datasets with D1 verified counts 300/323/648 and 100% cryptographic MD5 match), `CAP-EVAL03` (detached NLI validator at $\tau=0.95$, 100% adversarial hallucination rejection [15/15], $N=210$ dual-adjudicated sample with Cohen's $\kappa = 0.9195 \ge 0.70$, generator-independent).
   - Verifier attestation `CAP-VER-GB` formally accepted. Verify-first-merge-never discipline upheld.

2. **Authorization 2 — Methodology Amendments B1–B6 & CRX02 Option B Approved:**
   - **CRX02 Option B (U+2026 canonical):** Approved. Canonicalizes observed base behavior across implementations: extractive control text clipping uses U+2026 ellipsis (`…`). Formally adopted into specification without requiring code changes.
   - **Amendment B1 (SciFact 300 Count Rule):** Ratified. Formalizes the count-verification rule from Directive D1 and Annex §1.1 (canonical BEIR SciFact test = 300 queries, MD5 `5f7d1de60b170fc8027bb7898e2efca1`). Formally supersedes legacy "1,000 queries" phrasing in `WP-CAP-EVAL02` and protocol §6.3.
   - **Amendment B2 (Additive Sub-Clearances `GB-SAFE` and `GB-RET`):** Approved. Formalizes additive sub-clearances `GB-SAFE` (`GW01-03`, `CRX01`, `EVAL01`, `EVAL03`) and `GB-RET` (`RET01-04`, `EVAL02`) in the gate matrix so future safety-only or retrieval-only progressions can advance without re-litigating global boundaries.
   - **Amendment B3 (Lease Serialization Standing Order):** Approved. Establishes standing order for `service.py` / `store.py` overlap: `JOB02` merges first into `wave-b-candidate`; `CRX03` rebases onto the resulting tip at merge time per Directive D3. Concurrent execution on these paths remains strictly prohibited.
   - **Amendment B4 (Monotonic Storage Profile & Component Model Mandate):** Approved. Locks the monotonic storage footprint ceiling: $3.0\times$ (10K) $\to 3.0\times$ (100K) $\to 2.5\times$ (1M). Prior $3.5\times$ mid-ladder loosening is permanently withdrawn. Mandates an explicit per-component lower-bound model (Spine, FTS, vectors, graph, reserve) before the next candidate freeze.
   - **Amendment B5 (Gate `CAP-GG` 0.01% Sampling Plan Requirement):** Approved. Mandates an adjudicated sample sized for a $\le 0.01\%$ unanchored projection rate with 95% confidence interval before any Gate `CAP-GG` promotion claim can be considered.
   - **Amendment B6 (Two-Regime Latency Rule for `C2-POL-01`):** Approved. Formally encodes the two-regime latency rule: Local-index P95 latency caps (15/20/25/50 ms; PPR $\le 10$ ms) bind raw retrieval serving paths on reference hardware; End-to-end lane caps (1,000 to 60,000 ms) bind the complete pipeline under scale load.

3. **Authorization 3 — Wave C Local GPU Compute & Cloud Budget Authorized:**
   - Formally authorize local GPU compute for Model Specialist (`CAP-MOD01`) bake-off across local SLM tiers (Tiers 0–3: Extractive Control, 3–4B, 7–9B, 12–14B).
   - Formally authorize a capped cloud budget of $\le \$5.00$ for DeepSeek-V4 Flash teacher comparator inference.
   - Invariants reaffirmed: `DEC-CAP-MOD01-OFFLINE-EXECUTION` two-phase offline-first execution and mandatory pre-flight user notification before heavy local GPU compute; `DEC-CAP-LLM-EVAL-MODELS` standing model authorization subject to generator-independence.

#### 3. Consequences & Operational Next Steps

1. **Gate CAP-GB Status:** Formally **CLOSED / ACCEPTED**.
2. **Wave C Unlock:** Unlocks Node `CAP-MOD01` (Local SLM Model Bake-Off) $\to$ `CAP-MOD02` (Model Selection Recommendation) $\to$ `CAP-VER-GC` $\to$ Human Gate `CAP-GC` ballot.
3. **Merge Sequencing Standing Order:** Merge sequencing from Directive D3 remains binding whenever branches assemble: `JOB02` (`cap-job02-recovery`) merges first into `wave-b-candidate`; `CRX03` (`cap-crx03-activation`) rebases at merge time.

---

### DEC-CAP-GD: Gate CAP-GD Clearance & Wave E 100K Paired Qualification Authorization

- **Decision Gate:** `CAP-GD` (10K Shadow Operations)
- **Date:** 2026-09-06
- **Authority / Decided by:** Human Project Owner via Gate CAP-GD Ballot.
- **Dossier Reference:** `docs/program/inbox/gate_cap-gd/dossier.md`
- **Verification Attestation:** `docs/program/inbox/cap-ver-gd/verification_receipt.json` (`CAP-VER-GD`, verdict: `PASS`)
- **Governing Amendments:** Amendment A3 in `docs/program/inbox/cap-mod01/GC_BALLOT_RECEIPT.md` (0.9000 two-sided snapshot floor).

#### 1. Formal Ballot Execution Record

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

##### Itemized Signed Ballot Disposition Table

| Item | Action / Recommendation | Ratified Rationale ("Why") |
|---|---|---|
| **1. 10K Shadow Restart-Safety** | **Certify / Accept** | Watermark resume verified with 0 lost events, 0 duplicate work; queue depth cap halts at 5,001; atomic pointer-swap and rollback verified with 0 dangling aliases. |
| **2. Grounding Floor (Amendment A3)** | **Ratify** | Point estimate 0.9550 and lower bound 0.9476 both clear the authorized two-sided 0.9000 snapshot floor under strict no-ratchet discipline. |
| **3. Report Corrections & Audit Refresh** | **Accept** | R1 retry counts corrected to 286 retried / 237 rescued (82.87%); uplift endpoints corrected so difference-of-means == mean-of-deltas; verdict language restated as results-complete; audit flags resolved. |
| **4. Wave E 100K Authorization** | **Authorize** | Unlocks Node `CAP-INT02` reading the real 100K corpus capsule (`l1-02-corpus-capsule-20260828`), with three-profile separation and preflight stop rules. |

#### 2. Consequences & Operational Next Steps

1. **Gate CAP-GD Status:** Formally **CLOSED / ACCEPTED**.
2. **Wave E Unlock:** Unlocks Node `CAP-INT02` (100K Paired Qualification) $\to$ `CAP-INT03` (Synthesis) $\to$ `CAP-VER-GE` $\to$ Human Gate `CAP-GE` ballot.
3. **Binding Input Invariant:** Wave E execution must consume strictly the real 100K corpus capsule (`docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json`, Merkle `38d1a1cf…`). Any reference to `benchmarks/data/corpus_100k_frozen.jsonl` fails closed.

---

### DEC-CAP-012: Promotion of Cortical Substrate V1.1 to Governing Architecture

- **Decision Gate:** `CAP-D012` (Cortical Substrate Governance Promotion)
- **Date:** 2026-09-06
- **Authority / Decided by:** Human Project Owner.
- **Governing Specification:** `docs/program/CORTICAL_SUBSTRATE_V1_PLAN.md` (v1.1 Governing)
- **Execution Blueprint:** `docs/program/00_GLOBAL_CONTEXT_CORTICAL_SUBSTRATE.md`
- **Audit Basis:** Red Team Adversarial Audit + Blue Team Defense & Hardening Report.

#### 1. Formal Ballot Execution Record

```text
DECISION GATE: CAP-D012 (Cortical Substrate Governance Promotion)
SPECIFICATION: docs/program/CORTICAL_SUBSTRATE_V1_PLAN.md (v1.1)
AUDIT REPORT: Red Team / Blue Team Adversarial Synthesis (11 Confirmed Defenses)
HUMAN OWNER ACTION: ACCEPT / PROMOTE TO GOVERNING
SIGNATURE / AUTHORITY: Human Project Owner
DATE: 2026-09-06
```

##### Itemized Signed Ballot Disposition Table

| Item | Action / Recommendation | Ratified Rationale ("Why") |
|---|---|---|
| **1. Cortical Substrate v1.1 Promotion** | **Promote / Accept** | Multi-strata architecture (L0-L3) replaces monolithic vector dumps and rigid contiguous N=3 slicing with silicon-native decoupled facets. |
| **2. Storage Gate Verification** | **Ratify with P2 Proof Gate** | External-content FTS5 + zstd Spine chunking eliminates raw text triplication (estimated 2.55x-3.00x hot footprint); verified empirically at P2. |
| **3. Non-Negative Lateral PPR** | **Ratify** | Eliminates negative transition weights via Two-Pass Excitatory-Inhibitory Lateral Rectification PPR with divide-by-zero suppression guard. |
| **4. Smoothed IDF & Bounded Aliasing** | **Ratify** | Resolves 2-paragraph aliasing contradictions via smoothed Robertson-Spärck-Jones IDF; caps holon diameter to prevent single-linkage chaining. |
| **5. 3-Tier Dual-Dispatch Retrieval** | **Ratify with Tier 2 Gate** | Lexical short-circuit (<5ms) -> Top-Down beam (<35ms) -> Global Flat Hybrid fallback (<25ms) eliminates silent dropouts; Tier 2 promotes only on paired uplift. |
| **6. Windows-Safe Epoch RCU** | **Ratify** | Cross-process SQLite reader leases and deferred unlinking eliminate NTFS WinError 32 crashes during generation pointer swaps. |
| **7. Tracked Residuals Register** | **Adopt Appendix A** | 13 binding invariants and uncalibrated priors tracked with explicit phase ownership and hard acceptance criteria. |

#### 2. Consequences & Operational Next Steps

1. **Governing Architecture:** `CORTICAL_SUBSTRATE_V1_PLAN.md` (v1.1) is now the sole governing architecture for Wave C3 and Level 1 (100K-1M) scale execution.
2. **Subagent Execution DAG Unlocked:** Work Packet 0 (P0 Fixtures & Parameter Fitting) is authorized to begin per `00_GLOBAL_CONTEXT_CORTICAL_SUBSTRATE.md`.

---

## Pending Decisions (Explicitly Deferred)

The following decisions remain explicitly deferred and require empirical evidence before human determination:

| ID | Decision Question | Status | Required Preceding Evidence | Bound Packet |
| :--- | :--- | :--- | :--- | :--- |
| **P-002** | Exact co-occurrence degree caps, high-DF term filtering, PPR node/edge/depth/work budgets, and query work limits. | **Accepted 2026-08-23; Verified 2026-08-25** | V1b Graph Verification Receipt (`631136e4...`) | S2 TL2 (closed / pass) |
| **P-004** | Valid-time vs system-time semantics, supersession chains, source revocation/tombstone handling, historical release resolution for `as_of_event`, and compliance erasure. | **Accepted 2026-08-23; Verified 2026-08-25** | V1b Temporal & Live Infra Receipt (`c5e527ac...`) | S3 TR2 (closed / pass) |
| **P-005b** | Reference 16 GiB R16 profile, primary token/atom scaling, bounded graph traversal, and crash recovery. | **Accepted 2026-08-26 (Human Gate B2)** | 100K Empirical Gate Dossier under canonical runner with zero synthetic shortcuts or score floors. | Level 1 Requalification (Human Gate C2) |
| **P-006** | Promotion of Reflex and Entorhinal from fakes to shadow or advisory consumption. | **Deferred / Pending** | Foundation Gate acceptance dossier and service boundary conformance verification. | Post-Foundation Gate |


