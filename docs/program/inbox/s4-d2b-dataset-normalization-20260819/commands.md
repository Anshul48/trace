# S4 D2b commands

This log begins with read-only preflight. The external normalization command
will be appended after the candidate root is proven new and the input manifest
is present.

| Stage | Command / observation | Result |
| --- | --- | --- |
| Repository identity | `git rev-parse HEAD`; `git status --short --branch` | `c855bb06532b3b52b25f0bea969d2677e5049065`; dirty user snapshot preserved |
| Lease | Read `lease-s4-d2b-normalization-20260819.json` | valid through `2026-08-20T12:40:55.1070524Z`; network/download/provider disabled |
| B1.1 identity | Read local handoff and successor schema | commit and schema pinned; V1a independent verification pending |
| Raw inventory | Enumerate `C:\Users\anshu\AppData\Local\trace-bench-data` | 7 dataset roots, 85 files, 1,523,873,466 bytes |
| Capacity | `[System.IO.DriveInfo]::new('C')` | 391,809,900,544 bytes free at `2026-08-20T03:00:01Z` |
| Output collision check | Pending before external mutation | must be absent or packet stops |
| First normalization attempt | `normalize_d2b.py` with created-at pin `2026-08-20T03:00:01Z` | raw verification and dataset writes completed; final B1 validation failed with `ModuleNotFoundError: No module named 'trace_bench'` due packet utility import-root bug |
| Failed-attempt retention | Moved explicit failed root to `C:\\Users\\anshu\\AppData\\Local\\trace-bench-data\\verification\\d2b-20260819\\failed-attempt-import-path-20260820` | source output root restored absent; failed candidate retained for audit; raw roots unchanged |
| Utility repair | Corrected B1 import root from worktree root to `<worktree>\\src`; syntax rechecked | applied in corrected rerun |
| Post-build map review | Read-only count of `(entity_type, source_key)` in normalized native maps | MultiHop repeated deterministic segment maps detected; repair required before handoff |
| Utility repair 2 | Deduplicate reused deterministic MultiHop segment maps while retaining every judgment link | applied in corrected rerun |
| Owner-side verifier | `verify_d2b.py` against raw root and final candidate | first receipt failed only on missing MuSiQue derived source-document identities and BigANN source-key omission; no raw failures |
| Utility repair 3 | Add `source-documents.jsonl` identities for paragraph-derived MuSiQue documents; add BigANN vector `source_key`; correct SIFT learn count to the live 100,000-record layout | applied in corrected rerun |
| Corrected normalization | `normalize_d2b.py --raw-root C:\\Users\\anshu\\AppData\\Local\\trace-bench-data --out C:\\Users\\anshu\\AppData\\Local\\trace-bench-data\\normalized\\d2b-20260819 --portfolio docs/program/inbox/b2-authorized-data-staging-20260819/evidence/portfolio-staging-manifest.json --created-at-utc 2026-08-20T03:00:01Z` | exit 0; `completed_candidate`; no error receipt; all seven dataset roots written |
| Verifier repair | Updated `verify_d2b.py` to validate `source-documents.jsonl` identities and use them for source-document judgment references; verifier syntax check passed | verifier SHA-256 `8ae581d5719a85eda0355744c98acbdfc30b7f1b941edcf609db77371588c74a` |
| Final owner-side review | `verify_d2b.py` against the raw root, portfolio manifest, and candidate output | pass; raw failures `0`; output failures `0`; checksum entries `134`; receipt `owner-review-final-20260820.json` |
| Failed receipt retention | Moved the earlier failed receipt to `owner-review-initial-failure-20260820.json` | failure remains recoverable evidence; final receipt is separate |
| Clean reproduction | Same normalizer command and fixed timestamp into `verification\\d2b-20260819\\reproduction-output-20260820` | exit 0; no error receipt; checksum map has `134` entries and matches candidate exactly |
| Reproduction comparison | Compare both `checksums.json` maps and top-level/per-dataset manifest hashes | checksum map exact; `checksums.json`, `run-manifest.json`, `COMPLETED.json`, and all seven manifests exact |
| Packet evidence integrity | Parse `evidence/checksums.json`, hash its nine packet files and five external evidence files, and compile both packet utilities without writing bytecode | pass; 0 checksum mismatches; generated syntax-check cache removed |
