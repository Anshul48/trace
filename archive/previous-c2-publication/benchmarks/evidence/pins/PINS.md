# Dependency pins (bench harness of record)

Recorded from lane-BENCH10M REPORT.md §3 (the measured environment).
A byte-exact `pip freeze` was not preserved in the scoped sources, so
the first table is the reported record; the second table is the
actually-installed set a live smoke + curated re-run verified on
2026-10-14 (Linux x86_64, Python 3.12.3). Only the second table is a
tested installation — present it as such.

| component (reported record) | version |
|---|---|
| Python | 3.12.3 |
| trace-bench | 0.3.0 (wheel vendored in `../harness/vendor/`, `3c11d3ed…`) |
| torch | 2.14.0+cpu |
| sentence-transformers | 2.7.0 |
| pyarrow | 25.0.1 |
| numpy | 2.5.3 |
| MiniLM-L6-v2 weights | rev `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, `HF_HUB_OFFLINE=1` |

Tested install (2026-10-14; smoke + curated live lanes PASS, §C4):

```bash
pip install benchmarks/evidence/harness/vendor/trace_bench-0.3.0-py3-none-any.whl
pip install blake3 'numpy==2.5.3' 'pyarrow==25.0.1'
pip install 'torch==2.14.0+cpu' --index-url https://download.pytorch.org/whl/cpu
pip install 'sentence-transformers==2.7.0'
```

Resolved set (exact): blake3 1.0.11, torch 2.14.0+cpu (CPU-only,
`cuda.is_available()` False), sentence-transformers 2.7.0,
transformers 4.57.6, tokenizers 0.22.2 (both match the
`gpu_encode/config.py` PIN record), huggingface-hub 0.36.2, pyarrow
25.0.1, numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.1, safetensors
0.8.0, trace-bench 0.3.0 (vendored wheel).

Rules:

- `blake3` is REQUIRED by the product store and is provided by NONE
  of the other lines — install it explicitly.
- The `+cpu` torch build lives ONLY on the PyTorch CPU index: the
  `--index-url` is mandatory, not a hint.
- Do NOT use the wheel's `trace`/`dense` extras: they require
  `sentence-transformers>=3.0`, contradicting the historical pin.

Frozen-rung (scale10m, 2026-10-04) environment: laptop run, TOK-10M
exact vector, M_REGIONS=20, encode cached for all systems; see
`receipts-10m-shipped/scale10m/BUILD-REPORT.md` §5 for the exact
phase-2 command.

C2-10M demo/ingest environment (this tree): `pip install -e .[c10m]`
(numpy + blake3; MiniLM/torch NOT required — the demo discloses a
deterministic sha256-hash stand-in encoder).
