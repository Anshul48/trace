## Description

<!-- Brief summary of changes and operational rationale -->

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Performance optimization (improved latency or storage efficiency)
- [ ] Documentation update
- [ ] Benchmark / qualification verification

## Invariant Compliance Checklist

- [ ] **Byte-Exact Provenance**: Text spans match normalized source offsets (`text == normalized[start:end]`).
- [ ] **Single-Copy Storage**: External-content FTS5 tables (`content='atom'`) used; no duplicate text in auxiliary indexes.
- [ ] **Fail-Closed Guarantees**: No swallowed exceptions (`except: pass`), no synthetic score outcomes or hardcoded fallback dictionaries.
- [ ] **Additive Evolution**: Changes to `store.py`, `organization.py`, or schemas are strictly additive and backward-compatible.
- [ ] **Zero Domain/Storage Mocks**: Unit tests execute against real temporary SQLite databases and real subprocesses.
- [ ] **Storage Gate Respected**: Physical on-disk total-hot multiplier $\le 3.0\times$ admitted raw text bytes; durable Spine $\le 1.6\times$.

## Verification & Test Results

```text
<!-- Paste outputs of `pytest tests/ -q` or specific packet test runner here -->
```

- Packet-specific test results:
- Full test suite regression count vs baseline:
- Physical on-disk storage multiplier measured:
