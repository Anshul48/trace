# WP-CAP-CRX03 Dispatch Briefing: Risk-Tiered Projection Activation & Atomic Handover

- **Node ID:** `CAP-CRX03`
- **Assigned Role:** Cortex Specialist (`CRX-SPEC`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx03` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-crx03`)
- **Branch:** `cap-crx03-activation`
- **Base Commit:** `45c3591` (`cap-crx02-consolidator`)
- **Lease ID:** `lease-cap-crx03-20260903T130500Z`
- **Issued UTC:** `2026-09-03T13:05:00Z`

## Exclusive File Lease
- `src/trace/v2/service.py`
- `src/trace/v2/store.py`
- `tests/v2/test_cortex_activation.py`
- `docs/program/inbox/cap-crx03/handoff.md`

## Objectives & Deliverables
1. **Risk-Tiered Activation Rules:**
   - **Tier 1 (Navigation Summaries):** Auto-activates into active projections once detached validation receipts pass.
   - **Tier 2/3 (Factual claims, schema proposals, entity extractions):** Staged in durable `cortex_proposals` table requiring explicit human review / approval before promotion to canonical active release.
2. **Atomic Journaled Pointer Swaps:**
   - Active release transitions must execute within a transactional write lock with crash journal logging across SQLite/Postgres.
3. **Crash Rollback & Last-Known-Good Invariants:**
   - Injected failures or system crashes during handover must roll back cleanly to the last-known-good active release without partial state exposure.
4. **Acceptance Test Suite:**
   - `tests/v2/test_cortex_activation.py` demonstrating 100% pass under `/home/anshul/.venv/trace/bin/pytest tests/v2/test_cortex_activation.py -v`.
