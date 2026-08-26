# Commands Log — T1 Trace Cortex Release Audit

> **Task ID:** T1  
> **Session:** Trace Foundation  
> **Environment:** Windows PowerShell / Python 3.12  
> **Execution Mode:** Strictly Read-Only (No code modification, no database mutation, no benchmark execution)

---

## 1. Source Identity & Git State Commands

```powershell
# Check current Git branch and working tree status
git status
# Exit code: 0
# Output: On branch main, ahead of 'origin/main' by 3 commits.
# 26 tracked modified files, 5 untracked surfaces.

# Check recent commit history
git log -n 5 --oneline
# Exit code: 0
# Output: c855bb0 refactor: update repository with complete trace codebase

# Resolve exact base commit hash
git rev-parse HEAD
# Exit code: 0
# Output: c855bb06532b3b52b25f0bea969d2677e5049065

# Detailed porcelain file listing
git status --porcelain
# Exit code: 0
# Output: 26 modified tracked files, 5 untracked files/directories
```

---

## 2. Integrity & Fingerprint Calculations

```powershell
# Calculate SHA-256 of tracked modified diff
python -c "import subprocess, hashlib; diff = subprocess.check_output(['git', 'diff']); print('diff sha256:', hashlib.sha256(diff).hexdigest())"
# Exit code: 0
# Output: diff sha256: 00d6c966b9a8cdfe6ca0c0ec3456766017450660b6eb018e3890370df18fb180

# Calculate SHA-256 of untracked path list
python -c "import subprocess, hashlib; out = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard']); print('untracked sha256:', hashlib.sha256(out).hexdigest())"
# Exit code: 0
# Output: untracked sha256: 77771e9e0e067198711e335319976ef80d96e42500b11ab27809e827b55d7ab8
```

---

## 3. Static Code & Schema Audit Actions

The following source surfaces and migrations were inspected read-only via AST/text view tools:
- `migrations/001_trace_production.sql`: Canonical event spine, nodes, edges, anchors, bundles, RLS policies.
- `migrations/002_runtime_hardening.sql`: Forward-only hardening, RLS enforcement, outbox indexing.
- `migrations/003_auth_and_worker_scope.sql`: Auth lookup policies, worker query scoping.
- `migrations/004_cortex_projection_control_plane.sql`: Proposed Cortex control plane (`projection_runs`, `projection_objects`, `projection_memberships`, `affinity_edges`, `activation_priors`).
- `src/trace/v2/cortex.py`: Localized activation engine, energy conservation, degree capping.
- `src/trace/v2/store.py`: Materialized SQLite projection store, hierarchy delta, affinity upserts, priors.
- `src/trace/v2/production.py`: PostgreSQL production store, RLS tenant scoping, Cortex methods.
- `src/trace/v2/retrieval.py`: Multi-stage hybrid retrieval engine, hierarchy frontier, activation ladder.
- `src/trace/v2/service.py`: Application orchestration, query pipeline, evidence bundle generation, job dispatch.
- `src/trace/v2/projections.py`: `RevisionedProjectionController` lifecycle controls.
- `src/trace/v2/models.py`: Contract models (`QueryRequest`, `CognitivePolicy`, `ActivationWeights`).
- `src/trace/v2/release.py`: Release evidence gate evaluation.
- `tests/test_v2_cortex_controls.py`: Cortex control suite.
- `tests/test_v2_release_controls.py`: Release gate test suite.
- `tests/test_v2_production_controls.py`: Production control test suite.
