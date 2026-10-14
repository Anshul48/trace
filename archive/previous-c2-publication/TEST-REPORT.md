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
| 6c | `python c10m/data/bundle/verify_docs_10m.py --out …` (corrected A52 verifier) | 0 | `VERIFY PASS` (gz bytes/sha/mtime0 + raw sha/bytes/rows/keys; alias guards + atomic extraction) |
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

## C3 successor — corrected verifier adoption (A50–A53, 2026-10-14)

C2 `c0eede0…` is HOLD per A51 (old verifier truncated an aliased
asset/out before failing). C3 adopts the corrected
`data-public-package/verify_docs_10m.py` byte-exact (`8180c800…` →
`20bfbbf9…`, independently PASSed in channel
`trace-demo-review/FINAL-DATA-RECHECK.md`) and delegates the
`--from-bundle` path to it (the inline `gzip` copy in
`reconstruct_inputs.py`, which wrote `--out` before verifying, is
removed). Asset bytes unchanged: gz 21787645 B `31002b8c…`, raw
64291035 B `04bbbb3e…`, 3099 rows. Repinned: verifier `20bfbbf9…`,
`reconstruct_inputs.py` `f34ef62f…`, `DATA-README.md` `671be05a…`
(`sha256sum -c` 110/110 OK). No broad rerun per A51; focused checks
(all outputs to `/tmp` only; in-tree asset re-verified unchanged):

| # | command (root = tree) | exit | result |
|---|---|---|---|
| C3-1 | `python c10m/data/bundle/verify_docs_10m.py --self-test` | 0 | `SELF-TEST 7 passed, 0 failed` (same-path / symlink / hardlink / malformed-asset-schema-digest / normal-exact) |
| C3-2 | `python /tmp/w2d_negcheck.py` (disposable real-asset copies) | 0 | 5/5: same-path, symlink-alias, hardlink-alias, truncated-asset cases exit 1 with asset + sentinel output preserved; 2× extraction + `gzip -dc` byte-identical (`04bbbb3e…`, 64291035 B, 3099 rows); no `*.tmp-*` leftovers |
| C3-3 | `python c10m/data/reconstruct_inputs.py --out-dir … --from-bundle` + `cmp` vs `gzip -dc` | 0 | `VERIFY PASS` + `RECONSTRUCT PASS (--from-bundle)`; `cmp` identical |
| C3-4 | `sha256sum -c PINS.sha256` (in `c10m/`) | 0 | 110/110 OK |

## C4 — benchmark-CLI contract repair (A56/A58/A60/A61, 2026-10-14)

C3 `c604b46…` left the documented live-bench commands unrunnable
(`trace-demo-review/BENCH-COMMAND-RECHECK.md`, 8 blockers B1–B8) plus
audit doc nits F2/F3 (`trace-audit/FINDINGS.md`). C4 fixes docs only
and adds executable wrappers/config under
`benchmarks/evidence/live/` (outside the pinned sources); all 89
freeze-v2 producer/serving bytes, the wheel, and the 4 adapters are
byte-unchanged. Two c10m doc files changed text (F2/B8 + §7 pointer)
and were repinned: `README.md` `937df6a9…` → `df1cd8d0…`,
`data/DATA-README.md` `671be05a…` → `ed97e038…`.

Environment: Linux x86_64, Python 3.12.3, fresh `/tmp` venv
(`uv venv` + `uv pip install`): vendored wheel + blake3 1.0.11 +
numpy 2.5.3 + pyarrow 25.0.1 + torch 2.14.0+cpu (PyTorch CPU index,
`cuda.is_available()` False) + sentence-transformers 2.7.0
(resolving transformers 4.57.6, tokenizers 0.22.2 — both match the
`gpu_encode/config.py` PIN record — hub 0.36.2, scipy 1.18.1,
scikit-learn 1.9.1, safetensors 0.8.0). Weights: pinned MiniLM rev
`1110a243…` via `snapshot_download` into a disposable `HF_HOME`.

| # | command (root = tree) | exit | result |
|---|---|---|---|
| C4-1 | `HF_HOME=… HF_HUB_OFFLINE=1 python benchmarks/evidence/live/run_live_lane.py --dataset smoke` | 0 | `LIVE-LANE PASS` (bm25 + A1, real pinned encoder): bm25 0.903/0.833/0.933, A1 0.851/0.740/1.000/0.900 nDCG/MAP/R@20/MRR, 0 failures — REPORT.md §1 smoke row EXACT; RUN.json self-authenticates 7/7 serving shas + `shipped-M80-P100-A40` |
| C4-2 | same driver `--dataset curated` | 0 | `LIVE-LANE PASS` (100 docs / 320 queries): bm25 0.639/0.585/0.771, A1 0.621/0.555/0.703 — REPORT.md §1 curated row EXACT, 0 failures |
| C4-3 | `python …/adapters/stage_pinned.py --manifest …/vendor/upstream-links.json --cache …` | 0 | `STAGE-PINNED: DONE` (8 pinned files, bytes+sha verified; scifact 5183 docs / 300 test queries; nfcorpus 3633/323; pony parquets placed; parquet→jsonl round-trip identical) |
| C4-4 | driver `--dataset scifact --data-dir <same cache> --baselines bm25 --limit 5` | 0 | `LIVE-LANE PASS` — stage→run cache binding proven end to end on a bigger lane (diagnostic 5-query subset only, NOT comparable to full-lane numbers) |
| C4-5 | driver `--dataset scifact --data-dir <empty dir>` | 1 | refuses: `LIVE-LANE FAIL: staged layout … not found …; stage first` + exact stage command |
| C4-6 | driver `--dataset smoke` with empty `HF_HOME` | 1 | refuses: `WEIGHTS FAIL: pinned snapshot absent …` + acquisition instruction (no mid-run offline failure) |
| C4-7 | `python …/live/fetch_weights.py` then `--check-only` | 0 | `WEIGHTS OK` pinned snapshot (config.json + modules.json + weight file present) |
| C4-8 | `python …/live/assemble_runtime.py --out …` | 0 | `RUNTIME …` + `SERVING-OVERLAY 7/7 pinned bytes verified` |
| C4-9 | `python -m trace_bench run --dataset smoke --backends bm25` | 2 | `Error: No such option '--backends'` (documents B1: `--baselines` is the only flag) |
| C4-10 | `python …/live/prepare_emb_cache.py --docs <3-doc fixture> --cache-dir … --no-pin-check --max-docs 3` + strict `make_file_backed_emb` serve-back | 0 | `EMB-CACHE PARTIAL` (validation only): 3 docs / 3 chunks / 3 rows, 3/3 keys locate, `config_id` matches builder pin; strict serve-back `STRICT-SERVE OK` (1 chunk, dim 384, 0 misses) |
| C4-11 | `(cd c10m && sha256sum -c PINS.sha256)` | 0 | 110/110 OK (after the 2 doc repins above) |
| C4-12 | `sha256sum -c c10m/PINS.sha256` (root form, MUST fail) | 1 | 109 unreadable + 1 mismatch — evidences B8/F2 (manifest is c10m-relative) |
| C4-13 | `git diff C3 HEAD --name-only` scope check | 0 | docs/wrappers/config only; zero frozen-byte changes (wheel/adapters/producer/serving untouched) |

Truthful remaining limits (unchanged by C4): no full 1061-query
re-run (smoke 6 + curated 320 live-verified; bigger C2 arms project
~1000 s ingest per 5k-doc store, unmeasured here); no 10M store
build executed (recipe + cache-prep control flow verified on a tiny
fixture; store byte-identity with `:0:95436` NOT claimed); latencies
re-measured on this host only (p95 smoke A1 138.6 ms vs 17.2 ms of
record — new hosts re-measure per CONFIG.md). No broad suite rerun
per A61 (docs/wrappers only; rows 1–9 code paths untouched).

## Notes

- No network was used by rows 1–9 except the `uv` package fetch (row 11).
- `docs-10m.jsonl` reconstruction inputs (scifact 8 MB, delta 1.4 GB)
  were read from pinned local paths; outputs went to `/tmp` (not the tree).
- Demo/inspector/tutorial numbers are pre-rendered from row-2-class runs
  and mechanically re-verified per query (row 8), including the A41 span
  corrections and the 110-pin count.
