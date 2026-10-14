# 10M benchmarks (stack fork `38c66bef`, VM `trace-build500`)

All numbers below are read verbatim from `receipts/result.json`,
`receipts/source-pin.json`, `receipts/input.json`,
`receipts/cap-derivation.json`, `receipts/VM-10M-ACCEPTANCE.json`, and
`receipts/AUDIT-RESULT.json`. Metric definitions first, then arms and
conditions. Nothing here is inferred from any other campaign (C2, M1, 186,
v10, FAST); those stay out of this repo.

## Metric definitions

| Metric | Definition | Pass bar (this run) |
|---|---|---|
| `status` | pilot verdict in `result.json` | `PASS` |
| `actual_tokens` / `complete_documents` / `atoms` | TOK_V1 regex tokenizer counts over `docs-100m.jsonl` | 10,003,381 / 13,081 / 63,441, `cache_misses 0` |
| `pending_documents`, `repair_to_zero.final_debt` | unconverged docs / residual debt after bounded repair | both `0` |
| `commits` / `dedup` / `intake` (closed ledger) | ledger counts vs derived caps | 166,457 / 166,457 / 0 < 669,436 / 1,000,000 |
| `guided_recall10` / `flat_recall10` | Two recorded modes, 120 probes each: `all_sources` (LSO off) and `leave_source_out` (LSO on); guided and flat score identical mean rows per mode (matched work) | see both-modes table below |

**Scope of these metrics:** harness recall and oracle agreement on the recorded probe protocol, measured on a shared VM under experimental derived caps. They are **not** semantic-IR quality, nDCG, a BM25 comparison, a SOTA claim, or a universal latency guarantee.
| `all_within_5s` (F1) | 33 visibility queries, ACK-return→query latency | true (p50 119 ms, p95 130 ms, max 133 ms) |
| `manifest_match` | store manifest before==after byte-equal | `true` |
| `frozen_ok` / `frozen_files` | freeze rehash of all files + harness pin | `true` / 207 |
| `121/121PASS` | shipped fixture suite in audit | all pass, no FAILED/ERROR |
| oracle `240/240` | independent einsum/argpartition replay + native guided replay | worst abs diff 0.0, 0 mismatches |

## The qualified arm (the only 10M arm in this repo)

Launch: PID 63255, 2026-10-13T01:48:12Z → 05:24:36Z, CPUs 0–2 nice 19,
`--tokens 10000000 --profile vm --drain-instrument --drain-budget-s 5438`
(`= ceil(2 × 2,719 s)` measured v8/v10 initial drain), timeout 43,200 s,
`solo` VM, `batched` drain mode, 18 publications. `runs/t10M.rc = 0`.
Audit: `VERIFIED_VM_10M_RECEIPT` 05:45:23Z; fresh-verifier concurrence
07:56Z (50/50 predicates from fetched bytes + 240/240 oracle) →
`muse-verified`. First 10M receipt; v10 (deadline-miss) and FAST (rc −15)
are separate records, not arms here.

### Phase walls (s, observed)

| Phase | Wall (s) | Share |
|---|---|---|
| ingest (visible + prepare) | 917 | 7% |
| initial drain + prepare (3 cycles) | 1,781 | 14% |
| append ingest with readers | 1,885 | 15% |
| source-capacity rejection | 1 | <1% |
| prepare rejection (fresh frontier) | 497 | 4% |
| writer kill + restart (SIGKILL, exit −9) | 710 | 5% |
| remaining drain + prepare with readers (1 cycle) | 4,866 | 38% |
| repair_to_zero (5 iters, debt 5,314 → 0) | 2,234 | 17% |
| **total qual wall** | **12,973 (~3.6 h)** | 100% |

### Both recorded probe modes (guided vs matched-flat control)

| Mode | Guided recall@10 | Flat recall@10 | Mean scoring rows (guided = flat) | Guided p50 |
|---|---:|---:|---:|---:|
| `all_sources` (LSO off) | 0.73 | 0.055833333333333325 | 3,865.775 | 0.03319 s |
| `leave_source_out` (LSO on) | 0.4758333333333333 | 0.04833333333333333 | 3,836.241666666667 | 0.03324 s |

| Family | `all_sources` guided / flat | `leave_source_out` guided / flat |
|---|---|---|
| chunk | 0.81 / 0.0575 | 0.5775 / 0.04 |
| noisy | 0.75 / 0.05 | 0.5125 / 0.035 |
| cross | 0.63 / 0.06 | 0.3375 / 0.07 |

Work budget per guided query at final state (`final.guided_query_work`):
3,711 parents scored, 18 children scored, 145 atoms scored / member visits.
Each mode: 120 probes, 120 matched-work queries.

### Scale, ledger, hardware (observed)

| Field | Value |
|---|---|
| tokens / docs / atoms / chunks | 10,003,381 / 13,081 / 63,441 / 63,441, 0 misses |
| leaves / parents / membership revisions | 9,177 / 3,711 / 12,888 |
| closed ledger commits / dedup / intake | 166,457 / 166,457 / 0 (caps 669,436 / 1,000,000; headroom 502,979 / 833,543) |
| cap derivation | `ceil(2·max(basis))` from 1M measured 37,117 commits / 7,035 atoms / 4,424 docs, margin 2.0 → 669,436 |
| peak RSS parent / child | 22,566 MiB (22.0 GiB) / 15,669 MiB (15.3 GiB); tripwire/limit 46,811,848,704 B (43.6 GiB) |
| retained disk | 2,868,578,536 B (2.87 GB / 2.67 GiB) |
| kill_resume | exit −9, `source_recommit_count 0`, retry boundary 1/1/0, `repair_budget_at_boundary 0` |
| readers | 2 threads, 15,813 + 15,812 requests (~15.8k each, 31.6k total), 0 errors |
| F1 append | ack→query 0.12 s; ingest→ack 331.7 s (post-ingest visibility) |
| hardware | GCP `n2-highmem-16` (16 vCPU, ~125 GiB), solo CPUs 0–2, `nice 19`, BLAS threads = 1, numpy 2.5.3 |
| eval | 120 probes × 2 modes (table above), guided p50 ~33 ms in both modes |
| fixtures | `121/121PASS`; oracle 240/240 exact; store before==after (229,927 files, sha `52e88439…`) |

### Conditions (non-reference, read before comparing)

- Experimental derived caps (delta 669,436), not default product caps.
- Shared-VM walls (solo CPUs 0–2, single-thread BLAS); timing is not a
  reference benchmark.
- Corpus: VM-side staged cache (`beam/pkg/data/docs-100m.jsonl` slice by
  prefix `afaf20a8…`, meta `e5f9c706…`, index `885d31c0…`, vector
  `ebd46a7e…`); the corpus does NOT ship in this repo (see REPRO.md).
- Floor asserts at audit: hostname `trace-build500`, `MemAvailable ≥ 16 GiB`,
  free disk ≥ 80 GiB, affinity {0,1,2}, WAL empty, OFD read lock.

## Supporting arms (same freeze, smaller scope — context, not qualification)

| Arm | Result (reported from comms log; receipts not staged) |
|---|---|
| 1M Fix-1-only control (CPU 2) | rc 0, 960 s; publication cost linear in store size (mechanism finding) |
| 1M stack treatment (`--drain-budget-s 200`) | rc 0, 840 s; 3→1 drain cycles, −102 s fixed of −120 s; per-pub cost unchanged; commits identical (37,117) |
| 500k/1M/2M/4M profiles | cosine plumbing 2.8× for 2× scale (~N^1.4–1.6); fsync 1.9× linear |

## Negative findings (kept, not buried)

- v10 speed arm: DEADLINE-MISS (>10 h). FAST arm: rc −15. Both preserved as
  separate attributed records in the primary workspace, not in this repo.
- Drain throughput is the 100M blocker (per-doc cost ~N^1.5); publication is
  linear and no longer the lever. Cosine cache made it slower (+28–58% with
  readers). Repair-off default path still paid 2,234 s of `repair_to_zero`.
- Scope honesty: experimental caps, shared-VM walls, 120-probe eval. NOT a
  TRACE capability claim (no "notes → clusters/contradictions/gaps").
  Shipping/default adoption and protocol/acceptance changes are user-owned.
