# Session 4 — Trace Foundation

## Read first

1. `../prompts/GLOBAL_CONTEXT.md`
2. `../prompts/05_TRACE_ENGINEER.md`
3. `../FOUNDATION_RELEASE.md`
4. `../02_EXECUTION_DAG.md`
5. `../inbox/f0c-repository-boundary-20260819/packet.md`
6. `../inbox/t1-trace-cortex-release-audit/packet.md`

## Mission

Establish Trace's governed baseline: current release behavior, migration
boundary, and the concrete work needed for candidate/active isolation. Preserve
evented Spine truth, policy, recovery, and user-owned dirty changes.

## First work

- contribute the Trace portion of F0c;
- run the T1 audit/design packet in a read-only worktree or branch;
- prepare options for P-003/P-004 rather than choosing them;
- wait for accepted decisions before T2/TR1 or T3/TR2 mutation.

## Authority

May inspect Trace and write only task-local reports until a prepared mutation
packet exists. Must not transplant TL storage assumptions, change evaluator
policy, or make temporal/policy decisions unilaterally.

## Mandatory detail for this session

Read in this exact order after the initial list:

1. SESSION_OPERATING_MANUAL.md, COMPONENT_REGISTRY.md, FOUNDATION_STATUS.md.
2. 00_CHARTER.md, 01_INVARIANTS.md, 03_SHARED_CONTRACTS.md,
   FOUNDATION_GATE_DOSSIER.md, 06_DECISION_LOG.md, 07_RISK_REGISTER.md.
3. roles/05_trace_engineer.md and prompts/05_TRACE_ENGINEER.md.
4. F0c Trace component record and T1 packet.
5. Repository state, input manifest, worktree lease, verifier report, decision
   request templates.

### Required T1 outputs

1. Read/write map for hierarchy, affinity, activation priors, lexical/dense
   revisions, hot inbox, legacy hierarchy, evidence bundle, policy/time.
2. P-003 options: full rebuilt bundle versus release manifest carrying forward
   immutable components.
3. Additive migration concerns: release identity on affinity/prior,
   release-scoped uniqueness, active pointer, durable validation receipt,
   predecessor retention, external-index compensation, evidence identity,
   legacy backfill/retirement.
4. P-004 inputs: system/valid time, source lifecycle, supersession, revocation,
   tombstone/deletion, historical policy and release-pointer selection.
5. Narrow TR1/TR2 outlines. Do not implement them.

### Current source anchors

Verify path/line drift before citing affinity writes/reads, activation priors,
hierarchy active-run/as-of handling, query request time fields, event version
migration, and lexical/dense controller rollback. The dirty Trace snapshot is
audit input only, not an implementation base.
