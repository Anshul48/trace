# T1 — Trace Cortex Release Audit and Migration Design

> **Role:** Trace engineer
> **State:** Ready for read-only dispatch after F0c context is available
> **DAG node:** T1

## Objective

Audit current Trace projection activation and produce the concrete migration
design required for a unified, candidate-scoped Cortex Release lifecycle. This
is a design/current-state packet, not a mutation authorization.

## Broad scope

- inspect current projection kinds, active-read selection, affinity visibility,
  migration patterns, recovery, and policy boundaries;
- record candidate-leakage and rollback risks as observed/not observed;
- identify the minimum release identity, validation, activation, retention, and
  rollback fields needed for P-003;
- identify interfaces affected by temporal/revocation work for P-004.

## Forbidden work

- no schema migration, production code change, data rewrite, cleanup, or
  temporal-semantic decision;
- no replacement of Trace's event/version/policy foundation with TL storage
  shortcuts.

## Required output

- current-state audit with file/schema anchors;
- one or more migration alternatives with tradeoffs;
- explicit P-003 and P-004 decision inputs;
- narrow successor packet proposal for T2/TR1 after human acceptance.

## Detailed execution contract - 2026-08-19

### Source paths to map

Refresh exact anchors for hierarchy objects/memberships/active reads, affinity
builder writes and neighbor reads, activation-prior schema/writes/reads,
lexical/dense revision controller/rollback, query as_of_event, historical
node/edge/hierarchy retrieval, evidence bundles, Spine replay, legacy
hierarchy, and fallback retrieval.

### Required read/write map

| Structure | Storage/adapter | Candidate ID | Active selector | Policy selector | Historical selector | Failure | Retention | Verifier test |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hierarchy | <...> | <...> | <...> | <...> | <...> | <...> | <...> | <...> |
| affinity | <...> | <...> | <...> | <...> | <...> | <...> | <...> | <...> |
| activation priors | <...> | <...> | <...> | <...> | <...> | <...> | <...> | <...> |
| lexical/dense | <...> | <...> | <...> | <...> | <...> | <...> | <...> | <...> |
| legacy hierarchy | <...> | <...> | <...> | <...> | <...> | <...> | <...> | <...> |

### P-003 alternatives

Compare:

1. complete rebuild of every component in a full release bundle;
2. release root with immutable component membership carrying forward validated
   components that meet shared Spine/policy snapshot constraints.

Assess atomicity, incremental cost, rollback, external index behavior, policy,
source watermark, recovery, retention, migration, verifier observability.
The design to evaluate is:

~~~text
workspace -> active Cortex Release -> named component revision -> derived rows
~~~

not independently active hierarchy/affinity/index rows.

### TR1 migration concerns

- additive forward-only migration; do not amend migration 004 blindly;
- release root, immutable membership, active pointer, parent release;
- planned/building/validating/validated/active/retired/failed state;
- source/event, source manifest, policy, code/config/model/index fingerprints;
- durable structural/provenance/policy/parity/quality receipt;
- release ID on affinity/priors and release-scoped affinity uniqueness;
- retained predecessor and active-release reads;
- external index prepare/validate/alias compensation;
- legacy compatibility/backfill/retirement;
- release identity in evidence/diagnostics/jobs/admin.

### P-004 input

Address system versus real-world valid time, uncertain time, source lifecycle,
supersession, revocation/tombstone/deletion, historical authorization,
historical release pointer, and late correction.

### Required artifacts

- input-manifest.json, repository-state.json;
- evidence/read-write-map.md;
- evidence/P-003-options.md and P-003-decision-request.md;
- evidence/P-004-options.md;
- evidence/TR1-successor-outline.md and TR2-successor-outline.md;
- commands.md and handoff.md.

## Claim boundary

The audit may show a design gap. It does not prove a live candidate-leakage or
temporal fault without an independent reproduction.
