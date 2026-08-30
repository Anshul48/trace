# Handoff C2-POL-01: Scale Policy Reconciliation & Canonical Lockfile

> **Packet ID:** `c2-pol-01-policy-reconciliation-20260829`
> **Role:** Policy & Protocol Architect (Wave R2.2)
> **Authority Context:** [`00_GLOBAL_CONTEXT_WAVE_R2_2.md`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/00_GLOBAL_CONTEXT_WAVE_R2_2.md) • [`SCALE_100K_TO_1M_EXECUTION_PLAN.md`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/SCALE_100K_TO_1M_EXECUTION_PLAN.md)
> **Status:** **PROPOSED_POLICY_REPAIR_REQUIRED (PROPOSED_AWAITING_HUMAN_GATE)**
> **Standard ID:** `DEC-P-005b-LEVEL1-R2.2`
> **Canonical Lockfile SHA-256:** `983279467455f006a5245bea0e8c550ce3a286fbda3fc5b01f9d797b05e3d880`
> **Date:** 2026-08-29T03:51:10Z

---

## 1. Executive Summary

Packet **C2-POL-01** has completed the formal policy reconciliation for **Trace Wave R2.2 (Measurement Integrity Execution Closure)** and established the canonical, schema-validated policy lockfile at [`benchmarks/policies/scale_policy.lock.json`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/benchmarks/policies/scale_policy.lock.json) alongside its formal schema [`benchmarks/policies/scale_policy.schema.json`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/benchmarks/policies/scale_policy.schema.json) remediating Audit Defects #3, #4, and #5.

This reconciliation resolves the historical divergence between foundation-level decisions (`DEC-P-005`), large-token retrieval revisions (`DEC-P-005b`), and hardcoded Python script dictionaries by establishing a single, cryptographically bound source of truth.

### Key Policy Determinations:
1. **Retrieval Floors Uncompromised:** Capability quality floors remain strictly frozen:
   - SciFact (`direct_lookup`): $\text{nDCG@10} \ge 0.700$, $\text{Recall@20} \ge 0.880$, $\text{P95} \le 25.0\text{ ms}$
   - NFCorpus (`domain_semantic`): $\text{nDCG@10} \ge 0.350$, $\text{Recall@20} \ge 0.220$, $\text{P95} \le 25.0\text{ ms}$
   - FiQA (`semantic_qa`): $\text{nDCG@10} \ge 0.400$, $\text{Recall@20} \ge 0.550$, $\text{P95} \le 30.0\text{ ms}$
   - MultiHop-RAG (`multi_hop_reasoning`): $\text{nDCG@10} \ge 0.750$, $\text{Coverage@20} \ge 0.880$, $\text{P95} \le 45.0\text{ ms}$
2. **Unlabeled Abstention Contract:** 301 null queries must pass through the unified retrieval and citation filter without caller-supplied truth flags (`system_abstained`). Zero Hallucination Rate must equal $1.000$; Abstention Accuracy must be $\ge 0.900$.
3. **Storage Accounting Scope:** Maximum storage multiplier is $\le 3.00\times$ against canonical raw text ($65,394,921\text{ bytes}$), establishing an exact mathematical ceiling of $\le 196,184,763\text{ bytes}$ ($196.18\text{ MB}$, target $\le 170.0\text{ MB}$). The ceiling strictly applies to total hot database state (durable SQLite WAL Spine + derived FTS5 lexical index + Cortex graph state). Offline raw download caches are excluded.
4. **Host Reference Memory (R16):** Peak process-tree RSS must not exceed $8.0\text{ GiB}$ under the R16 reference profile, with zero OOM and zero allocator retry loops.
5. **Durability & Replay Parity:** 100.0% atom retention, 0.0% hash drift, 100.0% anchor recovery, $\Delta = 0$ repeat erasure, and 100.0% full event replay parity across all 6 core SQLite tables.
6. **Statistical Method:** $B = 10,000$ Bootstrap Confidence Intervals at $95\%$ confidence ($\alpha = 0.01$, seed 42) with paired Wilcoxon signed-rank and Student's $t$-tests.

---

## 2. Delivered Artifacts

| Artifact | Path | Purpose |
| :--- | :--- | :--- |
| **Formal JSON Schema** | [`benchmarks/policies/scale_policy.schema.json`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/benchmarks/policies/scale_policy.schema.json) | Draft 2020-12 schema validating policy structure, types, constraints, and governance status. |
| **Canonical Policy Lockfile** | [`benchmarks/policies/scale_policy.lock.json`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/benchmarks/policies/scale_policy.lock.json) | Authoritative JSON lockfile loaded by runner and verifier by SHA-256 digest (`PROPOSED_AWAITING_HUMAN_GATE`). |
| **Synchronized Policy Copy** | [`docs/program/inbox/c2-pol-01-policy-reconciliation-20260829/evidence/scale_policy.lock.json`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/c2-pol-01-policy-reconciliation-20260829/evidence/scale_policy.lock.json) | Archival evidence copy in the inbox packet directory. |
| **Policy Decision Brief** | [`docs/program/inbox/c2-pol-01-policy-reconciliation-20260829/evidence/policy_reconciliation_brief.md`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/c2-pol-01-policy-reconciliation-20260829/evidence/policy_reconciliation_brief.md) | In-depth technical brief detailing historical divergence analysis, mathematical accounting, and operational specifications. |
| **Work Packet** | [`docs/program/inbox/c2-pol-01-policy-reconciliation-20260829/packet.md`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/c2-pol-01-policy-reconciliation-20260829/packet.md) | Formal work packet declaration, governance authority, checksums, and compliance verification. |
| **Downstream Handoff** | [`docs/program/inbox/c2-pol-01-policy-reconciliation-20260829/handoff.md`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/c2-pol-01-policy-reconciliation-20260829/handoff.md) | Handoff instructions and unblocking directives for downstream subagents. |

---

## 3. Downstream Execution Directives

The delivery of this packet unblocks subsequent Wave R2.2 implementation tasks:

1. **Task R2.2-02 (Evaluator / Binding Specialist):**
   - Bind `benchmarks/policies/scale_policy.lock.json` (`e24975779672d5c2daf1993d5fb7bfdf29fd8825a7085b9a0af7e915022f2f64`) and `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_manifest.json` across runner and verifier scripts.
   - Prohibit hardcoded threshold dictionaries in python source.
2. **Task R2.2-03 (Scale Implementer):**
   - Update `scripts/run_100k_scale_gate.py` to ingest the policy lockfile dynamically.
   - Remove any implicit `[:200]` sampling; evaluate all 7,457 queries; emit full top-20 ranking candidate objects into `raw_query_evaluations.jsonl`.
3. **Task R2.2-04 (Retrieval & Abstention Specialist):**
   - Verify un-labeled null query routing and citation filter execution without `system_abstained` shortcuts.
4. **Task R2.2-05 (Independent Verifier Specialist):**
   - Update `scripts/verify_100k_candidate.py` to independently load `scale_policy.lock.json` by digest and recompute all metrics directly from raw candidate rankings and DB files.
5. **Task R2.2-06 (Test Specialist):**
   - Add negative integration fixtures verifying fail-closed exit if `scale_policy.lock.json` is modified, missing, or corrupted.

---

