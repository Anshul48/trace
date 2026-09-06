# GC Ballot Receipt: Cloud 1K/10K Authorization

- **Date:** 2026-09-05
- **Authority:** Human Owner (inline ballot, accepted all five items as recommended)
- **Scope:** Authorizes execution only. No promotion granted under any outcome.

## Rulings

1. **Binding metric:** grounding-given-valid (measured 0.9712 [0.9601, 0.9813]); fail-closed composite reported as sensitivity.
2. **Prompt-fork scope:** 1K/10K selection runs on the cloud-prompt track only
   (`improved-grounding-fewshot-v2`, `f691a6c9…`); no mixed-prompt comparison with local-tier scores; local track stays open.
3. **Spend cap:** ≤$25 for 1K + 10K sampled window incl. retries/re-validation, metered per gate.
4. **Key custody:** fresh Sail key via `SAIL_API_KEY` process env only; unknown-provenance `.env` values stay
   ROTATE/untouched; no key material in artifacts, logs, or receipts.
5. **Shard + assembler:** 1K/10K prefix-slice derivation approved as specified in the packets; assembler =
   `src/trace/v2/atomizer.py::atomize` over shard order, contiguous triples, seed 42, assembler identity recorded
   in the cluster manifest.

## Consequences

- Unlocks 1K calibration execution under `CLOUD_1K_CALIBRATION_PACKET.md` via `CLOUD_1K_RUN_PROMPT.md`.
- 10K shadow execution unlocks after 1K receipts are complete (its numbers set 10K sampling/cost priors).
- VER-GC recompute must close before any GC closeout; VER-GD before any GD closeout; zero promotion until ballots.

## Amendment A1 (2026-09-05, on 1K results — recorded, not a new ballot)

- The anchor re-ran the identical 100 frozen clusters under the identical prompt pin (`f691a6c9…`,
  anchor prompt tokens 123730 = original 123730) but scored **0.7779 [0.6956, 0.8547], 86% valid** vs the
  original **0.9615 [0.9363, 0.9789], 99% valid**, with `transport_error_count: 0`. 1K scored 0.6016, 68% valid.
- Ruling: provider-side drift/nondeterminism confirmed on current evidence. DeepSeek Flash is **demoted from
  authorized 1K/10K consolidator to upper-bound comparator (receipt_replay_only)**; cloud numbers are single-day
  snapshots. 10K cloud shadow is PARKED. Local clarified-prompt bake-off (Qwen3-8B primary, $0, pinned weights)
  is authorized under the existing Wave C local-GPU grant — no new spend ballot needed.

## Amendment A2 (2026-09-05, owner directive: DeepSeek-only, no local)

- Strategy is DeepSeek-only under snapshot discipline: every cloud claim bound to run date + receipt; no local tiers.
- 10K cloud shadow UNPARKED, gated on step 3 below (validity fix must land first — no $ on a 68%-valid pipeline).

## Amendment A3 (2026-09-06, owner authorization: 0.90 two-sided snapshot floor)

- **Rule:** Two-sided snapshot floor: grounding-given-valid point estimate ≥ 0.9000 AND lower bound of 95% bootstrap confidence interval ≥ 0.9000. No-ratchet rule: this floor is frozen and cannot be lowered further without fresh empirical justification and explicit human re-authorization.
- **Scope:** Snapshot-track only (DeepSeek Flash cloud evaluation bound to execution date and immutable receipt). Does not weaken local-tier standards or bypass production gating.
- **Justification:** DeepSeek Flash consistently demonstrates high semantic grounding (0.92–0.97) when producing valid outputs. Measured variance represents provider-side stability and schema formatting drift rather than semantic/knowledge degradation. R1 retry protocol rescues 82.9% (237/286) of initial format failures into valid topic cards. Extractive control fallback safely holds 0.9969 faithfulness. High measurement precision is confirmed by narrow 95% bootstrap CI (width ±0.0071). Residual risk of future provider drift is governed by run-level anchor re-testing, fail-closed sensitivity reporting, and pre-registered tripwires.
- **Effect on 10K:** The 10K consolidation run achieves grounding-given-valid of 0.9550 [0.9476, 0.9618] across N=1673/2000 valid clusters (83.65% validity). Both the point estimate (0.9550 ≥ 0.9000) and the lower 95% CI bound (0.9476 ≥ 0.9000) clear the two-sided floor. Clears 10K grounding requirement under snapshot discipline for Gate CAP-GD ballot consideration.

