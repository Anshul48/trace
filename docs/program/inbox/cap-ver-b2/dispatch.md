# VERIF-B2 Dispatch Briefing & Prompt: Codex Independent Verifier, Batch 2

- **Session ID:** `dispatch-verif-b2-20260903T144000Z`
- **Target Nodes:** `CAP-JOB02`, `CAP-CRX03`, `CAP-EVAL02`
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Tooling:** Codex CLI / Detached Worktree Execution
- **Worktree Root:** `C:/Users/anshu/AppData/Local/trace-worktrees/` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/`)
- **Issued UTC:** `2026-09-03T14:40:00Z`
- **Governing Directives:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§3), `docs/program/launch/CAP_001_WAVEB_DIRECTIVES.md` (Directives D1, D3)
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
TARGETS:
- CAP-JOB02, branch cap-job02-recovery, worktree trace-job02
- CAP-CRX03, branch cap-crx03-activation (expect ~824222e), worktree trace-crx03
- CAP-EVAL02, branch cap-eval02-datasets (expect ~587aa51), worktree trace-eval02

PROCEDURE per node (fresh detached checkout + lease check + tests first):
  JOB02:  $env:PYTHONPATH='src'; pytest tests/v2/test_job_recovery.py -v
  CRX03:  $env:PYTHONPATH='src'; pytest tests/v2/test_cortex_activation.py -v
  EVAL02: $env:PYTHONPATH='src'; pytest tests/v2/test_eval_datasets.py -v
          python benchmarks/verify_dataset_checksums.py --manifest benchmarks/manifests/beir_musique_frozen_v1.json

EXTRA CHECKS (these are the reason Batch 2 is separate):
1. LEASE-OVERLAP AUDIT (JOB02 × CRX03): both nodes lease service.py + store.py.
   Diff both branches against base and against each other. If hunks overlap or
   touch the same functions, mark both receipts "PASS_WITH_MERGE_RISK" (never
   silent PASS) and name the conflicting hunks. The coordinator merges JOB02
   first per Directive D3; CRX03 rebases onto it before its own clearance.
2. SCIFACT COUNT AUDIT (EVAL02, Directive D1): read the manifest's SciFact
   query count and archive MD5. Canonical BEIR SciFact test = 300 queries,
   MD5 5f7d1de60b170fc8027bb7898e2efca1. If manifest claims 1,000 with a named
   split + checksum + actual counts recorded → PASS with a note. If 1,000 with
   no verifiable split identity → FAIL the node back to EVAL-SPEC, do not PASS.
   Apply the same check to NFCorpus/323 and FiQA/648 (MD5s in annex §1.1).
3. CRX03 rollback proof: crash-injection log must show predecessor-release
   restoration with zero dangling aliases; otherwise FAIL.
Receipts to docs/program/inbox/<node>/verification_receipt.json (schema §12).
BEGIN with CAP-JOB02.
```

---

## 2. Mandatory Extra Audits: Specific Findings & Verifier Criteria

### A. Lease-Overlap Audit (`JOB02 × CRX03`, Directive D3)
- **Shared File Paths:** `src/trace/v2/service.py` and `src/trace/v2/store.py`.
- **Hunk Disjointness Analysis (against merge base `a9255b4`):**
  - In `src/trace/v2/service.py`:
    - `JOB02` modifies lines 12–906: Background job queue ingestion, worker loops, worker heartbeats, 300s lease expiry, and dead-letter routing.
    - `CRX03` modifies lines 3628–3810: Risk-tiered projection activation, staged proposal review, and atomic release pointer swaps.
  - In `src/trace/v2/store.py`:
    - `JOB02` modifies lines 50, 557, 898, and 5330–5776: SQLite job state persistence, lease expiration queries, and retry/dead-letter tables.
    - `CRX03` modifies lines 806 and 3847–4196: Cortex release table pointer updates, atomic transaction swap, and rollback restoration.
  - Three-way merge validation (`git merge-tree cap-job02-recovery cap-crx03-activation`) exits cleanly with code 0 (`tree 6598d878ffa5a341dd558f5f4aff355979dbb37f`).
- **Verifier Mandate:**
  - Mark receipts for both `CAP-JOB02` and `CAP-CRX03` with `verdict: "PASS_WITH_MERGE_RISK"`.
  - Name the overlapping files (`src/trace/v2/service.py` and `src/trace/v2/store.py`).
  - Document that per Directive D3 serialization, `JOB02` will be merged first into `wave-b-candidate`, and `CRX03` must rebase onto `cap-job02-recovery` prior to final merge clearance.

### B. SciFact Count Audit (`EVAL02`, Directive D1)
- Inspect `benchmarks/manifests/beir_musique_frozen_v1.json` on disk:
  - **SciFact:** Canonical BEIR test split = **300 queries** (archive MD5 `5f7d1de60b170fc8027bb7898e2efca1`, query file SHA-256 `703117bad47dd87bbd17fc56ca197f2e2453fc208f1c8f602c3f3399135e693e`, qrels count 339).
  - **NFCorpus:** Canonical BEIR test split = **323 queries** (archive MD5 `a89dba18a62ef92f7d323ec890a0d38d`, qrels count 12,330).
  - **FiQA:** Canonical BEIR test split = **648 queries** (archive MD5 `17918ed23cd04fb15047f73e6c3bd9d9`, qrels count 1,706).
  - **MuSiQue:** Canonical multi-hop dev split = **500 queries** (archive MD5 `b231ff6cb584f3e6a2569e5900224213`, qrels count 1,329).
- Any discrepancy with unnamed splits or count $\ne 300$ for SciFact requires immediate node failure (`verdict: "FAIL"`).

### C. CRX03 Crash Rollback Proof
- Execute `PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_cortex_activation.py -k test_post_swap_crash_injection_restores_last_known_good_release -v`.
- Verify that simulated crash during active pointer swap cleanly restores the predecessor release with zero dangling aliases.

---

## 3. Deliverable Receipts
Per Universal Schema in `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` §12:
- `docs/program/inbox/cap-job02/verification_receipt.json`
- `docs/program/inbox/cap-crx03/verification_receipt.json`
- `docs/program/inbox/cap-eval02/verification_receipt.json`
