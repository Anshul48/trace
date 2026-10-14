# Work Packet Template

> Copy this template into a task-specific inbox directory. Fill only from
> accepted program documents and current-checkout evidence.

## Identity

- **Task ID:**
- **Role:**
- **State:** Prepared
- **Base commit / worktree:**
- **Deadline or time budget:**

## Objective

State the bounded outcome in one paragraph.

## Context inputs

- Charter/invariant/decision references:
- Relevant source files and evidence:
- Input document hashes:
- Current-state assumptions to verify:

## Scope

- **Allowed paths:**
- **Forbidden paths:**
- **Required output files:**
- **Explicit non-goals:**

## Acceptance evidence

- Required tests or measurements:
- Required negative/failure tests:
- Required provenance or manifest records:
- Review criteria:

## Handoff

- Summary of changes or findings:
- Commands actually run:
- Artifacts produced:
- Risks and unanswered questions:
- Promotion recommendation: none / investigate / reject / promote for review

## Packet preflight checklist

The coordinator marks a packet Prepared only after confirming:

- the objective maps to one DAG node and one desired state transition;
- scope is narrow enough for a single worker/worktree;
- current repository assumptions were checked or explicitly marked for audit;
- document, code, and evaluator inputs are pinned;
- external authority for downloads, providers, migrations, or destructive work
  is explicit;
- acceptance includes a negative/failure condition where the task changes
  lifecycle, evaluation, policy, or data behavior;
- the verifier or review path is named.

## Detailed objective format

Write the objective in this form:

> Change or investigate **X** in **named scope** so that **observable condition**
> holds, while preserving **named invariants**. Success is measured by
> **specific evidence**; this task does not claim **explicit non-goals**.

Avoid objectives that combine data acquisition, architecture design,
implementation, benchmarking, and integration in one packet.

## Context manifest

| Input type | Record |
| --- | --- |
| Program direction | Decision IDs and charter/invariant hashes. |
| Repository state | Repository, base commit, branch/worktree, relevant dirty-state note. |
| Code anchors | Files, symbols, migrations, tests, and behavior to inspect. |
| Evaluation | Manifest, datasets, fixture IDs, baseline, expected claim level. |
| External state | Provider, data, service, credentials, or approval boundary. |
| Prior evidence | Handoff/report IDs and conclusions that may be relied on. |

## Scope declaration

| Field | Required content |
| --- | --- |
| Allowed paths | Exact directories/files the worker may create or edit. |
| Read-only paths | Related code/docs the worker may inspect but not modify. |
| Forbidden paths | User-owned, evaluator-owned, generated, data, secret, or unrelated areas. |
| Authorized operations | Tests, downloads, provider calls, migrations, staging, cleanup. |
| Forbidden operations | Auto-merge, deletion, threshold change, evaluator rewrite, direct consumer coupling. |

## Acceptance design

For an implementation packet, list:

1. expected happy-path behavior;
2. expected failure/rollback behavior;
3. source/provenance or policy behavior if applicable;
4. compatibility requirements;
5. command(s) or evaluator(s);
6. known environment limitations;
7. evidence artifact names and reviewer.

For a research/data packet, list the decision or manifest completeness checks
instead of pretending a code test is relevant.

## Stop-and-escalate conditions

Stop the task and produce a blocked handoff if:

- the packet conflicts with a charter/invariant or accepted decision;
- the required data/license/provider authority is absent;
- a destructive action or migration needs new approval;
- the current checkout differs materially from the packet assumptions;
- the change needs paths or dependencies outside the allowed scope;
- the evaluator cannot distinguish success from a prohibited fallback.
