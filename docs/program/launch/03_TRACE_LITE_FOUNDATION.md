# Session 3 — Trace-Lite Foundation

## Read first

1. `../prompts/GLOBAL_CONTEXT.md`
2. `../prompts/04_TRACE_LITE_ENGINEER.md`
3. `../FOUNDATION_RELEASE.md`
4. `../02_EXECUTION_DAG.md`
5. `../inbox/f0c-repository-boundary-20260819/packet.md`
6. `../inbox/l1-tl1-candidate-active-lifecycle/packet.md`

## Mission

Make Beta's current baseline safe and reproducible without reviving Alpha or
changing the benchmark policy. The first mutable target is release lifecycle
isolation; bounded graph work is a later decision-gated packet.

## First work

- contribute the TL portion of F0c: current commit, dirty state, relevant
  projection/graph/query anchors, and test entry points;
- do not edit product code until the coordinator pins L1;
- after L1 is prepared, work in an isolated TL worktree only.

## Authority

May inspect TL now. Later may modify only L1-approved paths. May not modify
Trace, the separate benchmark suite, global evaluator policy, raw datasets, or
canonical program decisions.

## Mandatory detail for this session

Read in this exact order after the initial list:

1. SESSION_OPERATING_MANUAL.md, COMPONENT_REGISTRY.md, FOUNDATION_STATUS.md.
2. 00_CHARTER.md, 01_INVARIANTS.md, 03_SHARED_CONTRACTS.md,
   FOUNDATION_GATE_DOSSIER.md, 06_DECISION_LOG.md, 07_RISK_REGISTER.md.
3. roles/04_trace_lite_engineer.md and prompts/04_TRACE_LITE_ENGINEER.md.
4. F0c Trace-Lite component record template and L1 scoped packet.
5. Repository state, worktree lease, verifier report, capability matrix
   templates.

### Required F0c contribution

Record TL root, commit/branch, dirty/untracked paths, protected user changes,
projection/activation/query anchors, legacy benchmark integration paths, test
entry points, and safe worktree-base recommendation. Do not decide whether
existing dirty changes are correct.

### L1 preparation boundary

L1 is candidate/active lifecycle only:

- map every projection read/write path;
- identify candidate identity, active selector, normal-read filter,
  validation, failure, retention, rollback;
- make no graph policy choice;
- leave DF/degree/PPR/latency/memory settings to P-002 and TL2.

L1 cannot be mutable until F0c is complete and clean lease/verifier matrix
exists.

## Later queued work

`L2 / TL2` requires accepted P-002. Deep bio-inspired graph research waits for
Foundation Complete and becomes an experiment, not an unreviewed rewrite.
