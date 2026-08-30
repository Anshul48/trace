# Scale Certification Recovery Plan

> **Status:** Draft, planning only.
>
> **Prepared:** 2026-08-28 against observed head `f74767e`.
>
> **Authority boundary:** This document authorizes neither a data download,
> provider call, benchmark execution, 100K/1M claim, promotion, nor a human
> decision. It defines the bounded work and evidence required before any of
> those actions can be proposed.

## 1. Purpose and current truth boundary

The immediate problem is not performance tuning. It is that runnable benchmark
scripts have emitted certification-shaped reports without proving the workload
they describe. The 1M result JSON files were removed by `f74767e`, but the
underlying scripts remain in the checkout and can still produce misleading
claims. The current 100K runner also requires requalification before its
historical reports can be used as a predecessor for 1M work.

For the execution of this plan, every prior 100K or 1M result is
**unconfirmed** until its frozen inputs, code identity, raw evidence, and
independent verification are reconciled. This is an operational classification
for the recovery work; it does not rewrite a human decision record.

The two levels are strictly sequential:

1. **Level 1 — requalify a truthful 100K real-corpus gate.**
2. **Level 2 — execute and independently verify a bounded 1M pilot only after
   an explicit human 100K promotion decision.**

No 10M, consumer-shadow, or broad cognitive-capability claim follows from
either level.

## 2. Facts this plan addresses

The following are observed code and artifact defects, not hypotheses:

| Surface | Observed defect | Required correction |
| --- | --- | --- |
| `scripts/run_1m_scale_gate.py` | The claimed ingestion loop only updates Python collections; it does not insert its million documents into the SQLite event store. It also repeats input sources until it reaches a target counter. | Replace it with a real, durable ingestion path and prove committed unique source records from the database. |
| Same 1M runner | Retrieval, durability, and recovery outcomes include literals or timing-only calculations. Graph timing uses only a prefix of entities and edges. | Measure each declared operation against its actual persisted projection; store query/fault traces and recompute aggregates. |
| `scripts/benchmark_1m_hybrid_comprehensive.py` | It falls back to an in-memory store, seeds a self-authored landmark corpus, judges answers by expected-keyword presence, and always writes `PASS_AND_CERTIFIED`. | Make the hybrid evaluator read-only, corpus-backed, judgment-backed, and unable to assign a certification status. |
| `scripts/run_100k_scale_gate.py` | It floors retrieval scores above a threshold, emits literal abstention metrics, declares an overall pass unconditionally, and replays only a bounded event prefix into an unrelated table. | Recompute metrics without score floors, validate abstention from frozen judgments, and perform a full declared replay/rebuild with state parity checks. |
| Checkpoints and reports | A Git commit and a JSON file are content snapshots, not live-run attestations. The deleted 1M checkpoint had no source selection hash, event watermark, DB snapshot hash, or signature. | Bind every run to a signed, immutable evidence manifest and an independently generated attestation. |

The current external 1M database and deleted reports are forensic inputs only.
Do not delete, reuse, or “top up” that database as a candidate spine without a
separate owner-approved retention decision.

## 3. Common containment wave (R0)

Level 1 cannot begin a candidate run until this containment wave is complete.
The work is deliberately small, read-mostly, and reversible.

| ID | Owner | Deliverable | Acceptance and stop rule |
| --- | --- | --- | --- |
| R0-01 | Coordinator | Claim inventory listing every 100K/1M assertion, commit, report, external path, and current status. | Preserve invalid artifacts by hash and Git object ID. Do not erase history or external data. Missing provenance is recorded as missing, not reconstructed. |
| R0-02 | Implementer | Narrow quarantine change for the three unsound scripts. | They must not emit `PASS`, `CERTIFIED`, or write to canonical result paths. Until replaced, they may run only under an explicit `diagnostic` mode whose output says non-certifying. |
| R0-03 | Custody owner | Read-only forensic manifest for the existing external databases and result roots. | Record path, size, SHA-256 of a quiescent snapshot if one can be safely obtained, SQLite integrity result, table counts, and access time. Never mutate the original while auditing it. |
| R0-04 | Coordinator | Reconciliation packet comparing the current source tree, decision log, status page, prior packets, and raw artifacts. | Contradictions remain visible. The packet distinguishes “reported”, “reproduced”, “independently verified”, and “human approved”. |
| R0-05 | Human owner | A short decision naming the canonical certification boundary and allowed result root. | Reconfirm or explicitly amend P-007/P-008. No in-repo convenience script becomes a certification runner by implication. |
| R0-06 | Verifier | Negative-integrity test packet. | Demonstrate that missing data, an in-memory fallback, a seeded landmark, a hard-coded metric, a missing attestation, or a mutable input produces a fail-closed result. |

### R0 non-negotiable rules

- Preserve false reports as revoked evidence in Git history; never relabel them
  as a passing result or overwrite them with corrected numbers.
- Disable automatic cloud-model opt-in. A certification runner must not set a
  cloud permission variable, choose a default model, or silently use an
  available credential.
- A missing database must fail preflight. It must never select `:memory:`,
  a default store, a sample corpus, or a previous result.
- A benchmark may not seed facts, answers, source anchors, schemas, or graph
  edges into the database it evaluates.
- A broad `except` may record a structured failure receipt, but must not skip
  input, reinterpret failure as abstention, or continue to a successful score.
- Result directories are verifier-owned or candidate-owned and immutable after
  completion. Raw corpus bytes stay outside Git; manifests and content hashes
  are retained in Git.

## 4. Shared certification contract

### 4.1 Units that must never be conflated

Every run reports all of the following separately:

| Symbol | Meaning | Minimum proof |
| --- | --- | --- |
| D | Unique canonical source documents after the frozen selection rule. | Native source ID plus content hash, with no duplicate pair. |
| A | Active atoms derived from D by the frozen transform. | Atom count, source-document mapping, content hash, and lifecycle state. |
| E | Committed Spine events. | Contiguous per-stream sequence, event ID, idempotency key, and payload hash. |
| R | Candidate or active projection release. | Input watermark, component revisions, validation receipt, and activation state. |
| Q | Evaluated query/judgment cases. | Frozen query ID, relevance/abstention judgment, exclusions, raw result, and timing. |

“1M” means exactly 1,000,000 unique D records unless a human decision states a
different unit in advance. It must not mean one million loop iterations, atoms,
token equivalents, repeated texts, or an approximate target counter.

### 4.2 Run-state machine

Use one schema-enforced state field, with transitions recorded in an append-only
claim ledger:

| State | Who may create it | Meaning |
| --- | --- | --- |
| `planned` | Coordinator | Scope exists; no frozen candidate or result claim. |
| `frozen` | Custody owner | Code, data, policy, environment, and queries have immutable identities. |
| `candidate_running` | Run operator | A declared candidate is executing in its isolated result root. |
| `candidate_complete` | Run operator | Raw evidence exists; no pass/promotion implication. |
| `candidate_failed` | Run operator or verifier | A declared invariant or threshold failed; retain the evidence. |
| `verification_failed` | Independent verifier | The verifier could not reproduce or accept the frozen candidate. |
| `independently_verified` | Independent verifier | The verifier accepted only the specified workload and limitation set. |
| `human_approved` | Human owner | A decision names the exact claim and next authorized step. |
| `revoked` | Human owner or audit record | A prior result may not support the named claim. |

Only a human decision can advance a scale claim beyond
`independently_verified`. A runner, dossier generator, or LLM must never
write `certified`, `approved`, or an equivalent success state.

### 4.3 Required immutable evidence bundle

Each candidate and verifier result root must contain, or reference by immutable
digest:

1. `identity.json`: source commit/tree, lockfile hash, runner hash, command,
   and clean-worktree status.
2. `corpus.lock.json`: source/rights records, file hashes, native record
   IDs, selected-record hash root, exact D count, deduplication policy, and
   exclusions.
3. `transform.lock.json`: parser, tokenizer, atomizer, normalization, and
   source-offset rules with versions and hashes.
4. `candidate.json`: workspace, data root identity, database snapshot
   identity, event-watermark range, projection component/release IDs, and
   hardware profile.
5. `preflight.json`: all checks and structured failure receipts. A preflight
   failure prevents a candidate result file.
6. Raw ingestion, resource, query, graph, citation, update/delete, and fault
   telemetry. Aggregates must be mechanically recomputable from these files.
7. A quiescent database backup or reproducible snapshot reference, its
   SHA-256, `PRAGMA integrity_check`, table counts, and WAL handling record.
8. `verifier-attestation.json`: an independently generated signature over
   the fixed evidence manifest and a limitation statement.

Git object identity protects the checked-in manifest. It does not substitute
for a snapshot hash, hardware receipt, raw telemetry, or independent signature.

## 5. Level 1 — 100K requalification plan

### 5.1 Entry and exit criteria

**Entry:** R0 is complete, the canonical runner boundary is decided, and a
fresh candidate can be built without using an unverified database or old result
root.

**Exit:** An independent verifier has reproduced the frozen 100K protocol and
a human owner has explicitly chosen one of: `promote_100k`, `repair`,
`reject`, or `defer`. Only `promote_100k` permits Level 2 planning to
become execution work.

### 5.2 Ordered, bounded work packets

| Packet | Owner | Scope and required output | Stop / repair route |
| --- | --- | --- | --- |
| L1-01: 100K reconciliation | Coordinator, read-only | Inventory the alleged 100K corpus, runner, result root, raw telemetry, verifier packet, and decision-chain hashes. Produce a gap list rather than a verdict by assertion. | Missing raw data, mismatch, or forged identity becomes a failure record and proceeds to L1-02; it never becomes a reconstructed pass. |
| L1-02: corpus and judgment capsule | Data steward | Build a reviewed 100K selection from real, license-aware sources. Freeze native IDs, content hashes, source byte locations, transforms, query/judgment packs, and exclusions. | Any duplicate D record, missing rights/source hash, absent judgment, or ambiguous offset stops the candidate. |
| L1-03: certification runner contract | Architect plus evaluator | Specify the only supported ingestion, projection, query, citation, fault, and artifact interfaces. Define the approved threshold policy before any run. | A requested change to truth semantics, threshold, corpus, or workload requires a new human decision, not a mid-run patch. |
| L1-04: runner repair | Implementer | Replace the old 100K runner in an isolated worktree. Add only the declared contracts and fail-closed behavior. | Unit/integration failure returns a narrow repair handoff; do not edit evaluator data or policy to make it pass. |
| L1-05: calibration | Run operator | Run 1K, 10K, and 25K diagnostic workloads using the same interfaces and manifests. Attribute bottlenecks from telemetry. | Calibration is non-certifying. Two repairs pointing to the same architectural bottleneck require an architecture decision. |
| L1-06: candidate freeze and 100K execution | Custody owner and run operator | Freeze the exact code/data/query/environment bundle, create a new candidate data root, and execute the full 100K protocol. | Any mismatch, resource breach, missing raw trace, or failed lane produces `candidate_failed`. |
| L1-07: independent verification | Separate verifier | Use a fresh pinned worktree, independent cache/data copy, fresh result root, and no access to candidate writes. Reproduce the protocol and write a signed attestation or failure packet. | The verifier never repairs the candidate. Any mismatch returns to L1-03 or L1-04. |
| L1-08: Gate C2 dossier | Coordinator and evaluator | Assemble the candidate and verifier evidence, limitations, and a recommendation. | The dossier cannot label the gate approved; it waits for the human decision. |

### 5.3 Required implementation corrections before a 100K candidate

The replacement runner must satisfy all of these conditions:

1. **Real durable ingestion.** It calls the supported Spine ingestion path or
   one audited batch adapter, commits events and source atoms transactionally,
   and verifies committed counts after each batch. It must not use a target
   counter as proof of D, A, or E.
2. **Idempotency and deduplication.** The durable key is derived from the
   canonical native source identity, content hash, and transform revision. A
   uniqueness constraint and a post-run audit reject duplicate D records.
3. **No silent input changes.** The runner validates every corpus file and
   frozen record selection hash before opening a candidate database. Missing
   paths, checksum changes, a changed tokenizer, or a platform fallback stop
   preflight.
4. **No score manipulation.** Remove threshold floors, literal retrieval
   scores, literal abstention scores, and unconditional overall verdicts.
   Metrics are calculated from retained per-query results; denominators,
   exclusions, failures, and bootstrap method are retained.
5. **Product-real retrieval.** Queries run through the same persisted
   lexical/vector/graph/projection interfaces that the declared product
   configuration uses. A local in-memory index may be a diagnostic comparison,
   never the source of a certification score.
6. **Bounded graph proof.** Store and report the real projection release,
   candidate-set limit, degree distribution, walk depth, visited-node count,
   and timeout behavior. A prefix such as “first 10,000 edges” cannot represent
   a 100K graph unless that prefix is the pre-frozen workload.
7. **Real recovery.** Faults terminate or interrupt the declared process,
   reopen from a fresh process/database state, replay the complete declared
   event range, and compare source atoms, lifecycle state, release identity,
   and content/evidence hashes. Copying a prefix into an unrelated table is not
   replay or parity.
8. **Verified citations.** The citation validator rereads the original
   immutable source bytes at every reported offset and checks source ID,
   boundaries, quote hash, and authorization. It does not trust an LLM's
   citation count.
9. **Separated LLM lane.** If synthesis is in scope, it is an explicit
   optional lane with a frozen provider/model policy, cost receipt, raw
   redacted request/response hashes, and judgment protocol. It cannot seed
   facts or certify the data-plane/retrieval result by itself.
10. **Proposal safety.** Schema/taxonomy output remains a proposal. No benchmark
    run may self-approve a schema or mutate trusted graph edges.

### 5.4 100K acceptance matrix

| Claim | Evidence that must exist | Automatic failure condition |
| --- | --- | --- |
| 100,000 real documents | 100,000 unique native-ID/content-hash pairs in the frozen selection and in the durable Spine audit. | Repeated source text, target-only counting, source hash mismatch, or D/A conflation. |
| Source and atom fidelity | Bidirectional D-to-A mapping, source offsets, sampled and deterministic anchor checks, and hash parity after rebuild. | Missing source bytes, invalid offset/hash, orphan atom, or unreported transform change. |
| Incremental behavior | A pre-registered resume test with idempotency audit, committed watermark, and no duplicated event/source key. | Full reprocessing, reused positional IDs, duplicate events, or checkpoint mismatch. |
| Retrieval quality | Frozen query/judgment pack, query-level ranked results, metric program, confidence intervals, and comparison to the declared baseline. | Keyword-only grading, injected gold text, missing judgments, score floor, or unreported exclusions. |
| Abstention | Frozen answerable/unanswerable labels and an evaluator that separately scores supported answers, abstentions, and unsupported claims. | Treating zero citations or an exception as a correct abstention. |
| Performance/resource behavior | Process-tree RSS, CPU/GPU, disk/WAL, I/O, queue/backlog, and cold/warm p50/p95/p99 traces tied to Q. | Aggregate-only output, hidden cache state, unbounded work, resource breach, or missing samples. |
| Crash/replay/rebuild | Fault schedule, process exit/restart receipts, full declared event replay, fresh rebuild, and state-hash comparison. | Timing-only replay, partial replay presented as full, non-equivalent state, or untested WAL recovery. |
| Reproducibility | Fresh verifier worktree, independent result root, exact identity checks, and signed attestation. | Shared mutable result root, verifier patching, identity drift, or missing attestation. |

The numerical quality and resource thresholds must be placed in a human-accepted
policy manifest before L1-06. They are not copied from previous scorecards or
relaxed after an observed result.

### 5.5 Minimum negative tests

The verifier and CI must retain tests that the old scripts would fail:

- missing master database rejects instead of selecting `:memory:`;
- a duplicate source hash rejects the candidate;
- a database with fewer committed source events than D rejects the candidate;
- a metric clamp, literal pass field, or static abstention score rejects the
  result schema;
- a query result without a frozen judgment cannot contribute to nDCG/recall;
- zero citations are not automatically a successful abstention;
- a citation whose byte range or quote hash is wrong rejects its case;
- a replay of fewer than the declared event range cannot claim full parity;
- a benchmark that writes to the evaluated workspace fails read-only mode;
- a missing provider or credential fails a required synthesis lane visibly.

## 6. Level 2 — true 1M pilot plan

### 6.1 Entry gate

Level 2 begins only when all of the following are present:

1. a human `promote_100k` decision naming the accepted 100K evidence bundle;
2. its independent verifier attestation and limitation statement;
3. a fresh 1M architecture/capacity plan derived from observed 100K
   coefficients rather than an extrapolated headline;
4. a Human Gate D decision that authorizes a **specific** 1M pilot, hardware
   profile, cost envelope, provider policy, and allowed claim boundary.

The old `trace_master_spine.db` is not an eligible bootstrap. Retain it
read-only as forensic evidence until its disposition is separately authorized.

### 6.2 1M corpus and checkpoint rules

The current audited source pool contains far fewer than one million unique
texts. Level 2 must obtain and freeze one million unique D records; it must
never loop a smaller corpus to reach the count.

The 1M corpus lock must include:

- one million native source IDs and content hashes, with source/rights records;
- a deterministic selection order and held-out query/judgment split;
- actual raw-byte and frozen-tokenizer counts, not token-equivalent estimates;
- per-source byte ranges or source-object identities sufficient for citation
  validation;
- the full transform/atomization revision and duplicate policy;
- a corpus hash root and a manifest signature.

A valid checkpoint may be written only after a durable, verifiable batch
boundary. It includes the corpus/selection/transform hashes, last committed
event watermark and hash-chain root, per-source progress, idempotency audit,
database snapshot hash, WAL state, candidate projection IDs, and environment
identity. Resume validates all fields against the live durable state before
ingesting a single new record.

### 6.3 Ordered 1M work packets

| Packet | Owner | Scope and output | Stop / repair route |
| --- | --- | --- | --- |
| L2-01: capacity decision | Scale architect | Measured 100K coefficients, 1M architecture, partition/release strategy, hardware/cost envelope, and expected bounded-work limits. | If 1M needs an architectural change, shard model, or new service, request Gate D before implementation. |
| L2-02: 1M data capsule | Data steward | One-million-unique corpus lock, held-out evaluation pack, source/rights proof, and independent duplicate audit. | Insufficient unique data, unclear license, or query contamination stops work before a candidate DB exists. |
| L2-03: data-plane implementation | Implementer | Actual durable, streaming 100K-to-1M ingestion, checkpoint/resume, candidate projection, and release activation behavior. | No direct reuse of unverified master state; any whole-corpus materialization or unbounded projection requires an architecture review. |
| L2-04: diagnostics | Run operator | 100K, 250K, and intermediate non-certifying checkpoints with resource/queue/recovery telemetry. | A bottleneck creates a bounded repair packet; it does not license a claim or an untracked rewrite. |
| L2-05: frozen 1M candidate | Custody owner and run operator | New isolated candidate data root, exact 1M run, full raw telemetry, and candidate-only results. | Any missing record, duplicate, resource breach, failed recovery, failed quality lane, or invalid citation yields `candidate_failed`. |
| L2-06: read-only hybrid evaluation | Evaluator | Frozen multi-domain query pack executed against the actual 1M candidate release, with retrieval and synthesis measured separately. | Any seeded fact, keyword-only judgment, hidden fallback, or database write invalidates the evaluation. |
| L2-07: independent F2 verification | Separate verifier | Fresh worktree/data copy/result root, evidence-manifest validation, independent reproduction, and signed limitation report. | The verifier does not patch data/code or reuse the candidate’s mutable cache. |
| L2-08: human F2 dossier | Coordinator and human owner | Narrow claim recommendation: exact corpus, configuration, hardware, scope, and residual limitations. | A pass cannot imply 10M, distributed readiness, general grounded cognition, or production adoption. |

### 6.4 Required 1M workload proofs

#### Persistent Spine and incremental ingestion

- Build a new candidate Spine from the frozen corpus. Report D, A, E, and R
  separately before and after every planned checkpoint.
- Demonstrate the 100K-to-1M delta using real new source identities. The final
  900K increment must contain no source record already accepted in the first
  100K segment.
- At pre-registered interruption points, restart from the checkpoint and prove
  that no accepted source record is reprocessed, omitted, or duplicated.
- Use database-backed idempotency rather than a positional counter such as
  `produced` or `existing_doc_count`.
- Take a safe immutable SQLite backup or equivalent snapshot after quiescing
  the declared state; include WAL semantics and integrity checks in the
  manifest.

#### Candidate projections and graph

- Build lexical, vector, hierarchy, and graph state as versioned projections
  from the committed Spine watermark; they are not sole sources of truth.
- Hold the previous valid release active until direct validation passes and
  record the atomic activation/rollback receipt.
- Instrument the full candidate workload: degree distribution, graph-edge
  provenance, candidate-set size, traversal depth, visited nodes, timeouts,
  queue backlog, projection lag, and rebuild cost.
- A bounded query may inspect a bounded candidate neighborhood, but the
  benchmark must declare and verify that bound. It may not silently substitute
  the first N edges or a test-only in-memory graph for the 1M projection.

#### Retrieval, synthesis, and grounding

The hybrid evaluator is a separate, read-only consumer of the frozen candidate:

1. It opens the Spine/projection in read-only mode and asserts that event,
   node, and projection counts do not change during evaluation.
2. It uses a pre-registered, multi-domain query/judgment pack with enough
   cases per lane to report uncertainty. Six prompts cannot establish a
   general factual-grounding rate.
3. It writes every retrieved item, rank, score, release ID, evidence bundle,
   latency, exclusion, and error. Retrieval latency and LLM latency are
   reported separately.
4. Its citation verifier independently rereads source bytes and validates
   source identity, range, quote hash, and authorization. Citation count alone
   is not proof.
5. An answerable case needs judged support; an abstention case needs a frozen
   no-answer judgment and a response without unsupported assertions. Neither
   a missing citation nor an exception is automatically a pass.
6. A required model call records provider/model revision, consented data policy,
   request/response hashes or approved redactions, token/cost receipt, and
   error behavior. Provider unavailability fails that declared lane.
7. Schema/taxonomy induction remains a proposal with evidence and reviewer
   status. It is never “approved” by the benchmark itself.

#### Fault and lifecycle matrix

At 1M, run the same declared matrix against the actual candidate state:

| Case | Required proof |
| --- | --- |
| Mid-batch process loss | Restart receipt, persisted watermark, no lost/duplicate source key, and resumed throughput. |
| WAL/restart recovery | Fresh-process open, integrity check, complete declared replay/rebuild, and state-hash parity. |
| Candidate validation/activation interruption | Exactly one valid active release or an explicit failed activation with rollback. |
| Source update, revocation, and repeat erasure | Correct lifecycle/access behavior, derived-state handling, and a delta-write audit. |
| Stale/corrupt projection | Direct validation rejects it; no silent fallback to a flat or old index outside declared policy. |
| Resource pressure | Process-tree and service telemetry show bounded backpressure/failure behavior without evidence loss. |

### 6.5 1M claim boundary

If Gate F2 is approved, the allowable statement is limited to the reproducible
workload: the frozen 1M corpus, exact candidate/release, machine and provider
profile, query protocol, measured outcomes, and verified limitations. It does
not establish:

- 10M, 100M, 10B, or distributed capacity;
- universal sub-second retrieval rather than the measured query distribution;
- general “zero hallucination” beyond the evaluated and independently judged
  cases;
- production readiness, autonomous action authority, or consumer adoption;
- a claim that a one-million-document result proves one-million-document
  cognition rather than the specified retrieval/synthesis workload.

## 7. Roles, custody, and handoffs

Implementation and verification must remain separate:

| Role | May do | Must not do |
| --- | --- | --- |
| Data steward | Build/freeze source and query capsules; report rights/provenance gaps. | Change scoring, synthesize missing data, or declare a gate pass. |
| Implementer/run operator | Repair runner, execute a frozen candidate, retain raw evidence. | Edit frozen queries/data/thresholds, verify its own candidate, or approve a claim. |
| Evaluator | Freeze protocols, calculate metrics from raw output, state limitations. | Change candidates during or after a run. |
| Independent verifier | Reproduce/read evidence from a fresh custody boundary and sign a result. | Patch code/data, share a mutable cache/result root, or make a human decision. |
| Coordinator | Reconcile facts and assemble handoffs/dossiers. | Invent approval, replace missing evidence, or reclassify a failure as a pass. |
| Human owner | Choose canonical boundary, thresholds, resource/cost envelope, promotion, and next scale scope. | Delegate the irreducible approval record to a runner or LLM. |

Every handoff contains: base commit/tree, worktree path, allowed paths,
manifest hashes, executed commands, exact result root, raw evidence hashes,
failures/exclusions, limitations, and the one next allowed packet.

## 8. Recommended bounded session order

| Session | Begins only after | Outcome |
| --- | --- | --- |
| S0 | This plan is accepted as a planning artifact. | R0 containment/reconciliation packet. |
| S1 | S0 custody facts are frozen. | 100K corpus/query/judgment capsule. |
| S2 | S1 contract is reviewed. | Canonical 100K runner repair candidate and negative tests. |
| S3 | S2 local checks pass. | Diagnostic calibrations and bottleneck attribution. |
| S4 | S3 repair loop, if any, is independently accepted. | Frozen 100K candidate run. |
| S5 | S4 raw evidence is sealed. | Independent 100K verification. |
| Gate C2 | S5 attestation and dossier exist. | Human promote, repair, reject, or defer decision. |
| S6 | Only if Gate C2 promotes 100K. | 1M capacity/data/claim plan for Gate D. |
| Gate D | S6 plan is reviewed. | Human authorization for a bounded 1M pilot or no execution. |
| S7 | Gate D authorizes execution. | 1M data-plane and evaluator candidate; diagnostic checkpoints. |
| S8 | S7 is frozen. | Full isolated 1M candidate run and read-only hybrid evaluation. |
| S9 | S8 evidence is sealed. | Independent F2 verification and limitation report. |
| Gate F2 | S9 report exists. | Human decision on the exact 1M claim and next allowed work. |

Corpus preparation and runner engineering may proceed in parallel only while
their inputs are still mutable and explicitly marked non-certifying. Candidate
execution, evaluation, and independent verification are serial.

## 9. First next action

Start with **R0-01 and R0-03 only**: create a read-only claim/custody inventory
that records the revoked 1M artifacts, the three runnable scripts, the external
database state, and the evidentiary gaps. Do not run the old scripts, mutate
the external database, download data, contact a provider, or amend a human
decision while that inventory is being prepared.

The resulting packet decides whether Level 1 starts with an evidence
reconciliation repair or a clean reimplementation. It does not pretend that
either the historical 100K result or the deleted 1M scorecards are already
trusted.
