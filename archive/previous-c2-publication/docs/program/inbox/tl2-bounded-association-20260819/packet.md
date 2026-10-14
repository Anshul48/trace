# TL2 - Bounded Association and Graph Work Baseline

> **Role:** Trace-Lite engineer with independent verifier
>
> **DAG node:** L2 / TL2
>
> **State:** Blocked. Requires accepted P-002, prepared TL lifecycle state,
> clean worktree lease, and fixed verifier matrix.

## 1. Objective

Replace unsafe all-pairs shared-term association construction with an explicitly
bounded, evidence-proven association baseline. Preserve source evidence and
candidate/active lifecycle. Do not treat affinity as fact.

## 2. Why this packet exists

Current co-occurrence work can scale approximately with the sum of pair counts
for each term frequency. A term in 100,000 atoms can imply around five billion
candidate pairs. That makes the current construction unacceptable for a 100K
real-corpus path.

This packet has two goals:

1. engineering safety: bounded build, storage, query work, and lifecycle;
2. scientific utility: preserve useful multi-hop association under fixed
   evidence/latency budgets.

It does not claim that a software graph reproduces the brain. Bio-inspired
language is a hypothesis source, not a truth/biology claim.

## 3. Required P-002 decision inputs

P-002 must freeze, per corpus/query class where relevant:

- maximum eligible term/document frequency or other participation rule;
- maximum candidate witnesses/partners per atom/term;
- maximum stored soft-affinity degree;
- maximum structural and semantic edge degree separately;
- edge expiry/decay/rebuild rule;
- PPR nodes, edges, depth, iterations, wall-time, and memory budget;
- build-time/memory/disk envelope;
- deterministic tie-break/sampling seed;
- telemetry and rejection/drop counters;
- policy for any learned/behavioral signal;
- 100K adversarial high-frequency test.

Proposals are not gates until human P-002 acceptance.

## 4. Bio-inspired hypotheses allowed for evaluation

The implementation may prototype one bounded sparse mechanism, but must state
which hypothesis it tests:

| Hypothesis | Engineering analogue | Safety restriction |
| --- | --- | --- |
| Sparse assemblies | A small set of context-specific atom groups or witness records rather than all term pairs. | Assembly membership has source/provenance and fixed capacity. |
| Local competition | Per-atom/term top-k selection using deterministic score/tie-break. | No unbounded global neighbor insertion. |
| Synaptic homeostasis | Degree/resource budget with replacement/decay of weakest affinity. | Affinity remains rebuildable and non-factual. |
| Episodic binding | Structural sequence/source/section edges separate from soft co-activity. | Typed edges do not share trust semantics. |
| Novelty/salience gating | Only unusual/discriminative bounded events create candidates. | Do not invent salience from hidden model state. |
| Replay/consolidation | Batch candidate build and validation before active handover. | Candidate never leaks to normal query. |

Acceptable alternatives include capped inverted-list witnesses, local sketch/
reservoir methods, sparse hyperedge/assembly indexes, or deterministic
co-occurrence sampling. The packet compares them against a simple bounded
baseline and retains discarded results.

## 5. Required design split

Maintain independent typed channels:

1. structural: sequence, source, section, parent/child;
2. trusted semantic/evidence relations: anchored, reviewed where required;
3. soft affinity: similarity/co-activity, rebuildable, bounded;
4. behavioral signals: separately authorized, decayed, never factual.

Each channel has its own provenance, storage budget, edge cap, TTL/decay,
query work budget, and evidence-bundle label.

## 6. Implementation requirements

- never enumerate all pairs for an unbounded high-frequency group;
- make every cap observable: eligible/skipped/capped/dropped/replaced counts;
- deterministic behavior under fixed input/configuration;
- candidate-scoped writes and validation through L1 lifecycle;
- source/witness provenance for every stored edge or assembly;
- active release cleanup/retention without stale-edge leakage;
- PPR/query controller enforces actual measured work cap;
- fallback on budget exhaustion is explicit insufficient/bounded result, not
  unbounded traversal or fact invention.

## 7. Acceptance and verifier cases

The packet cannot pass from average-case metrics alone. Required cases:

- one term in a large fraction of corpus;
- adversarial repetitive boilerplate;
- long document/section with repeated vocabulary;
- incremental source addition/removal/rebuild;
- prior active graph preserved across candidate failure;
- degree/work limits enforced exactly;
- deterministic repeat under same input;
- query evidence retains source/witness labels;
- multi-hop quality comparison against lexical/dense/hierarchy baseline;
- build/query resource measurements by class.

V1b independently validates source identity, lifecycle isolation, caps, and
reported work. A graph quality improvement that violates caps/provenance/
rollback is rejected.

## 8. Non-goals

- no new canonical facts or truth updates;
- no unrestricted global graph, all-pairs workaround, hidden large-model
  associations, or behavioral learning without separate authority;
- no 100K scale claim from synthetic-only adversarial test;
- no Trace adaptation until a promoted, verified mechanism exists.

## 9. Required artifacts

- completed P-002 decision record and input manifest;
- association policy/configuration schema;
- design alternatives and fixed ablation plan;
- edge/assembly provenance schema;
- adversarial workload manifest;
- build/query telemetry and budget reports;
- implementation handoff and V1b verification report;
- promotion/reject recommendation.
