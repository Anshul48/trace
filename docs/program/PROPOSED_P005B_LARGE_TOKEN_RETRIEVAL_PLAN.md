# Proposed P-005b: Large-Token Retrieval Readiness Plan

> **Status:** Proposed, planning-only. This document neither amends DEC-P-005
> nor closes, reopens, or promotes any existing Foundation, 100K, 1M, or human
> gate. Only the program owner may accept the proposed amendment and promotion
> decisions described here.
>
> **Purpose:** Give Trace a credible path to *fast enough and accurate enough*
> evidence-grounded retrieval over a realistically large token corpus. The
> immediate objective is a trustworthy 100K real-corpus proof and a measured
> 1M pilot, not a claim of universal SOTA, a broad language rewrite, or a
> distributed system.

## 1. Executive judgment

**Recommendation: amend P-005 deliberately, rather than retain its current
GPU/RAM clause unchanged.** Keep every durability, provenance, bounded-work,
storage, recovery, and retrieval-quality bar intact. Replace the single,
ambiguous hardware clause with two explicitly labelled evidence profiles:

1. a **reference-capacity profile** that proves the system functions on the
   intended 16 GiB-class local machine without memory pressure; and
2. an **accelerated-throughput profile** that proves a measured GPU-assisted
   build is genuinely faster, without allowing that result to be relabelled as
   CPU performance or as the only proof of viability.

The recorded 100K dossier currently reports 277.46 docs/s and 4425.9 MB peak
RAM while also identifying a CUDA-capable GPU. Its raw runner, raw corpus
capsule, and raw telemetry must be recovered or recreated before it can support
any gate claim. That is a reconciliation fact, not a reason to quietly lower a
threshold or retroactively classify the run.

The architecture decision is therefore modest:

- measure scale in source tokens, active atoms, bytes, updates, queries, and
  tail latency; keep documents/second as a secondary descriptive metric;
- retain Python while contracts and computational shape are still changing;
- make input manifests, telemetry, bounded retrieval, and replay the immediate
  engineering work; and
- extract only a proven hot path to Rust, Go, Julia, or a GPU kernel after a
  real profile demonstrates that doing so is material to the next accepted
  gate.

This is stricter than a benchmark-only plan: it requires real data, exact
source evidence, recovery, and independent reproduction. It is also more
practical than a premature perfection program: it asks for non-regression and
mechanism-specific benefit on the intended query classes, not an immediate
claim to win every benchmark or task.

## 2. Authority, scope, and current planning posture

DEC-P-005 remains binding until a human owner accepts an amendment. Its existing
quality floors, statistical methods, storage multiplier, graph degree,
walk-depth, and execution-time bounds remain unchanged by this proposal.

This plan may prepare evidence, contracts, data capsules, runners, and repair
packets immediately. It may not:

- record DEC-P-005b, Gate C, or any other human acceptance on the owner's
  behalf;
- treat a summary, checksum of a summary, or worker-authored handoff as an
  independent scale result;
- use synthetic data, mock providers, forced values, unavailable-data
  fallbacks, or relabelled hardware modes for a qualifying run;
- authorize 1M execution merely because a 1M architecture plan exists; or
- begin a whole-system language rewrite, distributed deployment, or new
  hardware procurement as a substitute for the evidence below.

For this program, any prior claimed Foundation, 100K, or Gate-C outcome is
treated as **unreconciled for new promotion purposes** until the reconciliation
session can bind it to executable runners, immutable data capsules, raw
telemetry, and an independent verifier attestation. This does not erase
historical documents; it prevents them from becoming unexamined authority.

## 3. What "large-token retrieval" must mean

A headline document count is not enough. Every calibration, 100K gate, and 1M
pilot must freeze the following workload vector in a signed manifest.

| Symbol | Required declaration | Why it matters |
| --- | --- | --- |
| T | Source-token count and tokenizer name/version | Makes token-scale claims comparable. |
| B | Raw source bytes and compressed bytes | Exposes amplification and I/O cost. |
| D | Document count and document-size distribution | Prevents a uniform tiny-document corpus from standing in for real text. |
| N | Atom/chunk count, tokenizer ranges, and atom-size distribution | Defines the actual indexable retrieval unit. |
| A | Active indexed atoms/tokens and archive fraction | Separates online retrieval from retained cold source. |
| U | Ingest, update, delete/revocation, and replay rates | Tests incremental economics instead of one static build. |
| Q | Query concurrency and query-class mix | Makes latency and QPS interpretable. |
| L | Cold/warm p50, p95, p99 by query class | Prevents idle means from becoming a latency claim. |
| R | Crash, replay, rebuild, rollback, RPO/RTO targets | Keeps durability part of scale proof. |
| P | Policy, retention, temporal, and evidence requirements | Ensures fast retrieval never bypasses truth or access controls. |
| C | Host RAM, VRAM, disk, CPU/GPU, and elapsed-cost envelope | Lets later hardware comparisons remain honest. |

The 100K label must additionally state whether it is 100K documents, atoms, or
another unit. The qualifying target for this plan is **at least 100K real source
atoms after the declared transform**; the manifest must also report D, T, and B.
A document-only count never substitutes for the atom count.

## 4. Proposed P-005b decision package

The owner has one decision: **retain P-005 unchanged, or accept the following
P-005b amendment as written.** The recommended choice is the amendment.

### 4.1 Proposed amendment text

P-005b changes only the early-scale hardware and resource-accounting clause of
P-005. It does not relax the existing quality, truth, recovery, graph, or
storage requirements.

| Topic | Proposed P-005b rule | Rationale |
| --- | --- | --- |
| Core qualifying environment | **R16:** a declared 16 GiB host-RAM reference machine. The qualifying timed phase has no OOM, allocator retry loop, or observed active paging. | A real local-machine capacity proof should be feasible while retaining substantial headroom. |
| Host-memory bound | Peak **program-owned process-tree RSS** is **<= 8 GiB** for a 100K gate under R16. Report process RSS, child-process RSS, service RSS/PSS where available, commit charge, and OS cache separately. | The former 2.0 GB bound is inconsistent with a realistic end-to-end 100K projection stack; 8 GiB leaves half of a 16 GiB system available for the OS and operational headroom. |
| CPU throughput profile | **C:** retain **>= 150 docs/s**, with source tokens/s, atoms/s, bytes/s, and document-size distribution reported alongside it. GPU use must be disabled or absent for this classification. | Preserves the prior CPU floor while preventing document size from hiding work. |
| Accelerated throughput profile | **A6:** retain the **>= 500 docs/s** target only when GPU counters show actual use in the declared embedding/index path; peak VRAM remains **<= 6 GiB**. Source tokens/s, atoms/s, and bytes/s are co-primary metrics. | A useful accelerator result remains a meaningful performance target, but it is not confused with the core capacity proof. |
| Faster hardware | A result on more RAM, more VRAM, or a faster GPU is a separately named hardware profile. It may demonstrate throughput/capacity, but cannot satisfy R16, C, or A6 by substitution. | Prevents an upgrade from retroactively validating the reference claim. |
| Primary scale metrics | Every report leads with T, N, B, tokens/s, atoms/s, p50/p95/p99, QPS, build/rebuild time, storage amplification, and resource scope. Docs/s remains supplemental. | Directly measures the large-token objective. |
| Quality at scale | Retain P-005 absolute public-lane floors. On declared scale query packs, require a pre-frozen paired comparison: the lower 95% bootstrap bound for candidate minus baseline is **>= -0.010** on the primary metric, and no target query class regresses by **>= 0.030**. A promoted optional mechanism still needs the existing P-005 practical-benefit rule (**>= +0.030** or Cohen's d **>= 0.20**) on its intended class. | Core viability needs no material regression; an added graph/router/reranker must still earn its complexity. |
| Existing hard bounds | Retain 100% source retention, 0% hash drift, exact offset recovery, repeat-erasure delta 0, orphan/purity requirements, storage **<= 3.0x**, graph degree **<= 50**, depth **<= 15**, and graph execution **<= 35 ms**. | These are correctness and bounded-work constraints, not hardware tuning knobs. |

P-005b must retain P-005's alpha (0.01), paired tests, 10,000-bootstrap
confidence intervals, denominator accounting, public benchmark floors, and
failure-closed behavior. If the owner retains P-005 instead, all sessions below
remain valid, but a qualifying 100K result must meet the original <= 2.0 GB
peak-RSS clause and its unambiguous accelerated/CPU classification.

### 4.2 Required decision record fields

The eventual human decision record must include, verbatim or equivalently:

1. choice: retain_p005 or accept_p005b;
2. the selected resource-profile table and numerical values;
3. statement that no existing 100K result is grandfathered;
4. statement that a faster GPU is an additional named profile, not a substitute
   for the accepted reference profile;
5. a named owner and date; and
6. the exact next packet that becomes eligible.

No worker may generate an "accepted" status for this record. A coordinator may
only store the owner's supplied decision.

## 5. Definition of a credible retrieval result

### 5.1 Query lanes

Every qualifying run must execute the frozen lane mix below, reporting each lane
separately. A high direct-lookup result never masks a poor multi-hop, negative,
temporal, or policy-safe result.

| Lane | Minimum evidence question | Required comparison |
| --- | --- | --- |
| Direct/evidence lookup | Can an exact source or distinctive passage be found and cited? | Lexical baseline and Trace candidate. |
| Semantic/domain retrieval | Can semantically related evidence be found without exact wording? | Dense/hybrid baseline and Trace candidate. |
| Multi-hop/compositional | Are all required supporting atoms retrieved under explicit graph/routing budgets? | Graph/routing-off ablation and bounded candidate. |
| Negative/abstention | Does Trace refuse unsupported retrieval rather than manufacture evidence? | Fixed abstention policy and unsupported-query pack. |
| Temporal/policy | Does the answer respect source revision, visibility, revocation, and access policy? | Current/revoked/historical fixture pairs. |
| Scale/load | Does the same system preserve tail latency and evidence under declared concurrency? | Cold and warm schedules at each load level. |

Use the existing admitted public lanes for external retrieval evidence and a
separate real 100K/1M corpus with a frozen scale-query pack. Add a held-out,
consented-private lane only if its access controls, retention policy, and
independent outcome owner are documented. Public and private results are
reported separately.

### 5.2 Baseline and ablation rules

Before the candidate run, freeze:

- a simple lexical baseline;
- the best permitted dense or hybrid baseline under the same corpus, query,
  hardware profile, and time budget;
- the Trace candidate configuration; and
- one-at-a-time ablations for each promoted complexity: graph expansion,
  routing signal, reranker, hierarchy, or model tier.

The evaluator owns baseline implementations, query pack, judgments, scoring,
and statistical scripts. The implementation worker cannot edit those artifacts
after the candidate identity is frozen. A candidate that wins only with more
hardware, hidden query filtering, an unavailable fallback, or an altered corpus
is exploratory evidence, not a causal retrieval result.

### 5.3 Latency and work accounting

Each query log must show:

- cold versus warm status and cache state;
- query class, concurrency, deadline, and outcome;
- candidate shard/partition count, vector/lexical candidates, graph nodes and
  edges touched, rerank/model calls, bytes read, and remaining budget;
- source revision, policy context, active release identity, and evidence offsets
  for returned results; and
- p50, p95, and p99 over a predeclared denominator, plus failed and excluded
  query counts.

For a single-node 100K run, the same accounting is required even before shards
exist. This avoids creating a local-only query path that cannot later prove
bounded routing.

## 6. Evidence architecture and minimum artifact set

All qualifying results must be reproducible from retained artifacts rather than
from prose summaries. The following paths are proposed conventions; each packet
may refine the path, but not omit the artifact.

~~~text
docs/program/inbox/<packet-id>/
  packet.md                         # scope, authority, prerequisites
  input-manifest.json               # immutable identities of all inputs
  repository-state.json             # commit and dirty-tree disposition
  worktree-lease.json               # mutable packets only
  commands.md                       # exact commands, no reconstructed log
  handoff.md                        # observed vs verified claim boundary
  evidence/
    corpus-manifest.json            # source/license/hash/transform/tokenizer
    workload-manifest.json          # T/B/D/N/A/U/Q/L/R/P/C vector
    candidate-manifest.json         # code/config/model/release identities
    baseline-manifest.json
    environment.json                # OS, drivers, CPU, RAM, GPU, disk
    telemetry/                      # raw time series, process tree, GPU, I/O
    query-results/                  # query-level, aggregate, exclusions
    recovery/                       # fault, replay, rebuild, rollback traces
    checksums.json                  # hashes of retained evidence
    verifier-attestation.json       # verifier-owned only
~~~

The scale runner must fail closed before execution if any required manifest,
dataset hash, model/configuration fingerprint, hardware-profile declaration, or
telemetry collector is absent. It must write a structured failure classification
instead of substituting a demo corpus, cached result, or different backend.

### 6.1 Telemetry requirements

The runner and verifier collect raw values, not only a final average:

| Area | Minimum raw evidence |
| --- | --- |
| Ingest/build | Start/end timestamps, docs/tokens/atoms/bytes processed, batch sizes, failures/retries, CPU/GPU utilization, disk and network I/O. |
| Memory | Parent/child/service process RSS or PSS, commit charge, allocator metrics if available, GPU allocation/utilization, and sampling cadence. |
| Storage | Raw source, event log, projection/index, snapshot, WAL/cache, and total bytes; identify excluded temporary files. |
| Retrieval | Query-level timing and work counters, cache state, result/evidence IDs, failure/exclusion reason, and aggregate quantiles. |
| Lifecycle | Candidate build identifier, validation result, activation pointer, rollback result, and visibility checks. |
| Recovery | Crash point, durable watermark, replay count/rate, rebuilt release identity, parity check, and elapsed RTO. |

The resource receipt must declare whether RAM includes embedded services,
separate database/index processes, caches, and the evaluator. The qualifying
R16 figure is the program-owned **product process tree**; evaluator-only
overhead is reported separately. This prevents both double-counting and hiding
an external index behind a different process.

## 7. Execution waves and gates

Run one bounded packet DAG at a time. A failed implementation never turns into a
verifier repair; it produces a narrow failure packet, a new frozen candidate,
and a new independent verification session.

### Wave R0 — Reconcile before relying on downstream claims

| ID | Owner / role | Start condition | Deliverable | Exit or stop rule |
| --- | --- | --- | --- | --- |
| LTR-00 | S0 coordinator, read-only | Start alone | Gate-truth reconciliation record, artifact inventory, missing-evidence list, and exact resumption node | Stop as needs-review on contradictory decision/receipt identities, missing runner, missing raw dataset/telemetry, or unresolved V1b/Foundation evidence. It cannot repair or promote. |
| LTR-01 | S6 evaluator + lead architect, planning | LTR-00 facts frozen | P-005b decision brief, profile definitions, and this plan's numeric appendix | Stop if a proposed rule silently changes quality/invariant/recovery semantics. |
| **Human Gate B2** | Program owner | LTR-01 supplied | Signed retain_p005 or accept_p005b decision | No candidate scale run proceeds under an unrecorded choice. |

LTR-00 is deliberately conservative: if prior results have all required raw
evidence and an independent attestation, it may reference them. If not, it
labels them development evidence and directs the program to reproduce them; it
does not edit historical handoffs to make them look complete.

### Wave R1 — Make a 100K result executable and independently reproducible

| ID | Owner / role | Prerequisites | Deliverable | Exit or stop rule |
| --- | --- | --- | --- | --- |
| LTR-02 | S4 data curator | B2 choice; data authority | Real corpus and query/judgment capsules with hashes, licenses, transforms, token/atom distributions, and no-fallback declaration | Missing license, hash, atom mapping, or holdout isolation is a data failure. |
| LTR-03 | S7 implementation | B2 choice; LTR-02 schema | Canonical scale runner and telemetry adapters in a clean implementation worktree | Runner must resolve only immutable manifests, emit the complete artifact set, and fail closed. No qualifying benchmark claim. |
| LTR-04 | S5 independent verifier | Frozen LTR-03 candidate and read-only LTR-02 capsule | Runner-integrity attestation on a fresh verifier worktree | Stop on mutable-source import, unpinned dependency, missing raw telemetry, fallback, or identity mismatch. The verifier does not patch it. |
| LTR-05 | S7 implementation | LTR-04 pass | 10K/25K calibration evidence under R16 and, if available, A6 | Diagnostic only. It discovers bottlenecks and validates instrumentation; it does not promote scale. |
| LTR-06 | Lead architect + evaluator, read-only | LTR-05 artifacts | Bottleneck attribution and one narrow repair packet | Stop and request an architecture decision if the remedy would change truth, release, policy, workload, or partition semantics. |
| LTR-07 | S2/S3/S7 repair implementation | Accepted narrow repair packet | One frozen repair candidate plus local implementation checks | Exactly one declared failure class and write scope. No threshold/evaluator/manifest edits. |
| LTR-08 | S5 independent verifier | Frozen LTR-07 candidate | Repair verification attestation or signed failure packet | A failure returns to LTR-06; it never continues directly to 100K. |

LTR-05 through LTR-08 may repeat only as explicit repair loops. Each loop must
retain its failure evidence, use a new candidate identity, and re-run an
independent verification. If two loops point to the same architectural cause,
the coordinator stops and asks for a focused architecture decision rather than
accumulating patches.

### Wave R2 — Establish the real 100K gate

| ID | Owner / role | Prerequisites | Deliverable | Exit or stop rule |
| --- | --- | --- | --- | --- |
| LTR-09 | S6 evaluator | Verified runner/corpus candidate | Frozen baseline, ablation, fault, statistical, and load schedules; query-pack identities | Any change after the candidate run begins invalidates the paired comparison. |
| LTR-10 | S7 implementation/run operator | LTR-08 pass and LTR-09 freeze | Candidate 100K run with raw evidence only | A resource, quality, provenance, or recovery failure is a failed candidate run, not a partial pass. |
| LTR-11 | S5 independent verifier | Frozen candidate bundle, read-only protocol/data, separate worktree and result root | Independent reproduction of required lanes, fault matrix, and result attestation | Stop on any data/configuration/hardware-profile mismatch. No source edits or packet reclassification. |
| LTR-12 | S0 coordinator + S6 evaluator | LTR-11 attestation | Evidence dossier and promotion recommendation with residual limitations | The dossier can recommend; it cannot record Gate C or call 1M authorized. |
| **Human Gate C2** | Program owner | Complete LTR-12 dossier | Explicit promote_100k, repair, reject, or defer decision | Only promote_100k permits a 1M plan. A verifier pass alone is not promotion. |

### Wave R3 — Build a measured 1M pilot, not a headline claim

| ID | Owner / role | Prerequisites | Deliverable | Exit or stop rule |
| --- | --- | --- | --- | --- |
| LTR-13 | S7 scale architect | Human promote_100k | 1M workload/capacity architecture plan using measured 100K coefficients | It must state whether 1M is single-node, multi-process, or requires a new architecture decision. No execution authority yet. |
| **Human Gate D** | Program owner | LTR-13 plan | Authorization, hardware profile, cost envelope, and 1M claims allowed | The owner may authorize only planning, only a pilot, or neither. |
| LTR-14 | S7 implementation/run operator | Gate D pilot authorization | 1M candidate run with update/delete/replay/load evidence | Whole-corpus work for a small update, unbounded work, or unsustainable memory/backlog is a failed pilot. |
| LTR-15 | S5 independent verifier | Frozen LTR-14 bundle | Independent F2 verification and limitation report | A 1M pass proves only the declared single-node/single-region workload, never 10B or distributed readiness. |
| LTR-16 | S0 coordinator + owner | LTR-15 result | Human-ready F2 dossier and next-scale decision recommendation | Any 10M+/10B work requires a new scale architecture decision record. |

## 8. What must change before the next qualifying 100K run

The following are required engineering outcomes. They are intentionally framed as
contracts and observability work, not a speculative data-plane rewrite.

| Priority | Change required now | Acceptance evidence |
| --- | --- | --- |
| Must | Restore or create one canonical real-corpus runner whose implementation is versioned and retained. | Fresh-worktree verifier can execute the runner from only its declared inputs. |
| Must | Add signed corpus, transform, tokenizer, query/judgment, candidate, and hardware manifests. | Hashes and identities match at runner start; any mismatch stops before results. |
| Must | Add process-tree, GPU, storage, I/O, latency, and bounded-work telemetry. | Raw sampled traces exist and aggregate values can be recomputed from them. |
| Must | Make cold/warm query profiles, baseline, ablations, and statistical script fixed before candidate execution. | Query-level artifacts show denominators, slices, and all failures/exclusions. |
| Must | Prove candidate build/validation/activation, crash/replay/rebuild, rollback, and source/evidence parity at load. | Fault receipts include exact watermark, rebuilt release identity, and parity result. |
| Must | Audit the ingest/index path for whole-corpus materialization, unbounded graph construction, and unbounded query expansion. | Counters show bounded batch/window/candidate/degree/depth work and controlled memory. |
| Conditional | Convert ingestion/projection work to streaming batches, checkpointed outbox processing, and incremental index fragments if the profile identifies whole-corpus memory or rebuild cost. | Same corpus/query manifest demonstrates lower bounded resource or recovery cost with no quality regression. |
| Conditional | Tune GPU dynamic batching, tokenization parallelism, encoding format, vector/index parameters, or cache policy only behind frozen configurations. | Paired test shows material benefit in its stated profile and no semantic/provenance divergence. |
| Deferred | Extract a native kernel, start multi-process/shard routing, or move to a faster GPU. | Requires a measured bottleneck, stable contract, explicit migration/parity plan, and a new approved packet. |

No code change should remove existing functionality merely to simplify the
benchmark. Every repair is additive or reversible, with source truth and the
last validated release retained throughout the candidate lifecycle.

## 9. Fault, durability, and recovery matrix

The 100K and 1M verification schedules must include at least these cases. Each
row needs an injected point, expected result, raw trace, and an explicit
pass/fail classification.

| Case | Injection point | Required outcome |
| --- | --- | --- |
| Ingest interruption | During a non-final batch | Canonical committed source is retained; replay resumes from a declared watermark; no duplicate/lost atoms. |
| Projection failure | Candidate build before activation | Candidate is invisible; previous active release stays queryable. |
| Activation interruption | Between validation and release-pointer update | Exactly one valid active release is visible after recovery. |
| Index/service restart | During load | Restart/reconnect is visible in telemetry; recovery honors the declared policy and release. |
| Source deletion/revocation | After projection/index build | Affected evidence becomes inaccessible as required; repeat erasure remains delta 0. |
| Corrupt/stale candidate | Before a query or activation | Direct validation rejects it; query fails visibly or uses the last valid release only under the declared policy. |
| Full replay/rebuild | Fresh process/index state | Rebuilt release has measured parity with the accepted canonical/source manifest. |
| Resource pressure | Near the accepted RAM/VRAM/disk envelope | System fails closed or backpressures within its declared behavior; it does not silently discard evidence or switch backends. |

## 10. Hardware and language evolution policy

### 10.1 Hardware

The reference proof and a faster machine answer different questions.

| Profile | Claim it may support | Claim it may not support by itself |
| --- | --- | --- |
| R16 | Practical local capacity, resource envelope, quality, recovery, and tail behavior on the reference host | High-end accelerator throughput or future distributed capacity |
| C | Declared CPU throughput on the exact reference machine | GPU acceleration or another machine's results |
| A6 | Declared RTX-5050-class GPU throughput/VRAM behavior | CPU-only performance or a larger-GPU result |
| H* | Exploratory or additional capacity/throughput evidence on explicitly described faster hardware | Compliance with any other profile without a rerun |

A faster GPU is valuable when it improves a measured embedding, batching,
routing, reranking, or build bottleneck. It is not evidence that the architecture
has bounded memory, correct recovery, source fidelity, or large-token retrieval
quality. Every new hardware profile must repeat the relevant fixed protocol and
report its exact environment.

### 10.2 Native components

Before authorizing Rust, Go, Julia, CUDA, or another native extraction, require
all of the following:

1. at least three retained real-corpus profiles identify the same dominant hot
   path or operational bottleneck;
2. the path has stable input/output, error, cancellation, resource, and
   observability semantics;
3. a reference implementation and golden fixture suite can compare source IDs,
   atom ranges, policy behavior, release identity, and evidence output;
4. the expected gain is material to the next accepted gate, rather than merely
   aesthetically faster; and
5. a reversible adapter/migration keeps the existing reference path available
   until independent parity verification passes.

Likely choices are deliberately narrow:

- **Rust:** compact encoding/hashing, source/atom transforms, projection
  serialization, memory-sensitive batch workers, or a bounded graph kernel.
- **Go:** a later high-concurrency router, worker supervisor, or network-facing
  service after the shard boundary is accepted.
- **Julia:** research/prototyping for a numerically intensive algorithm only if
  it has a clean, reproducible worker boundary; it is not a default serving
  rewrite.
- **Faster GPU/CUDA:** embedding, batch tokenization, candidate scoring, or
  reranking only after a profile shows that exact stage dominates.

Do not use a new language to compensate for a global graph, all-pairs build,
full-corpus update, uncontrolled fan-out, missing evidence, or unclear release
semantics. Fix computational shape first; optimize the measured bottleneck
second.

## 11. 1M pilot design constraints

The 1M plan is written only after a valid human 100K promotion and uses actual
100K measurements to estimate capacity. It must answer these questions before a
run is authorized:

1. What are T, N, A, B, query mix, update/delete rate, and document/atom
   distributions at 1M?
2. Which measured components grow linearly, sublinearly, or superlinearly from
   100K to 1M? Publish the fit and uncertainty rather than a single projection.
3. Can a single R16, another named host, or a small single-region deployment
   hold the active set with recovery headroom? If not, identify the exact
   pressure: RAM, VRAM, disk, build time, replay, queue lag, or tail latency.
4. Does each small update affect only bounded projection fragments and bounded
   candidate releases, rather than trigger a corpus-wide rebuild?
5. What is the bounded routing/candidate plan if the active index is
   partitioned? Logical source identity remains independent of physical
   placement.
6. How do source revisions, policy/revocation, activation pointers, snapshots,
   rollback, and evidence bundles remain reconstructible?

The first 1M pilot may remain a strong single node or a small single-region
multi-process deployment. It is successful only for the recorded configuration.
It is not a distributed, 10B-token, or trillion-token result. A 10M-50M atom
shard pilot requires a new Scale Architecture Decision Record with partition,
routing-oracle, recovery, cost, and independent-evidence design.

## 12. Handoff, verification, and repair contract

Every packet in this plan uses a prepared packet, isolated worktree, immutable
base identity, exact allowed paths, and a named verifier. Its handoff must
separate:

- implemented, implementation-checked, independently verified, and promoted
  statements;
- observed measurements from recomputable raw evidence;
- product-owned paths from verifier-owned result paths;
- passed checks from failures, exclusions, limitations, and open questions; and
- the one next allowed packet from speculative future work.

The independent verifier starts from a frozen candidate, uses its own clean
worktree and result root, and may write only verifier artifacts. It stops on an
identity mismatch, missing data/telemetry, fallback, evaluator drift, candidate
leakage, or missing recovery evidence. Its only failure output is a signed,
narrow repair request.

The coordinator may assemble a dossier but cannot invent a human approval. A
human promotion always records the exact claim, hardware profile, evidence
identities, residual limitations, and the only newly authorized successor.

## 13. Immediate next actions

1. Create LTR-00 as a read-only reconciliation packet. It should inventory the
   claimed 100K/1M artifacts, runner availability, raw corpus/query data, raw
   telemetry, V1b/Foundation prerequisites, and decision provenance.
2. In parallel, create LTR-01 as a planning-only P-005b decision brief using
   the proposed text in section 4. Do not edit the decision log yet.
3. The owner selects retain_p005 or accept_p005b. The recommended choice is
   accept_p005b.
4. After the choice is recorded, prepare LTR-02 through LTR-04; do not run a
   qualifying 100K candidate until runner integrity and the real-data capsule
   independently pass.

That sequencing preserves velocity: data, runner, observability, and protocol
work can begin immediately, while the one human decision prevents an ambiguous
hardware result from becoming an ambiguous scale claim.

