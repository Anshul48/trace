# B3 - Frozen Certification Manifest and Run Readiness

> **Role:** Evaluation engineer; independent verifier
>
> **DAG node:** B3 / E2b
>
> **State:** Blocked pending B1, B2, accepted P-005, and clean source
> identities. It does not itself claim a passing score.

## 1. Objective

Freeze complete certifying evaluation definition so a later run is reproducible
and fail-closed or explicitly blocked. The manifest records input identities,
policies, system configurations, environment, metrics, and output retention.

## 2. Required frozen fields

Use EVALUATION_MANIFEST_TEMPLATE.yaml and include:

- trace-bench canonical identity from P-007;
- certification runner/integration from P-008;
- TL/Trace adapter code/config/model/embedding fingerprints;
- P-001 admitted B2 staging records and raw/transform/query/judgment/evidence
  digests;
- frozen segmentation/evidence mapping;
- query classes, inclusion/exclusion policy, metric definitions;
- P-005 thresholds/significance;
- retrieval/hierarchy/graph policy hashes;
- provider identity and secure transport;
- hardware/runtime/database/index environment;
- seed/warmup/concurrency/cold-warm policy;
- receipt schema and prohibited-fallback preflight;
- output/retention paths and result manifest hashing.

## 3. Required preflight behavior

Runner refuses to begin if any field is absent/mismatched or source, data,
provider, policy, transport, evidence mapping unavailable. It writes
non-certifying receipt, never partial score.

## 4. Readiness review

Verifier checks:

- artifacts hash to frozen manifest;
- imports resolve expected identities;
- mode is certification, not mock/regression/exploratory;
- preflight rejects prohibited fixtures;
- metrics distinguish retrieval, abstention, exclusion, error;
- no prior result reused under new manifest;
- output directory new/versioned to avoid blended results.

## 5. Acceptance

B3 may say certification ready only at Gate Dossier L3 if V1a and every
manifest condition pass. It does not run external SOTA comparison, set
thresholds, or certify 100K.
