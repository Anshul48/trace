# LOAD.md — vm-trace-query-service measurements

Labels: M = measured by this hand on the VM. Env: Azure VM, 4 vCPU / 32 GiB
(shared, restore + other hands active), service at nice 10 in user scope
`vm-trace-query-service.scope` (MemoryMax=12G), torch 2 threads, sequential
4-shard fan-out. Retrieval = exact S8 path (`sa_shim.attach_sealed` +
`ns["search"]`, profile Q guided / exact flat, `tools/tree/cand_serve`,
route exact); encoder = staged all-MiniLM-L6-v2 rev 1110a24, offline CPU,
normalize_embeddings=True.

## Cold start (M)

- 8.8 s fresh process (`/health` cold_start_s 8.77; backend-direct reload 8.8).
  Covers: ST encoder load + 4 sealed attaches (meta.jsonl parse each) +
  812,545-line unit offset index + row0/ordinal self-check x4.
- Note: page cache was warm (build had been touched minutes earlier); a
  truly cold boot from disk may be slower. UNVERIFIED beyond the two runs.

## RAM (M)

- Scope MemoryPeak 951,730,176 B (~0.91 GiB) after full 50-question eval.
- Service process VmHWM 1,083,680 KiB (~1.03 GiB), VmRSS ~0.96 GiB.
- Headroom: 12 GiB cap enforced by scope; box had ~29 GiB available.

## Latency over 50 varied real questions (M)

Set: `eval_questions.json` — 10 S8 qpool probes (text[:48] prefixes, filed
ordinals) + 40 authored natural/keyword questions across all 4 shards.
Each asked once via HTTP GET /query, guided, k=10 (`eval_results.json`).

- End-to-end wall: p50 1238 ms, p95 1276 ms, max 1306 ms (n=50).
- Server embed: p50 17.7 ms, max 21.7 ms.
- Server search (4 shards sequential): p50 1218 ms, max 1286 ms.
- Single flat sanity query (k=3): 1343 ms total; guided k=3: 1893 ms
  (flat can beat guided on small k — straight scan vs nomination overhead).

## Recall: 10 S8 probes vs receipt (M)

Backend-direct through the same `Backend.search_shard` /query calls, GT via
the build's own `gt_exact` f64 module (S8 methodology), k=100, per shard
(`eval_recall.json`).

- Guided-Q vs f64 GT recall@10: mean 1.0000, min 1.000 (40/40 cells).
  Receipt (200 Q/shard): 0.9975 / 0.9975 / 0.999 / 0.9975. Consistent: a
  10-probe subset landing all-perfect is expected at ~0.5% miss rate.
- Guided-Q vs f64 GT recall@100: mean 0.9915, min 0.930 (receipt s0: 0.98985).
- Flat arm vs f64 GT recall@10: 1.0000 (sanity: flat == GT on this subset).
- Merged (cross-shard top-10) guided-vs-flat overlap@10 via HTTP: 1.000
  on all 10 probes.
- Source ordinal in merged top-10: 5/10 guided AND 5/10 flat, identical sets.
  The 5 misses are a prefix-query/corpus property (48-char title-prefix
  embedding vs full-unit embedding over 812k units), not a guided-vs-flat
  gap — both arms return the same top-10. S8 probes were designed for
  guided-vs-exact agreement, not source retrieval.

## CPU embed throughput (M)

- 50 sequential batch-1 encodes of the filed questions: 0.7 s wall =
  75.7 q/s (13 ms/q mean), torch 2 threads, nice 10, warm encoder.
- Embed is ~1.4% of per-query latency; search dominates.

## Not measured (UNVERIFIED)

- Concurrent-load latency (cap is 4, returns 429 past it; soak not run).
- Tailnet-remote latency (tailscale logged out; localhost only).
- Truly-cold-disk boot time.
