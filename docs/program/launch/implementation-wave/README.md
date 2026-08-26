# Foundation Implementation Wave

This directory is the execution-facing companion to the original read-only
foundation launch kit. The original files under `launch/` and `prompts/` are
preserved as historical foundation records. These files describe the mutable
implementation and verification waves that follow those records.

## Purpose

The program has eight long-lived session lanes:

| Session | Owner | Primary responsibility | First legal wave |
| --- | --- | --- | --- |
| S0 | Coordinator | Decisions, leases, manifests, task board, gates | Wave 0 |
| S1 | Benchmark | `trace-bench` Git bootstrap and fail-closed runner | Wave 1 |
| S2 | Trace-Lite | Candidate/active lifecycle and provenance/rebuild proof | Wave 1 |
| S3 | Trace | Frozen V2 snapshot and unified Cortex Releases | Wave 1 |
| S4 | Data | Real-data acquisition, manifests, normalization, evidence maps | Wave 1 |
| S5 | Independent verifier | Negative, lifecycle, rollback, and temporal verification | Gated later |
| S6 | Evaluation/promotion | Baselines, P-005 evidence, B3, Foundation Gate | Gated later |
| S7 | Scale | Real 100K gate, then 1M preparation | Foundation Gate only |

Start S0 alone. After S0 writes its D0 handoff, start S1, S2, S3, and S4 in
parallel. Do not start S5, S6, or S7 until the dependency conditions below
are met.

## How to launch a session

Open a new Codex session with access to the local repositories. Give it the
following instruction, then the named session file:

```text
You are a bounded worker in the Trace / Trace-Lite Foundation Program.
Read the shared global context and session protocol first, then read your
session brief and every packet it names. Treat those documents, the current
repository identity, and the worktree lease as binding. Do not rely on a
previous chat transcript. Produce the durable handoff required by the brief
before summarizing your work.
```

Then paste the contents of `00_GLOBAL_CONTEXT.md`, `01_SESSION_PROTOCOL.md`,
`04_SUBAGENT_RULES.md`, and the appropriate `10_*.md` through `17_*.md` file,
or instruct the session to read those local files directly.

The session must report its current packet state before making a mutable
change. A session may pause with `blocked` when a lease, decision, source
identity, or verifier is missing; it must not invent one.

## Repository boundaries

| Component | Canonical path | Mutation rule |
| --- | --- | --- |
| Trace-Lite | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite` | Never mutate the user checkout directly; use a clean worktree from `fe66a9e...` for L1. |
| Trace | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace` | Treat the current V2 checkout as a protected dirty snapshot; T0 freezes an isolated implementation base before TR1. |
| trace-bench | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench` | Initialize Git in place only under B0; do not delete caches/results; certification waits for a pinned source identity. |
| Raw data | `C:\Users\anshu\AppData\Local\trace-bench-data` | Keep outside Git and OneDrive; each dataset gets an immutable raw directory and manifest. |
| Program control plane | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program` | S0 is the sole coordinator writer; implementation sessions may add only their packet-local handoffs. |

## Hard rules

1. No certification may use a mock provider, synthetic substitute, editable
   local import, insecure TLS retry, silent exception, forced flat-search
   fallback, or empty-result-as-abstention interpretation.
2. The 320-case internal fixture is regression evidence only. It cannot prove
   public retrieval quality, SOTA, or scale.
3. The Spine is canonical. Cortex indexes, vectors, hierarchy, graphs,
   summaries, priors, and routing state are disposable projections.
4. Candidate projections are invisible until validated and atomically activated.
   The previous validated release must remain recoverable.
5. P-002 graph budgets, P-004 temporal/privacy semantics, and P-005 numeric
   release thresholds are human/evidence decisions. An agent may prepare a
   decision brief, but may not silently choose them.
6. Verification is independent. A verifier never repairs the implementation it
   is reviewing and never upgrades an observed fact into a certification claim.
7. Raw data is never committed to Git. Every downloaded source requires URL,
   license, version/date, archive hash, extraction hash, and layout evidence.

## Dependency DAG

```text
S0 D0
├── S1 B0 ──> S1 B1 ──> S5 V1a
├── S2 L1 ──> S2 TL3 ──> P-002 ──> S2 TL2 ──> S5 V1b-TL
├── S3 T0 ──> S3 TR1 ──> P-004 ──> S3 TR2 ──> S5 V1b-Trace
└── S4 D2a ────────────────> B1 manifest contract ──> S4 D2b
                                                        │
                                      B1 + D2b ──> S6 P-005/B3
                                                        │
                                               Foundation Gate
                                                        │
                                                S7 real 100K
                                                        │
                                                 S7 1M pilot
```

The exact transition criteria are in `02_WAVE_AND_GATE_MATRIX.md`.

## Completion standard

A session is complete only when its code/data/evidence artifacts, identity
hashes, tests, limitations, and next dependency are recorded in its packet
inbox. A green test command without a reproducible environment and a clear
claim boundary is not a completed gate.

## Post-foundation direction

This implementation wave does not authorize distributed infrastructure or a
whole-system language rewrite. After independent verification and the
Foundation Gate, S7 measures a real 100K corpus and prepares a 1M pilot. Any
later 10B-token active-memory effort is a separate, evidence-gated
shard-aware architecture program. Current workers should preserve portable
contracts and collect profiling evidence; Rust, Go, or other native components
are considered only for stable, measured hot paths with parity tests.

See [the future scale roadmap](../../../future-scale-roadmap.md) for the
transition triggers and long-term direction.
