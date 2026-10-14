# S4 D2b Verification Record

## Result

`PASS` for the fixed owner-side integrity and mapping verifier. This is not an
independent certification receipt: the named independent D2b verifier and B1.1
V1a verification are still pending.

| Check | Result | Evidence |
| --- | --- | --- |
| Raw D2a inputs | Pass; 78 checksum-listed files, 1,523,855,909 bytes, 0 failures | `C:\Users\anshu\AppData\Local\trace-bench-data\verification\d2b-20260819\owner-review-final-20260820.json` |
| Candidate checksum validation | Pass; 134 entries, 0 failures | Candidate `checksums.json` and final receipt |
| B1-compatible manifest validation | Pass for all seven manifests | Final receipt `output.datasets` |
| Mapping, native-map, split, duplicate, and malformed checks | Pass for all seven reports | Final receipt `output.datasets` |
| Round-trip samples | Pass; five samples per dataset, 31 total | Final receipt `output.datasets` |
| Deterministic replay | Pass; exit 0, no error receipt | `verification/d2b-20260819/reproduction-output-20260820` |
| Replay equality | Pass; checksum map and marker/manifests exact | `commands.md` comparison row |

## Dataset reports

| Dataset | Corpus/segment records | Source-document identities | Queries | Judgments | Cases | Status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `beir-scifact` | 5,183 | 5,183 | 1,109 | 1,258 | 1,109 | pass |
| `beir-nfcorpus` | 3,633 | 3,633 | 3,237 | 134,294 | 3,237 | pass |
| `beir-fiqa` | 57,600 | 57,600 | 6,648 | 17,110 | 6,611 | pass |
| `bright` | 928,750 | 928,750 | 752 | 4,073 | 752 | pass |
| `multihop-rag` | 609 corpus + 975 segments | 609 | 2,556 | 5,908 | 2,556 | pass |
| `musique` | 101,962 source segments | 84,459 derived/source identities | 22,355 | 53,017 | 22,355 | pass |
| `bigann` | operations-only | 0 | 0 | 0 | 0 | pass |

Mapping coverage (judgment source IDs resolved through the normalized corpus or
segment content hashes) is: SciFact `1,258/1,258`; NFCorpus
`134,294/134,294`; FiQA `17,072/17,110` with 38 explicitly excluded missing
documents; BRIGHT `4,073/4,073`; MultiHop-RAG `5,908/5,908`; and MuSiQue
`53,017/53,017`. Query coverage is complete for SciFact, NFCorpus, FiQA,
BRIGHT, and MuSiQue; MultiHop-RAG has `2,255/2,556` queries with evidence
links plus 301 explicit source-null expected-abstention cases. The 75 FiQA
exclusion records comprise 38 missing-document judgment records, 35 blocked
queries, and 2 queries with no positive judgment.

Explicit accounting retained in the manifests:

- FiQA: 38 empty-document records and 75 query/judgment exclusions.
- BRIGHT: 120 duplicate gold-document IDs; source split limitation retained.
- MultiHop-RAG: 176 duplicate evidence documents and 4,933 reused
  deterministic segment maps; repeated map rows were deduplicated while every
  judgment link was retained.
- MuSiQue: 345,077 duplicate paragraph-content reuses; source-document
  identities are derived from titles because native document IDs are absent.
- BIGANN: four operation files, including the observed 100,000-vector SIFT
  learn layout; no retrieval-quality cases are claimed.

## Replay evidence

The candidate output root is:

`C:\Users\anshu\AppData\Local\trace-bench-data\normalized\d2b-20260819`

The clean replay root is:

`C:\Users\anshu\AppData\Local\trace-bench-data\verification\d2b-20260819\reproduction-output-20260820`

Both were produced with the fixed timestamp `2026-08-20T03:00:01Z` and the
same normalizer SHA-256
`0000893590ab24bb64a62879047c0a34e1c74d13ba4806cec135b1f08523bd05`.
The parsed checksum maps each contain 134 entries and have no missing, extra,
size, or SHA-256 differences. The `checksums.json`, `run-manifest.json`,
`COMPLETED.json`, and all seven dataset `manifest.json` files are exact.

## Retained negative evidence

The failed import-path attempt, pre-map-repair candidate, and pre-source-doc
repair candidate remain under verifier scratch. The first owner receipt is
retained as `owner-review-initial-failure-20260820.json`; it recorded zero raw
failures and exposed the MuSiQue source-document and BIGANN native-map issues
that were repaired before the final pass. These files are evidence of the
repair path, not successful verification results.

## Boundary

The result establishes reproducible normalization and structural/evidence
integrity only. It does not establish retrieval quality, SOTA, atom mapping,
release readiness, provider behavior, or certification.
