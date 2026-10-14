# Workstream 04 — Trace-Lite Beta Hardening

> **Owner:** Trace-Lite engineer
> **Status:** Draft outline

## Intended outcome

Make Beta a safe local reference implementation whose source evidence remains
durable while all retrieval and organization state remains bounded, rebuildable,
and atomically activated.

## First work packages

1. Verify the current candidate/active lifecycle for hierarchy, vectors,
   summaries, routing, and graph edges.
2. Design and implement any needed run/revision scoping, stale-state retirement,
   validation, activation, and rollback behavior.
3. Bound co-occurrence construction, graph degree, storage growth, and PPR
   traversal work while retaining diagnosable behavior.
4. Expand recovery, source fidelity, topology, summary quality, and
   incremental/full parity evidence.
5. Prepare a versioned local evidence-bundle service boundary without exposing
   provider credentials or direct storage access.

## Required inputs

- Beta workstream, invariant contract, evaluation requirements,
- current code/test audit, and fixed acceptance packet,
- no assumption that historical findings remain open without verification.

## Expected artifacts

- narrow design/migration note,
- isolated code/test changes,
- active-versus-candidate failure tests,
- performance/graph-budget instrumentation,
- handoff for independent verification.

## Exit condition

The system is ready to attempt—not automatically pass—the real 100K gate.

## Stop conditions

Stop for a reviewed decision if a change would weaken fail-closed behavior,
canonical source fidelity, backward data compatibility, or existing supported
user workflows.

## Work-package decomposition

### TL1 — Active derived-state audit

Map all write and read paths for:

- source atoms and pending queues;
- index-build records and active manifest;
- tree/node replacement;
- vector collection creation/selection;
- graph edge generation/storage/query;
- validation and query gating;
- garbage collection and retained rollback material.

The output is a lifecycle diagram and a list of concrete leakage/retirement
risks verified against the current checkout.

### TL2 — Candidate graph/revision design

Define whether graph rows carry a build/revision identity, how active graph
selection occurs, how obsolete edges retire, how failed candidates are cleaned
or retained for diagnostics, and how graph/vector/tree activation is made one
logical operation.

The design must retain the previous verified active state until the new complete
candidate passes validation.

### TL3 — Bounded graph policy

Specify:

- term/document frequency threshold;
- maximum candidate partners per term/atom;
- directional/undirected edge rules;
- deterministic ordering or sampling;
- duplicate/weight aggregation;
- per-node degree limits;
- PPR seed, iteration, frontier, and expansion budgets;
- build and query diagnostics.

The implementation packet should include adversarial high-frequency cases and
an explicit complexity expectation.

### TL4 — Durability and organization proof

Define fixture and real-corpus checks for source hashes/offsets, atom coverage,
pending/orphan handling, tree topology, summary provenance/quality,
vector parity, graph validity, and incremental/full rebuild equivalence.

### TL5 — Local service contract

Map existing CLI/web/API behavior to the shared evidence-bundle statuses. Add
compatibility-preserving responses and diagnostics rather than removing useful
interfaces. Consumer use remains loopback, versioned, and advisory.

## Expected implementation evidence

| Change class | Required evidence |
| --- | --- |
| Schema/lifecycle | Before/after build IDs, failed-candidate test, active-state comparison. |
| Graph bound | Edge/work telemetry and adversarial input result. |
| Validation | Structural and quality error codes plus healthy-path report. |
| Recovery | Crash/replay/rebuild parity and retained source proof. |
| API/CLI | Contract fixture, HTTP/CLI behavior, redacted diagnostic sample. |
| Performance | Per-query-class measurement under declared environment. |

## 100K readiness checklist

Before the real run, ensure:

- lifecycle and graph tests are independent of the corpus size;
- the data manifest is reviewed and no private/raw data is committed;
- the evaluator can fail closed;
- resource capture is available on the target Windows environment;
- external temporary directories are writable and cleanup failures are reported
  separately from product failures;
- the prior active state and source databases are backed up or reproducibly
  recoverable;
- a verifier packet names the exact pass/fail evidence.
