# Phase A Windows run prompt (paste into a Windows agent CLI)

> SUPERSEDED — Phase A (Tiers 0-5 local-only, no runner edits) is complete as far as it goes.
> Active plan is now `PHASE_B_FINALISTS_PLAN.md`: finalists only (`gemma4:26b`, `qwen3.8:27b`, `deepseek-v4-flash`),
> Tiers 1-3 retired, skeleton-only GBNF schema for local models. Paste `PHASE_B_WINDOWS_AGENT_PROMPT.md`
> into the Windows agent CLI instead. This file is preserved as evidence; do not use it for new runs.

You are the Phase A runner for TRACE-CAP-001 Wave C (CAP-MOD01 redo).
Work in exactly this repo: `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace`
(`cap-mod01-bakeoff` state; runner already repaired — see below).

## Absolute rules (violations fail the node)

1. **No cloud. No keys.** Phase A is local-only. The DeepSeek teacher stays
   ABSENT. Never read, print, use, or rely on any key-like value in `.env`
   (unknown provenance — flag as ROTATE, never touch it). Never write any key
   to disk, logs, or receipts.
2. **Do not edit the runner.** `benchmarks/run_model_bakeoff.py` already has:
   hardcoded teacher + ladder DELETED, Tier 5 `gemma4:26b` dropped from
   `TIER_CONFIG`, fail-closed invalid-cluster scoring (invalid = 0.0; zero
   valid clusters = 0.0 `[0.0, 0.0]`, never clears the floor), and a verifier
   that FAILs on partial coverage or teacher presence. If it crashes, paste
   the traceback back — do not patch around it.
3. **Detached artifacts only.** All outputs go to
   `docs/program/inbox/cap-mod01/`. Zero writes to Spine/Cortex stores;
   `run_cognitive_delta` stays disabled.
4. **STOP after Phase A.** Do not run any teacher comparator, do not start
   MOD02, do not commit anything. Report back and halt.

## Steps

1. Preflight (DEC invariant — do this first, paste the output):
   `ollama --version`, confirm the Ollama app/serving is up
   (`curl http://127.0.0.1:11434/api/tags` must answer), and
   `ollama list` must show all four weights:
   `gemma4:e4b`, `qwen3:8b`, `gemma4:12b`, `qwen3.8:27b`.
   If any weight is missing, STOP and report which — do not substitute
   another tag.
2. Run (double-click `run_phaseA_bakeoff.bat` in this folder, or equivalently):
   `python benchmarks\run_model_bakeoff.py --manifest docs\program\inbox\cap-mod01\bakeoff_clusters_v1.json --clusters 100 --offline-local-only`
   Expect ~5h on the RTX 5050 (charger connected, machine kept awake).
   Progress streams to console and `docs/program/inbox/cap-mod01/progress.json`.
3. Verify:
   `python benchmarks\run_model_bakeoff.py --manifest docs\program\inbox\cap-mod01\bakeoff_clusters_v1.json --verify-receipt`
   It must exit 0. If it FAILs, paste every error line back — do not rerun
   with different flags to make it pass.
4. Report back (paste verbatim, no paraphrase):
   coverage per tier (expect 100/100), per-tier faithfulness point + 95% CI +
   CI width, warm tok/s, invalid-output rate, wall time, API spend (expect
   $0.00), the champion + rationale, and the full verify output.

Reference: the failed 1-cluster pilot is preserved under
`docs/program/inbox/cap-mod01/attempt1_pilot_1cluster/` (evidence only).
