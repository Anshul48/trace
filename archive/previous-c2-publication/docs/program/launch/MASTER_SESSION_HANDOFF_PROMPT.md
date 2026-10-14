========================================================================================
TRACE-CAP-001 PROGRAM COORDINATOR MASTER CONTINUATION PROMPT: WAVE B CONVERGENCE
========================================================================================

You are the Program Coordinator (COORD) for Project Trace.
You are running as an autonomous orchestrator in AGY CLI to drive the execution of:
- Master Plan: docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md (TRACE-CAP-001)
- Execution DAG: docs/program/CAP_001_EXECUTION_DAG.md
- Work Packets: docs/program/CAP_001_WORK_PACKETS_WAVE_A_B.md
- Responsibility Leases: docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md
- Gate Matrix: docs/program/CAP_001_GATE_MATRIX.md
- Checkpoint Manifest: docs/program/launch/CAP_001_PROGRAM_STATE_CHECKPOINT.md

WORKSPACE ROOT: C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/
BASE COMMIT:    a9255b4 (Gate CAP-GA ratified, verified, and officially CLOSED)

----------------------------------------------------------------------------------------
1. EXECUTIVE PROGRAM STATE & WAVE B CONVERGENCE SCORECARD
----------------------------------------------------------------------------------------
All major Wave B implementations are COMPLETE across all 5 tracks:
- Six nodes have been officially verified & CLOSED by Codex Independent Verifier (VERIF-INDEP).
- Six successor packets are fully implemented, hardened, tested 100%, and ready for verification:

• TRACK 1 (Gateway Safety & Economics) — 100% CLOSED & VERIFIED:
  - CAP-GW01 (Fail-Closed Gateway Hardening): CLOSED (PASS). Receipt: rcpt-cap-gw01-verif-indep-20260903T031302Z (31/31 pass).
  - CAP-GW02 (Model Pricing & Telemetry): CLOSED (PASS). Receipt: rcpt-cap-gw02-verif-indep-20260903T045901Z (85/85 pass).
  - CAP-GW03 (Budget Reservation & Spend Caps): CLOSED (PASS). Receipt: rcpt-cap-gw03-verif-indep-20260903T073715Z (131/131 pass).

• TRACK 2 (Retrieval Baseline Restoration):
  - CAP-RET01 (Dense Embedding Adapter): CLOSED (PASS). Receipt: rcpt-cap-ret01-verif-indep-20260903T085449Z (24/24 pass).
  - CAP-RET02 (BM25 + Dense RRF Fusion): IMPLEMENTED & REBASED on commit 94afcf3 in worktree trace-ret02.
    39/39 tests pass (23 hybrid retrieval + 16 embedding adapter). Postings list truncation ([:300]) eliminated,
    bit-exact RRF (k=60) enforced, and abstention thresholding calibrated for CPU fallback. READY FOR VERIFICATION.

• TRACK 3 (Cortex Projections):
  - CAP-CRX01 (Cortex Schemas & Evidence Anchors): CLOSED (PASS). Receipt: rcpt-cap-crx01-verif-indep-20260903-59ce53a (56/56 pass on win32).
  - CAP-CRX02 (Consolidator Engine Refactor): IMPLEMENTED on branch cap-crx02-consolidator in worktree trace-crx02 (commit 45c3591).
    15/15 unit tests pass, 78/78 cortex regression tests pass. Refactored EvidenceHierarchyBuilder into cortex_consolidator.py
    with extractive control vs semantic SLM modes. READY FOR VERIFICATION.
  - CAP-CRX03 (Risk-Tiered Projection Activation): IMPLEMENTED on branch cap-crx03-activation in worktree trace-crx03 (commit 824222e).
    24/24 unit tests pass. Implemented Tier 1 auto-activation for navigation summaries, Tier 2/3 staged proposal review, and
    atomic journaled pointer swaps with crash rollback restoring predecessor release. READY FOR VERIFICATION.

• TRACK 4 (Job Infrastructure):
  - CAP-JOB01 (Ingestion-to-Consolidation Pipeline Chaining): IMPLEMENTED on branch cap-job01-pipeline in worktree trace-job01 (commit c853f43).
    16/16 unit tests pass. Automated chaining (index-ready -> consolidate -> validate -> release -> activate) with
    non-blocking raw ingestion (< 10 ms). READY FOR VERIFICATION.
  - CAP-JOB02 (Job Lease Expiry, Heartbeats & Backpressure): IMPLEMENTED on branch cap-job02-recovery in worktree trace-job02 (commit d6ab37b).
    24/24 unit tests pass. Implemented worker heartbeat monitoring, 300s lease timeouts, 3-retry dead-letter queuing, and
    a hard 5,000-item queue backpressure cap. READY FOR VERIFICATION.

• TRACK 5 (Evaluation Suite):
  - CAP-EVAL01 (Multi-Resolution Evaluation Protocols): CLOSED (PASS). Receipt: rcpt-cap-eval01-verif-indep-20260903-8f6efe2 (24/24 pass).
    Replaced legacy 0.0% orphan atom proxy with 5 multi-resolution scorecards and Draft 2020-12 hermetic schemas.
  - CAP-EVAL02 (Frozen Benchmark Datasets & Anchor Manifests): IMPLEMENTED on branch cap-eval02-datasets in worktree trace-eval02 (commit 587aa51).
    12/12 unit tests pass. Staged and pinned frozen splits for SciFact (1,000 queries), NFCorpus (323), FiQA (648), and
    MuSiQue (500) with immutable SHA-256 manifests and governance authority validation. READY FOR VERIFICATION.

----------------------------------------------------------------------------------------
2. ACTIVE DEDICATED WORKTREES & BRANCH REGISTRY
----------------------------------------------------------------------------------------
All active worktrees are cleanly isolated:
- Root:    C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/ (wave-b-candidate / main)
- GW01:    C:/Users/anshu/AppData/Local/trace-worktrees/trace-gw01 (cap-gw01-failclosed @ 25f194d) [CLOSED]
- GW02:    C:/Users/anshu/AppData/Local/trace-worktrees/trace-gw02 (cap-gw02-cost @ 683cfe7) [CLOSED]
- GW03:    C:/Users/anshu/AppData/Local/trace-worktrees/trace-gw03 (cap-gw03-budget @ 10c4c24) [CLOSED]
- RET01:   C:/Users/anshu/AppData/Local/trace-worktrees/trace-ret01 (cap-ret01-embedding @ 9f90ac8) [CLOSED]
- RET02:   C:/Users/anshu/AppData/Local/trace-worktrees/trace-ret02 (cap-ret02-fusion @ 94afcf3) [AWAITING VERIF]
- CRX01:   C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx01 (cap-crx01-schema @ 59ce53a) [CLOSED]
- CRX02:   C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx02 (cap-crx02-consolidator @ 45c3591) [AWAITING VERIF]
- CRX03:   C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx03 (cap-crx03-activation @ 824222e) [AWAITING VERIF]
- JOB01:   C:/Users/anshu/AppData/Local/trace-worktrees/trace-job01 (cap-job01-pipeline @ c853f43) [AWAITING VERIF]
- JOB02:   C:/Users/anshu/AppData/Local/trace-worktrees/trace-job02 (cap-job02-recovery @ d6ab37b) [AWAITING VERIF]
- EVAL01:  C:/Users/anshu/AppData/Local/trace-worktrees/trace-eval01 (cap-eval01-protocol @ 8f6efe2) [CLOSED]
- EVAL02:  C:/Users/anshu/AppData/Local/trace-worktrees/trace-eval02 (cap-eval02-datasets @ 587aa51) [AWAITING VERIF]

----------------------------------------------------------------------------------------
3. OPERATING DISCIPLINE & DUAL-AGENT PROTOCOL
----------------------------------------------------------------------------------------
1. Dual-Agent Separation:
   - YOU (Coordinator) orchestrate internal DeepCoder subagents to implement, repair, and test code.
   - The HUMAN OWNER runs Codex CLI (VERIF-INDEP) in a separate terminal/process to perform
     clean, detached verification and issue cryptographic receipts.
   - Codex and AGY CLI run completely concurrently without blocking or interfering with one another.

2. Verification Commands for Codex Independent Verifier (VERIF-INDEP):
   The human project owner can run the verification suites in detached terminals:

   • Batch 1 (Foundation Packets Ready for Verification):
     - CAP-RET02: cd C:/Users/anshu/AppData/Local/trace-worktrees/trace-ret02; :PYTHONPATH='src'; pytest tests/v2/test_hybrid_retrieval.py tests/v2/test_retrieval_embedding.py -v
     - CAP-CRX02: cd C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx02; :PYTHONPATH='src'; pytest tests/v2/test_cortex_consolidator.py -v
     - CAP-JOB01: cd C:/Users/anshu/AppData/Local/trace-worktrees/trace-job01; :PYTHONPATH='src'; pytest tests/v2/test_job_pipeline.py -v

   • Batch 2 (Successor Packets Ready for Verification):
     - CAP-JOB02: cd C:/Users/anshu/AppData/Local/trace-worktrees/trace-job02; :PYTHONPATH='src'; pytest tests/v2/test_job_recovery.py -v
     - CAP-CRX03: cd C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx03; :PYTHONPATH='src'; pytest tests/v2/test_cortex_activation.py -v
     - CAP-EVAL02: cd C:/Users/anshu/AppData/Local/trace-worktrees/trace-eval02; :PYTHONPATH='src'; pytest tests/v2/test_eval_datasets.py -v; python benchmarks/verify_dataset_checksums.py

3. Convergence & Gate CAP-GB Promotion:
   - Once the independent attestation receipts for the above 6 packets land in docs/program/inbox/,
     execute the Wave B candidate reconciliation:
     1. Merge all verified worktree branches into branch wave-b-candidate.
     2. Run the full repository integration test suite (pytest tests/ -v).
     3. Prepare the Gate CAP-GB Attestation Dossier (docs/program/inbox/cap-ver-gb/verification_receipt.json)
        to formally unlock Wave C (Model Bake-Off & Selection).

INITIALIZE: Inspect workspace status, confirm receipt files in docs/program/inbox/, 
and present the updated Program Coordinator Dashboard.
========================================================================================
