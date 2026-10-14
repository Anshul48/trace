# C2-10M repro appendix (exact commands)

All commands run from the repository root EXCEPT the pins check in §0,
which runs inside `c10m/` (the manifest paths are c10m-relative; the
root form fails). Exit statuses below were observed in the packager's
verification runs on 2026-10-14 (Linux x86_64, Python 3.12.3); see
`TEST-REPORT.md` for the pipefail-captured record. No step needs
network except the pinned corpus/weight pulls, which are hash-gated.

## 0. Install

```bash
pip install -e .[c10m]          # demo: numpy + blake3 (stdlib-only core)
pip install -e .[test]          # test extras (pytest, …)
(cd c10m && sha256sum -c PINS.sha256)   # 110/110 OK expected
```

## 1. Primary demo (pinned serving stack, offline, <1 s)

```bash
python demos/demo_c10m_narrow.py
# DEMO PASS: pinned C2-10M serving stack ran offline (6 synth docs, 3 queries, budgets M80-P100-A40).
```

POSIX only (`fcntl` locking). `--out FILE` saves results JSON. Stable
across fresh runs: doc ids, scores, spans, returned order, status,
support. Varying fresh-store identities (preserved verbatim, never
byte-compared): store birth UUID/pin, per-entry `atom_id` hashes.
Walkthroughs: `demos/c10m_inspector.html` (static page) and
`demos/c10m_tutorial.md` (text equivalent).

## 2. Input reconstruction (exact freeze-v2 bytes)

```bash
python c10m/data/reconstruct_inputs.py --out-dir /tmp/c10m-inputs --from-bundle
# RECONSTRUCT PASS (--from-bundle): 3099 rows, 64291035 B, 04bbbb3e… exact
```

No 1.4 GB delta or 100M parent needed: the tool hash-gates the shipped
deterministic bundle, extracts it, and verifies rows/bytes/hash. The
upstream recipe (rebuilding both corpora from pinned sources + maps)
and `--check-only` mode, acquisition details, per-dataset
licenses/attribution, and the stated `wikipedia_delta.jsonl` fetch
note: `c10m/data/DATA-README.md`.

Extraction is NOT a store rebuild: it produces the exact input bytes
only. The true 10M build inputs (disposable producer-root staging,
profile/anchors, embedding-cache preparation): `c10m/data/DATA-README.md`
§7 + `benchmarks/evidence/live/STORE-BUILD.md`.

## 3. Bench receipt re-verification (stdlib only)

```bash
python benchmarks/evidence/repro-fixture/verify_smoke_receipts.py
# SMOKE-VERIFY PASS (2 arms success, 0 failures, published smoke numbers + identity match)
```

## 4. Live bench re-run (needs weights + corpora)

```bash
pip install benchmarks/evidence/harness/vendor/trace_bench-0.3.0-py3-none-any.whl
pip install blake3 'numpy==2.5.3' 'pyarrow==25.0.1'
pip install 'torch==2.14.0+cpu' --index-url https://download.pytorch.org/whl/cpu
pip install 'sentence-transformers==2.7.0'
# blake3 is required by the product store (no wheel extra provides it
# with the historical pins); the torch +cpu build lives ONLY on the
# PyTorch index; do NOT use the wheel trace/dense extras (they demand
# sentence-transformers>=3.0, contradicting the 2.7.0 pin).

# bounded weight acquisition FIRST (offline runs give no recovery):
HF_HOME=/tmp/c2-weights python benchmarks/evidence/live/fetch_weights.py
# WEIGHTS OK …/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41

# smoke (wheel-bundled fixture; NO staging step):
HF_HOME=/tmp/c2-weights HF_HUB_OFFLINE=1 \
  python benchmarks/evidence/live/run_live_lane.py --dataset smoke
# LIVE-LANE PASS dataset=smoke
#   baselines=bm25,python:c2_bench10m:C2Bench10MShipped rc=0

# bigger lanes (stage, then run against the SAME cache dir):
python benchmarks/evidence/harness/adapters/stage_pinned.py \
  --manifest benchmarks/evidence/harness/vendor/upstream-links.json \
  --cache /tmp/c2-bench-cache
# STAGE-PINNED: DONE /tmp/c2-bench-cache
HF_HOME=/tmp/c2-weights HF_HUB_OFFLINE=1 \
  python benchmarks/evidence/live/run_live_lane.py --dataset scifact \
  --data-dir /tmp/c2-bench-cache --output-dir /tmp/c2-bench-runs/scifact
```

The driver assembles the disposable runtime (producer tree + 7-file
serving overlay, hash-verified — never `c10m/producer` alone), writes
the keyed `--config`, and binds `TRACE_ARCHITECTURE_DIR`, adapter
`PYTHONPATH`, and `--data-dir`. The wheel option is `--baselines`
(there is no `--backends`); the manual env contract is in
`benchmarks/evidence/live/README.md` §4. Full protocol, conditions,
and host of record: `benchmarks/evidence/harness/README.md` +
`provenance/CONFIG.md`. Bigger lanes cost ~1000 s CPU ingest per 5k-doc
fresh store. Verified live 2026-10-14: smoke + curated reproduce the
REPORT.md §1 rows exactly (see TEST-REPORT.md C4 §).

## 5. Test suite (bounded legacy + candidate tests)

```bash
python -m pytest tests/test_c10m_demo.py tests/test_w2_demo_smoke.py -q  # 7 passed
python -m pytest tests/test_organization_toc.py -q -k "grace_period or 30_day"  # 3 passed
```

Full suite: 499 passed + fixes above; 4 pre-existing `test_p4_ballot_pack`
failures (commit `a9b4d3b…` absent from clone history — fails identically
at the base commit; unrelated to this candidate). Exact totals and
per-command exits: `TEST-REPORT.md`.

## Pins of record (re-verify any byte)

- Serving (7): `c10m/README.md` table / `c10m/PINS.sha256`.
- Harness (wheel + 4 adapters): `benchmarks/evidence/CANDIDATE-PINS.md`.
- Upstreams + corpora: `c10m/data/DATA-README.md` + tool `PINS` table.
- Bench corpora (8 files, URLs + revisions): `c2-bench10m-source-record.json`.
- Big run dumps (hash record only): `ARTIFACT-INVENTORY.md`.
