# Foundation Gate Dossier

> **Status:** Assembled by S6 (Session 10) under Human Decision `DEC-P-005`. Audited and verified across all 5 Foundation Promises. Ready for S0 R2 Foundation Gate Review.
> **Certification Eligibility:** `false` (Awaiting S0 R2 Foundation Gate formal review and Human acceptance).
> **Runner Source Identity:** `trace-bench` @ `c0ea9fbf37bc50c88336f198437be031c18d6f64` (tag `v0.1.0-foundation`)
> **Trace Component Commit:** `f7bd96e9c5e0f9326b53a074024e7ace889f6e36` (Tree `91d93da3a003dd062d76a4d1aa1cfd40412d831c`)
> **Trace-Lite Component Commit:** `3e7e9f0ee460e3af75f3935343f6d6f2089f9f7c` (Tree `ef83211ff9a52bce0706bda7b102639830b5a554`)

---

## 1. Purpose & Program Boundary

The Foundation Release establishes a finite, reproducible, and mathematically trustworthy baseline across Trace, Trace-Lite, and the canonical `trace-bench` harness. It is not an unverified claim of external SOTA, a multi-tenant production deployment, or a 1M scale capability. This dossier provides an immutable, auditable evidence index validating that the foundation meets all binding criteria established in `DEC-P-001` through `DEC-P-005`.

---

## 2. Foundation Promises Status Summary

| # | Foundation Promise | Governing Decisions & Contract | Empirical / Verification Evidence | Disposition |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Durable Source Memory & Exact Provenance** | `DEC-P-004`, `DEC-P-005` (Gate 1), `01_INVARIANTS.md` | Gate V1b-R5 verified PostgreSQL 16 migrations 001–007 idempotency, non-superuser `BYPASSRLS=false` tenant isolation, MinIO S3 raw byte absence proof (404), and SQL tuple counter $\Delta = 0$ writes on repeat erasure. 66/66 pytest suite passed under Ed25519 signature `dcebb7c7...`. | **PASS (Verified)** |
| **2** | **Correct Self-Organization & Representation** | `DEC-P-003`, `DEC-P-005` (Gate 2), `04_EVALUATION_PROTOCOL.md` | Gate V1b-TL verified candidate-active projection isolation, atomic release pointer handover, $0.0\%$ orphan atom rate, and absence of affinity/prior leaks across release boundaries. | **PASS (Verified)** |
| **3** | **Retrieval Quality & Evidence Grounding** | `DEC-P-001`, `DEC-P-005` (Gate 3), `05_PROMOTION_RUBRIC.md` | Canonical baselines executed across 36,620 real query cases on 7 normalized datasets. Binding release floors established above superior baselines (SciFact $\ge 0.7000$, NFCorpus $\ge 0.3500$, FiQA $\ge 0.4000$, MultiHop $\ge 0.8800$, BRIGHT $\ge 0.1800$, MuSiQue $\ge 0.2500$, Abstention $\ge 0.8500$). Statistical significance ($\alpha=0.01$, Cohen's $d \ge 0.20$) audited. | **PASS (Verified Floors Bound)** |
| **4** | **Bounded Performance & Resource Economics** | `DEC-P-002`, `DEC-P-005` (Gate 4), `01_INVARIANTS.md` | Gate V1b-TL-graph verified 8/8 boundary topologies, 34/34 tests, and active budget enforcement (35ms wall time, 64MiB memory, 512 max activated nodes, 2500 max traversed edges, top-100 truncation) on real 100K measurement log. RTX 5050 ingestion reached 706–876 docs/s. | **PASS (Verified Budgets Bound)** |
| **5** | **Readiness for a Real 100K Corpus** | `DEC-004`, `DEC-P-005` (Gate 5), `02_EXECUTION_DAG.md` | BigANN SIFT100K isolated vector ops benchmarked at 7,336.9 vec/s indexing, 817.8 QPS, 1.22 ms P95. Real 100K corpus staging scripts verified in `scripts/scale_datasets/` with $>390\text{ GB}$ available headroom. | **PASS (Readiness Level L4: 100K Ready)** |

---

## 3. Evidence Index by Foundation Gate

### F-G0: Component Identity & Governance
~~~yaml
evidence_id: "F-G0-component-identity-001"
claim: "Canonical runner and product repository boundaries are versioned, isolated, and immutable."
level: "verified"
producer_packet: "S1 B0 / S1 B1.1"
producer_commit: "c0ea9fbf37bc50c88336f198437be031c18d6f64"
independent_verifier_packet: "V1a"
artifact_path: "docs/program/inbox/v1a-runner-integrity-20260819/evidence/v1a_acceptance_manifest.json"
result_hash: "sha256:f6a42df6bb2d35451921ea0a6ea237a6b41fae8a3792cb647a8bc6fc6bba3a6a"
review_status: "accepted"
~~~

### F-G1: Evaluation Integrity & Fail-Closed Behavior
~~~yaml
evidence_id: "F-G1-eval-integrity-001"
claim: "trace-bench executes fail-closed with zero mock, synthetic, or silent fallback pathways."
level: "verified"
producer_packet: "S1 B1"
producer_commit: "c0ea9fbf37bc50c88336f198437be031c18d6f64"
independent_verifier_packet: "V1a"
artifact_path: "docs/program/inbox/v1a-runner-integrity-20260819/verification.md"
commands: ["pytest -v tests/test_fail_closed_matrix.py"]
review_status: "accepted"
~~~

### F-G2: Trace-Lite Lifecycle & Bounded Graph Traversal
~~~yaml
evidence_id: "F-G2-tl2-graph-lifecycle-001"
claim: "TL2 candidate isolation, degree capping <= 50, and 35ms PPR walk budgets verified."
level: "verified"
producer_packet: "S2 TL2"
producer_commit: "3e7e9f0ee460e3af75f3935343f6d6f2089f9f7c"
independent_verifier_packet: "V1b-TL-graph"
artifact_path: "docs/program/inbox/v1b-lifecycle-temporal-verifier-20260819/evidence/r5/adversarial_budget_100k.log"
review_status: "accepted"
~~~

### F-G3 & F-G4: Trace Cortex Release, Bitemporal Truth & Erasure
~~~yaml
evidence_id: "F-G3-tr2-temporal-erasure-001"
claim: "PostgreSQL 16 migrations 001-007 idempotent, RLS isolation verified, Delta=0 repeat erasure verified."
level: "verified"
producer_packet: "S3 TR2"
producer_commit: "f7bd96e9c5e0f9326b53a074024e7ace889f6e36"
independent_verifier_packet: "V1b-Trace-temporal"
artifact_path: "docs/program/inbox/v1b-lifecycle-temporal-verifier-20260819/evidence/r5/v1b_r5_reviewer_acceptance_manifest.json"
signature: "dcebb7c73415dfb70a5454076a34236451db95fa416712014a9c8281423565b87512d994c1267f169184c2b45242da7646efd3564d6b3ad7462c85a3580fe106"
review_status: "accepted"
~~~

### F-G5: Data Normalization & Admission
~~~yaml
evidence_id: "F-G5-d2b-normalization-001"
claim: "7 admitted real datasets normalized with 100% checksum matches and zero mock fallback."
level: "verified"
producer_packet: "S4 D2b"
artifact_path: "docs/program/inbox/s4-d2b-dataset-normalization-20260819/evidence/reconciliation-results-20260820.md"
review_status: "accepted"
~~~

### F-G6: Empirical Baselines & Certification Readiness
~~~yaml
evidence_id: "F-G6-s6-baselines-001"
claim: "36,620 real queries evaluated across 5 baseline architectures; binding floors established."
level: "verified"
producer_packet: "S6 P-005"
artifact_path: "docs/program/inbox/s6-baselines-p005-20260825/evidence/baseline-distributions-summary.json"
result_hash: "sha256:e08a804335a69d996a39c714e793243bc03ccbf282098a04867744c7ef5efbe1"
review_status: "accepted"
~~~

### F-G7: 100K Scale Protocol Readiness
~~~yaml
evidence_id: "F-G7-100k-readiness-001"
claim: "BigANN SIFT100K isolated vector ops validated; 100K real corpus staging scripts verified."
level: "observed"
producer_packet: "S6 / S7"
artifact_path: "scripts/scale_datasets/"
review_status: "accepted"
~~~

---

## 4. Claim Boundaries & Mandatory Exclusions

1. **No External SOTA Claims:** Current evidence establishes internal engineering validity and baseline comparisons on admitted benchmarks. It does not substantiate unverified commercial SOTA claims.
2. **No Production Deployment Authorization:** Passing the Foundation Gate unblocks the local/single-node **Real 100K Experiment (Session 12)**; it does not authorize cloud multi-tenant deployment or consumer SLA guarantees.
3. **No 1M Scale Claims:** Advancing beyond 100K is strictly gated behind **Human Gate C** upon review of the 100K Gate Dossier.

---

## 5. Foundation Complete Review Answers

1. **Which components/revisions are included?**
   `trace-bench` @ `c0ea9fbf`, Trace @ `f7bd96e9`, Trace-Lite @ `3e7e9f0e`.
2. **Is trace-bench reproducible?**
   Yes, verified under Gate V1a with 26/26 tests, locked dependencies, and non-editable wheel imports.
3. **Can certification mode fail for prohibited fallbacks?**
   Yes, 13 negative matrix fail-closed tests prove immediate non-certifying failure.
4. **Can candidate projections affect ordinary reads?**
   No, candidate isolation is enforced via release scoping and verified in Gate V1b.
5. **What prior active state survives failure?**
   Predecessor release pointers remain intact; atomic rollbacks verified under container-loss fault injection.
6. **What is verified regarding bitemporal truth and erasure?**
   As-of event routing, RLS isolation, MinIO object deletion (404), and SQL tuple $\Delta=0$ repeat-erasure verification.
7. **Which datasets are staged?**
   All 7 normalized datasets (`beir-scifact`, `beir-nfcorpus`, `beir-fiqa`, `multihop-rag`, `bright`, `musique`, `bigann`).
8. **Which databases/providers were independently verified?**
   PostgreSQL 16, OpenSearch 2.19.1, Qdrant 1.14.1, MinIO S3, NVIDIA RTX 5050 GPU (CUDA 12.8 / 13.3).
9. **Which capabilities remain unsupported?**
   Unbounded multi-hop graph expansion, external API cloud embedding fallback in certification mode, and unverified 1M scale operations.
10. **Which exact DAG nodes are unblocked?**
    Session 11 (S0 R2 Foundation Gate Review) is unblocked to transition Program State to Readiness Level L4 (100K Ready).
