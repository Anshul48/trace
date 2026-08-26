# Session 1 - S0 R1 Control-Plane Reconciliation

Read the shared bootstrap prompt first. You are the sole cross-lane
control-plane writer. Do not modify product code, migrations, benchmark code,
raw data, provider configuration, or user checkouts.

## Mission

Reconcile the completed implementation wave into the honest program state:
implementation_complete / independent_verification_pending.

## Inspect and reconcile

- Refresh identities and cleanliness for B1, L1, TR1, D2a, and every existing
  verifier packet.
- Treat the untracked trace-bench uv.lock as an identity blocker for V1a.
- Split V1b into explicit sub-gates: TL lifecycle, Trace release, TL graph,
  and Trace temporal.
- Inventory downstream-looking packet directories. Classify each as active
  evidence, planning material, historical material, or unverified; filenames
  alone are not evidence.
- Check existing lease expiry and issue fresh, isolated leases for S1 follow-up,
  S5 verifier worktrees/scratch roots, and S4 D2b.
- Keep P-002, P-004, and P-005 deferred.

## Outputs

- refreshed status board, risk state, and source-identity manifest;
- verifier assignments, including replacing TR1's pending verifier identifier;
- a concise reconciliation handoff naming exact next sessions and blockers.

## Suggested subagents

Use up to two read-only helpers: one repository-state observer and one
packet/DAG reconciler. Do not delegate a control-plane decision or let a helper
write program records.

## Exit

Stop only when every next session has a safe base, owner, path, lease, and
handoff destination. If any identity is unclear, mark the affected session
blocked rather than dispatching it.

## Authoritative inputs to inspect

At minimum inspect the live versions of:

- docs/program/06_DECISION_LOG.md;
- docs/program/07_RISK_REGISTER.md;
- docs/program/FOUNDATION_STATUS.md;
- docs/program/COMPONENT_REGISTRY.md;
- the implementation-wave README, DAG, and S0/S1/S4/S5 briefs;
- D0, B1, L1, TR1, D2a, V1a, and V1b packet directories;
- all existing TL2, TR2, B3, and Foundation Gate-looking directories.

Refresh, rather than trust, the following identities: Trace-Lite L1 commit
7ff40dc..., Trace TR1 commit 454c5ae..., trace-bench B1 commit 0b01de5... plus
its actual untracked state, and the external D2a manifest root.

## Required execution record

Create a new R1 packet directory rather than rewriting D0. Use names that
make the reconciliation date and role clear, for example:

- input-manifest.json;
- repository-state.json;
- packet-reconciliation.md;
- commands.md;
- leases for S1 follow-up, S5 V1a, S5 V1b, and S4 D2b;
- handoff.md.

The task board must show the exact next packet, its hard dependency, its
claim level, and its safe default. Record that no product, data, provider, or
user checkout state changed.

## Status reconciliation rules

The program-level label must be
implementation_complete / independent_verification_pending. Keep
implementation completion separate from verifier acceptance. Mark V1b-TL
lifecycle and V1b-Trace release independently executable; leave V1b-TL graph
and V1b-Trace temporal blocked until TL2/TR2. If an existing downstream
document claims more than its linked evidence, preserve it as historical or
planning material and open a narrow correction note.

## Acceptance checklist

- all source identities are fresh and reproducible;
- the trace-bench lock issue is an explicit V1a blocker;
- the original Trace and Trace-Lite checkouts remain untouched;
- every verifier has a separate worktree and scratch root;
- P-002, P-004, and P-005 remain human-owned;
- no session is labeled executable without the required lease and handoff.
