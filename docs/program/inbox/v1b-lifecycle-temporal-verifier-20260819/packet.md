# V1b - Independent Lifecycle and Temporal Conformance Verification

> **Role:** Independent verifier
>
> **DAG node:** V2 / V1b
>
> **State:** Blocked pending relevant L1/TL2/TR1/TR2 handoffs, accepted
> decisions, and disposable verification environments.

## 1. Objective

Independently test derived candidate state never changes ordinary reads before
validated activation, rollback preserves prior release, and temporal/policy
behavior matches accepted contracts.

## 2. Sub-gates

| Sub-gate | Dependencies | Claim tested |
| --- | --- | --- |
| V1b-TL lifecycle | L1/supporting environment | TL candidate isolation/recovery/provenance |
| V1b-TL graph | TL2/P-002 | bounded association/caps/work telemetry |
| V1b-Trace release | TR1/P-003 | unified active release/candidate isolation/rollback |
| V1b-Trace temporal | TR2/P-004 | system/valid time, lifecycle, historical policy |

Report sub-gates separately. A pass in one does not grant any other.

## 3. Mandatory fault families

- crash before candidate writes;
- crash after partial hierarchy writes;
- crash after candidate affinity/prior writes;
- validation failure;
- policy change during build;
- external component activation failure;
- restart/retry after interruption;
- source arrival during build;
- cross-workspace candidate access;
- pointer rollback;
- as_of_event release selection;
- valid-time/supersession/revocation/tombstone/denied history after TR2.

## 4. Evidence requirements

For each retain source identity, migration checksums, runtime/database versions,
exact command, raw result, predecessor/candidate/successor IDs, source/
projection hashes, evidence bundle sample, normal query observation, and
unsupported environment conditions.

## 5. Infrastructure constraint

Fake/in-memory/SQLite result proves exact contract only. It cannot establish
PostgreSQL/RLS, external-index alias, real crash recovery, deployment migration,
provider, or transport. Use isolated infrastructure or mark unverified.

## 6. Acceptance

No candidate leakage, mixed release read, stale edge, rollback, or temporal
claim is accepted without direct independent evidence. Failure creates narrow
repair/reverification, never silent test/evaluator change.
