# Real-Data Portfolio Layout and Schema Observation Summary

**DAG Node:** B2 / D2a
**Admission Authority:** DEC-P-001
**Staging Root:** `C:\Users\anshu\AppData\Local\trace-bench-data`
**Generated At:** 2026-08-19

## 1. Portfolio Overview

| Dataset Key | Dataset Name | Admitted Domains / Tasks | Total Documents | Total Queries | Total Judgments / Ground Truth | Raw Storage Size |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `beir-scifact` | BEIR SciFact | Scientific claim verification | 5,183 | 1,109 | 1,280 (test + train) | 12.24 MB |
| `beir-nfcorpus` | BEIR NFCorpus | Biomedical / nutrition retrieval | 3,633 | 3,237 | 134,294 (test + dev + train) | 11.99 MB |
| `beir-fiqa` | BEIR FiQA | Financial QA and opinion retrieval | 57,638 | 6,648 | 17,110 (test + dev + train) | 73.45 MB |
| `bright` | BRIGHT | Coding (leetcode, stackoverflow, pony) & Math (aops, theoremqa_questions, theoremqa_theorems) | 928,750 | 752 | 1,770 (gold pairs) | 374.62 MB |
| `multihop-rag` | MultiHop-RAG | Multi-document cross-hop evidence QA | 609 | 2,556 | 6,104 (evidence links) | 11.44 MB |
| `musique` | MuSiQue | Compositional multi-hop QA (2/3/4 hops) | 48,340 paragraphs (dev) / 398,760 (train) | 22,355 (dev: 2,417, train: 19,938) | 57,801 (supporting paragraphs) | 258.96 MB |
| `bigann` | BigANN / SIFT1M | Operations & vector scale ONLY (DEC-P-001) | 1,000,000 (128-d base vectors) | 10,000 (query vectors) | 10,000 x 100-NN (ground truth) | 710.58 MB |

---

## 2. Dataset-by-Dataset Structural Analysis

### 2.1 BEIR SciFact (`beir-scifact`)
- **Staging Path:** `C:\Users\anshu\AppData\Local\trace-bench-data\beir-scifact\`
- **Files Staged:**
  - `raw/corpus-00000-of-00001.parquet` (4.47 MB)
  - `raw/queries-00000-of-00001.parquet` (64.98 KB)
  - `raw/scifact/corpus.jsonl` (5,183 documents)
  - `raw/scifact/queries.jsonl` (1,109 queries)
  - `raw/scifact/qrels/test.tsv` (339 test judgments, 300 unique queries)
  - `raw/scifact/qrels/train.tsv` (941 train judgments, 809 unique queries)
  - `raw/README.md`
- **Native Document ID Format:** String representations of integers (e.g. `"4983"`, `"31715818"`).
- **Native Query ID Format:** String representations of integers (e.g. `"0"`, `"1"`).
- **Document Fields:** `_id` (str), `title` (str), `text` (str), `metadata` (dict).
- **Query Fields:** `_id` (str), `text` (str), `metadata` (dict).
- **Integrity Validation:** 100% of test and train query IDs exist in `queries.jsonl`; 100% of corpus IDs exist in `corpus.jsonl`. Zero orphan references.

### 2.2 BEIR NFCorpus (`beir-nfcorpus`)
- **Staging Path:** `C:\Users\anshu\AppData\Local\trace-bench-data\beir-nfcorpus\`
- **Files Staged:**
  - `raw/corpus-00000-of-00001.parquet` (3.97 MB)
  - `raw/queries-00000-of-00001.parquet` (82.99 KB)
  - `raw/nfcorpus/corpus.jsonl` (3,633 documents)
  - `raw/nfcorpus/queries.jsonl` (3,237 queries)
  - `raw/nfcorpus/qrels/test.tsv` (12,143 test judgments, 323 unique queries)
  - `raw/nfcorpus/qrels/dev.tsv` (11,460 dev judgments, 324 unique queries)
  - `raw/nfcorpus/qrels/train.tsv` (110,691 train judgments, 2,590 unique queries)
  - `raw/README.md`
- **Native Document ID Format:** Medical topic strings (e.g. `"MED-10"`, `"MED-1000"`).
- **Native Query ID Format:** Plain topic strings (e.g. `"PLAIN-1"`, `"PLAIN-10"`).
- **Document Fields:** `_id` (str), `title` (str), `text` (str), `metadata` (dict).
- **Query Fields:** `_id` (str), `text` (str), `metadata` (dict).
- **Integrity Validation:** 100% referential integrity across test, dev, and train splits.

### 2.3 BEIR FiQA (`beir-fiqa`)
- **Staging Path:** `C:\Users\anshu\AppData\Local\trace-bench-data\beir-fiqa\`
- **Files Staged:**
  - `raw/corpus-00000-of-00001.parquet` (27.70 MB)
  - `raw/queries-00000-of-00001.parquet` (321.68 KB)
  - `raw/fiqa/corpus.jsonl` (57,638 documents)
  - `raw/fiqa/queries.jsonl` (6,648 queries)
  - `raw/fiqa/qrels/test.tsv` (1,706 test judgments, 648 unique queries)
  - `raw/fiqa/qrels/dev.tsv` (1,237 dev judgments, 500 unique queries)
  - `raw/fiqa/qrels/train.tsv` (14,167 train judgments, 5,500 unique queries)
  - `raw/README.md`
- **Native Document ID Format:** Financial corpus string integers (e.g. `"1"`, `"10001"`).
- **Native Query ID Format:** Query string integers (e.g. `"0"`, `"1"`, `"2"`).
- **Document Fields:** `_id` (str), `title` (str), `text` (str), `metadata` (dict).
- **Query Fields:** `_id` (str), `text` (str), `metadata` (dict).
- **Integrity Validation:** 100% referential integrity across all splits.

### 2.4 BRIGHT (`bright`)
- **Staging Path:** `C:\Users\anshu\AppData\Local\trace-bench-data\bright\`
- **Admitted Subsets under DEC-P-001:**
  - **Coding Lane:** `leetcode`, `stackoverflow`, `pony`
  - **Math Lane:** `aops`, `theoremqa_questions`, `theoremqa_theorems`
- **Files Staged:**
  - `raw/documents/leetcode-00000-of-00001.parquet` (43,767 docs, 210.51 MB)
  - `raw/examples/leetcode-00000-of-00001.parquet` (159 queries, 168.56 KB)
  - `raw/documents/stackoverflow-00000-of-00001.parquet` (78,614 docs, 39.49 MB)
  - `raw/examples/stackoverflow-00000-of-00001.parquet` (134 queries, 250.46 KB)
  - `raw/documents/pony-00000-of-00001.parquet` (2,732 docs, 1.13 MB)
  - `raw/examples/pony-00000-of-00001.parquet` (41 queries, 27.72 KB)
  - `raw/documents/aops-00000-of-00001.parquet` (396,447 docs, 65.30 MB)
  - `raw/examples/aops-00000-of-00001.parquet` (186 queries, 1.34 MB)
  - `raw/documents/theoremqa_questions-00000-of-00001.parquet` (396,447 docs, 65.30 MB)
  - `raw/examples/theoremqa_questions-00000-of-00001.parquet` (187 queries, 1.49 MB)
  - `raw/documents/theoremqa_theorems-00000-of-00001.parquet` (10,743 docs, 7.63 MB)
  - `raw/examples/theoremqa_theorems-00000-of-00001.parquet` (45 queries, 124.48 KB)
  - `raw/README.md` (17.47 KB)
- **Document Schema:** `id` (str), `content` (str).
- **Example/Query Schema:** `id` (str), `query` (str), `gold_ids` (list of str).
- **Aggregate Metrics:** 928,750 total documents, 752 queries, 1,770 gold document pairs across 6 subsets.
- **Integrity Validation:** 100% of gold IDs referenced in examples exist in their respective document corpora.

### 2.5 MultiHop-RAG (`multihop-rag`)
- **Staging Path:** `C:\Users\anshu\AppData\Local\trace-bench-data\multihop-rag\`
- **Files Staged:**
  - `raw/MultiHopRAG.json` (2,556 multi-hop queries, 5.17 MB)
  - `raw/corpus.json` (609 news documents, 6.79 MB)
  - `raw/README.md` (1.31 KB)
- **Query Fields:** `query`, `answer`, `evidence_list`, `question_type`, `fact_list`.
- **Question Types:** `inference_query` (1,043), `comparison_query` (662), `temporal_query` (511), `null_query` (340).
- **Hop Distribution:** 2 hops (1,682 queries), 3 hops (756 queries), 4 hops (118 queries). Total evidence links: 6,104.
- **Corpus Fields:** `title`, `text`, `source`, `published_at`, `url`.
- **Source Distribution:** BBC (156), Reuters (142), CNN (128), Guardian (104), AP News (79).

### 2.6 MuSiQue (`musique`)
- **Staging Path:** `C:\Users\anshu\AppData\Local\trace-bench-data\musique\`
- **Files Staged:**
  - `raw/musique_ans_v1.0_dev.jsonl` (2,417 queries, 30.44 MB)
  - `raw/musique_ans_v1.0_train.jsonl` (19,938 queries, 241.05 MB)
  - `raw/README.md` (48.62 KB)
- **Record Schema:**
  - `id`: unique query string (e.g. `"2hop__12345_67890"`, `"3hop1__98765_43210"`)
  - `question`: complete multi-hop query string
  - `question_decomposition`: ordered list of single-hop subquestions with variable pointers (`#1`, `#2`)
  - `answer`: canonical gold answer string
  - `answer_alias`: list of alternative valid answer strings
  - `paragraphs`: list of 20 candidate paragraphs with `idx`, `title`, `paragraph_text`, and boolean `is_supporting` flag.
- **Dev Set Stats:** 2,417 queries; 48,340 total paragraphs; 6,241 supporting paragraphs (avg 2.58 per query); 2-hop (1,252), 3-hop (593), 4-hop (572).
- **Train Set Stats:** 19,938 queries; 398,760 total paragraphs; 51,560 supporting paragraphs (avg 2.59 per query); 2-hop (14,376), 3-hop (2,884), 4-hop (2,678).

### 2.7 BigANN / SIFT1M (`bigann`)
- **Staging Path:** `C:\Users\anshu\AppData\Local\trace-bench-data\bigann\`
- **Admitted Scope:** Operations / Vector-Scale Lane ONLY per DEC-P-001.
- **Files Staged:**
  - `raw/sift.tar.gz` (168.28 MB archive)
  - `raw/sift/sift_base.fvecs` (1,000,000 vectors x 128 float32 dimensions = 516,000,000 bytes)
  - `raw/sift/sift_query.fvecs` (10,000 vectors x 128 float32 dimensions = 5,160,000 bytes)
  - `raw/sift/sift_learn.fvecs` (25,000 vectors x 128 float32 dimensions = 12,900,000 bytes)
  - `raw/sift/sift_groundtruth.ivecs` (10,000 queries x 100 int32 nearest neighbors = 4,040,000 bytes)
  - `raw/fvecs_read.m` (1.36 KB)
  - `raw/ivecs_read.m` (1.36 KB)
- **Binary Format Verification:**
  - `.fvecs`: 4-byte `int32` dimension `d=128`, followed by `128` 4-byte `float32` values per vector. Exact record size = 516 bytes. All vector files verified to be exact integer multiples of 516 bytes.
  - `.ivecs`: 4-byte `int32` count `k=100`, followed by `100` 4-byte `int32` neighbor indices per query. Exact record size = 404 bytes. Ground truth file verified to be exact multiple of 404 bytes.
- **Sample Vector Norms:** Average L2 norm across sampled base vectors = 295.42 (valid SIFT descriptor range 0-255 per component).
