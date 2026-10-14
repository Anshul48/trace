# Bench harness (executable, pinned)

`adapters/` + `vendor/` reproduce the BENCH10M measurement stack:

- `vendor/trace_bench-0.3.0-py3-none-any.whl` (`3c11d3ed…`, 440383 B) —
  the exact harness build. Install: `pip install
  benchmarks/evidence/harness/vendor/trace_bench-0.3.0-py3-none-any.whl`
  (plus the dependency pins in `../pins/PINS.md`: torch 2.14.0+cpu,
  sentence-transformers 2.7.0, pyarrow 25.0.1, numpy 2.5.3, Python 3.12).
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

1. Stage corpora: `python adapters/stage_pinned.py` (pinned pull, all
   bytes+sha verified; BEIR parquet→jsonl round-trip identical).
2. Run lanes: trace-bench with `--top-k 100 --concurrency 1`, TB
   defaults otherwise (`warmup 0`, linear nDCG gain, official splits).
3. Compares: static mode, paired percentile bootstrap (2000 samples,
   seed 42), two-sided paired t-test, **no multiple-comparison
   correction** (original methodology — do not invent corrections).
4. Weights: MiniLM-L6-v2 rev `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`,
   `HF_HUB_OFFLINE=1`; A1/A2 raw encode, dense unit-normalized.
5. Host of record: `tl-m2-cpu`, Linux 7.0.0-1013-gcp x86_64, 12 vCPU,
   Python 3.12.3. New hosts re-measure; do not copy latencies across hosts.

The cheap runnable subset is `../repro-fixture/` (smoke lane, minutes).
Full-lane reproduction needs the weights + corpora above and CPU ingest
walls of ~1000 s per 5k-doc fresh store (REPORT §7.3).
