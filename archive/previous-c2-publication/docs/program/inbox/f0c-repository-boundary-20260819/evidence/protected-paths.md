# Protected Paths and Dirty-State Policy

> **Status:** Binding policy for all Foundation Program sessions.
> **Date:** 2026-08-19.

## 1. Absolute Prohibition on Destructive Operations

The following operations are strictly forbidden across all repositories:
- `git reset` (hard, soft, or mixed)
- `git checkout -- <file>` or `git restore`
- `git clean` (with any flags)
- `git stash` (pop, drop, or apply)
- Direct deletion, overwriting, formatting, or relocation of user-owned files
- Direct in-place mutation of the active working tree for mutable packets

## 2. Trace Protected Path Inventory

The Trace repository (`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace`) contains active user-owned V2 development work that is not yet committed.

### Tracked Modified Files (26 files — Protected)
- `MANIFEST.in`
- `README.md`
- `benchmarks/README.md`
- `benchmarks/load/trace-v2.js`
- `benchmarks/release-evidence.template.json`
- `docs/architecture.md`
- `docs/production-runbook.md`
- `docs/schemas.md`
- `docs/v2-architecture.md`
- `pyproject.toml`
- `src/trace/v2/api.py`
- `src/trace/v2/benchmark.py`
- `src/trace/v2/config.py`
- `src/trace/v2/migrations.py`
- `src/trace/v2/model_gateway.py`
- `src/trace/v2/models.py`
- `src/trace/v2/preflight.py`
- `src/trace/v2/production.py`
- `src/trace/v2/release.py`
- `src/trace/v2/repository.py`
- `src/trace/v2/retrieval.py`
- `src/trace/v2/service.py`
- `src/trace/v2/store.py`
- `tests/test_v2_production_controls.py`
- `tests/test_v2_release_controls.py`
- `uv.lock`

### Untracked Surfaces (Protected)
- `docs/program/` (canonical program control plane)
- `migrations/004_cortex_projection_control_plane.sql` (proposed V2 migration)
- `src/trace/v2/__main__.py` (V2 CLI)
- `src/trace/v2/cortex.py` (V2 cortex logic)
- `tests/test_v2_cortex_controls.py` (V2 test suite)

## 3. Trace-Lite Protected Path Inventory

The Trace-Lite repository (`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite`) has a clean tracked status but contains 11 untracked documentation and protocol files:

### Untracked Surfaces (Protected)
- `benchmarks/protocols/README.md`
- `benchmarks/protocols/templates/GATE_100K_REPORT_TEMPLATE.md`
- `benchmarks/protocols/templates/QUERY_CLASS_PROTOCOL_TEMPLATE.md`
- `benchmarks/protocols/templates/RELEASE_MANIFEST_TEMPLATE.yaml`
- `benchmarks/registry/README.md`
- `benchmarks/registry/templates/DATASET_MANIFEST_TEMPLATE.json`
- `benchmarks/registry/templates/DATASET_RECORD_TEMPLATE.md`
- `docs/program/AGENT_CONTEXT_MAP.md`
- `docs/program/BETA_WORKSTREAM.md`
- `docs/program/PROGRAM_REFERENCE.md`
- `docs/program/README.md`

## 4. trace-bench Protected Path Inventory

The entire `trace-bench` tree (`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench`) is an unversioned working source tree consisting of 41 files. All source, test, fixture, and configuration files are protected. Cache (`.pytest_cache/`, `__pycache__/`) and build artifacts (`egg-info/`) are excluded from source identity but must not be modified during read-only sessions.
