# RESULT — vm-trace-latency-profile-v1-r2 (2026-11-07, VM hand)

Profile of the TRACE 100M serve path (guided k=10): where the ~1.2 s per query goes.

## Headline: the split (shares measured here × live guided p50 1207 ms)

Live anchor: `vm-trace-latency-final` guided p50 1207.2 ms (embed ~14, search
~1191.5). Internal shares measured in this job (60-query sampler run, least
contended; cross-checked by cProfile run + 9903 wall samples):

| block | share of query (measured) | implied ms at live 1207 |
|---|---|---|
| engine children wall (4× `cand_serve`, sequential) | 88.8% (stage) / 91.2% (samples) | ~1070–1100 |
| ├─ in-engine compute (routing+scoring, receipt `total_us`, probe) | ~40% (probe, synthetic q) | ~480 |
| └─ spawn + HOT re-attach + npy IO gap (wall minus `total_us`, probe) | ~50% (probe) | ~600 |
| embed (MiniLM-L6-v2, CPU batch-1) | 4.5% here; 1.2% live (14 ms) | 14 (live) |
| Python nomination (`nominated_parents` ×4) | 6.4% stage / 3.6% samples | ~45–80 |
| Python search glue (valid + npy + result build) | 0.3% | ~4 |
| merge + units JSON (10 seeks + parses) | 0.03% | <1 |

Reading: the query is ~99% search; search is ~99% "parent blocked in
`communicate`/`select` waiting on engine children". In-process Python (embed +
nomination + glue) is ~5–8%. Routing-vs-scoring *inside* the engine is not
exposed by the receipt (one `total_us` per query) — UNVERIFIED, see caveats.

## Method (all read-only on the sealed store; live :8495 untouched)

- Code profiled: `Backend` from the live-service tree
  `wave2/vm-trace-query-concurrency-fix/svc/backend.py` (same class/store/model
  as pid 384358), fresh instance in our process (`-B`, no `.pyc` writes).
- Queries: 50 recorded questions
  (`trace-100m-rerun-r2/raw/questions.json`, sha256 `dc0b8958…f8a`).
- Run 1 (TIMED-200): 200 guided k=10 = 4 sequential passes, file order, whole
  loop under `cProfile`, per-query stage timers (`prof.py`). 200/200 ok, 0 err,
  wall 753.8 s. Affinity [0,1,2] (3 cores ✓), `nice -n 10` launch (effective
  nice 19 by stacking, see caveats). Loadavg 6.7–7.7 during run (shared box).
- Run 2 (FLAT-20): first 20 recorded, flat k=10, timed only. 20/20 ok.
- Run 3 (SAMPLE-60): 60 guided + SIGALRM wall sampler at 100 Hz (stdlib only,
  `stacksample.py`): 9907 alarms, 9903 captured, 4 skipped, 73 uniq stacks.
  60/60 ok, wall 101.9 s. `samples.folded` is flamegraph-compatible.
- Run 4 (ENGINE-PROBE): direct `cand_serve` on shard0 with synthetic unit
  query, Q×2 + exact×1, to read the full receipt (`total_us`, `mmap`,
  `native_tier`). Q: wall 352/271 ms, internal 121/122 ms. Exact: wall 314 ms,
  internal 168 ms. `mmap=1` all.
- py-spy: absent (`command -v py-spy` → 127) → cProfile + sampler per brief.

## Top 15 hot spots (guided k=10, per-query; triangulated)

"ms here" = stages60 run (contended, mean total 1699 ms) or cProfile run
(heavily contended, mean 3768 ms) as noted; "share" is the contention-robust
column. Sub-rows (a/b/c) decompose their parent and are not separate ranks.

| # | hot spot | evidence | ms here | share |
|---|---|---|---|---|
| 1 | engine child wall ×4 sequential (`communicate`→`select`/`poll`) | stage engine 1509.0; samples 91.2%; cProfile `poll` tt 627 s | 1509 | 88.8% |
| 1a | └ in-engine compute (`total_us` ≈121 ms/shard, Q probe) | engine receipt probe | ~484 | ~40% |
| 1b | └ spawn+attach+IO gap (fork+exec, 312 MB HOT mmap re-attach ×4, npy IO) | probe wall−`total_us` ≈150–230/shard | ~600–900 | ~50% |
| 2 | `nominated_parents` ×4: (22995,384) f32→f64 `astype` + matmul + argpartition | stage nom 108.4; cProfile `astype` tt 29.9 s /800 = 37/call; samples 3.6% | 108 (stage) | 3.6–6.4% |
| 3 | MiniLM embed fwd, CPU batch-1 (6-layer BERT + pool) | stage embed 75.7; live 14; cProfile `_inference` ct 43.2 s /200 | 76/14 live | 1–4.5% |
| 3a | └ `torch.linear` (7400 calls/200 q) | cProfile tt 24.4 s | ~122 (contended) | (of 3) |
| 3b | └ `layer_norm` + sdpa-attn + gelu | cProfile tt 7.1+3.5+3.3 s | ~70 (contended) | (of 3) |
| 4 | parent-side spawn CPU (`fork_exec` + `_execute_child`, 800 spawns) | cProfile tt 1.65 s; samples 0.3% | ~8 | 0.3–0.5% |
| 5 | query validation (2 finite-sweeps + f32-range over 384 els ×4) | samples QUERY_PREP 0.1%; cProfile `_is_finite*` | ~2 | ~0.1% |
| 6 | `npy_save_f4` query file + `npy_load` ×3 per shard (8 tmp files/q… 16 with mkstemp/out) | cProfile `npy_load` ct 0.62 s, `save` ct 1.85 s (contended) | ~12 (contended) | 0.1–0.3% |
| 7 | tmpfile churn (`mkstemp`×4–5 + `remove`×4 per shard = ~16–20 files/query) | cProfile `remove` tt 1.66 s /3200; samples `mkstemp` 0.1% | ~8 (contended) | ~0.2% |
| 8 | ST framework overhead (`named_modules` 2136/q, `isinstance` ~4950/q) | cProfile tt 0.41+0.41 s | ~4 (contended) | ~0.1% |
| 9 | `q.tolist()` + renormalize (384 f64) | stage (in embed); samples <0.1% | <1 | <0.1% |
| 10 | result build (`_sealed_row_of` + dict per hit ×40) | cProfile (below top-15 by tt) | ~1 | <0.1% |
| 11 | merge sort 40 + `_unit_at` ×10 (seek+readline+`json.loads`) + assign reads | stage merge 0.5 | 0.5 | 0.03% |
| 12 | `sa_shim._search` + `attach_search` glue (non-engine) | cProfile ct−engine ≈ 6 s /800 | ~8 (contended) | ~0.2% |
| 13 | `thread.lock acquire` (torch/sentence-transformers internals) | cProfile tt 35.6 s /602 — contention artifact | ~178 (contended) | artifact |
| 14 | file `__exit__`/close (1600/200 q) | cProfile tt 1.75 s | ~9 (contended) | ~0.2% |
| 15 | HTTP layer (parse/route/serialize) | not profiled (in-process `Backend`, no HTTP) | UNVERIFIED, prior runs ≈1–2 ms | ~0.1% |

Notes: #13 scales with box contention (futex wait), not query work — excluded
from the split. #15: service adds ~1–2 ms over in-process (prior LOAD.md);
not re-measured here.

## Flame summary (9903 wall samples @100 Hz; full stacks in `samples.folded`)

- 91.1% `timed_query → search_shard → _search → attach_search → _sealed_run →
  communicate → _communicate → selectors:select` (blocked on engine child).
- 3.5% `timed_query → nominated_parents` (numpy `astype`/matmul CPU burst).
- 2.8% BERT `linear.forward`, 0.7% `layer_norm`, 0.4% `sdpa_attention`, 0.2%
  `gelu/activations` (all under `SentenceTransformer._inference → encode`).
- 0.3% `_execute_child` (spawn), 0.2% `timed_query` glue, 0.1% `mkstemp`,
  0.1% query validation, <0.1% npy parse / units IO.
- Shards balanced: per-shard wall means 360–407 ms (run 3), 807–911 ms (run 1,
  more contended); no straggler shard. No widen-retry observed (800/800 engine
  calls first-attempt ok; `fork_exec` nc=800 exactly).

## 3 ranked engineering levers (savings are ESTIMATES, labelled E)

- **E1. Persistent warm engine pool + parallel shard fan-out.** Kills 4×
  fork+exec and 4× 312 MB HOT mmap re-attach per query, and the 4× sequential
  factor. Basis: measured spawn+attach+IO gap ~150–230 ms/shard (probe) and
  sequential shards (this job). E: persistent engines alone ≈ −600–800 ms
  (~50–65% of the 1.2 s); + parallel fan-out ≈ −70–80% combined *if ~4 cores
  free* — on this shared 4-vCPU box expect materially less. Needs engine
  protocol change (stdin/Unix-socket server instead of one-shot argv).
- **E2. Stop the per-query Python nomination recompute.** `nominated_parents`
  converts 4× 35 MB f32→f64 (283 MB/query) + 4 matmuls just for the response
  `nomination` extras, duplicating routing the engine already did. Options:
  precompute f64 cents once at load (+283 MB RAM), or f32 matmul, or reuse the
  engine's own nomination. E: ≈ −60–100 ms (~5–8% of query).
- **E3. Embed: batch / cache / quantize.** Batch-1 MiniLM on CPU is 14 ms live
  (76 ms contended here). Batch concurrent queries, cache top questions, or
  INT8/JIT the encoder. E: ≈ −10 ms live (~1%); up to −60 ms under contention
  (~4%). Small because embed is already a minor share.
- Measured non-levers (do not touch): units merge (<0.1%), npy/validation
  glue (~0.3–1%), HTTP layer (~0.1%).

## Caveats / not done / uncertain

- Absolute ms inflated by shared-box contention (load 6–7.7, ~11 other hands
  + restore running): run-1 mean 3768 ms, run-3 mean 1699 ms vs live p50
  1207 ms. Shares + sampler + probe gaps are the robust findings; implied-ms
  column assumes shares transfer (bias: CPU-bound in-process stages overstate,
  engine-wait understates — true engine share is ≥90%, live search 98.7%).
- Effective nice was 19, not 10 (`nice -n 10` stacked on inherited nice 10).
  Direction: we yielded MORE than briefed; shares unaffected in principle.
- Guided-vs-flat order reversed between run 1 (guided slower) and live box /
  engine probe (Q internal 121 ms < exact 168 ms) → run-1 flat comparison is
  contention-confounded; no routing-vs-scoring claim rests on it.
- In-engine routing-vs-scoring split: NOT exposed (receipt has one `total_us`;
  `route_backend=exact`, `ret/top` are counts) — UNVERIFIED. Needs engine-side
  timers or source read (out of scope: no `trace-architecture/` touch).
- cProfile caller map was garbled (missing `driver_loop`, self-callers —
  lsprof anomaly, see `profile_summary.json` note); worked around with
  independent stage timers + wall sampler, which reconcile. tottime/counts
  were exact multiples and trustworthy.
- HTTP layer not profiled (in-process only); tail latencies (p95/p99) are
  contention upper bounds, not engine properties.

## Files (workspace `/home/anshul/owner-hub/scratch/wave2/vm-trace-latency-profile-v1-r2/`)

- `prof.py` (new): stage-timed + cProfile driver (venv python, `-B`).
- `stacksample.py` (new): SIGALRM wall sampler, 100 Hz, 60 queries.
- `analyze.py` (new): stdlib analysis (stages, pstats top-15, buckets, flame).
- `test_prof.py` (new): hermetic unittest, 19 tests.
- `stages.tsv` (200 guided rows), `stages_flat.tsv` (20), `stages60.tsv` (60),
  `cprof.pstats`, `samples.json`, `samples.folded`, `run_meta.json`,
  `meta60.json`, `profile_summary.json`, `profile_summary60.json`,
  `run.log`, `run60.log` (evidence).
- Outbox copy: `/home/anshul/owner-hub/coord/outbox/vm-trace-latency-profile-v1-r2.result.md` (mode 600).

## Tests as actually run

- `python3 -W error::ResourceWarning -m unittest test_prof`: 19/19 OK (system
  python3, hermetic; run 3×, last after final edit: OK).
- Profiler smoke (1 guided query, venv python): ok, total 1262 ms.
- TIMED-200: 200/200 ok, 0 err. FLAT-20: 20/20 ok. SAMPLE-60: 60/60 ok,
  9903/9907 alarms captured.
