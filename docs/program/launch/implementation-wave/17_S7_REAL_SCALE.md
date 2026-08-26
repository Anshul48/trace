# S7 — Real-Scale Readiness Owner

## Mission

Prove progressively larger memory operation using real, license-aware text
corpora. S7 begins only after the Foundation Gate. It owns scale admission,
load/recovery measurements, resource accounting, and the 1M pilot proposal. It
does not use synthetic data as certification and does not claim that a vector
benchmark is a text-memory gate.

## 100K gate entry conditions

Require:

- accepted Foundation Gate dossier;
- real text corpus admission with source/license/version/checksum records;
- reversible source -> document -> segment/atom mapping;
- query and judgment/evidence protocol;
- pinned runner and implementation artifacts;
- lifecycle and fail-closed verifier evidence;
- capacity report with working headroom;
- explicit scale worktree/lease and external result root.

The 100K corpus must contain approximately 100,000 real source atoms or a
documented equivalent that exercises ingestion, organization, retrieval,
provenance, and recovery. BigANN/SIFT1M may run in parallel as vector/index
operations evidence, but cannot replace the text corpus.

## 100K test plan

Measure separately:

### Correctness and recovery

- complete source/atom coverage;
- orphan/unassigned counts;
- exact offsets and hashes;
- idempotent ingestion;
- crash/replay and rebuild equivalence;
- candidate/active isolation under large builds;
- stale-edge and rollback behavior;
- deletion/revocation behavior when the approved contract supports it.

### Retrieval

- query classes and stable query IDs;
- Recall@k, nDCG, precision/citation measures, and abstention metrics using
  the accepted denominator rules;
- evidence completeness and provenance validity;
- cold/warm p50/p95 and tail behavior;
- PPR/graph work, node counts, depth, and degree distributions.

### Operations and cost

- ingest throughput and replay time;
- build time and incremental delta cost;
- peak/steady memory, disk, index sizes, and temporary space;
- QPS under declared concurrency;
- provider/model calls and cost where applicable;
- restart/outage/cleanup behavior;
- observability and actionable error receipts.

Do not blend measurements from different source, configuration, model, or
release identities. Preserve raw metrics and derived summaries separately.

## 1M pilot preparation

Plan, but do not claim, the next scale step only after 100K evidence is
accepted. The pilot brief must address:

- partitioning/routing strategy;
- bounded incremental projection deltas;
- index build and alias management;
- graph degree and activation budgets;
- storage/backup/recovery economics;
- privacy/policy and historical-read costs;
- operational load, failure injection, and rollback;
- expected capacity and stopping thresholds.

10M/10B/100B are research and distributed-systems programs, not automatic
extrapolations from the 1M pilot.

## Subagents

Use a corpus partitioning helper and a resource-observability helper. They may
prepare disjoint reports and repeatable load scripts. The primary session owns
the corpus manifest, run identity, and claim wording.

## Required handoff

Include corpus admission, all raw/derived hashes, capacity report, test matrix,
resource and latency data, recovery evidence, failures, limitations, and the
separate 1M pilot recommendation. State clearly whether the 100K gate passed,
blocked, or was not attempted.

## Stop conditions

Stop if the corpus is synthetic/unlicensed/unmapped, the runner is not pinned,
any fallback or mock path is active, provenance is incomplete, active/candidate
state leaks, or the resource measurements cannot be reproduced.
