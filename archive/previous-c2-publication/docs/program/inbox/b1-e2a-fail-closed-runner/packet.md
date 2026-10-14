# B1 / E2a — Fail-Closed Benchmark Runner Foundation

> **Role:** Evaluation engineer
> **State:** Queued — requires accepted F0a re-anchor
> **DAG node:** B1 / E2a

## Objective

Implement a clearly separated certification-capable runner mode that fails with
an actionable receipt when a required source, data record, provider, judgment,
or retrieval stage is unavailable. It must never substitute mock, synthetic,
forced, insecure, or hidden fallback behavior.

## Required inputs before preparation

- current external benchmark-suite root and base commit;
- F0a source anchors and fallback inventory;
- exact allowed code/test paths;
- fixed error-receipt and manifest expectations;
- verifier assignment for V1.

## Broad scope

- explicit mode boundaries: unit/mock, regression, exploratory, certification;
- hard failure for prohibited fallback conditions;
- actionable redacted error receipts and preserved run metadata;
- clear treatment of empty retrieval, abstention, exclusions, and failed query
  stages;
- no changes to numerical thresholds or data admission policy.

## Non-goals

- no dataset download or certification run;
- no new retrieval algorithm;
- no modification of TL or Trace runtime code unless a later cross-repository
  packet explicitly authorizes it.

## Acceptance outline

- fixed negative cases fail closed and emit a receipt;
- a mock path is explicit and cannot be selected by certification mode;
- insecure TLS/fallback/retry behavior is absent from certification flow;
- V1 can independently reproduce the assertions.

## Stop

## Detailed prepared-packet requirements

This remains scoped, not prepared, until coordinator completes it after F0a,
P-007, and P-008.

### Preconditions

1. trace-bench has accepted immutable source identity/dependency pins.
2. One certification runner and adapter import boundary is accepted.
3. Clean benchmark worktree lease exists.
4. F0a anchors are current/complete.
5. V1a matrix is frozen and verifier has separate clean worktree plan.
6. Evaluation manifest/error-receipt schemas are versioned/pinned.
7. No data download, threshold, or P-001 work is implied.

### Certification mode semantics

Certification mode must reject:

- mock provider/default injection;
- synthetic data creation/substitution;
- forced-flat or hidden query/retrieval fallback;
- index, organize, query, metric, or result-write error;
- empty retrieval incorrectly turned into abstention success;
- expected abstention incorrectly awarded perfect retrieval metrics;
- insecure TLS retry;
- missing source identity, data record, checksum, license, judgment, evidence
  mapping, component pin, or provider identity.

It emits safe error receipt with correlation ID, stage, reason code, and
non-certifying status.

Unit/regression/exploratory fakes can remain only when explicitly named,
impossible to select from certification mode, and marked non-certifying.

### Required implementation outputs

- explicit mode/type/preflight;
- validated evaluation manifest and fail-closed receipt;
- no-fallback runner;
- query-level status/error representation;
- fixtures triggering every forbidden condition;
- legacy TL benchmark compatibility note;
- B1 handoff with source identity/changed paths.

### V1a acceptance

V1a proves every prohibited condition yields expected blocked receipt and no
certifying score/result. It proves unit/regression mock cannot be selected by
certification configuration.

### Explicit non-goals

B1 does not download data, run certification, choose P-005, alter retrieval,
or improve scores. Requirement to change data/metrics/source policy stops it.

Do not start until F0a provides current paths and the coordinator fills base,
allowed paths, tests, and exact verifier command(s).
