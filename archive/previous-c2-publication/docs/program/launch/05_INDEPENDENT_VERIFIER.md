# Session 5 — Independent Verifier

## Read first

1. `../prompts/GLOBAL_CONTEXT.md`
2. `../prompts/06_VERIFIER_INTEGRATION.md`
3. `../FOUNDATION_RELEASE.md`
4. `../02_EXECUTION_DAG.md`
5. `../inbox/f0a-e1-refresh-20260819/packet.md`
6. `../inbox/v1-v1a-integrity-verifier/packet.md`

## Mission

Remain independent of the implementation lanes. Establish the evidence matrix
and later test negative behavior: fallback resistance, candidate invisibility,
prior-active preservation, rollback, and contract outcomes.

## First work

- inspect packet completeness and define broad negative-case categories;
- verify F0 findings independently where possible;
- prepare V1 for execution after B1 exists;
- record failures without repairing the candidate.

## Authority

May create verification reports, fixtures, and test plans in its isolated
workspace when a packet permits. May not modify implementation under review,
relax acceptance criteria, promote a release, or substitute developer fixtures
for real certification evidence.

## Mandatory detail for this session

Read in this exact order after the initial list:

1. SESSION_OPERATING_MANUAL.md, COMPONENT_REGISTRY.md, FOUNDATION_STATUS.md.
2. 00_CHARTER.md, 01_INVARIANTS.md, 03_SHARED_CONTRACTS.md,
   04_EVALUATION_PROTOCOL.md, FOUNDATION_GATE_DOSSIER.md,
   06_DECISION_LOG.md, 07_RISK_REGISTER.md.
3. roles/06_verifier_integration.md and prompts/06_VERIFIER_INTEGRATION.md.
4. V0 packet before V1 packet.
5. Verifier report, error receipt, and capability matrix templates.

### V0 deliverables

- Immutable evaluator negative-case matrix for V1a.
- Lifecycle and temporal fault matrix for V1b.
- Verifier independence/worktree/environment requirements.
- Evidence retention/checksum/report format.
- Cases that cannot be certified with current fake/in-memory adapters.
- Packet-completeness review for F0/B1/L1/T1 successors.

### Independence constraints

Never repair candidate code before documenting failure. Never execute in
implementer worktree. Never infer PostgreSQL/RLS/external-index proof from
SQLite/in-memory/fake tests. Never treat hidden fallback as acceptable
developer convenience in certification mode.
