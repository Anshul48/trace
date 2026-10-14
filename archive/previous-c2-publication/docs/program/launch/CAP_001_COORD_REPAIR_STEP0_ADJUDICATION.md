# COORD-REPAIR Step-0 Adjudication (coordinator record)

- **Session:** COORD-REPAIR, 2026-09-03 (Muse coordinator)
- **Standing state:** EVAL02 PASS holds (300/323/648 + MD5s, D1 cleared). Five FAILs to repair: RET02, CRX02, JOB01, JOB02, CRX03 (overlap audit PASS_WITH_MERGE_RISK, D3 JOB02-first stands).
- **RET03/EVAL03:** dispatched, leases stand, untouched by this turn.
- **Filing note:** coordinator lease path `docs/program/inbox/cap-coord/` is not writable from this session's sandbox; filed here in `launch/` (writable). Move to `docs/program/inbox/cap-coord/repair_step0_adjudication.md` in a write-capable session.

## RET02 hunk table (`cap-ret01-embedding..cap-ret02-fusion`, `src/trace/v2/retrieval.py`, 508+/14-)

| Hunk (new-side) | Content | Ruling |
|---|---|---|
| 31 | Import `RetrievalBudget` | FUSION-NECESSARY (RRF budget plumbing) |
| 56-132 | `compute_rrf_score` (k=60 bit-exact) + helpers | FUSION-NECESSARY (core formula) |
| 561-789 | `InMemoryBM25Index`, full postings eval, no `[:300]` | FUSION-NECESSARY (truncation-removal acceptance) |
| 858-970 | Positive-score rank filter, dense-score gate, `missing[:1000]` removal, cosine>0 filter | FUSION-NECESSARY (no-truncation + abstention acceptance) |
| 1443-1476 | `dense_thresh=0.30` gate, `_extract_rrf_weights/k`, `compute_rrf_score` call-site replacing inline `1.0/(60+rank)` | FUSION-NECESSARY (RRF wiring) |
| 1749 | `projection_object_id` visibility fix in fused-candidate filter | FUSION-NECESSARY (fused-candidate correctness over projected atoms) |
| 1761-1765 | Telemetry keys (`dense_unpopulated`, `w_bm25`, `w_dense`, `rrf_k`) | FUSION-NECESSARY (acceptance telemetry) |
| 1786-1944 | `retrieve_hybrid` convenience wrapper + `EphemeralStoreAdapter` test harness (21 test call-sites) | FUSION-NECESSARY (test-called API + harness, not creep) |

**Result:** zero SCOPE-CREEP hunks, no split order. RET02 lease re-scoped to: `src/trace/v2/retrieval.py` hunks above + `tests/v2/test_hybrid_retrieval.py` + own `docs/program/inbox/cap-ret02/handoff.md` (standing: each node's own inbox handoff.md is inside its lease; recorded here for human confirmation at GB).

## JOB01 base ruling

Branch `cap-job01-pipeline`: `a9255b4` (main) -> `6430430` (feat pipeline) -> `c853f43` (harden). Intended base = **`a9255b4`**. No dependency on any CRX02 commit. R-JOB01 verifies against `a9255b4`.

## P0-ENV recon (2026-09-03, Linux mount probe)

Worktrees present under `/mnt/c/Users/anshu/AppData/Local/trace-worktrees/`. pytest shims found: `trace-crx02/.venv/bin/pytest`, `trace-job01/.venv/bin/pytest`, `trace-eval02/.venv/Scripts/pytest.exe` (Windows venv). Missing: `trace-ret02`, `trace-job02`, `trace-crx03`. Neural deps for trace-ret02 still to confirm (P0-ENV specialist task).

## Dispatch order (this turn)

1. P0-ENV recon (read-only, this session) -> env-fix commands for a write-capable session.
2. R-RET02 + R-CRX02 + R-JOB01 fix-specs (3 disjoint leases; read-only analysis this session, edits in write-capable session).
3. R-JOB02 only after R-JOB01 lands (shared `service.py`).
4. R-CRX03 only after R-JOB02 lands (D3 serialization; rebase at merge time, NOT in repair).
5. Re-verify per packet prompts Sections 2-3, then Section 5A GB dossier.
