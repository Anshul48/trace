# Promotion Rubric

> **Status:** Ratified promotion rubric under `DEC-CAP-001` (`TRACE-CAP-001`). A mechanism is not promoted by a worker, a benchmark number, or a passing unit suite alone.

## 1. Promotion question

For each Trace-Lite or research mechanism, ask:

> Does this mechanism improve a real memory outcome enough to justify its
> safety, provenance, latency, storage, rebuild, operational, and maintenance
> cost inside Trace?

## 2. Required dossier sections

1. Hypothesis and target query/task classes.
2. Mechanism definition and relevant configuration.
3. Baseline and paired ablation results.
4. Source/evidence and provenance impact.
5. Truth, policy, temporal, and rollback analysis.
6. Latency, storage, rebuild, and cost effects.
7. Recovery and failure-mode evidence.
8. Trace adaptation plan, or reasons not to adapt.
9. Recommendation: promote, reject, or investigate.

## 3. Evaluation dimensions

| Dimension | Broad requirement |
| --- | --- |
| Retrieval | Credible improvement on the intended query class. |
| Organization | Better coverage, faithfulness, stability, or routing. |
| Safety | Cannot contaminate canonical truth or bypass policy. |
| Provenance | Exact evidence remains recoverable and explainable. |
| Operations | Candidate lifecycle, observability, and rollback are defined. |
| Performance | Cost and latency fit explicit query-class budgets. |
| Scale | Storage and work growth remain bounded at the relevant gate. |
| Maintenance | Configuration and failure modes remain comprehensible. |

## 4. Automatic rejection signals

Reject or return for redesign when a mechanism:

- depends on hidden fallback behavior,
- turns affinity or generated text into canonical fact,
- cannot be scoped to a candidate/active release lifecycle,
- lacks exact source recovery,
- wins only on synthetic or self-referential certification data,
- has unbounded graph, rebuild, or query work,
- cannot be rolled back or observed.

## 5. Decision record & risk-tiered activation (`DEC-CAP-001`)

Under `DEC-CAP-001` (`CAP-D007`), promotion and activation are risk-tiered:

1. **Tier 1 (Low Risk - Derived Navigation Summaries):**
   - Cluster descriptions, section summaries, and topic navigation holons.
   - May auto-activate within approved profile scopes following passing detached
     validation (proposition support $\ge 95\%$, 100% byte anchor resolution).

2. **Tier 2 (Medium Risk - Relational Proposals):**
   - Inferred entity associations and inter-cluster affinity links.
   - Require validation receipts and automated consistency checks before
     activation; subject to rollback if drift exceeds thresholds.

3. **Tier 3 (High Risk - Schema Mutations & Factual Assertions):**
   - Schema modifications, ontology promotions, and authoritative assertions.
   - Strictly require explicit Human Owner review and ratification in `06_DECISION_LOG.md`.

Only a reviewed decision log entry can authorize overall architecture promotions.
Rejected mechanisms remain useful negative evidence and may be reconsidered only
with a new evidence packet.

## 6. Promotion units

Promote the smallest independently controllable unit:

| Unit | Example | Required boundary |
| --- | --- | --- |
| Retrieval policy | A controller decides whether graph activation is justified. | Query profile, work budget, fallback behavior, telemetry. |
| Graph mechanism | Bounded PPR over typed affinity/structural relations. | Edge provenance, degree bounds, candidate release scope. |
| Organization projection | A hierarchy/routing method. | Source coverage, topology/faithfulness, rebuild parity. |
| Model tier | A larger model only for a narrow summary/rerank step. | Fixed corpus/configuration ablation and cost ceiling. |
| Data/measurement practice | A new public benchmark or fault fixture. | License, provenance, reproducibility, claim boundary. |
| Service capability | Evidence-bundle status or temporal query feature. | Contract version, policy, conformance, rollback behavior. |

Do not promote an entire experimental subsystem when only one decision rule or
projection policy has evidence.

## 7. Dossier evidence checklist

Each dossier should attach or reference:

1. A problem statement tied to a named query/task class.
2. A concise mechanism specification and configuration hash.
3. Current-state code anchors and changed interfaces.
4. The exact dataset, transforms, query/judgment IDs, and manifest.
5. A paired baseline and single-mechanism ablation.
6. Query-level retrieval/evidence results and class slices.
7. Source-provenance and policy impact analysis.
8. Candidate/active release, recovery, and rollback behavior.
9. Graph/index/build/query cost measurements where relevant.
10. Known failures, uncertainty, and claim level.
11. A minimal Trace adaptation plan or explicit reason to retain the mechanism
    only in Trace-Lite.
12. Independent verification results.

## 8. Review sequence

1. **Completeness check:** the coordinator rejects incomplete dossiers before
   substantive review.
2. **Evidence review:** evaluator and verifier confirm that the protocol and
   reported artifacts support the claimed comparison.
3. **Invariant review:** Trace and TL owners identify truth, policy, release,
   and recovery impacts.
4. **Economics review:** compare benefit with latency, storage, model, and
   maintenance cost.
5. **Human decision:** accept for adaptation, retain as TL-only, investigate,
   reject, or defer.
6. **Post-adaptation verification:** Trace proves the accepted mechanism under
   its own contracts before it gains promoted status.

## 9. Decision categories

| Outcome | Meaning | Required next action |
| --- | --- | --- |
| Promote for adaptation | Evidence supports a bounded Trace implementation. | Create Trace packet and compatibility plan. |
| Retain in Trace-Lite | Useful local mechanism lacks a production case. | Keep experimental boundary and revisit only with new evidence. |
| Investigate | Signal is plausible but evidence/risks are incomplete. | Run a narrower decisive experiment. |
| Reject | Benefit does not justify cost/risk or violates invariants. | Preserve negative evidence and close packet. |
| Defer | External dependency, authority, or architecture decision is missing. | Record blocker and avoid speculative implementation. |

## 10. Trace adaptation checklist

Before a promoted mechanism is implemented in Trace, the packet must state:

- which Spine records and policy context it consumes;
- which Cortex projection family owns its derived state;
- candidate build, validation, activation, retirement, and rollback path;
- query controller/profile and explicit work budget;
- source/evidence explanation returned to clients;
- tenancy/RLS/redaction and deletion/revocation behavior;
- backfill/migration strategy and compatibility fixtures;
- observability, alarms, and operational failure behavior.

## 11. Promotion anti-patterns

The following are explicitly insufficient:

- copying a TL module because its algorithm is attractive;
- promoting a score improvement without a paired ablation;
- using a larger model result as proof of a graph or hierarchy improvement;
- calling a mechanism safe because it is rebuilding from a Spine while it can
  still leak candidate results;
- calling an API stable because a direct in-process client happens to work;
- declaring a mechanism production-ready before rollback and fault evidence.
