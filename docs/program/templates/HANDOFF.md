# Handoff Template

> Workers submit one concise handoff per task. A handoff is evidence for review,
> not an automatic completion or promotion decision.

## Outcome

- **Task ID:**
- **Status:** completed / blocked / needs review
- **One-sentence result:**

## Deliverables

- Changed files or produced artifacts:
- Data/manifests used:
- Evidence locations:

## Verification

- Commands and fixed evaluators:
- Results:
- Failure cases exercised:
- What remains unverified:

## Risks and follow-up

- New or changed risks:
- Recommended next packet:
- Questions requiring human direction:

## Claim boundary

- **Highest justified claim level:** C0 / C1 / C2 / C3 / C4 / C5
- **Why that level is justified:**
- **What this work explicitly does not establish:**

## Change and state accounting

| Field | Record |
| --- | --- |
| Base commit/worktree | Exact starting state. |
| Changed paths | Created/updated files and rationale. |
| Unchanged protected paths | Any relevant paths intentionally left untouched. |
| Data/external state | Downloads, providers, services, migrations, or none. |
| Retained state | Previous active release/build/source state preserved or affected. |
| Rollback path | Exact reversal/recovery route, or why not applicable. |

## Evidence inventory

| Artifact | Location | What it supports | Limitations |
| --- | --- | --- | --- |
| Tests |  |  |  |
| Manifest |  |  |  |
| Logs/report |  |  |  |
| Dataset record |  |  |  |
| Query/result sample |  |  |  |
| Research source |  |  |  |

## Verification truthfulness

State each result as one of:

- **Verified:** fixed check passed and artifact is available.
- **Observed:** behavior was seen but lacks an independent/fixed evaluator.
- **Planned:** described work was not run.
- **Blocked:** a stated prerequisite prevented the check.
- **Not applicable:** explain why.

Never summarize planned or observed behavior as verified.

## Reviewer decision prompt

End the handoff with:

1. The exact decision requested.
2. The safe default if no decision is made.
3. The smallest next packet for repair, verification, or follow-up.
