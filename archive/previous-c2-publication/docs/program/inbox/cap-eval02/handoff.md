# WP-CAP-EVAL02 Handoff Summary: Frozen Benchmark Datasets & Anchor Manifests

- **Node ID:** `CAP-EVAL02`
- **Work Packet:** `WP-CAP-EVAL02`
- **Role:** Evaluation Specialist (`EVAL-SPEC`)
- **Worktree Branch:** `cap-eval02-datasets`
- **Base Commit:** `8f6efe27fcbbba3a45cbe27ef3e80f2d87e07ca4` (`cap-eval01-protocol`)
- **Governing Plan:** `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`
- **Execution DAG:** `docs/program/CAP_001_EXECUTION_DAG.md` (Node `CAP-EVAL02`)
- **Directives & Annex:** `docs/program/launch/CAP_001_WAVEB_DIRECTIVES.md` (Directive D1), `docs/program/launch/CAP_001_BENCHMARK_METHODOLOGY_ANNEX.md` (§§1–5)
- **Status:** Complete & Ready for Independent Verification (`VERIF-INDEP`)

---

## 1. Scope of Mutation & Exclusive Lease Audit

Mutations strictly adhered to exclusive file lease boundaries declared in `docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md` and `docs/program/inbox/cap-eval02/dispatch.md`:
- `benchmarks/data/` (Created & Populated):
  - `benchmarks/data/scifact/queries.jsonl` (300 test queries)
  - `benchmarks/data/scifact/qrels.jsonl` (339 test judgments)
  - `benchmarks/data/nfcorpus/queries.jsonl` (323 test queries)
  - `benchmarks/data/nfcorpus/qrels.jsonl` (12,334 test judgments)
  - `benchmarks/data/fiqa/queries.jsonl` (648 test queries)
  - `benchmarks/data/fiqa/qrels.jsonl` (1,706 test judgments)
  - `benchmarks/data/musique/queries.jsonl` (500 stratified dev questions)
  - `benchmarks/data/musique/qrels.jsonl` (1,325 dev judgments)
- `benchmarks/manifests/` (Created & Populated):
  - `benchmarks/manifests/beir_musique_frozen_v1.json`: Immutable cryptographic manifest recording query counts, corpus counts, canonical archive MD5s, and SHA-256 digests for all staged files.
- `benchmarks/verify_dataset_checksums.py` (Created):
  - Standalone verification script checking cryptographic checksums, byte lengths, row counts, and schema conformance.
- `tests/v2/test_eval_datasets.py` (Created):
  - 10 unit and acceptance tests verifying manifest integrity, exact query counts, canonical BEIR archive MD5s, MuSiQue stratification, dynamic SHA-256 integrity, record schema, evidence grounding, and fail-closed tamper detection.
- `docs/program/inbox/cap-eval02/handoff.md` (Deliverable receipt).

---

## 2. Dataset Counts & Wave B Directives Reconciliation

Per **Directive D1** in `CAP_001_WAVEB_DIRECTIVES.md` and **§1.1** of `CAP_001_BENCHMARK_METHODOLOGY_ANNEX.md`:
- **SciFact:** The canonical BEIR `scifact` test split has **300 queries** (canonical archive MD5: `5f7d1de60b170fc8027bb7898e2efca1`). The provisional text "1,000 queries" is formally superseded by test/300 with zero count deviation.
- **NFCorpus:** Canonical BEIR `nfcorpus` test split has **323 queries** (canonical archive MD5: `a89dba18a62ef92f7d323ec890a0d38d`).
- **FiQA:** Canonical BEIR `fiqa` test split has **648 queries** (canonical archive MD5: `17918ed23cd04fb15047f73e6c3bd9d9`).
- **MuSiQue:** Stratified sample of **500 questions** from the `dev` split under fixed recorded seed `42`:
  - 2-hop: 259 questions
  - 3-hop: 157 questions
  - 4-hop: 84 questions
  - Total: 500 questions (resampling prohibited under Protocol §12).

---

## 3. Cryptographic Manifest Summary

From `benchmarks/manifests/beir_musique_frozen_v1.json`:

| File Path | SHA-256 Digest | Byte Length | Row Count |
|---|---|---|---|
| `benchmarks/data/scifact/queries.jsonl` | `83ea0e5f2cfc93717df3bc2f50b44a2c7c2dd49d6837eb5f02c0b565cb210437` | 158,683 | 300 |
| `benchmarks/data/scifact/qrels.jsonl` | `ce9dfd66324d20914f6b283995874c7308ca0693a743a6d967e51ca2273612f0` | 277,159 | 339 |
| `benchmarks/data/nfcorpus/queries.jsonl` | `f5cf7b32607590fe5e69bf0a3aa46220b327b3cb3d9e48f86f7347963ec7a68e` | 154,672 | 323 |
| `benchmarks/data/nfcorpus/qrels.jsonl` | `295a0a382e703358085eb5b21ea5c390500be8c616892629b3f9ff4330df30b4` | 9,997,092 | 12,334 |
| `benchmarks/data/fiqa/queries.jsonl` | `61a33d5f16a4c2bdcbb4c4d80d3645503240054a16cc985e1ae73071b83f1373` | 346,170 | 648 |
| `benchmarks/data/fiqa/qrels.jsonl` | `01cd54f708eb98bbe35c952ea1748545cac75763c971cb430a2135ef3bca3db0` | 1,415,806 | 1,706 |
| `benchmarks/data/musique/queries.jsonl` | `9bcebfa60897bb6e3260907fc2efc51c5b8b92b6794ce12a4df83c7482fce0bf` | 336,527 | 500 |
| `benchmarks/data/musique/qrels.jsonl` | `758f22336234fb23d339aad5c1fe3f5dbc0ac2ec99f3db0439485f6eb6aebe96` | 1,524,405 | 1,325 |

**Totals:** 4 datasets, 8 files, 1,771 queries, 15,704 qrels.

---

## 4. Verification Evidence

### Standalone Checksum Verification:
```bash
python3 benchmarks/verify_dataset_checksums.py
```
**Output:**
```text
Verifying dataset manifest: .../benchmarks/manifests/beir_musique_frozen_v1.json
Repository root: .../trace-eval02
[PASS] All 4 frozen dataset splits and 8 staged files matched cryptographic checksums 100%.
```

### Acceptance Test Suite:
```bash
PYTHONPATH=src:. /home/anshul/.venv/trace/bin/pytest tests/v2/test_eval_datasets.py -v
```
**Results:** `12 passed in 9.09s` (100% PASS)
1. `test_canonical_beir_archive_md5_digests`: PASSED
2. `test_cli_main_entry_point`: PASSED
3. `test_count_mismatch_reports_prerequisite_failure`: PASSED
4. `test_exact_query_counts_comply_with_wave_b_directives`: PASSED
5. `test_immutable_sha256_checksums_match_staged_files`: PASSED
6. `test_manifest_structure_and_authority`: PASSED
7. `test_musique_stratification_and_seed_stability`: PASSED
8. `test_qrels_evidence_grounding`: PASSED
9. `test_query_records_schema_and_id_uniqueness`: PASSED
10. `test_standalone_verifier_passes_on_current_repository`: PASSED
11. `test_tamper_detection_fails_closed_on_modified_file`: PASSED
12. `test_tampered_authority_fails_closed`: PASSED

---

## 5. Verification Command for Codex CLI (`VERIF-INDEP`)

```powershell
cd C:/Users/anshu/AppData/Local/trace-worktrees/trace-eval02
$env:PYTHONPATH='src;.'
pytest tests/v2/test_eval_datasets.py -v
python benchmarks/verify_dataset_checksums.py
```
