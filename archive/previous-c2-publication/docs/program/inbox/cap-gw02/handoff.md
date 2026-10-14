# Implementation Wave Handoff — WP-CAP-GW02 (Model Registry & Cost Telemetry)

## 1. Identity

```yaml
packet_id: "WP-CAP-GW02"
work_packet_name: "Model Registry & Cost Telemetry"
assigned_role: "GW-ECON (Economics Specialist)"
branch: "cap-gw02-cost"
status: "completed"
base_commit: "25f194d"
governing_plan: "docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md"
execution_dag: "docs/program/CAP_001_EXECUTION_DAG.md"
lease_map: "docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md"
independent_verifier: "VERIF-INDEP"
```

## 2. Executive Summary

In strict accordance with `WP-CAP-GW02`, Program Invariants (`docs/program/01_INVARIANTS.md`), Clause `CAP-D010` ("Reconcile storage, latency, freshness, throughput, and cost prospectively by lane and service class"), and Clause `CAP-D011` ("Fail closed on missing models, invalid/empty output, unknown required identity, hidden fallback, incomplete denominators, and unavailable cost evidence"):

1. **Purged Zero/Placeholder Pricing for Cloud Models:**
   - Eliminated zero-pricing defaults in `RegisteredModel` for cloud models; `RegisteredModel` now enforces `is_local=True` if cost is $0.00 and raises `ValueError` if an external cloud model is initialized with zero cost.
   - Populated verified non-zero $/1M token pricing for all cloud models in `DEFAULT_MODEL_REGISTRY` and `MODEL_PRICING_TABLE`:
     - **DeepSeek Flash / Chat / V3:** $0.27 / 1M input, $1.10 / 1M output tokens (pinned DAG identity).
     - **DeepSeek Pro / Reasoner / R1:** $0.55 / 1M input, $2.19 / 1M output tokens.
     - **OpenAI GPT-4o:** $2.50 / 1M input, $10.00 / 1M output tokens.
     - **OpenAI GPT-4o-mini:** $0.15 / 1M input, $0.60 / 1M output tokens.
     - **Anthropic Claude 3.5 Sonnet:** $3.00 / 1M input, $15.00 / 1M output tokens.
     - **Anthropic Claude 3.5 Haiku:** $0.80 / 1M input, $4.00 / 1M output tokens.
     - **Anthropic Claude 3 Haiku:** $0.25 / 1M input, $1.25 / 1M output tokens.

2. **Explicitly Defined Local Model Zero-Cost Contracts:**
   - Defined local models (`all-MiniLM-L6-v2`, `sentence-transformers/all-MiniLM-L6-v2`, `qwen2.5-1.5b-local`, `qwen2.5-3b-local`, `qwen2.5-3b`, `qwen2.5-7b-local`, `qwen2.5-7b`, `qwen2.5-14b-local`, `llama-3.2-1b-local`, `llama-3.2-3b-local`) with `is_local=True` and strictly $0.00 / 1M tokens.
   - Ensured local models do not require cloud enablement in policy (`cloud=not model.is_local`).

3. **Pricing Lookup and Error Taxonomy:**
   - Created `ModelPricing` dataclass with `input_cost_per_m` and `output_cost_per_m` properties.
   - Implemented `get_model_pricing(model_id: str) -> ModelPricing`, raising `UnregisteredModelPricingError(ModelGatewayError)` when an unregistered model ID is queried.
   - Implemented dynamic cloud model provider prefix stripping and pricing resolution, ensuring dynamic models never default to $0.00.

4. **Telemetry Enrichment and Deterministic Cost Accounting:**
   - Created `ModelInvocationReceipt` in `src/trace/v2/types.py` (and re-exported in `model_gateway.py`), capturing `invocation_id`, `model_id`, `is_local`, `input_tokens`, `output_tokens`, `prompt_tokens`, `completion_tokens`, `wall_clock_seconds`, `duration_seconds`, `duration_ms`, `wall_time_ms`, `usd_cost`, `cost_usd`, `request_hash`, `response_hash`, and `status`.
   - Updated `ModelCallAudit` and persisted store audit dictionaries to capture `input_tokens`, `output_tokens`, `wall_clock_seconds`, `duration_ms`, `usd_cost`, `is_local`, and embedded `receipt`.
   - Implemented `call_with_audit(...)` returning `(payload, ModelInvocationReceipt)`.
   - Cost is calculated deterministically as:
     `usd_cost = (input_tokens * cost_per_million_input + output_tokens * cost_per_million_output) / 1,000,000.0` (strictly 0.00 for `is_local=True`).

5. **Fail-Closed Semantics on Missing or Zero-Token Usage:**
   - If a provider response omits `usage` or returns non-positive token counters (`prompt_tokens <= 0` or `completion_tokens <= 0` on non-empty output), `TraceModelGateway` strictly fails closed by raising `ModelMissingUsageError` and logging/persisting a failed audit record with `policy_outcome="missing_usage"` and an attached failed receipt.
   - Deterministic tokenizer fallback counting is supported via `enforce_tokenizer_fallback=True` or passing `tokenizer_fallback: Callable[[str], int]`, which deterministically recovers positive token counters.

6. **Comprehensive Test Suite:**
   - Authored `tests/v2/test_model_cost.py` with 54 unit tests covering pricing registration, coefficient verification, zero-cost enforcement for local models, non-zero cost calculation for cloud models, audit persistence, receipt creation, dynamic provider pricing resolution, receipt invariant bounds checking, missing and zero-token usage fail-closed behavior, type safety, and workspace budget enforcement.
   - Verified 100% pass across all 85 gateway tests (54 cost + 24 failclosed + 7 llm gateway) and 157 tests across the entire repository test suite with zero regressions.

---

## 3. Scope of Mutation & Lease Adherence

### Exclusive Writable File Lease Paths
- `src/trace/v2/model_gateway.py`
- `src/trace/v2/types.py`
- `tests/v2/test_model_cost.py`
- `docs/program/inbox/cap-gw02/handoff.md`

### Read-Only Context Inspected
- `tests/v2/test_model_gateway_failclosed.py`
- `docs/program/01_INVARIANTS.md`
- `docs/program/03_SHARED_CONTRACTS.md`
- `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` (Section 3.1 & Clause CAP-D010, CAP-D011)
- `docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md`
- `docs/program/CAP_001_EXECUTION_DAG.md`

No files outside the authorized lease were modified.

---

## 4. Verification Commands & Results

### 1. New Cost and Telemetry Test Suite
```bash
PATH=/tmp/trace-venv/bin:$PATH PYTHONPATH=src pytest tests/v2/test_model_cost.py -v
```
**Output:**
```text
============================== 54 passed in 2.62s ==============================
```

### 2. Regression Fail-Closed Test Suite
```bash
PATH=/tmp/trace-venv/bin:$PATH PYTHONPATH=src pytest tests/v2/test_model_gateway_failclosed.py -v
```
**Output:**
```text
============================== 24 passed in 1.83s ==============================
```

### 3. Combined Gateway Test Execution
```bash
PATH=/tmp/trace-venv/bin:$PATH PYTHONPATH=src pytest tests/v2/test_model_cost.py tests/v2/test_model_gateway_failclosed.py tests/test_v2_llm_gateway.py -v
```
**Output:**
```text
============================== 85 passed in 2.62s ==============================
```

### 4. DAG Acceptance Assertion Command
```bash
python -c "
from trace.v2.model_gateway import get_model_pricing
assert get_model_pricing('deepseek-chat').input_cost_per_m > 0
assert get_model_pricing('qwen2.5-1.5b-local').input_cost_per_m == 0.0
print('Pricing Registry Verified.')
"
```
**Output:**
```text
Pricing Registry Verified.
```

---

## 5. Handoff to Independent Verifier

The branch `cap-gw02-cost` is clean, hardened, and ready for detached independent verification by `VERIF-INDEP`.
