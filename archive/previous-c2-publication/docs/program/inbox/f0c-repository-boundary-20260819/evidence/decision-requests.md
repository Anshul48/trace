# Decision Requests Summary

> **Status:** Coordinator proposal for human program owner review.
> **Date:** 2026-08-19.

## 1. Immediate Decision Requests (Prerequisites for B1)

### Decision Request: P-007 (trace-bench Source Governance)
- **State:** Proposed / Awaiting Human Decision
- **Question:** What establishes canonical source identity for the moved `trace-bench` suite?
- **Options:**
  1. **Option A (Independent Git Repository):** Initialize `trace-bench` as an independent Git repository with semantic release tags and pinned dependency contracts.
  2. **Option B (Content-Manifest Archive):** Maintain `trace-bench` as an external tree governed by a canonical content manifest (`739d7f42fb...`), versioned tarball archives, and strict inclusion/exclusion rules.
- **Consequence of Deferral:** `trace-bench` remains unversioned and non-certifying. B1 cannot be prepared as a certifying runner.
- **Safe Default:** `trace-bench` is unversioned; no benchmark result certifies release readiness.

---

### Decision Request: P-008 (Canonical Certification Runner Boundary)
- **Problem:** `src/trace_lite/engines/benchmark.py` and `trace-bench/src/trace_bench/runner.py` coexist, creating dual runner surfaces with differing fallback semantics.
- **State:** Proposed / Awaiting Human Decision
- **Options:**
  1. **Option A (trace-bench Sole Certification Runner):** Designate `trace-bench` as the sole certification execution harness. Demote `trace_lite/engines/benchmark.py` to internal regression testing, marking its results non-certifying.
  2. **Option B (Re-embed trace-bench):** Re-integrate `trace-bench` into `trace-lite/benchmarks/`.
- **Consequence of Deferral:** No runner is certification-authoritative.
- **Safe Default:** Neither runner is certification-authoritative.

---

## 2. Downstream Human Decisions (Blocked on Upstream Evidence)

| Decision ID | Subject | Required Precedent Evidence | Current Status |
| --- | --- | --- | --- |
| **P-001** | Initial Real-Data Portfolio | F0b candidate dataset admission records and license review. | Proposed; awaits F0b handoff. |
| **P-002** | Bounded Graph Degree & PPR Budgets | L1 lifecycle completion and graph scaling benchmarks. | Blocked on L1 completion. |
| **P-003** | Unified Trace Cortex Release Schema | T1 read-only audit of Cortex Release state and migration tradeoffs. | Proposed; awaits T1 handoff. |
| **P-004** | Temporal & Revocation Semantics in Trace | T1 audit and research on valid-time vs. event history. | Proposed; awaits T1 handoff. |
| **P-005** | Numerical 100K Gate Thresholds | B1 fail-closed runner, B2 staged data, and baseline cost envelope. | Blocked on B1, B2. |
| **P-006** | Reflex & Entorhinal Shadow Adoption | Stable evidence bundle and verified 100K gate. | Blocked on M5 milestone. |
