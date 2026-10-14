# Workstream Briefs

> **Status:** Draft broad-stroke briefs for task-packet generation.

These files sit between the program DAG and individual work packets. A brief
states the intended outcome, dependency inputs, first questions, expected
artifacts, and stop conditions for one specialist role. It does not authorize
unbounded research or code changes by itself.

| File | Primary role |
| --- | --- |
| [01_RESEARCH.md](01_RESEARCH.md) | Research analyst |
| [02_DATA_AND_STAGING.md](02_DATA_AND_STAGING.md) | Data steward |
| [03_EVALUATION.md](03_EVALUATION.md) | Evaluation engineer |
| [04_TRACE_LITE.md](04_TRACE_LITE.md) | Trace-Lite engineer |
| [05_TRACE.md](05_TRACE.md) | Trace engineer |
| [06_VERIFICATION_AND_INTEGRATION.md](06_VERIFICATION_AND_INTEGRATION.md) | Verifier / integration reviewer |

The coordinator turns approved portions of these briefs into a task-specific
packet under `../inbox/<task-id>/`.

## Brief-to-packet conversion

Each workstream brief answers broad program questions. A task packet narrows one
of them into a testable unit:

| Brief element | Packet translation |
| --- | --- |
| Intended outcome | One observable completion condition. |
| Work package | One task ID and a bounded objective. |
| Required inputs | Hash-pinned documents, code anchors, datasets, and evaluator. |
| Expected artifacts | Exact paths/names for memo, manifest, code handoff, or report. |
| Exit condition | Fixed acceptance checks and named verifier. |
| Stop condition | Explicit escalation route and safe default. |

The coordinator should never hand a worker an entire workstream as a single
unbounded task.

## Dependency map

~~~text
research ----+data ---------> evaluation -------> fixed acceptance criteria
                                  /                             +Trace-Lite lifecycle ------------/                               -> verification
Trace Cortex lifecycle ------------------------------------------/
verification + real-data evidence -> promotion -> scale -> shadow consumers
~~~

Research and data may run before implementation. Evaluation defines the
measurement boundary. Verification stays independent of the workers whose code
or data process it reviews.

## Workstream status discipline

Each brief may contain:

- **planned work:** no execution has begun;
- **current-state audit:** observed checkout facts with anchors;
- **implementation candidate:** scoped change awaiting verification;
- **verified evidence:** fixed evaluator/verifier result;
- **decision dependency:** a human choice needed before progression.

Do not use a completed checklist in a workstream brief to imply a program gate
has passed; gate status belongs in a dedicated report and decision record.

## Cross-workstream handoffs

| From | To | Required handoff |
| --- | --- | --- |
| Research | Coordinator / Evaluation | Mechanism card, alternatives, experiment/reject design. |
| Data | Evaluation | Dataset record, rights/staging/hash/transform evidence. |
| Evaluation | TL / Trace / Verifier | Fixed manifest, acceptance criteria, negative tests. |
| TL | Verifier / Promotion | Lifecycle/build evidence, tests, limitations, local claim level. |
| Trace | Verifier / Promotion | Release/migration evidence, compatibility/rollback notes. |
| Verifier | Coordinator / Human | Gate report, claim boundary, repair/promote/defer recommendation. |
