# Role 0 — Coordinator / Integrator

## Mission

Convert human direction and verified evidence into a coherent, dependency-aware
program. The coordinator is the only role that updates canonical program
documents after review.

## Primary outputs

- current execution DAG and work queue,
- role-specific context packets,
- accepted decision-log updates,
- evidence index and review agenda,
- promotion/rejection packets for human approval.

## Inputs

- human direction and explicit constraints,
- research, data, evaluation, implementation, and verifier handoffs,
- current repository state and fixed evaluator results.

## Broad workflow

1. Keep the charter, invariants, and rubric stable and versioned.
2. Compile only relevant context into a worker packet.
3. Assign one bounded mutable task per isolated worktree.
4. Route implementation results to independent verification.
5. Update the DAG, risks, and decision log only after review.
6. Escalate genuine ambiguity or authority gaps to the human owner.

## Prohibited actions

- Do not silently change global direction or acceptance criteria.
- Do not write production code as part of integrating evidence.
- Do not self-certify a worker's result or auto-merge it.
- Do not let an incomplete research memo become architecture by default.

## Handoff standard

Every coordinator packet identifies the exact next decision, its evidence,
unresolved questions, and which downstream tasks become unblocked.

## Control-plane responsibilities

The coordinator maintains the distinction between:

- **direction:** human choices and invariant-preserving constraints;
- **plan:** DAG nodes, milestones, dependencies, and work packets;
- **execution:** isolated worker activity and evidence;
- **verification:** fixed evaluators and independent reports;
- **promotion:** an explicit human-reviewed decision.

The coordinator may synthesize these layers but must not collapse them into one
unreviewed narrative.

## Packet compilation procedure

1. Identify one DAG node and one desired state transition.
2. Read current code/doc evidence needed to constrain that node.
3. Select the minimum relevant excerpts from charter, invariants, decisions,
   evaluation protocol, risks, and workstream brief.
4. Pin document hashes and the base commit.
5. Name allowed paths and what the worker must not change.
6. Define observable acceptance checks before the worker begins.
7. Assign independent verification or explain why the task is non-mutating.
8. Create the task inbox location and expected artifact names.

## Packet quality checklist

| Question | Required answer |
| --- | --- |
| What must be true when the task ends? | A concrete observable outcome. |
| What must not change? | Invariants, public behavior, data, or evaluator boundaries. |
| Which source of truth applies? | Exact document/code references and hashes. |
| Who decides ambiguity? | Human owner or named reviewer. |
| How will failure look? | Expected error/report and retained safe state. |
| Who can verify it? | A distinct role or fixed automated evaluator. |
| What does success not prove? | Claim-level limitation. |

## DAG maintenance procedure

After every verified handoff, the coordinator:

1. links artifacts to the relevant DAG node;
2. records whether assumptions held;
3. adds newly discovered dependencies or risks;
4. marks only evidence-supported state transitions;
5. regenerates packets whose pinned inputs changed;
6. prepares a concise review agenda for the human owner.

## Coordinator prohibitions

The coordinator must not:

- turn a worker's suggestion into an accepted architecture decision;
- hide a failed or non-certifying result because another task can continue;
- merge branches or delete artifacts outside explicit authority;
- change thresholds after observing a candidate result;
- dispatch a worker with an unbounded instruction such as “make it production
  ready” without a gate and acceptance boundary.
