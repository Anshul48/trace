# Bench harness (executable, pinned)

`adapters/` + `vendor/` reproduce the BENCH10M measurement stack:

- `vendor/trace_bench-0.3.0-py3-none-any.whl` (`3c11d3ed…`, 440383 B) —
  the exact harness build. Install: `pip install
  benchmarks/evidence/harness/vendor/trace_bench-0.3.0-py3-none-any.whl`
  (plus the dependency pins in `../pins/PINS.md`: blake3,
  torch 2.14.0+cpu from the PyTorch CPU index,
  sentence-transformers 2.7.0, pyarrow 25.0.1, numpy 2.5.3,
  Python 3.12).
- `adapters/c2_bench10m.py` (`0f6e7bc3…`) — A1 PRIMARY TB backend
  (`C2Bench10MShipped`: fresh Narrow store, shipped serving stack,
  M80-P100-A40) and A2 diagnostic (`C2Bench10MK100`, MAX_ENTRIES=100).
- `adapters/c2_store_probe.py` (`0ceb3670…`) — A3 standalone
  deployment-condition probe (not a TB backend): opens a byte-verified
  store copy read-only at pin `:0:95436` and times attach + query.
- `adapters/stage_pinned.py` (`06b279cd…`, 162-fix) — pinned pull +
  hash verify + TB-cache staging. Fixes the S1 same-basename collision
  that overwrote the pony corpus file (see `pony-collision-162.log` in
  the receipts; the vendored `SHA256SUMS` preserves the pre-fix record).
- `adapters/c2_rekey.py` (`07606fea…`) — lock-identity rekey for a store
  COPY, guarded to the lane dir (content untouched).
- `vendor/upstream-links.json` (`e5fb424a…`) — public upstream
  acquisition links (parquet URLs + revisions + row counts) for the
  bench tiers; `vendor/SHA256SUMS` — the original staging record.

## Run protocol (from REPORT.md §3)

1. Stage corpora (bigger lanes only; `smoke`/`curated` are
   wheel-bundled and need no staging), from the repo root:
   `python benchmarks/evidence/harness/adapters/stage_pinned.py
   --manifest benchmarks/evidence/harness/vendor/upstream-links.json
   --cache <dir>` (pinned pull, all bytes+sha verified; BEIR
   parquet→jsonl round-trip identical).
2. Run lanes: trace-bench with `--top-k 100 --concurrency 1`, TB
   defaults otherwise (`warmup 0`, linear nDCG gain, official splits).
   The selection flag is `--baselines` (there is no `--backends`).
3. Compares: static mode, paired percentile bootstrap (2000 samples,
   seed 42), two-sided paired t-test, **no multiple-comparison
   correction** (original methodology — do not invent corrections).
4. Weights: MiniLM-L6-v2 rev `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`,
   `HF_HUB_OFFLINE=1`; A1/A2 raw encode, dense unit-normalized.
   Acquire + validate the pinned snapshot BEFORE the offline run
   (`../live/fetch_weights.py`); offline runs give no recovery.
5. Host of record: `tl-m2-cpu`, Linux 7.0.0-1013-gcp x86_64, 12 vCPU,
   Python 3.12.3. New hosts re-measure; do not copy latencies across hosts.

## Live-run binding (what the wheel CLI requires)

- Runtime: the A1/A2 arms need the assembled product tree (producer +
  7-file serving overlay), bound as `TRACE_ARCHITECTURE_DIR` or the
  keyed `--config` `architecture_dir` (keyed by the full
  `python:...` engine name). Never point it at `c10m/producer` alone
  (pre-repair serving bytes). Assemble: `../live/assemble_runtime.py`.
- Adapters: `adapters/` must be on `PYTHONPATH` (the wheel resolves
  `python:module:Class` via `importlib.import_module`).
- Cache: stage `--cache` and run `--data-dir` (or `TRACE_BENCH_DATA`)
  must be the SAME dir; the wheel otherwise defaults to
  `~/.cache/trace-bench-data`.
- Executable driver doing all of the above: `../live/run_live_lane.py`
  (see `../live/README.md`); the historical `run-nfcorpus.sh` shows the
  same env contract (`TRACE_BENCH_DATA`, `TRACE_ARCHITECTURE_DIR`,
  `PYTHONPATH`, `HF_HOME`, `--baselines`).

The cheap runnable subset is `../repro-fixture/` (smoke lane, minutes).
Full-lane reproduction needs the weights + corpora above and CPU ingest
walls of ~1000 s per 5k-doc fresh store (REPORT §7.3).
