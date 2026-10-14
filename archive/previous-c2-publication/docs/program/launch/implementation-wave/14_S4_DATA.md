# S4 — Real-Data Steward and Staging Owner

## Mission

Acquire and prepare real, license-aware evaluation data without weakening the
benchmark boundary. S4 owns raw staging, dataset records, checksums, source
layouts, and reversible evidence mappings. It does not edit benchmark code,
Trace-Lite, or Trace product code.

Raw data root:

```text
C:\Users\anshu\AppData\Local\trace-bench-data
```

Create a capacity report before downloading. The user has made large storage
and network available, but the lane must still measure free space, expected
expanded size, and working headroom and stop if the estimate is unsafe.

## D2a — raw acquisition

For every source, create a separate directory with:

```text
<dataset>/raw/
<dataset>/source-record.json
<dataset>/checksums.json
<dataset>/LICENSE-or-rights-notice.txt
<dataset>/layout-observation.json
<dataset>/acquisition-log.md
```

The source record must include official URL/repository, release/version/date,
license and terms, intended query classes, split policy, expected files,
archive hash, extracted-file hash manifest, byte counts, and tool/runtime
identity. Record redirects and HTTP metadata where available. Use strict TLS;
never retry with certificate verification disabled. A download failure is a
blocked dataset, not permission to synthesize data.

The raw directory is immutable after verification. Re-downloads create a new
versioned attempt and do not overwrite a verified source.

## Initial admitted portfolio

Stage the following official real sources:

- BEIR SciFact, NFCorpus, and FiQA for direct/semantic retrieval;
- BRIGHT coding/math material, retaining the official release while declaring
  the exact task subsets used in each run;
- MultiHop-RAG for multi-document evidence and multi-hop retrieval;
- MuSiQue for compositional multi-hop questions and supporting evidence;
- BigANN/SIFT1M only for vector/index operations and scale mechanics.

BigANN/SIFT1M cannot establish text-memory quality, source-grounded citation
quality, hierarchy faithfulness, or 100K text-memory readiness.

Do not silently add RFC corpora, LongMemEval, HiChunk, TREC RAG, or another
dataset to the admitted bundle. Record them as candidates/deferred until their
own rights, version, query/evidence mapping, and admission decision exist.

## Data integrity rules

1. Preserve native IDs and raw records.
2. Never use a synthetic record to fill a missing download or parse failure.
3. Do not flatten documents into `atom-N` without a reversible source mapping.
4. Keep query, judgment, evidence-document, segment, and atom mappings
   explicit and versioned.
5. Separate raw, normalized, and derived data; hashes identify each layer.
6. Never commit raw data, credentials, caches, or large results.
7. Record restricted/denied/license-ambiguous sources as blocked, not admitted.

## D2b — normalization and evidence mapping

D2b begins only after S1 publishes the accepted B1 manifest/schema contract.
Normalize into an external versioned directory while retaining raw sources.
Produce:

- dataset manifest accepted by B1;
- split and query-class manifest;
- stable query IDs and native-source ID map;
- judgment/evidence mapping;
- source-to-document/segment/atom mapping rules;
- content normalization and hash procedure;
- duplicate and malformed-record report;
- license/retention constraints for derived artifacts;
- reproducibility command and expected output hash.

Normalization must never fabricate evidence. If a query lacks usable evidence
or a judgment is ambiguous, mark it excluded/blocked with a reason and keep it
out of certification until the evaluation owner resolves it.

## Subagents and parallel downloads

S4 may assign one acquisition worker per disjoint dataset directory. The main
session reserves directories, verifies URLs/rights, reconciles manifests, and
owns the final admission record. A worker may not choose a different release,
license interpretation, or normalization policy.

Use a separate checksum/reproduction reviewer after each source completes. A
failed worker leaves an error receipt and no synthetic substitute.

## Required handoff

Include capacity preflight, dataset portfolio, source/license/version records,
archive/extraction hashes, layout validation, acquisition logs, blocked sources,
D2b mapping manifests, and exact external paths. State which data is raw,
normalized, evaluation-ready, or scale-only. No certification claim is made by
S4.

## Stop conditions

Stop if source identity, rights, checksum, extraction, split, evidence mapping,
TLS, free-space headroom, or B1 manifest compatibility is unresolved.
