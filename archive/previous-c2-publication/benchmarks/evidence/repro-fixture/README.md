# Cheap public-fixture reproduction (minutes, NOT 10M measurements)

Two layers. Neither substitutes fixture scores for 10M measurements.

## Layer 1 — receipt re-verification (runs now, stdlib only)

```bash
python benchmarks/evidence/repro-fixture/verify_smoke_receipts.py
```

Expected: `SMOKE-VERIFY PASS …`. Parses the bundled smoke RUN.json +
TRECs and asserts the published smoke numbers (bm25 0.903 / A1 0.851
nDCG@10, 0 failures), the A1 self-identity (`shipped-M80-P100-A40`,
budgets, adapter `0f6e7bc3…`, all 7 serving shas). This checks receipt
integrity only.

## Layer 2 — live lane re-run (needs weights + corpora)

Reproduces the smoke lane (6 docs / 6 queries, wheel-bundled
`technical_docs_dev` fixture) end to end with the real pinned
encoder. Full guide: `../live/README.md`.

```bash
pip install benchmarks/evidence/harness/vendor/trace_bench-0.3.0-py3-none-any.whl
pip install blake3 'numpy==2.5.3' 'pyarrow==25.0.1'   # pins: ../pins/PINS.md
pip install 'torch==2.14.0+cpu' --index-url https://download.pytorch.org/whl/cpu
pip install 'sentence-transformers==2.7.0'
# Do NOT use the wheel trace/dense extras (they demand
# sentence-transformers>=3.0, contradicting the 2.7.0 pin).

# bounded weight acquisition FIRST (offline runs give no recovery):
HF_HOME=/tmp/c2-weights python benchmarks/evidence/live/fetch_weights.py
# WEIGHTS OK …/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41

# smoke needs NO dataset staging (wheel-bundled); there is no
# `--dataset smoke` staging flag:
HF_HOME=/tmp/c2-weights HF_HUB_OFFLINE=1 \
  python benchmarks/evidence/live/run_live_lane.py --dataset smoke
# LIVE-LANE PASS dataset=smoke
#   baselines=bm25,python:c2_bench10m:C2Bench10MShipped rc=0
```

(The driver assembles the disposable runtime — producer tree + 7-file
serving overlay — writes the keyed `--config`, and binds
`TRACE_ARCHITECTURE_DIR`, adapter `PYTHONPATH`, and `--data-dir`.
The wheel option is `--baselines`; there is no `--backends`.)

Expected: both arms `success`, 0 failures, metrics matching the smoke
row of REPORT.md §1 within rerun tolerance (fresh-store birth UUIDs
differ per run; scores are deterministic given the pinned weights).
Verified live 2026-10-14: smoke reproduces bm25 0.903 / A1 0.851
nDCG@10 exactly; curated (likewise wheel-bundled) reproduces bm25
0.639 / A1 0.621 exactly (see TEST-REPORT.md C4 §).
Bigger lanes stage first, then run against the SAME cache dir:

```bash
python benchmarks/evidence/harness/adapters/stage_pinned.py \
  --manifest benchmarks/evidence/harness/vendor/upstream-links.json \
  --cache /tmp/c2-bench-cache
# STAGE-PINNED: DONE /tmp/c2-bench-cache
HF_HOME=/tmp/c2-weights HF_HUB_OFFLINE=1 \
  python benchmarks/evidence/live/run_live_lane.py --dataset scifact \
  --data-dir /tmp/c2-bench-cache --output-dir /tmp/c2-bench-runs/scifact
```

Corpora for the bigger lanes arrive via the pinned pull
(`c2-bench10m-source-record.json` URLs + revisions); CPU ingest walls
run ~1000 s per 5k-doc fresh store.

The primary one-command runnable in this tree remains the pinned demo:
`python demos/demo_c10m_narrow.py` (synthetic 6-doc fixture, sha256
stand-in encoder, offline, <1 s).
