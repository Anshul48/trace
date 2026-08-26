# S5 Initial V1b Commands

Commands are appended as the verifier run proceeds. The preflight identities
and input hashes are recorded in `repository-state.json` and
`input-manifest.json`.

## Preflight

- `Get-Date` converted to UTC: `2026-08-20T02:19:18.9324392Z`.
- `git status --short --branch` and `git rev-parse HEAD` on both implementation
  worktrees: clean at the leased commits.
- `git worktree list --porcelain` on both component repositories: implementation
  worktrees are distinct from protected user checkouts.
- Lease JSON parsed from the two R1 lease files: both `assigned`, unexpired, and
  bound to the expected verifier IDs.
- `python --version`: `Python 3.12.0`.
- `uv --version`: `uv 0.12.2 (46ead6098 2026-08-05 x86_64-pc-windows-msvc)`.

No lifecycle test or implementation mutation has been run at the time of this
initial record. The execution records below were appended after preflight.

## Environment gate

- Clean TL attempt from the leased implementation environment:
  `uv run --offline --locked python -c "import pytest, lancedb; print('ready')"`
  could not resolve the locked uncached `torch==2.13.0` wheel requested by
  `sentence-transformers==5.7.0`; network remained disabled. No fallback
  dependency installation was attempted.
- C1 fallback execution used the host `C:\Program Files\Python312\python.exe`
  with only the clean verifier worktree on `PYTHONPATH`. The TL harness used
  `MockEmbedder`, `MockLLMAdapter`, and `MockVectorStore`; the Trace harness
  used local SQLite and deterministic in-process adapters.

## Independent execution

- TL harness, final tightened rerun:

  ```powershell
  $env:PYTHONPATH='C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-tl-lifecycle-20260819\src'
  $env:S5_SCRATCH='C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1b-tl-lifecycle-20260819'
  $env:S5_RECEIPT='C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\inbox\v1b-lifecycle-temporal-verifier-20260819\evidence\reports\tl-receipt.json'
  python 'C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\inbox\v1b-lifecycle-temporal-verifier-20260819\evidence\reports\tl_independent_lifecycle.py'
  ```

  Result: `passed=11 failed=0 total=11`; receipt SHA-256
  `c84e6537bb61d400d92e0ad34c68a6aac4595cd1a50ebf2a80b411d766526d57`.

- Trace harness:

  ```powershell
  $env:PYTHONPATH='C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-trace-release-20260819\src'
  $env:S5_SCRATCH='C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1b-trace-release-20260819'
  $env:S5_RECEIPT='C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\inbox\v1b-lifecycle-temporal-verifier-20260819\evidence\reports\trace-receipt.json'
  python 'C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\inbox\v1b-lifecycle-temporal-verifier-20260819\evidence\reports\trace_independent_release.py'
  ```

  Result: `passed=6 failed=0 total=6`; receipt SHA-256
  `ce0fd12dc611ec5c3af52aeefa1983a13ecbe370f456689cdfb115bab8d2b432`.

## Existing Trace suites

- Lifecycle isolation: `python -m unittest discover -s tests -p
  'test_v2_lifecycle_isolation.py' -v` from the Trace verifier worktree;
  result `Ran 5 tests ... OK`.
- API lifecycle: `python tests\\test_v2_api_cognitive.py` from the Trace
  verifier worktree; result `Ran 2 tests ... OK`.

## Cleanup and final state

- Removed the exact TL and Trace leased scratch roots after their receipts were
  written; the final TL rerun scratch root was removed again after hashing.
- Retained both verifier worktrees for coordinator review. No product source,
  implementation test, migration, user checkout, or implementation-owned
  database/cache/result was modified.
- Packet-local files were added after the pre-run control-plane snapshot;
  `CONTROL_PLANE_LOCK.json` was not rewritten because S0 remains the sole
  coordinator writer.
