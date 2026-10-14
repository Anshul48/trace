# Workstream 03 — Evaluation, Ablation, and Scale Measurement

> **Owner:** Evaluation engineer
> **Status:** Draft outline

## Intended outcome

Turn the benchmark system into a fail-closed, reproducible evaluator that
distinguishes regression evidence, public retrieval evidence, downstream
evidence, recovery evidence, and scale evidence.

## First work packages

1. Audit the current runner for mock, synthetic, flat-search, or missing-data
   fallback paths.
2. Specify a release manifest that pins data, transforms, baselines, settings,
   provider/model identity, and environment metadata.
3. Define fixed query classes, metrics, paired ablations, and result slices.
4. Define negative tests proving release runs fail when a prerequisite is
   missing or substituted.
5. Define 100K measures: source coverage, recovery, cold/warm latency, QPS,
   PPR work, memory, disk, build/rebuild time, and cost.

## Required inputs

- reviewed dataset records,
- shared invariants and promotion rubric,
- Beta/Trace workstream acceptance needs,
- known current-harness limitations.

## Expected artifacts

- evaluation manifest schema outline,
- runner assertions and test plan,
- query/judgment-pack design,
- baseline/ablation matrix,
- run report and release-evidence templates.

## Exit condition

A reviewer can tell exactly what a run proves, what it does not prove, and
whether a required condition failed closed.

## Stop conditions

Stop when a metric, data source, baseline, or provider is missing rather than
inventing a substitute that could be mistaken for release evidence.

## Current audit focus

The first packet should inspect actual benchmark entry points, including
Trace-Lite benchmark runner/engine code and fixture metadata. The audit must
answer:

- whether any default path selects a mock LLM;
- whether an indexing failure can fall through to an alternate retrieval mode;
- whether a public adapter can emit a sample/synthetic substitute;
- whether a fixture is marked release-authoritative without independent data;
- whether result records include enough manifest/environment information to
  reproduce a claim.

Findings are recorded as observed code behavior with file/symbol anchors; they
are not inferred from documentation alone.

## Evaluator build sequence

### E1.1 — Manifest and mode model

Define developer, regression, exploratory, certification, fault, and scale
modes. Certification mode must require explicit real-data records and reject
prohibited modes before any score is produced.

### E1.2 — Data and transform validation

Validate expected files, archive/normalized checksums, record counts,
segmentation mapping, query IDs, judgment IDs, and license/admission status.

### E1.3 — System/configuration capture

Capture code revision, dirty-worktree state, model/provider/embedding identity,
projection/release identity, retrieval profile, concurrency, warmup behavior,
hardware, and operating environment.

### E1.4 — Result artifact model

Persist query-level candidates/evidence, sufficiency/abstention states,
channel/work diagnostics, errors/exclusions, aggregate metrics, and report
metadata. Raw private content remains external or redacted.

### E1.5 — Negative integrity suite

Deliberately remove data, alter a checksum, enable a mock, force a fallback,
drop judgments, or change a required configuration. The certification runner
must fail with a specific taxonomy code.

## 100K evaluator requirements

The 100K protocol must measure both correctness and operations:

| Area | Required capture |
| --- | --- |
| Input | Source count, atom count, corpus/transform hashes, policy assumptions. |
| Build | Ingestion, organization, graph/index, validation, activation, and rebuild times. |
| Recovery | Crash/interruption point, replay result, active-state comparison, retained source coverage. |
| Retrieval | Query-class cold/warm latency, candidates, work budgets, quality/evidence outcome. |
| Resources | CPU where available, RAM/RSS, disk, graph/vector/index sizes, bytes per atom. |
| Economics | Provider/model calls, storage and compute estimates, operator burden. |

## Evaluation workstream exit

The evaluator is ready for a gate only when it can reject malformed evidence,
describe every run's exact scope, and produce a verifier-consumable report. A
dashboard or attractive aggregate chart is not an exit condition.
