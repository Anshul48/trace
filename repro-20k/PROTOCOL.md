# Recorded 10M qualification protocol — stack-fork `38c66bef`

All values below are copied from the recovered receipts in
`vm-recovery/receipts/` and `vm-recovery/audit/` (hashes in `MANIFEST.json`).
Nothing here is a semantic-relevance, nDCG, BM25-quality, or SOTA claim.
Recall values are **public-harness probe recall / oracle agreement** only.

## Identity

- Source: SOURCEFREEZE.json SHA256
  `38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54`
  (207 files, schema `sup-speed-candidate-v1+fix12356-stack`); **not** a git commit.
- Harness: `tools/product_pilot.py` SHA256
  `9f516288a098eff7b2a52373ad0eaf6b9ad1664377a9f7be4f974701b8d9b1a0`.
- Stack content (BUILD-REPORT): Fix-1 pilot params/instrumentation, Fix-3
  drain budget (the measured gain), Fix-6 partition-sort bound, Fix-2
  suffix-verify serving, Fix-5 generation GC. 5 modified + 2 added files
  over the 205-file speed parent `dd543d0e…be604b`.

## Input (receipt `input.json`, identical in `source-pin.json` / audit)

- Target 10,000,000 → actual **10,003,381** TOK_V1 tokens
  (tokenizer regex `[^\W_]+`), **13,081** complete documents,
  **63,441** atoms/distinct chunks, **0** cache misses.
- Corpus: contiguous complete-document prefix of `~/beam/pkg/data/docs-100m.jsonl`
  (VM-only; `prefix_raw_sha256 afaf20a8…54238`).
- Vectors: `tl-gpu-embcache-v1` cache, FP32 little-endian, dim 384,
  **unnormalized** (cosine normalizes at scoring);
  `cache_meta_sha256 e5f9c706…9761`, `cache_index_sha256 885d31c0…23ed`,
  `used_vector_sha256 ebd46a7e…25ba`. Encoder per `meta.json`:
  `sentence-transformers/all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`,
  mean pooling, max_seq 256, fp32 (see `LICENSES-DATA-MODEL.md`).
- Probes: `receipts/probes.json` SHA256 `b332d62d…ace8` — 120 probes
  (40 `chunk` + 40 `noisy` + 40 `cross`), each a 384-dim vector with source ids.
  Probe definition: cached structural probes scored against an exact
  float64 cosine oracle over the cached FP32 vectors, matched work
  (guided vs flat score the same row budget per query).

## Run + gates

- Command profile: `--tokens 10000000 --profile vm --drain-instrument
  --drain-budget-s 5438`; CPUs 0-2, nice 19, single-thread BLAS env;
  2026-10-13T01:48:12Z → 05:24:36Z, `t10M.rc = 0`, qualification wall
  **12,973.17 s**. Store 2.87 GB; 166,457 commits (final pin
  `e8334c07-731d-4ff9-a292-8329b89c41b9:0:166457`).
- `result.json` status **PASS**; lifecycle includes ingest → drain →
  bounded repair → publish faults + SIGKILL restart (`source_recommit_count 0`)
  → repair-to-zero → pinned guided eval (all-sources + leave-source-out).
- `VM-10M-ACCEPTANCE.json`: **PASS**, hardened, `manifest_match true`,
  fixtures 121/121. `AUDIT-RESULT.json`: **VERIFIED_VM_10M_RECEIPT**.
  `ORACLE.json`: **VERIFIED_PASS_READONLY_ORACLE_REPLAY** — 240/240 queries
  exact vs an independent einsum/argpartition reference, counts match,
  store digest identical before/after (229,927 files). Oracle scope:
  closed opt-in prefetch/top-k final state; **no new semantic relevance claim**.
- Caps (experimental, *derived* for this qualification — scope ruling
  2026-10-13T06:01Z; not shipping defaults): `max_delta_entries 669436`
  (= ⌈2.0 × max(37117/7035 × 63441, 37117/4424 × 13081)⌉ from 1M-gate
  measurements), `max_dedup_rows 1000000`, `max_delta_bytes 536870912`,
  `max_intake_backlog 10000`, `max_reservations 64`, deadline 5.0 s.
- Hardware: VM `trace-build500`, n2-highmem-16 (16 vCPU, 125 GiB),
  shared-VM walls; peak RSS parent 22.6 GiB (limit 46.8 GiB);
  `mem_available` 129,638,072 → 106,903,248 (KiB, receipt units).

## Harness recall — BOTH modes, with matched-flat controls (240 = 120 × 2)

| Mode | Guided recall@10 | Matched-flat recall@10 | Mean scoring rows (guided = flat) |
|---|---:|---:|---:|
| All sources | **0.730** | 0.056 | 3,865.8 |
| Leave-source-out (LSO) | **0.476** | 0.048 | 3,836.2 |

Per family (guided / flat): all-sources chunk 0.810/0.058, noisy 0.750/0.050,
cross 0.630/0.060; LSO chunk 0.578/0.040, noisy 0.513/0.035, cross 0.338/0.070.
Guided wall p50 ≈ 33 ms/query in both modes. F1 visibility: 33/33 queries
within 5 s (p50 119 ms, p95 130 ms, max 133 ms); append ack→query 0.12 s.

## Costs and negative findings (receipted, keep visible)

- Drain dominates: ~85%+ of wall; per-doc drain cost grows ~N^1.5
  (remaining-drain phase ≈ 1.49 s/doc at 10M scale).
- Repair-to-zero: 2,234 s (~17% of qualification wall).
- Concurrent readers impose ~2× drain penalty (reader-interference phases
  in `walls_s`: append-with-readers 1,885 s, remaining-drain-with-readers 4,866 s).
- Cosine-vector caching showed no gain (recorded negative).
- Walls are shared-VM observations under experimental derived caps —
  a qualification record, not a universal latency or capability claim.

## Small-scale reproduction

`prep_small_prefix.py` + `small-prefix-20k.tar.gz` in this directory
reproduce this protocol at 20k tokens from a clean checkout (same frozen
harness, same cache bytes for that prefix; local run PASS, 41.9 s).
To re-run at 10M you would need the VM data dir hashes above
(`afaf20a8…` prefix over `docs-100m.jsonl`, cache `885d31c0…`) and
`--profile vm`; no such run was performed for this staging.
