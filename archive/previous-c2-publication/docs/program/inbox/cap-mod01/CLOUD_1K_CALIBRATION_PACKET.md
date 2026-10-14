# Cloud 1K Calibration Packet (Cortex Consolidation, DeepSeek Flash)

- **Status:** FROZEN SPEC — pending Human GC-ballot authorization. No spend, no provider calls executed under this packet.
- **Lane:** CORTEX only. Core ingestion for the shard stays local-only, zero LLM in transaction (CAP-D003 preserved).
- **Parent goal:** 1K calibration + 10K shadow on authorized cloud consolidator; arch/math foreground; VER-GC/GD quarantined in background; zero promotion until ballots.

## 1. Frozen inputs

- **Source capsule:** `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json`
  (`FROZEN_APPROVED`, selection Merkle root `38d1a1cf980d447edef7bfaa1ebc4d06129386a82bdd2c6f724f45d8624fc530`,
  selection policy: deterministic zero-indexed contiguous prefix slicing `[0:N]` per dataset).
- **1K shard derivation (same policy, 1% scale):** prefix-slice per dataset from the frozen capsule order:

| Dataset | 100K count | 1K shard range |
|---|---|---|
| musique | 80,000 | `[0, 800)` |
| beir-fiqa | 10,575 | `[0, 106)` |
| beir-scifact | 5,183 | `[0, 52)` |
| beir-nfcorpus | 3,633 | `[0, 36)` |
| multihop-rag | 609 | `[0, 6)` |
| **Total** | **100,000** | **1,000 docs** |

- **Cluster assembly:** 3-atom bounded-neighborhood clusters over the shard (≈760 clusters at ~2.28 atoms/doc).
  FREEZE ITEM: pin the exact assembler code path + commit before execution (recommended: the path that built
  `bakeoff_clusters_v1.json`, manifest `042b78a7b730…`, identified and pinned, not re-described from memory).
- **Reference eval (comparability anchor):** re-run the frozen 100 clusters (`bakeoff_clusters_v1.json`) under this
  packet's pinned prompt/model first, so the 1K numbers dock to the measured 0.9615 baseline.
- **Independent recompute (2026-09-05, detached bootstrap, seed 42, B=10,000, /tmp scratch):**
  fail-closed 0.9615 [0.9363, 0.9789], grounding-given-valid 0.9712 [0.9601, 0.9813], validity 0.9900 —
  matches `model_bakeoff_report.json` to all 4 decimals. Anchor baseline confirmed independently reproducible.

## 2. Model + prompt pin (verified this session)

- **Model:** `deepseek-ai/DeepSeek-V4-Flash-0731` via Sail Research (`https://api.sailresearch.com/v1`).
- **Prompt:** `improved-grounding-fewshot-v2`, SHA-256 `f691a6c93471771cd4c70e3f6bdecf063a5db16e4ba0177b86ba3ac594d11f36`
  (recomputed from `benchmarks/run_deepseek_flash_bakeoff.py` `SYSTEM_PROMPT_IMPROVED` — matches receipt).
- FREEZE ITEMS before execution: decoding params (temperature/top-p/seed as recorded in raw receipts), key custody
  (fresh Sail key; unknown-provenance `.env` values stay ROTATE/untouched, never written to receipts),
  spend cap (recommended ≤$25 for 1K + 10K-sampled window incl. retries/re-validation, metered per gate).

## 3. Sizing math (measured, 100-cluster run)

| Quantity | Measured | 1K projection (≈760 clusters + 100 anchor) |
|---|---|---|
| Tokens/cluster | ~1,237 in / ~944 out | ~1.06M in / ~0.81M out |
| Cost | $1.3727 / 1K holons | **≈$1.20** |
| Wall (sequential) | 1,071 s / 100 clusters, P95 13.1 s | **≈2.5 h** (concurrency reduces) |

- 10K preview: full local Core ingest + *sampled* cloud consolidation window (e.g. ~2K clusters ≈ $2.75),
  not full-10K consolidation (~7.6K clusters ≈ $10.40, ~22 h sequential). Coverage target frozen at ballot.

## 4. Metric rule (recommended binding for ballot)

- **Binding:** grounding-given-valid — measured 0.9712, 95% CI [0.9601, 0.9813] (lower bound clears 0.95).
- **Reported alongside:** validity rate (measured 99.0%) and fail-closed composite (0.9615 [0.9363, 0.9789]) as sensitivity.
- **Rationale:** fail-closed conflates schema packaging with grounding; the disentangled pair is the honest
  fitness signal for the Tier 2/3 activation job, and matches the plan's 100%-anchor + support-rate intent.
- **1K success criterion (diagnostic, non-promoting):** complete receipts + independent VER recompute matches;
  report point + CI for both metrics. No promotion attaches to this packet under any outcome.

## 5. Quarantine + background verification

- Outputs to a detached directory only (never `cap-mod01/` artifacts, never Spine/Cortex stores); `run_cognitive_delta` stays disabled.
- Background (non-blocking to arch/math work): VER-GC recompute of the 1K receipts, crash/restart drill on the
  shadow job worker, EVAL03 validator cross-check (generator-independence per DEC-CAP-LLM-EVAL-MODELS).
- VER-GC must still close before the GC ballot; quarantined 1K outputs cannot promote anything.

## 6. Ballot asks (GC)

1. Ratify §4 metric rule. 2. Scope selection to the cloud-prompt track for 1K/10K (prompt fork acknowledged;
   local track stays open, no mixed-prompt comparison). 3. Authorize spend cap ≤$25 + key custody.
4. Approve §1 shard derivation + assembler pin. 5. Approve provisional quarantined execution (1K may run on raw
   receipts before VER-GC closes; promotion still gated).
