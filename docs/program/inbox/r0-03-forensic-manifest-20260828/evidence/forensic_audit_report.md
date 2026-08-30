# Forensic Audit Report: Read-Only Forensic Manifest & Custody Audit (R0-03)

> **Packet ID:** `r0-03-forensic-manifest-20260828`
> **Role:** Custody & Forensics Specialist
> **Wave:** Wave R0 (Containment, Claim Inventory & Forensics)
> **Authority:** `SCALE_CERTIFICATION_RECOVERY_PLAN.md` (R0-03) & `00_GLOBAL_CONTEXT_RECOVERY.md`
> **Audit Date:** 2026-08-28
> **Operating Mode:** Strictly Read-Only (Zero-Mutation Custody Invariant Preserved)
> **Status:** **COMPLETE / EVIDENCE SEALED**

---

## 1. Executive Summary & High-Severity Forensic Findings

As part of Wave R0 of the Scale Certification Recovery Plan, a strictly read-only forensic inspection was conducted across external data stores, scale corpora, and benchmark run artifacts.

The custody audit establishes three definitive, empirically proven forensic conclusions:

### Finding 1: The Disconnected Ingestion Loop (Spine Event Count = 45 vs Claimed 1,000,000)
The external master database [`trace_master_spine.db`](file:///mnt/c/Users/anshu/AppData/Local/trace-scale-data/trace_master_spine.db) (file size: **700,416 bytes**, SHA-256: `18f76269ebfdfec90bc9a9244ee163ec4ec7a7b8e5c8e3ca71d2bcf39c2c0199`) contains **only 45 SQLite events, 2 ingestions, 9 nodes, and 7 edges**.
Forensic analysis of the runner code (`scripts/run_1m_scale_gate.py`) and database state proves that the claimed "1,000,000 document ingestion" was purely an in-memory loop counter updating Python variables. No durable ingestion of the million documents ever occurred into the SQLite Spine.

### Finding 2: The 63,071 Unique Document Ceiling & 15.85x Synthetic Looping
The raw corpora in `/mnt/c/Users/anshu/AppData/Local/trace-scale-data/` contain a combined total of **only 63,071 unique text documents** across the 5 primary datasets (**63,076** including 2WikiMultiHop).
To reach the claimed "1,000,000 document scale", the benchmark ingestion loop repeated this 63,071 document set **~15.85 times** in an infinite/modulo iterator. Consequently, **93.69% of all 1M loop iterations were duplicate repetitions** of the same underlying texts.

### Finding 3: Benchmark Self-Authorship and In-Memory Fallback
The retained benchmark result [`benchmarks/runs/llm_benchmark_results.json`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/benchmarks/runs/llm_benchmark_results.json) (SHA-256: `749af1d886d8b93fe0f782d9fee93589240b7ad2bbfed7fd4ab2f4efaab05c5c`) reports a 100% "grounded factual accuracy" and 100% "zero hallucination rate" based on evaluating **only 5 self-authored queries** about Trace internal architecture against self-seeded landmark text.

---

## 2. Forensic Inspection of `trace_master_spine.db`

### 2.1 File Identity & Integrity Attributes
A quiescent binary SHA-256 digest and filesystem stat were computed:

| Attribute | Value |
| :--- | :--- |
| **Path** | `/mnt/c/Users/anshu/AppData/Local/trace-scale-data/trace_master_spine.db` |
| **File Size** | `700,416` bytes (`684.00` KB / `0.668` MB) |
| **Quiescent SHA-256** | `18f76269ebfdfec90bc9a9244ee163ec4ec7a7b8e5c8e3ca71d2bcf39c2c0199` |
| **Filesystem Modification Time (mtime)** | `2026-08-28T09:54:17.394376` |
| **Connection Mode** | Read-Only URI (`file:.../trace_master_spine.db?mode=ro`) |

### 2.2 SQLite PRAGMA Diagnostics

```sql
PRAGMA integrity_check;   -- Result: ok
PRAGMA quick_check;       -- Result: ok
PRAGMA journal_mode;       -- Result: wal
PRAGMA page_count;         -- Result: 171 pages
PRAGMA page_size;          -- Result: 4096 bytes
PRAGMA freelist_count;     -- Result: 0 pages
PRAGMA user_version;       -- Result: 0
PRAGMA schema_version;     -- Result: 42
PRAGMA synchronous;        -- Result: 2 (FULL)
PRAGMA encoding;           -- Result: "UTF-8"
PRAGMA foreign_keys;       -- Result: 0 (Disabled at connection time)
```

The database is structurally intact (`integrity_check = ok`) with SQLite WAL mode enabled. However, the allocation of only 171 pages (700 KB) confirms beyond doubt that no substantial document corpus was ever written to disk.

### 2.3 Complete SQLite Table Row Inventory

A full audit of all 40 declared tables in `sqlite_master` was performed:

| Table Name | Category | Exact Row Count | Status / Notes |
| :--- | :--- | :---: | :--- |
| `events` | Event Store | **45** | Spine append-only event stream |
| `outbox` | Messaging | **45** | Outbox messages mirroring events |
| `ingestions` | Data Plane | **2** | 1 in `1m_eval`, 1 in `1m_hybrid_eval` |
| `attachments` | Data Plane | **2** | Raw binary/text payload anchors |
| `attachment_staging` | Data Plane | **2** | Staged ingestion state |
| `nodes` | Knowledge Graph | **9** | 1 in `1m_eval`, 8 in `1m_hybrid_eval` |
| `node_versions` | Knowledge Graph | **9** | Immutable node state records |
| `source_lifecycle` | Data Plane | **9** | Active atom lifecycle state |
| `edge_versions` | Knowledge Graph | **7** | Versioned semantic edges |
| `evidence_anchors` | Provenance | **14** | Source byte slice references |
| `projection_revisions` | Projections | **2** | Projection metadata records |
| `hot_inbox` | Ingestion | **9** | Hot staging records |
| `proposals` | Governance | **1** | Schema/taxonomy proposal |
| `evidence_bundles` | Retrieval | **7** | Query evidence bundles |
| `cortex_releases` | Projections | **1** | Release `6005e790-a775-4b54-955c-d95618a85ef0` |
| `cortex_release_components` | Projections | **5** | hierarchy, affinity, lexical, dense, priors |
| `ingestion_index_state` | Indexing | **6** | Index tracking records |
| `erasure_operations` | Compliance | **0** | No records |
| `retrieval_feedback` | Retrieval | **0** | No records |
| `benchmark_runs` | Benchmark | **0** | No records |
| `dense_vectors` | Vector Store | **0** | No dense embeddings stored |
| `saved_queries` | Query Store | **0** | No records |
| `frozen_queries` | Query Store | **0** | No records |
| `index_revisions` | Indexing | **0** | No records |
| `model_registry` | ML Models | **0** | No records |
| `experiment_manifests` | Experiments | **0** | No records |
| `snapshots` | Backups | **0** | No records |
| `jobs` | Job Queue | **0** | No records |
| `projection_events` | Projections | **0** | No records |
| `webhooks` | Integration | **0** | No records |
| `webhook_deliveries` | Integration | **0** | No records |
| `api_keys` | Security | **0** | No records |
| `model_call_audits` | Telemetry | **0** | No records |
| `cognitive_policy_versions`| Policy | **0** | No records |
| `projection_runs` | Projections | **0** | No records |
| `projection_objects` | Projections | **0** | No records |
| `projection_memberships` | Projections | **0** | No records |
| `affinity_edges` | Graph | **0** | No records |
| `affinity_rejections` | Graph | **0** | No records |
| `activation_priors` | Graph | **0** | No records |

### 2.4 Events Stream & Watermark Analysis

- **Event Offset Range:** `1` to `45` (Continuous, no gaps).
- **Event ID Range:** Min `02163793-d226-4e3f-abba-daaf35ee829c` to Max `fa0259ba-5e49-4350-bbb3-3369ddfe64cb`.
- **Timestamp Range:** `2026-08-28T09:31:41.593311+00:00` to `2026-08-28T09:54:15.674403+00:00` (Span: 22 minutes 34 seconds).
- **Distinct Streams:** 18
  - `workspace:1m_hybrid_eval`: 21 events
  - `workspace:1m_eval`: 8 events
  - 9 individual node streams (`node:<uuid>`): 1 event each
  - 7 individual edge streams (`edge:<uuid>`): 1 event each
- **Event Types Breakdown:**
  - `node.created`: 9
  - `node.versioned`: 9
  - `edge.versioned`: 7
  - `evidence_bundle.created`: 7
  - `attachment.recorded`: 2
  - `attachment.staged`: 2
  - `attachment.staging_committed`: 2
  - `ingestion.accepted`: 2
  - `ingestion.atomized`: 2
  - `ingestion.index_state_updated`: 2
  - `proposal.created`: 1

### 2.5 Contrast: Claimed 1M Documents vs Actual DB Reality

| Evaluation Dimension | Benchmark Runner Claim | Physical Forensic Reality | Evidentiary Verdict |
| :--- | :--- | :--- | :--- |
| **Ingested Documents** | `1,000,000` documents | **2** ingestions (9 atoms total) | **FABRICATED / UNGROUNDED** |
| **Event Stream Count** | `1,000,000+` events | **45** events | **UNPERSISTED** |
| **Knowledge Graph Nodes** | Complete multi-corpus graph | **9** nodes | **TRIVIAL PREFIX** |
| **Knowledge Graph Edges** | Scale semantic connectivity | **7** edges | **TRIVIAL PREFIX** |
| **Dense Vector Embeddings**| 1M embeddings | **0** embeddings | **NON-EXISTENT** |
| **Cortex Releases** | Certified 1M Release | **1** bootstrap-v0 stub | **STUB ONLY** |

---

## 3. Forensic Inspection & Deduplication Audit of Scale Corpora

### 3.1 Inventory of Corpus Files in `trace-scale-data/`

All datasets located in `/mnt/c/Users/anshu/AppData/Local/trace-scale-data/` were audited at byte, record, and content levels:

| Relative File Path | Size (Bytes) | Size (MB) | Quiescent SHA-256 | Line Count | Valid Records | Unique Content Texts |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `enron/enron_emails.jsonl` | `203,459,076` | 194.03 | `4f9cc47b7e00fd6a89ff6e420bc3933b3c474044b8ceeb9c6f41a2491b4b5e6d` | 50,000 | 50,000 | 50,000 |
| `lkml/lkml_commits.jsonl` | `202,775,494` | 193.38 | `da65054eb7182843cb03af86d9f1412c861b774151cc49f177367e8034f21cd7` | 31 | 31 | 31 |
| `edgar/sec_edgar_filings.jsonl` | `4,075,941` | 3.89 | `a11a3ad8b174e40941840fde99cce5b9c430149c09639c629ede41829b73836f` | 50 | 50 | 47 |
| `wikipedia/wikipedia_stream.jsonl` | `1,933,222` | 1.84 | `7fb07abced3848a6ec6803571b9f0e40c7bbd9264feec183b41b0ab76459859a` | 500 | 500 | 500 |
| `multihop/musique_corpus.jsonl` | `12,730,930` | 12.14 | `7f8041692226f5c8ddf01777a3a66322e3bd04312b87c93487e9d16bdaa3c20e` | 12,493 | 12,493 | 12,493 |
| `multihop/2wikimultihop_corpus.jsonl`| `3,540` | 0.003 | `d19eb980e29e1039da710f6c8263a14348088576e20c971f4a48c5de3a75f705` | 5 | 5 | 5 |
| **Total Scale Corpus** | **425,002,203** | **405.31** | *(Combined Corpus Pool)* | **63,079** | **63,079** | **63,076** |

*(Note: EDGAR filings contained 3 duplicated text bodies across 50 records, yielding 47 unique texts. Across the primary 5 datasets, the unique text total is exactly **63,071**).*

### 3.2 Deduplication Audit & Mathematical Proof of Synthetic Repetition

```
Primary Corpus Unique Text Breakdown:
  + Enron Emails:             50,000 unique texts
  + MusiQue MultiHop Corpus:  12,493 unique texts
  + Wikipedia Articles:          500 unique texts
  + SEC EDGAR Filings:            47 unique texts (out of 50 records)
  + LKML Commits:                 31 unique texts (large diff blocks)
  -------------------------------------------------------------
  Canonical 5-Corpus Total:   63,071 UNIQUE DOCUMENTS
  + 2WikiMultiHop:                 5 unique texts
  -------------------------------------------------------------
  All-6 Corpus Pool Total:    63,076 UNIQUE DOCUMENTS
```

#### The Duplication Multiplier
To execute a loop of N = 1,000,000 iterations using a pool of U = 63,071 unique source documents:
- **Duplication Factor:** 1,000,000 / 63,071 = **15.8551x**
- **Synthetic Duplication Rate:** (1 - 63,071 / 1,000,000) * 100% = **93.6929%**

This confirms that the 1M scale claims were grounded on repeating a ~63K dataset nearly 16 times in memory.

### 3.3 Binary & Secondary Scale Data Assets

| File Path | Size (Bytes) | Size (MB) | SHA-256 Digest | Notes |
| :--- | :---: | :---: | :---: | :--- |
| `enron/enron_mail_20150507.tar.gz` | `443,254,787` | 422.72 | `b3da1b3fe0369ec3140bb4fbce94702c33b7da810ec15d718b3fadf5cd748ca7` | Raw maildir archive |
| `wikipedia/wikipedia.db` | `2,252,800` | 2.15 | `0a9f3bf785d6941a914fa243d91f66a51ee3816c60b1e7b03767031c651179bd` | SQLite DB (504 articles) |
| `wikipedia/wikipedia_bulk.db` | `16,515,072` | 15.75 | `32ac1ae7612997ad1a88bb45886cf88cef596a77498e99d518117343cdcf001e` | SQLite DB (3,748 articles) |
| `wikipedia/wikipedia_bulk_stream.jsonl` | `15,723,403` | 14.99 | `6abefc80e730a0cba0415a9e907fa1077cf6a60e9e0a9d3db84d857d316abbe0` | 3,744 JSONL records |
| `edgar/sp100_sec_edgar_bulk.jsonl` | `37,996,366` | 36.24 | `8bb920eae2133f35447b835d51843c18b9f01d7337767425ec2aa476d3c21200` | 300 JSONL records |
| `multihop/musique_queries.jsonl` | `1,751,135` | 1.67 | `1842b7ccfc64771ead2a347baa48bb448f8172d9d572229ddf7823128617f7f0` | 1,000 test queries |
| `multihop/2wikimultihop_queries.jsonl` | `2,131` | 0.002 | `2272163b811cbf300cee375dba90e321025c412c15d071d72d9d776dedf214d8` | 2 test queries |
| `1m_scale_corpus_manifest.json` | `1,995` | 0.002 | `88d7fb5be399083572894a152ac208f0ffd58bd3a8a17703dbc63e77c2e08885` | Legacy manifest |

---

## 4. Forensic Inspection of Benchmark Runs & Data

### 4.1 Audit of `benchmarks/runs/llm_benchmark_results.json`

- **File Path:** [`benchmarks/runs/llm_benchmark_results.json`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/benchmarks/runs/llm_benchmark_results.json)
- **Size:** `3,142` bytes
- **SHA-256:** `749af1d886d8b93fe0f782d9fee93589240b7ad2bbfed7fd4ab2f4efaab05c5c`
- **Reported Run Timestamp:** `2026-08-28T05:19:33Z`
- **Model Identifier:** `openrouter/deepseek/deepseek-v4-flash-0731`
- **Cases Evaluated:** 5
- **Claimed Metrics:**
  - `grounded_factual_accuracy`: `1.0` (100%)
  - `zero_hallucination_rate`: `1.0` (100%)
  - `total_citations_verified`: `11`
- **Evaluated Query Contents:**
  1. *"What theory is Trace architecture built on?"*
  2. *"How does retrieval combine lexical and graph methods?"*
  3. *"What must happen before activating Trace version 2.0?"*
  4. *"What validates workspace authentication tokens and scopes?"*
  5. *"What logging format does the Spine provide?"*

**Forensic Evaluation:**
The test questions were created by the system developers about Trace internal code concepts and evaluated against landmark texts self-seeded into the store. A 5-prompt evaluation cannot substantiate a general 1M-scale factual grounding or zero-hallucination rate.

### 4.2 Survey of `trace-bench-data/` Directories

The benchmark data repository at `/mnt/c/Users/anshu/AppData/Local/trace-bench-data/` comprises **1,153 files** totaling **35,744.09 MB (~34.91 GB)** across 9 directories:

| Directory | Total Files | Total Size (MB) | Primary Content / Purpose |
| :--- | :---: | :---: | :--- |
| `beir-fiqa` | 13 | 73.45 | BEIR Financial QA benchmark corpus |
| `beir-nfcorpus` | 13 | 11.99 | BEIR Medical nutrition corpus |
| `beir-scifact` | 12 | 12.24 | BEIR Scientific claim verification |
| `bigann` | 12 | 710.58 | Approximate nearest neighbor vector benchmarks |
| `bright` | 18 | 374.62 | BRIGHT reasoning evaluation corpus |
| `multihop-rag` | 8 | 11.44 | Multi-hop reasoning dataset |
| `musique` | 8 | 258.97 | MusiQue 2-4 hop reasoning corpus |
| `normalized` | 270 | 9,109.33 | Normalized parquet/jsonl chunks from S4/D2B |
| `verification` | 799 | 25,182.49 | S4 reproduction verification output (d2b-20260819) |

---

## 5. Custody Invariant Verification & Recommendations

### 5.1 Verification of Zero-Mutation Invariant
All inspections were executed with strictly read-only primitives:
- Python standard library `sqlite3` was opened strictly using `uri=True` with `file:...db?mode=ro`.
- File reads were performed in streaming binary read mode (`rb`).
- Filesystem modification timestamps on all external databases and corpora remain untouched.

### 5.2 Evidentiary Custody Classification
Pursuant to Section 4.2 of `SCALE_CERTIFICATION_RECOVERY_PLAN.md`:
1. `trace_master_spine.db` is classified as **`revoked`** forensic evidence. It cannot serve as a bootstrap spine for Level 1 or Level 2.
2. The legacy 1M scorecards and benchmark JSONs are classified as **`revoked`**.
3. The raw corpus files (`enron_emails.jsonl`, `musique_corpus.jsonl`, etc.) are retained as immutable raw inputs; however, their frozen D-count is capped at **63,071**.

### 5.3 Recommendations for Level 1 (100K Requalification)
- **Do not reuse `trace_master_spine.db`**: Level 1 candidate execution must write to a completely fresh, isolated candidate data root.
- **Corpus Expansion Required for 100K**: The existing 63,071 unique documents are insufficient to reach a real 100K D-count without duplication. Additional real, license-cleared sources (e.g. expanding Enron, Wikipedia bulk, or BEIR) must be formally locked in L1-02 before running a 100K candidate.
- **Enforce Database Commit Parity**: The repaired runner (L1-04) must verify SQLite committed transaction counts against document input counts.

---
*Sealed and attested by Custody & Forensics Specialist on 2026-08-28.*
