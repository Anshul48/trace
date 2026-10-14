# Dependency pins (bench harness of record)

Recorded from lane-BENCH10M REPORT.md §3 (the measured environment).
A byte-exact `pip freeze` was not preserved in the scoped sources, so
these are the reported component versions — re-running reviewers should
pin to them and record their own freeze.

| component | version |
|---|---|
| Python | 3.12.3 |
| trace-bench | 0.3.0 (wheel vendored in `../harness/vendor/`, `3c11d3ed…`) |
| torch | 2.14.0+cpu |
| sentence-transformers | 2.7.0 |
| pyarrow | 25.0.1 |
| numpy | 2.5.3 |
| MiniLM-L6-v2 weights | rev `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, `HF_HUB_OFFLINE=1` |

Frozen-rung (scale10m, 2026-10-04) environment: laptop run, TOK-10M
exact vector, M_REGIONS=20, encode cached for all systems; see
`receipts-10m-shipped/scale10m/BUILD-REPORT.md` §5 for the exact
phase-2 command.

C2-10M demo/ingest environment (this tree): `pip install -e .[c10m]`
(numpy + blake3; MiniLM/torch NOT required — the demo discloses a
deterministic sha256-hash stand-in encoder).
