# Workstream 01 — Deep Research and Decision Support

> **Owner:** Research analyst
> **Status:** Draft outline

## Intended outcome

Produce decision-ready, source-grounded research that narrows the architecture
choices most likely to improve durable, evidence-grounded memory.

## First topic clusters

1. **Cortex Releases:** atomic derived-state lifecycle, validation, rollback,
   and active-read isolation.
2. **Temporal truth:** revisions, supersession, contradiction, validity,
   revocation, deletion, and as-of retrieval.
3. **Self-organization:** measurements for coverage, faithfulness, stability,
   routing utility, and peripheral evidence retention.
4. **Bounded activation:** typed graph relations, degree/work budgets, PPR and
   other multi-hop alternatives.
5. **Large-memory routing:** 100K to 1M lessons, partitioning, incremental
   projections, recovery, and economics.
6. **Model tiering:** controlled upper-bound experiments rather than model-size
   assumptions.

## Required inputs

- charter, invariants, promotion rubric, and open risks,
- a narrowly defined research question,
- relevant current architecture documents and code evidence,
- explicit evaluation or decision target.

## Expected artifacts

- research memo with primary sources and claim boundaries,
- option matrix with tradeoffs,
- candidate mechanism cards,
- smallest credible experiment and rejection criteria,
- questions requiring human direction.

## Exit condition

The coordinator can turn the memo into either an accepted decision proposal or
a bounded evaluation/implementation packet.

## Stop conditions

Stop and escalate when a question changes canonical truth, privacy/policy,
consumer authority, or scale commitments beyond accepted program direction.

## Priority packet sequence

### R1.1 — Cortex Release evidence and design axes

**Question:** What concrete release-state, validation, activation, retention,
and rollback behavior is required for a derived projection to be safe in Trace?

**Deliverables:** current-state map, external design references, alternatives,
failure-mode matrix, proposed contract amendments, and a small fault-test plan.

**Decision target:** P-003 in the decision log.

### R1.2 — Temporal truth minimum viable scope

**Question:** Which distinctions must the first Trace temporal contract express:
source version, ingestion time, effective time, supersession, revocation,
deletion/tombstone, or as-of query?

**Deliverables:** vocabulary map, consumer use cases, schema/compatibility
options, query examples, and a recommended staged scope.

**Decision target:** P-004.

### R1.3 — Bounded activation and graph economics

**Question:** Which relation classes and work budgets can preserve multi-hop
utility without unbounded degree, stale state, or fact/affinity confusion?

**Deliverables:** relation taxonomy, graph-growth analysis, controller/ablation
proposal, adversarial cases, and candidate budget dimensions.

**Decision target:** P-002.

### R1.4 — Measured self-organization

**Question:** How should hierarchy/organization quality be measured without
rewarding visually attractive but unhelpful topology?

**Deliverables:** metric mapping for coverage, topology, faithfulness, parity,
stability, routing benefit, and peripheral evidence retention.

### R1.5 — 100K to 1M architecture frontier

**Question:** Which assumptions change between a local real 100K corpus and a
1M pilot?

**Deliverables:** complexity/cost model, partitioning options, delta/rebuild
strategy, recovery considerations, and explicit unknowns.

## Research artifact standards

Each memo should include a compact option table:

| Option | Expected benefit | Invariant risk | Evidence maturity | Smallest test | Reject if |
| --- | --- | --- | --- | --- | --- |

It should also include a list of terms that are overloaded between papers and
the local codebase, so later implementation agents do not import ambiguous
terminology.

## Research review gates

The coordinator can prepare an implementation packet only when the memo:

- names a bounded mechanism or contract choice;
- separates documented facts from extrapolation;
- proposes an evaluator that can falsify the hypothesis;
- identifies policy/provenance/recovery impact;
- states what must remain TL-only until further proof.
