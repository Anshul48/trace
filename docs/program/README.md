# Trace / Trace-Lite Program Control Plane

> **Status:** Draft planning scaffold. These documents define work, evidence,
> and handoffs; they do not establish that a feature, benchmark, or operational
> guarantee already exists.

## Purpose

This directory is the canonical control plane for the Trace and Trace-Lite
program. It turns the high-level architecture direction into bounded work
packets, independently verifiable evidence, and reviewed promotion decisions.

Trace-Lite remains the local research and reference environment. Trace remains
the governed system of record. The program transfers measured mechanisms
between them; it does not merge their runtimes or storage assumptions.

## Execution priority

The program is **foundation-first**. First make the existing Trace-Lite,
Trace, and separately versioned benchmark component trustworthy, reproducible,
and complete for the defined foundation release. Then use that reliable
baseline for broad architecture research, deep investigation, and bounded
mechanism experiments.

Construction may proceed in parallel across independent lanes. Proof, release,
promotion, scale, and consumer adoption remain sequential gates.

## Canonical documents

| File | Role |
| --- | --- |
| [00_CHARTER.md](00_CHARTER.md) | Goal, authority boundaries, scope, and non-goals. |
| [01_INVARIANTS.md](01_INVARIANTS.md) | Constraints no task may weaken without an explicit decision. |
| [02_EXECUTION_DAG.md](02_EXECUTION_DAG.md) | Dependency-ordered stages and gates. |
| [FOUNDATION_RELEASE.md](FOUNDATION_RELEASE.md) | Finite baseline-release scope and Foundation Complete gate. |
| [FOUNDATION_STATUS.md](FOUNDATION_STATUS.md) | Current starter-packet state and decision blockers. |
| [SCALE_CERTIFICATION_RECOVERY_PLAN.md](SCALE_CERTIFICATION_RECOVERY_PLAN.md) | Draft, planning-only route to requalify 100K before a separately verified 1M pilot. |
| [SCALE_100K_TO_1M_EXECUTION_PLAN.md](SCALE_100K_TO_1M_EXECUTION_PLAN.md) | Detailed execution amendment from the failed R2.1 measurement state through truthful Gate C2, Gate D, and Gate F2. |
| [03_SHARED_CONTRACTS.md](03_SHARED_CONTRACTS.md) | Evidence, release, task, and handoff contracts. |
| [04_EVALUATION_PROTOCOL.md](04_EVALUATION_PROTOCOL.md) | Real-data evaluation and scale proof boundary. |
| [05_PROMOTION_RUBRIC.md](05_PROMOTION_RUBRIC.md) | Criteria for promoting an experimental mechanism. |
| [06_DECISION_LOG.md](06_DECISION_LOG.md) | Human-reviewed program decisions. |
| [07_RISK_REGISTER.md](07_RISK_REGISTER.md) | Material risks, owners, and mitigation direction. |

## Worker assets

| Location | Role |
| --- | --- |
| [roles/](roles/README.md) | Seven logical role contracts and authority boundaries. |
| [workstreams/](workstreams/README.md) | Broad-stroke briefs used to create task packets. |
| [templates/](templates/WORK_PACKET.md) | Work-packet and handoff formats. |
| [inbox/](inbox/README.md) | Per-task context, evidence, and handoff locations. |
| [prompts/](prompts/README.md) | Copy-paste global context and role prompts. |
| [launch/](launch/README.md) | Five independent-session briefs and their first packets. |

## Operating model

```text
human direction
  -> reviewed decision
  -> role-specific work packet
  -> isolated worktree and bounded task
  -> evidence and independent verification
  -> promote, reject, or revise
```

Workers write task-local outputs. The coordinator alone updates canonical
program documents after review. A worker may propose a decision but cannot
make it canonical, promote its own mechanism, or auto-merge a change.

## Status vocabulary

- **Draft:** proposed structure or open work.
- **Prepared:** a task packet is complete and may be assigned.
- **In progress:** an isolated worker has accepted the packet.
- **Verified:** fixed acceptance checks and evidence have passed.
- **Promoted:** a human-reviewed decision authorizes a mechanism or release.
- **Rejected:** the hypothesis or implementation is retained as negative
  evidence, not silently deleted.

## Local references

### Boundary correction - 2026-08-19

The legacy wording below is overridden for certification work. Trace-Lite keeps
local Beta workstream material, but the moved trace-bench component is the
intended certification boundary. It currently has no Git identity, so it is
non-certifying until P-007 resolves a repository or content-manifest policy.
Legacy trace-lite benchmark material is regression/exploratory context until
P-008 chooses the canonical certification runner/integration boundary. Raw
data remains outside Git and is referenced by provenance records only.

Trace-Lite contains local operational pointers and Beta-specific workstream
documents under `trace-lite/docs/program/`. Dataset manifests and protocols
belong under `trace-lite/benchmarks/`; raw downloaded data remains outside
Git and is referenced by provenance records only.

## Document precedence

When documents disagree, resolve them in this order:

1. Explicit human direction recorded in an accepted decision.
2. [00_CHARTER.md](00_CHARTER.md) and
   [01_INVARIANTS.md](01_INVARIANTS.md).
3. The accepted task packet and its pinned input hashes.
4. The relevant current-checkout code, schemas, and tests.
5. Research memos, workstream briefs, and implementation handoffs.

The program documents are a control plane, not a substitute for inspecting the
current checkout. A worker must call out an inconsistency rather than silently
choosing a convenient interpretation.

## How work enters and exits the program

1. A human or coordinator records a concrete question, defect, hypothesis, or
   required capability.
2. The coordinator identifies the dependency node in the execution DAG and
   assembles a bounded work packet.
3. The worker verifies the packet's current-state assumptions in an isolated
   worktree before editing.
4. The worker returns a structured handoff with artifacts, commands, evidence,
   failures, risks, and a recommendation.
5. An independent verifier checks the fixed acceptance criteria.
6. The coordinator proposes a decision-log, DAG, risk, or follow-up update.
7. The human owner accepts, rejects, or redirects the next step.

No handoff alone advances a gate. A passing unit suite alone does not advance a
research, release, scale, or consumer-integration gate.

## Review cadence and work-in-progress limits

The program uses short evidence cycles rather than a single large build:

| Cadence | Purpose | Required output |
| --- | --- | --- |
| Packet review | Before a worker starts. | Scope, inputs, allowed paths, acceptance checks. |
| Mid-task checkpoint | Only when assumptions fail or scope grows. | Blocker, evidence, and decision request. |
| Handoff review | At task completion. | Structured result and verifier assignment. |
| Gate review | At a DAG gate. | Consolidated evidence and promote/reject/defer decision. |

Run no more than three mutable worker tasks at once. Keep research, data,
evaluation, and implementation work separate enough that an implementation
cannot silently change the evaluation that certifies it.

## Repository and artifact rules

- Use one isolated worktree per mutable task. Record its base commit and the
  selected paths in the packet.
- Do not add raw public caches, private data, provider secrets, benchmark
  results, build directories, or temporary verification output to Git.
- Preserve source data, manifests, result hashes, and negative evidence long
  enough to reproduce a decision. Pruning requires a separate approval.
- Treat existing dirty changes as user-owned unless their author and scope are
  known. Work around them or create a new worktree.
- Keep global documents concise enough to be read by every worker; put deep
  research, raw reports, and task-specific evidence in the task inbox.

## First dispatch order

### Detailed dispatch correction - 2026-08-19

There are three read-only F0 records, not merely two:

1. F0a captures current evaluator and benchmark code/source anchors.
2. F0b closes dataset candidate/provenance records without downloading.
3. F0c records Trace-Lite, Trace, trace-bench, and control-plane identities,
   dirty-state protection, and stale packet boundaries.

No mutable benchmark implementation starts until F0a plus P-007/P-008. No
mutable TL or Trace implementation starts until F0c identifies a clean
accepted base and a packet is prepared with a lease. See
[SESSION_OPERATING_MANUAL.md](SESSION_OPERATING_MANUAL.md).

The coordinator starts with two short, read-only record-closure packets:

1. **F0a / E1-refresh:** re-anchor the evaluation and benchmark audit to the
   current Trace-Lite checkout and the separately versioned benchmark suite.
2. **F0b / D1-refresh:** create durable source, license, version, checksum,
   staging, and query/evidence-mapping records. No data download is implied.

After review of those records, prepare independent foundation packets for:

1. the fail-closed benchmark runner and release manifest;
2. the Trace-Lite candidate/active projection lifecycle and safe bounded graph
   baseline;
3. the Trace Cortex Release and temporal/revocation foundation;
4. independent negative verification and consumer-conformance fixtures.

Broad architecture research is intentionally deferred until the resulting
foundation baseline is reproducible and independently verified. Narrow
research needed to resolve a named implementation dependency remains allowed,
but does not itself authorize a product change or promotion.

## Detailed Foundation Procedure

The broad material in this document is expanded by:

- [SESSION_OPERATING_MANUAL.md](SESSION_OPERATING_MANUAL.md), which defines
  agent/session, worktree, artifact, and stop-condition procedure;
- [COMPONENT_REGISTRY.md](COMPONENT_REGISTRY.md), which records current roots,
  dirty-tree protection, moved benchmark constraints, and source observations;
- [FOUNDATION_GATE_DOSSIER.md](FOUNDATION_GATE_DOSSIER.md), which prevents
  feature completeness from being confused with data admission, certification,
  100K readiness, or a passed scale gate.

If these detailed documents conflict with broad wording here, detailed
Foundation procedure controls until a human accepts a replacement decision.
