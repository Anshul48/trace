# S0 — Coordinator / Control-Plane Owner

## Mission

Turn the read-only foundation reports into a controlled implementation wave.
S0 is the only session that coordinates cross-lane state. It owns decisions,
leases, packet status, input manifests, risk state, and gate transitions. It
does not implement product code, download data, invoke providers, certify a
run, or merge another session's work.

## Start condition

Start S0 alone. It must read the global context, protocol, subagent rules,
foundation release, decision log, risk register, execution DAG, component
registry, and the F0a/F0b/F0c/T1/V0 handoffs. It must refresh all source
identities before changing any control-plane record.

## Responsibilities

### D0 decision reconciliation

Record the human owner's accepted decisions in the canonical decision log with:

- decision ID and selected option;
- date/authority/source of the decision;
- alternatives rejected and why;
- affected packets and dependencies;
- what remains deferred;
- evidence and claim boundary.

The intended launch records are P-001 core portfolio, P-003 release-root
architecture, P-007 dedicated trace-bench Git source, and P-008 sole
certification runner. Keep P-002, P-004, and P-005 explicitly pending. Do not
convert a recommendation in a handoff into a decision without the human
record.

### Source and boundary refresh

Re-anchor:

- Trace-Lite clean base `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1`;
- current dirty Trace commit, tracked diff, and untracked V2 surfaces;
- unversioned trace-bench content manifest;
- program-control-plane tree and protected untracked docs.

Mark all chat-only or stale-base evidence as non-certifying until refreshed.
Preserve the original working trees and never run destructive Git commands.

### Leases and input manifests

For each implementation packet, publish a lease containing:

- absolute worktree path;
- starting commit/content manifest;
- owner session and optional subagent IDs;
- allowed and forbidden paths;
- external scratch/database/data roots;
- verifier assignment;
- expiration/release rule;
- expected handoff path.

Use a separate absolute path for every mutable worktree. Validate that it is
not the user's active checkout and that it does not collide with another lease.

### Task board

Maintain lifecycle status for D0, B0/B1, L1/TL3/TL2, T0/TR1/TR2, D2a/D2b,
V1a/V1b, P-005/B3, Foundation Gate, and 100K/1M. Every status links to an
artifact and names its next hard dependency. Use `blocked` for missing
authority; never use “ready” as a substitute for an accepted lease.

### Dispatch

After the D0 handoff is durable, dispatch S1, S2, S3, and S4 in parallel. Do
not dispatch S5 until B1 has a complete implementation handoff. Do not dispatch
S6 until B1 and D2b have real manifests. Do not dispatch S7 until the
Foundation Gate is jointly accepted.

## Allowed changes

S0 may update only program-control-plane documents and packet-local planning or
handoff records. It may create lease/input-manifest directories. It must not
edit `src/`, migrations, tests, benchmark source, raw data, or provider config.

## Subagents

Use at most two read-only helpers:

1. a repository-state observer to compute current identities and protected paths;
2. a packet/dependency reconciler to compare handoffs with the DAG.

Helpers may not write product code or alter the decision log. S0 reviews their
reports before recording anything.

## Required outputs

- D0 handoff using `03_HANDOFF_TEMPLATE.md`;
- accepted/deferred decision record updates;
- refreshed component and source identity manifest;
- worktree lease records for S1-S4;
- current task board and risk update;
- dispatch note naming the exact next packets;
- explicit statement that no product/data/provider state changed.

## Acceptance criteria

- Every accepted decision is traceable to the human instruction and has no
  hidden threshold or temporal assumption.
- Every mutable packet has a concrete base, path scope, owner, verifier, and
  output location.
- The dirty Trace checkout and Trace-Lite user checkout are unchanged.
- No downstream packet is marked executable without its hard dependencies.
- The handoff distinguishes observation, preparation, authorization, and
  certification.

## Stop conditions

Stop and report `blocked` if:

- the human decision cannot be located;
- a source identity has drifted or a worktree is unexpectedly dirty;
- a lease path is not absolute, unique, or safe;
- a packet requires a missing schema/manifest/verifier;
- a worker attempts to claim a gate or change code outside its scope.
