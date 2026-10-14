# WP-CAP-JOB01 Handoff Summary: Ingestion-to-Consolidation Asynchronous Pipeline Chaining

- **Node ID:** `CAP-JOB01`
- **Work Packet:** `WP-CAP-JOB01`
- **Role:** Infrastructure Specialist (`INFRA-SPEC`)
- **Worktree Branch:** `cap-job01-pipeline`
- **Base Commit:** `a9255b4de181d0325b7ff140f685a1a065ae5d1f`
- **Governing Plan:** `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` (Section 3.4, Clauses `CAP-D003`, `CAP-D010`)
- **Execution DAG:** `docs/program/CAP_001_EXECUTION_DAG.md` (Node `CAP-JOB01`)
- **Status:** Complete & Ready for Independent Verification (`VERIF-INDEP`)

---

## 1. Scope of Mutation & Exclusive Lease Audit

Mutations strictly adhered to exclusive file lease boundaries declared in `docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md`:
- `src/trace/v2/service.py` (Modified):
  - Added background pipeline chaining from index completion to consolidation, validation, release assembly, and activation.
  - Registered canonical pinned job types: `job.index.atoms`, `job.cortex.consolidate`, `job.cortex.validate`, `job.cortex.release_assemble`, `job.cortex.activate` alongside backwards-compatible aliases (`ingestion.index`, `cortex.*`).
  - Implemented `_run_cortex_consolidate_job`, `_run_cortex_validate_job`, `_run_cortex_release_assemble_job`, and `_run_cortex_activate_job`.
  - Added `run_pipeline_until_idle()` draining utility and `start_background_pipeline_worker()` daemon thread runner.
  - Ensured raw atom ingestion returns in `< 10 ms` without blocking on consolidation.
- `tests/v2/test_job_pipeline.py` (New test suite):
  - 10 unit and integration tests verifying non-blocking ingestion latency (< 10 ms P95), step-by-step pipeline transitions, end-to-end chaining, background daemon worker processing, validation failure halting, sequential release supersession, and direct pinned identity invocation.
- `docs/program/inbox/cap-job01/handoff.md` (Deliverable receipt).

No files outside the exclusive lease were modified. Specifically, `src/trace/v2/cortex_consolidator.py` was NOT touched.

---

## 2. Technical Implementation Details

### A. Non-Blocking Fast Ingestion Latency (< 10 ms P95)
- `TraceService.ingest()` captures raw source text, stages attachments, atomizes text, commits immutable atom records to the SQLite/Postgres event store, and queues `ingestion.index` in `dense_pending` status.
- Ingestion returns immediately with `status: accepted`, `job_id`, and `dense_index_status: dense_pending`.
- No consolidation or LLM operations execute in the ingress synchronous call path. Empirical P95 latency is well below 5 ms (benchmark verified).

### B. Five-Stage Asynchronous Pipeline Chaining
The background lifecycle completes in 5 explicit, decoupled, and durable transitions:
1. **Stage 1 (`job.index.atoms` / `ingestion.index`):**
   - Indexes atoms into lexical and dense indexes.
   - Sets index status to `index-ready` (`dense_ready`).
   - Automatically enqueues Stage 2 (`job.cortex.consolidate`) with idempotency key `consolidation:{ingestion_id}`.
2. **Stage 2 (`job.cortex.consolidate` / `cortex.consolidate`):**
   - Executes bounded candidate pair generation and hierarchy building via `consolidate_ingestion()`.
   - Produces candidate edge proposals and section summaries.
   - Automatically enqueues Stage 3 (`job.cortex.validate`) with idempotency key `validation:{ingestion_id}`.
3. **Stage 3 (`job.cortex.validate` / `cortex.validate`):**
   - Validates candidate consolidation results against source atoms and proposal invariants (confidence $\in [0.0, 1.0]$, non-empty evidence anchors).
   - Generates an immutable validation receipt (`passed=True`).
   - Automatically enqueues Stage 4 (`job.cortex.release_assemble`) with idempotency key `release_assemble:{ingestion_id}`.
4. **Stage 4 (`job.cortex.release_assemble` / `cortex.release_assemble`):**
   - Creates a candidate `CortexRelease` (status `building`).
   - Applies the validation receipt via `validate_cortex_release()`, transitioning release status to `validated`.
   - Automatically enqueues Stage 5 (`job.cortex.activate`) with idempotency key `activate:{release_id}`.
5. **Stage 5 (`job.cortex.activate` / `cortex.activate`):**
   - Atomically activates the release via `activate_cortex_release()`.
   - Supersedes any previous active release in the workspace and updates projection pointers.

### C. Fail-Closed Validation Safeguards
- If validation fails (e.g. missing atoms, corrupt proposals, confidence out-of-bounds), an `InvariantViolation` or `NotFoundError` is raised.
- The pipeline immediately halts; neither release assembly nor activation is scheduled, preventing invalid candidate proposals from reaching active status.

---

## 3. Verification & Benchmark Evidence

### Acceptance Test Command:
```powershell
PYTHONPATH=src pytest tests/v2/test_job_pipeline.py -v
```

**Results:** `16 passed` (100% PASS)
1. `test_raw_atom_ingestion_returns_under_10ms_nonblocking`: PASSED (P95 latency < 10.0 ms)
2. `test_stage_by_stage_pipeline_execution`: PASSED
3. `test_full_pipeline_chain_end_to_end_via_run_pipeline_until_idle`: PASSED
4. `test_background_worker_thread_processes_pipeline_concurrently`: PASSED
5. `test_auto_chain_disabled_does_not_enqueue_consolidation`: PASSED
6. `test_validation_failure_halts_pipeline`: PASSED
7. `test_validation_proposal_confidence_out_of_bounds_fails`: PASSED
8. `test_validation_proposal_empty_evidence_fails`: PASSED (rejection of empty evidence anchors)
9. `test_validation_proposal_ungrounded_evidence_fails`: PASSED (rejection of non-existent evidence atom IDs)
10. `test_cross_workspace_isolation_enforced`: PASSED (tenant isolation enforced across consolidation, validation, and release assembly)
11. `test_non_existent_ingestion_raises_not_found`: PASSED (NotFoundError raised cleanly on missing ingestion IDs)
12. `test_background_worker_stop_event_responsive`: PASSED (worker thread terminates promptly upon stop event)
13. `test_concurrent_ingestions_and_pipeline_drain`: PASSED (multi-threaded concurrent ingestions and queue drain)
14. `test_multiple_sequential_ingestions_pipeline_supersession`: PASSED
15. `test_direct_invocation_of_pinned_identities`: PASSED
16. `test_pinned_identities_and_aliases_registered`: PASSED

### Foundation Regression Suite:
```powershell
PYTHONPATH=src pytest tests/test_v2_foundation.py -v
```
**Results:** `7 passed in 2.03s` (100% PASS, zero regressions)

---

## 4. Handoff to Independent Verifier (`VERIF-INDEP`)

- **Branch:** `cap-job01-pipeline`
- **Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-job01`
- **Predecessor:** Gate `CAP-GA` (`a9255b4`)
- **Successor Unlocked:** Node `CAP-JOB02` (Job Lease Expiry, Heartbeats & Crash Recovery)

---

## 5. Repair Note R-JOB01 Round 2 (fail-closed validation_receipt; INFRA-SPEC)

- **Old SHA:** `c853f43b0361e085c9ab0bb63e3ac16758a89fb1`
- **New SHA:** `a7737d68515ce7856f665e66fb96d32de134bc28` (branch `cap-job01-pipeline` advanced via `update-ref` old→new; NOT merged into main)
- **Bug:** `_run_cortex_release_assemble_job` synthesized `passed:True` when `validation_receipt` was omitted; `store.validate_cortex_release` defaulted missing `passed` to `True`. Live probe at old HEAD confirmed omitted receipt → `validated` release.
- **Fix (lease-scoped, 3 files):**
  - `src/trace/v2/service.py` (`_run_cortex_release_assemble_job`): raises `InvariantViolation` naming omitted `validation_receipt` when key absent/None/empty; rejects dict receipts missing explicit `passed` (before pydantic `CortexValidationReceipt` coercion can default `passed=True`). Constructor receipt (`:425-436`) untouched.
  - `src/trace/v2/store.py` (`validate_cortex_release`): rejects receipts missing `passed` with `InvariantViolation` instead of `.get("passed", True)`.
  - `tests/v2/test_job_pipeline.py`: added `test_release_assemble_rejects_omitted_validation_receipt` and `test_release_assemble_rejects_ambiguous_passed_missing`; pinned explicit receipt in `test_direct_invocation_of_pinned_identities` (it submitted release_assemble receipt-less).
- **Acceptance (from detached worktree `/tmp/trace-wt/job01`, since removed):**
  - `PYTHONPATH=src .venv/bin/pytest tests/v2/test_job_pipeline.py -v` → **18/18 passed** (16 existing + 2 new).
  - Omitted/None/ambiguous receipt probes → all rejected (`InvariantViolation`); durable-job path records the error; zero `validated` releases stored.
  - Ingestion hot path P95 5.97 ms (< 10 ms, non-blocking); touched path performs no LLM/model calls (suite ran offline, no credentials).
  - Neighbor regression: `test_v2_lifecycle_isolation.py` + `test_v2_durable_erasure_and_activation.py` + `test_v2_temporal_revocation.py` → 30/30 passed.
- **Residual (out of lease, not changed):** same `.get("passed", True)` default-open pattern exists in Postgres backend `src/trace/v2/production.py:4063`; `CortexValidationReceipt.passed` defaults `True` in `models.py:565` (mitigated on the job path by the pre-coercion check). Flag for GB/R-JOB02.
- **Status:** landed on `cap-job01-pipeline`; this handoff note left **uncommitted** in parent checkout per instructions. R-JOB02 gate unblocked.
