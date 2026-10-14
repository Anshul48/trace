# WP-CAP-JOB02 Dispatch Briefing: Job Lease Expiry, Heartbeats & Backpressure

- **Node ID:** `CAP-JOB02`
- **Assigned Role:** Infrastructure Specialist (`INFRA-SPEC`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-job02` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-job02`)
- **Branch:** `cap-job02-recovery`
- **Base Commit:** `c853f43` (`cap-job01-pipeline`)
- **Lease ID:** `lease-cap-job02-20260903T130500Z`
- **Issued UTC:** `2026-09-03T13:05:00Z`

## Exclusive File Lease
- `src/trace/v2/service.py`
- `src/trace/v2/store.py`
- `tests/v2/test_job_recovery.py`
- `docs/program/inbox/cap-job02/handoff.md`

## Objectives & Deliverables
1. **Worker Heartbeat Monitoring:**
   - Active job workers periodically update a heartbeat timestamp on running jobs.
2. **300-second Lease Timeout & Zombie Reclamation:**
   - Jobs whose heartbeat exceeds 300s without completion are flagged as expired/orphaned and automatically recovered into runnable state or scheduled for retry.
3. **Dead-Letter Policy (3 Retries):**
   - When a poisoned job fails 3 consecutive times, route it to `failed_dead_letter` status with complete stack trace / error diagnostics.
4. **Queue Backpressure Cap (5,000 pending items):**
   - Reject new ingress calls or queueing when queue depth exceeds 5,000 pending tasks, returning a deterministic backpressure exception (HTTP 429 equivalent).
5. **Acceptance Test Suite:**
   - `tests/v2/test_job_recovery.py` demonstrating 100% pass under `/home/anshul/.venv/trace/bin/pytest tests/v2/test_job_recovery.py -v`.
