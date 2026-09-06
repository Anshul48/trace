# COORD-REPAIR Review Notes: Batch-1 + Batch-2 Fix Specs (coordinator spot-check)

- **Session:** COORD-REPAIR, 2026-09-03 (Muse coordinator)
- **Specs:** `CAP_001_R_BATCH1_FIXSPEC.md`, `CAP_001_R_BATCH2_FIXSPEC.md` (read-only, no src/test/git writes — sandbox permits no repo writes outside `launch/`)

## Spot-check results (independent `git show` verification)

| Claim | Verdict |
|---|---|
| R-RET02 guard `test_hybrid_retrieval.py:293` + `:309` fallback branch | CONFIRMED (own grep: test at :293) |
| R-CRX02 `model_gateway.py` flash entry sets no price coefficients | CONFIRMED (`DEFAULT_MODEL_REGISTRY` flash entry, no coefficients) |
| R-CRX02 `:534` `estimated_cost` input-tokens-only | CONFIRMED |
| R-CRX02 `cortex_consolidator.py:589-591` bare-float manifest audit | CONFIRMED |
| R-CRX02 base file already emits `…` (spec-change option B favored) | NOT independently re-verified; flagged as specialist-observed, needs GB decision either way per packet (no silent third spelling) |
| R-JOB01 fallback `service.py:475-479` + `store.py:3812` | CONFIRMED (matches receipt probe) |
| R-JOB01 16 existing tests | CONFIRMED (`grep -c "def test"` = 16) → 18/18 after 2 new |
| R-JOB02 new-test spec + symbols | PLAUSIBLE, line-refs match receipt; test-body review deferred to write-capable session |
| R-CRX03 crash-log artifact spec + no-rebase rule | CONFIRMED consistent with receipt + D3 |
| D3 merge order (JOB02 first, CRX03 rebases at merge) | CONFIRMED (matches receipt `overlap_audit`, zero textual conflicts) |

## CORRECTION — R-JOB02 acceptance count

Spec §R-JOB02.5 claims "14 existing + 1 new = 15/15". Independent count: `cap-job02-recovery:tests/v2/test_job_recovery.py` has **15** existing `def test` functions. After the new crash-after-consolidation test lands, the literal suite is **16 tests → acceptance is 16/16** (new test present + passing, full suite green), not 15/15. (Turn prompt §13 predates the count; evidence wins.)

## P0-ENV spot-check

`CAP_001_P0_ENV_RECON.md` venv table is CONSISTENT with the coordinator's own Linux-mount probe (crx02/job01 Linux venvs, ret02/job02/crx03 without usable pytest, eval02 Windows venv reference). Root cause agreed: bare `pytest` not on PATH in any of the 5 verification shells. Env-fix commands + acceptance checks look correct for a Windows write-capable session; installs not executed here.

## Blockers for the write-capable session

1. DONE — P0-ENV recon filed (`CAP_001_P0_ENV_RECON.md`).
2. All five repairs need src/test edits + commits + literal pytest runs — impossible in this sandbox.
3. R-CRX02 byte-parity needs a GB-level choice (restore `?` vs canonize `…`) if option B is taken.
4. Fresh ≥8h leases must be reissued for JOB02/CRX03 (expired 15:05Z) before re-verification; re-verify from detached-clean checkouts per §§2–3, then §5A GB dossier.
