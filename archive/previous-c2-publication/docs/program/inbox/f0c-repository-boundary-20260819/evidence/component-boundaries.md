# Component Boundaries Synthesis

> **Status:** Current observed boundaries across Trace-Lite, Trace, trace-bench, and Program Control Plane.
> **Date:** 2026-08-19.

## 1. Architectural Roles and Ownership

| Component | Canonical Root | Identity at Refresh | Architectural Role | Boundary Governance |
| --- | --- | --- | --- | --- |
| **Trace-Lite** | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite` | Git `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1` on `main` | Fast local experimental retrieval proving ground & embedded reference. | Isolated Git repo; Beta is canonical runtime (DEC-001); Alpha archived. |
| **Trace** | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace` | Git `c855bb06532b3b52b25f0bea969d2677e5049065` on `main` (active V2 development snapshot) | Governed, versioned, policy-aware memory infrastructure of record with an evented Spine. | Isolated Git repo; adopts only promoted mechanisms (DEC-002). |
| **trace-bench** | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench` | Unversioned (`.git` absent); 41 files; manifest SHA `739d7f42fb40c9234b716f5a30aa9e0acd224c4e486e24f95e4afa8f1ca36f1e` | External benchmark suite and multi-adapter evaluation harness. | External moved source tree; non-certifying until P-007 and P-008 are accepted. |
| **Program Control Plane** | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program` | Snapshot `foundation-control-plane-20260819-initial`; tree SHA `c65926092d2dc7b4472dd1ac4da2af853b2fd8a24ecd93c9b748bd37c16df2f5` | Canonical charter, invariants, DAG, contracts, decisions, risks, and task packets. | Governed solely under Trace `docs/program` by Coordinator (DEC-006). |

## 2. Cross-Component Interface Contracts

```text
               +-------------------------------------------+
               |           trace-bench (Harness)           |
               +--------------------+----------------------+
                                    |
                  (Dynamic unpinned imports / adapters)
                                    |
          +-------------------------+-------------------------+
          |                                                   |
          v                                                   v
+-----------------------+                           +-------------------+
|      Trace-Lite       |                           |       Trace       |
| (Local Lab / Embedded)|                           | (System of Record)|
+-----------------------+                           +-------------------+
          |                                                   |
          +-------------------------+-------------------------+
                                    |
                             (Shared Schema)
                                    v
               +-------------------------------------------+
               |        Evidence Bundle / Contracts        |
               +-------------------------------------------+
```

### Critical Cross-Component Touchpoints
1. **trace-bench -> Trace-Lite:** `trace_bench.baselines.trace_retriever` imports `trace_lite` directly. P-007/P-008 must formalize package versioning and import pinning.
2. **trace-bench -> Trace:** `trace_bench.baselines.trace_retriever` imports `trace.v2` components. Certification mode must never mock or synthesize adapter data.
3. **Trace-Lite internal benchmark -> trace-bench:** `src/trace_lite/engines/benchmark.py` coexists with `trace-bench`. P-008 designates `trace-bench` as the sole certification runner, retaining `engines/benchmark.py` for internal unit/regression checks only.
4. **Evidence Bundle:** Both runtimes must produce opaque, anchored evidence bundles conforming to `03_SHARED_CONTRACTS.md` with active release correlation.
