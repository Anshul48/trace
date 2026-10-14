# TEST-REPORT.md — candidate verification record

Date: 2026-10-14 (UTC). Tree: `trace-final-release/`, content commit C1
(SHA in MANIFEST.md). Environment: Linux x86_64, Python 3.12.3, venv via
`uv sync` (`UV_CACHE_DIR` + `UV_PROJECT_ENVIRONMENT` overrides), extras
`c10m` (numpy 2.5.1, blake3 0.4.1) + `test` (pytest 9.1.1). Every piped
command ran under `bash -c 'set -o pipefail; …'`; exits below are the
captured `PIPESTATUS`/process exits, not pipeline tails.

## Candidate checks (all must pass — all pass)

| # | command (root = tree) | exit | result |
|---|---|---|---|
| 1 | `sha256sum -c PINS.sha256` (in `c10m/`) | 0 | 110/110 OK |
| 2 | `python demos/demo_c10m_narrow.py --quiet` | 0 | `DEMO PASS` (6 docs, 3 queries, M80-P100-A40), 0.83 s, offline |
| 3 | `python demos/demo_phase1_api.py --quiet` | 0 | `DEMO PASS` (legacy surface) |
| 4 | `pytest tests/test_c10m_demo.py tests/test_w2_demo_smoke.py -q` | 0 | 7 passed |
| 5 | `pytest tests/test_organization_toc.py -q -k "grace_period or 30_day"` | 0 | 3 passed (clock-frozen legacy tests) |
| 6 | `python c10m/data/reconstruct_inputs.py --out-dir … --scifact … --delta …` | 0 | `RECONSTRUCT PASS` (docs-100m 30927 rows / 622471790 B / `c098fdac…`; docs-10m 3099 rows / 64291035 B / `04bbbb3e…`) |
| 6b | `python c10m/data/reconstruct_inputs.py --out-dir … --from-bundle` + `cmp` vs recovered bytes | 0 | `RECONSTRUCT PASS (--from-bundle)` + `BUNDLE-BYTE-IDENTICAL-TO-RECOVERED` |
| 6c | `python c10m/data/bundle/verify_docs_10m.py --out …` (adopted A47 verifier) | 0 | `VERIFY PASS` (gz bytes/sha/mtime0 + raw sha/bytes/rows/keys) |
| 7 | `python benchmarks/evidence/repro-fixture/verify_smoke_receipts.py` | 0 | `SMOKE-VERIFY PASS` (2 arms, 0 failures, identity match) |
| 8 | demo-table check (`/tmp/check_demo_tables2.py`, per-query cells vs `--out` JSON) | 0 | no errors (inspector + tutorial match actual run) |
| 9 | staged-bytes check (`git cat-file :path` vs worktree, all staged paths) | 0 | identical (CRLF normalization defeated via `.gitattributes -text`) |

## Full legacy suite (bounded, one run)

| # | command | exit | result |
|---|---|---|---|
| 10 | `pytest tests/ -q -p no:cacheprovider -rf` (~11:05Z) | 1 | 6 failed, 503 passed, 3 xpassed in 672 s: 4× `test_p4_ballot_pack` (pre-existing missing object `a9b4d3b…`, fails identically at base) + 2× `test_100k_qualification_scaffold` (transient: run while `scale_100k.db` was experimentally removed; see row 10b) |
| 10b | `pytest tests/test_100k_qualification_scaffold.py -q` (post-restore, ~11:18Z) | 0 | 17 passed — db restored to HEAD bytes per ruling (SECRET-SCAN.md §5); full-suite state converges to 4 failed (p4 pre-existing) / 507 passed |

Pre-fix baseline (same command as row 10, before the clock freeze):
exit 1 — 6 failed, 499 passed, 3 xpassed in 690 s (2 clock time-bombs
since fixed test-only, row 5; 4 p4 missing-object, unchanged).

## Install / environment

| # | command | exit | result |
|---|---|---|---|
| 11 | `uv sync --frozen` then `uv lock` + `uv sync --extra c10m --extra test` | 0 | venv resolves; `c10m` extra added (numpy/blake3) + `uv.lock` updated |
| 12 | `python -m pytest tests/ --collect-only -q` (implicit in row 10) | 0 | suite collects (count in row 10) |

## Notes

- No network was used by rows 1–9 except the `uv` package fetch (row 11).
- `docs-10m.jsonl` reconstruction inputs (scifact 8 MB, delta 1.4 GB)
  were read from pinned local paths; outputs went to `/tmp` (not the tree).
- Demo/inspector/tutorial numbers are pre-rendered from row-2-class runs
  and mechanically re-verified per query (row 8), including the A41 span
  corrections and the 110-pin count.
