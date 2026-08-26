# S3 TR2 command receipt

All commands ran in the fresh TR2 worktree unless noted. No network, provider,
fallback, mock, or synthetic certification run was used.

| Check | Exact command/result |
| --- | --- |
| Base regression | `$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\anshu\\OneDrive\\Documents\\Code\\Utilities\\trace\\.venv\\Scripts\\python.exe' -m unittest discover -s tests -p 'test_v2*.py' -v` at clean 454: 41 passed. |
| Focused temporal matrix | `$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\anshu\\OneDrive\\Documents\\Code\\Utilities\\trace\\.venv\\Scripts\\python.exe' -m unittest tests.test_v2_temporal_revocation -v`: 6 passed. |
| Full V2 regression | Same absolute-path discover command after TR2: 47 passed in 1.791s. |
| Syntax | AST parse of 36 `src` files plus 8 V2 test files: `ast-ok:44`. |
| PostgreSQL adapter import | `from trace.v2.production import PostgresEventStore`: import passed; no connection or migration apply. |
| Diff hygiene | `git diff --check`: passed. |
| Pytest capability | `python -m pytest -q`: blocked, `No module named pytest`; unittest was used. |
| Docker capability | `docker info --format '{{json .ServerVersion}}'`: blocked, permission denied on `dockerDesktopLinuxEngine` npipe. |

The live SQLite evidence sample is in `evidence/sqlite-evidence-sample.json`.
