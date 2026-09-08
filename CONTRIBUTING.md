# Contributing to Trace

Thank you for your interest in contributing to **Trace**! Trace is an evidence-preserving, fail-closed cognitive retrieval engine with a high-performance Cortical Substrate. We hold code quality, mathematical rigor, and reliability to the highest standards.

This document outlines the principles, conventions, and procedures required for contributing code and documentation.

---

## Table of Contents

1. [Core Engineering Invariants](#core-engineering-invariants)
2. [Development Environment Setup](#development-environment-setup)
3. [Testing & Verification Standards](#testing--verification-standards)
4. [Storage and Performance Contracts](#storage-and-performance-contracts)
5. [Git Workflow & Branching](#git-workflow--branching)
6. [Code Style & Conventions](#code-style--conventions)
7. [Submitting Pull Requests](#submitting-pull-requests)
8. [Auditing & Certification](#auditing--certification)

---

## Core Engineering Invariants

Every contribution must preserve the fundamental invariants of Trace:

1. **Byte-Exact Provenance**:
   - Every span extracted from a source document must be verifiable against the normalized original text:
     $$\text{text} == \text{normalized}[\text{start}:\text{end}]$$
   - Spans must preserve cryptographic identifiers (BLAKE3 or SHA-256) and source boundaries.
   - Text duplication inside auxiliary indexes (such as SQLite FTS5) is strictly prohibited. External-content FTS5 tables (`content='atom'`, `content_rowid='id'`) must be used to ensure single-copy storage.

2. **Fail-Closed Operations**:
   - Never swallow exceptions with `except Exception: pass` or return synthetic fallback values on failure.
   - If an index, corpus, or schema is corrupt or incomplete, raise a domain error (e.g., `PreflightFailure`, `IntegrityError`) immediately.
   - Never invent information or return hallucinatory answers. When no evidence is present, return explicit `insufficient_evidence`.

3. **Additive Schema & APIs**:
   - Changes to database schemas (`store.py`, SQLite, PostgreSQL migrations) and public interfaces must be **strictly additive**.
   - Existing tables, columns, and public method behaviors must never be silently broken or rewritten.
   - New capabilities land alongside existing functionality and must pass existing test suites without regression.

4. **No Domain or Storage Mocks in Tests**:
   - Unit and integration tests must run against **real SQLite databases**, real filesystem directories, and real subprocesses.
   - Do not monkeypatch file systems, database cursors, or scoring functions.

---

## Development Environment Setup

Trace is developed for Python 3.12+ and runs natively on both **Linux** and **Windows**.

### Prerequisites

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/) (recommended) or standard `pip` and `venv`
- `git`
- SQLite 3.38+ with FTS5 and dbstat support enabled

### Quick Setup with `uv`

```bash
# Clone repository
git clone https://github.com/Anshul48/trace.git
cd trace

# Create virtual environment with Python 3.12
uv venv .venv --python 3.12
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install editable package with all development and production extras
uv pip install -e ".[test,production]"
```

### Setup with Standard `pip`

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[test,production]"
```

---

## Testing & Verification Standards

We maintain a 100% green test policy. Before submitting any change, run the test suites:

### 1. Fast Unit Tests
Run targeted unit tests for the area you are modifying:
```bash
pytest tests/test_wp5_retrieval.py -v
pytest tests/test_atomizer_aba_aliasing.py -v
pytest tests/test_two_pass_ppr.py -v
pytest tests/test_organization_toc.py -v
```

### 2. Full Regression Suite
Execute the entire test suite to ensure zero regressions:
```bash
pytest tests/ -q
```
Expected output: **All tests passing, 0 failures, 0 regressions**.

### 3. Windows Epoch RCU Concurrency Test
Verify concurrency and mmap memory safety under multi-process reader pressure:
```bash
pytest tests/test_windows_generation_leases.py -v
```
This test asserts that active readers holding memory-mapped leases do not cause `WinError 32` file locking errors during pointer swaps.

### 4. 100K Qualification & Telemetry Benchmark
For changes affecting storage, retrieval, or the Cortical Substrate, execute the live qualification runner:
```bash
python benchmarks/run_100k_qualification.py --compare-profiles --verify-receipts
```

---

## Storage and Performance Contracts

Trace adheres to strict physical storage and latency limits (Appendix A):

| Metric | Threshold | Measurement Method |
| :--- | :--- | :--- |
| **Total-Hot Storage Multiplier** | $\le 3.0\times$ | Measured physical on-disk bytes / raw admitted UTF-8 bytes |
| **Durable Spine Multiplier** | $\le 1.6\times$ | Cold SQLite DB data file + WAL + SHM / raw admitted UTF-8 bytes |
| **Tier 1 Lexical Latency (p95)** | $\le 5\text{ ms}$ | Measured under active query load |
| **Tier 2 Hierarchical Beam (p95)**| $\le 35\text{ ms}$ | Measured across 1,000 query evaluation set |
| **Tier 3 Flat Hybrid Latency (p95)**| $\le 25\text{ ms}$ | Dense kNN + Lexical RRF |
| **End-to-End Retrieval (p95)** | $\le 65\text{ ms}$ | Full 3-tier cascade with grounding verification |
| **Negation Inversion Rejection** | $100\%$ | Grounding polarity verifier rejects contradicted claims |

---

## Git Workflow & Branching

1. **Base Branch**: All pull requests target `main`.
2. **Feature Branches**: Cut topic branches using descriptive names:
   - `feat/cortical-beam-expansion`
   - `fix/rcu-lease-cleanup`
   - `perf/fts5-token-cache`
   - `docs/clarify-quickstart`
3. **Commit Messages**: Follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat(retrieval): implement dynamic beam pruning in tier 2`
   - `fix(store): ensure atomic file release on lease expiry`
   - `perf(cortex): vectorize lateral rectification inner loop`
   - `docs(readme): add storage model architecture diagram`

---

## Code Style & Conventions

- **Formatter & Linter**: We use [`ruff`](https://beta.astral.sh/ruff/) with a 100-character line limit.
  ```bash
  ruff check src/ tests/
  ruff format --check src/ tests/
  ```
- **Type Annotations**: All public APIs, classes, and helper functions must include standard Python 3.12+ type hints.
- **Documentation**: Provide clear docstrings explaining rationale, edge cases, and computational complexity for graph/retrieval algorithms.
- **Line Endings**: Preserve existing CRLF / LF line endings in files where applicable.

---

## Submitting Pull Requests

When opening a Pull Request:
1. Complete the [Pull Request Template](.github/pull_request_template.md).
2. Attach output from `pytest tests/ -q`.
3. Provide diff verification showing:
   - Zero synthetic score derivations or test mocking.
   - Zero modifications to frozen Appendix A constants unless accompanied by an explicit decision log.
   - 100% byte-exact provenance compliance.
4. Ensure CI checks pass on both Linux and Windows runners.

---

## Auditing & Certification

Trace releases undergo blind auditor scrutiny (Paste E validation protocol). Pull requests are evaluated for:
- Absence of domain/storage mocks.
- Absolute avoidance of silent fallbacks or swallowed errors.
- Strict adherence to physical on-disk storage gates ($\le 3.0\times$).
- Additive nature of store/schema evolutions.

Thank you for helping build a rigorous, evidence-grounded future with Trace!
