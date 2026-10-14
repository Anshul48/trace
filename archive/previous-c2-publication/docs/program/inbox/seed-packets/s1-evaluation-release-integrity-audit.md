# Prepared Packet: S1 Evaluation — Release Integrity and Manifest Design

> **State:** Prepared, unassigned
> **Role:** Evaluation engineer
> **DAG nodes:** E1, V1 input
> **Mutation authority:** Audit and design artifacts only. Do not alter
> retrieval algorithms, score thresholds, or release claims.

## Objective

Audit the current Trace-Lite benchmark execution paths and produce a detailed
design for a machine-validated, fail-closed evaluation manifest and release
mode. The output must distinguish development/regression behavior from any
future certification path.

## Required inputs

- Shared evaluation protocol, contracts, promotion rubric, risk register, and
  evaluator role/workstream brief.
- Trace-Lite benchmark README, benchmark matrix, runner, benchmark engine,
  adapters, fixtures, reporter, and current tests.
- Dataset-record templates and any data-steward interim handoff available.

## Required audit questions

1. Which defaults choose mock models, sample data, synthetic data, or fallback
   retrieval paths?
2. What happens after organization/reindex/query failures?
3. How is a fixture marked release-authoritative, and what evidence actually
   supports that label?
4. Which run metadata is captured now, and what required provenance/config
   information is missing?
5. Which metrics are query-level versus aggregate only?
6. How can the runner distinguish a developer smoke test from a certification
   candidate before execution?

## Required design

Propose:

- manifest schema and mode/state model;
- preflight assertions and failure taxonomy;
- public/held-out/fault/scale lane separation;
- query-class labels and result artifact schema;
- paired baseline/ablation policy;
- 100K resource/recovery measurement plan;
- tests proving that prohibited fallback paths fail closed.

## Required output

1. Current-state audit table with code/symbol anchors.
2. Manifest and protocol amendment proposal.
3. Negative integrity test plan.
4. Migration sequence that preserves existing developer/regression capabilities.
5. Explicit non-goals and claim boundary.

## Acceptance criteria

- The design can fail before producing a score when required inputs are absent.
- Existing internal fixture use is labeled regression/development unless
  independently admitted.
- The plan records exact data/config/environment needed to reproduce a run.
- No score threshold is changed based on a candidate result.

## Stop conditions

Stop and escalate if the design would require a new provider/data policy,
deleting historical results, or changing an evaluator-owned contract without
human direction.

## Handoff

Return a fixed-evaluator proposal suitable for the later TL/Trace implementation
and verifier packets.
