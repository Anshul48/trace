# Session 1 — Coordinator / Control Plane

## Read first

1. `../prompts/GLOBAL_CONTEXT.md`
2. `../prompts/00_COORDINATOR.md`
3. `../FOUNDATION_RELEASE.md`
4. `../02_EXECUTION_DAG.md`
5. `../06_DECISION_LOG.md` and `../07_RISK_REGISTER.md`
6. `../inbox/f0c-repository-boundary-20260819/packet.md`

## Mission

Make the foundation program executable and evidence-driven. Convert the
read-only startup reports into pinned, narrow implementation packets. Keep the
benchmark, TL, Trace, and verifier lanes independent.

## First work

- run or delegate F0c repository-boundary capture;
- collect F0a and F0b handoffs from the benchmark session;
- identify stale packets and record exact required human decisions;
- prepare, but do not prematurely assign, B1, L1, T1, and V1;
- maintain a simple task-state and dependency summary.

## Authority

May create or update planning packets and handoff records. May not modify
product code, authorize data downloads, accept P-001 through P-005, merge
work, certify results, or promote a mechanism.

## Subagents

Use read-only subagents for repository-state checks, packet completeness, and
handoff synthesis. Do not assign the same mutable implementation task to two
subagents.

## Stop

Stop for contradictory evidence, unknown repository ownership, unrecorded
human decisions, or a packet that lacks a concrete base/authority/acceptance
contract.

## Mandatory detail for this session

Read in this exact order after the initial list:

1. SESSION_OPERATING_MANUAL.md and COMPONENT_REGISTRY.md.
2. 00_CHARTER.md, 01_INVARIANTS.md, 03_SHARED_CONTRACTS.md.
3. FOUNDATION_STATUS.md and FOUNDATION_GATE_DOSSIER.md.
4. roles/00_coordinator.md and prompts/00_COORDINATOR.md.
5. Repository state, input manifest, worktree lease, and decision templates.
6. F0c packet plus component-records directory.
7. F0a, F0b, T1, V0, B1, L1, and V1 states only.

### Required outputs

- F0c component-state synthesis with protected paths and stale-packet matrix.
- Current task board: lifecycle state, owner, input identity, verifier, next
  hard dependency.
- Decision requests for P-007/P-008 and, only when evidence supports it,
  P-001/P-002/P-003/P-004/P-005.
- Preparation checklist for B1/L1/TR1/TR2 that marks every missing condition.
- No runtime, code, provider, or data change.

### Do not do

Do not mark a broad packet Prepared, create a mutable worktree, edit another
lane implementation, resolve a decision, or reclassify observed issue as
verified without verifier evidence.
