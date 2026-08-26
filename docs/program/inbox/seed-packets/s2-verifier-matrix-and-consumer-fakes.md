# Prepared Packet: S2 Verification — Fixed Matrix and Consumer Fake Design

> **State:** Prepared, unassigned
> **Role:** Independent verifier / integration reviewer
> **DAG nodes:** V1
> **Mutation authority:** Test/fixture/report design only. Do not repair TL or
> Trace implementation, and do not introduce live consumer dependencies.

## Objective

Create the fixed verification matrix and fake-client design that later
implementation packets must satisfy. The matrix covers lifecycle, evaluation
integrity, source evidence, performance/scale capture, and consumer status
semantics.

## Required inputs

- Charter, invariants, contracts, evaluation protocol, promotion rubric, risks.
- TL and Trace workstream briefs.
- Existing source/test documentation sufficient to name likely interfaces.
- Any completed evaluation/TL/Trace audits; otherwise mark dependencies pending.

## Required design areas

### Lifecycle verification

Define test cases for candidate invisibility, failed validation, active-state
retention, rollback, restart/replay, new source during build, stale graph, and
source/projection identity comparisons.

### Evaluation integrity

Define manifest assertions for absent/corrupt dataset, mock/synthetic/sample
fallback, missing judgments, forced retrieval fallback, configuration drift,
and non-certifying output behavior.

### Evidence bundle

Define contract fixtures for trusted evidence, insufficient evidence, pending,
unavailable, denied/redacted, stale, untrusted, malformed, duplicate, and
rollback responses.

### Consumer fakes

Define lightweight fakes for Reflex and Entorhinal that assert:

- no direct database/filesystem/credential access;
- versioned evidence bundle only;
- advisory System-2 behavior;
- source anchors and result status preserved;
- no automatic fact, journal, or action mutation.

## Required output

- requirement-to-test matrix;
- fixture/interface outline;
- clean-environment and Windows/temporary-directory guidance;
- verifier report template mapping each check to claim level;
- known gaps that block later implementation verification.

## Acceptance criteria

- Tests can distinguish a safe failure from a successful result.
- The matrix is independent of a specific candidate implementation.
- Consumer fakes do not become live dependencies.
- The output names which checks need real data or external infrastructure.

## Stop conditions

Stop if a test design needs to weaken policy, access private raw data, change a
human-owned evaluator, or grant live consumer/service authority.

## Handoff

Return a fixed verification packet input set for TL, Trace, and evaluation
implementation tasks.
