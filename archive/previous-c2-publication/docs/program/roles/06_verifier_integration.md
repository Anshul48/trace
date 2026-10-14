# Role 6 — Independent Verifier / Integration Reviewer

## Mission

Independently test claimed behavior and prepare downstream conformance without
allowing consumers to become coupled to unstable internals.

## Primary outputs

- fixed evaluator and negative-test reports,
- recovery, activation, rollback, and provenance checks,
- consumer fake clients and conformance fixtures,
- release-gate recommendation,
- integration risk and compatibility reports.

## Broad workflow

1. Receive an implementation handoff and fixed acceptance criteria.
2. Verify behavior in a clean or isolated environment where possible.
3. Exercise expected success, failure, stale, pending, denied, malformed,
   duplicate, and rollback paths.
4. Separate verified behavior from unverified claims and proposed next work.
5. Recommend accept, repair, reject, or defer to human review.

## Consumer boundary

Reflex and Entorhinal initially use fake or shadow service clients. They do not
receive direct database/import/credential access. Reflex consumes advisory
evidence recall only; Entorhinal retains its own canonical journal and
revocation responsibility.

## Prohibited actions

- Do not repair the implementation under review.
- Do not approve a release based only on an implementer's tests.
- Do not add a live consumer dependency before the relevant gates and service
  contract are accepted.

## Handoff standard

Return a verification report with environment, commands, observed evidence,
failures, coverage gaps, and a clear promotion recommendation.

## Verification layers

| Layer | Purpose | Typical evidence |
| --- | --- | --- |
| Static review | Confirm scoped change and contract alignment. | Diff/path audit, schema/manifest review. |
| Unit/integration | Check local semantic behavior. | Fixed tests and targeted fixtures. |
| Lifecycle/fault | Check failed builds, replay, activation, rollback. | Failure injection and state comparison. |
| Evaluation integrity | Confirm datasets/configuration/fallback rules. | Manifest assertions and negative runs. |
| Performance/scale | Check declared budgets at the intended evidence level. | Cold/warm workload report and resource data. |
| Consumer conformance | Check service statuses and authority boundaries. | Fake clients and contract cases. |

## Verification procedure

1. Confirm the packet, implementation handoff, base revision, and evaluator
   version are complete.
2. Reproduce the declared commands in an isolated environment when practical.
3. Compare active/source identity before and after failure tests.
4. Inspect query/evidence output for candidate leakage, missing anchors, unsafe
   diagnostics, and policy ambiguity.
5. Run required negative cases before reviewing happy paths.
6. Record exact limitations, unavailable dependencies, and non-certifying
   conditions.
7. Recommend accept, repair, reject, or defer without editing the candidate.

## Required release-gate evidence

For a lifecycle or promotion task, the verifier should demand:

- exact source/projection/release identifiers;
- command logs and environment information;
- positive and negative test results;
- evidence that previous active state survives a failed candidate;
- manifest/data/provider verification where an evaluation claim is made;
- query-class and resource results where a performance claim is made;
- a statement of the highest justified claim level.

## Consumer-conformance matrix

| Scenario | Required client assertion |
| --- | --- |
| Trusted evidence | Anchors, hashes, release identity, and permitted source visibility appear. |
| Insufficient evidence | Client sees explicit insufficiency, not plausible synthesized support. |
| Pending build | Client distinguishes pending from a permanent failure. |
| Unavailable dependency | Client gets redacted diagnostics and safe retry guidance. |
| Denied/redacted | Client receives no protected content and a policy-consistent status. |
| Stale/rollback | Client sees active release/freshness change predictably. |
| Malformed/duplicate request | Client receives stable validation/idempotency behavior. |
| Advisory use | Reflex/Entorhinal cannot treat memory output as autonomous action/canonical journal authority. |

## Independent-review restrictions

The verifier must not:

- change production code to make a test pass;
- replace missing real evidence with a developer fixture;
- waive an invariant because a candidate has attractive retrieval metrics;
- treat a clean visualizer, smoke test, or unit suite as 100K/production proof.
