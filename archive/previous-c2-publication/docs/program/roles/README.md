# Agent Roles

> **Status:** Draft role contracts. These are logical roles, not a requirement
> to run all workers simultaneously.

Use seven logical roles: one coordinator and six specialist workers. Run no
more than three workers at a time, each in an isolated worktree with a fixed
packet. The human program owner remains the architecture and promotion
authority.

| File | Role |
| --- | --- |
| [00_coordinator.md](00_coordinator.md) | Integrates evidence and dispatches bounded work. |
| [01_research_analyst.md](01_research_analyst.md) | Deep research and hypothesis formation. |
| [02_data_steward.md](02_data_steward.md) | Real-data discovery, licensing, and staging records. |
| [03_evaluation_engineer.md](03_evaluation_engineer.md) | Fail-closed evaluation and measurement. |
| [04_trace_lite_engineer.md](04_trace_lite_engineer.md) | Beta lifecycle and local reference hardening. |
| [05_trace_engineer.md](05_trace_engineer.md) | Cortex Releases and governed Trace evolution. |
| [06_verifier_integration.md](06_verifier_integration.md) | Independent verification and consumer conformance. |

## Role topology

The roles form a review pipeline, not a hierarchy of autonomous authority:

~~~text
human owner
    |
coordinator
    |------ research analyst ------+    |------ data steward -----------> evaluation engineer
    |------ TL engineer -----------+    |------ Trace engineer ---------> verifier / integration reviewer
    ---------------------------------> human decision
~~~

Research and data inform evaluation. Evaluation fixes the proof boundary before
implementation claims are assessed. TL and Trace work in separate repositories
and worktrees. The verifier receives fixed criteria, not an invitation to
redesign the feature under review.

## Concurrency and conflict rules

| Rule | Operational meaning |
| --- | --- |
| Maximum mutable work | Three workers at a time, each in a separate worktree. |
| Shared documents | Only the coordinator changes canonical program documents after review. |
| Evaluator independence | The evaluator and verifier do not accept algorithm changes in the same task that produced them. |
| Repository ownership | A TL worker edits TL only; a Trace worker edits Trace only unless a packet explicitly creates a cross-repo contract artifact. |
| External state | Downloads, provider calls, datasets, migrations, and deletion require explicit packet authority. |
| Handoffs | Every worker leaves commands, artifacts, test limits, and follow-up risks. |

## Minimum role packet

Every role packet includes:

1. The exact question or implementation objective.
2. A task ID, base commit, worktree, and time/budget limit.
3. Program-doc and input hashes.
4. Allowed and forbidden paths.
5. Required evidence, negative tests, and exit criteria.
6. A statement of whether code edits, downloads, provider calls, or data access
   are authorized.
7. A handoff location and named independent verifier where applicable.

## Escalation convention

Workers stop and ask the coordinator when they encounter an unapproved
architecture choice, a contradictory invariant, private/unclear data rights,
destructive cleanup, a change in evaluator semantics, or a need to expand the
allowed path set. A high-quality blocked handoff is preferable to an
unauthorized workaround.

## Prompt pairing

Copy-paste behavior prompts for these roles live in
[../prompts/](../prompts/README.md). Use one role description, one prompt, one
workstream brief, and one assigned task packet; do not send the role prompt
alone and expect the model to infer repository scope.

## Foundation-session clarification

The foundation launch kit uses five sessions, not seven simultaneous mutable
workers. Session 2 may use the combined
[07_benchmark_foundation.md](07_benchmark_foundation.md) contract to coordinate
separate read-only F0a/F0b subagents. This does not merge data admission and
evaluation certification authority: P-001, P-005, P-007, and P-008 remain
human decisions, and V1a remains independent.
