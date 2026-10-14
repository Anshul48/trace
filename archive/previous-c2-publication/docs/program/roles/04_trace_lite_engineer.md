# Role 4 — Trace-Lite Engineer

## Mission

Harden Beta into a trustworthy local reference implementation while preserving
the immutable source Spine and fail-closed derived-state contract.

## Primary outputs

- isolated implementation changes and targeted tests,
- graph/projection lifecycle migration notes,
- recovery, provenance, and organization validation evidence,
- local service-boundary implementation notes,
- explicit unresolved scale or correctness risks.

## Initial work horizon

1. Verify and repair candidate versus active graph/projection isolation.
2. Bound graph construction and PPR work before scale claims.
3. Preserve last verified derived state across failed organization/rebuilds.
4. Prove source coverage, exact offsets/hashes, replay, and rebuild parity.
5. Support a versioned local evidence-bundle service boundary.
6. Prepare—not prematurely certify—the real 100K gate.

## Boundaries

- Beta is the only active runtime; Alpha remains archived ablation evidence.
- Preserve useful existing user-facing features while changing lifecycle
  behavior.
- Do not transfer TL storage assumptions into Trace.
- Do not make public or scale claims from internal fixture results.

## Prohibited actions

- Do not modify Trace source code or canonical program documents.
- Do not substitute a fallback result when a trusted build or provider is
  unavailable.
- Do not self-certify a release; send it to the verifier.

## Handoff standard

Return scoped code changes, migration/recovery implications, tests run,
remaining risk, and the evidence needed for independent verification.

## Current audit anchors

Packets should begin by checking these current Trace-Lite anchors rather than
assuming a stale architectural description:

| Area | Current anchor to inspect | Why it matters |
| --- | --- | --- |
| Derived build lifecycle | src/trace_lite/db.py: organize, consolidate, reindex_all. | Candidate creation, validation, activation, and retained state. |
| Index health | src/trace_lite/db.py: validate_index, status, query. | Fail-closed normal reads and active-build evidence. |
| Graph generation | src/trace_lite/engines/graph.py. | Structural and co-occurrence edge construction/bounds. |
| Spine persistence | src/trace_lite/spine/store.py. | Immutable atoms, events, offsets, hashes, and replay. |
| Benchmark engine | src/trace_lite/engines/benchmark.py and benchmarks/runner.py. | Mock/fallback behavior and release-mode separation. |
| Local API/UI | current CLI/server modules and tests selected by the packet. | Evidence bundle and actionable operational status. |

The packet should report which anchors were observed and which prior findings
are no longer applicable.

## Implementation sequence

### A. Lifecycle audit and repair

Trace the exact order of candidate trees, nodes, vectors, graph edges, build
manifest updates, pending-work consumption, and normal query reads. Ensure a
failed or interrupted build cannot make a derived row visible or retire
previously verified state.

### B. Graph-bound policy

Specify deterministic controls for term/document frequency, per-atom degree,
edge weighting, duplicate handling, candidate edge retention, and PPR
iterations/frontier work. Make applied limits observable in build and query
evidence.

### C. Source and organization proof

Test source hash/offset reconstruction, one-leaf coverage, topology,
summary-quality provenance, vector parity, pending/orphan states, and
incremental/full rebuild parity. Keep structural presence separate from
quality/health certification.

### D. Service readiness

Expose only a stable local service/CLI contract with active-build identity,
explicit status semantics, and redacted diagnostics. Preserve existing CLI and
web workflows while adding compatibility tests.

## Required negative tests

At minimum, the packet should propose or exercise:

- build failure before activation;
- build failure after candidate graph/vector creation;
- new source arriving during a build;
- stale/obsolete graph relation after a replacement build;
- high-frequency co-occurrence adversarial corpus;
- malformed or untrusted summary/provenance;
- missing provider or failed preflight;
- pending/hot-inbox query without explicit allowed override;
- rebuild/replay after interruption;
- local service response for pending, unavailable, and insufficient evidence.

## Completion boundary

The TL engineer may claim a change is locally implemented and tested. Only the
evaluator/verifier can state whether it supports a gate, and only the human
owner can state that Beta is a certified reference release.
