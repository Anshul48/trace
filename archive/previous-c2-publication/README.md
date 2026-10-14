# Trace

<div align="center">

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python: 3.12+](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](https://www.python.org/)
[![C2-10M: SHIP 2026-10-08](https://img.shields.io/badge/C2--10M-SHIP_2026--10--08-success.svg)](docs/C2-10M-PUBLICATION.md)
[![Pins: 89/89 verified](https://img.shields.io/badge/Pins-89%2F89_verified-success.svg)](c10m/README.md)

**Evidence-preserving retrieval: the pinned C2-10M historical release,
reproducible bench evidence, and runnable demos.**

[Run the demo](#quickstart-c2-10m-demo) •
[Publication record](docs/C2-10M-PUBLICATION.md) •
[Repro appendix](docs/C2-10M-REPRO-APPENDIX.md) •
[Bench evidence](benchmarks/evidence/) •
[Contributing](CONTRIBUTING.md) •
[Security](SECURITY.md)

</div>

---

## The release: C2-10M freeze-v2 (SHIP 2026-10-08)

This repository publishes the last receipt-backed successful old 10M
candidate: the **C2-10M freeze-v2 qualified release**, passed 7/7 gates
by an independent lane-READ10M review, shipped store pin
`ee06a4e4-83f7-4315-9e23-bd6e5034cccb:0:95436`, producer freeze
`c2-b100m-producer-freeze-002` with **89/89 bytes recovered and
hash-verified** (closure 44/44).

| what | where |
|---|---|
| Exact source (85 producer + 7 serving + policy + data) | [`c10m/`](c10m/README.md) (`PINS.sha256`, 110 entries) |
| Input-reconstruction recipe (verified `RECONSTRUCT PASS`) | [`c10m/data/`](c10m/data/DATA-README.md) |
| Primary demo (pinned stack, offline, <1 s) | [`demos/`](demos/README.md) |
| Bench harness + receipts + negatives + fixture repro | [`benchmarks/evidence/`](benchmarks/evidence/) |
| Claims, figures, limitations | [`docs/C2-10M-PUBLICATION.md`](docs/C2-10M-PUBLICATION.md) |
| Exact repro commands | [`docs/C2-10M-REPRO-APPENDIX.md`](docs/C2-10M-REPRO-APPENDIX.md) |

## Quickstart (C2-10M demo)

Requires Python 3.12+ on Linux/POSIX (the pinned store uses `fcntl`
locking).

```bash
pip install -e .[c10m]
python demos/demo_c10m_narrow.py
# DEMO PASS: pinned C2-10M serving stack ran offline (6 synth docs, 3 queries, budgets M80-P100-A40).
```

The demo runs the pinned serving stack (TLStore → ingest → NarrowIndex
→ NarrowQuery, budgets M80-P100-A40) over a 6-document synthetic
corpus. Rendered walkthroughs: the static offline
[inspector](demos/c10m_inspector.html) and its
[text equivalent](demos/c10m_tutorial.md). The shipped stack encodes
with MiniLM-L6-v2 (weights + torch, not vendored); the demo discloses
a deterministic SHA-256 stand-in encoder — its scores are NEVER 10M
measurements. What the demo proves is that the pinned code paths run.

## Measured conditions

Persistent serving process + resident MiniLM encoder. Warm 1620–2358 ms
and storage-cold 3530 ms PASS vs 5 s; fresh-process first request
~8–10 s exceeds (voids latency claims outside the condition;
correctness stands). On the resident 10M store, queries take ~1 s but
each NarrowIndex (re)attach costs ~2 min and dominates cold serving
(two probe runs agree; 5/5 requests, 40/40 entries).

## Evidence, honestly

- Fresh-store lanes (1061 queries × arms, 0 failures): the shipped
  stack trails bm25/dense on 4 of 5 lanes and leads on BRIGHT-pony —
  all arms and misses preserved, none promoted selectively.
- Frozen 10M rung: TL ndcg10 0.6311, 0 errors; provisional latency
  MISS recorded as the specified "superlinear latency regime" finding.
- Campaign-186 completed later with ORIGINAL F2 overall FAIL
  (fresh-reader p95 13.3–13.9 s); it ships as evidence WITH its
  failures, never as the build. No thresholds rewritten.
- 100M retrieval is NOT evidenced and NOT claimed.

Details: [publication record](docs/C2-10M-PUBLICATION.md) and
[bench evidence](benchmarks/evidence/).

## Limitations

- Demo/synthetic surfaces prove code paths, never quality at scale.
- Fresh-store scores must never be quoted as 10M results.
- Latency claims hold only inside the deployment condition above.
- Corpus texts carry dataset-specific licenses/attribution (see
  [`c10m/data/DATA-README.md`](c10m/data/DATA-README.md)), not the
  repository's Apache-2.0 grant.

---

## Legacy surfaces (explicitly separate)

The older **Phase 1** (lightweight local core: `trace_local` SDK/CLI)
and **Trace V2 / Cortical Substrate v1.1** (TOC-DAG, two-pass PPR,
3-tier cascade, Epoch RCU) product surfaces remain in this tree and
keep working, but they are **not** the C2-10M candidate: their badges,
gates, and benchmarks below do not certify the C2-10M release, and
nothing below re-states C2-10M claims.

### Legacy: Phase 1 CLI & SDK

```bash
pip install -e .
trace init --data-dir ./my-trace-data
trace ingest --data-dir ./my-trace-data ./documents.jsonl
trace query --data-dir ./my-trace-data "memory-mapped lease swap"
trace verify --data-dir ./my-trace-data
```

```python
from trace_local import Trace

with Trace.open("./my-trace-data") as trace:
    trace.ingest({
        "record_id": "arch-001",
        "document_name": "Epoch_RCU.md",
        "file_uri": "file:///docs/epoch_rcu.md",
        "content": "Active reader leases track process IDs to prevent file unlinking during mmap reads.",
        "metadata": {"subsystem": "storage"},
    })
    evidence = trace.query("reader leases mmap")
    for hit in evidence["results"]:
        print(f"Document: {hit['document_name']}")
        print(f"Matched text: {hit['matched_span']}")
        print(f"Offsets: {hit['offsets']}")
        print(f"SHA-256: {hit['content_hash']}")
```

Legacy demo: `python demos/demo_phase1_api.py` (3-doc fixture,
init/ingest/query/refuse/verify). Guides: [Quickstart](docs/QUICKSTART.md),
[Phase 1 local-first](docs/phase1-local-first.md).

### Legacy: Trace V2 core invariants & guarantees

1. **Byte-Exact Provenance**: every matched span satisfies
   `span_text == normalized_text[start:end]`, with SHA-256 and BLAKE3
   content identifiers. No generative model rewrites source citations.
2. **Single-Copy Storage**: SQLite external-content FTS5 tables;
   hot on-disk footprint bounded to ≤ 3.0× admitted UTF-8 text
   (measured at 0.0997× on the legacy 100k benchmarks — a legacy
   figure, not a C2-10M claim).
3. **Fail-Closed Execution**: explicit `insufficient_evidence` when no
   relevant evidence is found; corrupt state raises instead of
   degrading silently.
4. **Cross-Platform Epoch RCU**: isolated compaction generations with
   atomic pointer swaps and reader leases (no Windows mmap `WinError 32`).

### Legacy: V2 3-tier retrieval architecture

```mermaid
flowchart TD
    Q([Incoming Query]) --> T1{Tier 1: Lexical Short-Circuit\n<= 5 ms}
    T1 -- "Quoted / UPPER_SNAKE / Code Match" --> V[3-Stage Grounding Verifier]
    T1 -- "No Exact Match" --> T2{Tier 2: Hierarchical Beam\n<= 35 ms}

    subgraph Substrate [Cortical Substrate V1.1]
        T2 --> TOC[TOC-DAG Macro Hierarchy\nBisecting 2-Means]
        TOC --> PPR[Two-Pass Lateral Rectification PPR\nExcitatory + Inhibitory Suppression]
    end

    PPR -- "Beam Candidates" --> V
    T2 -- "Low Cohesion / Fallback" --> T3{Tier 3: Flat Hybrid Control\n<= 25 ms}
    T3 --> RRF[Dense MiniLM kNN + BM25 Lexical\nReciprocal Rank Fusion]
    RRF --> V

    subgraph Grounding [Verification Pipeline]
        V --> G1[1. Polarity Parity Check]
        G1 --> G2[2. Entity Containment Recall >= 0.80]
        G2 --> G3[3. Cross-Encoder NLI Classification]
    end

    G3 -- "Verified Grounding" --> OUT([Immutable Evidence Bundle])
    G3 -- "Contradicted / Unverified" --> FAIL([insufficient_evidence])
```

Docs: [Cortical Substrate](docs/CORTICAL_SUBSTRATE.md),
[V2 architecture](docs/v2-architecture.md).

### Legacy: 100K qualification & benchmark results

Legacy TraceV2 qualification on a 100,000-document snapshot (SciFact,
NFCorpus, FIQA; 1,000 judged queries; 5 ablation arms):

| Ablation Arm | Configuration | nDCG@10 | Recall@20 | MRR@20 | p95 Latency |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `bm25_only` | Pure BM25 inverted lexical search | 0.4412 | 0.4721 | 0.4690 | 4.65 ms |
| `dense_only` | Dense all-MiniLM-L6-v2 embeddings | 0.4682 | 0.5012 | 0.4851 | 12.80 ms |
| `hybrid_rrf` | **Tier 3 Flat Hybrid Control** (Dense + BM25 RRF) | 0.5019 | 0.5482 | 0.5284 | 17.25 ms |
| `graph_csr` | Hybrid RRF + Graph CSR Spreading Activation | 0.5098 | 0.5591 | 0.5389 | 20.84 ms |
| `toc_beam` | **Tier 2 Top-Down TOC Beam Search** + Two-Pass PPR | **0.5141** | **0.5684** | **0.5492** | 24.95 ms |

| Acceptance Gate | Appendix A Limit | Measured Live Result | Status |
| :--- | :--- | :--- | :--- |
| **Total-Hot Storage Multiplier** | ≤ 3.0× admitted raw text | **0.0997×** (6.52 MB / 65.39 MB) | **PASS** |
| **Durable Spine Multiplier** | ≤ 1.6× admitted raw text | **0.0675×** (4.41 MB / 65.39 MB) | **PASS** |
| **Tier 2 Uplift Promotion Gate** | 95% CI > 0 (10,000 bootstraps) | **+0.0122** (95% CI: [+0.0118, +0.0127]) | **PROMOTE** |
| **Negation Inversion Rejection** | 100% rejected | **100%** | **PASS** |
| **Host Memory (RSS under load)** | Monitored via `psutil` | **27.73 MB** (Peak VmHWM: 55.74 MB) | **PASS** |

```bash
python benchmarks/run_100k_qualification.py --compare-profiles --verify-receipts
```

Methodology: [BENCHMARKS](docs/BENCHMARKS.md).

### Legacy: installation options

```bash
pip install trace-local                    # Phase 1 CLI & SDK
pip install "trace-local[production]"      # V2 Cortical Substrate
```

Development from source:

```bash
git clone https://github.com/Anshul48/trace.git
cd trace
uv venv .venv --python 3.12
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[test,production]"
```

---

## Project Structure

```text
trace/
├── c10m/                         # C2-10M freeze-v2 candidate (89/89, PINS.sha256)
│   ├── producer/                 # 85 frozen producer files (exact bytes)
│   ├── serving/                  # 7 serving files (repaired + pre-176 query.py)
│   ├── policy/                   # CRITERIA/requirements/anchors pins
│   └── data/                     # inputs + maps + reconstruct tool + DATA-README
├── demos/                        # primary C2-10M demo + inspector/tutorial, Phase 1 demo
├── benchmarks/evidence/          # bench harness + receipts + negatives + fixture repro
├── docs/                         # C2-10M publication + repro appendix + legacy docs
│   ├── C2-10M-PUBLICATION.md     # claims, figures, limitations
│   ├── C2-10M-REPRO-APPENDIX.md  # exact repro commands
│   └── program/                  # decision logs, invariants, binding plan
├── src/
│   ├── trace/                    # V2 Cortical Substrate engine (legacy surface)
│   └── trace_local/              # Phase 1 lightweight CLI/SDK (legacy surface)
├── tests/                        # real-fixture test suite (no domain mocks)
├── .github/                      # CI/CD workflows and issue/PR templates
├── CONTRIBUTING.md               # contribution guidelines & invariants
├── CODE_OF_CONDUCT.md           # Contributor Covenant v2.1
├── SECURITY.md                   # security policy & reporting
├── CITATION.cff                  # citation metadata
├── LICENSE                       # Apache License 2.0 (code; corpus texts carry own terms)
└── pyproject.toml                # packaging (extras: c10m, test, v2, production)
```

---

## Contributing

We welcome contributions! Please read our [Contributing Guide](CONTRIBUTING.md)
and [Code of Conduct](CODE_OF_CONDUCT.md) before submitting pull requests.

All contributions must preserve Trace's fundamental invariants:

- Zero domain/storage mocks in tests (real SQLite databases and subprocesses).
- Zero synthetic score fallbacks or swallowed exceptions.
- Strict byte-exact span provenance.
- Additive schema migrations.
- Pinned `c10m/` bytes are immutable: never edit them in place; any new
  candidate is a new pin set with fresh provenance.

---

## License

Trace code is open-source software licensed under the
[Apache License, Version 2.0](LICENSE). Third-party corpus texts
reconstructed via `c10m/data/` carry their own dataset-specific license
and attribution terms (see
[`c10m/data/DATA-README.md`](c10m/data/DATA-README.md)).
