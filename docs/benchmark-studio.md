# Trace One-Click Benchmark & Live Demo Studio

The **Trace Benchmark & Live Demo Studio** is an interactive, visual evaluation and demonstration suite for Trace's evidence-preserving cognitive retrieval engine. It provides zero-setup, one-click benchmarking across real-world scale datasets, a live architectural interactive demo, and a side-by-side comparison arena against naive vector search, pure BM25, and standard unverified RAG.

---

## 🚀 Quickstart

### 1. Launch the Interactive Web Dashboard
Run a single command to open the Studio in your browser:

```powershell
uv run python main.py studio --open-browser
# or
uv run python scripts/benchmark_studio.py --ui --open-browser
```

Open your browser to [http://localhost:8501/studio](http://localhost:8501/studio) (or [http://localhost:8501/dashboard](http://localhost:8501/dashboard)).

### 2. Run Headless CLI Benchmarks
Run instant evaluations across discovered scale datasets or deterministic fixtures:

```powershell
# Run on deterministic fixture
uv run python main.py benchmark-suite --dataset fixture-technical-docs-v1 --max-cases 6

# Run on MuSiQue Multi-Hop dataset from C:\Users\anshu\AppData\Local\trace-scale-data
uv run python main.py benchmark-suite --dataset multihop-musique --max-cases 20

# Run with custom output report export
uv run python scripts/benchmark_studio.py --benchmark --dataset enron-emails --output report.json
```

---

## 🏛️ Features & Web UI Overview

```
+---------------------------------------------------------------------------------------+
|  🧠 TRACE HYBRID BENCHMARK & LIVE DEMO STUDIO                                         |
+---------------------------------------------------------------------------------------+
| [ 1. Interactive Architecture Demo ]  [ 2. One-Click Benchmark ]  [ 3. DB Arena ]     |
+---------------------------------------------------------------------------------------+
```

### 1. Interactive Architecture & Live Query Sandbox
- **Interactive Component Pipeline**: Visual nodes for Ingest Adapters ➔ Immutable Atoms ➔ Master WAL Spine ➔ Neocortex Projections.
- **5-Stage Sequential Lighting Animation**: Visual animation stepping through:
  1. `BM25 Lexical Filter` (fast candidate pruning)
  2. `Dense Vector Search` (semantic concept discovery)
  3. `Cortex Graph PageRank` (multi-hop entity expansion)
  4. `Hierarchy Holon Navigation` (namespace & container resolution)
  5. `Neocortex Grounding & Byte-Anchor Proof` (exact character span offset verification)
- **Zero-Hallucination Abstention**: Demonstrates how Trace returns `insufficient_evidence` when evidence does not exist in the corpus, preventing hallucinations.

### 2. One-Click Benchmark Suite with Real-Time SSE Telemetry
- **Auto-Discovered Scale Datasets**:
  - `multihop-musique`: 12,493 multi-hop articles & 1,000 queries
  - `enron-emails`: 50,000 corporate emails
  - `sec-edgar`: SEC 10-K / 10-Q financial filings & footnotes
  - `wikipedia-stream`: Wikipedia encyclopedic articles
  - `lkml-commits`: Linux kernel mailing list discussions
  - `fixture-technical-docs-v1`: 6-case deterministic developer fixture
  - `fixture-bright-coding-v1`: BRIGHT coding reasoning fixture
- **Live Streaming Metrics**:
  - Real-time Server-Sent Events (SSE) progress bar and query streaming log.
  - Metrics cards: `Recall@5`, `Recall@20`, `NDCG@10`, `Citation Precision`, `Complete Gold Evidence Coverage`, `Abstention Accuracy`, `P50/P95 Latency`, `Cloud Token Cost`.
  - Chart.js Radar and Latency Bar Charts.

### 3. Side-by-Side Comparison Arena
Compare queries across 4 distinct paradigms side-by-side:
1. **Trace 5-Stage Hybrid**: Full multi-hop retrieval with exact byte-anchor citation proof and verified abstention.
2. **Pure Dense Vector**: Cosine similarity top-K embeddings (illustrates missing graph links & contextual blindness).
3. **Pure Lexical (BM25)**: Keyword search only (illustrates failure on synonyms, paraphrasing, and multi-hop questions).
4. **Naive RAG**: Top-K chunk injection with unanchored generation (illustrates plausible hallucinations on out-of-scope queries).

### 4. System & Custom Database Connectors
- Real-time view of active Master WAL Spine database (`trace_master_spine.db`).
- Configurable model gateway, cloud vs. local model policies, and custom database connector adapters (PostgreSQL with pgvector, OpenSearch, etc.).

---

## 📦 Discovered Dataset Manifest

Datasets located in `C:\Users\anshu\AppData\Local\trace-scale-data` are automatically cataloged at startup:

| Dataset ID | Name | Category | Record Count |
| :--- | :--- | :--- | :--- |
| `multihop-musique` | MuSiQue Multi-Hop Corpus | Multi-Hop Reasoning | 12,493 |
| `enron-emails` | Enron Corporate Communications | Enterprise Email | 50,000 |
| `sec-edgar` | SEC EDGAR Filings | Financial / Regulatory | 50 |
| `wikipedia-stream`| Wikipedia Knowledge Stream | Encyclopedic | 500 |
| `lkml-commits` | Linux Kernel Commits | Code / Kernel | 31 |
| `fixture-technical-docs-v1` | Trace Technical Docs | Developer Fixture | 6 |
| `fixture-bright-coding-v1` | BRIGHT Coding Fixture | Coding Reasoning | 3 |

---

## 🧪 Testing

The studio test suite validates dataset discovery, comparative engines, telemetry calculations, and API routes:

```powershell
uv run pytest tests/test_v2_studio.py
```
