# Cloud 1K R1 Retry Prompt (paste into agy CLI at repo root)

You are the R1 retry runner for TRACE-CAP-001. Work in exactly this repo:
`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace`.
Normative specs (read first, they outrank this prompt on any conflict):
`docs/program/inbox/cap-mod01/METRIC_AMENDMENT_M2.md` (§M2 rules + §R1 protocol),
`docs/program/inbox/cap-mod01/GC_BALLOT_RECEIPT.md` (ballot + Amendments A1–A2),
`docs/program/inbox/cap-mod01/MODEL_PROMPT_REVISION_PIN.json`.

## Absolute rules (violations fail the run)

1. **Key custody.** `SAIL_API_KEY` process env only. Never `--api-key`, never `.env`, never echo, never in artifacts.
2. **Spend cap.** Cumulative cloud spend so far is $0.9151; cap is $25.00. This retry pass budgets ≈$0.30. Halt before any call breaching the cap.
3. **Quarantine.** Outputs to `docs/program/inbox/cap-mod01-cloud-1k/run-1k-r1/` only. Zero Spine/Cortex writes,
   zero edits to existing artifacts (read `run-1k/` and `anchor-100/`, never modify them).
4. **Minimal runner patch.** You are authorized to patch ONLY `benchmarks/run_deepseek_flash_bakeoff.py`
   (the serial runner — NOT the concurrent file, which stays untouched and unused).
   Additive changes only: new fields, new retry function, raised cap. Never change the proposition scorer,
   the bootstrap, or any recorded history. Paste `git diff --stat` plus the full diff of the runner before running.
5. **No 10K, no promotion.** Retry pass only. Halt and report.

## Step 1 — Patch (M2 + R1, exactly)

1. Default `max_tokens` 2048 → 4096 at the call site; capture per-cluster `finish_reason` (length vs stop)
   alongside tokens in the cluster record.
2. Empty output (zero extracted propositions) → `is_invalid=true` (fail-closed). Never valid-0.0.
3. Implement R1 exactly per M2 §R1: R1a truncated → one retry cap 4096 same prompt; R1b empty → one retry with
   "no scorable content, emit full holon JSON" feedback; R1c unparseable → one retry with the parse error string
   fed back, "raw JSON only". Serial only. One retry per class; record attempt number, feedback text,
   `finish_reason`, cap per attempt (additive receipt fields).
4. Sanity: `python -c "import ast; ast.parse(open('benchmarks/run_deepseek_flash_bakeoff.py').read())"`.

## Step 2 — Retry manifest

From frozen `run-1k/bakeoff_raw_results.json`, collect cluster IDs with `is_invalid=true` OR zero propositions
OR `completion_tokens >= 2048` (expect ≈286). Write a filtered copy of
`docs/program/inbox/cap-mod01-cloud-1k/clusters_1k_v1.json` with only those clusters (identical schema),
record its SHA-256 at the top of your report. Do NOT touch the original manifest.

## Step 3 — Serial retry run

`python benchmarks/run_deepseek_flash_bakeoff.py --manifest <retry-manifest> --clusters <its total> --out-dir docs/program/inbox/cap-mod01-cloud-1k/run-1k-r1`
then `--verify-receipt --out-dir` the same dir (must PASS). Serial path only — this doubles as the
concurrency-sensitivity test, so also report: rescue rate per class (R1a/R1b/R1c separately).

## Step 4 — Audits (paste all output)

(a) receipt PASS; (b) spend vs $25 cap; (c) key-leak search over the new out dir
(`SAIL_API_KEY`, `sk-`, `api_key` in filenames + contents — zero hits in ARTIFACTS required);
(d) confirm `run-1k/` and `anchor-100/` file hashes unchanged (relist + sha).

## Step 5 — Report back (verbatim, then HALT)

Rescued/total per class, merged M2 numbers (original 483 good + rescued, recomputed grounding + CI +
strict validity — show your arithmetic), total spend, wall time, all verify outputs. Then HALT.
