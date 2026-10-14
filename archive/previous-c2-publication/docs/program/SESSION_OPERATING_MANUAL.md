# Foundation Session Operating Manual

> **Status:** Binding operating procedure for the current Foundation Program.
> It governs agent sessions and task packets. It is not a software release
> claim and does not grant authority outside a prepared packet.

## 1. Purpose and component split

The program has three separately evolving components:

1. **Trace-Lite** - local experimental retrieval reference.
2. **Trace** - governed system of record with an evented Spine.
3. **trace-bench** - moved benchmark/evaluation component.

They must become trustworthy and reproducible without collapsing into one
repository or allowing a benchmark, dirty worktree, or implementation worker
to certify itself. This manual gives every session the same safe procedure.

## 2. Five session types

| Session | Primary responsibility | First packet | May mutate product code now? |
| --- | --- | --- | --- |
| Coordinator | Pin boundaries, route packets, preserve evidence, request decisions. | F0c | No |
| Benchmark foundation | Audit evaluator/data boundary and prepare fail-closed work. | F0a, F0b | No |
| Trace-Lite foundation | Record TL state and prepare lifecycle work. | F0c contribution, L1 review | No |
| Trace foundation | Audit Cortex/temporal state and prepare decisions. | F0c contribution, T1 | No |
| Independent verifier | Freeze negative matrices and inspect packet integrity. | V0 | No |

Later implementation packets are not automatically assigned merely because
their directories exist. They require a current input manifest, clean isolated
worktree, exact allowed paths, and an independent verifier assignment.

## 3. Required reading order

Every agent reads these in order before using tools:

1. its file in [launch/](launch/README.md);
2. [README.md](README.md);
3. [prompts/GLOBAL_CONTEXT.md](prompts/GLOBAL_CONTEXT.md);
4. [00_CHARTER.md](00_CHARTER.md) and [01_INVARIANTS.md](01_INVARIANTS.md);
5. [FOUNDATION_RELEASE.md](FOUNDATION_RELEASE.md),
   [FOUNDATION_STATUS.md](FOUNDATION_STATUS.md), and
   [02_EXECUTION_DAG.md](02_EXECUTION_DAG.md);
   verify [CONTROL_PLANE_LOCK.json](CONTROL_PLANE_LOCK.json) when preparing a
   mutable packet or when another session may have edited the control plane;
6. named role prompt/contract and scope-specific evaluation, lifecycle,
   decision, and risk documents;
7. exactly one current packet, its input manifest, and approved amendments;
8. only the source paths named in that packet.

If the packet or manifest is absent, stale, contradictory, or refers to a
different repository boundary, the agent stops and produces a repair/request
record. It must not infer permission from a broad roadmap.

## 4. Authority model

### Read-only packets

Read-only packets may inspect source, Git state, documents, local manifests,
and safe test metadata. They may write only under their own inbox directory.
They may not download data, call a provider, run a certification benchmark,
modify product code, modify global policy, or clean a worktree.

### Prepared mutable packets

A mutable packet is executable only when all fields are concrete:

- source repository root and immutable base commit;
- a new isolated worktree/branch owned by the packet;
- a worktree lease and source-state record proving the base is clean;
- allowed and forbidden paths;
- data, provider, and network authority;
- acceptance commands and expected negative cases;
- a named independent verifier and fixed verification matrix;
- safe rollback/recovery statement.

The worker mutates only allowed paths in the leased worktree. It may not merge,
rebase, reset, stash, clean, amend unrelated documents, change thresholds, or
add a fallback to make a test pass.

### Decision authority

Agents may propose but never accept P-001 through P-008. The human owner
accepts, rejects, or defers them. The coordinator records outcomes and
unblocks only the exact successor nodes in the DAG.

## 5. Worktree and dirty-tree policy

Current Trace and Trace-Lite trees are working snapshots, not safe mutable
bases. Existing modifications are user-owned until explicitly classified.

Never:

- reset, checkout-overwrite, clean, stash, reformat, move, or commit existing
  dirty work;
- create a mutable task directly in the user working tree;
- cite a commit alone when evidence depends on dirty or untracked files;
- treat a non-Git benchmark directory as reproducible merely because it exists.

For each mutable packet, first record the base commit, source inventory,
dirty-state disposition, and a new worktree lease. The verifier uses a
separate clean worktree based on the implementation commit, never the
implementer's live directory.

## 6. Packet lifecycle and evidence levels

Packet state is distinct from claim strength:

| Packet lifecycle | Meaning |
| --- | --- |
| draft | Idea or broad outline; cannot be assigned. |
| scoped | Objective/non-goals exist; inputs or authority incomplete. |
| prepared | All required fields concrete; may be assigned. |
| assigned | Named worker has a lease. |
| in_progress | Worker operates in the lease. |
| handed_off | Worker submitted durable artifacts. |
| independently_verified | Separate verifier ran fixed checks. |
| accepted | Human accepted bounded result. |
| repair_requested / rejected / deferred | Closed attempt with retained evidence. |

| Evidence level | Meaning |
| --- | --- |
| planned | Not performed. |
| observed | Seen in source or local environment; not independently reproduced. |
| verified | Fixed check passed with retained commands/artifacts. |
| non-certifying | Useful development evidence below release/scale proof. |

No row becomes verified merely because a worker reports it.

## 7. Required durable artifacts

Each task directory uses this structure:

~~~text
inbox/<task-id>/
  packet.md
  input-manifest.json
  repository-state.json
  worktree-lease.json
  commands.md
  handoff.md
  verification.md
  decision.md
  packet-amendments/
  evidence/
    README.md
    checksums.json
    reports/
~~~

Read-only work needs no lease, but it still creates a current state record,
source anchors, command log (or explicit declaration that no commands ran),
and a structured handoff. Missing files are deliverables, not permission to
omit the record.

## 8. Mandatory stop conditions

Stop and hand off as **blocked** or **needs-review** if:

- component root, commit, or dependency identity differs from the packet;
- data source/license/version/checksum is incomplete;
- certification needs a mock, synthetic data, forced result, silent fallback,
  insecure TLS exception, or altered evaluator;
- a schema migration, destructive operation, or external-index alias change
  lacks rollback;
- a task needs a pending decision;
- a candidate could be visible before validation;
- source, policy, or temporal semantics would be weakened;
- an independent verifier cannot run.

Report evidence. Do not bypass the condition.

## 9. Handoff protocol

Use [templates/HANDOFF.md](templates/HANDOFF.md) and include:

1. packet ID, state, worker, and elapsed work;
2. exact repository/worktree identities;
3. source anchors and artifacts;
4. commands run and raw-result locations;
5. observed versus verified facts;
6. changed paths or explicit statement no product code/data changed;
7. claim boundary, open risks, one recommended next packet;
8. whether independent verification is now possible.

The agent chat response is a notification. The task-local handoff is durable.

## 10. Foundation exit discipline

There are four distinct readiness levels:

1. **Foundation infrastructure complete** - packets, identities, manifests,
   failure receipts, lifecycle, and verifier interfaces exist.
2. **Real-data evaluation ready** - P-001 data is admitted and staging records
   exist; no certification result is implied.
3. **Certification ready** - B1/B2/B3 and negative verification show a frozen
   real-data run could be trusted.
4. **100K ready** - P-005 and a supported real-corpus environment are
   accepted.

Foundation Complete must name its achieved level. It never means SOTA, 100K
pass, 1M pass, or downstream production adoption by itself.
