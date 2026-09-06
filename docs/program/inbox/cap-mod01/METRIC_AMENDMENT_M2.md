# Metric Amendment M2 (post-hoc rescore rule + forward pipeline fix)

- **Status:** SPEC + executed rescore over frozen receipts. Runner patch still required before 10K (outside this
  workspace; needs a proper code packet + independent verifier).
- **Why:** the frozen fail-closed composite scored harness artifacts as model failures: 41 empty-but-valid
  clusters (1K) and 48 cap-truncated clusters. Corrected handling below; scorer formula itself unchanged.

## M2 scoring rules

1. **Empty → invalid.** Zero extracted propositions = `is_invalid=true`, never valid-0.0 (fail-closed, CAP-D011).
2. **Truncated → robustness ledger, not grounding denominator.** `completion_tokens >= max_tokens` cap (or
   `finish_reason=length` when recorded) marks the cluster `truncated`: excluded from grounding stats, counted
   in the validity/robustness ledger. Forward pipeline rule: retry once with raised cap; score only the retry.
3. **Triple reporting (all three, every run):** grounding over strict-valid clusters (point + 95% CI, B=10,000,
   seed 42) + validity rates (schema-valid AND strict-valid) + frozen fail-closed composite as sensitivity.
4. **NLI overlay (spec'd, NOT run):** EVAL03-class NLI rescore of stored propositions needs an implementation plus
   pinned weights — this machine has no transformers/torch and an empty HF cache. Authorized as a forward
   model-admission decision, not part of M2.

## M2 rescore results (frozen receipts, 2026-09-05, /tmp scratch)

| Run | Grounding (strict-valid) | 95% CI | Schema validity | Strict validity | Frozen composite |
|---|---|---|---|---|---|
| anchor-100 | 0.9693 (n=72) | [0.9370, 0.9893] | 86.0% | 72.0% | 0.7779 |
| run-1k | 0.9232 (n=483) | [0.9038, 0.9419] | 68.1% | 62.8% | 0.6016 |

- Honest read: M2 reframes but does not pass 1K — 1K upper bound 0.9419 < 0.95 floor; anchor passes point only.
  Remaining gap is real (grounding shortfall ~3 points + validity collapse), not pure artifact.
- 1K dossier must carry BOTH numbers labeled (frozen-metric + M2); GC ratifies M2 for forward use. Post-hoc
  rescore never silently replaces the pre-registered metric.

## Forward pipeline fix (required in runner patch before 10K)

- `max_tokens` 2048 → raised cap + `finish_reason` capture; length-truncated outputs auto-retry once, never scored.
- Empty output → invalid + counted; three-strike cluster abort rule stays fail-closed.
- Record per-cluster `finish_reason`, cap value, and retry count in raw receipts (schema addition).

## Retry protocol R1 (error-feedback retries, serial)

- **R1a truncated** (`finish_reason=length` or tokens ≥ cap): retry once, cap 4096, same prompt.
- **R1b empty** (<100 completion tokens or zero propositions): retry once with feedback:
  "Your previous response contained no scorable content. Emit the full holon JSON."
- **R1c unparseable** (HTTP 200, parse fail): retry once with feedback including the parse error string:
  "Your previous response failed JSON parsing with: <err>. Return raw JSON only."
- **Serial retry pass** (concurrency=1): doubles as the concurrency-sensitivity test — compare serial retry
  success against the original 16-worker outcome on the same clusters.
- One retry per class max; three-strike abort stays fail-closed. Record attempt number, feedback text,
  `finish_reason`, and cap per attempt in raw receipts.
- Cost to retry all 286 failed 1K clusters: ≈$0.30. No full rerun required.
