# TRACE-CAP-001 Gate & Dependency Matrix

> **Document ID:** `TRACE-CAP-001-GATE-MATRIX`
> **Plan Reference:** [`COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`](COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md)
> **DAG Reference:** [`CAP_001_EXECUTION_DAG.md`](CAP_001_EXECUTION_DAG.md)
> **Status:** Governing Gate Matrix.
> **Principle:** Completion evidence makes a node eligible for promotion; explicit Human Decisions authorize progression and unlocks.

---

## 1. Master Gate Progression Summary

```text
========================================================================================================================
                                         TRACE-CAP-001 GATE PIPELINE
========================================================================================================================

   [CAP-GA] ─────────────► [CAP-GB] ─────────────► [CAP-GC] ─────────────► [CAP-GD] ─────────────► [CAP-GE]
  Governance              Contracts &             Model Bake-off          10K Shadow              100K Paired
  Reconciliation          Infrastructure          Selection               Operations              Qualification
  (Docs Relocked)         (Safety/Retrieval)      (Local SLM Winner)      (Restart-Safe)          (Separate Lanes)
                                                                                                         │
                                                                   ┌─────────────────────────────────────┴──────────────────┐
                                                                   ▼                                                        ▼
                                                            [CAP-GF] (1M Core)                                       [CAP-GG] (1M Cortex)
                                                            Spine Replay Parity                                      Semantic Projections
                                                            Durability at 1M                                         Combined System Claim
========================================================================================================================
```

---

## 2. Detailed Gate Specifications

| Gate ID | Gate Purpose | Required Completion Nodes | Required Evidence Dossier | Independent Verifier Attestation | Human Decision Node Required | Successor Nodes Unlocked | Mandatory Stop Rules |
|---|---|---|---|---|---|---|---|
| **`CAP-GA`** | Canonical Architecture Reconciliation | `CAP-A01`<br>`CAP-A02`<br>`CAP-A03` | Contradiction ledger fully checked; patch applied; `CONTROL_PLANE_LOCK.json` validated. | `CAP-VER-GA` receipt signed with zero hash mismatches. | **Human Gate CAP-GA:** Ratification of `DEC-CAP-001`. | Wave B nodes:<br>`CAP-GW01`<br>`CAP-RET01`<br>`CAP-CRX01`<br>`CAP-JOB01`<br>`CAP-EVAL01` | Any unratified clause or uncommitted document diff halts progression. |
| **`CAP-GB`** | Infrastructure, Contracts & Safety Baseline | `CAP-GW01-03`<br>`CAP-RET01-04`<br>`CAP-CRX01-03`<br>`CAP-JOB01-02`<br>`CAP-EVAL01-03` | Gateway fail-closed test logs; non-zero cost receipts; retrieval baseline nDCG receipts; schema tests; job recovery trace; faithfulness tests. | `CAP-VER-GB` receipt confirming 100% test pass on clean detached worktree. | **Human Gate CAP-GB:** Contract & Safety Approval. | Wave C bake-off:<br>`CAP-MOD01`<br>`CAP-MOD02` | Any manufactured fallback or failed negative test halts progression. |
| **`CAP-GC`** | Local SLM Model Bake-Off Selection | `CAP-MOD01`<br>`CAP-MOD02` | Raw bake-off results across 100 clusters; Pareto chart; faithfulness $\ge 95\%$; tokens/sec; cost per 1K holons; negative results ledger. | `CAP-VER-GC` receipt verifying prompt hashes and detached validation logs. | **Human Gate CAP-GC:** Model Selection Approval. | Wave D 10K shadow:<br>`CAP-INT01` | All local models failing $\ge 95\%$ proposition support stops pipeline. |
| **`CAP-GD`** | 10K Shadow Cortex Operations | `CAP-INT01` | 10K ingestion rate $\ge 800\text{ docs/s}$; WAL zero lost events; crash/recovery receipt; detached validation $\ge 95\%$; storage multiplier $\le 3.0\times$. | `CAP-VER-GD` receipt confirming zero duplicate work and zero unanchored nodes. | **Human Gate CAP-GD:** 10K Shadow Clearance. | Wave E 100K paired qualification:<br>`CAP-INT02`<br>`CAP-INT03` | Lost event during crash simulation or queue runaway $> 5,000$ items stops pipeline. |
| **`CAP-GE`** | 100K Paired Qualification (Core + Ret + Crx) | `CAP-INT02`<br>`CAP-INT03` | 100K qualification dossier with separate scorecards for Profile 1, 2, and 3; paired Wilcoxon tests; retrieval floors met; synthesis grounding. | `CAP-VER-GE` receipt verifying independent scorecards and storage accounting. | **Human Gate CAP-GE:** 100K Advancement Approval. | Scale eligibility:<br>`CAP-SCALE01`<br>`CAP-SCALE02` | Regression on SciFact/NFCorpus/FiQA or storage multiplier $> 3.5\times$ stops pipeline. |
| **`CAP-GF`** | 1M Core Scale Gate (`G1M-CORE`) | `CAP-SCALE01` | 1M Core scale dossier; 250K/500K/750K ladder logs; 100% WAL replay parity; $\Delta = 0$ erasure; storage $\le 2.5\times$; zero LLM calls. | `CAP-VER-GF` forensic attestation receipt confirming bit-exact replay. | **Human Gate CAP-GF:** Formal `G1M-CORE` Certification. | Official G1M-CORE claim; hosts optional 1M Cortex. | Any byte-offset drift or corrupted replay halts certification. |
| **`CAP-GG`** | 1M Cortex & Combined Release Gate (`G1M-CORTEX`) | `CAP-SCALE02` | 1M Cortex dossier; consolidated coverage; holon coherence; multi-hop retrieval uplift; isolated resource telemetry; synthesis grounding. | `CAP-VER-GG` receipt confirming projection integrity and isolated accounting. | **Human Gate CAP-GG:** Combined System Promotion. | Official Promoted Release Claim for Project Trace. | Resource runaway or unanchored projection rate $> 0.01\%$ stops promotion. |

---

## 3. Human Decision Node Templates

### Human Gate CAP-GA (Governance)
```text
DECISION GATE: CAP-GA (Governance & Architecture Ratification)
PREREQUISITES: CAP-A01, CAP-A02, CAP-A03, CAP-VER-GA
VERIFIER ATTESTATION: rcpt-cap-ver-ga-[date].json (PASS)
AUTHORIZATION SOUGHT:
  - Approve ratification of TRACE-CAP-001 (Clauses CAP-D001 through CAP-D016).
  - Unblock Wave B work packets (Infrastructure, Contracts, Safety Hardening).
HUMAN OWNER ACTION: [ ACCEPT / AMEND / REJECT ]
```

### Human Gate CAP-GB (Contracts & Safety)
```text
DECISION GATE: CAP-GB (Infrastructure, Contracts & Safety Baseline)
PREREQUISITES: All Wave B nodes, CAP-RET04, CAP-VER-GB
VERIFIER ATTESTATION: rcpt-cap-ver-gb-[date].json (PASS)
AUTHORIZATION SOUGHT:
  - Approve fail-closed gateway, pricing telemetry, dense retrieval adapter, and Cortex schemas.
  - Authorize local GPU compute and max $5.00 cloud budget for Wave C bake-off.
HUMAN OWNER ACTION: [ ACCEPT / AMEND / REJECT ]
```

### Human Gate CAP-GC (Model Selection)
```text
DECISION GATE: CAP-GC (Local SLM Model Selection)
PREREQUISITES: CAP-MOD01, CAP-MOD02, CAP-VER-GC
VERIFIER ATTESTATION: rcpt-cap-ver-gc-[date].json (PASS)
AUTHORIZATION SOUGHT:
  - Approve selected local SLM (e.g. Qwen2.5-3B/7B) for Cortex consolidation.
  - Authorize 10K shadow integration run (Wave D).
HUMAN OWNER ACTION: [ ACCEPT / AMEND / REJECT ]
```

### Human Gate CAP-GD (10K Shadow)
```text
DECISION GATE: CAP-GD (10K Shadow Operations)
PREREQUISITES: CAP-INT01, CAP-VER-GD
VERIFIER ATTESTATION: rcpt-cap-ver-gd-[date].json (PASS)
AUTHORIZATION SOUGHT:
  - Certify restart-safety, crash-recovery, and decoupled ingestion at 10K.
  - Authorize 100K paired qualification run (Wave E).
HUMAN OWNER ACTION: [ ACCEPT / AMEND / REJECT ]
```

### Human Gate CAP-GE (100K Paired Qualification)
```text
DECISION GATE: CAP-GE (100K Paired Qualification)
PREREQUISITES: CAP-INT02, CAP-INT03, CAP-VER-GE
VERIFIER ATTESTATION: rcpt-cap-ver-ge-[date].json (PASS)
AUTHORIZATION SOUGHT:
  - Approve separate scorecards for Core, Retrieval, and Cortex.
  - Unblock eligibility for 1M scale execution.
HUMAN OWNER ACTION: [ ACCEPT / AMEND / REJECT ]
```

### Human Gate CAP-GF (1M Core Scale Gate)
```text
DECISION GATE: CAP-GF (1M Core Scale Certification - G1M-CORE)
PREREQUISITES: CAP-SCALE01, CAP-VER-GF
VERIFIER ATTESTATION: rcpt-cap-ver-gf-[date].json (PASS)
AUTHORIZATION SOUGHT:
  - Certify G1M-CORE: 1M documents ingested, 100% bit-exact replay, storage <= 2.5x.
  - Authorize public or internal G1M-CORE claim.
HUMAN OWNER ACTION: [ ACCEPT / AMEND / REJECT ]
```

### Human Gate CAP-GG (1M Cortex & Combined Release)
```text
DECISION GATE: CAP-GG (1M Cortex & Combined System Promotion)
PREREQUISITES: CAP-SCALE02, CAP-VER-GG
VERIFIER ATTESTATION: rcpt-cap-ver-gg-[date].json (PASS)
AUTHORIZATION SOUGHT:
  - Certify G1M-CORTEX and Promoted Combined Trace Architecture.
HUMAN OWNER ACTION: [ ACCEPT / AMEND / REJECT ]
```
