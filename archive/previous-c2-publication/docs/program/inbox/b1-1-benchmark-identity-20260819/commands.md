# B1.1 Commands and Preflight Results

All commands below were read-only preflight commands. No dataset, provider,
or certification command was run.

| Purpose | Command/result |
| --- | --- |
| Current time | `Get-Date`; local `2026-08-20T07:49:30.6469566+05:30`; UTC `2026-08-20T02:19:30.6469566Z` |
| Canonical identity | `git -C C:\\Users\\anshu\\OneDrive\\Documents\\Code\\Utilities\\trace-bench branch --show-current`; `main`; `git ... rev-parse HEAD`; `0b01de5e49dcb18d43876b0b6004da58b35b72aa` |
| Canonical status | `git ... status --porcelain=v2 --untracked-files=all`; `? uv.lock` |
| Lease status | Lease `lease-s1-b1-1-benchmark-identity-20260819`, expiry `2026-08-20T12:40:55.1070524Z`; valid at capture time |
| Assigned worktree | `Test-Path C:\\Users\\anshu\\AppData\\Local\\trace-worktrees\\trace-bench-b11-20260819`; `False` |
| Toolchain | Git `2.52.0.windows.1`; Python `3.12.0`; uv `0.12.2`; Windows |
| Lock hash | `Get-FileHash -Algorithm SHA256 uv.lock`; `fd4bbc4107d965f570493afb2a425b0482363b126532d023744e0a7d46745c50` |
| Existing source manifest | SHA-256 `7603803ffc6537b84e67daa1b8d526a04cd173dc6c081089d947b0a3f93bc075`; declares 42 files |
| Inventory comparison | `git ls-files` reports 44 files; `tests/test_fail_closed_negative_matrix.py` is absent from manifest coverage; `SOURCE_MANIFEST.json` is self-excluded |

## Scope note

The only implementation action authorized after this preflight is to
materialize the exact leased worktree and modify its identity paths. The
canonical checkout, Trace, Trace-Lite, data root, and global control-plane
records remain protected.

## Implementation and verification commands

| Stage | Exact command | Result |
| --- | --- | --- |
| Lease worktree | `git worktree add -b feat/b1-identity-refresh-20260819 C:\\Users\\anshu\\AppData\\Local\\trace-worktrees\\trace-bench-b11-20260819 0b01de5e49dcb18d43876b0b6004da58b35b72aa` | Created from the exact B1 base; no canonical checkout mutation |
| Lock validation | `uv lock --check --python "C:\\Program Files\\Python312\\python.exe"` | `Using CPython 3.12.0`; `Resolved 72 packages` |
| Source manifest validation | JSON parse plus deterministic sorted `path|sha256|size_bytes` SHA-256 recomputation | Valid; 44 entries; composite `3c3b4a6fd30127654e387401b9f64191a700e21fbc78b732fe8b3fb99c353c55` |
| Identity commit | `git add -- uv.lock SOURCE_MANIFEST.json; git commit --amend --no-edit` | Final `dcd32396f6430e6865176f053a3ce57112db6df3`; parent `0b01de5e49dcb18d43876b0b6004da58b35b72aa` |
| Clean clone | `git clone --no-local --branch feat/b1-identity-refresh-20260819 C:\\Users\\anshu\\AppData\\Local\\trace-worktrees\\trace-bench-b11-20260819 C:\\Users\\anshu\\AppData\\Local\\Temp\\trace-bench-b11-20260820\\clone-final`; set local `core.autocrlf=false`; `git checkout-index -a -f`; `git add --renormalize .` | Final clone clean; 45 Git files including the self-excluded manifest |
| Locked environment | `uv sync --locked --extra dev --no-editable --python "C:\\Program Files\\Python312\\python.exe" --cache-dir C:\\Users\\anshu\\AppData\\Local\\Temp\\trace-bench-b11-20260820\\cache` | Success; 51 pinned packages installed into external `venv-final`; project built non-editably |
| Installed import check | `uv run --locked --no-sync python -c "import importlib.metadata as m, sys, trace_bench; ..."` | `trace_bench` resolved from `venv-final\\Lib\\site-packages`; Python `3.12.0`; distribution `0.1.0` |
| B1 suite | `uv run --locked --no-sync python -m pytest -q -o pythonpath= --basetemp C:\\Users\\anshu\\AppData\\Local\\Temp\\trace-bench-b11-20260820\\pytest-basetemp-final` | `26 passed in 75.01s (0:01:15)`; 0 failed, 0 skipped |
| Final lock check | `uv lock --check --python "C:\\Program Files\\Python312\\python.exe"` | `Using CPython 3.12.0`; `Resolved 72 packages in 1ms` |

## Environment limitations and non-substitutions

- The first sandboxed dependency sync could not fetch `safetensors==0.8.0`
  because the network tunnel refused the connection. The identical strict-TLS
  dependency-only command was retried with approved network escalation and
  passed; no substitute package or fallback was used.
- The default uv cache was ACL-blocked (`Access is denied`), so all dependency
  work used the unique external cache recorded above. No cache was present in
  that root before the first sync.
- No dataset download, provider call, certification run, benchmark result, or
  Trace/Trace-Lite modification occurred.
