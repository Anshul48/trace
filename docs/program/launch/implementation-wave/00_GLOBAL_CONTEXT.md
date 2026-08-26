# Global Implementation Context

This file is the common context for every implementation-wave session. It is
intentionally self-contained so a new session does not need the prior chat.
The canonical program documents under `docs/program/` remain authoritative when
this file and a newer decision record disagree.

## Mission

Build a durable, self-organizing, evidence-grounded memory substrate:

- Trace-Lite is the fast local proving ground and embedded reference.
- Trace is the governed, versioned, policy-aware system of record.
- `trace-bench` is the separately versioned certification/evaluation harness.
- Reflex and Entorhinal are later consumers through a stable evidence-bundle
  service boundary, initially in shadow or advisory mode.

The project is not optimizing one benchmark number. It is proving durable
truth, replaceable organization, auditable retrieval, bounded computation,
recovery, policy correctness, and progressive scale.

## Accepted launch direction

The current execution plan assumes the following decisions have been accepted
by the human owner and must be recorded by S0 in the canonical decision log:

- **P-001:** admit the core real-data portfolio: BEIR SciFact, NFCorpus, and
  FiQA; BRIGHT coding/math material; MultiHop-RAG; and MuSiQue. BigANN/SIFT1M
  is an operations/vector-scale lane, not text-memory quality evidence.
- **P-003:** use a unified Cortex Release root with immutable component
  membership and a single active-release pointer.
- **P-007:** initialize `trace-bench` as an independent Git repository in its
  current directory, without inventing a remote.
- **P-008:** designate `trace-bench` as the sole certification runner. Legacy
  Trace-Lite benchmark surfaces remain regression/development-only.

The following remain explicitly deferred:

- **P-002:** exact co-occurrence degree, common-term, PPR, and query work
  budgets. Measure before choosing.
- **P-004:** valid-time, supersession, revocation, tombstone, deletion,
  historical-policy, and compliance-erasure semantics. TR1 prepares the
  decision brief; TR2 cannot claim completion before the decision.
- **P-005:** numerical release thresholds and statistical-significance method.
  Baseline evidence must precede the proposal.

If the canonical decision log does not contain these decisions, stop mutable
work and report the missing control-plane record to S0. Do not treat this file
as authority to bypass the log.

## Architectural invariants

### Spine / truth

The Spine owns source evidence, event/version history, atoms, exact character
offsets, content hashes, evidence anchors, revision relationships, temporal
validity, review state, authorization, deletion, and revocation semantics.

Everything that changes truth must be evented, anchored, policy-governed, and
recoverable. A retrieval score, graph edge, summary, embedding, or ranking
decision cannot silently alter truth.

### Cortex / projection

The Cortex owns lexical and vector indexes, hierarchy, summaries, affinity and
trusted relation projections, activation priors, routing, ranking, caches, and
other derived state. Cortex state is disposable and rebuildable.

Every derived component follows:

```text
Spine watermark -> candidate build -> integrity/provenance/policy validation
-> atomic active-release handover -> retained predecessor -> pointer rollback
```

No normal read may observe a candidate or partial release. A failed build must
be invisible, and rollback must not require reconstructing the old release.

### Evidence

Every result must be traceable to a source artifact, atom/segment identifier,
exact offsets, source hash, projection/release identity, and channel scores.
Native dataset IDs and query IDs must survive normalization. Mappings must be
reversible from query -> judgment -> evidence source -> segment/atom.

## Non-negotiable certification behavior

Certification mode must fail closed for:

- implicit or injected mock LLM/provider;
- unavailable or unpinned provider/model;
- missing, unadmitted, or checksum-mismatched dataset;
- synthetic dataset generation or fallback fixtures;
- insecure TLS or certificate bypass;
- swallowed indexing/query errors;
- forced flat-search or hidden fallback;
- editable local source import instead of a pinned artifact;
- unknown source identity or missing license/manifest;
- empty retrieval being interpreted as an abstention;
- missing evidence mappings or fabricated coverage;
- missing output/error receipt.

Mocks may exist only in explicitly named unit/regression modes and their
outputs must never be certification-eligible.

## Current observed risks to preserve in the work plan

- Trace-Lite graph co-occurrence currently has an all-pairs risk of
  approximately `sum C(df(term), 2)`; L1 must not silently set graph budgets or
  redesign graph generation. That belongs to TL2 after P-002.
- Trace-Lite graph rows and manifests need one candidate/active identity and
  retained predecessor behavior.
- Trace V2 affinity writes can become visible while a release is building;
  activation priors lack release scoping; external vector/lexical aliases do
  not yet share one atomic release root.
- Historical reads must not silently resolve current projections when the
  requested event is earlier. Valid-time and revocation semantics remain a
  decision-gated Trace task.
- `trace-bench` began as an unversioned external tree and has legacy fail-open
  behavior. B0/B1 must establish source identity and close every listed path.
- Existing Trace and Trace-Lite user worktrees may be dirty. Preserve them;
  use isolated worktrees and fresh external test databases.

## Repository and data boundaries

```text
Trace-Lite: C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite
Trace:      C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace
Bench:      C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench
Data:       C:\Users\anshu\AppData\Local\trace-bench-data
```

The current Trace-Lite clean implementation base is
`fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1`. The current Trace checkout is a
dirty user snapshot; T0 must pin a clean snapshot before TR1. Every session
must refresh identities before mutation and record any drift.

Do not delete, reset, clean, stash, or overwrite unknown files. Do not put raw
datasets, provider credentials, test databases, large result files, or caches
in Git or OneDrive-synchronized source directories.

## Claims and gates

The five release gates are:

1. durable memory: crash/replay, idempotency, hashes/offsets, coverage,
   rebuild equivalence;
2. self-organization: no orphan current atoms, valid topology, faithful
   summaries, incremental/full parity;
3. accurate retrieval: independent public/held-out evidence, paired ablations,
   no fallback paths;
4. fast retrieval: cold/warm latency by class, QPS, PPR work, memory, disk;
5. real scale: a real 100K text-memory corpus before any 1M claim.

Internal tests, synthetic scale data, self-descriptive fixtures, mock-provider
runs, and source-level inspection can support development but cannot certify a
gate.

## Required session behavior

Before editing, a session must:

1. read this file, `01_SESSION_PROTOCOL.md`, `04_SUBAGENT_RULES.md`, its own
   session brief, and its packet;
2. inspect the actual checkout and compare it with the packet identity;
3. verify its worktree lease, allowed paths, and verifier assignment;
4. write an input manifest before making substantive changes;
5. keep observed facts, runtime verification, proposals, and certification
   claims in separate sections;
6. leave a durable handoff even when blocked.

The coordinator controls cross-lane state. Agents may propose changes to
decisions but may not silently promote them.
