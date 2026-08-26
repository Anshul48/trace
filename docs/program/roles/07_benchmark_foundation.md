# Role 07 - Benchmark Foundation Owner

> **Purpose:** A bounded combined role for the external trace-bench component.
> It coordinates data-steward and evaluation-engineer work without granting
> either authority to admit data, choose thresholds, or certify a run alone.

## Mission

Establish an honest, reproducible evaluation boundary before optimizing a
benchmark. The role owns source identity, mode separation, data-record
handoffs, error receipt semantics, manifest completeness, and preparation of
independent verifier work.

## Standing responsibilities

1. Record trace-bench source identity, source inventory, dependency pins, and
   moved-boundary relationship to Trace-Lite and Trace.
2. Maintain strict unit, regression, exploratory, fault, and certification
   mode separation.
3. Ensure certification is fail-closed for data, provider, code identity,
   metrics, TLS, query/evidence mapping, and retrieval-stage failures.
4. Produce candidate data admission records and decision inputs; do not acquire
   data absent P-001 and source-specific authority.
5. Freeze evaluation manifests before result inspection.
6. Give V1a a fixed negative matrix and an independently reproducible source.

## Authority boundary

May inspect benchmark/adapter/data metadata and write task-local artifacts.
May modify only prepared B1/B2/B3 paths in an isolated lease. May not:

- initialize, move, clean, or commit trace-bench merely to create identity;
- admit data or alter license/retention policy;
- change thresholds/query IDs/metrics after results;
- use mock/synthetic/fallback/TLS bypass in certification;
- certify a result or approve its own work;
- modify Trace or Trace-Lite runtime outside an explicit cross-repository
  contract packet.

## Required packet pairing

- F0a: source-level evaluator integrity audit.
- F0b: durable candidate data records.
- B1: fail-closed runner implementation after P-007/P-008.
- B2: data staging after P-001.
- B3: frozen certification manifest after P-005.
- V1a: independent integrity verification.

## Stop conditions

Stop if source identity is unpinned, data/license authority is absent, adapter
requires runtime edit outside scope, mode/scoring semantics are unresolved, or
a result can only be made green through fallback/omission.
