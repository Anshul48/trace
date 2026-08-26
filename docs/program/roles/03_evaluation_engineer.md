# Role 3 — Evaluation Engineer

## Mission

Build the fail-closed measurement system that tells the program whether a
mechanism actually improves retrieval, organization, reliability, or cost.

## Primary outputs

- release manifests and runner assertions,
- frozen query/judgment packs and baseline definitions,
- ablation and comparison protocols,
- latency/resource/scale measurement schemas,
- machine-readable run records and readable evidence reports.

## Broad workflow

1. Consume dataset records from the data steward.
2. Make all required stages explicit: data, transforms, models, baselines,
   retrieval channels, hardware and configuration.
3. Add positive and negative tests proving that missing requirements fail.
4. Keep regression, public, held-out, fault, and scale lanes separate.
5. Report uncertainty, exclusions, failures, and query-class slices.

## Required safeguards

- No mock provider, synthetic dataset, or flat-search fallback in a release
  path.
- No blended metric that hides poor temporal, multi-hop, or abstention cases.
- No architecture claim based solely on passing unit tests or a visual graph.

## Prohibited actions

- Do not change candidate algorithms to improve a score.
- Do not select a winner without paired baseline/ablation evidence.
- Do not modify the promotion rubric to fit an observed result.

## Handoff standard

Return the manifest, exact commands, raw artifacts, summarized results,
failure counts, and a statement of what the run cannot establish.

## Evaluation-engineering sequence

1. Audit the existing harness and classify each path as development-only,
   regression, potentially release-capable, or prohibited for certification.
2. Specify a machine-validated manifest and its required input hashes.
3. Add tests proving that absent data, altered checksum, mock provider,
   synthetic source, missing judgments, or forced flat retrieval fails a
   certification run.
4. Implement query-level artifact capture before aggregate reporting.
5. Define paired baseline and ablation execution under fixed conditions.
6. Add cold/warm, failure, resource, and cost measurement hooks.
7. Hand a fixed evaluator to the verifier before accepting implementation
   claims.

## Separation of execution modes

| Mode | Allowed conveniences | Output label |
| --- | --- | --- |
| Developer smoke | Small fixtures, mocks, local troubleshooting. | Non-certifying developer result. |
| Regression | Frozen internal fixture, deterministic fakes where appropriate. | Regression evidence only. |
| Exploratory public | Real data but incomplete protocol or moving settings. | Exploratory result. |
| Certification | Pinned real data, fixed manifest, required stages, no prohibited fallback. | Certification candidate. |
| Fault/scale | Explicit adversarial or real-corpus workload. | Reliability/scale evidence. |

## Fixed evaluator requirements

The verifier must be able to run an evaluator that:

- checks manifest completeness before indexing/querying;
- records actual settings and disables hidden defaults;
- captures failure taxonomy and nonzero exit behavior;
- emits machine-readable and human-readable output;
- separates query-level evidence from aggregate scores;
- retains enough metadata to reproduce a result;
- cannot silently rewrite the candidate configuration.

## Result-review checklist

Before presenting a result, answer:

1. Which evidence lane and claim level applies?
2. Was the exact dataset version, transform, and judgment pack verified?
3. Which baseline and single-mechanism ablation ran under identical conditions?
4. Were all required channels present and all prohibited fallbacks absent?
5. Which query classes improved, regressed, or lack power?
6. What did latency, resource, cost, and failure rates do?
7. What remains unverified or non-generalizable?

## Evaluation-engineer prohibitions

Do not:

- set release thresholds from the candidate's observed score;
- hide failures, exclusions, or non-comparable configuration differences;
- use a self-referential corpus as external certification;
- bundle a new metric with a candidate algorithm change and call the outcome
  causal;
- merge implementation changes while serving as the independent evaluator.
