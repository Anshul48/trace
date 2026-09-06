# WP-CAP-RET03 Dispatch Briefing & Prompt: Graph PPR Spreading Activation

- **Node ID:** `CAP-RET03`
- **Work Packet:** `WP-CAP-RET03`
- **Assigned Role:** Retrieval Specialist (`RET-SPEC`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-ret03` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-ret03`)
- **Branch:** `cap-ret03-graph`
- **Base Commit:** `94afcf3b358c351ac7a71e466a18fca67c32e81a` (`cap-ret02-fusion`)
- **Lease ID:** `lease-cap-ret03-20260903T144000Z`
- **Issued UTC:** `2026-09-03T14:40:00Z`
- **Governing Directives:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§4A), `docs/program/CAP_001_EXECUTION_DAG.md`
- **Status:** ACTIVE_DISPATCHED

---

## 1. Verbatim Copy-Paste Implementer Prompt

The following block is self-contained and copy-paste ready for the Retrieval Specialist subagent session:

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

ROLE: Retrieval Specialist (RET-SPEC) | TOOL: AGY CLI (subagent, Workspace=inherit)
WORK PACKET: WP-CAP-RET03 | WORKTREE: isolated branch cap-ret03-graph
LEASE (exclusive): src/trace/v2/retrieval.py (graph-walk section only),
tests/v2/test_graph_retrieval.py. Do NOT touch RRF/fusion sections (RET02 lease).

OBJECTIVE: Optimize Personalized PageRank spreading activation over associative
edges (CONTAINS, DEPENDS_ON, ASSOCIATED_WITH): max out-degree ≤ 50, walk depth
≤ 15, teleport α = 0.15, max 20 iterations, end-to-end multihop P95 ≤ 10 ms
annex-class budget. Empty graph ⇒ return hybrid candidates with explicit
telemetry flag (never fail open, never fabricate traversal).

ACCEPTANCE: pytest tests/v2/test_graph_retrieval.py -v (100% pass).
DELIVERABLE: commit + handoff in docs/program/inbox/cap-ret03/handoff.md
(base commit, test log, latency receipt, cycle/guard behavior).
BEGIN WORK.
```

---

## 2. Exclusive File Lease & Boundaries

- **Allowed Paths:**
  - `src/trace/v2/retrieval.py` (graph-walk / spreading activation section only; lines 981–1050 / multihop)
  - `tests/v2/test_graph_retrieval.py`
  - `docs/program/inbox/cap-ret03/handoff.md`
- **Strictly Prohibited Paths:**
  - `src/trace/v2/retrieval.py` (BM25 or dense RRF fusion sections owned by `CAP-RET02`)
  - `src/trace/v2/cortex/`
  - `benchmarks/manifests/`

---

## 3. Specific Technical Invariants

1. **PPR Spreading Activation Parameters:**
   - Teleport probability: $\alpha = 0.15$
   - Max iterations: 20
   - Out-degree bound: $\le 50$ per node
   - Depth bound: $\le 15$ hops
   - Target Latency: P95 $\le 10\text{ ms}$ annex-class budget.
2. **Fail-Closed Semantics:**
   - If associative graph is empty or disconnected, return hybrid seed candidates with explicit telemetry flags (`graph_applied=False`, `empty_graph=True`).
   - Runaway walk and cyclic edge guards must be strictly enforced.
3. **Acceptance Command:**
   ```bash
   PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_graph_retrieval.py -v
   ```
4. **Deliverable Receipt:**
   - Handoff receipt filed at `docs/program/inbox/cap-ret03/handoff.md`.
