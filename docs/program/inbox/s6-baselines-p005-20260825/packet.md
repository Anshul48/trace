# S6 — Real Baselines and P-005 Decision Brief

> **Role:** Evaluation & Promotion Owner (S6)
>
> **DAG Node:** S6 / P-005 Decision Brief
>
> **State:** Unblocked / In Execution
>
> **Authority Level:** C3 (Empirical Real-Data Baseline Evidence) / Decision Proposal

## 1. Objective

Execute reproducible, fail-closed baseline evaluations across all admitted real datasets in the DEC-P-001 portfolio using the canonical 	race-bench runner. Produce empirical latency, accuracy, memory, and error distributions across capability lanes. Deliver the P-005 Decision Brief proposing numerical release thresholds and statistical methods for Human Gate B.

## 2. Boundaries & Invariants

- Use only the canonical 	race-bench runner (commit c0ea9fbf...) and admitted normalized datasets (d2b-20260819/repair-mq-roundtrip-20260820).
- Strict fail-closed execution: zero mock LLM/provider substitution, strict TLS, non-editable wheel imports.
- Maintain separate capability lanes: direct lookup, semantic retrieval, multi-hop reasoning, chronology, abstention, organization, and operations/vector scale.
- BigANN / SIFT1M vector scale results remain strictly isolated as an operations lane and are NEVER blended into text retrieval quality metrics.
- S6 proposes, but does NOT approve, P-005 release thresholds. Certification eligibility remains
alse until human approval at Human Gate B and B3 dossier assembly.
- Preserve source truth, native IDs, exact offsets, and denominator distinctions (positive queries, expected abstentions, exclusions, failures).

## 3. Admitted Portfolio Scope

1. **BEIR SciFact** (Direct/Source Lookup, Scientific Claims): 1,109 cases, 5,183 documents
2. **BEIR NFCorpus** (Domain Semantic Retrieval, Medical): 3,237 cases, 3,633 documents
3. **BEIR FiQA** (Domain QA / Financial Retrieval): 6,611 cases, 57,600 documents
4. **BRIGHT** (Complex Reasoning / Math / Coding): 752 cases, 928,750 documents
5. **MultiHop-RAG** (Multi-hop Evidence & Chronology): 2,556 cases (2,255 positive + 301 abstentions), 609 documents / 975 segments
6. **MuSiQue** (Compositional Multi-Hop Reasoning): 22,355 cases (2-hop, 3-hop, 4-hop), 101,962 segments
7. **BigANN / SIFT1M** (Operations / Vector Scale Lane): 100,000 vectors, isolated operations profile

## 4. Evaluated Baselines

- m25: Standard Okapi BM25 Lexical Retrieval
- dense: Bi-Encoder Dense Retrieval (sentence-transformers/all-MiniLM-L6-v2)
- hybrid_rrf: Reciprocal Rank Fusion of BM25 + Dense
- hipporag_ppr: Graph-based Personalized PageRank Retrieval
-
lat_hierarchy: Clustered Hierarchical Index Retrieval
- nn_scale: High-throughput Vector Indexing & Nearest Neighbor Search (SIFT1M)

## 5. Required Deliverables

1. Immutable per-case and aggregate baseline evaluation artifacts in evidence/runs/.
2. Empirical baseline distributions summary (evidence/baseline-distributions-summary.json).
3. Capability lane breakdown (evidence/lane-metrics-breakdown.json).
4. P-005 Decision Brief for Human Gate B (evidence/p005-decision-brief.md).
5. Complete packet handoff (handoff.md).
