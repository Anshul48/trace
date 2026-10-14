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

`run_all.sh` defaults to `/tmp/baseline-venv/bin/python`; override with
`PY=python3`. These are the builder's synthetic suites — they do NOT
reproduce the 10M run and claim nothing about it.

## What the 10M run needs (not runnable from this repo)

- Corpus: staged `docs-100m.jsonl` cache + prefix/meta/index/vector pins in
  `receipts/input.json` (VM-side `beam/pkg/data/`, not shipped).
- Hardware: 16 vCPU / ~125 GiB GCP VM, solo CPUs 0–2, ~3.6 h wall, ~2.9 GB
  retained store. Do NOT relaunch a 10M run casually: it is a billed,
  multi-hour experiment, not a test.
- Command (record, from the audit plan): `taskset -c 0-2 nice -n 19
  product_pilot.py --tokens 10000000 --profile vm --drain-instrument
  --drain-budget-s 5438` with derived caps 669,436 / 1,000,000.

## Receipts

`receipts/` carries the staged VM JSONs verbatim: `result.json`,
`source-pin.json`, `input.json`, `cap-derivation.json`,
`phase-telemetry.json`, `manifest-before/after.json`, `memory.json`,
`probes.json`, `kill-marker.stages.json`, plus audit `AUDIT-RESULT.json`,
`AUDIT-STATUS.json`, `VM-10M-ACCEPTANCE.json`, `MANIFEST.json`, `PLAN.json`,
`LAUNCH.json`. The 3.4 GB `runs/pilot-10M/store/` is excluded (size);
its sha (`52e88439…`, 229,927 files) is asserted in the acceptance record.

## Data / third-party note

The corpus cache is VM-side staged data (see `documents_source` in
`receipts/input.json`); no corpus, weights, or private data ship here.
Corpus abstracts licensing follows the source collection's terms; this repo
adds no new data rights. Code: Apache-2.0 (`LICENSE`).
