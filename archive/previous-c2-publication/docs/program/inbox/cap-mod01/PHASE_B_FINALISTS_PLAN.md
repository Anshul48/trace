# Phase B Finalists Plan (CAP-MOD01 redo, local + teacher)

Status: ACTIVE. Supersedes Phase A scope (Tiers 0-5 all-model sweep).

## 1. Model decision (locked)

Active finalists only:

- `gemma4:26b` (26B MoE, local) — speed pick. ~19.9 tok/s, 0/10 invalid so far, ~0.93 avg grounding on completed clusters (`bakeoff_checkpoint.json`, `progress.json`).
- `qwen3.8:27b` (27B dense, local) — accuracy anchor. 0/15 invalid so far, ~0.93 avg, ~3.7 tok/s.
- `deepseek-v4-flash` (236B MoE, cloud teacher comparator) — upper bound. 0.9615 fail-closed / 0.9712 grounding-given-valid, 99% validity, independently reproduced (`CLOUD_1K_CALIBRATION_PACKET.md` §1). No rerun.

Retired (do not run, do not fix):

- Tier 1 `gemma4:e4b`: 0.6030 overall, 30% invalid, ~0.861 conditional. GBNF ceiling ~0.86 < 0.95 floor.
- Tier 2 `qwen3:8b`: 0.7237 overall, 19% invalid, ~0.893 conditional. GBNF ceiling ~0.89 < 0.95 floor. Slower than 26B MoE anyway (7.3 vs 19.9 tok/s).
- Tier 3 `gemma4:12b`: 0.5801 overall, 24% invalid, ~0.76 conditional. Worst of both.
- Tier 0 `extractive_control` stays as a detached reference number only (0.9971 lexical copy baseline). Not a candidate, never runs again.

Rationale: light-model gap is semantic (paraphrase/glue penalty), not just JSON syntax. GBNF cannot close 0.86-0.89 to 0.95. 26B MoE dominates 8B on both quality and speed.

## 2. Local-model changes (minimal, transport-only)

Apply to `benchmarks/run_model_bakeoff.py` Ollama call only. Prompt text stays byte-identical (local track prompt frozen; cloud prompt fork already acknowledged in `CLOUD_1K_CALIBRATION_PACKET.md` §6):

1. Skeleton-only GBNF schema: replace `"format": "json"` with a JSON-schema dict for the Holon object (keys/arrays/types + `required`, derived from the runner's own parser — reference skeleton in the agent prompt). No `pattern`/`regex` on inner text fields.
2. `options`: `temperature 0.0`, `num_predict 1536` (floor; 2048 acceptable).
3. Keep everything else frozen: fail-closed invalid=0.0 scoring, verifier completeness checks, detached outputs to `docs/program/inbox/cap-mod01/`, `run_cognitive_delta` disabled.
4. Explicitly OUT: LoRA, task decomposition, definition-injection pre-pass, prompt rewording.

Why still add schema when 26B/27B show 0% invalid: insurance. One malformed overnight cluster = dropped day. Cost is one config change + ~5-10% TPS.

## 3. Experiments to run

- B1 (local, schema on): resume `gemma4:26b` 10→100 and `qwen3.8:27b` 10→100 (use `--cluster-start 10 --cluster-end 100 --resume` so already-done clusters are kept; back up `bakeoff_checkpoint.json` first as the pre-schema baseline). 26B first (~1h remaining), then 27B (~6h). Charger connected, machine awake.
- B2 (verify + report): `--verify-receipt` must exit 0. Report per model: coverage, fail-closed point + 95% CI + width, grounding-given-valid (conditional), validity/invalid rate, warm tok/s, P95 latency, wall time, $0.00 spend. Pre/post-schema split noted (clusters 0-10/15 pre-schema baseline preserved in backup).
- B3 (teacher): no run. Anchor numbers stand.
- B4 (DEFERRED, decision after B2): Entity-Grounding Pre-Pass limited to ID-only sidecar (alias table, internal-acronym expansion, cosine cohesion filter refusing incoherent merges) + allowlist metric variant (`allowed = atom_words ∪ matched glossary terms`) tested on real jargon-heavy notes — NOT on the Wikipedia bakeoff clusters. No definitions injected under the current lexical metric. No code in Phase B.

## 4. Success criteria

- 100/100 coverage on both local finalists, receipt PASS, $0.00 local spend.
- Selection by smallest-passing rule on fail-closed score, with conditional grounding reported alongside (per `CLOUD_1K_CALIBRATION_PACKET.md` §4 rationale).
- No Tier 1-3 reruns, no teacher calls, no Spine/Cortex writes, no commits.
