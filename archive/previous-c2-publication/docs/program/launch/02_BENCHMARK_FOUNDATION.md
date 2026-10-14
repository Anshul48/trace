# Session 2 — Benchmark Foundation

## Read first

1. `../prompts/GLOBAL_CONTEXT.md`
2. `../prompts/03_EVALUATION_ENGINEER.md`
3. `../prompts/02_DATA_STEWARD.md`
4. `../FOUNDATION_RELEASE.md`
5. `../04_EVALUATION_PROTOCOL.md`
6. `../inbox/f0a-e1-refresh-20260819/packet.md`
7. `../inbox/f0b-d1-refresh-20260819/packet.md`

## Mission

Make the separately versioned benchmark component an honest, reproducible
evaluation foundation. Record its boundary with Trace-Lite rather than assuming
the old in-repository path is current.

## First work

- delegate F0a and F0b as separate read-only subagents if useful;
- capture the benchmark-suite revision, runner/adapters/loaders, data sources,
  current fallback behavior, and current claim boundary;
- create durable data/evaluation handoffs;
- prepare B1 only after its current source anchors are known.

## Authority

Read-only during F0. No dataset download, TLS exception, provider call,
threshold change, certification claim, or Trace/TL product edit without a later
explicit packet.

## Mandatory detail for this session

Read in this exact order after the initial list:

1. SESSION_OPERATING_MANUAL.md, COMPONENT_REGISTRY.md, FOUNDATION_STATUS.md.
2. 00_CHARTER.md, 01_INVARIANTS.md, 03_SHARED_CONTRACTS.md,
   04_EVALUATION_PROTOCOL.md, and 07_RISK_REGISTER.md.
3. prompts/07_BENCHMARK_FOUNDATION.md, roles/02_data_steward.md, and
   roles/03_evaluation_engineer.md.
4. Data admission, evaluation manifest, error receipt, and repository state
   templates.
5. F0a and F0b packets/manifests; B1 only as scoped successor.

### Required outputs

- F0a exact runner/adapter/loader/metric anchors, mode classification,
  forbidden fallback inventory, and stale-reference list.
- F0b durable candidate record per proposed dataset: source, license, version,
  intended query class, judgment/evidence mapping gap, post-download checksum.
- trace-bench source inventory excluding generated/cache/results and listing
  unpinned TL/Trace imports.
- P-007/P-008 decision inputs, not assumed selections.
- B1 preparation delta naming every code path/test; no data staging/threshold
  change.

### Later integrity matrix

Certification must block with receipt on mock provider, synthetic dataset,
forced/flat fallback, swallowed indexing/query error, empty retrieval
incorrectly scored as abstention, missing evidence mapping, checksum/license
failure, and insecure TLS fallback. It must never turn these into a score.

## Later queued work

`../inbox/b1-e2a-fail-closed-runner/packet.md` becomes eligible only after
F0a review. Dataset staging is separately gated by P-001.
