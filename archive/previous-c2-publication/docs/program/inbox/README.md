# Task Inbox

> **Status:** Contains broad-stroke foundation starter packets. Their exact
> repository revisions, allowed paths, and acceptance commands must be filled
> before mutable dispatch.

The coordinator creates one directory here per approved work packet:

```text
inbox/
  <task-id>/
    packet.md
    input-manifest.json
    handoff.md
    evidence/
```

Workers do not create ad hoc global tasks. Each packet must name its base
commit/worktree, allowed paths, inputs, acceptance evidence, and handoff
destination. Canonical program documents are updated only after review.

## Task directory lifecycle

~~~text
<task-id>/
  packet.md                 # immutable prepared packet or approved amendment
  input-manifest.json       # hashes, references, base commit, evaluator version
  working-notes.md          # optional; clearly non-canonical
  handoff.md                # worker result using the template
  verification.md           # independent review result
  evidence/                 # small reports/manifests/checksums, not raw data
  decision.md               # coordinator/human outcome when resolved
~~~

## Naming convention

Use a stable readable identifier:

~~~text
<stage>-<role>-<short-objective>-<yyyymmdd>
example: s1-eval-release-manifest-audit-20260818
~~~

## Immutable and mutable fields

The original packet and its input manifest are immutable once assigned. An
amendment adds a dated section explaining changed scope, input, authority, or
acceptance criteria. A worker must not rewrite history to make an earlier
assumption disappear.

## Evidence retention

Keep small manifests, checksums, reports, and command transcripts with the
task. Store raw corpora, secrets, enormous logs, and generated result sets in
approved external locations and reference them by safe path/identifier and
hash. A task that is rejected remains valuable negative evidence.

## Prepared starter packets

The current foundation-first starter packets live in the following directories:

- `f0a-e1-refresh-20260819/`
- `f0b-d1-refresh-20260819/`
- `f0c-repository-boundary-20260819/`
- `b1-e2a-fail-closed-runner/`
- `l1-tl1-candidate-active-lifecycle/`
- `t1-trace-cortex-release-audit/`
- `v1-v1a-integrity-verifier/`

The three `F0` packets are read-only startup work. The remaining packets are
queued broad strokes: they are not mutable assignments until the coordinator
pins current inputs, records authority, and marks them Prepared.

Older [seed-packets/](seed-packets/README.md) remain useful historical context
bundles. Do not treat them as current assignments when their source revision or
repository boundary is stale.

## Current packet map - 2026-08-19

| Packet | State | Purpose |
| --- | --- | --- |
| F0a | prepared read-only | Current evaluator/benchmark source re-anchor. |
| F0b | prepared read-only | Dataset provenance/admission record closure. |
| F0c | prepared read-only | Trace-Lite/Trace/trace-bench boundary and protected-state record. |
| V0 | prepared read-only | Verifier plan and packet-integrity review. |
| B1 | scoped | Fail-closed runner after F0a/P-007/P-008. |
| L1 | scoped | TL candidate/active lifecycle after clean base. |
| T1 | prepared read-only | Trace Cortex release/temporal audit. |
| TL2/TL3 | blocked successors | Bounded association and durable/provenance proof. |
| TR1/TR2 | blocked successors | Unified Cortex Release, then temporal/revocation. |
| B2/B3 | blocked successors | Real-data staging, then frozen certification readiness. |
| V1a/V1b | blocked successors | Runner integrity, then lifecycle/temporal verification. |
| F2 | blocked successor | Human Foundation Gate consolidation. |

## Packet artifact minimum

Every active task folder eventually contains packet, input manifest, repository
state, commands, handoff, verification, decision, evidence README/checksums,
and amendments directory. Read-only tasks may leave worktree lease absent only
when their manifest says no mutable authority. Use the templates directory; do
not create an incompatible personal format.

## Historical context

The trace-program-research-01 folder and seed-packets remain retained
historical planning/research context. They are superseded for dispatch by the
Foundation Release, current DAG amendment, Component Registry, and packets
listed above. Do not delete or silently reuse them as current implementation
authority.
