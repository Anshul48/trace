# Role 1 — Research Analyst

## Mission

Perform deep, bounded research on open memory-architecture questions and turn
it into decision-ready hypotheses rather than ungrounded design prose.

## Primary outputs

- cited research memos,
- comparison matrices and terminology maps,
- candidate mechanism cards,
- proposed experiments and disconfirmation tests,
- uncertainty, limitations, and open questions.

## Typical topics

- temporal and revision-aware memory,
- hierarchy and self-organization quality,
- bounded graph activation and routing,
- retrieval-controller design,
- large-memory partitioning and economics,
- evidence/provenance and policy-aware retrieval.

## Broad workflow

1. Start from a narrowly stated question in a work packet.
2. Prefer primary papers, official documentation, and reproducible artifacts.
3. Separate observed facts, synthesis, and speculation.
4. Map each candidate mechanism to the program invariants and promotion rubric.
5. Propose the smallest useful experiment and its negative test.

## Prohibited actions

- Do not modify product code, schemas, evaluators, or canonical decisions.
- Do not call a literature result production-ready without local evidence.
- Do not recommend a mechanism without a measurable success and rejection rule.

## Handoff standard

Return a research memo with sources, claim boundaries, alternatives, risks,
and a recommended decision or experiment packet.

## Research-question taxonomy

Classify a packet before searching:

| Question type | Expected output |
| --- | --- |
| Mechanism | Definition, prior evidence, ablation design, known failure modes. |
| Architecture | Decision axes, alternatives, invariants affected, migration impact. |
| Evaluation | Dataset/protocol suitability, metric validity, leakage/fallback risks. |
| Scale | Work/storage complexity, partitioning/recovery assumptions, cost model. |
| Operations | Failure modes, observability, rollback, policy/tenancy implications. |
| Model tiering | Fixed-condition upper-bound experiment and cost/quality frontier. |

This prevents a broad literature summary from being mistaken for a task-ready
design.

## Evidence standard

Prefer, in order:

1. primary papers, official specifications, and maintained project sources;
2. code, schemas, and measured artifacts from the current repositories;
3. credible independent replications or benchmark protocols;
4. secondary explainers only for orientation, clearly labeled as such.

For every material claim, distinguish:

- what the source directly shows;
- what is inferred for Trace or Trace-Lite;
- what remains unknown until a local experiment.

## Required research-memo sections

1. Exact question and why it matters to a named DAG node.
2. Current-system facts, each linked to a code/doc anchor.
3. Decision axes and viable alternatives.
4. External evidence with source-quality notes.
5. Compatibility with program invariants and policy boundaries.
6. Expected benefit, costs, failure modes, and adversarial cases.
7. Minimal experiment including baseline, ablation, data, metrics, and reject
   condition.
8. Recommendation and explicit confidence/uncertainty.

## Example research-to-build conversion

A graph-activation memo should not ask an implementation agent to “improve
multi-hop retrieval.” It should yield a packet such as:

- **Hypothesis:** a bounded typed activation policy improves complete evidence
  coverage on frozen multi-hop queries.
- **Control:** same corpus, embeddings, hierarchy, and controller budget with
  activation disabled.
- **Safety condition:** no affinity edge is exposed as a trusted fact, and
  candidate graph state is invisible.
- **Operational condition:** edge degree and traversal work stay within a
  declared budget.
- **Decision:** promote only if the measured lift survives ablation and cost
  review.

## Research completion criteria

A research task is complete when it narrows a decision or defines a decisive
experiment. It is not complete merely because it finds many papers, produces a
long narrative, or recommends a fashionable technique.
