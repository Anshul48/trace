# Plan: GD Ballot to Wave E (DeepSeek-Only, 0.90 Snapshot Floor)

## Goal

Close Gate CAP-GD on recorded, reproducible evidence and open Wave E (100K paired qualification) with no
ungrounded claims, no invented inputs, and the 0.90 snapshot floor properly authorized.

## Success Criteria

- A3 (0.90 two-sided snapshot floor) recorded in `GC_BALLOT_RECEIPT.md` with rule, scope, justification, effect.
- 10K report corrected (uplift deltas, R1 numbers, verdict language) and re-verified PASS by its own commands.
- Audit flags resolved or explicitly carried; GD ballot presented with caveats disclosed.
- Human GD decision recorded; Wave E scaffolds only after ACCEPT, against the real 100K capsule path.

## Context And Current Facts

- 10K grounding 0.9550 [0.9476, 0.9618], n=1673/2000 (83.65%), fail-closed 0.7989 — independently recomputed exact
  match (`AUDIT_10K.md`). Spend $4.2794 / $25 cap. Receipts verify PASS (rerun).
- R1 retry: 286 retried (as predicted), 237 rescued (82.9%). Report's "540/867" contradicts the artifact.
- Uplift deltas inconsistent for SciFact (0.0249 vs +0.0179) and NFCorpus (0.0001 vs +0.0097); FiQA consistent.
- Owner authorized 0.90 floor and DeepSeek-only strategy verbally; neither is recorded yet (A3 pending).
- `benchmarks/data/corpus_100k_frozen.jsonl` does not exist; the 100K source is the l1-02 capsule
  (`docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json`, Merkle `38d1a1cf…`).
- Retrieval baseline verified PASS with $0 spend; lifecycle drills verified PASS; 16/16 unit tests PASS (all rerun).

## Constraints And Non-goals

- DeepSeek-only: no local tiers. No 1M work, no NLI-validator build, no further threshold changes.
- No promotion and no Wave E execution before a human GD ACCEPT. No invention of corpus paths or numbers.
- Spend stays under the $25 cap; key custody unchanged (session env only).

## Key Decisions

1. **Trust DeepSeek at a 0.90 two-sided floor: yes, with guardrails.** For: grounding 0.92–0.97 whenever the
   model answers; the drift is stability, not knowledge; R1 rescues 82.9%; extractive fallback holds 0.9969;
   CI width is narrow (±0.007), so the number is precise. Against: drift direction is unknown — the next
   snapshot could print below 0.90. Carried risk is handled by tripwires, not optimism (see Risks).
   Rejected: keeping an unrecorded 0.90 (binds nothing) and re-raising to 0.95-lower-bound for unpinned weights
   (measures provider stability, not our quality).
2. **Fix reports before ballot, not after.** A ballot on incorrect numbers is voidable; corrections are cheap.
3. **Wave E reads the capsule, not a nonexistent file.** Any scaffold referencing
   `benchmarks/data/corpus_100k_frozen.jsonl` fails preflight by design.

## Recommended Approach

Record-then-correct-then-ballot: file A3 first (makes the 10K verdict valid), correct the two numbers plus
verdict language, re-verify mechanically, refresh the audit, then present the GD ballot with the
verifier-separation caveat disclosed. Scaffold Wave E only on ACCEPT, pinned to the capsule path.

## Work Plan

1. **File A3** (`docs/program/inbox/cap-mod01/GC_BALLOT_RECEIPT.md`, append): 0.90 two-sided rule, snapshot-track
   scope, provider-band justification, effect on 10K (clears both sides). Owner: human (text supplied).
2. **Correct 10K report** (agy, at trace root): recompute paired uplift deltas from raw per-query records or
   correct endpoints (mean-of-deltas must equal difference-of-means); replace "540/867" with 286/237 (82.9%);
   restate verdict as results-complete with promotion reserved to ballot. Re-run both `--verify-receipt`
   commands to confirm PASS.
3. **Refresh audit** (independent rerun): recompute grounding CI from raw, rerun pytest suite and both
   verifiers, rescan key leaks; update `AUDIT_10K.md` flags to resolved/carried.
4. **GD ballot** (human): ACCEPT / AMEND / REJECT on 10K shadow clearance + Wave E authorization, with the
   same-session audit caveat and the A3 floor disclosed in the ballot text.
5. **Wave E scaffold** (only on ACCEPT): 10K dossier assembly; INT02 design reading the l1-02 capsule manifest
   (never the nonexistent frozen.jsonl); three-profile separation per DAG; stop rules (Profile 2 regression,
   storage >3.5×) wired as preflight failures.

## Validation Plan

- Unit 1: `git diff docs/program/inbox/cap-mod01/GC_BALLOT_RECEIPT.md` shows only the A3 append.
- Unit 2: uplift deltas satisfy mean-of-deltas == difference-of-means (recomputed); both verify commands print
  PASS; `pytest tests/test_deepseek_flash_concurrent_10k.py` 16 passed.
- Unit 3: grounding recompute matches report to 4 decimals; key-leak grep zero hits; spend ≤ $25 in receipts.
- Unit 4: ballot text names candidate, verifier, policy digests, caveats, and exact claim (per gate matrix).
- Unit 5: scaffold preflight fails closed on any reference to the nonexistent corpus path; capsule Merkle
  `38d1a1cf…` verified before ingestion design.
- Highest-risk validation: Unit 2's uplift recompute — if raw per-query records can't reproduce either number,
  the uplift claim is withdrawn to "unverified," not repaired by editing.

## Risks / Rollback

- **Next snapshot prints below 0.90:** tripwire — no promotion, diagnose (re-anchor the frozen 100 first),
  extractive fallback serves; the floor is never lowered again without fresh justification (no ratchet).
- **Uplift records irreproducible:** withdraw the uplift claim; GD ballots on grounding + lifecycle only.
- **Rollback:** every unit is additive (appends, corrections with diffs); revert is `git checkout` of the
  touched files. No Spine/Cortex state is touched at any step.

## Open Questions

None. All material facts verified locally this session; preferences (DeepSeek-only, 0.90 trust) given by owner.
