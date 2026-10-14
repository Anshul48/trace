# F0b Evidence — P-001 Decision Input

## 1. Candidate Dataset Evaluation Matrix

The table below provides the comparative evaluation for human decision P-001 (initial real-data portfolio admission), with evidence confidence ratings, query-evidence fit, scale potential, transform risks, and explicit recommendations.

| Candidate Dataset | License & Identity Confidence | Query / Evidence Fit | Scale Potential | Transform Risk | Recommendation for P-001 |
|---|---|---|---|---|---|
| **BEIR / SciFact** | **HIGH** (CC BY-NC 4.0 / Apache-2.0, UKP Darmstadt authoritative mirror) | **HIGH** (Expert qrels, 300 verifiable scientific claim queries) | Low (~5.1K passages) | **LOW** (Standard JSONL/TSV format) | **ADMIT** (Priority for zero-shot scientific lookup) |
| **BEIR / NFCorpus** | **HIGH** (CC BY-SA 4.0, UKP Darmstadt authoritative mirror) | **HIGH** (Graded qrels, 323 medical nutrition queries) | Low (~3.6K docs) | **LOW** (Standard JSONL/TSV format) | **ADMIT** (Domain generalization) |
| **BEIR / FiQA** | **HIGH** (CC BY-SA 3.0, UKP Darmstadt authoritative mirror) | **HIGH** (Financial QA, 648 queries) | Medium (~57.6K passages) | **LOW** (Standard JSONL/TSV format) | **ADMIT** (Information-dense retrieval) |
| **BRIGHT (Coding/Math)** | **HIGH** (Apache-2.0 / CC BY-SA 4.0, HuggingFace `xlangai/BRIGHT`) | **VERY HIGH** (Reasoning-intensive queries where dense embeddings fail) | Medium (~10K docs) | **LOW** (Parquet/JSON download) | **ADMIT** (Core reasoning benchmark for tree/graph RAG) |
| **MultiHop-RAG** | **HIGH** (Apache-2.0, GitHub / HuggingFace `yixuantt/MultiHop-RAG`) | **VERY HIGH** (2-4 hop reasoning chains with explicit gold doc IDs) | Medium (~10K docs) | **LOW** (Structured JSON format) | **ADMIT** (Core multi-hop inference benchmark) |
| **HippoRAG 2 / MuSiQue** | **HIGH** (CC BY 4.0 / Apache-2.0, OSU NLP Group) | **HIGH** (Associative graph reasoning chains) | Medium (~20K paragraphs) | **MEDIUM** (Full dataset script needed; sample URL in current adapter) | **ADMIT MuSiQue subset** (Prohibit 2-question synthetic sample) |
| **HiCBench / HiChunk** | **LOW** (Unpinned academic repository; current adapter is synthetic) | **HIGH** (Hierarchical multi-level chunking) | Low-Medium (~5K sections) | **HIGH** (Must resolve official source repository in D2) | **DEFER** (Do not admit until source archive is pinned) |
| **LongMemEval** | **MEDIUM** (MIT/Apache-2.0 open source; current adapter is synthetic) | **VERY HIGH** (Temporal updates & selective forgetting) | Low (~500 sessions) | **HIGH** (Must build multi-session ingestion pipeline in D2) | **DEFER** (Do not admit until real fetch script is verified) |
| **TREC RAG 2026** | **LOW (Access-Restricted)** (Requires NIST participant user agreement) | **HIGH** (Large-scale segmented deep retrieval) | High (100K+ segments) | **HIGH** (Restricted distribution, non-public credentials) | **REJECT for initial open baseline**; defer to restricted pilot |
| **ANN Scale / BigANN** | **HIGH** (Public Domain / MIT, standard HDF5 format) | **LOW (Ops only)** (Vector nearest neighbor ground truth, zero text semantics) | High (100K to 1M vectors) | **LOW** (Standard HDF5 parser) | **ADMIT for Scale/Ops Lane Only** (Non-retrieval claim) |

---

## 2. Proposed Initial Admitted Portfolio (Core Recommended Bundle)

Upon acceptance of P-001, the recommended initial open-benchmark portfolio consists of:
1. **Zero-Shot & Direct Retrieval**: BEIR (`scifact`, `nfcorpus`, `fiqa`).
2. **Reasoning-Intensive Retrieval**: BRIGHT (`coding`, `math`).
3. **Multi-Hop & Graph Associative Retrieval**: MultiHop-RAG and MuSiQue.
4. **Vector Scaling & Throughput**: BigANN (100K vectors, ops lane).

### Excluded / Deferred from Initial Bundle:
- `LongMemEval` and `HiChunk` remain **DEFERRED** to packet D2 until real download endpoints replace synthetic sample generators.
- `TREC RAG 2026` is **REJECTED** from the open baseline due to restricted participant agreements.
- Synthetic scale ladders and internal 320-case fixtures are strictly classified as **non-certifying regression/fault tools**.
