# F0c — Trace Component Record

> **Contract Version:** 1.0
> **Record ID:** trace-f0c-20260819
> **Captured At:** 2026-08-19T04:41:00Z
> **Captured By:** Trace Foundation Engineer
> **Component:** Trace
> **Canonical Root:** `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace`

---

## 1. Identity and Source Control

| Field | Value | Notes |
| :--- | :--- | :--- |
| **Identity Kind** | `git` | Local Git repository |
| **Remote URL** | `https://github.com/Anshul48/trace.git` | Primary origin |
| **Current Branch** | `main` | Ahead of `origin/main` by 3 commits |
| **Commit Hash** | `c855bb06532b3b52b25f0bea969d2677e5049065` | Base commit identity |
| **Tag** | `null` | No release tag assigned |
| **Identity Certifying** | `false` | Working tree contains uncommitted user V2 snapshot |

---

## 2. Working Tree State & Dirty Classification

The Trace working tree is **not clean**. It contains 26 tracked modified files and 5 untracked surfaces representing active user V2 development.

### Fingerprints
- **Tracked Modified Count:** 26 files
- **Tracked Diff SHA-256:** `00d6c966b9a8cdfe6ca0c0ec3456766017450660b6eb018e3890370df18fb180`
- **Untracked Path List SHA-256:** `77771e9e0e067198711e335319976ef80d96e42500b11ab27809e827b55d7ab8`

### Path Classification & Protection Matrix

| Relative Path | State | Classification | Protected | Notes & Disposition |
| :--- | :--- | :--- | :---: | :--- |
| `docs/program/` | Untracked | Documentation | **Yes** | Canonical program control plane pack and task inboxes. |
| `migrations/004_cortex_projection_control_plane.sql` | Untracked | Migration | **Yes** | Proposed V2 Cortex projection control plane SQL schema. Deployment status unknown. Must not be amended or applied without an approved mutation packet. |
| `src/trace/v2/__main__.py` | Untracked | User Code | **Yes** | V2 entrypoint implementation. |
| `src/trace/v2/cortex.py` | Untracked | User Code | **Yes** | Pure localized activation engine & helper structures. |
| `tests/test_v2_cortex_controls.py` | Untracked | Test / Fixture | **Yes** | Unit tests for V2 Cortex projection controls & activation. |
| `src/trace/v2/store.py` | Tracked Modified | User Code | **Yes** | Materialized SQLite store (+1358 lines) with Cortex projection & affinity methods. |
| `src/trace/v2/service.py` | Tracked Modified | User Code | **Yes** | Trace V2 application service (+1605 lines) with query orchestration & job runner. |
| `src/trace/v2/production.py` | Tracked Modified | User Code | **Yes** | PostgreSQL production store (+1072 lines) with RLS & Cortex projection methods. |
| `src/trace/v2/retrieval.py` | Tracked Modified | User Code | **Yes** | Hybrid retrieval engine (+456 lines) with multi-stage ranking & activation. |
| `src/trace/v2/models.py` | Tracked Modified | User Code | **Yes** | Pydantic request/response & policy models (+127 lines). |
| `src/trace/v2/api.py` | Tracked Modified | User Code | **Yes** | FastAPI HTTP endpoints for V2. |
| `src/trace/v2/config.py` | Tracked Modified | User Code | **Yes** | Trace settings and environment configuration. |
| `src/trace/v2/migrations.py` | Tracked Modified | User Code | **Yes** | Migration runner and checksum verification logic. |
| `src/trace/v2/model_gateway.py` | Tracked Modified | User Code | **Yes** | Gateway policy and model calling wrapper. |
| `src/trace/v2/preflight.py` | Tracked Modified | User Code | **Yes** | Environment preflight checks. |
| `src/trace/v2/release.py` | Tracked Modified | User Code | **Yes** | Declarative release gate evaluator. |
| `src/trace/v2/repository.py` | Tracked Modified | User Code | **Yes** | Store protocol definitions. |
| `src/trace/v2/benchmark.py` | Tracked Modified | User Code | **Yes** | Benchmark runner and evaluation fixtures. |
| `tests/test_v2_production_controls.py` | Tracked Modified | Test / Fixture | **Yes** | Production PostgreSQL / RLS control tests. |
| `tests/test_v2_release_controls.py` | Tracked Modified | Test / Fixture | **Yes** | Production release gate control tests. |
| `uv.lock` | Tracked Modified | Generated / Lockfile | **Yes** | Python package dependency lockfile (+1355 lines). |
| `pyproject.toml` | Tracked Modified | Configuration | **Yes** | Project build and dependency specifications. |
| `MANIFEST.in` | Tracked Modified | Configuration | **Yes** | Package manifest definitions. |
| `README.md` | Tracked Modified | Documentation | **Yes** | Top-level repository documentation. |
| `docs/architecture.md` | Tracked Modified | Documentation | **Yes** | Architecture specification. |
| `docs/production-runbook.md` | Tracked Modified | Documentation | **Yes** | Production deployment and operations runbook. |
| `docs/schemas.md` | Tracked Modified | Documentation | **Yes** | Database and contract schema documentation. |
| `docs/v2-architecture.md` | Tracked Modified | Documentation | **Yes** | V2 architecture specification. |
| `benchmarks/README.md` | Tracked Modified | Documentation | **Yes** | In-repo benchmark documentation. |
| `benchmarks/load/trace-v2.js` | Tracked Modified | Test / Fixture | **Yes** | K6 load test script. |
| `benchmarks/release-evidence.template.json`| Tracked Modified | Test / Fixture | **Yes** | Release gate evidence template. |

---

## 3. Source Inventory & Exclusions

### Inclusion Rules
- `src/trace/`
- `tests/`
- `migrations/`
- `benchmarks/`
- `docs/`
- `pyproject.toml`

### Exclusion Rules
- `.pytest_cache/`
- `__pycache__/`
- `*.egg-info/`
- `results/`
- `.coverage`
- `.trace/` (local SQLite / object store artifacts)

---

## 4. Integration Boundaries

| Consumer | Producer | Interface / Anchor | Pin Status | Boundary Assessment |
| :--- | :--- | :--- | :---: | :--- |
| `trace-bench` | `trace` | `src/trace/v2` Python imports | Unpinned | `trace-bench` is unversioned and references `trace.v2` directly. Blocked on P-007 / P-008. |
| `trace` | `trace` | `src/trace/v2/cortex.py` | Untracked Snapshot | Proposed Cortex primitives. T1 audits boundary; TR1 implements after P-003. |
| `Reflex` / `Entorhinal` | `trace` | Evidence Bundle (`trace_evidence_bundles`) | Unpinned / Draft | Downstream consumers must use fakes / conformance fixtures until C5 promotion. |

---

## 5. Safe Mutation Base Assessment

- **Clean Mutation Base Available:** **`false`**
- **Commit Reference:** `c855bb06532b3b52b25f0bea969d2677e5049065` (base in Git)
- **Rationale:** The working tree has substantial uncommitted user modifications representing core V2 architectural work. Direct in-tree mutation would risk destroying or corrupting user-owned state.
- **Requirement:** All future mutable packets (TR1, TR2) must operate in isolated worktrees created from an accepted base commit and hold an explicit worktree lease.

---

## 6. Packet Status Matrix

| Packet ID | Status | Reason / Dependency |
| :--- | :---: | :--- |
| **F0c** | Ready | Read-only current-state and repository boundary record. |
| **T1** | Ready | Read-only Cortex Release audit and migration design (this session). |
| **TR1** | Blocked | Blocked on T1 handoff and human acceptance of P-003. |
| **TR2** | Blocked | Blocked on TR1 completion and human acceptance of P-004. |

---

## 7. Claim Boundary

This record is a read-only static observation of repository state, file classifications, and integration boundaries. It does not certify runtime behavior, approve schema migrations, or choose architecture decisions.
