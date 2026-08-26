# V1a - Independent Fail-Closed Runner Verification

> **Role:** Independent verifier
>
> **DAG node:** V1 / V1a
>
> **State:** Blocked pending B1 handoff, frozen negative matrix, and separate
> clean verifier worktree.

## 1. Objective

Independently verify B1 certification runner rejects each prohibited
fallback/integrity violation and leaves no certifying-looking score/result.

## 2. Independence requirements

- verifier checkout clean/separate from implementation commit;
- evaluator source P-007-compliant;
- runner boundary P-008-compliant;
- verifier-owned or packet-fixed fixtures/configuration;
- no implementer repair during evidence collection;
- environment/command outputs retained.

## 3. Mandatory cases

| Case | Required result |
| --- | --- |
| Unversioned/unpinned evaluator | blocked source identity receipt |
| Mock provider/default | blocked mock receipt |
| Synthetic data/fallback | blocked synthetic receipt |
| Forced/flat fallback | blocked fallback receipt |
| Missing data/license/checksum | blocked prerequisite receipt |
| Missing query/evidence mapping | blocked integrity receipt |
| Index/organize/query exception | blocked stage-error receipt |
| Empty retrieval | explicit outcome, not automatic abstention win |
| Expected abstention | dedicated result, no perfect retrieval score |
| TLS failure | blocked transport receipt; no insecure retry |
| Metric/output failure | blocked receipt/no partial aggregate |

## 4. Evidence requirements

For each retain command, config/manifest digest, receipt, output inventory,
correlation ID, source/worktree identity, proof certification eligibility
false. Preserve unexpected success as failure evidence; request repair, do not
patch implementation.

## 5. Acceptance

Accept only exact tested properties. Mark data/scoring/performance claims
outside this matrix unverified. V1a pass alone is not B3, lifecycle, scale,
or consumer integration pass.
