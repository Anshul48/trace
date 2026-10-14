# WP-CAP-CRX03 Handoff Summary: Risk-Tiered Projection Activation & Atomic Handover

- **Node ID:** `CAP-CRX03`
- **Work Packet:** `WP-CAP-CRX03`
- **Role:** Data Engine Specialist (`DATA-SPEC`)
- **Worktree Branch:** `cap-crx03-activation`
- **Base Commit:** `45c3591942fc692c8427fbf0cf339bf4b3ca4254` (`cap-crx02-consolidator`)
- **Governing Plan:** `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`
- **Execution DAG:** `docs/program/CAP_001_EXECUTION_DAG.md` (Node `CAP-CRX03`)
- **Status:** Complete & Ready for Independent Verification (`VERIF-INDEP`)

---

## 1. Scope of Mutation & Exclusive Lease Audit

Mutations strictly adhered to exclusive file lease boundaries declared in `docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md` and `docs/program/inbox/cap-crx03/dispatch.md`:
- `src/trace/v2/store.py` (Modified):
  - Created `cortex_proposals` table and indices (`proposal_id`, `workspace_id`, `release_id`, `risk_tier`, `proposal_type`, `status`, `candidate_json`, `evidence_atom_ids_json`, `confidence`, `created_at`, `reviewed_at`, `reviewer_actor`, `review_reason`).
  - Created `cortex_activation_journal` table and indices (`journal_id`, `workspace_id`, `from_release_id`, `to_release_id`, `status`, `started_at`, `finished_at`, `error_detail`).
  - Implemented `create_cortex_proposal()`, `get_cortex_proposal()`, `list_cortex_proposals()`, and `review_cortex_proposal()`.
  - Implemented `record_activation_journal_start()` and `record_activation_journal_finish()`.
  - Implemented risk-tiered activation logic in `activate_cortex_release()`:
    - Tier 1 (Navigation Summaries) auto-activates into `status = 'auto_activated'`.
    - Tier 2/3 (Factual claims, schema proposals, entity extractions) remain `status = 'staged'` until human approval.
    - Promotes approved proposals to `status = 'promoted'`.
    - Supports strict approval mode (`require_all_proposals_approved=True`), failing closed if unreviewed Tier 2/3 items exist.
  - Implemented atomic journaled pointer swaps with crash rollback:
    - Pre-swap failure injection fails closed cleanly without touching active pointers.
    - Post-swap failure injection triggers rollback cleanly restoring last-known-good predecessor release.
    - Journal logs `rolled_back` with error detail and candidate release transitions to `failed`.
- `src/trace/v2/service.py` (Modified):
  - Updated `activate_cortex_release()` to support `require_all_proposals_approved` and `simulate_crash_stage`.
  - Added `activate_projection()` high-level service method.
  - Exposed `create_cortex_proposal()`, `get_cortex_proposal()`, `list_cortex_proposals()`, `review_cortex_proposal()`, and `list_cortex_activation_journals()`.
  - Hardened exception handling to preserve `validated` status when strict approval is rejected, while failing candidate on crash/alias errors.
- `tests/v2/test_cortex_activation.py` (New test suite):
  - 7 comprehensive unit and integration tests covering Tier 1 auto-activation, Tier 2/3 review gating, strict approval rejection, atomic journaled pointer swaps, pre-swap crash rollback, post-swap crash rollback restoring last-known-good, and explicit predecessor rollback.
- `docs/program/inbox/cap-crx03/handoff.md` (Deliverable receipt).

---

## 2. Technical Implementation Details

### A. Risk-Tiered Activation Rules
- **Tier 1 (Navigation Summaries / Topic Holons):** Low-risk structural summaries automatically transition to `auto_activated` upon activation of a validated release (`reviewer_actor = 'system_tier1_auto'`).
- **Tier 2/3 (Factual Claims, Entity Extractions, Schema Proposals):** Semantic claims and ontology updates remain staged in `cortex_proposals` until explicitly reviewed by an authorized actor via `review_cortex_proposal(..., decision="approve")`. Approved proposals promote upon release activation.
- **Fail-Closed Gate (`require_all_proposals_approved`):** When strict promotion is enabled, any unreviewed Tier 2/3 proposals halt activation with `InvariantViolation`, leaving the release in `validated` status for remediation.

### B. Atomic Journaled Pointer Swaps
- Prior to modifying release status, `record_activation_journal_start()` registers an `in_progress` journal entry in `cortex_activation_journal` capturing `from_release_id`, `to_release_id`, and `workspace_id`.
- The pointer swap (previous active -> `superseded`, new -> `active`) and event append (`cortex.release_activated`) execute within a single database transaction.
- On success, `record_activation_journal_finish()` records `committed` status with completion timestamp.

### C. Crash Rollback & Last-Known-Good Invariants
- Injected failures or database errors during the activation process trigger an atomic rollback:
  - SQLite transaction rollback automatically reverts any uncommitted pointer changes, ensuring the previous active release remains active.
  - External index aliases are compensated and restored to their previous targets.
  - The journal records `status = 'rolled_back'` with complete error context.
  - The candidate release transitions to `status = 'failed'` with failure detail.
  - Workspaces are never left without an active release or in an indeterminate state.

---

## 3. Verification Evidence

### Acceptance Test Suite:
```bash
PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_cortex_activation.py -v
```

**Results:** `9 passed in 5.31s` (100% PASS)
1. `test_atomic_journaled_pointer_swap_and_supersession`: PASSED
2. `test_create_cortex_proposal_rejects_out_of_bounds_confidence_or_empty_type`: PASSED
3. `test_explicit_cortex_release_rollback_restores_predecessor`: PASSED
4. `test_mid_swap_transactional_rollback_preserves_predecessor`: PASSED
5. `test_post_swap_crash_injection_restores_last_known_good_release`: PASSED
6. `test_pre_swap_crash_injection_rolls_back_cleanly`: PASSED
7. `test_strict_proposal_approval_blocks_activation_if_unreviewed_proposals_exist`: PASSED
8. `test_tier1_navigation_summaries_auto_activate_upon_release_activation`: PASSED
9. `test_tier2_and_tier3_proposals_remain_staged_until_explicitly_approved`: PASSED

### Full Regression Suite:
```bash
PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_cortex_activation.py tests/v2/test_cortex_consolidator.py -v
```
**Results:** `24 passed in 6.16s` (100% PASS, zero regressions)

---

## 4. Verification Command for Codex CLI (`VERIF-INDEP`)

```powershell
cd C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx03
$env:PYTHONPATH='src'
pytest tests/v2/test_cortex_activation.py -v
```
