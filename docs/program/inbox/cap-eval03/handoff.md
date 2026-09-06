# WP-CAP-EVAL03 Handoff: Detached Faithfulness Validator

- **Node ID:** `CAP-EVAL03`
- **Work Packet:** `WP-CAP-EVAL03`
- **Role:** Evaluation Specialist (`EVAL-SPEC`)
- **Base Commit:** `587aa514e254bc33a5bc18b90ce399cf602992ef`
- **Candidate Commit SHA:** `d00cd0533c4353aa3b3bf9100c5492094ea09e51`
- **Candidate Tree Hash:** `5faf880ee4df64bf3705dd6c542eb0ae9ed63bb8`
- **Target Branch:** `cap-eval03-faithfulness`
- **Status:** COMPLETED / PASSED

---

## 1. Technical Invariants & Implementation Summary

1. **Detached Validation Pipeline** (`benchmarks/evaluators/faithfulness_validator.py`):
   - **Atomic proposition extraction**: Decomposes summary text into independent verifiable assertions, handling abbreviations (e.g. "U.S.", "i.e."), compound conjunctions, and numerical tokens.
   - **Source-atom span alignment**: Grounds propositions against source atom content, mapping character start/end offsets and lexical/semantic match scores.
   - **NLI entailment scoring at threshold $\\tau = 0.95$**: Directional entailment scoring gating support on $\\ge 0.95$.
   - **ValidationReceipt**: Durable dataclass with `passed` (bool), `support_ratio` (float), and `details` (dict), supporting both attribute and dict-style indexing.

2. **Mandatory Calibration Invariants (Methodology Annex §4)**:
   - **Adversarial Hallucination Rejection**: Evaluated on frozen adversarial hallucination set across unsupported entities, invented numbers, and cross-atom false splices. **15/15 rejected (100% rejection rate)**.
   - **Dual-Adjudicated Proposition Sample**: Evaluated on $N = 210$ sample ($N \\ge 200$). **Cohen's $\\kappa = 0.9195 \\ge 0.70$**, verified bit-identically against `sklearn.metrics.cohen_kappa_score`. Validator consensus accuracy: $85.71\\%$.
   - **Generator Independence**: Judge model identity and weights verified to share zero lineage with generator under test. Direct matches or lineage sharing raise explicit exceptions.

---

## 2. Calibration Log

```text
Calibration Run Summary:
------------------------
Adversarial Hallucination Set:
  Total Cases: 15
  Rejected Cases: 15
  Rejection Rate: 100.0%
  Status: PASS

Dual-Adjudicated Proposition Sample:
  Sample Size: 210 (required >= 200)
  Cohen's Kappa: 0.919540 (required >= 0.70)
  Sklearn Verification: 0.919540 (exact match)
  Consensus Accuracy: 85.71%
  Status: PASS

Generator Independence:
  Judge: cross-encoder/nli-deberta-v3-base
  Generator: deepseek-v4-flash -> ALLOWED (independent)
  Generator: cross-encoder/nli-deberta-v3-base -> REJECTED (ValueError raised)
  Status: PASS
```

---

## 3. Test Execution Log

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0 -- /tmp/trace-ret02-venv/bin/python
cachedir: .pytest_cache
rootdir: /tmp/trace-wt/eval03
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 11 items

tests/evaluators/test_faithfulness.py::test_atomic_proposition_extraction_simple_and_compound PASSED [  9%]
tests/evaluators/test_faithfulness.py::test_atomic_proposition_extraction_abbreviations_and_numbers PASSED [ 18%]
tests/evaluators/test_faithfulness.py::test_atomic_proposition_extraction_edge_cases PASSED [ 27%]
tests/evaluators/test_faithfulness.py::test_source_span_alignment_offsets_and_scoring PASSED [ 36%]
tests/evaluators/test_faithfulness.py::test_source_span_alignment_unmatched PASSED [ 45%]
tests/evaluators/test_faithfulness.py::test_validation_receipt_schema_conformance PASSED [ 54%]
tests/evaluators/test_faithfulness.py::test_strict_tau_0_95_threshold_enforcement PASSED [ 63%]
tests/evaluators/test_faithfulness.py::test_frozen_adversarial_hallucination_100_percent_rejection PASSED [ 72%]
tests/evaluators/test_faithfulness.py::test_dual_adjudicated_sample_size_and_cohens_kappa PASSED [ 81%]
tests/evaluators/test_faithfulness.py::test_generator_independence_invariant PASSED [ 90%]
tests/evaluators/test_faithfulness.py::test_fail_closed_on_empty_and_corrupt_inputs PASSED [100%]

============================== 11 passed in 1.91s ==============================
```
