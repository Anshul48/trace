# Foundation Task Board

> **Status:** Current operational task board as of 2026-08-19.
> **Governed by:** Coordinator.

| Node | Packet ID | State | Session / Role | Input Identity | Verifier Assignment | Next Hard Dependency |
| --- | --- | --- | --- | --- | --- | --- |
| **C0** | Program Control Plane | accepted | Coordinator | Snapshot `foundation-control-plane-20260819-initial` (`c6592609...`) | Self-locking (`CONTROL_PLANE_LOCK.json`) | Unblocks F0a, F0b, F0c, V0 |
| **F0c** | `f0c-repository-boundary-20260819` | handed_off (read-only) | Coordinator | TL `fe66a9e`, Trace `c855bb0`, trace-bench `739d7f4` | Peer review / Control plane lock | Synthesis unblocks T1 dispatch & P-007/P-008 requests |
| **F0a** | `f0a-e1-refresh-20260819` | ready (read-only) | Benchmark (Evaluation Engineer) | `trace-bench` root + TL benchmark code | Evaluator review | Unblocks B1 scoping & P-008 evidence |
| **F0b** | `f0b-d1-refresh-20260819` | ready (read-only) | Benchmark (Data Steward) | Candidate dataset metadata & licenses | Schema conformance review | Unblocks P-001 decision request |
| **V0** | `v0-verifier-plan-20260819` | ready (read-only) | Independent Verifier | F0c repository records + program invariants | Verifier self-consistency | Produces frozen V1a & V1b negative matrices |
| **T1** | `t1-trace-cortex-release-audit` | ready (read-only) | Trace (Trace Engineer) | Trace `src/trace/v2/` + migrations snapshot | Architecture review | Produces P-003 & P-004 decision inputs |
| **B1** | `b1-e2a-fail-closed-runner` | scoped (not prepared) | Benchmark (Evaluation Engineer) | trace-bench source under P-007 + P-008 | V1a (Independent Verifier) | Blocked on F0a handoff, P-007, and P-008 |
| **L1** | `l1-tl1-candidate-active-lifecycle` | scoped (not prepared) | Trace-Lite (Trace-Lite Engineer) | TL `fe66a9e` isolated worktree | V1b (Independent Verifier) | Blocked on concrete manifest, lease, and verifier assignment |
| **TL2** | `tl2-bounded-association-20260819` | blocked | Trace-Lite (Trace-Lite Engineer) | L1 handoff | V1b | Blocked on L1 completion and P-002 acceptance |
| **TL3** | `tl3-durable-provenance-proof-20260819` | blocked | Trace-Lite (Trace-Lite Engineer) | L1 handoff | V1b | Blocked on L1 completion |
| **TR1** | `tr1-unified-cortex-release-20260819` | blocked | Trace (Trace Engineer) | T1 audit handoff + clean base lease | V1b | Blocked on T1 handoff and P-003 acceptance |
| **TR2** | `tr2-temporal-revocation-20260819` | blocked | Trace (Trace Engineer) | TR1 handoff | V1b | Blocked on TR1 completion and P-004 acceptance |
| **V1a** | `v1a-runner-integrity-20260819` | blocked | Independent Verifier | B1 implementation handoff | Independent verification report | Blocked on B1 completion and separate worktree |
| **V1b** | `v1b-lifecycle-temporal-verifier-20260819` | blocked | Independent Verifier | L1/TL2 and TR1/TR2 handoffs | Independent verification report | Blocked on implementation handoffs |
| **B2** | `b2-authorized-data-staging-20260819` | blocked | Benchmark (Data Steward) | F0b handoff + P-001 acceptance | Verifier checksum verification | Blocked on P-001 and download authority |
| **B3** | `b3-certification-manifest-20260819` | blocked | Benchmark (Evaluation Engineer) | B1 runner + B2 staged data + P-005 | V1a / Verifier | Blocked on B1, B2, and P-005 acceptance |
| **F1** | Foundation Verification & Repair | blocked | Coordinator / Verifier | Consolidated V1a & V1b evidence | Verifier consolidation | Blocked on V1a and V1b completion |
| **F2** | Foundation Complete Dossier | blocked | Coordinator / Program Owner | F1 verification report | Human Program Owner review | Blocked on F1 completion |
