# Program Charter

> **Status:** Draft broad-stroke charter. Human direction is authoritative.

## 1. Mission

Build durable, self-organizing, evidence-grounded memory systems whose source
truth survives independently of retrieval and organization mechanisms.

Trace-Lite is the fast local proving ground. Trace is the governed, versioned,
policy-aware system that adopts only mechanisms that earn promotion.

## 2. Near-term outcomes

1. Make Trace-Lite Beta a trustworthy local reference implementation.
2. Establish real-data, fail-closed evaluation before broad quality claims.
3. Make Trace Cortex projections versioned, validated, atomically activated,
   and rollbackable.
4. Prove the 100K gate before a 1M pilot or live downstream dependency.
5. Use Reflex and Entorhinal initially as shadow/conformance consumers.

## 3. Scope

This program covers:

- Trace-Lite projection lifecycle, graph safety, retrieval evaluation, and
  local service boundary.
- Trace V2 Cortex Release lifecycle, temporal truth, typed activation, and
  production verification.
- Shared evidence-bundle contracts, real benchmark staging, and promotion
  decisions.

## 4. Non-goals for the initial program

- A wholesale Trace-Lite fork into Trace.
- Public SOTA claims from internal or synthetic-only benchmarks.
- An autonomous agent that changes architecture, evaluators, or main branches.
- Scaling to 1M or beyond before the real 100K proof gate.
- Making affinity, summaries, or query-time activation authoritative truth.

## 5. Authority model

The human program owner decides direction, accepts architecture decisions, and
authorizes promotions. The coordinator compiles evidence and creates bounded
work packets. Workers may investigate, implement in isolated worktrees, and
recommend actions; they may not expand scope or merge themselves.

## 6. Success definition

Success is not a single benchmark number. It is a repeatable loop in which a
useful memory mechanism can be:

1. proposed,
2. evaluated on real evidence,
3. constrained by provenance, policy, recovery, and cost,
4. activated atomically,
5. rolled back safely, and
6. retained or rejected with a durable record of why.

## 7. Strategic model

The program is deliberately asymmetric:

| System | Primary responsibility | What it should optimize |
| --- | --- | --- |
| Trace-Lite | Fast local experimentation and trustworthy embedded reference behavior. | Iteration speed, evidence preservation, bounded retrieval, developer ergonomics. |
| Trace | Governed, versioned, policy-aware memory infrastructure. | Truth, recovery, temporal semantics, release control, tenancy/policy, scalable operations. |
| Evaluation layer | Independent measurement and certification. | Reproducibility, no hidden fallbacks, useful ablations, honest claim boundaries. |
| Consumers | Real task pressure and conformance feedback. | Stable evidence semantics without surrendering their own authority. |

The unit of transfer is a **measured mechanism** with a promotion dossier. It
is not a repository, a database schema, a graph shape, or a benchmark slogan.

## 8. Capability claim levels

Every status report must identify its claim level:

| Level | Meaning | Minimum evidence |
| --- | --- | --- |
| C0 — idea | A plausible design or research hypothesis. | Problem statement and falsifiable experiment. |
| C1 — local behavior | A feature works in a controlled developer fixture. | Targeted tests and explicit limitations. |
| C2 — regression evidence | Behavior is stable against a frozen internal fixture. | Reproducible internal run and baseline. |
| C3 — credible retrieval evidence | It performs on pinned real/public or held-out data. | Fail-closed manifest, paired baselines, query-level evidence. |
| C4 — operational evidence | It survives recovery, faults, and bounded real-corpus load. | Recovery and workload reports with resource/cost data. |
| C5 — promoted infrastructure | It is governed, observable, rollbackable, and adopted selectively. | Accepted promotion dossier and Trace release evidence. |

Workers must not use a higher-level label than their evidence supports.

## 9. Milestone definitions

### M0 — Program control plane

The charter, invariants, task packet, evaluation boundary, role contracts, and
decision/risk logs are reviewed. This milestone creates no product claim.

### M1 — Trace-Lite lifecycle readiness

Candidate-versus-active derived state, graph bounds, source fidelity,
organization validation, and failure retention are defined and independently
tested. M1 is a prerequisite for a credible scale run, not a scale result.

### M2 — Evaluation readiness

The required public/held-out dataset records, transforms, release manifest,
fallback assertions, baseline matrix, and result schema are ready for review.

### M3 — TL real 100K gate

The five proof areas have measured real-corpus evidence:

- durable headless memory,
- self-organization correctness,
- accurate retrieval,
- latency/resource behavior by query class,
- recovery/cost at 100K source atoms.

### M4 — Trace promotion readiness

Trace has a validated Cortex Release lifecycle and receives only a mechanism
whose dossier meets the promotion rubric.

### M5 — 1M pilot and consumer shadowing

The 100K evidence has been accepted, a bounded 1M design exists, and consumers
exercise the stable contract in shadow mode. This is not broad autonomous or
irreversible adoption.

## 10. Direction-change protocol

A direction change is required before work that would:

- alter a program invariant,
- make a new external dependency canonical,
- expose a new consumer to raw storage or credentials,
- authorize real data with uncertain license/privacy status,
- change a release threshold or evaluator after seeing candidate results,
- delete or migrate material user data,
- expand from a bounded 100K/1M plan into distributed-scale commitments.

The coordinator records the proposal, alternatives, evidence, affected DAG
nodes, and rollback implications. The human owner decides whether to accept it.
