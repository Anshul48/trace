# Trace Phase 1 pilot validation contract

## Corpus handling

Publish a small reproducible public fixture and its expected evidence IDs.
Run owner-approved engineering document and decision corpora privately on the
operator's machine. Private corpus text, paths, URLs, attachments, and query
judgments must not be uploaded by Trace.

For every reported scale point, publish:

- hardware profile and operating system;
- Trace version and export schema version;
- current immutable source-atom count;
- average and distribution of tokens per source atom;
- immutable-version growth during the run;
- lexical projection size and attachment size;
- query mix and retrieval budget;
- p50 and p95 latency by query class; and
- failures, retries, capacity deferrals, and recovery results.

Do not convert a source-atom count into a token-capacity claim without those
measurements.

## Required staged runs

Run the same validation contract for ordinary local datasets, 100,000 current
source atoms, and 1,000,000 current source atoms on explicitly documented test
hardware. The latter two are scale experiments, not prerequisites for a user
to install or use the local alpha.

Each run must exercise:

- offline startup, ingest, query, and status output;
- source text, URL, file URI, document name, metadata, and image-description
  retention;
- export, import, projection rebuild, and evidence-query parity;
- bounded lexical retrieval and bounded optional local plugins;
- review control for relation, schema, claim, and feedback topology proposals;
- exact-source validation for navigation summaries;
- resource-pressure deferral and retriable write rejection;
- Windows and Linux installation; and
- integrity verification after an interrupted or repeated import attempt.

## Frozen judged queries

Freeze at least 100 judged queries before the pilot decision. Cover direct
lookup, dependency, contradiction, chronology, navigation, and out-of-scope
requests. Every judgment must identify the complete accepted gold evidence
atom IDs, not merely an answer string.

Record the query, class, source corpus snapshot, expected atom IDs, retrieved
atom IDs, selected citations, review result, retrieval mode, plugin versions,
and latency. Out-of-scope queries must be able to pass by returning
insufficient evidence.

## Pilot release gate

The pilot passes only if all of the following are true:

| Measure | Gate |
| --- | --- |
| Complete-gold-evidence coverage | at least 80% |
| Citation precision | at least 90% |
| Reviewer approval of navigation summaries | at least 70% |
| Latency | p95 reported by query class and hardware profile |
| Provenance, privacy, destructive-data defects | zero critical defects |
| Rebuild and import recovery | source evidence and judged-query parity verified |

Report failures rather than averaging them away. A quality result from a
fixture is evidence about that fixture and hardware profile, not a universal
retrieval promise.

## Phase boundary

The future managed API may add distributed storage, tenant isolation, support,
billing, and availability objectives. It must retain the Phase 1 event and
export semantics: source evidence remains immutable, provenance remains
searchable, derived facts remain anchored and reviewed, and projections remain
rebuildable.
