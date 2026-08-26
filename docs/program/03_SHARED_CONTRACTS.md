# Shared Contracts

> **Status:** Draft outline. Schema details and compatibility rules will be
> added through reviewed decisions, not inferred by individual workers.

## 1. Evidence bundle

Every query or benchmark result should eventually identify:

- request and retrieval profile,
- result status and trust state,
- source artifact and atom identifiers,
- exact offsets and hashes,
- active projection/release identity,
- relevant channel scores and bounded work used,
- policy/redaction outcome,
- diagnostic correlation identifier.

The contract must represent insufficient evidence and unavailable or untrusted
derived state without fabricating an answer.

## 2. Projection and release lifecycle

The shared lifecycle vocabulary is:

```text
planned -> building -> validating -> active -> retired
                     -> failed
```

The detailed storage model may differ between Trace-Lite and Trace. The
semantic contract does not: normal reads resolve through a verified active
revision only, and failed candidates remain non-queryable.

## 3. Work packet

A work packet carries a bounded objective, base commit, allowed paths,
context/input hashes, non-goals, acceptance evidence, output locations,
timeout/retry limits, and handoff requirements. See
[templates/WORK_PACKET.md](templates/WORK_PACKET.md).

## 4. Dataset record

Every externally sourced dataset requires a human-readable provenance record:

- source and license,
- intended benchmark role,
- acquisition instructions,
- content/version checksum,
- permitted local staging location,
- transform and segmentation identity,
- known limitations and fallback prohibition.

Raw corpus data is not committed to the repository unless explicitly approved.

## 5. Promotion dossier

A promotion dossier links a candidate mechanism to its hypothesis, measured
benefits, ablations, risk analysis, release behavior, cost, rollback plan, and
recommendation. It is evidence for a human decision, not an automatic trigger.

## 6. Consumer conformance

Consumers test stable service outcomes: successful evidence retrieval, no
evidence, pending build, unavailable provider, stale/revoked evidence, denied
access, malformed input, duplicate request, and rollback visibility.

## 7. Contract identifiers and compatibility

Every cross-role or cross-system artifact carries:

| Field | Meaning |
| --- | --- |
| contract_version | Semantic schema version for consumers and evaluators. |
| artifact_id | Stable opaque identifier for the record or generated artifact. |
| created_at | UTC creation time. |
| producer | Component, task, and code revision that produced it. |
| input_manifest_id | Exact source/configuration/evaluation inputs. |
| correlation_id | Request, build, or run identity for logs and handoffs. |
| status | Lifecycle/validity state defined by the contract. |

Additive fields may be introduced in a compatible minor version. Renaming,
changing semantics, weakening required evidence, or changing status behavior
requires a new contract version and conformance fixtures.

## 8. Evidence-bundle contract outline

The future wire schema may differ between Trace-Lite and Trace, but a result
bundle should be semantically equivalent to:

~~~yaml
contract_version: "1.x"
request:
  request_id: opaque-id
  query: redacted-or-permitted-query-text
  retrieval_profile: direct|semantic|broad|multihop|temporal|abstention
  policy_context_id: opaque-id
result:
  status: evidence|insufficient_evidence|pending|unavailable|denied|stale|untrusted
  active_release:
    system: trace-lite|trace
    release_id: opaque-id
    source_revision_range: opaque-reference
  sufficiency:
    state: sufficient|ambiguous|insufficient
    reason_codes: []
  evidence:
    - artifact_id: opaque-id
      atom_or_version_id: opaque-id
      char_start: integer
      char_end: integer
      content_hash: sha256
      visibility: permitted|redacted|revoked
      relation_to_query: lexical|dense|hierarchy|activation|trusted_relation
      scores: {}
  work:
    candidate_count: integer
    graph_edges_examined: integer
    controller_actions: []
  diagnostics:
    correlation_id: opaque-id
    stage: retrieval|policy|release|provider
    safe_reason_codes: []
~~~

The bundle should expose why evidence was returned without exposing raw provider
secrets, disallowed content, candidate-only state, or unbounded internal graph
detail.

## 9. Result-status semantics

| Status | Client meaning | Retry/next action |
| --- | --- | --- |
| evidence | Anchored permitted evidence is available. | Consume under client policy. |
| insufficient_evidence | Retrieval did not meet the evidence threshold. | Ask a narrower question or ingest/organize more source. |
| pending | Relevant source exists but trusted derived state is not ready. | Poll job/status or use an explicitly permitted source-only path. |
| unavailable | Required service/provider/index is unavailable. | Follow redacted diagnostic action; do not fabricate a result. |
| denied | Policy prevents the requested evidence exposure. | Change authorization or request an allowed representation. |
| stale | A prior verified release may be readable but does not include newer source/policy state. | Surface freshness and let policy decide whether it is usable. |
| untrusted | Validation or provenance conditions failed. | Do not use result for an authoritative decision. |

## 10. Projection-release contract

A release is an atomic bundle of derived structures tied to a Spine/source
revision set. It has at least:

~~~yaml
release_id: opaque-id
workspace_id: opaque-id
projection_kind: hierarchy|vector|lexical|affinity|controller|bundle
state: planned|building|validating|active|retired|failed
source_snapshot:
  revision_or_watermark: opaque-reference
  source_manifest_hash: sha256
build:
  code_revision: git-or-build-id
  algorithm_config_hash: sha256
  model_and_embedding_fingerprints: []
  policy_snapshot_id: opaque-id
validation:
  structural: pass|fail
  provenance: pass|fail
  policy: pass|fail
  quality: pass|fail|not_applicable
  evaluator_manifest_id: opaque-id
activation:
  activated_at: utc
  supersedes: opaque-id|null
retention:
  rollback_until: utc-or-policy
~~~

Rules:

1. A candidate release can be inspected by its builder and verifier but is not
   selected by normal retrieval.
2. Activation is a single logical handover after all required validation passes.
3. A failed candidate retains diagnostics and evidence but cannot leak rows into
   normal queries.
4. Retirement preserves rollback and audit information until retention permits
   cleanup.

## 11. Dataset and evaluation-manifest contract

The data steward produces a record; the evaluation engineer assembles a run
manifest. The run manifest includes:

- immutable dataset-record identifiers and checksums;
- data-localization paths excluded from Git;
- transform/segmentation/judgment versions;
- query pack and exclusion policy;
- candidate and baseline configurations;
- required model/provider conditions;
- disallowed fallback assertions;
- hardware/runtime capture requirements;
- output location and retention policy.

The runner must mark a run non-certifying when any required input is missing,
altered, inaccessible, or replaced.

## 12. Work-packet contract details

A prepared packet is executable only when all fields are concrete:

| Section | Required detail |
| --- | --- |
| Objective | One bounded change, audit, or artifact; no compound roadmap. |
| Base | Repository, commit, worktree path, and relevant dirty-state note. |
| Inputs | Canonical document versions/hashes and code/evidence references. |
| Scope | Allowed paths, forbidden paths, external services, and data boundary. |
| Acceptance | Commands, fixtures, metrics, negative tests, and review criteria. |
| Outputs | Exact handoff, artifact, and evidence destinations. |
| Authority | Whether the worker may download, edit, run a provider, or request review. |
| Stop conditions | Ambiguities, destructive operations, policy issues, or scope growth requiring escalation. |

## 13. Consumer-conformance contract

Consumer fixtures must test at least one request for every result status and
verify that:

- opaque identifiers are stable enough for correlation but reveal no sensitive
  storage implementation;
- source anchors and visibility states are preserved;
- a client cannot request candidate releases by accident;
- retries distinguish pending from unavailable and denied;
- a rollback changes active-release identity predictably;
- advisory evidence does not grant Reflex action authority or replace
  Entorhinal's canonical journal.

## 14. Foundation contract clarifications

The release YAML earlier in this document is illustrative semantic shape, not
an accepted Trace physical schema. P-003 decides whether one release root owns
immutable component membership, how carried-forward components are represented,
and how external index aliases are prepared/compensated.

Until P-003/TR1:

- no worker interprets a projection-kind active flag as a unified Cortex
  Release;
- candidate affinity/activation state is a known isolation risk, not an
  acceptable implementation detail;
- evidence bundles may report a component revision but must not claim an
  atomic multi-component release that does not exist.

Until P-004/TR2:

- as_of_event means system/event history only where implementation applies it;
- event version range is not effective/valid time;
- historical read is never assumed to bypass revocation/policy;
- temporal evidence distinguishes requested time, resolved system watermark,
  valid-time result if supported, source lifecycle, and exclusion reason.

## 15. Certification-result contract

A certification result exists only when its evaluation manifest identifies:

1. immutable trace-bench source identity under P-007;
2. canonical runner/integration under P-008;
3. admitted/staged data and frozen evidence mapping;
4. fixed metric/query/exclusion/threshold policy;
5. product adapter commits/configuration;
6. secure provider/runtime environment;
7. query-level/aggregate output and error receipts;
8. explicit no-fallback preflight result.

Otherwise output is unit, regression, exploratory, or non-certifying
diagnostic evidence. It may be useful but never advances a release/scale gate.
