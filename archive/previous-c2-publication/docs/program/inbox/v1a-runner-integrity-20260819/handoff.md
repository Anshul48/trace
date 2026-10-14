# V1a Independent Runner Integrity Handoff

## 1. Identity

```yaml
packet_id: "v1a-runner-integrity-20260819"
session: "S5"
role: "Independent Verifier"
status: "completed"
authority_level: "C1"
started_utc: "2026-08-25T13:10:00.000000Z"
completed_utc: "2026-08-25T13:26:00.000000Z"
worktree_path: "C:\\Users\\anshu\\AppData\\Local\\trace-verifier-worktrees\\v1a-benchmark-20260819"
worktree_lease_id: "lease-s5-v1a-benchmark-20260819"
base_commit: "c0ea9fbf37bc50c88336f198437be031c18d6f64"
parent_commit: "0b01de5e49dcb18d43876b0b6004da58b35b72aa"
verifier_id: "v1a-runner-integrity-20260819"
```

## 2. Summary

The canonical `trace-bench` repository was reconciled on `main` at commit `c0ea9fbf37bc50c88336f198437be031c18d6f64`, tracking `uv.lock` and `SCALE_EVIDENCE_PLAN.md` with a fully refreshed `SOURCE_MANIFEST.json` covering all 45 non-manifest tracked files (composite SHA-256 `554555030a8ee6037b41aba3e163b616d1f43ef6b057cb98c7f9242271dad83f`).

The previously missing offline dependency `torch==2.13.0` was provisioned into the verifier cache root `C:\Users\anshu\AppData\Local\trace-verifier-cache\` and mirrored to `C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819\uv-cache`. The locked environment was built strictly offline without network access, and the project was installed non-editably into the verifier-owned virtual environment.

The complete frozen V1a negative fail-closed runner matrix and unit test suite executed cleanly: **26/26 tests passed in 202.39s (0 failures, 0 skips)**. All 13 negative matrix fail-closed paths were verified to block or fail with expected error codes, structured error receipts, and `certification_eligible: false`.

## 3. Inputs and Provenance

| Input | Absolute Path | Version / Hash | Purpose | Freshness Check |
| --- | --- | --- | --- | --- |
| Canonical repository | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench` | `c0ea9fbf37bc50c88336f198437be031c18d6f64` | Canonical benchmark source | Reconciled & clean on `main` |
| Verifier worktree | `C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1a-benchmark-20260819` | `c0ea9fbf37bc50c88336f198437be031c18d6f64` | Independent checkout | Clean, `core.autocrlf=false` |
| Source manifest | `SOURCE_MANIFEST.json` in verifier worktree | LF SHA-256 `24e3c942227ab5203dfc324f83ed3eee4c5e4d2af784e23223b2f9f1f131b5cc` | Source identity | 45 entries; composite `554555030a8ee6037b41aba3e163b616d1f43ef6b057cb98c7f9242271dad83f` |
| Dependency lock | `uv.lock` in verifier worktree | SHA-256 `fd4bbc4107d965f570493afb2a425b0482363b126532d023744e0a7d46745c50` | Locked dependencies | 72 packages resolved |
| Verifier cache | `C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819\uv-cache` | Offline wheel cache | Offline dependencies | All 51 packages including `torch==2.13.0` |

## 4. Scope and Authority

### Allowed paths
- Isolated verifier worktree at `C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1a-benchmark-20260819`.
- External scratch / venv at `C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819`.
- Canonical `trace-bench` repository on `main` for reconciliation.
- Packet-local evidence under `docs/program/inbox/v1a-runner-integrity-20260819/`.

### Protected / forbidden paths
- Canonical `trace` and `trace-lite` product implementations.
- Raw evaluation data and provider secrets.
- Real-data certification publication.

## 5. Observed Facts

1. Canonical `trace-bench` is clean on `main` at commit `c0ea9fbf37bc50c88336f198437be031c18d6f64`.
2. `SOURCE_MANIFEST.json` contains 45 non-manifest tracked entries and computes composite SHA-256 `554555030a8ee6037b41aba3e163b616d1f43ef6b057cb98c7f9242271dad83f`.
3. Offline wheel cache contains all required dependencies, resolving the prior environment blocker `V1A-ENV-001`.
4. The locked verifier virtual environment built offline in 20.83s and loaded `trace_bench` from `venv\Lib\site-packages` non-editably.
5. All 26 tests passed in 202.39s with 0 failures and 0 skips.

## 6. Verification Summary

| Test Family | Cases | Passed | Failed | Status |
| --- | ---: | ---: | ---: | --- |
| Benchmark Harness & Metric Unit Tests | 13 | 13 | 0 | PASS |
| Frozen Negative Fail-Closed Matrix | 13 | 13 | 0 | PASS |
| Total | 26 | 26 | 0 | PASS |

## 7. Invariant Checks

- [x] Source truth was not mutated by a projection operation.
- [x] Exact source and dependency provenance was pinned in the verifier checkout.
- [x] No certification fallback or synthetic substitution was accepted.
- [x] Non-editable wheel installation was strictly enforced.
- [x] Offline execution was strictly verified with zero network calls during testing.
- [x] All 13 negative matrix cases fail closed with `certification_eligible: false`.

## 8. Claim Boundary

Authority level C1: This handoff proves that the `trace-bench` runner at commit `c0ea9fbf37bc50c88336f198437be031c18d6f64` fails closed under the frozen negative matrix and produces valid structured receipts. It does not certify retrieval accuracy, dataset quality, system scale, or downstream release gate passage.
