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

Reproduces the smoke lane (6 docs / 6 queries, bundled
`technical_docs_dev` fixture) end to end:

```bash
pip install benchmarks/evidence/harness/vendor/trace_bench-0.3.0-py3-none-any.whl
pip install 'torch==2.14.0+cpu' 'sentence-transformers==2.7.0' \
    'pyarrow==25.0.1' 'numpy==2.5.3'   # pins of record (../pins/PINS.md)
export HF_HUB_OFFLINE=1   # MiniLM-L6-v2 rev 1110a243… staged locally
python benchmarks/evidence/harness/adapters/stage_pinned.py --dataset smoke
trace-bench run --dataset smoke --backends bm25,python:c2_bench10m:C2Bench10MShipped \
    --top-k 100 --concurrency 1
```

Expected: both arms `success`, 0 failures, metrics matching the smoke
row of REPORT.md §1 within rerun tolerance (fresh-store birth UUIDs
differ per run; scores are deterministic given the pinned weights).
Corpora for the bigger lanes arrive via the same pinned pull
(`c2-bench10m-source-record.json` URLs + revisions); CPU ingest walls
run ~1000 s per 5k-doc fresh store.

The primary one-command runnable in this tree remains the pinned demo:
`python demos/demo_c10m_narrow.py` (synthetic 6-doc fixture, sha256
stand-in encoder, offline, <1 s).
