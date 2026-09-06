# Implementation Wave Handoff — WP-CAP-GW01 (Gateway Fail-Closed Hardening)

## 1. Identity

```yaml
packet_id: "WP-CAP-GW01"
work_packet_name: "Gateway Fail-Closed Hardening"
assigned_role: "GW-SPEC (Gateway Safety Specialist)"
branch: "cap-gw01-failclosed"
status: "completed"
base_commit: "a9255b4"
governing_plan: "docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md"
execution_dag: "docs/program/CAP_001_EXECUTION_DAG.md"
lease_map: "docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md"
independent_verifier: "VERIF-INDEP"
```

## 2. Executive Summary

In strict accordance with `WP-CAP-GW01`, Program Invariants (`docs/program/01_INVARIANTS.md`), and Clause `CAP-D011` ("Fail closed on missing models, invalid/empty output, unknown required identity, hidden fallback, incomplete denominators, and unavailable cost evidence"):

1. **Hard Purge of Manufactured Fallbacks:**
   - Completely purged lines 581–600 in `src/trace/v2/model_gateway.py` where fake schemas (`"TechnicalArchitecture"`), fake renderings (`"Evidence-grounded architectural specification."`), or arbitrary candidates (`selected_ids`) were manufactured on empty/malformed responses.
   - Removed ungrounded fallback in `_normalize_dict_keys` where missing `"rendering"` was synthesized from arbitrary string values or full JSON dumps.
   - Removed plain-text passthrough in `_extract_json_payload` that bypassed JSON validation for `"rendering"`.
   - Verified that zero manufactured fallbacks remain anywhere in `src/trace/v2/model_gateway.py`.

2. **Explicit Fail-Closed Exception Taxonomy:**
   - Implemented `ModelEmptyResponseError(ModelGatewayError)`: Raised when the model returns an empty or whitespace-only response.
   - Implemented `ModelMalformedJsonError(ModelGatewayError)`: Raised when JSON parsing fails or does not match payload schema boundaries.
   - Implemented `ModelUncitedOutputError(ModelGatewayError)`: Raised when an extractive/synthesizing output lacks required evidence anchors or references ungrounded anchors.

3. **Audit Persistence and Failure Logging:**
   - Updated `TraceModelGateway._persist_audit` and `ModelCallAudit` to record:
     - `status`: `"failed"` on any failure, `"succeeded"` on valid completion.
     - `policy_outcome`: Exact categorization (`"empty_response"`, `"malformed_json"`, `"uncited_output"`, `"provider_failed"`).
     - Wall-clock duration: Tracked via high-resolution `time.perf_counter()` and recorded as `wall_clock_duration` (seconds) and `duration_ms` (milliseconds).
   - Added standard library logger warnings capturing `status=failed`, `policy_outcome`, model ID, purpose, and duration metrics.

4. **Comprehensive Test Suite:**
   - Authored `tests/v2/test_model_gateway_failclosed.py` with 24 dedicated negative and invariant tests verifying that empty responses, malformed JSON, missing schema properties, type mismatches, missing evidence anchors, ungrounded anchors, and provider failures strictly raise typed exceptions without synthetic fallbacks.
   - Verified that existing regression tests in `tests/test_v2_llm_gateway.py` continue to pass 100% (7/7 pass).

---

## 3. Scope of Mutation & Lease Adherence

### Exclusive Writable File Lease Paths
- `src/trace/v2/model_gateway.py`
- `tests/v2/test_model_gateway_failclosed.py`

### Read-Only Context Inspected
- `src/trace/v2/models.py`
- `docs/program/01_INVARIANTS.md`
- `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` (Section 3.1 & Clause CAP-D011)
- `docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md`
- `docs/program/CAP_001_WORK_PACKETS_WAVE_A_B.md`

No files outside the authorized lease were modified.

---

## 4. Verification Commands & Results

### 1. New Fail-Closed Test Suite
```bash
PATH=/tmp/trace-venv/bin:$PATH PYTHONPATH=src pytest tests/v2/test_model_gateway_failclosed.py -v
```
**Output:**
```text
============================== 24 passed in 2.16s ==============================
```

### 2. Regression Gateway Test Suite
```bash
PATH=/tmp/trace-venv/bin:$PATH PYTHONPATH=src pytest tests/test_v2_llm_gateway.py -v
```
**Output:**
```text
============================== 7 passed in 1.69s ===============================
```

### 3. Combined Test Execution
```bash
PATH=/tmp/trace-venv/bin:$PATH PYTHONPATH=src pytest tests/v2/test_model_gateway_failclosed.py tests/test_v2_llm_gateway.py -v
```
**Output:**
```text
============================== 31 passed in 2.33s ==============================
```

### 4. Zero Manufactured Fallbacks Audit
```bash
grep -rn "TechnicalArchitecture" src/trace/v2/model_gateway.py  # Zero results
grep -rn "Evidence-grounded" src/trace/v2/model_gateway.py     # Zero results
```

---

## 5. Handoff to Independent Verifier

This packet is complete and ready for independent verification by `VERIF-INDEP`:
- Branch: `cap-gw01-failclosed`
- Verification commands:
  - `pytest tests/v2/test_model_gateway_failclosed.py -v` (Expect: 100% PASS)
  - `pytest tests/test_v2_llm_gateway.py -v` (Expect: 100% PASS)
- Unblocks downstream DAG node: `CAP-GW02` (Model Registry & Cost Telemetry) and `CAP-CRX02` (Cortex Consolidator).
