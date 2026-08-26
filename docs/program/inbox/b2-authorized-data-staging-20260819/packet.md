# B2 - Authorized Real-Data Staging and Evidence Mapping

> **Role:** Data steward
>
> **DAG node:** B2 / D2
>
> **State:** Blocked pending accepted P-001 and source-specific download
> authority. No download occurs under the current packet draft.

## 1. Objective

Acquire and stage only P-001-admitted real-world datasets using reproducible,
license-aware, checksum-verified procedures. Produce immutable local records
that let a verifier reconstruct the exact corpus/query/judgment/evidence
inputs without committing raw data to Git.

## 2. Preconditions

1. Every source has an accepted DATA_ADMISSION_RECORD.
2. Human P-001 names dataset/version/role and allowed local use.
3. Packet names destination, retention policy, source URL/distribution, and
   allowed network operation.
4. trace-bench identity/integration policy is accepted if data is for
   certification.
5. Staging root is external to Git, capacity/access reviewed.
6. Expected source, query, judgment, transform record exists.

## 3. Required staging sequence

1. Record manifest and expected layout before fetch.
2. Fetch named official source through normal TLS validation.
3. Record retrieval time, source headers/version/signature where available,
   exact download command, raw SHA-256.
4. Verify expected layout, supplied signature/checksum, license receipt.
5. Transform using pinned code/config, emitting transform manifest.
6. Generate source artifact, atom, query, judgment, evidence mapping records
   with stable IDs.
7. Validate source coverage, duplicate/missing IDs, counts, segment-anchor/hash.
8. Store raw data/results outside Git; Git stores manifests/checksums/reports.

## 4. Fail-closed rules

Stop with data prerequisite failure if source unavailable, TLS fails,
license/version differs, checksum/layout differs, transform fails, evidence
mapping incomplete, or path would use synthetic/sample substitution.

No partial/stale cache becomes admitted data automatically. Never weaken
checksums/TLS to make acquisition succeed.

## 5. Required outputs

- per-dataset frozen staging manifest;
- raw/query/judgment/transform/evidence SHA-256 records;
- layout/count/source coverage report;
- segmentation and atom/source mapping report;
- retention/location/access record;
- data failure receipts where applicable;
- independent sample verification plan.

## 6. Acceptance

B2 produces staged real inputs, not a benchmark score. It passes only when a
verifier validates sample against source records and all inputs reconstruct from
manifests.
