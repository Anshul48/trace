# Trace Scale Agent Work Contract

> Applies to scale-program work after the current Foundation prerequisite and to
> planning-only elaboration that does not inspect unfinished handoffs. It does
> not replace the active implementation-wave bootstrap or packet instructions.

## 1. Purpose

This contract lets inexpensive agents perform exhaustive work without allowing
routine elaboration to settle the hard architecture, certify its own output, or
blur durable truth with derived projections.

The execution model is:

```text
human direction
  -> lead architecture/research decision packet
  -> accepted ADR
  -> acyclic implementation packet DAG
  -> frozen artifact
  -> separate independent verifier
  -> human promotion or narrow repair packet
```

Architecture may include feedback loops; the build plan must remain a DAG with
explicit inputs and outputs.

## 2. Required reading order

For a scale packet, read only what its scope requires, beginning with:

1. `docs/SCALE_PROGRAM.md`
2. `docs/SCALE_MASTER_PLAN.md`
3. the relevant section of `docs/SCALE_HARD_PROBLEMS.md`
4. the accepted ADR(s) named by the packet
5. the repository component plan:
   - `trace-lite/docs/dev/SCALE_ROLE.md`, or
   - `trace-bench/SCALE_EVIDENCE_PLAN.md`
6. exact source/schema files named in the packet

Do not inspect unfinished handoffs, session artifacts, unrelated dirty changes,
or broad research folders unless the packet explicitly names them.

## 3. Roles and authority

| Role | May do | May not do |
| --- | --- | --- |
| Human owner | Define goals, accept/reject ADRs and thresholds, authorize promotion/deletion/major scope | Delegate final authority implicitly |
| Lead architect/researcher | Identify hard decisions, research options, design experiments, recommend ADRs, review cross-repo consistency | Self-accept ADRs or substitute paper evidence for a gate |
| Elaboration agent | Expand schemas, inventories, checklists, examples, dashboards, failure permutations, and links under accepted semantics | Choose identity, partition, consistency, deletion, gate, or promotion semantics |
| Implementation agent | Modify only declared files/worktree to implement an accepted packet; produce build evidence | Verify/promote its own artifact or relax its packet |
| Data curator | Acquire authorized real datasets, record exact bytes/hashes/licenses/transforms, produce immutable capsules | Invent expected hashes, silently substitute mirrors, expose held-out qrels |
| Independent verifier | Consume frozen artifacts and read-only protocol/data capsules; run tests/faults; sign pass/fail evidence | Patch candidate code, change thresholds, or continue after identity mismatch |
| Repair agent | Address one signed failure packet in a new implementation session | Reclassify failure as a pass or edit verifier evidence |

## 4. Work classes

### L0: routine elaboration, preferred for lower-cost models

- enumerate current APIs, schema fields, configuration, and metrics;
- create cross-reference and migration tables;
- expand a fixed fault taxonomy into concrete cases;
- populate runbook steps and dashboard/alert descriptions;
- generate JSON/YAML examples from an accepted schema;
- catalog fixtures, datasets, licenses, URLs, and checksum slots;
- add documentation links and glossary entries.

L0 work must contain no new architecture decision. When ambiguity appears, add a
clearly named open question linked to the relevant `SCALE-NNN` entry.

### L1: bounded engineering

- implement a schema or adapter defined by an accepted ADR;
- add deterministic fixtures and migrations;
- implement one projection fragment, telemetry path, or fault injector behind a
  disabled/shadow boundary;
- create reversible data-format prototypes for a named experiment.

L1 packets require exact write scope, tests, rollback, and output artifacts.

### L2: lead-only architecture/research

- workload and target definition;
- canonical IDs and ordering;
- logical partition and split/merge semantics;
- segment/manifest commit and collection semantics;
- release-root atomicity and historical read cuts;
- router budgets and accepted recall tradeoffs;
- hierarchy/graph authority and update shape;
- revocation, erasure, retention, and historical authorization;
- availability, RPO/RTO, multi-region, and cost commitments;
- gate thresholds, evidence sufficiency, and promotion recommendation;
- native-language/service-boundary decisions.

Lower-cost agents may gather evidence for L2 but do not resolve it.

## 5. Mandatory task packet

Every agent receives a bounded packet with these fields:

```yaml
packet_id: SCALE-Wx-NNN
class: L0 | L1 | L2 | verification | curation | repair
objective: one concrete outcome
repository: trace | trace-lite | trace-bench
base_identity: commit, artifact, or manifest digest
worktree: absolute isolated worktree/path when code changes are allowed
read_scope: exact files/directories
write_scope: exact files/directories
forbidden_scope: unfinished handoffs, unrelated dirty files, secrets, held-out data
prerequisites: accepted ADR and predecessor packet IDs
inputs: immutable artifact and protocol identities
invariants: truth, policy, release, evidence, and bounded-work constraints
deliverables: files plus machine-readable result/evidence artifacts
tests_or_checks: implementation checks or verifier checks, never both roles
resource_budget: time, CPU, memory, storage, model tokens/cost
stopping_conditions: ambiguity, identity mismatch, failed invariant, budget breach
rollback: how to disable/revert without destructive checkout operations
```

An agent must stop if the base identity, prerequisite ADR, or scope does not
match. It may perform read-only diagnosis and report the mismatch; it may not
repair the packet definition itself.

## 6. Implementation-session rules

1. Work in the declared isolated worktree or file scope.
2. Preserve user changes and unrelated dirty files.
3. Implement only accepted semantics; record unavoidable deviations as blockers.
4. Keep source truth writes separate from projection work and test fail-closed
   behavior.
5. Use deterministic IDs, fixtures, and clocks/seeds where the contract permits.
6. Emit the telemetry and evidence required by the packet, not only functional
   output.
7. Run implementation checks named in the packet.
8. Freeze the result as a commit, wheel/container, migration set, config/model
   fingerprint, and evidence digest as applicable.
9. Report limitations and failed checks exactly.
10. Do not call the result verified, release-ready, SOTA, or gate-passing.

Implementation sessions may not run the authoritative verification protocol.
Local unit/integration checks are implementation evidence, not independent
verification.

## 7. Verification-session rules

1. Start from a frozen candidate artifact, not an editable source checkout.
2. Verify all candidate, baseline, dataset, transform, protocol, model, hardware,
   and environment identities before execution.
3. Keep data capsules and held-out query/qrel material read-only.
4. Use narrow versioned CLI/service adapters; do not import the candidate's
   mutable source tree.
5. Run the predeclared protocol, metrics, statistics, resource schedule, and
   fault schedule without changes.
6. Write only verifier-owned telemetry, results, attestations, and failure
   packets.
7. Stop on identity mismatch, synthetic fallback, missing telemetry, metric
   impossibility, candidate leakage, or protocol drift.
8. Never patch a failure. Sign a narrow repair packet and end the session.
9. A repaired artifact requires a new verification session and attestation.
10. Human promotion remains separate from verifier pass/fail.

## 8. Result contract

Every task result should include:

```json
{
  "packet_id": "...",
  "role": "elaboration|implementation|curation|verification|repair",
  "base_identity": "...",
  "status": "completed|failed|blocked",
  "changed_files": [],
  "output_artifacts": [{"path": "...", "sha256": "..."}],
  "checks": [{"name": "...", "status": "pass|fail|not_run", "receipt": "..."}],
  "invariant_receipts": [],
  "resource_receipt": {},
  "limitations": [],
  "open_questions": [],
  "next_allowed_packet": "..."
}
```

Exact schemas will be added by an accepted architecture/evidence ADR. Until
then, agents use this shape as a documentation contract and must not fabricate
hashes or receipts.

## 9. Evidence language

Use these terms precisely:

- **implemented**: present in the named frozen artifact;
- **implementation-checked**: named local checks passed in the implementation
  session;
- **independently verified**: a separate verifier attestation passed under the
  exact protocol identity;
- **promoted**: the human owner accepted the attestation for a named claim;
- **development evidence**: useful but not release authority;
- **synthetic evidence**: valid only for the explicitly synthetic claim;
- **planned** or **proposed**: no implementation claim.

Never translate a smoke test, code inspection, generated dataset, visual report,
paper result, or `release_authority` boolean into a promoted system claim.

## 10. Data and research discipline

- Prefer real, downloadable, license-aware datasets for claims.
- Record publisher, exact release/snapshot, URL, expected bytes/hash, license,
  split, exclusions, and transformation identity.
- Acquisition workers discover and verify actual hashes; planning agents leave
  explicit placeholders rather than inventing them.
- Keep controlled-segmentation and native-ingestion lanes separate.
- Keep public development queries separate from evaluator-held release slices.
- Use primary research/official docs for technical decisions and record limits
  or contradictory evidence.
- Do not select a mechanism because it is biologically inspired, fashionable,
  or successful on a different workload. Require a fixed ablation against the
  current baseline.

## 11. Cross-repository boundaries

### Trace

Owns canonical source/event/policy/release/evidence contracts and production
scale. An implementation in Trace-Lite or Trace-Bench cannot redefine them.

### Trace-Lite

Owns embedded behavior, inspectable correctness fixtures, conformance, and
bounded mechanism ablations. It does not need to ingest the full billion or
trillion corpus.

### Trace-Bench

Owns independent identities, adapters, protocols, metrics, telemetry, fault
receipts, and attestations. It must not import mutable candidate code or infer
organization evidence.

Cross-repository changes use versioned schemas/adapters and independent packets.
Do not coordinate them through undocumented shared files or moving branch state.

## 12. Completion and escalation

An agent completes only when every declared deliverable and implementation check
is accounted for. It reports `blocked` rather than making a new L2 decision when:

- accepted semantics are missing or contradictory;
- the input identity differs from the packet;
- scope would touch unfinished handoffs or unrelated user changes;
- a destructive migration/deletion lacks explicit authority;
- evidence cannot be produced within the resource budget;
- a required external dataset/service is unavailable;
- a truth, policy, release, or bounded-work invariant fails.

The report must identify the exact missing decision or evidence and the smallest
next packet that could resolve it.

