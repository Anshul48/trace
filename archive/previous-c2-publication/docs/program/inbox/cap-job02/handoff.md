# WP-CAP-JOB02 Handoff Summary: Job Lease Expiry, Heartbeats & Backpressure

- **Node ID:** `CAP-JOB02`
- **Work Packet:** `WP-CAP-JOB02`
- **Role:** Infrastructure Specialist (`INFRA-SPEC`)
- **Worktree Branch:** `cap-job02-recovery`
- **Base Commit:** `c853f43b0361e085c9ab0bb63e3ac16758a89fb1` (`cap-job01-pipeline`)
- **Governing Plan:** `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`
- **Execution DAG:** `docs/program/CAP_001_EXECUTION_DAG.md` (Node `CAP-JOB02`)
- **Status:** Complete & Ready for Independent Verification (`VERIF-INDEP`)

---

## 1. Scope of Mutation & Exclusive Lease Audit

Mutations strictly adhered to exclusive file lease boundaries declared in `docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md` and `docs/program/inbox/cap-job02/dispatch.md`:
- `src/trace/v2/store.py` (Modified):
  - Added `QueueBackpressureError` (inherits `TraceStoreError`, `status_code = 429`).
  - Added `heartbeat_at TEXT` column to `jobs` table schema and upgrade migration.
  - Added `heartbeat_job()` method updating `heartbeat_at` timestamp and extending `lease_until`.
  - Added `reclaim_stale_jobs()` and transactional `_reclaim_stale_jobs_in_tx()` reclaiming expired running jobs into `queued` state (or `failed_dead_letter` if attempts exceed `max_attempts`).
  - Updated `claim_jobs()` to automatically reclaim stale/expired running jobs before leasing queued work.
  - Updated `fail_job()` to route poisoned jobs failing 3 consecutive times (`attempts >= max_attempts`) to `failed_dead_letter` status with complete stack trace / error diagnostics.
  - Added `get_queue_depth()` with thread-safe lock protection.
  - Enforced queue depth backpressure cap in `create_job()`, rejecting new job creation with `QueueBackpressureError` when queue depth meets or exceeds capacity.
- `src/trace/v2/service.py` (Modified):
  - Imported and exposed `QueueBackpressureError`.
  - Initialized configurable `self.max_queue_depth` (default 5,000, configurable via `TRACE_JOB_MAX_QUEUE_DEPTH`).
  - Added fast backpressure rejection in `_ingest()` prior to parsing/staging/atomization.
  - Exposed `get_queue_depth()`, `heartbeat_job()`, and `reclaim_stale_jobs()` on `TraceService`.
  - Integrated zombie reclamation into `run_pipeline_until_idle()` and background pipeline worker loop.
- `tests/v2/test_job_recovery.py` (New test suite):
  - 15 comprehensive unit and integration tests covering heartbeats, 300s lease expiry, zombie reclamation, dead-letter routing, backpressure rejection, queue recovery, tenant isolation in job claims, operator retry budget reset, and stale heartbeat recovery.
- `docs/program/inbox/cap-job02/handoff.md` (Deliverable summary).

---

## 2. Technical Implementation Details

### A. Worker Heartbeat Monitoring & Stale Heartbeat Reclamation
- `store.heartbeat_job(job_id, lease_seconds=300)` updates `heartbeat_at = now()` and sets `lease_until = now + lease_seconds`.
- Appends `job.heartbeat` event to the durable audit stream.
- Rejects heartbeats on non-running or missing jobs fail-closed (`InvariantViolation` / `NotFoundError`).
- Stale worker heartbeats trigger reclamation even if `lease_until` was set in the future.

### B. 300-Second Lease Timeout & Zombie Reclamation
- When an active worker crashes or fails silently, running jobs exceed their lease without completion.
- `reclaim_stale_jobs(lease_timeout_seconds=300)` identifies orphaned running jobs.
- If `attempts < max_attempts`, the job status resets to `queued` with reason `lease_timeout_reclaimed` and becomes immediately available to other healthy workers.
- `claim_jobs()` triggers `_reclaim_stale_jobs_in_tx()` on every lease claim cycle, ensuring dead-worker jobs are recovered proactively.
- `claim_jobs()` supports `workspace_id` filtering to ensure tenant isolation during job leasing.

### C. 3-Retry Dead-Letter Policy (`failed_dead_letter`)
- `fail_job()` tracks execution attempts against `max_attempts` (default: 3).
- When a job fails under the retry limit, it reschedules with deterministic backoff.
- On the 3rd consecutive failure (`attempts >= max_attempts`), the job transitions to `failed_dead_letter`.
- The error dictionary retains complete diagnostics: error type, detail message, attempt counts, kind, and job ID.
- Operators can manually rescue dead-letter jobs via `retry_job(job_id, reset_attempts=True)`.

### D. Queue Backpressure Cap (5,000 pending items)
- Ingress calls via `service.ingest()` verify pending queue depth (`queued` + `running`) before allocating staging bytes or atomizing text.
- If pending depth $\ge 5,000$ (or configured threshold), the service immediately rejects the ingress with `QueueBackpressureError` (HTTP 429 equivalent).
- `store.create_job()` enforces the identical cap at the data layer to safeguard background job creation.
- Once workers process queued work and pending depth falls below the cap, new requests are accepted without manual intervention.

---

## 3. Verification Evidence

### Acceptance Test Command:
```bash
PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_job_recovery.py -v
```

**Results:** `15 passed in 9.24s` (100% PASS)
1. `test_backpressure_recovers_after_queue_drains`: PASSED
2. `test_claim_jobs_automatically_reclaims_expired_leases`: PASSED
3. `test_claim_jobs_with_workspace_id_preserves_tenant_isolation`: PASSED
4. `test_heartbeat_on_missing_job_raises_not_found`: PASSED
5. `test_heartbeat_on_non_running_job_raises_invariant_violation`: PASSED
6. `test_ingress_rejected_when_queue_depth_exceeds_backpressure_cap`: PASSED
7. `test_manual_operator_retry_of_dead_letter_job`: PASSED
8. `test_manual_operator_retry_resets_attempts_for_dead_letter_job`: PASSED
9. `test_poison_job_routed_to_failed_dead_letter_after_3_retries`: PASSED
10. `test_queue_backpressure_cap_enforced_in_store`: PASSED
11. `test_run_pipeline_until_idle_reclaims_and_drains_cleanly`: PASSED
12. `test_stale_running_job_is_reclaimed_to_queued_state`: PASSED
13. `test_worker_heartbeat_timeout_reclaims_job_even_with_extended_lease`: PASSED
14. `test_worker_heartbeat_updates_timestamp_and_extends_lease`: PASSED
15. `test_zombie_job_exceeding_max_attempts_routes_to_failed_dead_letter`: PASSED

### Full Regression Suite:
```bash
PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_job_recovery.py tests/v2/test_job_pipeline.py tests/test_v2_foundation.py -v
```
**Results:** `38 passed in 12.37s` (100% PASS, zero regressions)

---

## 4. Verification Command for Codex CLI (`VERIF-INDEP`)

```powershell
cd C:/Users/anshu/AppData/Local/trace-worktrees/trace-job02
$env:PYTHONPATH='src'
pytest tests/v2/test_job_recovery.py -v
```

---

## 5. R-JOB02 Repair Record (INFRA-SPEC, lease `lease-cap-job02-linux-20260904`)

- **Repair commit:** `e9dec7856fafbbc12c1d5a8db49b5891628fd438` on `cap-job02-recovery`
  (old tip `d6ab37b0514bbc02108529a942fa038c946bc596` → new tip `e9dec78...`; via `update-ref`, no rebase/merge).
- **Worktree:** detached at `d6ab37b` in `/tmp/trace-wt/job02` (verified via `rev-parse`, clean before/after); `.venv`/`.pytest_cache` removed, worktree removed `--force` after landing.
- **Change:** +68 lines in `tests/v2/test_job_recovery.py` only (file 412 → 480 lines) — new test
  `test_crash_after_consolidation_zero_orphans_activation_idempotent` (~line 413+). No `src/` changes:
  the run proved no defect (`complete_job` is already idempotent on `succeeded`, `store.py:5708-5709`).
- **New-test flow:** `store.create_job` → `store.claim_jobs` (running) → `service.heartbeat_job`
  → crash-after-consolidation simulated (never `complete_job`; `heartbeat_at`/`lease_until` forced 400s
  stale) → `service.reclaim_stale_jobs(lease_timeout_seconds=300)` → `queued` → re-claim → handler to
  `succeeded` via `store.complete_job` → handler invoked a 2nd time (double activation, effects-once).
- **Acceptance:** `PYTHONPATH=src .venv/bin/pytest tests/v2/test_job_recovery.py -v` → **16/16 passed**
  (15 existing + 1 new; per COORD CORRECTION, supersedes stale 15/15 in fix-spec §R-JOB02.5).
- **Orphan/double-activation evidence (asserted in-test):** orphan
  `SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')` == 0; exactly 1 job row;
  `handler_invocations == 2` with single applied effect; status `succeeded`.
- **Handoff status:** this record appended in the parent checkout, left UNCOMMITTED as instructed. No merge.
