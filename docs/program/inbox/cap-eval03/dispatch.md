# WP-CAP-EVAL03 Dispatch Briefing & Prompt: Detached Faithfulness Validator

- **Node ID:** `CAP-EVAL03`
- **Work Packet:** `WP-CAP-EVAL03`
- **Assigned Role:** Evaluation Specialist (`EVAL-SPEC`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-eval03` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-eval03`)
- **Branch:** `cap-eval03-faithfulness`
- **Base Commit:** `587aa514e254bc33a5bc18b90ce399cf602992ef` (`cap-eval02-datasets`)
- **Lease ID:** `lease-cap-eval03-20260903T144000Z`
- **Issued UTC:** `2026-09-03T14:40:00Z`
- **Governing Directives:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§4B), `CAP_001_BENCHMARK_METHODOLOGY_ANNEX.md` (§§1–5 binding), `CAP_001_WAVEB_DIRECTIVES.md` (Directive D2)
- **Status:** ACTIVE_DISPATCHED

---

## 1. Verbatim Copy-Paste Implementer Prompt

The following block is self-contained and copy-paste ready for the Evaluation Specialist subagent session:

```text
================================================================================
TRACE-CAP-001 BOOTSTRAP PREAMBLE (MANDATORY INSTRUCTION)
================================================================================
You are a bounded, role-isolated participant in the Trace Cognitive Architecture
Correction Program (TRACE-CAP-001).

WORKSPACE ROOT: C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/
GOVERNING PLAN: docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md
EXECUTION DAG:  docs/program/CAP_001_EXECUTION_DAG.md
LEASE MAP:      docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md
GATE MATRIX:    docs/program/CAP_001_GATE_MATRIX.md
METHODOLOGY:    docs/program/launch/CAP_001_BENCHMARK_METHODOLOGY_ANNEX.md (§§1-5 binding)
WAVE-B STATE:   docs/program/launch/CAP_001_PROGRAM_STATE_CHECKPOINT.md

OPERATING CONSTRAINTS:
1. Do not rely on prior chat context. Repository files + this packet are your
   sole instructions.
2. Spine tables (atoms, events, source_blobs, WAL) are CANONICAL and IMMUTABLE.
   Vectors, indexes, summaries, holons, relations are DERIVED PROJECTIONS.
3. Fail closed on missing identities, empty model responses, broken anchors,
   unrecorded costs, or count/checksum mismatches. Never invent a workaround.
4. You are strictly bound to your assigned Work Packet and Exclusive File Lease.
   Editing files outside your lease is a critical violation that aborts the session.
5. You CANNOT approve your own work, certify a gate, change a threshold, launch
   a scale run ≥10K documents, spend provider funds, or merge into main.
6. One session = one packet. Terminate after filing your handoff receipt.
================================================================================

ROLE: Evaluation Specialist (EVAL-SPEC) | TOOL: AGY CLI (subagent, Workspace=inherit)
WORK PACKET: WP-CAP-EVAL03 | WORKTREE: isolated branch cap-eval03-faithfulness
LEASE (exclusive): benchmarks/evaluators/faithfulness_validator.py,
tests/evaluators/test_faithfulness.py. Do NOT touch candidate generation code.

OBJECTIVE: Build the detached validator per methodology annex §4 (binding):
atomic proposition extraction → source-atom span alignment → NLI/entailment
scoring at τ = 0.95 → ValidationReceipt(passed, support_ratio).
CALIBRATION (part of this packet, not later): frozen hallucination set
(unsupported entities, invented numbers, cross-atom splices) must reject at
100%; dual-adjudicated sample ≥ 200 propositions with Cohen's κ reported
(κ < 0.70 = rework the extractor, never lower the threshold); NLI model must
share no weights/data/revision with any generator under test.

ACCEPTANCE: pytest tests/evaluators/test_faithfulness.py -v (100% pass)
plus calibration log attached to the handoff.
DELIVERABLE: commit + handoff in docs/program/inbox/cap-eval03/handoff.md.
BEGIN WORK.
```

---

## 2. Exclusive File Lease & Boundaries

- **Allowed Paths:**
  - `benchmarks/evaluators/faithfulness_validator.py`
  - `tests/evaluators/test_faithfulness.py`
  - `docs/program/inbox/cap-eval03/handoff.md`
- **Strictly Prohibited Paths:**
  - `src/trace/v2/` (Production runtime code)
  - `benchmarks/data/` (Immutable ground-truth corpora)
  - `benchmarks/manifests/` (Frozen anchor manifests)

---

## 3. Specific Technical & Calibration Invariants

1. **Detached Validation Pipeline (`benchmarks/evaluators/faithfulness_validator.py`):**
   - Atomic proposition extraction: decomposes summary/answer text into independent verifiable assertions.
   - Source-atom span alignment: grounds each proposition against source atom spans.
   - NLI / Entailment scoring: threshold $\tau = 0.95$.
   - Output Schema: `ValidationReceipt(passed: bool, support_ratio: float, details: dict)`.
2. **Mandatory Calibration Invariants (Methodology Annex §4):**
   - Adversarial hallucination set: must reject 100% of unsupported entities, invented numbers, and cross-atom false splices.
   - Dual-adjudicated proposition sample: $\ge 200$ test propositions with Cohen's $\kappa$ reported ($\kappa \ge 0.70$ required; $\kappa < 0.70 \Rightarrow$ rework extractor, never lower threshold).
   - Generator independence: NLI scoring model must share zero weights, training data, or revision with any generator under test.
3. **Acceptance Command:**
   ```bash
   PYTHONPATH=src:. /home/anshul/.venv/trace/bin/pytest tests/evaluators/test_faithfulness.py -v
   ```
4. **Deliverable Receipt:**
   - Handoff receipt filed at `docs/program/inbox/cap-eval03/handoff.md` with attached calibration log.
