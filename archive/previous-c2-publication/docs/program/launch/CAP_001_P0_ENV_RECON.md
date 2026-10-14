# CAP-001 P0-ENV Recon (READ-ONLY, 2026-09-03)

Root cause (all 5 receipts): bare `pytest` is not on PATH in a clean PowerShell —
`pytest : The term 'pytest' is not recognized...` (VERIFICATION_ERROR, 0 collected).
Working pattern (eval02 receipt): `$env:PYTHONPATH='src;.'; .\.venv\Scripts\pytest.exe ...` → 12 passed.

## 1. Per-worktree pytest status

| Worktree | .venv layout (seen from Linux) | pytest entry point | Python | Clean-shell `pytest` |
|---|---|---|---|---|
| trace-ret02 | STUB: only `lib64->lib` + `pyvenv.cfg`, no `bin/`, no `Scripts/`, no interpreter | NONE | 3.12.3 (cfg `home=/usr/bin`) | FAIL (receipt exit 1) |
| trace-crx02 | Linux venv: `.venv/bin/pytest` (9.1.1), no `Scripts/` | `.venv/bin/pytest` only; NO `Scripts\pytest.exe` | 3.12.3 | FAIL (receipt exit 1) |
| trace-job01 | Linux venv: `.venv/bin/pytest` (9.1.1), no `Scripts/` | `.venv/bin/pytest` only; NO `Scripts\pytest.exe` | 3.12.3 | FAIL (receipt exit 1) |
| trace-job02 | NO `.venv` at all (worktree clean) | NONE (`C:/Program Files/Python312/python.exe`, no pytest) | 3.12 | FAIL (receipt exit 1) |
| trace-crx03 | NO `.venv` at all (worktree clean) | NONE (same system python, no pytest) | 3.12 | FAIL (receipt exit 1) |
| trace-eval02 (reference) | Windows venv: `.venv/Scripts/pytest.exe` + `python.exe` | `.\.venv\Scripts\pytest.exe` | 3.12.11 (uv 0.12.5) | WORKS via venv path |

Notes: ret02 non-isolated `uv run` failed (`Access is denied` removing `.venv\lib64`);
isolated `uv run --isolated --locked --extra test pytest ...` passed 39/39 (control only).
Linux side: system python3 = 3.12.3 with NO pytest module; `uv` 0.12.7 available.
`test` extra = pytest>=8.0, pytest-asyncio, fastapi, httpx, uvicorn, python-multipart,
litellm, jsonschema, psutil (`requires-python = >=3.12`). No neural extra declared.

## 2. trace-ret02 neural-dep table

Receipt `dense_backend_observation`: `provider_id` =
`local-dense:sentence-transformers/all-MiniLM-L6-v2:deterministic-fallback:cpu`,
`active_backend=deterministic-fallback`, `is_neural=false` → `NO_NEURAL_QUALIFICATION`.

| Package | System python3 (3.12.3) | crx02/job01 venv python | ret02 venv python |
|---|---|---|---|
| numpy / torch / onnxruntime / sentence_transformers | NOT importable (all 4) | NOT importable (all 4; pytest 9.1.1 only) | NO INTERPRETER (stub venv) |

## 3. Env-fix commands (Windows PowerShell, write-capable session — DO NOT run here)

```powershell
# trace-ret02: remove broken stub, rebuild, add neural deps (no pyproject extra covers them)
cd C:\Users\anshu\AppData\Local\trace-worktrees\trace-ret02
Remove-Item -Recurse -Force .venv
uv sync --extra test
uv pip install --python .\.venv\Scripts\python.exe numpy torch onnxruntime sentence_transformers
$env:PYTHONPATH='src'; .\.venv\Scripts\pytest.exe tests/v2/test_hybrid_retrieval.py tests/v2/test_retrieval_embedding.py -v

# trace-crx02 (Linux-layout venv, no Scripts\: rebuild as Windows venv)
cd C:\Users\anshu\AppData\Local\trace-worktrees\trace-crx02
Remove-Item -Recurse -Force .venv; uv venv; uv sync --extra test
$env:PYTHONPATH='src'; .\.venv\Scripts\pytest.exe tests/v2/test_cortex_consolidator.py -v

# trace-job01 (same layout issue as crx02)
cd C:\Users\anshu\AppData\Local\trace-worktrees\trace-job01
Remove-Item -Recurse -Force .venv; uv venv; uv sync --extra test
$env:PYTHONPATH='src'; .\.venv\Scripts\pytest.exe tests/v2/test_job_pipeline.py -v

# trace-job02 (no venv: create)
cd C:\Users\anshu\AppData\Local\trace-worktrees\trace-job02
uv venv; uv sync --extra test
$env:PYTHONPATH='src'; .\.venv\Scripts\pytest.exe tests/v2/test_job_recovery.py -v

# trace-crx03 (no venv: create)
cd C:\Users\anshu\AppData\Local\trace-worktrees\trace-crx03
uv venv; uv sync --extra test
$env:PYTHONPATH='src'; .\.venv\Scripts\pytest.exe tests/v2/test_cortex_activation.py -v
```

Acceptance check (each worktree):
`$env:PYTHONPATH='src'; .\.venv\Scripts\pytest.exe --version` exits 0;
in trace-ret02 additionally `.\.venv\Scripts\python.exe -c "import torch, sentence_transformers"` exits 0.
No installs were executed in this recon session.
