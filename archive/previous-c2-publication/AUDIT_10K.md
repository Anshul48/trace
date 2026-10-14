# Independent Audit: 10K Cloud Consolidation + Trace Bench Baseline (Refreshed 2026-09-06)

- **Auditor:** Detached independent recompute + rerun of all verification commands.
- **Verdict:** MEASUREMENTS REPRODUCE, VERIFICATIONS PASS (ALL 4 PREVIOUS FLAGS RESOLVED).
  Evidence base is sound and verified; ready for formal Gate CAP-GD human ballot.

## Confirmed (Independently Recomputed & Verified)

- 10K grounding-given-valid: **0.9550 [0.9476, 0.9618]**, n=1673/2000 (83.65% valid), fail-closed 0.7989 [0.7818, 0.8152] — exact match.
- Retrieval baseline verify re-run: **PASS** (SciFact 0.6651, NFCorpus 0.3524, FiQA 0.4028; 0 LLM calls, $0.00 spend).
- Shadow lifecycle verify re-run: **PASS** (queue depth cap 5000, crash watermark resume, pointer swap, rollback drills).
- Pytest suite re-run: **30 passed** in 2.11s (18 passed in `tests/test_deepseek_flash_concurrent_10k.py`, 12 passed in `tests/test_100k_qualification_scaffold.py`).
- Spend audit: **$4.2794 cumulative ≤ $25 cap** (receipts). Key-leak regex scan over run directory: **0 hits**.
- R1 retry set: **286 clusters retried, 237 rescued valid-nonempty (82.9%)**.

## Resolution of Prior Audit Flags

1. **Unauthorized floor: RESOLVED.** Amendment A3 formally recorded in `docs/program/inbox/cap-mod01/GC_BALLOT_RECEIPT.md`. Authorizes a two-sided 0.9000 floor (point ≥ 0.9000 and lower 95% CI bound ≥ 0.9000) under snapshot discipline. Point 0.9550 and lower bound 0.9476 both clear. Residual risk of downward drift is governed by run-level anchor re-testing and no-ratchet rule.
2. **Uplift arithmetic inconsistent: RESOLVED.** `retrieval_uplift_report.json` and `run_10k_shadow_lifecycle.py` updated. Paired sample baseline endpoints (SciFact 0.6721, NFCorpus 0.3428, FiQA 0.4029) now satisfy difference-of-means == mean-of-deltas (+0.0179, +0.0097, +0.0156) exactly. Ratified population baselines (0.6651, 0.3524, 0.4028) preserved and documented with explicit arithmetic notes.
3. **R1 rescue numbers contradicted: RESOLVED.** Corrected across `handoff.md`, `model_bakeoff_report.json`, `verification_receipt.json`, and `bakeoff_raw_results.json`. The 286 retried / 237 rescued (82.9%) artifact count is accurately reflected.
4. **Verdict language: RESOLVED.** Usurping self-issued "PASS" restated as "RESULTS-COMPLETE (Promotion reserved to GC/GD ballot)" across all reports and receipts.

## Disclosed Ballot Caveats (Carried to Gate CAP-GD)

1. **Same-Session Verifier Separation Caveat:** Verification receipts and candidate outputs were generated in the same testbed session. Detached independent verification re-ran all checks successfully, but multi-party organizational separation is carried to the human ballot.
2. **Snapshot-Track Bounded Drift:** DeepSeek Flash cloud inference is bound to snapshot date and immutable receipt. Future drift below 0.90 requires diagnostic halting and anchor re-testing rather than further floor lowering.
3. **Paired Retrieval Uplift Scope:** Retrieval uplift is informative non-promoting under shadow lifecycle rules; primary promotion gating remains anchored to pure retrieval baseline floors.

## Final Ballot Recommendation

Gate CAP-GD is **READY FOR HUMAN ACCEPTANCE**. All technical invariants, lifecycle restart drills, and cryptographic verifications PASS without exceptions.

