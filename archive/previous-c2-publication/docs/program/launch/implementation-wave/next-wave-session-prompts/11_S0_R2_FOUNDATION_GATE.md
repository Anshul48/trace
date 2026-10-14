# Session 11 - S0 R2 Foundation Gate Review

Read the shared bootstrap prompt first. You are a control-plane reviewer, not
an implementer, verifier, or promoter. Do not alter product, benchmark, or raw
data artifacts.

## Mission

Reconcile the B3 dossier and independent verifier handoffs into an explicit
Foundation Gate decision record.

## Direction

- Confirm every referenced commit, manifest, receipt, decision, and artifact
  is present and internally consistent.
- Confirm V1a and every applicable V1b sub-gate are independent of their
  implementation sessions.
- Check that P-002, P-004, and P-005 were actually human-recorded decisions.
- For each of the five Foundation promises, label passed, blocked, or not
  attempted with evidence and limitation links.
- Preserve a strict boundary: an accepted Foundation Gate authorizes a real
  100K experiment, not a production or 1M claim.

## Suggested subagents

Use two read-only reviewers: one evidence-chain auditor and one DAG/claim-
boundary auditor. They must not rewrite handoffs or decide the gate.

## Exit

Update only control-plane records and write an R2 handoff. If any requirement
is missing, leave the gate blocked and name the narrow next repair or evidence
packet.

## Gate review procedure

Start by hashing the dossier, B3 manifest, verifier handoffs, decision log,
status board, and all referenced input manifests. Resolve every reference to
an exact commit, dataset/version, configuration, output hash, or verifier
receipt. A missing or contradictory reference is a gate blocker.

Review the five promises separately. Confirm source truth and evidence
provenance, candidate isolation and rollback, real-data retrieval metrics and
denominators, bounded resource observations, and the explicit 100K readiness
protocol. Confirm that BigANN/vector operations were not presented as
text-memory quality and that no internal fixture was upgraded to public
certification evidence.

Check the independence boundary: implementation tests may support a claim, but
V1a/V1b must provide independent evidence for their applicable surfaces. Check
that verifier failures were not repaired in-place and that repaired identities
were re-verified.

## Required decision record

Create an R2 gate-review packet containing an evidence index, decision matrix,
unresolved risks, rejected/blocked claims, safe default, and coordinator
decision. Use only passed, blocked, or not attempted. Do not use partial as a
synonym for production readiness. The decision must say whether S7 real 100K
is authorized and list its exact corpus/protocol prerequisites.

## Stop conditions

Block the gate if any required verifier handoff is absent, any human decision
is only a recommendation, any source or dataset identity is mutable, any
fallback path was used, any cleanup failed, or any claim depends on an
unavailable environment. Do not dispatch S7 from an ambiguous or self-approved
gate.
