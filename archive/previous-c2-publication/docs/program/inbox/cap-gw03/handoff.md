# Implementation Wave Handoff — WP-CAP-GW03 (Token Budget Reservation & Hard Spend Caps)

## 1. Identity

```yaml
packet_id: "WP-CAP-GW03"
work_packet_name: "Token Budget Reservation & Hard Spend Caps"
assigned_role: "GW-ECON (Economics Specialist)"
branch: "cap-gw03-budget"
status: "completed"
base_commit: "683cfe7"
governing_plan: "docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md"
execution_dag: "docs/program/02_EXECUTION_DAG.md"
invariants: "docs/program/01_INVARIANTS.md"
independent_verifier: "VERIF-INDEP"
```

## 2. Executive Summary

In strict accordance with `WP-CAP-GW03`, Program Invariants (`docs/program/01_INVARIANTS.md`), Clause `CAP-D010` ("Reconcile storage, latency, freshness, throughput, and cost prospectively by lane and service class"), and Clause `CAP-D011` ("Fail closed on missing models, invalid/empty output, unknown required identity, hidden fallback, incomplete denominators, and unavailable cost evidence"):

1. **Two-Phase Budget Reservation Protocol:**
   - Implemented `reserve_budget(workspace_id, model_id, estimated_tokens=1000, ...) -> BudgetReservation`: Preflight checks against workspace spend cap. If estimated cost breaches remaining dollar budget, raises `BudgetExceededError` before network invocation.
   - Implemented `settle_budget(reservation, receipt)`: Deducts actual `receipt.usd_cost` from remaining budget, records spent USD in workspace ledger, and releases reserved excess funds.
   - Implemented `release_reservation(reservation)`: Releases the entire reservation if an invocation aborts, fails, or times out, ensuring zero reserved funds leak.
   - Wired reservation lifecycle into `TraceModelGateway.call_json`, `call_with_audit`, and `select_navigation` with automatic exception release on provider failure, empty response, malformed JSON, uncited output, or missing usage telemetry.

2. **Zero-Cost Exemption for Local Models:**
   - Guaranteed local models (`is_local=True`, $0.00 cost, e.g. `qwen2.5-3b-local`, `all-MiniLM-L6-v2`, `llama-3.2-1b-local`) completely bypass dollar budget ceilings without failing even when the dollar budget is exhausted ($0.00 remaining or in deficit).
   - Local model reservations create $0.00 reservations and settle with $0.00 receipts without altering dollar balances.

3. **Thread-Safe, Crash-Safe, and Cross-Process Budget Ledger:**
   - Implemented `WorkspaceBudgetLedger` in `src/trace/v2/model_gateway.py` tracking `total_spent_usd`, `total_reserved_usd`, and `hard_cap_usd`.
   - Thread safety: Every ledger operation is synchronized via `threading.RLock()`.
   - Cross-process concurrency: Advisory POSIX file locking (`_FileLock` via `fcntl.flock`) and nanosecond disk timestamp sync (`_sync_from_disk_unlocked`) prevent state divergence and cap over-allocation across independent OS processes sharing the same ledger.
   - Crash safety: File-backed persistence writes atomic temporary files (`.tmp.<pid>.<uuid>`), flushes, fsyncs data and directory descriptors, and performs POSIX atomic rename (`os.replace`). Robust exception cleanup (`try...except BaseException`) ensures zero dangling `.tmp` files on filesystem errors or disk full (ENOSPC). Corrupted state files fail closed with `RuntimeError`.
   - Bounded memory: In-memory transaction `_history` is strictly bounded to prevent memory exhaustion in long-running processes.

4. **Error Taxonomy & Strict Input Validation:**
   - Introduced `BudgetExceededError(ModelPolicyDenied)` with fine-grained diagnostic attributes (`workspace_id`, `requested_cost_usd`, `available_budget_usd`, `hard_cap_usd`, `total_spent_usd`, `total_reserved_usd`).
   - Retained 100% backward compatibility with existing callers catching `ModelPolicyDenied` and `ModelGatewayError`.
   - Hardened boundary checking: Rejects `NaN`, `Inf`, boolean spoofing, negative output tokens, and zero-cost cloud reservations. Rejects foreign workspace reservations and unregistered reservations. Enforces preflight validation in `call_json` to prevent executing models on stale, settled, released, or locality-mismatched reservations.

5. **Comprehensive Test Suite:**
   - Authored `tests/v2/test_budget_cap.py` with 53 unit tests covering preflight reservation, two-phase settlement and excess release, hard cap rejection with `BudgetExceededError`, unreserved budget release on all gateway failure modes, local model zero-cost exemption under $0.00 cap / budget exhaustion, multi-threaded and cross-process concurrency safety without over-allocation, crash-safe persistence and reload, tempfile cleanup on error, and strict type/boundary validation.
   - Verified 100% pass across all 131 gateway tests (53 budget cap + 54 model cost + 24 failclosed) and all 339 tests in the repository test suite with zero regressions.

---

## 3. Scope of Mutation & Lease Adherence

### Exclusive Writable File Lease Paths
- `src/trace/v2/model_gateway.py`
- `tests/v2/test_budget_cap.py`
- `docs/program/inbox/cap-gw03/handoff.md`

### Read-Only Context Inspected
- `src/trace/v2/types.py`
- `tests/v2/test_model_cost.py`
- `tests/v2/test_model_gateway_failclosed.py`
- `docs/program/01_INVARIANTS.md`
- `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` (Section 3.1 & Clause CAP-D010, CAP-D011)

No files outside the authorized lease were modified.

---

## 4. Verification Commands & Results

### 1. New Budget Reservation & Spend Cap Test Suite
```bash
PYTHONPATH=src ./.venv/bin/pytest tests/v2/test_budget_cap.py -v
```
**Output:**
```text
============================== 53 passed in 5.07s ==============================
```

### 2. Regression Cost and Fail-Closed Test Suites
```bash
PYTHONPATH=src ./.venv/bin/pytest tests/v2/test_model_cost.py tests/v2/test_model_gateway_failclosed.py -v
```
**Output:**
```text
============================== 78 passed in 4.62s ==============================
```

### 3. Combined Gateway Test Execution
```bash
PYTHONPATH=src ./.venv/bin/pytest tests/v2/test_budget_cap.py tests/v2/test_model_cost.py tests/v2/test_model_gateway_failclosed.py -v
```
**Output:**
```text
============================= 131 passed in 5.39s ==============================
```

### 4. Repository-Wide Full Test Suite
```bash
PYTHONPATH=src ./.venv/bin/pytest tests/ -v
```
**Output:**
```text
======================= 339 passed in 637.34s (0:10:37) ========================
```

### 5. Programmatic Acceptance Assertion
```bash
PYTHONPATH=src ./.venv/bin/python -c "
from trace.v2.model_gateway import (
    WorkspaceBudgetLedger,
    BudgetExceededError,
    get_workspace_budget_ledger,
    reset_budget_ledgers,
)

reset_budget_ledgers()
ledger = WorkspaceBudgetLedger('ws-test', hard_cap_usd=0.0)
assert ledger.is_exhausted is True

# 1. Local model must succeed under $0.00 cap
local_res = ledger.reserve_budget('qwen2.5-3b-local', estimated_tokens=5000)
assert local_res.is_local is True
assert local_res.reserved_cost_usd == 0.0

# 2. Cloud model must raise BudgetExceededError under $0.00 cap
try:
    ledger.reserve_budget('deepseek-v4-flash', estimated_tokens=1000)
    assert False, 'Expected BudgetExceededError'
except BudgetExceededError as e:
    assert e.available_budget_usd == 0.0

print('Token Budget Reservation & Hard Spend Cap Invariants Verified.')
"
```
**Output:**
```text
Token Budget Reservation & Hard Spend Cap Invariants Verified.
```

---

## 5. Handoff to Independent Verifier

The branch `cap-gw03-budget` is fully implemented, hardened against cross-process concurrency and input boundary corruption, verified, and ready for detached independent verification by `VERIF-INDEP`.
