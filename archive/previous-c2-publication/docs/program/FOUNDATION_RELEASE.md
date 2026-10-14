# Foundation Release Contract

> **Status:** Broad-stroke planning contract. It defines what “feature
> complete” means for the current foundation program; it is not evidence that
> the release exists or is certified.

## Purpose

Create a finite, trustworthy, reproducible baseline across three separately
versioned components:

1. Trace-Lite Beta;
2. Trace;
3. the benchmark suite and its dataset/evaluation records.

This is the baseline from which later architecture research and deep mechanism
experiments will be measured.

## In scope

- explicit repository boundaries, revisions, dirty-state handling, and input
  manifests;
- source/provenance/recovery behavior required by each current runtime;
- candidate-build validation, active-release isolation, rollback, and
  fail-closed unavailable/untrusted states;
- a benchmark suite that is separately versioned, reproducible, and incapable
  of silently using mock, synthetic, forced, or insecure fallback paths;
- independent verification and a clear capability/exclusion matrix;
- stable evidence-bundle and consumer-conformance boundaries.

## Not in scope

- a public SOTA claim;
- a 100K or 1M scale certification claim;
- broad architecture redesign, large-model substitution, or speculative
  retrieval mechanisms;
- automatic downstream production adoption;
- treating a passing unit suite as full release evidence.

## Definition of Foundation Complete

The coordinator may propose Foundation Complete only when the release record
contains, at broad minimum:

- exact component revisions and documented repository boundaries;
- an explicit supported-capability matrix and known exclusions;
- a fail-closed evaluation mode plus negative integrity evidence;
- a reproducible input/configuration/environment manifest format;
- candidate/active lifecycle evidence for each applicable derived projection;
- source/provenance/recovery evidence appropriate to the supported scope;
- independent verifier findings, unresolved risks, and repair disposition;
- a statement of what remains non-certifying.

## Required human decisions

### Expanded decision set

The original P-001 through P-005 list is extended by:

- **P-007:** trace-bench canonical source-control or content-manifest policy;
- **P-008:** one canonical certification runner/integration boundary between
  trace-bench and legacy Trace-Lite benchmark code.

The two new decisions are prerequisites for B1. They prevent a clean runner
implementation from being falsely described as reproducible while its own
source or product adapter identity is ambiguous.

The Foundation Release does not erase pending decisions. Work that depends on
them remains blocked until accepted:

- P-001: initial real-data portfolio;
- P-002: graph/PPR/resource budgets;
- P-003: unified Trace Cortex Release schema;
- P-004: temporal/revocation and valid-time contract;
- P-005: numerical 100K gate thresholds.

## Exit paths

## Detailed foundation baseline contract

The Foundation Release has seven bounded deliverables. Each has a distinct
evidence level, verifier, and claim boundary.

| Deliverable | Required result | Current state | Later gate enabled |
| --- | --- | --- | --- |
| Component identity | Trace-Lite, Trace, trace-bench, and control-plane identities plus protected dirty-state records. | In progress; trace-bench unversioned. | Mutable packet preparation. |
| Benchmark integrity | Certification cannot mock, synthesize, flat-fallback, swallow errors, reinterpret empty results, or disable TLS. | Blocked pending F0a/P-007/P-008. | B1/V1a. |
| Data admission | Source/license/version/checksum/transform/evidence records plus P-001. | Candidate records only. | D2/B2. |
| TL release safety | Candidate isolation, validation, atomic activation, failed-build preservation, rollback proof. | Not assigned. | TL2/TL3/100K. |
| Trace release safety | One active Cortex Release selects all release components; no candidate affinity/prior leak. | Source-level gap observed; P-003 open. | TR1/V1b. |
| Temporal/policy truth | System time, valid time, source lifecycle, revocation, historical policy selection are explicit. | Design gap observed; P-004 open. | TR2/V1b. |
| Independent evidence | Separate worktree/verifier reruns fixed negative/lifecycle tests. | Verifier planning only. | Foundation review. |

### Hard exclusions

Foundation Complete cannot claim external SOTA, a passed public benchmark, a
real-data certification run without B2/B3, 100K/1M/distributed/consumer
readiness, valid-time/revocation before P-004 implementation/verification,
production PostgreSQL/RLS proof from fake tests, or reproducible trace-bench
before P-007.

### Current-state anchors

Preserve these observed starting facts until new evidence supersedes them:

- Trace-Lite Git identity observed: fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1.
- Trace Git identity observed: c855bb06532b3b52b25f0bea969d2677e5049065.
- Trace contains user-owned tracked/untracked V2 work, including a proposed
  Cortex-control migration; it is not a clean mutable base.
- trace-bench is a moved source tree without Git identity and has generated,
  cache, and result material excluded from source identity.
- The internal 320-case fixture is regression-only.

### Prepared implementation checklist

Before B1, L1, TR1, or TR2 is mutable, its task folder has:

1. input manifest and component state record;
2. accepted dependencies and human decisions;
3. clean isolated worktree lease at accepted source identity;
4. exact allowed/forbidden paths and external authority;
5. acceptance and negative test matrix;
6. independent verifier assignment/separate worktree plan;
7. recovery/rollback behavior;
8. structured handoff/evidence destination.

### Readiness labels

Any review selects exactly one:

1. Planning only.
2. Foundation infrastructure.
3. Real-data evaluation ready.
4. Certification ready.
5. 100K ready.

Only human review assigns a label; the Gate Dossier gives requirements.

```text
Foundation Complete
  -> deep architecture research and mechanism cards
  -> bounded prototype + fixed ablation
  -> independent verification
  -> human promotion decision
  -> real-corpus 100K gate
```

No path skips the evaluator, verifier, or human promotion decision.

## After Foundation Complete

Foundation Complete is the beginning of measured scale work, not a declaration
that Trace is distributed or 10B-token ready. The next evidence gates are a
real 100K corpus and then a separately authorized 1M pilot. Any later
shard-aware or 10B-token program requires its own workload model, capacity
plan, fault/verifier protocol, and human decision record. Native language
components remain profile-guided and parity-tested rather than a wholesale
rewrite. See [the future scale roadmap](../future-scale-roadmap.md).
