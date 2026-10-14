# V1 / V1a — Independent Integrity Verifier Foundation

> **Role:** Independent verifier
> **State:** Queued for execution after B1; planning may begin read-only
> **DAG node:** V1 / V1a

## Objective

Create and later execute an independent negative integrity matrix for the
benchmark/release boundary. Verify that prohibited fallback and hidden
substitution paths cannot produce certifying-looking success.

## Broad scope

- inspect F0a and B1 handoffs against fixed invariant/evaluation rules;
- define negative cases for missing data, checksum mismatch, mock provider,
  synthetic input, forced retrieval, failed indexing/query, TLS failure, and
  missing judgment/evidence mappings;
- define expected exit/error-receipt behavior and retained evidence;
- report failures without repairing the implementation.

## Non-goals

- no implementation repair;
- no threshold, query-pack, or dataset-policy change;
- no certification claim or real-data staging;
- no consumer production integration.

## Required inputs before execution

- F0a current audit;
- B1 implementation handoff, fixed manifest, and exact test command(s);
- isolated verifier worktree/environment;
- immutable expected failure matrix.

## Acceptance outline

- every prohibited condition fails rather than silently substitutes;
- receipts identify the blocked stage without exposing secrets;
- result artifacts clearly state non-certifying status;
- the verifier can reproduce outcomes independently of the implementer.

## Handoff

## Detailed verifier execution contract

### Packet split

- V0 is read-only plan/packet review.
- V1a executes evaluator integrity after B1 in separate verifier worktree.
- V1b executes TL/Trace lifecycle/temporal conformance after L1/TL2 and
  TR1/TR2. V1a pass does not imply V1b.

### V1a evidence

For every negative case retain verifier source identity/clean worktree, fixed
command/config, input/evaluation digest, expected/actual receipt,
certification false, proof no substitute result written, safe diagnostic,
correlation ID.

Cases: unpinned source, mock, synthetic, flat fallback, missing
data/license/checksum/evidence mapping, indexing/query error, empty result,
metric after failure, TLS failure, result output failure.

### V1b evidence

For every fault retain predecessor/candidate/successor IDs, source/projection
hashes, normal query observation, restart state, evidence-bundle sample:

- pre-write/partial-write crash;
- affinity/prior candidate leak;
- validation/policy/external activation failure;
- source arrival/retry;
- cross-workspace access;
- pointer rollback;
- as_of_event release selection;
- valid-time/revocation after TR2.

### Infrastructure boundary

SQLite/in-memory/fake evidence verifies exact contract only. It cannot certify
PostgreSQL/RLS, real crash durability, external-index alias atomicity, provider
behavior, or transport. Mark unsupported or provision disposable environment
under later packet.

Return `accept for Foundation evidence`, `repair`, `defer`, or `reject`; never
merge or repair the candidate directly.
