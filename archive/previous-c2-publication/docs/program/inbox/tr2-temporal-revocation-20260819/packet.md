# TR2 - Trace Temporal Truth, Revocation, and Historical Retrieval

> **Role:** Trace engineer; independent verifier
>
> **DAG node:** T3 / TR2
>
> **State:** Blocked pending TR1 and accepted P-004. This packet must not use
> retrieval ranking heuristics as truth semantics.

## 1. Objective

Add the first explicitly governed temporal/source-lifecycle contract to Trace:
system/event time, valid/effective time, supersession, source lifecycle,
policy-first historical visibility, and release selection consistent with a
requested historical point.

## 2. Decision contract required from P-004

P-004 must select:

- request fields for system time and valid/effective time;
- unknown/partial/uncertain time representation;
- source/fact lifecycle: active, superseded, revoked, tombstoned, redacted,
  legally purged where applicable;
- supersession representation: version lineage, typed relation, or both;
- whether/when a historical query can expose later revoked source;
- deletion retention/audit policy;
- relationship between policy snapshot and historical release;
- late-arriving correction and interval-conflict rules;
- evidence bundle fields/exclusion reason.

The safe default for ordinary readers is policy-denied for revoked/denied
content even when a system-time query could reconstruct historical state.

## 3. Implementation requirements

1. Extend request/result contracts with explicit system time and valid time.
2. Store source/fact valid intervals with anchor, precision, and unknown state.
3. Event supersession/revocation/tombstone/deletion-policy transitions in Spine.
4. Apply authorization/policy before historical evidence exposure.
5. Make hierarchy, affinity, priors, lexical/dense selection resolve release
   appropriate to requested system time, not merely today active release.
6. Ensure valid-time filtering and source lifecycle affect every retrieval
   channel consistently.
7. Include requested time, resolved event watermark/release, valid-time result,
   lifecycle state, policy result, and exclusion reasons in evidence bundle.
8. Preserve replay/audit while distinguishing retained tombstone from readable
   content.

## 4. Acceptance tests

- current versus historical revision;
- effective-time interval query;
- late-arriving correction;
- supersession chain;
- revoked source;
- tombstoned/redacted source;
- denied historical read;
- deletion/purge policy behavior;
- as_of release pointer selection;
- rollback across release history;
- multi-tenant/policy isolation.

## 5. Non-goals

- LLM-only temporal resolution;
- treating ingestion time as effective time when unknown;
- bypassing policy for convenient evaluation;
- changing benchmark thresholds/data policy;
- distributed scale design.

## 6. Required artifacts

- accepted P-004 decision and data/query contract;
- source-lifecycle state machine;
- schema/migration and replay/retention plan;
- temporal evidence-bundle schema;
- channel-by-channel temporal selector map;
- policy/revocation fault matrix;
- V1b report and capability update.
