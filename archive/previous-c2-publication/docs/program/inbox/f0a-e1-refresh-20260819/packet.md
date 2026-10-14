# F0a / E1-refresh — Current Evaluation and Benchmark Re-anchor

> **Role:** Evaluation engineer
> **State:** Ready for read-only dispatch
> **DAG node:** F0a

## Objective

Re-anchor the release-integrity audit to the current Trace-Lite checkout and
the separately versioned benchmark suite. Produce durable facts about the
actual runner, adapters, loaders, fixtures, fallback behavior, and claim
boundary.

## Broad inputs

- `GLOBAL_CONTEXT.md`, `FOUNDATION_RELEASE.md`, `04_EVALUATION_PROTOCOL.md`;
- current Trace-Lite repository state;
- current benchmark-suite repository state and location supplied by the user or
  discovered from current integration references;
- prior evaluation handoff only as non-authoritative context.

## Allowed work

- read repositories, docs, configuration, and test code;
- record current commits, dirty state, exact files/symbols, and stale anchors;
- write only task-local evidence and `handoff.md` under this directory.

## Forbidden work

- no product or benchmark code edits;
- no data downloads, provider calls, TLS changes, test execution, or
  certification claims;
- no cleanup, stash, reset, or modification of user-owned dirty files.

## Required broad outputs

- repository-boundary record and current source anchors;
- inventory of mock/synthetic/forced/fallback/error-handling/TLS paths;
- classification of each fixture and evaluation mode;
- corrected claim boundary for the internal 320-case fixture;
- precise prerequisites for the B1 fail-closed implementation packet.

## Acceptance

The handoff identifies what was observed in the current source, what could not
be inspected, and which earlier claims/paths are stale. It does not certify
runtime behavior.

## Detailed execution contract - 2026-08-19

### Component boundary to verify

Expected moved benchmark root:

C:\\Users\\anshu\\OneDrive\\Documents\\Code\\Utilities\\trace-bench

It is currently observed as an unversioned source tree. Record that fact
instead of assuming Trace-Lite benchmark paths remain certification source.
Inventory legacy internal Trace-Lite benchmark engine and any imports/config
joining the two surfaces.

### Current source anchors to refresh

Verify all paths/lines against current source:

| Concern | Expected surface | Required classification |
| --- | --- | --- |
| Runner default/mode | trace-bench/src/trace_bench/runner.py | mock/default/certification/exploratory |
| Trace-Lite adapter | trace-bench/src/trace_bench/baselines/trace_retriever.py | injection/index/query exception |
| Retrieval scoring | trace-bench/src/trace_bench/metrics/retrieval.py | empty/expected-abstention semantics |
| Adapter transport/data fallback | trace-bench/src/trace_bench/adapters | synthetic and TLS behavior |
| Dataset fallback | HippoRAG, TREC, LongMemEval, ANN adapters | data creation/substitution |
| Internal fixture | trace-bench fixtures/registry and TL material | release authority/regression designation |
| Legacy internal engine | Trace-Lite src/trace_lite/engines/benchmark.py | same fail-open behavior class |

### Mandatory findings table

For every fallback/error path record:

1. file, symbol, current branch/commit or unversioned manifest;
2. trigger and current behavior;
3. unit/regression/exploratory/certification allowance;
4. required B1 behavior and error-receipt reason;
5. negative test needed;
6. whether it can contaminate metric or only diagnostic.

### Required artifacts

- input-manifest.json and repository-state.json;
- evidence/current-surface-map.md;
- evidence/fallback-inventory.md;
- evidence/fixture-claim-boundary.md;
- evidence/stale-packet-matrix.md;
- commands.md and handoff.md.

### B1 preparation result

Recommend B1 only if it names canonical source identity status, all code/test
paths, explicit mode separation, receipt schema, V1a matrix, and P-007/P-008
status. F0a cannot create certification mode, alter metric, network, or admit
data.

## Handoff

Create `handoff.md` from `../../templates/HANDOFF.md`. Recommend only one of:
prepare B1, refresh again, or block pending a missing repository/path.
