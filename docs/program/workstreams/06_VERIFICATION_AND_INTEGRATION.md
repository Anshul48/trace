# Workstream 06 — Independent Verification and Consumer Integration

> **Owner:** Verifier / integration reviewer
> **Status:** Draft outline

## Intended outcome

Provide independent evidence for release claims and make downstream consumers
exercise a stable contract before they depend on live memory infrastructure.

## First work packages

1. Create a fixed verification matrix for source durability, projection
   isolation, graph bounds, fallback resistance, retrieval evidence, scale,
   rollback, and service status behavior.
2. Define clean-environment and negative-path verification procedures.
3. Design consumer fakes and conformance cases for successful, no-evidence,
   pending, unavailable, stale, denied, malformed, duplicate, and rollback
   outcomes.
4. Define shadow-mode observability and explicit non-authority behavior for
   Reflex and Entorhinal.
5. Produce gate reports that separate observed evidence from unverified claims.

## Required inputs

- fixed acceptance packet and evaluator,
- implementation handoff and release metadata,
- shared evidence-bundle/service contract,
- consumer task/query requirements.

## Expected artifacts

- verification report,
- negative test/fixture plan,
- conformance client or fixture outline,
- gap/risk report,
- recommendation: accept, repair, reject, or defer.

## Exit condition

The human owner can make an informed promotion or shadow-integration decision
without relying solely on the implementer's account.

## Stop conditions

Stop on missing evaluator, undocumented release identity, direct consumer
access to internals, or a request to turn advisory evidence into action or
canonical-journal authority.

## Verification packet sequence

### V1.1 — Fixed evaluator admission

Review evaluator version, manifest, data identity, required commands, expected
outputs, negative tests, and environment limits before accepting an
implementation handoff.

### V1.2 — Lifecycle failure matrix

For each candidate/active system, exercise:

- fail before any candidate write;
- fail after some candidate objects are written;
- fail during validation;
- fail during/after activation boundary;
- restart/replay after interruption;
- rollback to prior verified release;
- new source arriving while a build is active;
- stale/revoked/policy-changed source visibility.

### V1.3 — Retrieval and evidence matrix

Check direct, broad, multi-hop, temporal, contradiction, and abstention cases
for exact anchors, correct active-release identity, no candidate leakage,
bounded work capture, and appropriate no-evidence behavior.

### V1.4 — Consumer conformance

Build fakes before live wiring. Verify the service response contract and make
every downstream invocation advisory until a separate decision grants broader
scope.

## Gate-report format

Each gate report should contain:

1. Scope, environment, base revision, and evaluator identity.
2. Requirement-by-requirement status: verified, observed, blocked, or failed.
3. Links to logs/manifests/checksums and redacted evidence samples.
4. Failure reproduction and retained-state comparison.
5. Claim level justified and unsupported claims.
6. Residual risks, recommended repair packet, and promotion recommendation.

## Shadow-integration rules

Before a consumer begins shadow use:

- the service contract and conformance fixtures are accepted;
- requests are loopback/local and capability-scoped;
- provider credentials and raw databases remain inaccessible to the consumer;
- latency/freshness and unavailable/pending behavior are visible;
- consumer output is logged as advisory and cannot silently mutate a canonical
  journal, factual graph, or physical action plan.

## Verification workstream exit

Verification is complete for a packet only when a reviewer can answer:

- What exactly was tested?
- What data, release, and configuration were used?
- Did the required negative paths fail safely?
- What does the result prove, and what does it not prove?
- What decision is now safe for the human owner to make?
