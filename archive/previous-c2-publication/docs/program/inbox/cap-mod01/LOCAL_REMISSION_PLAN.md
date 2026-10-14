# Plan: Local Remission, Fresh Matrix (Think-Max, Pilot-Then-Full)

## Goal

Measure every viable local tier fresh — clarified few-shot prompt, thinking dials to max where supported —
pilot 10 clusters per model for early signal, then the remaining 90, and route per pre-committed thresholds.

## Success Criteria

- Per tier (Gemma-4B, Qwen-8B, Gemma-12B): pilot-10 receipts + full-90 receipts, combined frozen-100 numbers,
  same scorer, M2 triple reporting, all receipts verifying PASS.
- Think-max effect recorded per tier (setting actually applied, think-token share where measurable).
- GC routing executed mechanically per pre-commit. DeepSeek-only 10K untouched until that routing.

## Context And Current Facts

- Old baselines (old prompt, think off): Gemma-4B 0.6030, Qwen-8B 0.7237 — retained as history only, NOT
  comparison arms. This matrix starts afresh: identical treatment for all tiers.
- Local runner already defaults `num_predict=8192`, `num_ctx=16384`, temp 0.0, strips think blocks — deltas are
  the clarified-prompt constant, think toggle parameterized to max, and a new prompt-revision hash record.
- Runs execute Windows-side (Ollama app + bridge); agy prompt targets Windows agent CLI.
- Measured think-off pace ≈150 s/cluster on 8B (≈25 min per pilot-10, ≈4 h per full-100); think-max slower —
  pilot exists so a dead tier shows itself in under an hour before the overnight burns.

## Constraints And Non-goals

- Frozen 100 per tier, split identically: pilot = clusters 001–010, completion = 011–100. Same scorer, M2
  reporting, no formula changes. Pilot numbers are directional only — no champion, no routing off the pilot.
- Local 0.95 floor retained. No threshold edits. No 10K/100K local consolidation, no NLI build.
- 27B excluded: measured 0.0 tok/s on 8 GB VRAM (cannot load). Preflight `ollama list` must show the three
  tiers or the run halts before spending GPU-hours.

## Key Decisions

1. **Fresh matrix, three tiers, think max.** gemma4:e4b, qwen3:8b, gemma4:12b — clarified prompt + thinking to
   max/xhigh wherever the tier supports it; record the actual applied setting per tier (a non-thinking tier
   runs at its max available setting, labeled, not forced). Rejected: carrying old-prompt arms forward (mixed
   treatments can't share a denominator) and 27B (hardware-bound).
2. **Pilot-then-full per tier, sequentially.** 10-cluster pilot first for prior understanding; 90-cluster
   completion only if the tier isn't dead on arrival (pilot grounding <0.50 or validity <50% retires the tier
   with receipts kept). Combined score always over the full frozen 100.
3. **Outcome routing pre-committed:** any tier ≥0.95 → GC ballot on local champion/cascade (reopens A2);
   best tier 0.90–0.95 → local-first cascade dossier; all <0.90 → local stays fallback, DeepSeek-only stands.

## Recommended Approach

One reviewed runner patch (prompt constant + think parameterization + hash record), then per tier: preflight,
pilot-10, gate check, full-90 overnight, verify. Qwen-8B first (primary), Gemma-12B second, Gemma-4B last
(cheapest, weakest signal — runs while 8B arms occupy nights).

## Work Plan

1. **Patch + record** (reviewed): clarified prompt as parallel constant (old bytes untouched); think flag
   parameterized (max/on per tier capability); new prompt-revision SHA recorded; `git diff` pasted pre-run.
2. **Preflight per tier**: `ollama list` shows the weight; 1-cluster smoke (cluster_001) returns valid JSON.
3. **Pilot-10** (clusters 001–010, identical set all tiers): run, verify-receipt PASS, report M2 triple + pace
   extrapolation. Gate: grounding <0.50 or validity <50% retires the tier.
4. **Full-90** (clusters 011–100, surviving tiers): overnight run, verify-receipt PASS, combined-100 M2 numbers.
5. **Dossier + routing**: per-tier pilot-vs-full consistency check (pilot within full CI, else flag drift),
   Pareto vs DeepSeek snapshot (grounding, $0 cost, privacy, reproducibility), GC routing per pre-commit.

## Validation Plan

- Unit 1: diff shows prompt + think parameterization + hash record only.
- Units 3–4: coverage exactly 10 then 90, union exactly the frozen 100, no overlap; receipts PASS; $0.00 spend.
- Pilot-full consistency: pilot point inside full-100 95% CI, else the tier's numbers carry a drift flag.
- Highest-risk validation: think-max output discipline — reasoning tokens share the `num_predict` budget, so
  record think share; truncation under think-max is a cap event (retry/raise), never a grounding score.
- Champion claims cite lower CI too; nothing routes off pilot numbers alone.

## Risks / Rollback

- **Think-max 3× slower:** pilot bounds the damage — dead tiers retire after ~1 h, survivors earn overnights.
- **Ollama OOM (12B):** retire the tier with the hardware bound recorded; remaining tiers stand.
- **Rollback:** `git checkout` the runner; receipts are additive quarantined dirs.

## Open Questions

None. Tiers, pace, flags, split, and thresholds verified or owner-directed this session.
