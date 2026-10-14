# Live BENCH10M reproduction (executable)

Re-run the BENCH10M lanes with the bundled wheel (0.3.0) and the
shipped C2-10M serving stack — not the receipt re-verifier (that is
`../repro-fixture/`, Layer 1) and not the sha256 stand-in demo. The
wrappers in this directory bind every piece the real wheel CLI
requires; they live OUTSIDE the pinned sources and change no frozen
byte.

Historical record of what the numbers mean (fresh Narrow stores per
lane, NOT 1061 queries over the prebuilt 10M corpus; A1 trails on four
lanes, leads pony; attach wall; _186 F2 FAIL): `../provenance/`,
`../receipts-10m-shipped/lane-BENCH10M/REPORT.md`. That record is
unchanged — this directory makes the commands runnable.

## 0. Install (tested 2026-10-14, Linux x86_64, Python 3.12.3)

```bash
pip install benchmarks/evidence/harness/vendor/trace_bench-0.3.0-py3-none-any.whl
pip install blake3 'numpy==2.5.3' 'pyarrow==25.0.1'
pip install 'torch==2.14.0+cpu' --index-url https://download.pytorch.org/whl/cpu
pip install 'sentence-transformers==2.7.0'
```

Notes (pins of record: `../pins/PINS.md`):

- `blake3` is REQUIRED by the product store and comes from NEITHER the
  base wheel nor this recipe's other lines — do not skip it.
- The torch line MUST name the CPU index explicitly: bare
  `pip install 'torch==2.14.0+cpu'` fails on PyPI (the `+cpu` build
  lives only on the PyTorch index).
- Do NOT satisfy these via the wheel's `trace`/`dense` extras: they
  require `sentence-transformers>=3.0`, contradicting the historical
  2.7.0 pin.
- `smoke`/`curated` need no `pyarrow` (wheel-bundled fixtures); the
  BEIR bigger lanes do (parquet→jsonl conversion in `stage_pinned.py`).

## 1. Weights (BEFORE any offline run)

A1/A2 load MiniLM-L6-v2 rev `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
with `HF_HUB_OFFLINE=1`, which gives NO recovery when the revision is
absent. Acquire + validate first (bounded: one repo, one rev, ~90 MB
of model files):

```bash
HF_HOME=/tmp/c2-weights python benchmarks/evidence/live/fetch_weights.py
# WEIGHTS OK /tmp/c2-weights/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243...
```

Keep that `HF_HOME` for every run below.

## 2. Smoke lane (wheel-bundled, no staging)

`smoke` resolves to the wheel-bundled `technical_docs_dev.json`
(6 docs / 6 queries). There is NO `--dataset smoke` staging step —
`stage_pinned.py` stages only the bigger lanes.

```bash
HF_HOME=/tmp/c2-weights HF_HUB_OFFLINE=1 \
  python benchmarks/evidence/live/run_live_lane.py --dataset smoke
# LIVE-LANE PASS dataset=smoke baselines=bm25,python:c2_bench10m:C2Bench10MShipped rc=0
```

Expected: both arms `success`, 0 failures, metrics matching the smoke
row of REPORT.md §1 within rerun tolerance (fresh-store birth UUIDs
differ per run; scores are deterministic given the pinned weights).
The driver assembles the disposable runtime (producer + 7-file serving
overlay, 7/7 hash-verified), writes the keyed `--config`, exports
`TRACE_ARCHITECTURE_DIR` + adapter `PYTHONPATH`, and execs the real
`trace-bench run --baselines ...` (there is no `--backends` option).

`curated` (100 docs / 320 queries) is likewise wheel-bundled:
`--dataset curated`.

## 3. Bigger lanes (stage, then run against the SAME cache)

```bash
python benchmarks/evidence/harness/adapters/stage_pinned.py \
  --manifest benchmarks/evidence/harness/vendor/upstream-links.json \
  --cache /tmp/c2-bench-cache
# STAGE-PINNED: DONE /tmp/c2-bench-cache   (~9 MB pinned pull, hash-gated)

HF_HOME=/tmp/c2-weights HF_HUB_OFFLINE=1 \
  python benchmarks/evidence/live/run_live_lane.py --dataset scifact \
  --data-dir /tmp/c2-bench-cache --output-dir /tmp/c2-bench-runs/scifact
```

Stage `--cache` and run `--data-dir` MUST be the same directory (the
wheel otherwise defaults to `~/.cache/trace-bench-data` and finds
nothing staged). The driver refuses to run a bigger lane whose staged
layout is absent, naming the exact stage command. Bigger-lane CPU
ingest walls run ~1000 s per 5k-doc fresh store (REPORT §7.3); the
`nfcorpus`/`scifact`/`pony` runs are the full-lane reproduction, not
this README's smoke.

## 4. Manual equivalent (no driver)

The driver is convenience over this exact contract (mirroring the
historical `run-nfcorpus.sh`: `TRACE_BENCH_DATA`,
`TRACE_ARCHITECTURE_DIR`, `PYTHONPATH`, `HF_HOME`, `--baselines`):

```bash
RUNTIME=$(python benchmarks/evidence/live/assemble_runtime.py | sed -n 's/^RUNTIME //p')
cat > /tmp/engines.json <<EOF
{"python:c2_bench10m:C2Bench10MShipped": {"architecture_dir": "$RUNTIME"}}
EOF
TRACE_BENCH_DATA=/tmp/c2-bench-cache TRACE_ARCHITECTURE_DIR=$RUNTIME \
PYTHONPATH=benchmarks/evidence/harness/adapters HF_HOME=/tmp/c2-weights \
HF_HUB_OFFLINE=1 python -m trace_bench run --dataset scifact \
  --baselines bm25,python:c2_bench10m:C2Bench10MShipped \
  --config /tmp/engines.json --data-dir /tmp/c2-bench-cache \
  --top-k 100 --concurrency 1 --output-dir /tmp/c2-bench-runs/scifact
```

Config keys are the FULL `python:module:Class` engine names; pointing
`architecture_dir` at `c10m/producer` alone would silently serve
pre-repair bytes — always use the assembled runtime.

## 5. 10M store build (separate recipe)

Extracting the exact inputs (`reconstruct_inputs.py --from-bundle`)
is NOT a store rebuild. The true build inputs, disposable-root
staging, and the embedding-cache preparation path are in
`STORE-BUILD.md` + `prepare_emb_cache.py`.
