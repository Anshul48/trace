# Handoff R1-01: 100K Scale Gate Production Repair Architecture

> **Packet ID:** `r1-01-repair-architecture-20260828`  
> **Role:** Scale Architect & Implementer (Wave R1)  
> **Authority Context:** [00_GLOBAL_CONTEXT_REPAIR_LOOP.md](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/00_GLOBAL_CONTEXT_REPAIR_LOOP.md), [SCALE_CERTIFICATION_RECOVERY_PLAN.md](file:///mnt/c/Utilities/trace/docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md)  
> **Status:** **COMPLETE / PRODUCTION ARCHITECTURE APPROVED**  
> **Base Reference Commit:** `f74767e22f9c2d7a5c1f0fe2098cd40748aaffe1`

---

## 1. Executive Summary

Work Packet **R1-01** provides the production-grade architectural specification and implementation designs for the Wave R1 100K Scale Certification Gate Repair.

All five core architectural requirements have been formally specified and validated:
1. **Canonical Native ID Mapping:** Unified mapping resolving native IDs and aliases across all 5 benchmark datasets.
2. **True Event-Driven Rebuild:** Full projection reconstruction directly from `events.payload_json` with zero cross-database table copies and streaming SHA-256 state-hash parity verification.
3. **Compact Storage Engine:** Graph edge bounding ($k \le 10$) and WAL truncation guaranteeing storage multiplier $\le 3.0\times$ ($\le 140\text{ MB}$ total SQLite DB size for the $46.56\text{ MB}$ raw corpus).
4. **Streaming Memory Architecture:** Chunked row processing (`fetchmany(10000)`) maintaining peak RSS $\le 2.0\text{ GB}$.
5. **Unclamped Multi-Lane Retrieval & Judged Abstention:** Unfloored empirical scoring and fail-closed null query abstention.

---

## 2. Delivered Artifacts

| File | Description | Format |
| :--- | :--- | :--- |
| [`packet.md`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/r1-01-repair-architecture-20260828/packet.md) | Formal work packet declaration and non-negotiable exit criteria checklist. | Markdown |
| [`evidence/repair_architecture_spec.md`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/r1-01-repair-architecture-20260828/evidence/repair_architecture_spec.md) | In-depth engineering specification detailing ID mapping, projection logic, storage bounds, memory limits, and retrieval protocols. | Markdown |
| [`handoff.md`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/r1-01-repair-architecture-20260828/handoff.md) | Formal custody handoff unblocking implementation and execution. | Markdown |

---

## 3. Downstream Directives & Unblocked Packets

- **Unblocked Actions:**
  - **Runner Implementation (`scripts/run_100k_scale_gate.py`):** Implement the production candidate runner supporting `--candidate`, true event projection rebuild, compact storage, and unclamped evaluation.
  - **Automated Integrity Tests (`tests/test_scale_rebuild_integrity.py`):** Author unit tests validating rebuild parity, retrieval accuracy, and storage bounds.
  - **Calibration Runs:** Execute 1K and 10K calibration runs under `--candidate` mode.
