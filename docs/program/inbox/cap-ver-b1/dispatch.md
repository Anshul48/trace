# VERIF-B1 Dispatch Briefing & Prompt: Codex Independent Verifier, Batch 1

- **Session ID:** `dispatch-verif-b1-20260903T144000Z`
- **Target Nodes:** `CAP-RET02`, `CAP-CRX02`, `CAP-JOB01`
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Tooling:** Codex CLI / Detached Worktree Execution
- **Worktree Root:** `C:/Users/anshu/AppData/Local/trace-worktrees/` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/`)
- **Issued UTC:** `2026-09-03T14:40:00Z`
- **Governing Directives:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§2)
- **Status:** ACTIVE_DISPATCHED

---

## 1. Verbatim Copy-Paste Verifier Prompt

The following block is self-contained and copy-paste ready for the independent Codex verification session:

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

ROLE: Codex Independent Verifier (VERIF-INDEP) | TOOL: Codex CLI
TARGETS (verify each independently, one receipt per node):
- CAP-RET02, branch cap-ret02-fusion (expect ~94afcf3), worktree trace-ret02
- CAP-CRX02, branch cap-crx02-consolidator (expect ~45c3591), worktree trace-crx02
- CAP-JOB01, branch cap-job01-pipeline (expect ~c853f43), worktree trace-job01
WORKTREE ROOT: C:/Users/anshu/AppData/Local/trace-worktrees/

PROCEDURE per node:
1. Fresh detached checkout of the candidate branch. Record commit SHA.
2. Lease conformance: `git diff <base> --name-only` must stay inside the
   node's lease (RET02: retrieval.py RRF section + test_hybrid_retrieval.py;
   CRX02: organization.py + cortex_consolidator.py + test_cortex_consolidator.py;
   JOB01: service.py job-chaining section + test_job_pipeline.py).
   Any file outside lease = FAIL.
3. Run acceptance commands, all must exit 0 with 100% pass:
   RET02:  $env:PYTHONPATH='src'; pytest tests/v2/test_hybrid_retrieval.py tests/v2/test_retrieval_embedding.py -v
   CRX02:  $env:PYTHONPATH='src'; pytest tests/v2/test_cortex_consolidator.py -v
   JOB01:  $env:PYTHONPATH='src'; pytest tests/v2/test_job_pipeline.py -v
4. Negative assertions: RET02 — confirm no [:300] truncation remains on the
   retrieval path and RRF k=60 bit-exact; CRX02 — extractive_control output
   byte-identical to legacy clipping; JOB01 — ingestion hot path <10ms and
   zero blocking on LLM (fail the node if any synthetic fallback exists).
5. Write receipt per node to docs/program/inbox/<node>/verification_receipt.json
   (schema §12). PASS only if steps 2–4 all hold. Sign with session + UTC time.
BEGIN with CAP-RET02.
```

---

## 2. Target Candidates & Worktrees

1. **CAP-RET02 (BM25 + Dense RRF Fusion, k=60):**
   - **Branch:** `cap-ret02-fusion`
   - **Commit:** `94afcf3b358c351ac7a71e466a18fca67c32e81a` (expect `~94afcf3`)
   - **Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-ret02` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-ret02`)
   - **Base Ref:** `cap-ret01-embedding` (`9f90ac8`) / `main` (`a9255b4`)
   - **Exclusive Lease:** `src/trace/v2/retrieval.py` (RRF section only), `tests/v2/test_hybrid_retrieval.py`
   - **Acceptance Command:**
     - Windows PowerShell: `$env:PYTHONPATH='src'; pytest tests/v2/test_hybrid_retrieval.py tests/v2/test_retrieval_embedding.py -v`
     - Linux / Bash: `PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_hybrid_retrieval.py tests/v2/test_retrieval_embedding.py -v`
   - **Negative Assertions:** Confirm zero `[:300]` truncation remains on retrieval path; assert RRF `k=60` bit-exact calculation; test fallback when dense unpopulated.

2. **CAP-CRX02 (Consolidator Engine Refactor):**
   - **Branch:** `cap-crx02-consolidator`
   - **Commit:** `45c359118991bb6670092baf36cee3f573fc6454` (expect `~45c3591`)
   - **Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx02` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-crx02`)
   - **Base Ref:** `cap-crx01-schema` (`59ce53a`) / `main` (`a9255b4`)
   - **Exclusive Lease:** `src/trace/v2/organization.py`, `src/trace/v2/cortex_consolidator.py`, `tests/v2/test_cortex_consolidator.py`
   - **Acceptance Command:**
     - Windows PowerShell: `$env:PYTHONPATH='src'; pytest tests/v2/test_cortex_consolidator.py -v`
     - Linux / Bash: `PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_cortex_consolidator.py -v`
   - **Negative Assertions:** Assert `extractive_control` output is byte-identical to legacy clipping (`test_build_delta_exact_parity`); assert invalid schema and ungrounded entities fail closed.

3. **CAP-JOB01 (Ingestion-to-Consolidation Pipeline):**
   - **Branch:** `cap-job01-pipeline`
   - **Commit:** `c853f43b0361e085c9ab0bb63e3ac16758a89fb1` (expect `~c853f43`)
   - **Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-job01` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-job01`)
   - **Base Ref:** `main` (`a9255b4`)
   - **Exclusive Lease:** `src/trace/v2/service.py` (job chaining section only), `tests/v2/test_job_pipeline.py`
   - **Acceptance Command:**
     - Windows PowerShell: `$env:PYTHONPATH='src'; pytest tests/v2/test_job_pipeline.py -v`
     - Linux / Bash: `PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_job_pipeline.py -v`
   - **Negative Assertions:** Raw atom ingestion hot path `<10ms` and zero blocking on LLM (`test_raw_atom_ingestion_returns_under_10ms_nonblocking`). Fail closed on synthetic fallbacks.

---

## 3. Deliverable Receipts
Per Universal Schema in `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` §12:
- `docs/program/inbox/cap-ret02/verification_receipt.json`
- `docs/program/inbox/cap-crx02/verification_receipt.json`
- `docs/program/inbox/cap-job01/verification_receipt.json`
