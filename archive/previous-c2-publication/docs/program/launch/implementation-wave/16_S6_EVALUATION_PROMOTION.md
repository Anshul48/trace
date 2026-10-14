# S6 — Evaluation, Promotion, and Foundation Gate Owner

## Mission

Turn B1 and D2b outputs into reproducible baseline evidence, a P-005 decision
brief, a B3 certification manifest, and a Foundation Gate dossier. S6 does not
choose thresholds silently, self-certify, or promote a mechanism merely because
one metric improved.

## Entry conditions

S6 starts only when all are available:

- accepted B1 handoff and pinned runner/source identity;
- D2a raw manifests and D2b normalized/evidence mappings;
- V1a result or an explicit documented blocker;
- L1/TR1 lifecycle identities sufficient to know which retrieval runtime was
  evaluated;
- coordinator-approved query-class protocol;
- no unresolved fallback, provenance, or source-license blocker.

## Baseline evidence

Run only through the canonical `trace-bench` runner. For every run record:

- runner commit/tag and Trace-Lite artifact hash;
- dataset raw/normalized manifest hashes;
- query-set and judgment mapping hashes;
- configuration, embedding, hierarchy, graph, and model fingerprints;
- hardware/runtime/parallelism metadata;
- cold/warm status and resource limits;
- stable query IDs and per-case status;
- source evidence IDs, offsets, hashes, and release identity;
- complete error/abstention/exclusion counts.

Separate capability lanes: direct lookup, semantic retrieval, chronology,
multi-hop, contradiction/revision, thematic context, abstention, organization,
and operations/scale. Do not blend BigANN vector scores with text-memory
quality.

## P-005 decision brief

Prepare, but do not approve, numeric gates. The brief must propose:

- primary/secondary metrics by query class;
- denominator and exclusion rules;
- latency cold/warm and resource budgets;
- minimum evidence/provenance coverage;
- statistical comparison and confidence/significance method;
- practical-effect requirement;
- reproducibility requirements;
- handling of failed/blocked cases;
- rationale based on baseline distributions rather than arbitrary numbers.

The human owner records P-005. Until then, label thresholds as proposed and
keep certification eligibility false.

## B3 certification manifest

Assemble a manifest that binds:

- admitted dataset/source records and rights;
- runner source/tag and package artifact hashes;
- Trace-Lite/Trace release identities;
- model/provider/embedding fingerprints;
- query/judgment/evidence mappings;
- hardware and environment;
- test/verifier receipts;
- threshold decision and statistical method;
- output hashes and retention location;
- explicit assertion that no fallback/mock/synthetic path ran.

The manifest must be rejected if any required field is absent or contradictory.

## Foundation Gate dossier

The dossier must show evidence for all five gates:

1. durable memory;
2. self-organization;
3. retrieval accuracy;
4. bounded performance/resources;
5. readiness for a real 100K corpus.

For each, list evidence, authority level, verifier, limitations, and unresolved
risks. A gate can be `passed`, `blocked`, or `not attempted`; “partial” must
not be presented as production readiness.

## Promotion rubric

Promote a mechanism only when it improves the target task with credible
evidence and does not violate truth, provenance, policy, recovery, latency,
memory, or economic constraints. A retrieval win that contaminates truth or
leaks a candidate projection is rejected.

## Subagents

Use independent query-class, statistics, and manifest reviewers. They may
recompute metrics from immutable outputs, but they cannot alter the canonical
result or approve thresholds.

## Required handoff and stop conditions

Return baseline manifests, run receipts, P-005 brief, B3 draft, gate dossier,
and explicit next action. Stop if any run used a fallback, lacks source
provenance, cannot reproduce its query IDs, or depends on an undecided policy.
