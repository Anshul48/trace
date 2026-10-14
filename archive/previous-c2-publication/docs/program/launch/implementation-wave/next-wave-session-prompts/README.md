# Next-Wave Session Prompt Pack

This pack turns the approved session order into small, copyable launch prompts.
It deliberately gives broad operating directions rather than implementation
recipes. The assigned worker must inspect the cited source, choose safe local
details, and record all evidence in a durable handoff.

## Use

For each new Codex session:

1. Give it the shared bootstrap prompt in 00_SHARED_BOOTSTRAP.md.
2. Give it exactly one numbered prompt from this directory.
3. Require it to stop at every listed human gate and to write its handoff
   before it summarizes.

The existing implementation-wave briefs remain authoritative for detailed
requirements. This pack neither replaces them nor changes their ownership
boundaries.

## Session order

1. 01_S0_R1_RECONCILIATION.md
2. 02_S1_B11_BENCHMARK_IDENTITY.md and 03_S5_INITIAL_V1B.md in parallel
3. 04_S5_V1A.md and 05_S4_D2B_NORMALIZATION.md in parallel, after session 2
4. Human Gate A: record P-002 and P-004
5. 06_S2_TL2.md and 07_S3_TR2.md in parallel
6. 08_S5_FINAL_V1B.md
7. 09_S6_BASELINES_P005.md
8. Human Gate B: record P-005
9. 10_S6_B3_DOSSIER.md
10. 11_S0_R2_FOUNDATION_GATE.md
11. 12_S7_REAL_100K.md
12. Human Gate C: explicit 100K promotion decision
13. 13_S7_1M_PILOT_PLAN.md

The human gates are not Codex sessions. No later numbered prompt may begin
until its gate is durably recorded.

## Launch wrapper

Give the worker this short wrapper, followed by 00_SHARED_BOOTSTRAP.md and the
numbered prompt:

You are executing one bounded Trace Foundation session. Read the shared
bootstrap and your numbered prompt completely before inspecting or changing
anything. Reconcile live repository and packet state with the prompt. Use
isolated worktrees and external scratch paths. You may delegate bounded,
non-overlapping inspection or verification to subagents, but you own the
scope, evidence, and handoff. Do not cross a human decision gate. Stop as
blocked when a hard prerequisite is missing; never replace it with a mock,
synthetic fixture, fallback, or undocumented assumption.

## What every worker must return

Every session must leave a packet-local handoff, even when it is blocked. The
handoff must identify:

- the packet, session, operator, lease, absolute paths, base and head
  identities, and verifier identity;
- the exact inputs, packet hashes, repository status, environment, and
  external service/data identities;
- the authority actually exercised and the authority intentionally not used;
- observed facts separately from interpretations, proposals, and decisions;
- every created/changed artifact with a hash and reversibility statement;
- exact commands, test counts, durations, skipped cases, cleanup status, and
  raw evidence locations;
- invariant checks, risks, blockers, claim level, and one hard next dependency.

The final chat response is only a summary of the durable handoff. It must not
be the only record of work.

## Subagent launch contract

When a prompt permits subagents, the session owner must first write a small
delegation table containing subagent role, allowed paths, forbidden paths,
inputs, expected output, and whether the role is read-only. Subagents must
return evidence to the owner and must not edit shared control-plane records,
decision logs, evaluator policy, or another worker's worktree. The owner
reconciles their results before writing the handoff.

## Repair and re-verification

If an implementation fails independent verification, freeze the verifier
receipts and open a narrow repair packet for the owning implementation lane.
The verifier does not patch the candidate. A repair produces a new immutable
identity and reruns only the affected verification plus any explicitly
dependent checks. Existing passing evidence is retained but is not silently
applied to the new identity.

## Claim discipline

Passing unit tests, source inspection, synthetic fixtures, or a local SQLite
run cannot establish public retrieval quality, production readiness,
PostgreSQL/external-index behavior, or 100K/1M scale. The prompts require
those claim boundaries to be repeated in each handoff.

## After the 13-session sequence

The sequence ends at a Foundation Gate and then the real 100K/1M evidence
path. It does not automatically begin a distributed implementation or a
Rust/Go rewrite. Workers should preserve portable contracts and capture
profiling evidence so a later scale program can make those choices from data.
See [the future scale roadmap](../../../../future-scale-roadmap.md).
