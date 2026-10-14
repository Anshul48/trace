# Program Invariants

> **Status:** Ratified program invariants under `DEC-CAP-001` (`TRACE-CAP-001`). Any change to an invariant requires a reviewed decision record and an update to affected evaluators.

## 1. Truth versus projection

- Source artifacts, immutable atoms, event/version history, exact offsets,
  hashes, evidence anchors, temporal validity, and policy/review state are
  canonical truth (Spine).
- Trees, summaries, embeddings, lexical indexes, graph affinity, routing,
  scores, holons, and caches are rebuildable projections.
- Spine data and deterministic indexes require 100% bit-exact replay parity.
- Generative projections (summaries, holons, entity/relation proposals) require
  declared reproducibility classes, immutable prompt/model/runtime receipts, and
  permanent lineage anchors (`CAP-D005`).
- Query-time activation or synthesis may improve recall or reasoning but may
  never rewrite canonical truth.

## 2. Candidate isolation

- Derived state is built as a named candidate revision or build.
- Candidate rows are invisible to normal reads.
- Detached validation precedes atomic active-revision handover.
- Risk-tiered activation (`CAP-D007`): low-risk navigation summaries may
  auto-activate post-validation; high-risk factual/schema proposals require
  explicit human approval.
- Failure preserves the last verified active state and source Spine.
- Rollback targets an already verified release, not a fresh reconstruction.

## 3. Evidence and provenance

- Every material result must identify source data, transformation, configuration,
  model/provider where relevant, code revision, and evaluation manifest.
- Exact source evidence remains recoverable from retrieved output via UTF-8 byte
  spans.
- A plausible generated summary never substitutes for missing source evidence.

## 4. Evaluation integrity

- Certification uses real, downloadable, license-aware data and frozen query
  sets where applicable.
- Release paths fail closed on missing data, mock providers, synthetic
  substitutes, or disabled required retrieval stages.
- Internal fixtures remain useful regression evidence but are not external
  superiority claims.

## 5. Graph and semantic boundaries

- Structural relations, trusted evidence relations, soft affinity, and
  behavioral signals have distinct schemas, provenance, trust, and budgets.
- Soft affinity is never promoted to fact solely because it improves retrieval.
- Graph construction and query traversal are bounded and observable.

## 6. Operational boundaries

- Consumers receive a versioned evidence-bundle/service contract, not direct
  database, filesystem, or credential access.
- Provider credentials remain operator-managed and are not exposed to clients.
- Pending, unavailable, stale, denied, malformed, and untrusted conditions are
  explicit and actionable.

## 7. Agent boundaries

- One mutable task uses one isolated worktree.
- Human-owned charter, invariants, evaluators, and promotion rules are hashed
  into each work packet and cannot be modified by workers.
- Research, implementation, and verification are independently reviewable.

## 8. Invariant enforcement matrix

| Invariant | Design requirement | Required evidence | Violation response |
| --- | --- | --- | --- |
| Canonical truth | Source/event/version records remain independently reconstructible. | Replay, source coverage, offset/hash checks. | Stop promotion; repair or restore source path. |
| Candidate isolation | Derived candidate objects cannot influence normal reads. | Failed-build and active-pointer tests. | Quarantine candidate and block release. |
| Active-release validity | Activation follows structural, provenance, policy, and quality checks. | Validation report attached to release. | Retain prior active release. |
| Bounded retrieval | Graph/index/controller work has explicit query-class budgets. | Work, degree, latency, and resource telemetry. | Disable or narrow the mechanism. |
| Fail-closed evaluation | Missing required stages fail a release run. | Negative tests for every prohibited fallback. | Mark result non-certifying. |
| Evidence recoverability | Each result can return exact source anchors. | Query-level evidence bundle checks. | Treat output as untrusted. |
| Policy separation | Authorization/redaction precedes exposure of protected evidence. | Denied/redacted/tenant tests. | Block endpoint or release. |
| Independent verification | Certification is not only an implementer assertion. | Verifier handoff and fixed evaluator output. | Mark status unverified. |

## 9. Data lifecycle rules

### Canonical source material

Canonical source material is immutable or versioned. A correction, revocation,
or deletion request creates an auditable event and affects visibility according
to policy; it must not silently mutate historical evidence.

### Derived material

Summaries, vectors, hierarchies, graph edges, activation priors, and caches are
addressed by their build/release identity. They may be discarded, rebuilt, or
replaced once source and policy inputs are known.

### Evaluation material

Dataset manifests, query packs, judgments, code/configuration hashes, and run
metadata are retained as evidence. Raw private corpora remain in approved
external stores and are referenced by stable identifiers and checksums.

## 10. Query and response rules

A response path must preserve these distinctions:

| State | Required behavior |
| --- | --- |
| Evidence found and trusted | Return anchored evidence plus active release identity. |
| Evidence insufficient | Return an explicit insufficiency state; do not invent support. |
| Candidate build in progress | Return pending/stale state according to contract; do not expose candidate rows. |
| Provider/index unavailable | Return actionable, redacted diagnostics and last-known-good availability where applicable. |
| Policy denied/redacted | Return an authorization-aware response without leaking denied content. |
| Source revoked | Explain the visibility state without treating revoked material as current truth. |

## 11. Observability requirements

Every build, query, evaluation run, and agent task needs a correlation identity.
Logs may include stage names, counts, timing, configuration hashes, error
categories, and redacted traceback references. They must not emit secrets,
unredacted prompts, protected source text, or provider credentials.

Operational messages must describe the failing stage and recovery action. A bare
status code or generic failure is not an adequate contract for a human or
downstream worker.

## 12. Compatibility and migration rules

- A migration names the source schema/version, target schema/version, forward
  path, rollback behavior, and retained evidence.
- Backfills run as explicit jobs or candidate releases; normal reads retain a
  verified fallback only when it is marked as such and does not weaken truth.
- A change in a data contract requires fixture, API, and evaluator review.
- Cleanup of obsolete derived revisions occurs only after retention and rollback
  policies have been met; source evidence is never pruned as routine cleanup.
