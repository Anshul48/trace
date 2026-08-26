# Session 5 - S4 D2b Dataset Normalization and Evidence Mapping

Read the shared bootstrap prompt first. Start only after B1.1 publishes the
final manifest/schema contract. Work outside Git and outside immutable raw
directories.

## Mission

Turn the admitted D2a raw sources into versioned, reversible,
evaluation-ready normalized manifests without inventing evidence.

## Direction

- Keep raw data immutable; write normalized outputs to a new versioned external
  location.
- For every admitted dataset, retain native query/document/judgment IDs,
  split/query-class data, source hashes, rights constraints, and exclusion
  reasons.
- Define reversible mappings from query to judgment to source document and,
  where supported, segment/evidence offsets.
- Define deterministic normalization and atom-mapping rules tied to a named
  ingest/chunking artifact. Do not fabricate atom IDs before such an artifact
  exists.
- Produce duplicate, malformed-record, ambiguous-evidence, and retention
  reports.
- Keep BigANN/SIFT1M isolated to the operations/vector lane.

## Suggested subagents

Use disjoint dataset workers and a separate checksum/round-trip reviewer. The
S4 owner alone reconciles schemas, rights interpretation, and final manifests.

## Exit

Provide dataset manifests accepted by B1.1, normalization hashes, reproduction
commands, round-trip evidence samples, exact external paths, and a handoff that
labels each dataset evaluation-ready, excluded, blocked, or operations-only.

## Dataset scope and directory contract

Use only the P-001 admitted portfolio already staged by D2a:

- BEIR SciFact, NFCorpus, and FiQA;
- the declared BRIGHT subsets;
- MultiHop-RAG;
- MuSiQue;
- BigANN/SIFT1M as operations/vector-only.

Do not silently add LongMemEval, HiChunk, TREC RAG, RFC corpora, or another
source. Each normalized dataset gets a new versioned directory containing a
manifest, split/query-class record, native-ID maps, judgment/evidence maps,
normalization configuration, content hashes, exclusions, and reproduction
log. Raw directories, source records, license notices, and verified checksums
remain immutable.

## Mapping requirements

For each usable query, preserve the reversible chain:

query native ID -> judgment/native evidence ID -> source document ID ->
segment/span or source offset -> deterministic content hash.

If the source does not provide a span, record the strongest supported
document-level evidence and its limitation. Do not claim atom-level evidence
until the ingest/chunking artifact that creates atoms is identified. Keep
query, document, segment, and atom IDs namespaced so collisions cannot be
mistaken for reversibility.

## Validation sequence

Run schema validation, native-ID uniqueness checks, split leakage checks,
duplicate detection, malformed-record accounting, license/retention review,
hash verification, and a round-trip sample for every dataset. Re-run
normalization from the recorded command in a clean output directory and
compare expected hashes. Ambiguous or unusable evidence becomes an explicit
excluded/blocked record with a reason.

## Handoff details

State raw, normalized, evaluation-ready, excluded, blocked, and operations-
only counts separately. Include free-space/capacity observations, source
rights, tool/runtime identity, output hashes, mapping coverage, and all
unsupported mapping classes. S4 does not certify retrieval quality.
