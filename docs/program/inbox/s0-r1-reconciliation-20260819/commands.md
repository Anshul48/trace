# R1 Command Log

All commands below were read-only observations unless explicitly marked as a
packet-document write. No product, benchmark, provider, or raw-data command
was run.

| Check | Exact command / action | Result | Durable evidence |
| --- | --- | --- | --- |
| Governing-doc read | `Get-Content -Raw` for implementation-wave README, global context, session protocol, gate matrix, handoff template, subagent rules, S0 brief, R1 prompt, decision log, risk register, status, registry | pass; live files read | `input-manifest.json` hashes |
| Packet inventory | `rg --files docs/program`; `Get-ChildItem docs/program/inbox -Directory` | pass; 213 live regular files before R1 packet files; all existing packet directories listed | `evidence/downstream-packet-classification.md` |
| Control-plane snapshot | Enumerated regular files under `docs/program` excluding `CONTROL_PLANE_LOCK.json`, hashed each file, joined sorted `relative-path:sha256` lines with LF, SHA-256 hashed joined bytes | pass; 213 files, tree `1213c046efda3b66b67939cb6a88bea2d80bb41618f2f731a40dd00daf8a72d7` | `input-manifest.json` |
| Trace identity | `git rev-parse --show-toplevel`; `git branch --show-current`; `git rev-parse HEAD`; `git status --porcelain=v1`; `git diff --stat`; `git diff --binary --no-ext-diff | git hash-object --stdin`; `git ls-files --others --exclude-standard | git hash-object --stdin` | pass; main `c855bb0...`; 26 modified tracked files; 5 untracked surfaces; protected dirty snapshot | `repository-state.json` |
| Trace-Lite identity | Same Git identity/status commands in user checkout and `git worktree list --porcelain` | pass; user main `fe66a9e...` with protected untracked paths; clean L1 worktree `7ff40dc...` | `repository-state.json` |
| Trace TR1 identity | Same Git identity/status commands in `C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr1` | pass; clean `454c5ae...` worktree | `repository-state.json` |
| trace-bench identity | Same Git identity/status commands; `git describe --tags --always --dirty`; `git cat-file -t 0b01de5c...`; `Get-FileHash SOURCE_MANIFEST.json`; `Get-FileHash uv.lock` | pass for live identity; claimed B1 full hash does not exist; one untracked `uv.lock` | `source-identity-manifest.json` |
| D2a external identity | Enumerated seven top-level dataset directories and file counts/bytes; hashed all 35 governance metadata files; compared each metadata hash to `portfolio-staging-manifest.json` | pass; all 35 metadata hashes match; 7 directories, 85 files, 1,523,873,466 bytes | `source-identity-manifest.json` and `repository-state.json` |
| Worktree collision check | `Test-Path` on all fresh S1/S5/D2b worktree and scratch paths; `git worktree list --porcelain` in trace-bench | pass; fresh paths absent; existing implementation worktrees not reused | `leases/*.json` |
| Lease freshness | Compared current UTC `2026-08-19T12:40:55.1070524Z` with D0 expiry `2026-08-20T07:00:00Z` | pass; D0 leases expired at refresh time | `repository-state.json` |
| Tool/runtime preflight | `$PSVersionTable.PSVersion`; `[Environment]::OSVersion`; `git --version`; `uv --version`; `.venv\\Scripts\\python.exe --version`; `System.IO.DriveInfo` for `C:\` | pass; PowerShell 5.1, Git 2.52.0, uv 0.12.2, Python 3.12.11, 367.68 GB available | `repository-state.json` |
| Runtime/product tests | No test command run by S0 | not attempted; no test count or cleanup claim | `repository-state.json` |
| External mutation | No network, provider, data, migration, reset, checkout, clean, stash, or source write | pass by scope; protected state unchanged before R1 global-record writes | `repository-state.json` |
| Final JSON parse | `Get-ChildItem docs/program/inbox/s0-r1-reconciliation-20260819 -Filter *.json -Recurse; ConvertFrom-Json`; plus `CONTROL_PLANE_LOCK.json` | pass; 12 JSON files parsed | `verification.md` |
| Final control-plane hash | Recomputed sorted LF-joined `relative-path:sha256` tree excluding `CONTROL_PLANE_LOCK.json` | pass; 232 files; `67413aa6a8865c2c6d792b699dbdd8ecf1891529a373a5016c9825cf72e784ff` matches lock | `CONTROL_PLANE_LOCK.json` |
| Final artifact hash check | Read `evidence/checksums.json`; `Get-FileHash` for each listed artifact | pass; 21 artifacts, 0 mismatches | `evidence/checksums.json` |
| Final D2a hash check | Read D2a portfolio manifest; compare live `source-record.json`, `checksums.json`, `layout-observation.json`, license, and acquisition-log hashes for each dataset | pass; 7 datasets, 35 metadata files, 0 mismatches | `evidence/source-identity-manifest.json` |
| Final protected-state check | Git status/head for Trace-Lite user checkout, L1, TR1, trace-bench; filter Trace untracked list outside `docs/program` | pass; user/implementation worktrees unchanged; only pre-existing non-control Trace untracked paths remain; trace-bench only `uv.lock` | `repository-state.json` |
| Final lease collision check | `Test-Path` over all nine reserved S1/S5/D2b worktree/scratch paths | pass; 0 paths already existed | `leases/*.json` |

## Write record

The R1 packet files were created with `apply_patch`. The only subsequent
mutable writes authorized by this packet are the R1 packet-local records and
the four current control-plane records named in `packet.md`. No source
checkout, raw data, provider configuration, database, or test result path is
within that write scope.

## Test and cleanup accounting

- Tests run: `0`.
- Test duration: not applicable.
- Skipped tests: not applicable.
- External provider/data calls: `0`.
- Cleanup: no test or data cleanup performed; no temporary run state created.
