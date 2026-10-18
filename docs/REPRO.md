# Reproducibility (pins, hardware, re-verification)

## Source pins (frozen bytes)

- Freeze manifest: `freeze-src/cand/SOURCEFREEZE.json`, sha256
  `38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54`
  (207 files, drift `[]`, schema `sup-speed-candidate-v1+fix12356-stack`).
- Parent speed freeze: `dd543d0e2a12c82539bc9381c0fa76f3dd8f713e2138b7690da32de2b8be604b`
  (205 files; copy at `freeze-src/SOURCEFREEZE.speed-parent.json`).
- Baseline freeze: `9cdbc2a48d0ffb84d53c8a3f25012cd352cde7eaf340296441a3ce13ddc55d78`
  (`freeze-src/cand/BASELINE-SOURCEFREEZE.json`).
- Harness pin: `tools/product_pilot.py`
  `9f516288a098eff7b2a52373ad0eaf6b9ad1664377a9f7be4f974701b8d9b1a0`
  (asserted by the audit; equals the manifest entry).
- Base pilot pin (pre-stack): `b25195ba41f7…` (see `freeze-src/BUILD-REPORT.md`).
- Encoder/cache: MiniLM-class staged cache is VM-side data, not source;
  normalization "cached FP32, unnormalized; cosine normalizes at scoring".

## Closure check (no corpus needed)

```bash
python3 tools/verify_freeze.py   # rehashes all 207 files vs SOURCEFREEZE.json
```

`tools/verify_freeze.py` (wrapper, outside `freeze-src/`) must print
`entries=207 ok=207 missing=0 mismatch=0`. Frozen bytes are never edited;
wrappers live outside `freeze-src/`.

## Local tests (synthetic, no corpus, no 10M run)

```bash
bash freeze-src/run_all.sh stack    # stack unit tests (needs a Python with numpy)
bash freeze-src/run_all.sh existing # shipped suites: pending_topk, publication, pool_reuse, serving_pool
```

`run_all.sh` defaults to `/tmp/baseline-venv/bin/python` (falling back to
`python3` on a clean host where that venv does not exist); override with
`PY=python3`. These are the builder's synthetic suites — they do NOT
reproduce the 10M run and claim nothing about it.

Clean-host / CI exclusions (same in `stack`, `existing`, and the default
`run_all.sh` / `all` mode): two checks compare against trees that only
ever existed on the original build host, outside the 207-file freeze.
When the required tree is absent, only that one check is skipped, with
an explicit printed notice, and all other checks still run; when the
tree is present, the full set runs unchanged:

- Stack: 5 of 6 checks; `test_changed_set` is skipped only when the
  staged overlay at `/tmp/fix1stage/up` is absent (the frozen test
  hardcodes that path). Full 6 when it exists.
- Publication (in `existing`, via `tools/run_publication_suite.py`):
  14 of 15 tests; only
  `FlagOffIdentity.test_original_source_bytes_unchanged` is excluded
  when the build host's upstream source tree is absent. Full 15 when
  it exists (or set `TRACE_BUILD_HOST_SOURCE`).

## What the 10M run needs (not runnable from this repo)

- Corpus: staged `docs-100m.jsonl` (VM-side data dir, not shipped);
  10,003,381 actual tokens / 13,081 docs. Vectors are FP32 cached,
  generated/cached at run time.
- Hardware: shared VM, solo CPUs 0–1, ~2.6 h wall (9,494.9 s), 2.85 GiB
  retained store, ~8.5 GB parent RSS peak. Do NOT relaunch a 10M run
  casually: it is a billed, multi-hour experiment, not a test.
- Command (record, seam12a run `o94-scale10m`): `taskset -c 0,1 nice -n 19
  runtime.sh tools/product_pilot.py --tokens 10000000 --profile vm
  --drain-attribution --drain-census --holon-descriptor-columnar
  --overrides-columnar --descriptor-matrix-all --per-view-sharing
  --cold-scan-chunk 4096 --repair-columnar --candidate-source hnsw
  --drain-bounded-k 32 --candidate-shadow-audit 8` with
  `SUP_REUSE_VIEW_POOL=1` and derived cap `max_delta_entries` 669,436.

## Receipts

`receipts/` carries the staged VM JSONs verbatim: `result.json`,
`source-pin.json`, `input.json`, `cap-derivation.json`,
`phase-telemetry.json`, `manifest-before/after.json`, `memory.json`,
`probes.json`, `kill-marker.stages.json`, plus audit `AUDIT-RESULT.json`,
`AUDIT-STATUS.json`, `VM-10M-ACCEPTANCE.json`, `MANIFEST.json`, `PLAN.json`,
`LAUNCH.json`. These stage the earlier-freeze run bytes (see the identity
note in BENCHMARKS.md); the large retained store is excluded (size).

## Small-scale portable reproduction (20k)

[`repro-20k/`](../repro-20k/README.md) ships an exact 88-document /
20,030-token prefix (SciFact corpus abstracts, ODC-By 1.0 per the upstream
allenai/scifact LICENSE record; claims annotations CC-BY-4.0 and SciFact
code Apache-2.0 are not in this export) with derived FP32 vectors from
`all-MiniLM-L6-v2` (Apache-2.0 per its model card; no weights shipped).
All 88 exported rows were inspected as numeric SciFact corpus ids. This
runs the frozen harness locally to PASS and reproduces the *protocol* at
small scale; it is not full-10M reproduction. Full attribution:
[`repro-20k/LICENSES-DATA-MODEL.md`](../repro-20k/LICENSES-DATA-MODEL.md).

## Data / third-party note

The full corpus cache is VM-side staged data (see `documents_source` in
`receipts/input.json`); only the inspected 88-document prefix above ships.
Corpus abstracts licensing follows the source collection's terms; this repo
adds no new data rights beyond that record. Code: Apache-2.0 (`LICENSE`).
