# Cloud 10K Shadow Spec (Cortex Consolidation, DeepSeek Flash)

- **Status:** DRAFT SPEC — pending Human GC-ballot authorization (shares ballot §6 with `CLOUD_1K_CALIBRATION_PACKET.md`). No spend, no provider calls executed.
- **Lane:** CORTEX shadow only. Core ingestion of the full 10K shard stays local-only, zero LLM in transaction (CAP-D003 preserved).
- **Predecessor:** 1K calibration packet must have complete receipts first (its numbers set the 10K sampling + cost priors).

## 1. Frozen inputs

- **Source capsule:** same frozen 100K capsule (`corpus_manifest.json`, Merkle `38d1a1cf…`, prefix-slice policy).
- **10K shard derivation (10% scale, exact):**

| Dataset | 100K count | 10K shard range | Docs |
|---|---|---|---|
| musique | 80,000 | `[0, 8000)` | 8,000 |
| beir-fiqa | 10,575 | `[0, 1058)` | 1,058 |
| beir-scifact | 5,183 | `[0, 518)` | 518 |
| beir-nfcorpus | 3,633 | `[0, 363)` | 363 |
| multihop-rag | 609 | `[0, 61)` | 61 |
| **Total** | **100,000** | | **10,000** |

- **Core phase (local, all 10K docs):** ingest → atomize → Spine WAL commit. Record docs/sec, tokens/s, atoms/s,
  peak RSS, storage. Hot-path acceptance stays local-gated (≥800 docs/s target per DAG CAP-INT01).
- **Cortex phase (cloud, sampled window):** consolidate a frozen coverage window of **2,000 clusters**
  (~6.8K docs equivalent at ~2.28 atoms/doc, 3 atoms/cluster) drawn by deterministic stride over the shard order
  (seed 42). Full-10K consolidation is explicitly out of scope (cost/wall, see §3).
- **Model + prompt:** identical pins to the 1K packet (DeepSeek Flash 0731; prompt `f691a6c9…`; decoding/key/cap freeze items carry over).

## 1b. Generation cap policy (frozen for 10K)

- `max_tokens` floor **8192** for all 10K cloud calls. Rationale: the cap is one shared completion budget
  covering `<think>` reasoning + JSON (output-only enforcement is unavailable on this endpoint); truncation at
  2048/4096 was a measured score-killer (48 truncated clusters in 1K). The safety case rests on temp 0, fixed
  prompt, 90s timeout, and the $25 spend cap — not on a tight token leash.
- **Think-metering required:** runner records pre-strip reasoning length per cluster; cap sized from observed
  P99 reasoning + P99 JSON + margin in the 10K dossier.
- Per-cluster receipt must carry `finish_reason`, cap value, attempt number, and retry feedback (per M2 forward fix).

## 2. Shadow lifecycle checks (the point of 10K)

1. Ingestion throughput not degraded while consolidation jobs queue behind it (queue depth cap 5,000; halt + alert above).
2. Crash/restart drill mid-consolidation: zero lost events, zero duplicate cluster work (WAL watermark resume).
3. All projections remain candidate-shadow until detached validation passes; journaled pointer-swap activation
   for low-risk summaries only; predecessor release retained for rollback.
4. Retrieval uplift vs extractive control reported paired (same frozen query subset, bootstrap CIs) — informative,
   non-promoting.

## 3. Sizing math (measured priors)

| Item | Estimate |
|---|---|
| Cloud consolidation (2,000-cluster window) | ≈$2.75, ≈6 h sequential (concurrency reduces) |
| 1K + 10K cloud subtotal | ≈$3.95 + anchor re-run ≈ **under $5** |
| Recommended ballot cap (headroom for retries/re-validation) | **≤$25** (unchanged) |

## 4. Acceptance (diagnostic, non-promoting)

- Complete Core dossier (ingest rate, RSS, storage split Spine vs projections) + complete cloud receipts for the
  2,000-cluster window + shadow-lifecycle receipts (crash drill, pointer swap, rollback).
- Report: faithfulness point + 95% CI for both binding (grounding-given-valid) and sensitivity (fail-closed)
  metrics, validity rate, cost/compute ledger.
- Independent VER recompute matches; VER-GD closes before the GD ballot. Nothing promotes under any outcome.
