# Trace Cognitive Architecture Correction Plan

> **Plan ID:** `TRACE-CAP-001`
>
> **Status:** Proposed architecture and execution plan, prepared 2026-09-02.
> It becomes governing direction only after explicit Human Owner acceptance and
> the corresponding decision-log amendment.
>
> **Observed implementation base:** `33c80651f2fd05ffef0b1b6a491f0d860dbb8179`.
> The worktree was clean before this plan and its program-index link were added.
>
> **Authority boundary:** This document authorizes no provider call, model or
> dataset download, benchmark execution, 100K/1M run, threshold change,
> projection activation, promotion, or release. It defines the decisions and
> execution shape from which bounded work packets and an implementation DAG may
> be compiled.

## 1. Executive decision

Trace should retain a model-independent canonical Spine, but it should not
remain a model-free cognitive system.

The architecture is corrected as follows:

1. **CORE**, **RETRIEVAL**, **CORTEX**, and **SYNTHESIS** are distinct
   capability lanes with separate contracts, evaluations, budgets, and claims.
2. Engineering and research in those lanes may proceed in parallel once their
   shared contracts and evaluators are frozen.
3. Certification and promotion remain dependency-ordered. A Cortex result
   cannot repair or certify a failed Core result, and a Core result cannot be
   presented as proof of semantic organization.
4. Semantic condensation belongs in the Cortex. It runs asynchronously over
   bounded, changed source neighborhoods and produces evidence-anchored,
   revisioned, rebuildable projections.
5. No particular language-model family or size is canonical. Trace selects the
   smallest model or cascade that passes prospective quality, faithfulness,
   privacy, latency, throughput, and cost gates.
6. A million-document run is a release-scale experiment, not the inner loop
   for retrieval or Cortex development. Mechanisms must earn admission through
   smaller frozen experiments first.

The previous statement "G1M-HYBRID starts only after G1M-CORE" remains valid
only as a **combined promoted claim order**. It must not prohibit Cortex
implementation, model bake-offs, shadow consolidation, or smaller-scale
evaluation before G1M-CORE passes.

## 2. North-star capability

Trace is intended to be a headless, self-organizing memory database that:

- preserves exact source truth, history, policy, and evidence independently of
  every learned or generated mechanism;
- turns new evidence into useful multi-resolution semantic organization rather
  than merely assigning every atom to a structurally valid container;
- retrieves exact and semantically relevant evidence quickly across direct,
  temporal, cross-domain, and multi-hop queries;
- can explain every result through resolvable source anchors and declared
  projection/model revisions;
- adapts derived organization without silently changing canonical truth;
- operates locally when required and uses remote models only under explicit
  policy, privacy, budget, and audit controls; and
- scales by bounding work and tiering active cognition, not by pretending every
  source byte needs permanent expensive model attention.

Scale, topology, and benchmark scores are evidence about this capability. They
are not the capability itself.

## 3. What is retained, corrected, and rejected

### 3.1 Retained non-negotiable principles

- The Spine is the canonical factual and temporal record.
- Source bytes, source revisions, atom identities, offsets, hashes, events,
  policy state, and evidence anchors remain recoverable and auditable.
- Cortex artifacts are derived, revisioned, replaceable, and rollbackable.
- Candidate projections remain invisible to ordinary reads until validated and
  atomically activated or explicitly selected for shadow evaluation.
- Retrieval must expand back to raw source atoms; a generated summary is never
  sufficient evidence for a factual answer.
- Work, graph traversal, model calls, storage, latency, and cost are bounded and
  observable.
- Evaluation inputs and thresholds are frozen prospectively. Implementers do
  not edit the evaluator that promotes their candidate.
- Independent verification and explicit Human Owner promotion remain required
  for release, certification, threshold changes, and high-impact topology.
- A model cannot excuse lost events, corrupt anchors, broken replay, privacy
  leakage, or unbounded resource use.

### 3.2 Corrected principles

| Previous interpretation | Corrected interpretation |
| --- | --- |
| Core must certify before Cortex work begins. | Core must certify before a combined promoted 1M claim; Cortex engineering starts as soon as shared contracts and evaluators are ready. |
| Offline implies model-free organization. | Offline permits pinned local embedding, reranking, extraction, and generative models. Model-free fallbacks remain controls and degraded modes. |
| Zero orphans and routing purity prove self-organization. | They prove structural coverage and assignment stability only. Semantic organization requires separate quality and utility evidence. |
| Extractive clipping is a sufficient hierarchy summary. | It is a deterministic control and emergency fallback, not the target condensation mechanism. |
| Every generated projection must replay byte-for-byte. | Canonical Spine and deterministic projections require exact replay. Generative projections require immutable inputs/configuration/output receipts, stable lineage, and reproducible regeneration within a declared equivalence policy. |
| Every useful semantic relation needs manual review. | Review is risk-tiered. High-impact factual/schema/topology changes remain human-governed; low-risk navigation projections may auto-activate after strict validation and sampled audit. |
| One latency ceiling covers Trace retrieval. | Direct retrieval, graph retrieval, background consolidation, deep navigation, and answer synthesis have separate SLOs and budgets. |
| Storage amplification against raw text alone is sufficient. | Core durability and Cortex projection economics are reported separately, plus total-system cost. Vector/graph/summary cost is normalized by documents, atoms, tokens, active set, and workload—not hidden in one ratio. |
| "Hybrid" is one capability. | Dense retrieval, graph navigation, semantic consolidation, and answer generation are separate mechanisms and must be independently ablated. |

### 3.3 Explicitly rejected directions

- Synchronous LLM calls in the canonical ingestion transaction.
- Calling a remote LLM once per document merely because a document was
  ingested.
- Treating generated summaries, labels, schemas, claims, or relations as Spine
  truth.
- Using a model-generated answer to hide failed evidence retrieval.
- Selecting a canonical model from reputation, parameter count, advertised
  speed, or price without Trace-specific evidence.
- Requiring another full 1M execution to tune a prompt, model, retrieval fusion
  weight, relation policy, or summary validator.
- Global all-pairs clustering or unbounded semantic graph construction.
- Silent fallback from a required semantic model to lexical or hashing-only
  behavior in an evaluation or promoted profile.
- Manufactured model responses, zero/unknown costs reported as free, or
  self-issued certification receipts.
- One agent implementing a candidate, changing its release evaluator, and
  verifying its own result.

### 3.4 Decision clauses for ratification

These stable provisional IDs let the follow-on DAG reference an exact decision
instead of paraphrasing this document. On acceptance, W0 must map each accepted
clause to a permanent decision-log entry without changing its meaning.

| ID | Decision clause |
| --- | --- |
| `CAP-D001` | Adopt CORE, RETRIEVAL, CORTEX, SYNTHESIS, and EVALUATION/CONTROL as distinct capability and claim lanes. |
| `CAP-D002` | Permit parallel engineering after shared-contract readiness; retain sequential candidate freeze, verification, scale authorization, and promotion. |
| `CAP-D003` | Keep canonical ingestion free of generative calls; run semantic consolidation asynchronously over bounded changed neighborhoods. |
| `CAP-D004` | Keep Spine state canonical and all learned/generated organization rebuildable, revisioned, evidence-anchored Cortex state. |
| `CAP-D005` | Require exact replay for canonical/deterministic state and declared reproducibility classes plus retained outputs/receipts for generative state. |
| `CAP-D006` | Select the smallest passing model or cascade empirically; use a strong hosted model only as a policy-approved teacher, upper bound, or escalation candidate. |
| `CAP-D007` | Use risk-tiered activation: validated navigation and retrieval-only projections may auto-activate; factual/schema/governance changes retain stricter review. |
| `CAP-D008` | Evaluate structural organization, semantic organization, direct retrieval, multi-hop retrieval, and synthesis with separate scorecards and paired ablations. |
| `CAP-D009` | Use small frozen experiments, then 10K and 100K gates before admitting a Cortex mechanism to 1M; never use 1M as a tuning loop. |
| `CAP-D010` | Reconcile storage, latency, freshness, throughput, and cost prospectively by lane and service class before freezing a candidate. |
| `CAP-D011` | Fail closed on missing models, invalid/empty output, unknown required identity, hidden fallback, incomplete denominators, and unavailable cost evidence. |
| `CAP-D012` | Preserve Human Owner authority over architecture, thresholds, credentials, provider spend, protected changes, scale execution, and promotion. |
| `CAP-D013` | Issue component claims and decisions separately; only a compatible, independently verified integrated release may support a combined Trace claim. |

## 4. Capability lanes and truth boundaries

| Lane | Responsibility | Canonical truth? | Typical execution | Primary proof |
| --- | --- | --- | --- | --- |
| **CORE** | Source capture, atomization, identities, WAL/events, history, policy, erasure, replay, recovery, projection release roots. | Yes, for source and governance state. | Synchronous capture plus durable asynchronous maintenance. | Retention, anchor validity, replay/recovery, isolation, throughput, storage, failure handling. |
| **RETRIEVAL** | Lexical search, pinned dense embeddings, fusion, reranking, temporal/policy filtering, bounded graph activation, raw-evidence bundles. | No; indexes and scores are rebuildable projections. | Immediate indexing/delta overlay and query-time bounded work. | Recall/nDCG/coverage, abstention, citation precision, latency, bounded work, index correctness. |
| **CORTEX** | Cluster/routing proposals, multi-resolution summaries, entities, schemas, claims, relations, contradiction/revision proposals, salience and consolidation policy. | No; all outputs are derived projections or proposals. | Asynchronous delta consolidation, periodic sleep/reconsolidation, shadow or active release. | Faithfulness, coherence, relation quality, navigation utility, retrieval uplift, stability, backlog, model economics. |
| **SYNTHESIS** | Optional natural-language answer, report, comparison, or deep research rendering over an evidence bundle. | No; rendering is disposable or explicitly saved as derived output. | User- or agent-requested query-time call. | Answer correctness, citation entailment, abstention, latency, token/cost and privacy compliance. |
| **EVALUATION/CONTROL** | Frozen corpora, judgments, manifests, thresholds, run custody, raw evidence, verification, and promotion. | Canonical only for accepted decisions and evidence records. | Independent of candidate implementation. | Identity integrity, denominator integrity, reproducibility, detached verification, human decision. |

Dense embeddings are part of the Retrieval lane even though they are learned
models. Generative semantic consolidation is part of the Cortex lane. A model
used for query-time navigation does not automatically make the final answer a
Synthesis result.

## 5. Target end-to-end lifecycle

```text
source bytes
  -> CORE capture and deterministic atomization
  -> canonical event/atom/source state
  -> lexical+dense delta indexing ---------------------> query retrieval
  -> bounded changed-neighborhood candidate assembly       |
  -> asynchronous CORTEX consolidation                     |
  -> validation and risk classification                    |
  -> candidate Cortex release                              |
  -> shadow evaluation -> activate / retain / reject       |
                                                           v
query -> RETRIEVAL fusion + optional graph/hierarchy -> raw evidence bundle
                                                           |
                                                           +-> cited result
                                                           +-> optional SYNTHESIS
```

### 5.1 Ingestion hot path

The hot path captures source truth and queues work. It must not wait for a
generative model. Local embeddings may be computed in a separate immediate
indexing stage when the accepted profile and hardware make that appropriate;
they are not part of the canonical source transaction.

An accepted ingestion returns at least:

- canonical ingestion/source/event identity;
- atomization status;
- lexical and dense indexing state;
- Cortex consolidation state/backlog position; and
- actionable degraded/failure state without claiming unavailable capability.

### 5.2 Cortex consolidation path

The consolidator operates on bounded candidate clusters formed from structural
neighbors, lexical/dense candidates, current hierarchy, temporal locality,
typed graph neighbors, and explicit workspace policy. It must never scan or
pair the entire corpus merely to process one delta.

For each run, it may produce:

- section and topic summaries;
- cluster labels and routing candidates;
- entity and normalized-concept candidates;
- atomic claims with supporting and contradicting anchors;
- typed relation candidates;
- schema/ontology candidates;
- uncertainty, novelty, conflict, and escalation signals; and
- a declaration that evidence is insufficient.

Every output binds source atom-version IDs, source checksum, consolidation run,
model/tokenizer/runtime revision, prompt/schema revision, decoding parameters,
policy revision, timestamps, usage/cost receipt, validator receipt, and parent
projection lineage.

### 5.3 Validation and activation path

Validation separates three questions:

1. **Is the output structurally admissible?** Schema, IDs, anchors, policy,
   bounds, and provenance are valid.
2. **Is the output faithful/useful?** Claims are supported, important evidence
   is covered, uncertainty is calibrated, and the target task improves or at
   least does not regress.
3. **May it activate automatically?** Its projection type and measured risk fit
   the accepted policy tier.

Passing structural validation alone never proves semantic quality.

## 6. Projection types and promotion policy

### 6.1 Required object types

The implementation DAG should converge on explicit, versioned contracts for:

- `ConsolidationRunManifest`
- `ModelRevision`
- `PromptRevision`
- `CandidateCluster`
- `SummaryProjection`
- `EntityCandidate`
- `ClaimCandidate`
- `RelationCandidate`
- `SchemaCandidate`
- `CortexValidationReceipt`
- `CortexReleaseManifest`
- `CortexActivationDecision`
- `ModelCallReceipt`
- `CortexEvaluationResult`

Names may change during contract design, but the identities and boundaries may
not be collapsed into one generic JSON blob without an explicit decision.

### 6.2 Risk tiers

| Tier | Examples | Default disposition |
| --- | --- | --- |
| **T0: disposable aid** | Query-time outline, unsaved explanation. | May be generated under request policy; never used as evidence. |
| **T1: navigation projection** | Bounded section summary, topic label, routing description. | May auto-activate after strict anchor/faithfulness/stability validation and sampled audit. |
| **T2: retrieval relation** | `associated_with`, similarity/routing edge, salience prior. | May activate inside bounded retrieval releases when evidence and precision thresholds pass; never presented as fact. |
| **T3: factual/typed claim** | `depends_on`, `contradicts`, causal or temporal assertion. | Pending proposal unless an accepted policy defines a high-precision automatic verifier and rollback path. |
| **T4: schema/governance change** | Ontology definition, policy, evaluator, threshold, release or deletion decision. | Human decision required. |

The objective is not to remove human authority. It is to spend human attention
on ambiguity and consequence instead of forcing manual approval of every safe
navigation artifact.

## 7. Reproducibility contract

### 7.1 Exact replay domain

The following require byte- or state-exact replay under their declared
contract:

- canonical events and source lifecycle;
- source bytes, revisions, atomization and anchors;
- deterministic identifiers and policy decisions;
- deterministic lexical/control projections; and
- accepted release manifests and activation history.

### 7.2 Generative regeneration domain

Generative Cortex outputs require:

- immutable source cluster identity;
- exact stored output bytes and output digest from the admitted run;
- model weight/API revision identity as far as the provider exposes it;
- tokenizer, prompt, response schema, decoding and runtime identity;
- raw, redacted provider receipt and measured usage/cost;
- validator identity and result;
- lineage to the preceding projection; and
- an explicit reproducibility class:
  `bit_reproducible`, `semantically_reproducible`,
  `receipt_replay_only`, or `provider_revision_unavailable`.

An inability to reproduce the exact text later does not corrupt the Spine. It
may, however, make that Cortex release ineligible for promotion or require its
stored output to remain available for audit.

## 8. Model strategy

### 8.1 No predetermined minimum model

DeepSeek Flash is a teacher/upper-bound candidate, not an architectural
minimum. Parameter count is not a gate. The initial bake-off should include:

1. deterministic extractive control;
2. a local 3-4B instruction model where supported;
3. a local 7-9B instruction model as the likely primary candidate tier;
4. a local 12-14B model only where hardware/offload economics are viable; and
5. one policy-approved strong hosted model as teacher, upper bound, and
   difficult-case escalation comparator.

Exact model names, quantizations, licenses, runtimes, and provider endpoints
are selected in a separate frozen model-admission record after current hardware
discovery. No model is downloaded or called merely by accepting this plan.

### 8.2 Selection rule

Choose the smallest local model or bounded cascade whose lower-confidence
quality results meet the prospective thresholds. Escalate only clusters that
trip declared uncertainty, disagreement, novelty, complexity, or validation
signals. Measure the cascade as a system; do not report the cheap model's cost
while silently relying on a larger teacher for difficult cases.

### 8.3 Cost accounting

Local does not mean free. Record:

- wall time, model loading and warm/cold throughput;
- CPU, GPU, RAM, VRAM, energy when observable, and contention;
- tokens/second, input/output tokens, retries and invalid-output rate;
- storage for weights, caches, outputs and projection growth;
- hosted input/output/cache charges and failed/retried calls; and
- cost per source token, atom, document, accepted projection, and useful
  retrieval improvement.

Unknown pricing or usage is `unknown` and blocks a cost-qualified claim. It is
never coerced to zero.

## 9. Evaluation architecture

### 9.1 Separate capability scorecards

| Scorecard | Required measures |
| --- | --- |
| **CORE** | Source/atom retention, anchor verification, replay/recovery, lifecycle/erasure, index watermark coverage, ingestion throughput, backlog, disk/RSS and fault behavior. |
| **RETRIEVAL-DIRECT** | Recall, nDCG, complete-gold coverage, citation precision, abstention and latency for exact/domain semantic lookup. |
| **RETRIEVAL-MULTIHOP** | Per-hop evidence recall, complete-chain coverage, path precision, graph work, failure/abstention and end-to-end latency. |
| **CORTEX-SUMMARY** | Atomic-claim support, contradiction rate, evidence coverage, omission, compression, coherence, stability/churn, navigation utility and human preference. |
| **CORTEX-RELATION** | Typed-relation precision/recall, evidence validity, confidence calibration, graph utility, degree/work growth and temporal correctness. |
| **CORTEX-SYSTEM** | Retrieval uplift by query class, no-regression slices, consolidation throughput/backlog, incremental/full equivalence, storage and model economics. |
| **SYNTHESIS** | Answer correctness, citation entailment, unsupported-claim rate, useful abstention, latency, tokens/cost and privacy behavior. |

SciFact, NFCorpus and FiQA primarily inform direct/domain retrieval. MuSiQue or
MultiHop-RAG primarily informs evidence-chain assembly. Neither is sufficient
by itself to certify semantic condensation or general Trace usefulness.

### 9.2 Required baselines and ablations

Every Cortex experiment compares the same frozen inputs across at least:

- lexical only;
- pinned dense only;
- lexical+dense fusion;
- fusion+reranking;
- deterministic hierarchy/control summaries;
- model-generated hierarchy without proposed relations;
- relations/graph without generated summaries where meaningful;
- full Cortex retrieval without answer synthesis; and
- optional synthesis over the identical frozen evidence bundle.

This prevents gains from one mechanism being credited to another.

### 9.3 Faithfulness gate

The current token-overlap heuristic is not a sufficient faithfulness gate. The
replacement evaluation must:

- split summaries into atomic propositions;
- map each proposition to resolvable supporting and, where present,
  contradicting source spans;
- distinguish supported paraphrase from unsupported novelty;
- measure omission of material cluster content;
- preserve uncertainty and conflict rather than forcing consensus;
- include deterministic adversarial cases and a frozen human-reviewed sample;
- use an independent verifier/model only as supporting evidence, never as the
  sole judge of another model; and
- retain raw judgments and disagreements.

Automatic publication requires 100% valid source identity/anchor coverage and
zero known critical unsupported claims. Numeric precision, preference, uplift,
and sampling thresholds must be chosen prospectively by the Human Owner before
the bake-off; they may not be relaxed after seeing a candidate result.

The 95% proposition-support target below is a bake-off admission threshold
across the frozen evaluation set, not permission to knowingly publish the other
5%. Every factual proposition in an auto-active navigation summary must be
supported by its anchors, explicitly represented as uncertain/conflicted under
an accepted contract, or omitted.

### 9.4 Storage and latency policy correction

Report at least three storage views:

1. **Core amplification:** canonical hot durability state versus canonical raw
   admitted bytes.
2. **Cortex amplification:** active lexical/vector/graph/hierarchy/summary state
   by source tokens, atoms, documents, and active working set.
3. **Total operating footprint:** active state, temporary build headroom,
   retained rollback release, model weights/cache, snapshots and recovery
   reserve.

The existing `<=3.0x` rule must not be silently removed or relaxed. Before a
new candidate freezes, the Human Owner must decide whether it remains a Core
gate, a total-system gate for a named workload, or is replaced prospectively by
component budgets that preserve an explicit total-cost ceiling.

Latency must be reported by lane and service class:

- direct lexical/dense retrieval;
- reranked retrieval;
- graph/hierarchy retrieval;
- bounded deep navigation;
- asynchronous consolidation throughput/backlog; and
- optional synthesis.

A background consolidation task is not required to satisfy an interactive
query SLO. A query cannot hide unacceptable stale-projection lag merely because
its foreground latency is low.

### 9.5 Provisional Cortex and Synthesis promotion targets

These are recommended starting decisions for Human Owner ratification at Gate
A, not thresholds silently activated by this planning document. Gate A may
amend them before any candidate or promotion set is exposed.

| Capability | Recommended initial target |
| --- | --- |
| Cortex identity/provenance | 100% resolvable source membership and evidence anchors; zero active orphan members. |
| Summary factual support | At least 95% supported atomic propositions on the frozen held-out set, with 95% confidence intervals, and zero known critical unsupported propositions. |
| Summary usefulness | At least 70% reviewer approval/usefulness on the frozen sample, preserving the existing pilot bar while replacing extractive-only scoring. |
| High-confidence relation tier | At least 90% precision before a relation may influence an active retrieval release automatically; factual typed relations otherwise remain proposals. |
| Retrieval contribution | Prospectively significant improvement in the targeted class, normally practical effect `>= +0.030` or an accepted equivalent, with no material regression in unaffected classes. |
| Synthesis grounding | 100% citation-anchor validity, at least 90% citation precision, and at least 95% supported atomic factual propositions on the frozen set. |
| Synthesis abstention | At least 90% accuracy on held-out unanswerable cases; a provider error or empty output is not an abstention pass. |

All percentages use complete denominators that include failures and empty
outputs. A single evaluator model cannot be the sole source of a faithfulness
or correctness judgment. Results must report uncertainty and category slices;
the zero-critical-defect rule is not represented as a universal zero-
hallucination claim.

## 10. Program workstreams and responsibility split

The detailed DAG may create more nodes, but it must preserve these ownership
boundaries.

| Workstream | Primary responsibility | Required outputs | Must not own |
| --- | --- | --- | --- |
| **W0 Architecture/governance** | Reconcile charter, invariants, decisions, vocabulary and precedence. | Accepted decision request, contradiction ledger, amended canonical docs. | Candidate implementation or self-verification. |
| **W1 Evaluation/data** | Freeze datasets, cluster samples, judgments, metrics, baselines and result schemas. | Evaluation manifest, judgment capsule, metric implementations, negative tests. | Tuning candidate prompts/models after promotion data is exposed. |
| **W2 Model gateway/economics** | Fail-closed invocation, registry, local/hosted adapters, receipts, privacy and budgets. | Provider/model admission contract, usage/cost accounting, failure tests. | Choosing winners or certifying quality. |
| **W3 Retrieval** | Establish honest lexical+dense+fusion+rerank baseline and bounded graph hooks. | Pinned indexes/models, query-level results, ablations, latency/work evidence. | Crediting Cortex before separate ablation. |
| **W4 Cortex contracts/releases** | Typed projection objects, lineage, candidate isolation, validation and activation. | Schemas/migrations, release manifest, rollback, historical visibility tests. | Generative quality evaluator. |
| **W5 Cortex generation** | Bounded cluster assembly, summaries, entities, claims and typed relation proposals. | Local-first generators, prompt/schema revisions, abstention and invalid-output behavior. | Auto-promoting high-impact schemas or facts. |
| **W6 Runtime/jobs** | Delta scheduling, leases, retries, cancellation, backpressure, checkpoints and observability. | Restart-safe worker flow, backlog telemetry, idempotency and recovery tests. | Changing semantic thresholds. |
| **W7 Model bake-off/research** | Execute frozen comparisons and uncertainty/escalation studies. | Raw outputs, scorecards, cost frontier, smallest-passing recommendation. | Editing frozen evaluator or promoting its own recommendation. |
| **W8 Scale/integration** | Run admitted 10K, 100K and later 1M shadow/candidate stages. | Resource/recovery evidence, release compatibility, scale dossier. | Skipping readiness gates or changing policy post hoc. |
| **W9 Independent verification** | Reproduce from frozen identity and test hostile failure cases. | Detached verification report and exact artifact digests. | Candidate authorship or promotion. |

The coordinator owns dependencies, packet quality, contradiction resolution,
integration sequencing, and evidence synthesis. The Human Owner owns
architecture/value decisions, credentials, thresholds, provider spend,
protected mutations, scale-run authorization, and promotion.

No more than three mutable implementation tasks should run concurrently until
the contracts stabilize. Read-only research and verification preparation may
proceed in parallel when they do not leak held-out judgments.

## 11. Execution waves

### Wave A - accept and reconcile the correction

Objective: make the new lane boundaries authoritative before implementation.

Required outcomes:

- Human Owner accepts, rejects, or amends `TRACE-CAP-001`.
- The decision log records the exact superseding clauses.
- A contradiction ledger maps every conflicting active document and prompt.
- The materially different numerical policies in `DEC-P-005`, the active scale
  policy lock, and `docs/v2-architecture.md` are reconciled prospectively into
  one profile/versioned policy table.
- `benchmarks/policies/scale_policy_level2.lock.json` is checked against the
  actual decision log. If its claimed Human Gate D authority has no accepted
  decision record, it is reclassified as prospective rather than silently
  treated as authorization.
- `Hybrid` is replaced by the precise lane name in new work.
- Legacy packets and evidence remain immutable historical records.
- No task can infer that Cortex development is blocked on a 1M Core pass.

**Gate A:** one unambiguous precedence chain exists and every downstream packet
can name its governing decision digest.

### Wave B - repair measurement and model-call integrity

Objective: make small experiments trustworthy before improving algorithms.

Parallel bounded tracks:

- freeze Cortex evaluation objects, cluster samples, held-out judgments and
  scorecard schemas;
- remove manufactured model-response fallbacks and fail closed on invalid or
  empty output;
- implement explicit unknown/nonzero cost semantics and complete usage receipts;
- define local-model admission/runtime identity and privacy policy;
- establish a real pinned dense+fusion retrieval baseline; and
- define typed Cortex projection/run/validation contracts; and
- freeze golden evidence bundles so Synthesis can be developed without waiting
  for a candidate retriever or gaining write access to evaluated state.

**Gate B:** the same frozen fixture can execute control and candidate paths,
retain raw outputs, expose every fallback/failure, and produce independently
recomputable metrics. No provider spend is implied until separately approved.

### Wave C - bounded model and mechanism bake-off

Objective: decide whether semantic Cortex mechanisms earn implementation
priority without a scale-run confounder.

Use a small but real, diverse, frozen corpus and held-out cluster/query sets.
Compare the model tiers and ablations in Section 9. The initial experiment must
fit within a separately accepted time, privacy and cost envelope.

Synthesis experiments, if included, consume only the frozen golden evidence
bundles and produce no writes to the evaluated Spine or Cortex. This separates
answer quality from retrieval failures during early development.

**Gate C:** select the smallest passing model/cascade per task, retain negative
results, and state separately whether summaries, relations, navigation, and
retrieval improved. A winner at this gate is experimental, not production or
scale-qualified.

### Wave D - integrated 10K shadow Cortex

Objective: prove the asynchronous lifecycle and operational shape.

Required evidence includes:

- ingest is not blocked by generative consolidation;
- delta candidate assembly is bounded;
- crash/retry/resume does not duplicate or lose work;
- candidate projections remain isolated;
- shadow retrieval names the exact Cortex release;
- activation and rollback are atomic;
- backlog, churn, storage, throughput and resource use remain within the frozen
  envelope; and
- source anchors and privacy policy survive every path.

**Gate D:** the end-to-end lifecycle is useful and restart-safe at 10K without
unbounded review or work.

### Wave E - real 100K paired qualification

Objective: assess Core, Retrieval, and Cortex on the same frozen source
snapshot while preserving separate claims.

Run the accepted Retrieval baseline and Cortex candidate in paired shadow
profiles. Evaluate direct, multi-hop, temporal, organization, recovery and
economics scorecards. Synthesis, if tested, uses the identical retrieved
evidence and remains a separate result.

First freeze and verify the compatible Core, Retrieval, Cortex, and optional
Synthesis component releases separately. Then bind their exact identities in
an `IntegratedReleaseManifest` for retrieval-only, retrieval+Cortex, and
retrieval+Cortex+Synthesis shadow ablations. Each component receives its own
limitation statement and decision; the integrated manifest cannot upgrade a
failed component claim.

**Gate E:** independently verified 100K results justify either promotion to a
bounded active profile, repair, rejection, or additional investigation. A
Cortex pass cannot overwrite an unresolved Core/Spine failure.

### Wave F - repaired 1M Core candidate

Objective: complete the existing honest Core/storage/recovery scale claim after
its readiness prerequisites pass.

This wave follows the accepted 100K-to-1M custody and evidence controls. It does
not need a generative provider and does not claim semantic self-organization.
The admitted Retrieval configuration may change only through a prospective,
verified migration decision; it is not frozen forever merely because it was
used at 100K.

Before the single frozen candidate, run non-certifying 250K, 500K, and 750K
diagnostics (or the exact ladder accepted at Gate D) with the complete Core and
serving-index path. Cortex consolidation may run asynchronously to the declared
coverage target; hosted teachers remain sampled comparators, and Synthesis is
evaluated only on the frozen query pack—not once per document.

Core capacity measurements must not be confounded by concurrent Cortex or
Synthesis resource use. Run a declared Core-only profile first, then a separate
combined/background-consolidation profile against an immutable copy or the same
frozen source release with isolated accounting. Retrieval serving indexes are
included only when the claim and policy name them explicitly.

**Gate F:** independently verified G1M-CORE plus explicit Human Gate decision.

### Wave G - optional 1M Cortex and combined-system gate

Objective: measure the cost and usefulness of semantic organization at 1M only
after the 10K/100K mechanism has earned scale admission and the Core candidate
is stable enough to host it.

This may be a shadow release, sampled/tiered consolidation, or full active-set
consolidation depending on the accepted service class. It need not call a model
for every document. Report unconsolidated/stale coverage explicitly.

**Gate G:** separate G1M-CORTEX and optional G1M-SYNTHESIS results, followed by
an explicit decision about any combined Trace claim. Nothing in this gate may
retroactively certify Gate F.

## 12. Hard readiness dependencies for the DAG

The exhaustive DAG must encode at least these edges:

1. Accepted architecture decision -> canonical document reconciliation -> all
   mutable implementation packets.
2. Frozen evaluation contract -> retrieval/Cortex candidate comparison.
3. Fail-closed model gateway + complete receipts -> any hosted-model bake-off.
4. Typed projection/run contracts -> semantic generator persistence.
5. Candidate isolation + rollback -> auto-activation experiments.
6. Pinned dense retrieval baseline -> claims of Cortex retrieval uplift.
7. Small frozen bake-off -> 10K shadow admission.
8. Verified 10K lifecycle -> 100K Cortex admission.
9. Independently verified 100K results -> 1M Cortex admission.
10. Core readiness/custody gates -> frozen G1M-CORE execution.
11. Independent verifier output -> Human Owner promotion decision.

It must **not** encode G1M-CORE completion as a prerequisite for beginning
Cortex contracts, evaluator work, model safety repairs, small bake-offs, 10K
shadowing, or 100K paired research.

## 13. Required DAG-node schema for the follow-on agent

Every node produced from this plan must include:

- stable node ID and lane/workstream;
- objective and explicit non-goals;
- governing decision/invariant IDs;
- prerequisites and typed dependency reason;
- pinned repository/base/source/evaluator/model/prompt/policy identities as
  applicable;
- allowed paths and mutation authority;
- named owner role and separate verifier role;
- inputs, expected outputs and artifact schemas;
- deterministic acceptance commands or review procedure;
- raw evidence and receipt requirements;
- time, token, provider, storage and compute budgets;
- fallback/degraded behavior;
- stop conditions and escalation owner;
- rollback/recovery obligations;
- claim ceiling (`C0` through `C5` or the current replacement vocabulary); and
- successor nodes unlocked by verified completion and, separately, by human
  promotion.

The implementation DAG must be acyclic even though the knowledge graph and
research feedback loops are cyclic. Feedback creates a new revision/wave; it
must not mutate a completed node's frozen inputs.

### 13.1 Seed node families

The detailed DAG should expand, not erase, these seed families:

- `CAP-A*` - decision acceptance, precedence and contradiction reconciliation;
- `CAP-EVAL*` - data/judgment/metric/result-contract preparation;
- `CAP-GW*` - gateway failure semantics, model registry, privacy and economics;
- `CAP-RET*` - honest dense/fusion/rerank retrieval baselines;
- `CAP-CRX*` - Cortex objects, consolidation, validation and release lifecycle;
- `CAP-JOB*` - asynchronous scheduling, leases, backlog and recovery;
- `CAP-MOD*` - frozen model bake-off and cascade experiments;
- `CAP-INT*` - 10K and 100K paired integration;
- `CAP-SCALE*` - separately authorized 1M Core/Cortex runs; and
- `CAP-VER*` - detached verification and human decision dossiers.

Do not create umbrella nodes such as "implement Cortex" or "fix retrieval."
Each mutable node should fit one isolated worktree, one owner, one coherent
artifact set, and one independent verification boundary.

## 14. P0 implementation findings that shape the first wave

These are current-state anchors for planning, not a complete audit or proof of
behavior:

1. `src/trace/v2/organization.py:22-29` currently builds summaries from clipped
   excerpts joined with separators. This remains the deterministic control but
   is not the target Cortex summarizer.
2. `src/trace/v2/organization.py:58-70` accepts a configurable 5% token-overlap
   floor and reports full coverage. It is a smoke check, not a semantic
   faithfulness validator.
3. `TraceService.run_cognitive_delta(..., model_id=...)` passes the model to
   schema proposal but not hierarchy generation (`service.py:2109-2132`). The
   public signature therefore overstates model-assisted consolidation.
   Hierarchy materialization is also duplicated between `organization.py` and
   `service.py`; all hierarchy, delta, and cognitive entry points should converge
   on one `CortexConsolidator` contract.
4. The job system has a `cognitive.delta` handler, but ingestion queues only
   indexing and successful indexing does not enqueue the Cortex dependency
   chain (`service.py:571-599`, `3442-3461`). Extend the existing lifecycle with
   `index-ready -> candidate consolidation -> validation -> release assembly ->
   activation`; do not introduce an unrelated scheduler.
5. The model registry supports `hierarchy_summary`, but the hierarchy builder
   does not invoke that gateway path. Local and hosted generators must share one
   hardened invocation/receipt contract.
6. `TraceModelGateway.call_json` currently manufactures schemas, renderings, or
   selected IDs when parsed output is empty (`model_gateway.py:578-610`). It can
   dynamically accept recognized model prefixes and marks calls as cloud even
   for potential local backends. Empty/malformed output must fail closed; model
   IDs, local/cloud execution, authorization and privacy policy must be explicit.
7. Registered model cost coefficients default to zero, input estimates omit
   material prompt/output costs, and persisted audits lack parts of the exact
   input/output/policy identity. Unknown costs and actual zero-API-cost local
   profiles must be distinguishable, with budget reservation and settlement.
8. Projection/release validation currently trusts caller-supplied/default-pass
   receipts and can invent empty component metadata; activation is not fully
   journaled across the database and external aliases (`store.py:3513-3540`,
   `3600-3617`, `3812-3902`; `service.py:3628-3709`). Cortex work must first
   make component identity and detached validation fail closed and make
   activation/rollback reconcilable after a crash.
9. Generated hierarchy state can become active without a meaningful semantic
   validation stage. Candidate, validated, shadow, active, rejected, and failed
   states must be explicit; failure leaves the previous release active.
10. The retrieval engine already exposes lexical, dense, fusion, reranking,
    hierarchy and graph mechanisms, but hashing/heuristic defaults and provider
    degradation cannot support a required semantic lane. Scale runners must use
    the canonical configured path, and hierarchy navigation must avoid
    whole-table substring scans before scale qualification.

Before mutation, each assigned worker must re-anchor these observations to its
frozen base commit and report drift.

### 14.1 First-wave negative and recovery tests

Wave B work packets must require at least:

- empty, malformed, nested-invalid, unsupported and uncited model output fails
  closed while preserving a complete failure audit;
- unregistered/dynamic model IDs are rejected, local execution does not require
  cloud permission, and route authorization is consistent across hierarchy,
  schema, navigation and synthesis calls;
- concurrent budget reservations cannot overspend and actual usage settles the
  reservation without treating unknown price as zero;
- identical retries are idempotent, while source/model/prompt/policy/runtime
  changes create a new projection revision;
- generated candidates are invisible until detached validation and explicit
  policy/human activation;
- empty, invented or default-pass release components/receipts are rejected;
- crash-point tests prove database release pointers and external index aliases
  converge on activation and rollback;
- job heartbeat, lease expiry, cancellation, retry, dependency-resume and
  backpressure behavior retain exactly one durable outcome; and
- semantic hierarchy retrieval preserves authorization and raw-atom expansion
  while avoiding an unbounded/table-scan navigation path.

## 15. Canonical-document amendment map

After Human Owner acceptance, W0 should prepare precise, minimal amendments to:

| Document | Required correction |
| --- | --- |
| `docs/program/00_CHARTER.md` | Add semantic condensation and adaptive organization to the mission; clarify parallel engineering versus sequential claims. |
| `docs/program/01_INVARIANTS.md` | Separate exact Spine replay from generative-output reproducibility classes; add model-call/evidence rules. |
| `docs/program/02_EXECUTION_DAG.md` | Add parallel Cortex research/implementation nodes and separate Core/Cortex/Synthesis scale gates. |
| `docs/program/03_SHARED_CONTRACTS.md` and `docs/schemas.md` | Add the typed run, model/prompt, candidate projection, validation, release, receipt and error contracts required by Section 6. |
| `docs/program/04_EVALUATION_PROTOCOL.md` | Replace proxy-only organization evidence with the separate scorecards and ablations in this plan. |
| `docs/program/05_PROMOTION_RUBRIC.md` | Add risk-tiered projection activation, semantic utility, cascade economics and sampled audit. |
| `docs/program/06_DECISION_LOG.md` | Record the accepted correction; amend the DeepSeek baseline and Release Gate 2 wording prospectively. Do not rewrite historical decisions. |
| `docs/program/07_RISK_REGISTER.md` | Add hallucination, semantic drift, review saturation, provider drift, consolidation debt and evaluation leakage risks. |
| `docs/program/SCALE_100K_TO_1M_EXECUTION_PLAN.md` | Preserve G1M-CORE custody while replacing the blanket post-Core Hybrid-development reading with separate G1M-CORTEX and G1M-SYNTHESIS claims. |
| `docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md` | Reconcile its permitted read-only Hybrid evaluator with the four-lane claim model and ensure Core-only versus combined resource profiles cannot be confused. |
| `docs/program/README.md`, `docs/SCALE_PROGRAM.md`, and `docs/SCALE_MASTER_PLAN.md` | Update active-program routing and precedence so workers discover this accepted correction before stale execution wording. |
| `docs/SCALE_DECISION_REGISTER.md` and `docs/program/CONTROL_PLANE_LOCK.json` | Bind the accepted decision and current policy/plan identities without rewriting historical entries. |
| `docs/program/FOUNDATION_STATUS.md` and `docs/program/FOUNDATION_GATE_DOSSIER.md` | Reclassify any proxy-only structural organization claim; retain achieved lifecycle evidence at its actual claim level. |
| `README.md` and `docs/phase1-local-first.md` | Preserve and scope the extractive-only Phase 1/control contract; distinguish its query plugins from V2 asynchronous Cortex providers, then document the separately gated abstractive policy. |
| `docs/v2-architecture.md` | Specify model-assisted hierarchy/claim/relation contracts, validation, reproducibility classes and tiered activation. |
| `docs/benchmark-studio.md` | Separate benchmark profiles and telemetry for Retrieval, Cortex, and Synthesis; prevent a Studio rendering from becoming certification evidence. |
| `docs/SCALE_HARD_PROBLEMS.md` | Add model-compute tiering, consolidation scheduling and semantic projection economics to the scale cliffs. |
| `docs/future-scale-roadmap.md` | Make bounded active cognition and sampled/tiered reconsolidation explicit at larger scales. |
| active global prompts, role briefs, and launch material | Remove language that tells workers Cortex development is blocked until a 1M Core pass or that one named model is canonical without evidence. |

Historical inbox packets, run dossiers and forensic reports remain immutable.
New documents supersede their planning assumptions through precedence and
decision references; they do not alter the historical record.

## 16. Risks and mandatory stop rules

| Risk | Required control | Stop condition |
| --- | --- | --- |
| Hallucinated condensation | Atomic claims, anchors, contradiction checks, abstention, shadow release. | Critical unsupported claim in an auto-activation candidate. |
| Semantic drift/churn | Stable cluster identity, parent lineage, change thresholds, retained predecessor. | Unbounded neighborhood churn or inability to explain a changed projection. |
| Review saturation | Risk tiers, confidence/calibration, sampling, escalation queue metrics. | Review backlog grows without a bounded drain policy. |
| Model/provider drift | Pinned local weights or provider revision receipts, canaries, retained outputs. | Provider identity or behavior changes during a frozen run. |
| Cost explosion | Preflight estimates, hard budgets, cascade telemetry, cancellation. | Missing/unknown receipt, budget breach, or projected scale cost exceeds authority. |
| Consolidation debt | Backpressure, priority, checkpoints, freshness coverage and degraded state. | Backlog grows faster than bounded steady-state capacity. |
| Privacy leakage | Workspace policy, redaction, local-only profiles, audit. | Unauthorized text reaches any model/provider. |
| Retrieval regression | Paired ablation, query-class slices, raw results, rollback. | Prospective no-regression or critical-lane threshold fails. |
| Evaluation leakage | Separate custody, held-out data, frozen manifests. | Candidate owner accesses or changes held-out judgments/evaluator. |
| Scale-run thrashing | Readiness gates and smaller ladders. | Any request to rerun 1M for an unresolved small-scale mechanism question. |

Failures produce retained evidence and a repair/reject decision. They do not
trigger silent fallback, threshold adjustment, result deletion, or an automatic
larger-model escalation.

## 17. Definition of program success

This correction succeeds when Trace can truthfully demonstrate all of the
following as separate, composable claims:

1. **Core truth:** exact evidence survives ingestion, update, failure, replay,
   policy and erasure at the admitted scale.
2. **Retrieval quality:** a pinned, no-fallback retrieval release finds the
   correct source evidence with bounded latency and work.
3. **Semantic organization:** the Cortex creates faithful, useful, stable
   multi-resolution organization and relations that improve the intended tasks
   enough to justify their cost.
4. **Operational cognition:** consolidation is asynchronous, incremental,
   restart-safe, privacy-safe, economically bounded and observable.
5. **Optional synthesis:** generated answers remain grounded in the retrieved
   evidence and abstain when evidence is insufficient.
6. **Governance:** every active release and public/internal claim is bound to
   immutable identities, independent verification and an explicit Human Owner
   decision.

Passing G1M-CORE alone proves Item 1 at 1M plus only those retrieval/operations
claims explicitly evaluated. It does not prove semantic self-organization.
Passing a Cortex bake-off proves neither 1M durability nor production fitness.
Only the combined, separately evidenced gates justify the combined Trace claim.

## 18. Immediate handoff

The next agent should not implement code. It should transform this plan into:

1. a contradiction ledger with exact active-document clauses and proposed
   replacements;
2. a decision request for Human Owner acceptance;
3. an exhaustive acyclic DAG using the schema in Section 13;
4. the first bounded work packets for Wave A and Wave B only;
5. a responsibility/lease map with no implementer-verifier collision;
6. a gate matrix showing which completion evidence versus human decision
   unlocks each successor; and
7. a consistency report proving the DAG has unique IDs, no missing dependencies,
   no cycles, explicit budgets, and no path from unverified model output to
   canonical truth or release promotion.

The first implementation dispatch occurs only after the Human Owner accepts
the corrected direction and the Wave B packets are independently reviewable.
