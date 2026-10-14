# Stale Packet & Evidence Matrix

> **Status:** Current disposition of past handoffs, memos, and candidate packets as of 2026-08-19.

| Packet / Evidence ID | Subject | Prior Assumption | Current Reality | Status | Required Action |
| --- | --- | --- | --- | --- | --- |
| **Legacy TL Handoffs** | Trace-Lite base commit | Assumed Git commit `63bb3cb` | Current Git commit is `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1` on `main`. | **STALE** | Invalidate all references to `63bb3cb`; re-anchor L1 to `fe66a9e`. |
| **Chat-only Data Memos** | Dataset admission / staging | Discussed data downloads and synthetic samples in chat. | No data admitted without formal admission record and human P-001 decision. Synthetic data prohibited (DEC-008, R-04). | **NON-DURABLE / INVALID** | F0b must close durable candidate records; B2 staged only after P-001. |
| **Chat-only Eval Audits** | Benchmark evaluation claims | Evaluator results cited in conversation without frozen manifests. | trace-bench is unversioned; mock defaults and flat-fallbacks exist. | **NON-CERTIFYING** | F0a re-anchors static audit; B1 creates fail-closed runner; V1a verifies independently. |
| **Embedded Benchmark Packets** | Benchmark location | Assumed benchmarks reside solely inside `trace-lite/benchmarks/`. | Benchmark suite moved to external `trace-bench` tree. | **STALE** | P-007 decides source governance; P-008 decides runner boundary. |
| **L1 Packet** | TL Candidate/Active Lifecycle | Scoped broadly; lacked isolated worktree and verifier assignment. | Requires clean lease at `fe66a9e`, exact allowed paths, and V1b assignment. | **SCOPED (NOT PREPARED)** | Prepare concrete manifest, lease, and verifier matrix before assignment. |
| **TL2 Packet** | Bounded Graph & PPR Budgets | Proposed graph degree and PPR limits without decision. | All-pairs co-occurrence loop observed in `graph.py` ($O(n^2)$ term frequency). | **BLOCKED** | Blocked on L1 completion and human acceptance of P-002. |
| **T1 Packet** | Trace Cortex Release Audit | Assumed migration 004 was deployed or canonical. | Migration 004 and `v2/cortex.py` are uncommitted snapshots; candidate affinity/priors leak. | **READY (READ-ONLY)** | Dispatch read-only T1 audit to map read/write and evaluate P-003/P-004 alternatives. |
| **TR1 Packet** | Unified Cortex Release Implementation | Assumed ready for coding. | Blocked on T1 audit and human acceptance of P-003. | **BLOCKED** | Do not dispatch until P-003 accepted and isolated worktree leased. |
| **TR2 Packet** | Temporal & Revocation Implementation | Assumed partial event versioning was sufficient. | Valid-time, historical release selection, and revocation require P-004 decision. | **BLOCKED** | Do not dispatch until TR1 complete and P-004 accepted. |
| **B1 Packet** | Fail-Closed Runner | Assumed ready for dispatch. | Blocked on F0a audit, P-007 (source governance), and P-008 (runner boundary). | **SCOPED (NOT PREPARED)** | Prepare after F0a, P-007, and P-008. |
| **B2 / B3 Packets** | Data Staging & Certification Manifest | Assumed real data could be staged immediately. | Blocked on F0b, source authority, P-001, B1 runner, and P-005 thresholds. | **BLOCKED** | Keep strictly blocked until prerequisites are met. |
| **V0 Packet** | Independent Verifier Plan | Verifier planning. | Ready for read-only dispatch to freeze V1a/V1b test matrices. | **PREPARED (READ-ONLY)** | Ready for verifier session dispatch. |
| **100K / 1M / Shadow Gates** | Scale and adoption | Speculative roadmaps. | All scale/shadow gates blocked behind Foundation Complete. | **BLOCKED** | Enforce DAG discipline. |
