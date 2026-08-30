# F0c Execution Commands Log

> **Role:** Coordinator & Trace-Lite Foundation Engineer (read-only boundary capture)
> **Date:** 2026-08-19

## 1. Trace Repository Inspection

```powershell
# 1. Inspect git status and latest commit
git status --short; git log -1 --format="%H %B"
# Cwd: C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace
# Result: Commit c855bb06532b3b52b25f0bea969d2677e5049065 on main.
# 26 tracked modified files, 5 untracked surfaces (docs/program/, migrations/004..., src/trace/v2/__main__.py, src/trace/v2/cortex.py, tests/test_v2_cortex_controls.py).

# 2. Branch, remote, and diff statistics
git branch --show-current; git remote -v; git diff --stat
# Cwd: C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace
# Result: main branch; origin https://github.com/Anshul48/trace.git
# 26 files changed, 6291 insertions(+), 187 deletions(-)

# 3. Tracked diff and untracked path list SHA256 digests
# Cwd: C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace
# TRACE_DIFF_SHA: dbc213b9cd609f35562891f789dbc1daaef762ddf2f81030847529be756089ae
# TRACE_UNTRACKED_SHA: 3b406fa08deb2847770656ffdf2e3908a079547250ac6af90b21d98cd709afa5
```

## 2. Trace-Lite Repository Inspection (Trace-Lite Foundation Session)

```powershell
# 1. Inspect full git status with untracked all
git -C "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite" status -uall
# Result: On branch main, up to date with 'origin/main'.
# 0 tracked modifications. 11 untracked files in benchmarks/protocols/, benchmarks/registry/, docs/program/.

# 2. Commit log and rev-parse
git -C "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite" log -n 5 --oneline
git -C "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite" rev-parse HEAD
# Result: fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1
# Subject: refactor: clean up architecture docs, lattice fusion, and forest pending queues

# 3. Remote configuration
git -C "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite" remote -v
# Result: origin git@github.com:Anshul48/trace-lite.git (fetch & push)

# 4. Untracked files list SHA-256 calculation
$files = (git -C "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite" status -uall --porcelain | ForEach-Object { $_.Substring(3) }) -join "`n"
[BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($files))).Replace("-","").ToLower()
# Result: 793075dc20d2660da284b606fa8acffb50e59acb921e2f28652dc13b302eec04
```

## 3. trace-bench Directory Inspection

```powershell
# 1. Top-level directory listing
Get-ChildItem -Path "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench" -Force
# Result: .pytest_cache, benchmarks, src, tests, pyproject.toml, README.md

# 2. Check for Git repository
Test-Path "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench\.git"
# Result: False (unversioned source tree)

# 3. Recursive file inventory and manifest calculation (excluding caches and egg-info)
# Result: 41 source/fixture/config files.
# TRACE_BENCH_MANIFEST_HASH: 739d7f42fb40c9234b716f5a30aa9e0acd224c4e486e24f95e4afa8f1ca36f1e
```

## 4. Program Control Plane Validation

```powershell
# Verified against CONTROL_PLANE_LOCK.json
# Snapshot ID: foundation-control-plane-20260819-initial
# Tree SHA256: c65926092d2dc7b4472dd1ac4da2af853b2fd8a24ecd93c9b748bd37c16df2f5
# Total files: 103
```
