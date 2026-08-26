# B1.1 Verification Record

## Final implementation identity

```yaml
repository_root: "C:\\Users\\anshu\\OneDrive\\Documents\\Code\\Utilities\\trace-bench"
implementation_worktree: "C:\\Users\\anshu\\AppData\\Local\\trace-worktrees\\trace-bench-b11-20260819"
branch: "feat/b1-identity-refresh-20260819"
commit: "dcd32396f6430e6865176f053a3ce57112db6df3"
parent_b1_commit: "0b01de5e49dcb18d43876b0b6004da58b35b72aa"
worktree_status: "clean"
clean_clone: "C:\\Users\\anshu\\AppData\\Local\\Temp\\trace-bench-b11-20260820\\clone-final"
clean_clone_status: "clean"
core_autocrlf: false
```

## Source and dependency identity

| Artifact | SHA-256 / identity | Size |
| --- | --- | ---: |
| `SOURCE_MANIFEST.json` in final LF clone | `b0d58be58ed76fd67942cc6ab5b4346057a5ec27986199b6f91757a53591031b` | recorded in Git |
| `SOURCE_MANIFEST.json` composite | `3c3b4a6fd30127654e387401b9f64191a700e21fbc78b732fe8b3fb99c353c55` | 44 entries |
| `uv.lock` | `fd4bbc4107d965f570493afb2a425b0482363b126532d023744e0a7d46745c50` | 265,239 bytes |
| `pyproject.toml` LF content | `6e04c7b19ec204ae15ebbfbd5421062985e5234e8564e6d61207df632e371437` | 1,307 bytes |

The manifest excludes itself from the tracked-file set. The final clone has
45 Git-tracked files total and 44 manifest entries; the coverage comparison
has no missing or extra source entry. The lock declares format version 1,
revision 3, `requires-python >=3.11`, and resolves 72 packages. Package
metadata is `trace-bench==0.1.0`, eight runtime dependency specifications,
three `dev` optional dependencies, and one `sota` optional dependency.

The declared verification runtime is uv `0.12.2
(46ead6098 2026-08-05 x86_64-pc-windows-msvc)` with CPython `3.12.0` at
`C:\\Program Files\\Python312\\python.exe` on Windows. The clean-clone
environment was built with `--locked --extra dev --no-editable` and imported
`trace_bench` from the external wheel environment, not from an editable
install.

## Clean-clone raw results

```text
head=dcd32396f6430e6865176f053a3ce57112db6df3
parent=0b01de5e49dcb18d43876b0b6004da58b35b72aa
status=
tracked=45
autocrlf=false
json=valid
entries=44 declared=44
missing=
lock_hash=fd4bbc4107d965f570493afb2a425b0482363b126532d023744e0a7d46745c50
lock_size=265239
composite=3c3b4a6fd30127654e387401b9f64191a700e21fbc78b732fe8b3fb99c353c55 declared=3c3b4a6fd30127654e387401b9f64191a700e21fbc78b732fe8b3fb99c353c55
Using CPython 3.12.0 interpreter at: C:\Program Files\Python312\python.exe
Resolved 72 packages in 1ms
```

## B1 test result

Exact final command:

```powershell
$env:UV_CACHE_DIR='C:\Users\anshu\AppData\Local\Temp\trace-bench-b11-20260820\cache'
$env:UV_PROJECT_ENVIRONMENT='C:\Users\anshu\AppData\Local\Temp\trace-bench-b11-20260820\venv-final'
uv run --locked --no-sync python -m pytest -q -o pythonpath= --basetemp 'C:\Users\anshu\AppData\Local\Temp\trace-bench-b11-20260820\pytest-basetemp-final'
```

Raw result:

```text
..........................                                               [100%]
26 passed in 75.01s (0:01:15)
```

The test-managed external basetemp completed without a pytest cleanup error;
the external scratch tree is retained for audit and is outside all source and
data roots.

## Negative/environment evidence

- A sandboxed locked sync failed only at the network fetch for
  `safetensors==0.8.0` with connection refused. The same command under
  approved network escalation downloaded only lock-pinned dependencies and
  succeeded.
- The first `--dev` sync did not install pytest because this project declares
  `dev` as an optional extra. The corrected `--extra dev` command installed
  the lock-pinned `pytest==9.1.1` and `pytest-asyncio==1.4.0`; no source change
  was needed.
- No dataset/provider/certification command was run. No Trace or Trace-Lite
  path was touched.
