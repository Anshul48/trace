# TRACE-CAP-001 Responsibility & Exclusive Lease Map

> **Document ID:** `TRACE-CAP-001-LEASE-MAP`
> **Plan Reference:** [`COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`](COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md)
> **DAG Reference:** [`CAP_001_EXECUTION_DAG.md`](CAP_001_EXECUTION_DAG.md)
> **Status:** Governing Responsibility and Lease Allocation.
> **Principle:** Strict separation of implementation from verification. No agent, role, or session may verify, audit, or certify code, data, or documentation that it authored.

---

## 1. Role Definitions & Non-Colliding Authority Boundaries

| Role ID | Role Name | Allowed Authority | Strictly Prohibited Authority |
|---|---|---|---|
| **`HUMAN-OWNER`** | Project Architect / Human Owner | Architecture ratification, budget approval, scale authorizations, release promotions. | None (Ultimate program authority). |
| **`COORD`** | Program Coordinator | DAG tracking, work packet assignment, lease issuance, dossier compilation, blocker escalation. | Runtime code editing; test-suite modification; self-certification of gates. |
| **`ARCH-SPEC`** | Architecture Specialist | Governance documentation amendments (`docs/program/`), decision cross-referencing. | Writing runtime code in `src/`; modifying test assertions; verifying own diffs. |
| **`GW-SPEC`** | Gateway Safety Specialist | `src/trace/v2/model_gateway.py` fail-closed semantics, gateway exception handling. | Relaxing safety tests; issuing self-verification receipts; running unbudgeted calls. |
| **`GW-ECON`** | Economics Specialist | Model pricing registry, token budget reservation, spend telemetry. | Falsifying cost estimates; modifying retrieval or core storage code. |
| **`RET-SPEC`** | Retrieval Specialist | `src/trace/v2/retrieval.py`, dense embedding adapter, BM25+Dense RRF fusion, graph walks. | Modifying evaluation ground-truth qrels; self-verifying retrieval baseline gates. |
| **`CRX-SPEC`** | Cortex Specialist | `src/trace/v2/cortex/`, `cortex_consolidator.py`, risk-tiered activation logic. | Touching canonical Spine WAL tables; bypassing detached validation checks. |
| **`INFRA-SPEC`** | Infrastructure Specialist | `src/trace/v2/service.py` job queues, heartbeats, lease timeouts, crash recovery. | Modifying evaluation protocols; altering model invocation logic. |
| **`EVAL-SPEC`** | Evaluation Specialist | `docs/program/04_EVALUATION_PROTOCOL.md`, benchmark manifests, faithfulness validator tooling. | Implementing candidate algorithms; modifying production runtime code. |
| **`MOD-SPEC`** | Model Specialist | Local SLM bake-off execution, Pareto frontier analysis, model configuration files. | Calling cloud models without budget cap; writing to production Spine database. |
| **`INT-SPEC`** | Integration Specialist | 10K shadow execution, 100K paired qualification test harnesses. | Fabricating run logs; merging candidate branches before verifier signoff. |
| **`SYN-SPEC`** | Synthesis Specialist | Answer generation evaluation harness, citation precision/recall scoring. | Generating ungrounded assertions; writing to system knowledge graphs. |
| **`SCALE-OP`** | Scale Operator | 1M Core and 1M Cortex run execution under explicit Human Owner authorization. | Modifying gate thresholds; self-attesting to scale qualification. |
| **`VERIF-INDEP`** | Codex Independent Verifier | Detached verification runs from clean worktrees, cryptographic audit of receipts. | Editing any candidate code, documentation, or benchmark under review. |

---

## 2. Complete Node Responsibility & Lease Map

The table below defines the exclusive write leases and verification boundaries for every node in [`CAP_001_EXECUTION_DAG.md`](CAP_001_EXECUTION_DAG.md).

```text
========================================================================================================================
                                     TRACE-CAP-001 EXCLUSIVE LEASE TABLE
========================================================================================================================
```

| Node ID | Primary Assignee | Prohibited Roles | Independent Verifier | Exclusive Writable File Lease Paths | Read-Only Dependency Paths |
|---|---|---|---|---|---|
| **`CAP-A01`** | `HUMAN-OWNER` | All AI Agents | `VERIF-INDEP` | `docs/program/06_DECISION_LOG.md` (append only) | `CAP_001_CONTRADICTION_LEDGER_AND_DECISION_REQUEST.md` |
| **`CAP-A02`** | `ARCH-SPEC` | `VERIF-INDEP`, `RET-SPEC` | `VERIF-INDEP` | `docs/program/00_CHARTER.md`<br>`docs/program/01_INVARIANTS.md`<br>`docs/program/02_EXECUTION_DAG.md`<br>`docs/program/03_SHARED_CONTRACTS.md`<br>`docs/program/04_EVALUATION_PROTOCOL.md`<br>`docs/program/05_PROMOTION_RUBRIC.md`<br>`docs/program/07_RISK_REGISTER.md`<br>`docs/program/SCALE_*.md`<br>`docs/program/README.md` | `06_DECISION_LOG.md`<br>`COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` |
| **`CAP-A03`** | `COORD` | `ARCH-SPEC`, `VERIF-INDEP` | `VERIF-INDEP` | `docs/program/CONTROL_PLANE_LOCK.json`<br>`docs/program/FOUNDATION_STATUS.md` | All `docs/program/*.md` files |
| **`CAP-GW01`** | `GW-SPEC` | `VERIF-INDEP`, `CRX-SPEC` | `VERIF-INDEP` | `src/trace/v2/model_gateway.py`<br>`tests/v2/test_model_gateway_failclosed.py` | `src/trace/v2/types.py`<br>`01_INVARIANTS.md` |
| **`CAP-GW02`** | `GW-ECON` | `VERIF-INDEP`, `GW-SPEC` | `VERIF-INDEP` | `src/trace/v2/model_gateway.py` (pricing section)<br>`tests/v2/test_model_cost.py` | `src/trace/v2/types.py`<br>`COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` |
| **`CAP-GW03`** | `GW-ECON` | `VERIF-INDEP`, `GW-SPEC` | `VERIF-INDEP` | `src/trace/v2/model_gateway.py` (budget section)<br>`tests/v2/test_budget_cap.py` | `tests/v2/test_model_cost.py` |
| **`CAP-RET01`**| `RET-SPEC` | `VERIF-INDEP`, `EVAL-SPEC` | `VERIF-INDEP` | `src/trace/v2/retrieval.py` (embedding section)<br>`src/trace/v2/adapters/embedding.py`<br>`tests/v2/test_retrieval_embedding.py` | `src/trace/v2/types.py` |
| **`CAP-RET02`**| `RET-SPEC` | `VERIF-INDEP`, `EVAL-SPEC` | `VERIF-INDEP` | `src/trace/v2/retrieval.py` (RRF fusion section)<br>`tests/v2/test_hybrid_retrieval.py` | `src/trace/v2/adapters/embedding.py` |
| **`CAP-RET03`**| `RET-SPEC` | `VERIF-INDEP`, `EVAL-SPEC` | `VERIF-INDEP` | `src/trace/v2/retrieval.py` (graph walk section)<br>`tests/v2/test_graph_retrieval.py` | `src/trace/v2/retrieval.py` |
| **`CAP-RET04`**| `VERIF-INDEP` | `RET-SPEC`, `COORD` | `VERIF-INDEP` | `docs/program/inbox/cap-ret04/` | `src/trace/v2/retrieval.py`<br>`benchmarks/manifests/` |
| **`CAP-CRX01`**| `CRX-SPEC` | `VERIF-INDEP`, `INFRA-SPEC`| `VERIF-INDEP` | `src/trace/v2/cortex/` (all schema files)<br>`tests/v2/test_cortex_schemas.py` | `src/trace/v2/types.py`<br>`01_INVARIANTS.md` |
| **`CAP-CRX02`**| `CRX-SPEC` | `VERIF-INDEP`, `GW-SPEC` | `VERIF-INDEP` | `src/trace/v2/organization.py`<br>`src/trace/v2/cortex_consolidator.py`<br>`tests/v2/test_cortex_consolidator.py` | `src/trace/v2/cortex/`<br>`src/trace/v2/model_gateway.py` |
| **`CAP-CRX03`**| `CRX-SPEC` | `VERIF-INDEP`, `INFRA-SPEC`| `VERIF-INDEP` | `src/trace/v2/service.py` (activation section)<br>`src/trace/v2/store.py` (pointer swap section)<br>`tests/v2/test_cortex_activation.py` | `src/trace/v2/cortex/`<br>`benchmarks/evaluators/` |
| **`CAP-JOB01`**| `INFRA-SPEC`| `VERIF-INDEP`, `CRX-SPEC` | `VERIF-INDEP` | `src/trace/v2/service.py` (job chaining section)<br>`tests/v2/test_job_pipeline.py` | `src/trace/v2/cortex_consolidator.py` |
| **`CAP-JOB02`**| `INFRA-SPEC`| `VERIF-INDEP`, `CRX-SPEC` | `VERIF-INDEP` | `src/trace/v2/service.py` (lease/heartbeat section)<br>`src/trace/v2/store.py` (job recovery section)<br>`tests/v2/test_job_recovery.py` | `tests/v2/test_job_pipeline.py` |
| **`CAP-EVAL01`**| `EVAL-SPEC` | `VERIF-INDEP`, `RET-SPEC` | `VERIF-INDEP` | `docs/program/04_EVALUATION_PROTOCOL.md`<br>`benchmarks/protocols/` | `01_INVARIANTS.md`<br>`06_DECISION_LOG.md` |
| **`CAP-EVAL02`**| `EVAL-SPEC` | `VERIF-INDEP`, `RET-SPEC` | `VERIF-INDEP` | `benchmarks/manifests/`<br>`docs/program/inbox/cap-eval02/` | `docs/program/04_EVALUATION_PROTOCOL.md` |
| **`CAP-EVAL03`**| `EVAL-SPEC` | `VERIF-INDEP`, `CRX-SPEC` | `VERIF-INDEP` | `benchmarks/evaluators/faithfulness_validator.py`<br>`tests/evaluators/test_faithfulness.py` | `docs/program/04_EVALUATION_PROTOCOL.md` |
| **`CAP-MOD01`**| `MOD-SPEC` | `VERIF-INDEP`, `COORD` | `VERIF-INDEP` | `docs/program/inbox/cap-mod01/` | `src/trace/v2/model_gateway.py`<br>`benchmarks/data/` |
| **`CAP-MOD02`**| `MOD-SPEC` | `VERIF-INDEP`, `HUMAN-OWNER`| `VERIF-INDEP` | `docs/program/inbox/cap-mod02/` | `docs/program/inbox/cap-mod01/` |
| **`CAP-INT01`**| `INT-SPEC` | `VERIF-INDEP`, `COORD` | `VERIF-INDEP` | `docs/program/inbox/cap-int01/` | `src/trace/v2/`<br>`benchmarks/data/` |
| **`CAP-INT02`**| `INT-SPEC` | `VERIF-INDEP`, `SCALE-OP` | `VERIF-INDEP` | `docs/program/inbox/cap-int02/` | `src/trace/v2/`<br>`benchmarks/data/` |
| **`CAP-INT03`**| `SYN-SPEC` | `VERIF-INDEP`, `INT-SPEC` | `VERIF-INDEP` | `docs/program/inbox/cap-int03/` | `docs/program/inbox/cap-int02/` |
| **`CAP-SCALE01`**| `SCALE-OP` | `VERIF-INDEP`, `COORD` | `VERIF-INDEP` | `docs/program/inbox/cap-scale01/` | `src/trace/v2/`<br>`benchmarks/` |
| **`CAP-SCALE02`**| `SCALE-OP` | `VERIF-INDEP`, `COORD` | `VERIF-INDEP` | `docs/program/inbox/cap-scale02/` | `docs/program/inbox/cap-scale01/`<br>`src/trace/v2/` |
| **`CAP-VER-*`** | `VERIF-INDEP` | All Implementers | `VERIF-INDEP` | `docs/program/inbox/cap-ver-*/` | Target node worktrees & receipts |

---

## 3. Lease Acquisition & Release Protocol

1. **Lease Issuance:** Only the Program Coordinator (`COORD`) issues write leases. A lease specifies `Node ID`, `Branch Name`, `Exclusive Paths`, `Expiry Timestamp (UTC)`, and `Assigned Role`.
2. **Branch Concurrency:** Parallel Wave B workers must operate in isolated Git worktrees. Two workers with overlapping paths (e.g. `GW-SPEC` and `GW-ECON` on `model_gateway.py`) must be executed sequentially or on isolated file sections with strict merge ordering.
3. **Lease Expiry & Reclamation:** If a worker does not submit deliverables within its time budget, the Coordinator reclaims the lease, resets the branch to clean base, and escalates to the Human Owner.
4. **Independent Verification Protocol:** Once deliverables are committed, the worker signals completion. The Coordinator issues a verification task to `VERIF-INDEP`. The Independent Verifier checks out a fresh, detached worktree, executes acceptance commands, verifies raw receipts, and files the `verification_receipt.json`. Under no circumstances may an implementer approve their own PR or sign their own gate receipt.
