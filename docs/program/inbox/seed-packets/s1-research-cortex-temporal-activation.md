# Prepared Packet: S1 Research — Cortex Releases, Temporal Truth, and Bounded Activation

> **State:** Prepared, unassigned
> **Role:** Research analyst
> **DAG nodes:** R1, P-002, P-003, P-004
> **Mutation authority:** None. Read, research, and create task-local memo only.

## Objective

Produce a decision-ready research memo that narrows three linked design
questions:

1. What atomic Cortex Release lifecycle is minimally required for safe derived
   state in Trace?
2. What temporal truth semantics are required first for revision, supersession,
   revocation, deletion, and as-of retrieval?
3. How can typed bounded activation improve recall without allowing affinity to
   become fact or graph work to become unbounded?

This task does not design or implement a final schema. It creates evidence and
alternatives for human review.

## Required inputs

- Program charter, invariants, shared contracts, evaluation protocol, promotion
  rubric, decision log, and risk register.
- Research and Trace workstream briefs.
- Current Trace architecture/docs and relevant V2 source anchors:
  cortex, release, repository, retrieval, schemas, and production/runbook docs.
- Current Trace-Lite Beta workstream and graph/lifecycle overview for
  comparison only.

## Questions to answer

### Cortex Releases

- What is the minimum state machine and immutable metadata for candidate,
  validation, activation, retirement, and rollback?
- Which projection families must switch together to prevent mixed revisions?
- What validation dimensions are universal versus projection-specific?
- How should prior active revisions remain available for rollback and audit?

### Temporal truth

- Which temporal distinctions should be explicit in source/event contracts?
- What are the semantics of current, historical, superseded, revoked, and
  deleted evidence?
- How do effective time and ingestion time differ operationally?
- Which functions belong in canonical truth versus query-time ranking?

### Typed bounded activation

- Which relation families require separate trust, provenance, degree, and
  decay/revision rules?
- What controller decisions and work budgets are needed by query class?
- Which graph/PPR results should remain TL experiments until measured?

## Research method

1. Inspect current Trace and TL code/docs to separate implemented anchors from
   desired behavior.
2. Use primary literature/specifications/official systems sources where
   available.
3. Make an option matrix for each question with benefit, invariant risk,
   operational cost, smallest experiment, and rejection condition.
4. Identify a staged minimum viable scope, not a maximal architecture.
5. End with decision proposals for P-002, P-003, and P-004.

## Required output

Create a task-local research memo containing:

- source-grounded current-state facts;
- terminology map;
- three option matrices;
- recommended staged direction;
- open risks and non-goals;
- one minimal experiment or fault test per recommendation;
- exact questions requiring human direction.

## Acceptance criteria

- Material claims identify source type and confidence.
- The memo separates facts, inference, and speculation.
- Each recommendation preserves source truth, candidate isolation, policy, and
  bounded-work invariants.
- Each recommendation names a falsifiable local test.
- No implementation is proposed as ready solely from literature.

## Stop conditions

Stop and return a blocked memo if resolving a question requires choosing new
tenant/policy authority, deleting/migrating user data, or committing to a
distributed-scale platform beyond the 100K/1M program boundary.

## Handoff

Use the shared handoff template. Recommend: decision review, focused
experiment, retain as TL-only, defer, or reject.
