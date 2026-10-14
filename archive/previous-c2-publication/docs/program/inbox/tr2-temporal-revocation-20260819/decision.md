# P-004 Human Decision - Temporal Truth, Revocation, and Historical Retrieval

## Decision

- Status: accepted human decision
- Date: 2026-08-23
- Authority: program owner
- Option: A, Full Bitemporal Contract with First-Class Revocation and Historical Release Selection

## Binding contract

- Track immutable system/event time and explicit real-world valid time using half-open `[valid_from, valid_to)` intervals.
- Unknown or partial times remain explicit with precision, confidence, and provenance; the implementation must not infer missing dates.
- Represent supersession with both immutable version lineage and typed supersession events.
- Use lifecycle states `active`, `superseded`, `revoked`, `tombstoned`, and `redacted/purged`.
- Apply the most restrictive result of historical authorization, current authorization, revocation, and legal-erasure policy.
- Ordinary readers never receive revoked or redacted content, including through historical queries. Audited privileged review may expose status, provenance, and exclusion reasons, but not erased content.
- Resolve the Cortex release active at the requested `as_of_event` across every retrieval channel. If historical state is unavailable, return `historical_unavailable`; never substitute the current release.
- Late corrections append new revisions. Conflicting assertions remain explicit with a conflict state; no silent overwrite is permitted.
- Compliance erasure removes readable canonical payload and derived projections while preserving only signed non-content tombstone/audit metadata needed for policy and replay accounting.
- Every temporal evidence bundle records requested time, resolved event watermark, release ID, valid interval, lifecycle state, policy result, provenance, and exclusion reason.

## Scope and claim boundary

This decision authorizes S3 TR2 to implement the accepted temporal and
revocation contract in its isolated worktree. It does not certify PostgreSQL,
RLS, external indexes, deployment behavior, historical completeness, or release
quality; those remain verification obligations.

## Repeat-Erasure Idempotency & Fail-Closed Addendum (2026-08-25)

- Completed repeat erasure requests for an already erased source return the byte-identical signed receipt and original event offset.
- Completed repeat erasure operations perform zero database writes, zero object-store calls, zero index mutations, and append zero new canonical events.
- Erasure operations are durable and fail-closed: any lookup, authentication, timeout, deletion, or absence-verification failure returns an erasure-incomplete error—never a success receipt.
- Raw text, object keys, attachment metadata, embeddings, derived text, free-form reasons, and original content fingerprints are strictly excluded from retained receipts via an explicit non-content allow-list.

