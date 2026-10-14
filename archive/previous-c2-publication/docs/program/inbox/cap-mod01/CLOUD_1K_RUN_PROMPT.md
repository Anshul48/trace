# Cloud 1K Run Prompt (paste into agy CLI at repo root)

You are the cloud 1K runner for TRACE-CAP-001 (Cortex calibration on authorized cloud consolidator).
Work in exactly this repo: `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace`.
Normative specs (read first, they outrank this prompt on any conflict):
`docs/program/inbox/cap-mod01/CLOUD_1K_CALIBRATION_PACKET.md`,
`docs/program/inbox/cap-mod01/GC_BALLOT_RECEIPT.md`,
`docs/program/inbox/cap-mod01/MODEL_PROMPT_REVISION_PIN.json`.

## Absolute rules (violations fail the run)

1. **Key custody.** Fresh Sail key via `SAIL_API_KEY` process env only (`$env:SAIL_API_KEY="..."` in your
   shell, never persisted). Never pass `--api-key` (leaks to history), never read/write `.env` for keys,
   never echo the key, never let it into any artifact, log, or receipt.
2. **Spend cap.** Halt before any call that would push cumulative 1K spend past $25. Report running spend after each phase.
3. **Quarantine.** All outputs to `docs/program/inbox/cap-mod01-cloud-1k/` (create it; anchor run under
   `anchor-100/`, 1K run under `run-1k/`). Zero writes to Spine/Cortex stores, zero writes to `cap-mod01/`
   artifacts, `run_cognitive_delta` stays disabled.
4. **No promotion.** This run is diagnostic under the ballot receipt. Do not start 10K, MOD02, or any gate dossier. Halt and report.
5. **Do not edit the runner.** `benchmarks/run_deepseek_flash_bakeoff.py` is frozen. On crash, paste the traceback and halt.

## Steps

0. **Preflight (paste all output):**
   `python --version`,
   `python benchmarks/run_deepseek_flash_bakeoff.py --check-key` (must print key-valid; else HALT),
   confirm `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json` exists.
1. **Anchor re-run (comparability):**
   `python benchmarks/run_deepseek_flash_bakeoff.py --manifest docs/program/inbox/cap-mod01/bakeoff_clusters_v1.json --clusters 100 --out-dir docs/program/inbox/cap-mod01-cloud-1k/anchor-100`
   then `--verify-receipt --out-dir` the same dir (must print PASS). Expect ≈$0.14, ≈18 min.
2. **Phase 0 local (Core, zero LLM):** derive the 1K shard doc IDs per the packet §1 table from the frozen capsule
   order; atomize each doc with `src/trace/v2/atomizer.py::atomize` defaults; group atoms into contiguous triples
   in shard order (seed 42); write `clusters_1k_v1.json` mirroring `bakeoff_clusters_v1.json` schema exactly
   (same top-level keys; each atom keeps node/atom-version/workspace IDs, content, content_hash).
   Record assembler identity (file + function + params + seed) at the top of your report. HALT if atom count
   deviates from ≈2,280 by more than 15% — report, do not improvise.
3. **Phase 1 cloud:** same command shape as step 1 with `--manifest <clusters_1k_v1.json path> --clusters <its total>
   --out-dir docs/program/inbox/cap-mod01-cloud-1k/run-1k`, then verify-receipt on that dir (must PASS).
4. **Audits (all must pass, paste output):**
   (a) receipt PASS from step 3;
   (b) spend audit: total spend vs $25 cap from the run report;
   (c) key-leak audit: search the entire out dir for `SAIL_API_KEY`, `sk-`, `api_key` — must return zero hits
   (search filenames + contents; the word "api-key" in YOUR report-back prose is fine, hits in ARTIFACTS fail the run).
5. **Report back (paste verbatim, no paraphrase):** clusters evaluated, fail-closed point + 95% CI,
   grounding-given-valid point + 95% CI, validity rate, prompt + completion tokens, spend, wall time + P95,
   invalid-cluster count, all verify outputs. Then HALT.
