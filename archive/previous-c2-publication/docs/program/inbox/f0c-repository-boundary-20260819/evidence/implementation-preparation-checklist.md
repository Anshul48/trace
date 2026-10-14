# Implementation Preparation Checklist

> **Status:** Gap analysis of missing conditions before mutable implementation packets (B1, L1, TR1, TR2) can be marked `prepared`.
> **Date:** 2026-08-19.

## 1. Preparation Requirements Matrix

To transition a packet from `scoped` to `prepared`, all 8 conditions must be satisfied:

1. Input manifest and repository state record pinned.
2. Accepted dependencies and human decisions recorded.
3. Clean isolated worktree lease at accepted source identity.
4. Exact allowed and forbidden paths specified.
5. Acceptance and negative test matrix defined.
6. Independent verifier assignment and separate worktree plan established.
7. Safe recovery and rollback statement documented.
8. Structured handoff and evidence destination prepared.

---

## 2. Packet Readiness Assessment

| Packet | Condition 1: Inputs/Repo State | Condition 2: Decisions & Deps | Condition 3: Clean Worktree Lease | Condition 4: Exact Paths | Condition 5: Negative Tests | Condition 6: Verifier Assigned | Condition 7: Rollback Defined | Condition 8: Handoff Dest | Overall State |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B1** (Fail-Closed Runner) | ❌ Missing F0a handoff & trace-bench pin | ❌ Blocked on P-007 & P-008 | ❌ No lease; source unversioned | ⚠️ Broad paths only | ⚠️ Needs V0/V1a matrix | ❌ V1a not assigned | ⚠️ Preliminary | ✅ Destination exists | **SCOPED (NOT PREPARED)** |
| **L1** (TL Candidate/Active) | ⚠️ F0c ready; manifest draft | ✅ No open decision for L1 | ❌ Worktree not yet created/leased | ⚠️ Broad paths only | ⚠️ Needs V0/V1b matrix | ❌ V1b not assigned | ⚠️ Preliminary | ✅ Destination exists | **SCOPED (NOT PREPARED)** |
| **TR1** (Unified Cortex Release) | ❌ Missing T1 handoff | ❌ Blocked on P-003 decision | ❌ Trace tree dirty; no clean lease | ⚠️ Broad paths only | ❌ Awaits T1 audit | ❌ V1b not assigned | ⚠️ Preliminary | ✅ Destination exists | **BLOCKED** |
| **TR2** (Temporal & Revocation) | ❌ Missing TR1 handoff | ❌ Blocked on P-004 decision | ❌ Awaits TR1 baseline | ⚠️ Broad paths only | ❌ Awaits T1/TR1 | ❌ V1b not assigned | ⚠️ Preliminary | ✅ Destination exists | **BLOCKED** |

---

## 3. Required Next Actions to Unblock Preparation

1. **For B1:**
   - Execute read-only **F0a** evaluation audit.
   - Obtain human decisions on **P-007** (source identity) and **P-008** (runner boundary).
   - Execute read-only **V0** to freeze the V1a negative test matrix.
   - Issue isolated worktree lease and complete input manifest.

2. **For L1:**
   - Complete `input-manifest.json` for L1 referencing `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1`.
   - Create isolated worktree `..\trace-lite-l1` and issue `worktree-lease.json`.
   - Narrow allowed source paths to exact modules (`retrieval/`, `models/`, `tests/`).
   - Assign V1b with explicit verification commands.

3. **For TR1:**
   - Execute read-only **T1** Cortex Release audit.
   - Present **P-003** decision options to human program owner.
   - Upon acceptance of P-003, prepare clean base lease and assign V1b.

4. **For TR2:**
   - Complete TR1 implementation and obtain human decision on **P-004**.
