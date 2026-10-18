# 10M benchmarks (freeze `seam12a`, run `o94-scale10m`)

All numbers below are from the seam12a freeze audit (tarball sha256
`8d3bbb6bf53e1731811065a9de156a9997be740d598cd1dfa0a3d946928dbf64`,
253 frozen files re-verified 0-diff). Metric definitions first, then the
run and conditions. Nothing here is inferred from any other campaign;
those stay out of this repo.

## Metric definitions

| Metric | Definition | Pass bar (this run) |
|---|---|---|
| `status` | pilot verdict in `result.json` | `PASS` |
| `actual_tokens` / `complete_documents` / `atoms` | TOK_V1 counts over the staged corpus | 10,003,381 / 13,081 / 63,441 |
| `pending_documents`, `repair_to_zero.final_debt` | unconverged docs / residual debt after bounded repair | both `0` |
| `commits` (closed ledger) | ledger commits vs derived cap | 164,195 < 669,436 (`max_delta_entries`) |
| `guided_recall10` / `flat_recall10` | Two recorded modes, 120 probes each: `all_sources` and `leave_source_out`; guided and flat score identical mean rows per mode (matched work) | see both-modes table below |

**Scope of these metrics:** harness recall and probe agreement on the recorded probe protocol, measured on a shared VM under experimental derived caps. They are **not** semantic-IR quality, nDCG, a BM25 comparison, a SOTA claim, or a universal latency guarantee.
| `all_within_5s` (F1) | 33 visibility queries, ACK-return→query latency | true (p50 96.8 ms, p95 115.5 ms) |
| `manifest_match` | store manifest before==after byte-equal | `true` |
| `frozen_ok` / `frozen_files` | freeze rehash of all files + harness pin | `true` / 253 |
| probes pin | evaluation probe set sha | `b332d62d…` |
| harness pin | `tools/product_pilot.py` freeze entry | `9f78479a…` |

## The qualified run (the only 10M run in scope)

Run `o94-scale10m`, CPUs 0–1, nice 19, numpy 2.5.3, BLAS threads = 1.
`taskset -c 0,1` + `SUP_REUSE_VIEW_POOL=1`, candidate source hnsw,
drain bounded k32, cold-scan chunk 4096, repair columnar.
Wall **9,494.9 s (~2.6 h)**. Verdict `PASS`.

### Phase walls (s, observed)

| Phase | Wall (s) | Share |
|---|---|---|
| ingest (visible + prepare) | 586.9 | 6% |
| initial drain + prepare | 999.4 | 11% |
| append ingest with readers | 1,163.2 | 12% |
| source-capacity rejection | 1.83 | <1% |
| prepare rejection (fresh frontier) | 170.3 | 2% |
| writer kill + restart | 516.5 | 5% |
| remaining drain + prepare with readers | 4,654.4 | 49% |
| repair_to_zero (6 iters, debt 5,847 → 0) | 1,162.1 | 12% |
| **total run wall** | **9,494.9 (~2.6 h)** | 100% |

### Both recorded probe modes (guided vs matched-flat control)

| Mode | Guided recall@10 | Flat recall@10 | Probes |
|---|---|---:|---:|
| `all_sources` | 0.7367 | 0.055 | 120 |
| `leave_source_out` | 0.4883 | 0.0017 | 120 |

Fresh-item query: p50 96.8 ms / p95 115.5 ms (n=33, all within 5 s);
append ack→query 0.114 s. Readers: 2 threads, 27,796 requests, p50 74.7 ms.

### Scale, ledger, hardware (observed)

| Field | Value |
|---|---|
| tokens / docs / atoms | 10,003,381 / 13,081 / 63,441 |
| leaves / parents | 9,177 / 3,711 |
| closed ledger commits | 164,195 (derived cap `max_delta_entries` 669,436, measured from 37,117 commits / 7,035 atoms, margin 2.0) |
| peak RAM | parent 8,489.1 MiB (~8.5 GB) / child 7,169.2 MiB; transient tree 9,700.9 MiB at t≈3,097 s (restart window); mem floor 3 GB |
| retained disk | 3,058,624,883 B (2.85 GiB) |
| kill + restart | writer kill + restart phase 516.5 s; repair converged 5,847 → 0 |
| readers | 2 threads, 27,796 requests, p50 74.7 ms |
| F1 fresh frontier | 33 probes, all within 5 s; p50 96.8 ms, p95 115.5 ms; ack→query 0.114 s |
| hardware | shared VM, solo CPUs 0–1, `nice 19`, single-thread BLAS, numpy 2.5.3 |
| sources | 253 frozen files, re-verified 0-diff; probes `b332d62d…`; harness `9f78479a…`; 164,195 final commits |

### Conditions (non-reference, read before comparing)

- Experimental derived cap (delta 669,436), not default product caps.
- Shared-VM walls (solo CPUs 0–1, single-thread BLAS); timing is not a
  reference benchmark.
- Corpus: VM-side staged cache (10M-token slice of `docs-100m.jsonl`);
  the corpus does NOT ship in this repo (see REPRO.md).
- One measured run on one VM. Larger scales are roadmap, not measured.

## Staged byte artifacts in this repo (earlier freeze — identity note)

`freeze-src/`, `receipts/`, and `docs/explorer/*.json` still stage
earlier-freeze bytes (207-file candidate, its own pins and walls).
Corpus scale and graph counts match the latest run
(10,003,381 tokens / 13,081 docs; 3,711 parents / 9,177 leaves /
63,441 atoms). The statistics above — not the staged bytes — are the
latest measured run.

## Negative findings (kept, not buried)

- Drain throughput is the scaling risk: remaining drain under readers
  took 4,654.4 s (49.0% of wall); initial drain took 999.4 s.
- Repair is real work: `repair_to_zero` took 1,162.1 s (12.2% of wall)
  over 6 iterations, 5,847 → 0.
- Scope honesty: experimental caps, shared-VM walls, 120-probe eval. NOT a
  TRACE capability claim. Shipping/default adoption and
  protocol/acceptance changes are user-owned.
