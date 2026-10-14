# F0c — Repository Boundary and Current-State Record

> **Role:** Coordinator with read-only TL/Trace contributors
> **State:** Ready for read-only dispatch
> **DAG node:** F0c

## Objective

Capture the current identities and boundaries of Trace-Lite, Trace, and the
separate benchmark suite before any mutable packet is prepared. Explain dirty
state without altering it.

## Allowed work

- inspect repository roots, commits, branches, `git status`, and relevant
  integration paths;
- record whether benchmark files moved, were deleted, or became a separate
  repository boundary;
- identify user-owned dirty paths and known generated/cache paths;
- write task-local records and `handoff.md` only.

## Forbidden work

- no reset, checkout, clean, stash, move, delete, reformat, merge, or commit;
- no code or benchmark behavior changes;
- no inference that a dirty tree proves a defect without path-level evidence.

## Required broad outputs

- one record per component: root, revision, branch, dirty-state summary, and
  relevant integration boundary;
- list of packets made stale by a changed path or revision;
- recommended worktree starting points and protected user-owned paths;
- unresolved location/ownership questions for human review.

## Acceptance

All later mutable packets can name a concrete base and avoid overwriting dirty
user state. This task is a record, not a cleanup or release approval.

## Handoff

## Detailed execution contract - 2026-08-19

### Required component set

F0c has four records:

1. Trace-Lite component record.
2. Trace component record.
3. trace-bench component record.
4. Coordinator synthesis including program-control-plane snapshot.

Starter records under component-records identify expected observations but must
be refreshed. Do not infer identity from a folder name.

### Current observations to re-anchor

| Component | Observed identity | Required disposition |
| --- | --- | --- |
| Trace-Lite | Git fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1 | Record status; mark older 63bb3cb handoffs stale. |
| Trace | Git c855bb06532b3b52b25f0bea969d2677e5049065 on main, dirty V2 snapshot | Protect changes; no mutable base before accepted clean base. |
| trace-bench | External source root without Git identity | Record inventory/exclusions and P-007 need. |

Trace static inspection observed 26 tracked modified files, roughly 6,291
insertions and 187 deletions, untracked migration/control files, tracked-diff
SHA-256 7c8fad6257203dc71af2c08407c5a06b77cb9899b10101c259da97e4ae73881a,
and untracked-list SHA-256
05242cea3a984f2ece88e9fe9fcbbbf96265ea34836e5c2ae77c9fcc8297a996.
Refresh; do not blindly reuse.

### Required classification

Classify each dirty/untracked/ignored path as user implementation, migration,
test/fixture, documentation, generated/cache, result/output, or unknown.
Unknown/user paths remain protected. F0c never cleans, stages, relocates,
merges, or decides whether they should exist.

### Required synthesis

- repository-state.json per component;
- evidence/component-boundaries.md;
- evidence/protected-paths.md;
- evidence/stale-packet-matrix.md;
- evidence/benchmark-boundary-disposition.md;
- evidence/safe-worktree-recommendation.md;
- commands.md and handoff.md.

Stale matrix marks old TL base 63bb3cb handoffs stale, chat-only data/eval
handoffs non-durable, embedded benchmark assumptions stale, and T1 audit-only.

### Acceptance

F0c is accepted only when coordinator can prepare one bounded packet without
touching user state. It does not authorize a worktree if clean base absent.

Create `handoff.md` from `../../templates/HANDOFF.md` and give the coordinator
the exact state required to prepare B1, L1, T1, and V1.
