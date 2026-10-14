# V1a Execution Note

## 1. Objective

Independently exercise the frozen S5 negative matrix against the canonical `trace-bench` repository at commit `c0ea9fbf37bc50c88336f198437be031c18d6f64` and prove, for each case, the expected structured failure, `certification_eligible: false`, and absence of a certifying-looking result or partial aggregate.

## 2. Pinned Inputs

- Packet: `v1a-runner-integrity-20260819`
- Verifier: `v1a-runner-integrity-20260819`
- Commit: `c0ea9fbf37bc50c88336f198437be031c18d6f64`
- Parent: `0b01de5e49dcb18d43876b0b6004da58b35b72aa`
- Canonical repository: `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench`
- Verifier worktree: `C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1a-benchmark-20260819`
- Source manifest composite SHA-256: `554555030a8ee6037b41aba3e163b616d1f43ef6b057cb98c7f9242271dad83f`
- Source manifest LF SHA-256: `24e3c942227ab5203dfc324f83ed3eee4c5e4d2af784e23223b2f9f1f131b5cc`
- Dependency lock SHA-256: `fd4bbc4107d965f570493afb2a425b0482363b126532d023744e0a7d46745c50`

## 3. Environment Resolution

The initial blocker `V1A-ENV-001` (`torch==2.13.0` wheel missing from offline cache) was resolved by pre-caching the required wheel into `C:\Users\anshu\AppData\Local\trace-verifier-cache\` and mirroring it to `C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819\uv-cache`. The verifier environment was then constructed with `uv sync --locked --extra dev --no-editable --offline`.

## 4. Test Results

The test suite executed with all 26 tests passing in 202.39 seconds:
- 13 benchmark harness and metric calculation unit tests: PASSED
- 13 negative matrix fail-closed tests: PASSED
- Total: 26 passed, 0 failed, 0 skipped.
