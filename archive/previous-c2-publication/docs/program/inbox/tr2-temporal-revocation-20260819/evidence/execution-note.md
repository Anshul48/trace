# TR2 execution note

## Objective

Implement only the accepted P-004 contract from decision SHA-256
`d4ea0969d4af2e698f5838de0598e17aa40a66a6d1712c0b47496811b527333c` on the
clean TR1 head `454c5aed2200796ac9874e4fbe6e099bdb53f830`. The bounded outcome
is additive temporal/source-lifecycle behavior, historical Cortex release
selection, policy-first visibility, evidence diagnostics, focused tests, and a
durable handoff.

## Inputs

- Packet: `tr2-temporal-revocation-20260819/packet.md`
- Accepted decision: `tr2-temporal-revocation-20260819/decision.md`
- TR1 handoff: `tr1-unified-cortex-release-20260819/handoff.md`
- Fresh lease: `lease-s3-tr2-temporal-revocation-20260823`
- Base: `454c5aed2200796ac9874e4fbe6e099bdb53f830`

## Allowed mutation

Only the files named in `worktree-lease.json` may be changed in the TR2
worktree. Packet-local evidence and handoff files may be added under this
packet directory. The protected user checkout, old TR1 worktree, verifier
worktree, global control-plane documents, prior migrations, providers, data,
and network are forbidden.

## Expected outputs

1. Fresh clean exclusive TR2 worktree and lease record.
2. Forward-only/additive temporal migration with upgrade, rollback, and replay
   notes.
3. Temporal request/result/source-lifecycle behavior across all local channels.
4. Focused positive and negative temporal/policy tests.
5. Code commit, migration/test hashes, raw command results, limitations, and a
   fresh V1b temporal-verifier input manifest.

## Acceptance checks

- Valid-time half-open intervals preserve unknown/partial precision without
  inference.
- Supersession, contradiction, revocation, tombstone/redaction, erasure,
  historical authorization, and current-vs-historical visibility are explicit.
- `as_of_event` selects the release valid at the requested event across
  channels; missing history returns `historical_unavailable` and never uses
  the current release silently.
- Evidence carries requested time, resolved watermark/release, valid interval,
  lifecycle, policy result, provenance, and exclusion reason.
- Existing migrations remain unchanged; candidate/release rollback behavior is
  preserved.
- Local SQLite evidence is reported as C1/C2 only; unavailable PostgreSQL/RLS,
  external-index, deployment, and scale evidence remains explicit.

## Stop conditions

Stop and record blocked/failed evidence if the fresh worktree cannot be created
cleanly from `454c5a…`, an input identity drifts, a semantic dimension is not
covered by the accepted decision, migration rollback is unsafe, or any test
requires network/provider/mock/fallback data. Do not repair the old lease or
global control plane.

## Delegation

No subagents are delegated in this execution. If that changes, each helper
must be read-only, disjoint, and limited to temporal-contract,
migration/replay, or privacy/policy review with compact findings only.
