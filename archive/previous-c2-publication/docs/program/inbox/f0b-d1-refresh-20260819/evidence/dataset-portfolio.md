# F0b Evidence — Candidate Dataset Portfolio

## 1. Capability Portfolio Matrix

The table below catalogs all evaluated candidate datasets across the 6 required program evaluation dimensions, detailing official sources, licenses, versions, target query classes, scale potential, and current admission gaps.

| Capability Lane | Candidate Dataset | Official Source / Distribution ID | License & Permitted Use | Canonical Version / Release | Intended Query Class | Scale (Atoms / Queries) | Admission & Evidence Gaps | Recommendation for P-001 |
|---|---|---|---|---|---|---|---|---|
| **Lexical / Direct Lookup** | **BEIR / SciFact** | UKP Darmstadt (`https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip`) | CC BY-NC 4.0 / Apache-2.0 | BEIR v1.0.0 (SciFact 2020) | `direct_lookup` (verifiable claims) | 5,183 passages / 300 test queries | Needs formal license clarification (non-commercial clause for enterprise use); post-download checksum required. | **Propose P-001 Admission** (for non-commercial research lane) |
| **Lexical / Direct Lookup** | **BEIR / NFCorpus** | UKP Darmstadt (`https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip`) | CC BY-SA 4.0 | BEIR v1.0.0 | `direct_lookup` (medical nutrition) | 3,633 documents / 323 test queries | ShareAlike license compatibility; post-download checksum required. | **Propose P-001 Admission** |
| **Semantic Lookup** | **BEIR / FiQA** | UKP Darmstadt (`https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip`) | CC BY-SA 3.0 | BEIR v1.0.0 (FiQA 2018) | `direct_lookup` / `semantic` | 57,638 passages / 648 test queries | Financial domain terminology; requires frozen qrels test split. | **Propose P-001 Admission** |
| **Reasoning / Semantic** | **BRIGHT (Coding, Math, StackEx)** | HuggingFace `xlangai/BRIGHT` (NeurIPS 2024) | Apache-2.0 / CC BY-SA 4.0 | Commit `main` (ACL/NeurIPS release) | `cross_domain` / `multi_hop` | ~10K documents / 1,398 reasoning queries | High-difficulty reasoning queries where dense embeddings fail; needs pinned HF snapshot hash. | **Propose P-001 Admission** (Priority for reasoning) |
| **Multi-Hop Evidence** | **MultiHop-RAG** | GitHub / HF `yixuantt/MultiHop-RAG` | Apache-2.0 | v1.0 (2024 release) | `multi_hop` (2-4 hop reasoning) | ~10K passages / 2,556 queries | Gold evidence chain mapping needs atom-level offset verification; null query handling. | **Propose P-001 Admission** |
| **Multi-Hop / Graph** | **HippoRAG 2 / MuSiQue / 2Wiki** | GitHub `OSU-NLP-Group/HippoRAG` / HuggingFace | Apache-2.0 / CC BY 4.0 | HippoRAG v2 release | `multi_hop` (associative graph) | 10K-50K paragraphs / 1,000+ queries | Current adapter only points to sample URL; needs full dataset staging script and entity mapping. | **Defer full suite; admit MuSiQue subset** |
| **Long Hierarchy** | **HiCBench / HiChunk** | Academic paper / GitHub repo | Academic open source (license review pending) | Release 2024 | `global_context` (hierarchical chunks) | ~5K sections / 500 queries | Current adapter has NO download URL and creates synthetic sample; source repository must be pinned. | **Defer until official release archive is resolved** |
| **Temporal / Revision** | **LongMemEval** | GitHub / HF `LongMemEval` (MemoryAgentBench) | MIT / Apache-2.0 | Release 2024 | `historical` / `contradiction` | 500 multi-session conversations | Current adapter has NO download URL and creates synthetic sample; needs real multi-session trace ingestion. | **Defer until source URL is pinned in D2** |
| **Segmented Deep Retrieval** | **TREC RAG 2026** | NIST TREC 2026 RAG Track (ClimbMix) | NIST / LDC Data Agreement (Restricted) | TREC 2026 Test Collection | `global_context` / `broad` | Large-scale (100K+ segments) | Restricted participant agreement required; adapter currently generates synthetic sample. | **Reject for initial open baseline; defer to later restricted pilot** |
| **Vector Scale (100K)** | **BigANN / SIFT1M / Deep10M** | `ann-benchmarks.com` / Yandex BigANN | Public Domain / MIT | Standard HDF5 release | Vector Scale Only | 100K to 1M 128d/384d vectors | Pure vector index throughput; does not test text organization or hierarchical summarization. | **Admit for scale/ops lane only** |

---

## 2. Capability Portfolio Balance & Coverage Gaps

1. **Adequately Covered Dimensions (Ready for P-001)**:
   - *Direct / Semantic*: BEIR (SciFact, NFCorpus, FiQA) and BRIGHT (Coding/Math) provide excellent diversity across zero-shot factual lookup and difficult reasoning.
   - *Multi-Hop*: MultiHop-RAG and MuSiQue provide realistic multi-document evidence chains.
2. **Critical Gaps Requiring Deferred Resolution**:
   - *Temporal / Historical Valid Time*: LongMemEval adapter is currently synthetic; official download pipeline must be implemented in D2.
   - *Hierarchical Long Documents*: HiChunk adapter lacks official URL; needs pinned repository in D2.
   - *Real 100K Text Corpus*: A real-world 100K document text corpus (e.g. arXiv abstracts, Wikipedia subset, or technical RFCs) must be assembled for the 100K proof gate, replacing the synthetic scale generator.
