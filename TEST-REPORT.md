# TEST-REPORT.md — TRACE stack-fork publication verification

Staged: 2026-10-14. Runner: Muse coordinator. Host: Linux, CPython 3.12.3.
Env: `/tmp/anima-pub-verify2` (uv-seeded + pip) with `blake3` installed for
the frozen suites; `/tmp/baseline-venv` symlinked to it (the frozen
`run_all.sh`/fix1 tests hardcode that build-host path — test-env
provisioning only, frozen bytes untouched).

## Freeze identity (local, independent of any record)

| # | Check | Result |
|---|---|---|
| 1 | `sha256sum stage…/cand/SOURCEFREEZE.json` after VM `scp` | `38c66bef71fb…a43a0d54`, matches audit plan (also computed on-VM) |
| 2 | `tools/verify_freeze.py` on the publication tree | `entries=207 ok=207 missing=0 mismatch=0` |
| 3 | `cand/tmp/` scratch (locks, sqlite, replay outputs, NOT in manifest) | excluded from publication; retained in channel staging copy |

## Suites (frozen bytes, unmodified)

| # | Command | Result |
|---|---|---|
| 4 | `run_all.sh stack` | 5/6 PASS (default_path_identity, fix3_knob, fix6_parity, fix2_suffix, fix5_gc). `test_changed_set`: all in-freeze asserts pass (manifest, drift `[]`, markers, changed-set counts); final sub-check compares against the original build host's `/tmp/fix1stage/` (unrecoverable, never part of the freeze) — environmental, documented in CI |
| 5 | `run_all.sh fix1` | 4/4 PASS (identity_off, schema, selfvalidation, falsifier) |
| 6 | `run_all.sh existing` | PASS (pending_topk 2 passed; publication + pool_reuse unittest OK; serving_pool RESULT: PASS) |
| 7 | `demo/synthetic_recall.py` (20 probes, 2k atoms, seed 7) | runs; `guided_recall10=0.180` on random data — illustrative only, labeled as such |
| 8 | filename secret scan over tracked files | clean (no `.env`/`.pem`/`.key`/`id_rsa`/consented corpus) |
| 9 | SVG parse (`trace-hero`, `trace-architecture`, `phase-walls`, `recall`) | all well-formed; charts carry measured receipt numbers only |

## Not run (by design)

- No 10M run (billed multi-hour VM hardware + VM-side corpus; forbidden by
  task). No full-store download (3.4 GB excluded; sha asserted in acceptance).
- Oracle replay not re-run locally (needs the store); the staged
  `AUDIT-RESULT.json` + fresh-verifier concurrence record stand as the
  qualification evidence, quoted verbatim in `docs/BENCHMARKS.md`.
