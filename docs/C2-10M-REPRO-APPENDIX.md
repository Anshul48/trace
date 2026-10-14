# C2-10M repro appendix (exact commands)

All commands run from the repository root. Exit statuses below were
observed in the packager's verification runs on 2026-10-14 (Linux
x86_64, Python 3.12.3); see `TEST-REPORT.md` for the pipefail-captured
record. No step needs network except the pinned corpus/weight pulls,
which are hash-gated.

## 0. Install

```bash
pip install -e .[c10m]          # demo: numpy + blake3 (stdlib-only core)
pip install -e .[test]          # test extras (pytest, …)
sha256sum -c c10m/PINS.sha256   # 105/105 OK expected (run inside c10m/)
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

## 3. Bench receipt re-verification (stdlib only)

```bash
python benchmarks/evidence/repro-fixture/verify_smoke_receipts.py
# SMOKE-VERIFY PASS (2 arms success, 0 failures, published smoke numbers + identity match)
```

## 4. Live bench re-run (needs weights + corpora)

```bash
pip install benchmarks/evidence/harness/vendor/trace_bench-0.3.0-py3-none-any.whl
pip install 'torch==2.14.0+cpu' 'sentence-transformers==2.7.0' \
    'pyarrow==25.0.1' 'numpy==2.5.3'
export HF_HUB_OFFLINE=1   # MiniLM-L6-v2 rev 1110a243… staged locally
python benchmarks/evidence/harness/adapters/stage_pinned.py
trace-bench run --dataset smoke --backends bm25,python:c2_bench10m:C2Bench10MShipped \
    --top-k 100 --concurrency 1
```

Full protocol, conditions, and host of record:
`benchmarks/evidence/harness/README.md` + `provenance/CONFIG.md`.
Bigger lanes cost ~1000 s CPU ingest per 5k-doc fresh store.

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
