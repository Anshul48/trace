# CONFIG.md — budgets, protocol, deployment conditions

## Serving budgets

M80-P100-A40 everywhere (M_REGIONS=80, PRUNE_CAP=100, MAX_ENTRIES=40),
except the frozen scale10m rung (M_REGIONS=20, Narrow release 4c8c9673)
and the A2 k100 diagnostic (MAX_ENTRIES=100, otherwise identical to A1).

## Measurement protocol (BENCH10M, all 5 lanes)

- `--top-k 100 --concurrency 1`, TB defaults otherwise (`warmup 0`,
  linear nDCG gain, official splits).
- Compares: static mode, paired percentile bootstrap (2000 samples,
  seed 42), two-sided paired t-test, no multiple-comparison correction.
- Empties (bm25's 25 on nfcorpus) scored at zero per TB, recorded as
  empty — never fabricated, never dropped from the denominator.

## Deployment condition (part of the release)

Persistent serving process + resident MiniLM encoder:

| condition | measured | vs 5 s gate |
|---|---|---|
| warm query | 1620–2358 ms | PASS |
| storage-cold query | 3530 ms | PASS |
| fresh-process first request | ~8–10 s | EXCEEDS (voids latency claims outside the condition; correctness stands) |

10M-store attach cost (A3 probe, two independent runs agree): serving a
query on the resident store takes ~0.8–1.4 s; (re)attaching the
NarrowIndex takes ~103–122 s and dominates every cold-attach request.
No storage-cold sample (`drop_caches` not authorized) — page-cache
state unrecorded, so these are warm-cache observations. 5/5 requests
complete, 40/40 entries, at pin `:0:95436`.

## 10M gate eval protocol

Frozen queries: `queries-10m.json` (`77336d62…`, inputs id
`gate-10m-inputs-v3`, frozen BEFORE results). Confirmation fixtures:
`CONFIRM-INPUTS.v3-10m.json` (`ece682c7…`, newly authored `gatefx-*`
ids). Grounding rule, chunker (`CHUNK_TOKENS=200`, overlap 50), and
tokenizer (TOK-v1) are recorded inside those files and in
`c10m/data/inputs/corpus-manifest-10m.json`.
