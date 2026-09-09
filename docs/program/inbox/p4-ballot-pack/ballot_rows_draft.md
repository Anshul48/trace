# Ballot rows — DRAFT ONLY (P4 dossier assembly, scripts only, no new claims)

> **Status: DRAFT.** Nothing here passes, fails, certifies, or approves
> anything. Each row becomes effective only when the human owner records it
> in `docs/program/06_DECISION_LOG.md`. No Amendment (A1–A6) is ratified by
> this draft; ratified Law (L1–L7) is cited, never modified.
> Packet states transcribed 2026-09-09 from branch `p11-p4-ballot-pack`
> (base `43ed591`): P0 HOLD (critic-APPROVED (P0 attempt 2), corpus
> UNADOPTED); P1/P2a/P2b/P2c NOT-BUILT; P3 PENDING-CRITIC on
> `p11-p3-warm-dream@a9b4d3b`, unapproved, unmerged.

## Row 1 — H0 H0-1M-CORPUS-CONTRACT (Corpus-Contract head)

| Field | Draft |
|---|---|
| Evidence | `docs/program/inbox/p4-ballot-pack/evidence_manifest.json` packet P0 (29 files, SHA-256 pinned); gate verdict HOLD, co-signature PENDING_HUMAN_BALLOT; independent checker INDEPENDENT-PASS on the provisional manifest (100000 + 900000 = 1000000 docs, 2014465744 bytes, union `5039acef…`), corpus itself UNADOPTED |
| Options | PASS (adopt successor H0-1M-SUCCESSOR-SEL-01) / HOLD (re-seal or re-stage) / ABORT (license/data blocker) |
| Suggested | No suggestion: PASS requires the human to accept the forensic selection hypothesis; HOLD is the fail-closed default |
| Rollback | No merge has occurred: rollback = do not merge; packet branch `p11-h0-seal-repair@43ed591` preserved as evidence; frozen BEIR baseline (`cap-ret04`) untouched and green |
| Cost/quality | $0 spent (no gate run, local-only evidence); quality risk carried forward: delta-side selection is a forensic hypothesis, not a staged-byte proof |

## Row 2 — H1 CAP-GF (G1M-CORE durability)

| Field | Draft |
|---|---|
| Evidence | None: P1 NOT-BUILT (`p11-h1-core` cut, no commits). No 1M runner, no replay parity proof, no 4-number storage table, no WAL ingest measurement |
| Options | GO / NO-GO |
| Suggested | NO-GO (insufficient evidence — not a quality failure; enter fresh on P1 delivery) |
| Rollback | Nothing to roll back; entry gate stays closed; H0 outcome unaffected (stacked-gate rule: downstream NO-GO never invalidates upstream) |
| Cost/quality | Unmeasured: L1/L2/L3 ceilings, L4 floor, and the 7.54x-recurrence risk all await the P1 measured (not modeled) storage gate |

## Row 3 — H2 cognitive retrieval (B/C1/C4/C2 heads)

| Field | Draft |
|---|---|
| Evidence | None: P2a NOT-BUILT (no branch); P2b NOT-BUILT (`p11-p2b-bridge-contradiction` cut, no commits). No paired deltas, no kill-bar audits |
| Options | GO (promote winners) / PARTIAL (promote winners, drop losers) / NO-GO (ship H1 stack) |
| Suggested | NO-GO (nothing in shadow; H1 stack ships by default when H1 passes) |
| Rollback | Per-mechanism flags never created; rollback pointer is the frozen H1 baseline once CAP-GF passes |
| Cost/quality | Unmeasured: P95/latency and nDCG deltas await shadow A/B with seed-42/10k-bootstrap CI |

## Row 4 — Tier-4 reasoning lane [A4] (P2c)

| Field | Draft |
|---|---|
| Evidence | None: P2c NOT-BUILT (`p11-p2c-hyde` cut, no commits). Local-SLM availability unprobed — the probe belongs to the P2c packet |
| Options | Shadow-entry on paired delta (CI excludes 0) / PARKED (no local SLM) |
| Suggested | Defer to the P2c packet: PARKED (no SLM) is a valid terminal state, not a failure; pipeline proceeds on lexical paths |
| Rollback | Interactive Tiers 1–2 (≤50 ms) untouched by construction; no default-path change to revert |
| Cost/quality | Budget table (P95 ≤800 ms metered, token/compute accounting) awaits the adapter |

## Row 5 — H3/H4 CAP-GG (Dreaming + CORTEX head)

| Field | Draft |
|---|---|
| Evidence | Partial: P3 code delivered on `p11-p3-warm-dream@a9b4d3b` (4 files, SHA-256 pinned in the manifest) but PENDING-CRITIC — unapproved, unmerged, invisible until CAP-GG unproven by ballot |
| Options | GO (active release) / NO-GO (ship H2 winners, dreaming stays experimental) |
| Suggested | NO-GO until the blind-critic verdict lands; then re-ballot on the verdict plus bound/invariance/invisibility proofs |
| Rollback | Branch preserved as evidence either way; NO-GO ships the H2 stack; versioned rollback for C8 distillation is part of the pending delivery |
| Cost/quality | Unmeasured: warm/cold hit-rate, cold-path cost, guard logs, and the Spine-invariance proof (zero Spine-byte delta on projection drop) await the critic-approved delivery |

## Cross-gate notes

- Stacked, never retroactive: each gate ballots independently; a downstream NO-GO never invalidates an upstream PASS.
- Merges to `main` stay individually human-gated; auto-commit is never auto-merge. No packet branch in this dossier has merged.
- Recompute: `python3 docs/program/inbox/p4-ballot-pack/assemble_ballot_manifest.py --check` (exit 0 = manifest recomputable, scan clean).
