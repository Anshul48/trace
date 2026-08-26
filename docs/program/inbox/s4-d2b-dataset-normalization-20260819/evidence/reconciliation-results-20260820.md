# S4 D2b reconciliation results — 2026-08-20

## Result

`PASS` for this bounded current-session reconciliation. The checker is
independent of the packet's `verify_d2b.py` owner utility, but it is not the
named coordinator/independent-verifier receipt; the packet therefore remains
`needs_review` for independent acceptance.

## Exact commands and environment

Environment: Windows PowerShell, CPython `3.12.0`, PyArrow `24.0.0`, network
and provider calls disabled by the lease.

1. Syntax check:

   `python -c "import ast, pathlib; ast.parse(pathlib.Path(r'docs\\program\\inbox\\s4-d2b-dataset-normalization-20260819\\evidence\\reconcile_d2b.py').read_text(encoding='utf-8')); print('syntax: pass')"`

   Result: pass.

2. Fresh deterministic replay, into the new lease-authorized scratch root:

   `python docs/program/inbox/s4-d2b-dataset-normalization-20260819/evidence/normalize_d2b.py --raw-root C:\\Users\\anshu\\AppData\\Local\\trace-bench-data --out C:\\Users\\anshu\\AppData\\Local\\trace-bench-data\\verification\\d2b-20260819\\independent-replay-20260820 --portfolio docs/program/inbox/b2-authorized-data-staging-20260819/evidence/portfolio-staging-manifest.json --created-at-utc 2026-08-20T03:00:01Z`

   Result: exit `0`, `completed_candidate`, 156.3 seconds, no error receipt.

3. Independent reconciliation:

   `python docs/program/inbox/s4-d2b-dataset-normalization-20260819/evidence/reconcile_d2b.py --raw-root C:\\Users\\anshu\\AppData\\Local\\trace-bench-data --candidate C:\\Users\\anshu\\AppData\\Local\\trace-bench-data\\normalized\\d2b-20260819 --replay C:\\Users\\anshu\\AppData\\Local\\trace-bench-data\\verification\\d2b-20260819\\independent-replay-20260820 --portfolio docs/program/inbox/b2-authorized-data-staging-20260819/evidence/portfolio-staging-manifest.json`

   Result: exit `0`, `error_count: 0`, 80.4 seconds.

The first replay attempt was denied by the sandbox with `WinError 5` while
creating the already-authorized external scratch directory. It did not create
the target or touch raw/candidate data. The same offline command succeeded
after the required approved external-write boundary. An initial inline
checker version was also retained as a non-acceptance attempt after it
incorrectly treated explicit FiQA blocked rows and MuSiQue corpus-backed
segments as failures; the persisted checker contains the corrected, explicit
rules and passed.

## Fresh identity and hash evidence

| Item | Path | Hash/count |
| --- | --- | --- |
| Raw inventory | `C:\Users\anshu\AppData\Local\trace-bench-data` | 85 files / 1,523,873,466 bytes |
| Raw checksum-listed inputs rehashed | all seven `raw/*/checksums.json` inventories | 78 files / 1,523,855,909 bytes / 0 failures |
| Candidate checksums | `C:\Users\anshu\AppData\Local\trace-bench-data\normalized\d2b-20260819\checksums.json` | SHA-256 `4c150a7827836c0ec41e02c302720d84ab0e83e859bf24c884a7bafc52907f5d`; 134 entries |
| Candidate run manifest | `...\\normalized\\d2b-20260819\\run-manifest.json` | SHA-256 `d7401a9624bef59b47c7985248215406175477c7f7b9c4a16970cc1b52a3fd39` |
| Candidate completion marker | `...\\normalized\\d2b-20260819\\COMPLETED.json` | SHA-256 `c2d2081ce8bc475a93616975bd2b38281eb746ad9d3a9ab8e41020491d528998` |
| Fresh replay checksums | `C:\Users\anshu\AppData\Local\trace-bench-data\verification\d2b-20260819\independent-replay-20260820\checksums.json` | SHA-256 `4c150a7827836c0ec41e02c302720d84ab0e83e859bf24c884a7bafc52907f5d`; 134 entries |
| Fresh replay run manifest | `...\\independent-replay-20260820\\run-manifest.json` | SHA-256 `d7401a9624bef59b47c7985248215406175477c7f7b9c4a16970cc1b52a3fd39` |
| Fresh replay completion marker | `...\\independent-replay-20260820\\COMPLETED.json` | SHA-256 `c2d2081ce8bc475a93616975bd2b38281eb746ad9d3a9ab8e41020491d528998` |
| Candidate/replay tree | both roots, checksum file excluded | 134 files / 4,775,895,582 bytes each; exact file inventory and hashes |

The candidate and fresh replay checksum maps, `run-manifest.json`, and
`COMPLETED.json` are byte-identical. Both markers state `completed_candidate`,
`raw_mutated: false`, `network_used: false`, `provider_used: false`, and
`atom_ids_created: false`. Post-replay free space was `362,032,492,544`
bytes.

## Dataset status and mapping coverage

| Dataset | Manifest status | Queries / resolved-evidence queries | Judgments / resolved | Cases | Explicit exclusions | Source docs | Round trips |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BEIR SciFact | `evaluation_ready_document_level` | 1,109 / 1,109 | 1,258 / 1,258 | 1,109 | 0 | 5,183 | 5 |
| BEIR NFCorpus | `evaluation_ready_document_level` | 3,237 / 3,237 | 134,294 / 134,294 | 3,237 | 0 | 3,633 | 5 |
| BEIR FiQA | `evaluation_ready_document_level` | 6,648 / 6,646 | 17,110 / 17,072 | 6,611 | 75 | 57,600 | 5 |
| BRIGHT | `evaluation_ready_document_level_with_source_split_limitation` | 752 / 752 | 4,073 / 4,073 | 752 | 0 | 928,750 | 5 |
| MultiHop-RAG | `evaluation_ready_document_or_span_level_with_derived_source_keys` | 2,556 / 2,255 | 5,908 / 5,908 | 2,556 (301 expected abstentions) | 0 | 609 + 975 segments | 5 |
| MuSiQue | `evaluation_ready_source_segment_level_atom_mapping_deferred` | 22,355 / 22,355 | 53,017 / 53,017 | 22,355 | 0 | 84,459 identities + 101,962 corpus segments | 5 |
| BigANN/SIFT1M | `operations_only` | 0 / 0 | 0 / 0 | 0 | 1 operations-only exclusion | 0 | 1 vector round trip |

The six text datasets provide 31 round-trip samples total. FiQA's 38
unresolved judgments are retained with `unresolved` /
`blocked_missing_source_document` status and matching exclusion records; they
are not treated as successful evidence. MultiHop-RAG's 301 source-null cases
are explicit expected abstentions. Native IDs, derived-source origins,
namespace-stable internal IDs, split/query-class records, source hashes, and
offset/segment links passed the independent checks. No atom IDs are present;
atom mapping remains deferred until a named ingest/chunking artifact exists.

## Claim boundary

This receipt proves current-session structural, provenance, deterministic
replay, raw-integrity, and reversible mapping checks at C3 evidence strength.
It does not certify retrieval quality, SOTA, provider behavior, atom-level
identity, release activation, P-005 thresholds, or independent V1a/D2b gate
acceptance.
