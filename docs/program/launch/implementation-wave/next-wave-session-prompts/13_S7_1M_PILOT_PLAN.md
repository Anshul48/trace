# Session 13 - S7 1M Pilot Plan

Read the shared bootstrap prompt first. Start only after the human owner has
accepted the 100K result and explicitly authorized 1M planning.

## Mission

Produce a bounded, reviewable 1M pilot plan. This is planning and readiness
work only; do not ingest or claim a 1M result.

## Direction

- Reuse the accepted 100K evidence as the baseline and state every assumption
  that would change at 1M.
- Specify candidate corpus admission, storage and cost envelope, hardware,
  capacity, recovery, observability, retention, and verification requirements.
- Identify expected bottlenecks and pre-declare stop conditions, fault tests,
  and promotion criteria.
- Preserve the Spine/Cortex, fail-closed evaluation, provenance, and
  candidate-isolation invariants at the larger scale.
- Separate local-pilot facts from any future distributed-scale research.

## Suggested subagents

Use read-only capacity, protocol, and failure-mode reviewers. No helper may
download data, provision infrastructure, or start a 1M build.

## Exit

Write a 1M readiness plan, input manifest, risk register update, and explicit
human-approval request for any future execution wave.

## Required plan sections

Use the accepted 100K dossier as the baseline and identify its exact
limitations. The plan must cover:

- candidate 1M corpus sources, rights, splits, and retention;
- expected raw/normalized/derived size and storage headroom;
- hardware, provider/model, network, concurrency, and operating envelope;
- ingest, projection, validation, activation, rollback, and recovery protocol;
- query classes, held-out evidence, provenance, and paired comparison design;
- cold/warm latency, QPS, memory, disk, graph work, build time, and cost
  measurements;
- observability, alerting, checkpointing, restart, and data-integrity checks;
- fault-injection matrix and independent-verifier assignment;
- explicit stop conditions, kill criteria, and promotion thresholds;
- what remains local-pilot-only versus what would require distributed design.

## No-execution boundary

Do not download or normalize a new 1M corpus, provision production
infrastructure, change P-005, activate a new release, or run a purported 1M
certification in this session. A cheaper planning reviewer may critique
capacity and fault assumptions, but may not mutate the plan or authorize the
pilot.

## Exit

Return a versioned plan with input-manifest hash, 100K evidence references,
capacity calculations, risk owners, verifier strategy, human approvals
required, and the exact packet that would be launched if the owner authorizes
execution.
