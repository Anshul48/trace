# Trace 100K-to-1M Scale Qualification Execution Plan

> **Status:** Draft, planning only.
>
> **Prepared:** 2026-08-29 from the current audited repository state.
>
> **Authority boundary:** This plan does not approve Gate C2, authorize a 1M
> run, amend DEC-P-005/DEC-P-005b, download a corpus, call a model provider, or
> certify any result. The human owner retains threshold, cost, execution, and
> promotion decisions.
>
> **Relationship to the recovery plan:**
> `SCALE_CERTIFICATION_RECOVERY_PLAN.md` remains the governing truth and
> containment contract. This document is its execution amendment for the
> present R2.1 state. Historical LTR-13 1M plans derived from the invalid 100K
> predecessor are forensic records, not execution authority.

## 1. Objective and exact finish line

The program objective is to reach a narrowly truthful 1M claim through two
strictly sequential qualifications:

1. **G100K-CORE:** promote one frozen, real, persistent 100,000-document
   candidate after independent verification and Human Gate C2.
2. **G1M-CORE:** append 900,000 new unique documents to an immutable copy of
   the accepted 100K base, operate and evaluate the resulting persistent
   1,000,000-document system, independently verify it, and obtain Human Gate
   F2 approval.

An optional **G1M-HYBRID** synthesis/LLM claim is a later, separate gate. It
cannot create, repair, or certify G100K-CORE or G1M-CORE.

For this plan, "1M reached" means all of the following at the same frozen
candidate identity:

- exactly 1,000,000 admitted canonical documents, each with a stable native
  source identity and unique canonical content hash;
- durable committed events and source records in the declared Spine, not a
  Python counter, loop iteration, atom count, or token-equivalent estimate;
- exactly 100,000 accepted base documents plus exactly 900,000 new documents,
  with a full duplicate and idempotency audit;
- persisted, versioned lexical/dense/graph projections built from a declared
  event watermark;
- raw query, citation, graph, resource, update/erasure, interruption, recovery,
  and rebuild evidence mechanically recomputable by a separate verifier;
- an immutable evidence manifest bound to code, data, policy, environment,
  database snapshot, and projection identities;
- an independent verification result; and
- an explicit Human Gate F2 decision naming the exact allowed claim.

No runner or report generator may emit `CERTIFIED`, `APPROVED`, or a human
promotion state.

## 2. Starting truth ledger

| Subject | Starting classification | Consequence |
| --- | --- | --- |
| Commit `b9b03f3` and historical 1M reports | `REVOKED_NON_CERTIFYING` | Preserve by hash for forensics. Never use as a baseline, checkpoint, or predecessor. |
| Historical `trace_master_spine.db` | Forensic database, not a 1M candidate | Keep read-only. Do not top up, migrate, or relabel it. |
| Historical 1M corpus loop | 63,071 distinct texts repeated toward a counter | It cannot contribute any admitted record to a new 1M claim without re-entering through the new frozen corpus contract. |
| Current 100K candidate | `CANDIDATE_FAILED` | Useful diagnostic evidence only; no Gate C2 promotion. |
| R2.1 protocol changes | Partially implemented; no fresh bound 100K execution | Finish and prove the measuring system before retrieval/storage tuning is credited. |
| Retained R2.1 query telemetry | Stale 500-row output with no complete MultiHop/Top-20 evidence | Do not use it as the R3 baseline or as proof of the new evaluator. |
| Current R2.1 verifier receipt | Bound to a 1K calibration rather than the retained 100K candidate | It cannot attest the 100K gate. Generate a fresh receipt only after a fresh candidate. |
| R2.1 custody/reporting | Relevant work remains outside a clean immutable candidate lineage | Source implementation, candidate execution, verifier output, and human decision must be distinct artifacts. |
| Gate C2 | `REPAIR` | Level 2 execution remains blocked. |
| Level 2 / 1M | Planning only | No corpus acquisition, candidate build, or provider use until Gate D authorizes the exact pilot. |

The next valid evidence lineage starts from a reviewed clean source commit. It
does not inherit a PASS bit, metric, checkpoint, database count, or scale claim
from any earlier candidate.

## 3. Governance and threshold change control

### 3.1 Three classes of requirements

| Class | Examples | Change rule |
| --- | --- | --- |
| Truth and integrity | Unique D count, provenance, hashes/offsets, no fallback, full replay, idempotency, raw evidence, verifier separation | Non-negotiable for this program. A failure is repaired, not waived. |
| Capability quality | Frozen qrels, nDCG/Recall/Coverage, grounded citations, abstention | May change only through a prospective human decision supported by baseline methodology, never because a candidate missed the bar. |
| Capacity profile | Latency, RSS/VRAM, throughput, storage, hardware, cost | May be revised prospectively for a named hardware/software profile before candidate freeze. The old result is still failed under its old policy. |

### 3.2 Required policy-reconciliation decision before the next candidate

The repository currently contains conflicting latency policies: the accepted
DEC-P-005 decision and the later R2.1 runner/verifier literals are not the same.
Before another qualifying run, packet **C2-POL-01** must produce one canonical,
schema-validated `scale_policy.lock.json` and a human decision that resolves:

- the exact per-lane 100K quality and latency thresholds;
- whether the 3.0x storage ceiling covers the durable Spine alone or all hot
  derived projections as well;
- the canonical raw-byte denominator and treatment of WAL, sidecars, vector
  files, caches, temporary build files, and retained backups;
- the R16 reference host and any separate accelerated profile;
- cold/warm measurement rules, concurrency, cache preparation, query count,
  percentiles, and process-tree accounting; and
- which optional lanes are informative rather than promotion-blocking.

Recommended disposition for the human brief:

- keep all truth, replay, provenance, uniqueness, citation, and fail-closed
  requirements unchanged;
- keep retrieval quality floors unchanged until a baseline/qrels audit proves
  a methodological defect rather than an implementation deficit;
- permit the already proposed R2.1 Python/R16 latency profile only if it is
  accepted prospectively and named explicitly;
- do not relax storage merely from the observed 6.88x result; first produce a
  component lower-bound model for the Spine, FTS, dense vectors, graph, and
  recovery reserve. If 3.0x is incompatible with the selected product
  representation, amend the policy before the next candidate and report both
  durable-Spine and total-hot-state amplification.

Runner and verifier must load the same policy file by digest. Threshold copies
embedded independently in two Python files are prohibited.

### 3.3 Decision sequence

```text
R2.1 measuring system proven
        |
        v
R3 engineering + non-certifying rehearsals
        |
        v
Frozen 100K candidate -> independent verifier -> Human Gate C2
        |
        v
1M capacity/corpus/protocol dossier -> Human Gate D
        |
        v
Frozen 1M candidate -> independent verifier -> Human Gate F2
```

Candidate execution and verification are serial. Engineering experiments may
run in parallel only when they use separate mutable diagnostic roots and are
clearly non-certifying.

## 4. Level 1: finish a truthful 100K qualification

### Wave R2.2 - measurement integrity execution closure

The purpose of R2.2 is to prove the measuring system. It is allowed to produce
a truthful failed candidate. Passing retrieval/storage is not an R2.2 exit
criterion; complete and independently recomputable measurement is.

| ID | Owner | Work and required artifact | Exit / stop rule |
| --- | --- | --- | --- |
| R2.2-01 | Coordinator/custody owner | Reconcile the dirty worktree. Inventory every R2/R2.1 changed or untracked file; select reviewed code/manifests; create one clean candidate commit and retain a diff-to-predecessor receipt. | Any unexplained file, mutable threshold, or evidence file mixed into the source commit stops the run. |
| R2.2-02 | Evaluator | Freeze `scale_policy.lock.json`, `queries.lock.json`, qrels, exclusions, metric algorithms, percentile method, bootstrap seed/method, and exact evaluation counts. | A policy/query change after freeze creates a new candidate identity. |
| R2.2-03 | Implementer | Make the runner consume the frozen cohort IDs and hashes. Remove implicit `[:200]` sampling unless an exact seed and sample list are in the lock. Emit Top-20 ranked records for every declared query and a structured error for every failed query. | Missing lane, row, Top-20 field, qrel, or error receipt yields `CANDIDATE_FAILED`. |
| R2.2-04 | Implementer/evaluator | Route null queries through the same unlabeled retrieval/answer decision path. Record scores, overlap/features, decision, citations, and unsupported claims; keep expected labels in verifier-only custody. | Candidate output containing expected labels or a caller-provided `system_abstained` truth value is invalid. |
| R2.2-05 | Verifier implementer | Remove legacy Top-3 fallback. Require exact policy/query/candidate bindings; recompute every metric from raw output; enforce scale, RSS, storage, all lane latencies, graph limits, replay, and evidence completeness. Repair non-ASCII console failure and return one deliberate schema-defined exit status. | A verifier exception is `VERIFICATION_ERROR`, never an attestation or pass. |
| R2.2-06 | Test owner | Add negative integration fixtures for stale timestamps, 500-row truncation, missing MultiHop, absent Top-20, forced abstention, missing citations, policy drift, manifest drift, DB substitution, altered raw telemetry, and verifier write attempts. | Unit-test count alone is insufficient; each old failure mode must be shown to fail closed. |
| R2.2-07 | Run operator | From the clean commit, execute a fresh full 100K measurement run into a new candidate root. Never reuse the Aug-28 DB/dossier/raw telemetry as the new result. | The outcome may be `CANDIDATE_FAILED`; incomplete evidence is `INVALID_RUN`, not a performance failure. |
| R2.2-08 | Independent verifier | Verify from a detached clean worktree with read-only candidate access and a fresh result root. Recompute query metrics and inspect the database directly. | Verifier and candidate roots, caches, and mutable workspaces must not be shared. |

R2.2 is closed only when all declared cases can be counted from raw files,
every aggregate is independently reproduced, the candidate and verifier agree
on identity, and deliberate corruptions are rejected. Its closure statement is
`MEASUREMENT_PROTOCOL_VERIFIED`; it is not `promote_100k`.

If the current R2.1 query manifest is adopted unchanged, the run contract is
7,457 total cases: 7,156 answerable cases across the four retrieval suites and
301 unanswerable/null cases. A smaller predeclared sample may be diagnostic,
but it cannot be described as the complete R2.1 suite.

### Wave R3A - retrieval quality engineering

R3A addresses the measured capability deficit without using evaluation labels
inside the product path.

| ID | Owner | Work | Required evidence |
| --- | --- | --- | --- |
| R3A-01 | Data/evaluation steward | Split frozen cases into development, qualification-readiness, and untouched promotion sets. Audit qrels closure, doc-ID mapping, duplicate queries, leakage, label balance, and added-corpus contamination. | Signed split manifest and leakage report. Qualification and promotion qrels stay unavailable to tuning code. |
| R3A-02 | Retrieval engineer | Establish honest BM25/FTS baselines on the complete development protocol. Fix tokenization, field weighting, native-ID resolution, and empty-query/error behavior. | Per-query Top-20, query latency, index identity, and unfloored metrics. |
| R3A-03 | Retrieval engineer | Bake off a small bounded set of locally pinned dense embedding candidates. Use `TRACE_DENSE_MODEL`, exact revision/hash/config, `local_files_only`, deterministic batching, and no silent/hash-vector fallback. | Dense-only development metrics, vector-build cost, bytes/vector, RSS/VRAM, and latency for each candidate. |
| R3A-04 | Retrieval engineer | Implement lexical+dense Reciprocal Rank Fusion with all constants frozen. Keep score calibration transparent; do not learn weights on the promotion set. | BM25-only, dense-only, and RRF paired ablations with 95% bootstrap confidence intervals. |
| R3A-05 | Graph engineer | Add bounded graph/PPR reranking only if it improves held-out development quality within graph, storage, and latency budgets. Record candidate-set size, degree, visited nodes, depth, and timeouts per query. | RRF vs RRF+graph paired ablation. A ceremonial graph lane with no benefit is excluded from the candidate profile. |
| R3A-06 | Evaluator | After configuration freeze, run the qualification-readiness pack once. Do not tune further from its results; a repair that needs label feedback retires this pack and requires a newly frozen qualification pack. | All absolute floors and no-regression criteria must pass without metric floors or exclusions added after observation. The untouched promotion pack remains sealed for R4. |

The LLM is not part of R3A. Retrieval must first locate judged evidence. An LLM
cannot compensate for missing gold documents or promote a weak retriever.

### Wave R3B - storage, latency, and recovery engineering

R3B begins from page/file accounting, not from a desired multiplier.

| ID | Owner | Work | Required evidence |
| --- | --- | --- | --- |
| R3B-01 | Storage engineer | Freeze the canonical raw-byte denominator. Account for every database page, index, WAL/SHM file, vector file, graph file, cache retained for serving, and temporary peak during rebuild. | Machine-readable object/page report whose totals reconcile to filesystem bytes. |
| R3B-02 | Storage architect | Remove duplicate full-text storage. Store canonical source bytes once in a content-addressed, checksummed object representation; events retain immutable object references, payload hashes, source identity, and transform revision. | Source-byte and event replay proofs show that compression/reference changes preserve exact citations and rebuildability. |
| R3B-03 | Storage engineer | Use compact stable integer IDs, bounded/provenance-tagged adjacency, contentless or external-content FTS where safe, and measured vector precision/quantization. | Component-by-component bytes/document and bytes/atom, quality delta, build time, and replay parity. |
| R3B-04 | Performance engineer | Profile query stages separately: FTS, dense search, fusion, graph, evidence materialization, and serialization. Remove avoidable Python/SQLite hot-path overhead before considering a native component. | Cold/warm p50/p95/p99, CPU, I/O, RSS, and flame/profile artifacts on the declared host. |
| R3B-05 | Data-plane engineer | Implement real transaction boundaries, idempotency constraints, resumable batch checkpoints, quiescent snapshots, and event-projection rebuild. | Mid-batch kill/restart, WAL recovery, complete event replay, and table/projection state-hash parity. |
| R3B-06 | Architect | If profiling shows a bounded hotspot that cannot meet the accepted profile, propose a Rust/Go/native component behind the existing contract with golden parity tests. | Native work is accepted only when it preserves evidence semantics and improves the named bottleneck. No whole-system rewrite. |

Storage optimization must not delete canonical evidence, weaken offsets, omit
derived-state files from accounting, or call a projection rebuild "zero
reprocessing." The zero-duplicate claim applies to source ingestion. A
versioned projection may legitimately reread accepted source bytes, and that
work must be reported.

### Wave R3C - diagnostic ladder and candidate readiness

Run the same code paths and schemas at 1K, 10K, 25K, and one full 100K
non-certifying rehearsal. Each run gets a new root and immutable manifest.

The diagnostic ladder records:

- D, A, E, and active projection R separately;
- raw bytes, source tokens, atoms, events, edges, and vector count;
- ingest/index throughput and queue/projection lag;
- process-tree RSS, GPU/VRAM if used, disk/WAL/temp peak, CPU, and I/O;
- cold and warm per-lane query distributions;
- complete raw query results and errors;
- graph bounds and provenance;
- checkpoint/restart and complete rebuild parity; and
- component cost coefficients with predicted 1M confidence ranges.

Candidate freeze is allowed only when the 100K rehearsal:

1. satisfies every truth/integrity invariant exactly;
2. meets quality floors on the untouched promotion pack;
3. has enough capacity headroom to tolerate run variance rather than landing
   exactly on a limit;
4. reconciles all storage files to the accepted policy;
5. has no paging, OOM, retry loop, hidden fallback, missing query, or verifier
   exception; and
6. can be rebuilt from the declared event/source objects in fresh custody.

The readiness review should target at least 20% latency/RSS headroom and 10%
storage headroom. These are launch margins, not alternative certification
thresholds.

### Wave R4 - frozen 100K candidate and Gate C2

| ID | Owner | Work and output | Stop rule |
| --- | --- | --- | --- |
| R4-01 | Custody owner | Freeze source commit/tree, lockfile, policy, corpus/query/transform/model locks, command, environment, hardware, clean status, and candidate root. | Any identity drift aborts before ingestion. |
| R4-02 | Run operator | Build and evaluate the 100K candidate exactly once under the frozen protocol. Store raw evidence continuously and finalize only after quiescence. | Any invariant/threshold breach is retained as `CANDIDATE_FAILED`. |
| R4-03 | Custody owner | Snapshot the DB and sidecars; record WAL disposition, integrity check, counts, hashes, event watermarks, projection IDs, and a Merkle root over all artifacts. | A mutable or incomplete bundle is `INVALID_CUSTODY`. |
| R4-04 | Independent verifier | Recompute the full protocol from read-only evidence and independently rebuild the declared state in a fresh root. | No candidate repair, policy change, or shared mutable cache. |
| R4-05 | Coordinator | Assemble a dossier containing candidate outcome, verifier outcome, limitations, failures, and exact claim text. | The dossier may recommend but cannot promote. |
| Gate C2 | Human owner | Choose `promote_100k`, `repair`, `reject`, or `defer`, naming exact artifact and policy digests. | Only `promote_100k` unlocks Gate D preparation for execution. |

## 5. Level 2: build and prove the true 1M pilot

### Wave D0 - Gate D scope and capacity authorization

After `promote_100k`, produce a Gate D decision brief from observed 100K
coefficients. It must freeze:

- G1M-CORE claim scope and the exclusion or inclusion of optional lanes;
- the accepted 100K base snapshot, its event watermark, and projection/model
  compatibility rules;
- the 1M document definition and duplicate policy;
- source/rights policy and allowed data roots;
- reference hardware, storage headroom, process RSS, paging, throughput,
  latency, and cost/time envelopes;
- query packs, qrels protocol, statistical method, and no-regression rule;
- checkpoint locations and failure-injection schedule;
- required snapshots/copies and minimum free-disk headroom; and
- provider/network policy. G1M-CORE should require no generative provider.

Proposed starting profile for Gate D analysis, not a binding decision:

- use the accepted 100K retrieval configuration unchanged unless a migration
  is separately verified;
- enforce the accepted quality floors plus no material regression from 100K;
- use the already accepted DEC-P-005 large-scale query ceiling of 100 ms as an
  outer bound, with tighter per-lane budgets derived from the 100K run;
- on a 32 GiB host, model a program-owned RSS ceiling no greater than 16 GiB
  with zero active paging, then accept or revise it before execution; and
- reserve enough disk for corpus objects, live candidate, build temporaries,
  one quiescent snapshot, and one independent rebuild. A single-copy fit is
  not sufficient capacity.

Gate D may authorize a bounded pilot, require architecture repair, or deny the
run. It does not certify 1M.

### Wave D1 - one-million-document corpus and judgment capsule

The 63,071-text input pool is inadequate. D1 must freeze exactly 1,000,000
admitted canonical documents without cycling, padding, synthetic repetition,
or splitting merely to inflate D.

| ID | Owner | Work | Acceptance rule |
| --- | --- | --- | --- |
| D1-01 | Data steward/human owner | Define the native document unit per source before counting. | Chunks/atoms are reported separately and cannot count as D unless the source contract natively defines them as records. |
| D1-02 | Data steward | Acquire or stage license-compatible real sources under the Gate D policy. | Every source has origin, rights/use classification, acquisition timestamp, and immutable object hash. |
| D1-03 | Data engineer | Canonicalize deterministically and compute native-ID, raw hash, canonical hash, length, language/type, source offsets/object ID, and transform revision. | Canonicalization cannot use candidate query labels or generated filler. |
| D1-04 | Independent data auditor | Run exact content-hash deduplication and report near-duplicate clusters separately. | Exactly 1,000,000 unique admitted canonical hashes; duplicates and exclusions remain in the audit ledger. |
| D1-05 | Custody owner | Partition the lock into accepted base 100K and new delta 900K, with deterministic order and Merkle roots for each and the union. | `base intersect delta = empty`; `count(base union delta) = 1,000,000`. |
| D1-06 | Evaluation steward | Freeze three query families: 100K regression, queries whose gold evidence lies in the new 900K, and answerable/unanswerable stress cases. | Promotion queries are held out; all admitted gold IDs exist in the 1M lock. Added data cannot be tested only as distractors. |

The manifest may be chunked outside Git, but every chunk and the ordered root
must be content-addressed. Git retains the root manifest, schema, generation
code identity, signatures, counts, and immutable artifact locator.

### Wave D2 - incremental 100K-to-1M data plane

Start from an immutable copy of the Gate-C2-approved 100K snapshot. Do not use
the revoked historical master database.

Required behavior:

1. Validate the complete base identity before accepting any delta record.
2. Append only the 900,000 delta records through the audited durable ingestion
   interface.
3. Enforce unique native source key, canonical content hash, event ID,
   idempotency key, and per-stream sequence constraints in persistent state.
4. Commit batches transactionally and reconcile attempted, accepted,
   duplicate-rejected, failed, and committed counts after every batch.
5. Write checkpoints only after durable commit boundaries.
6. Resume by comparing the checkpoint to live database state before reading a
   new source object.
7. Record source ingestion and derived projection work separately. A
   projection rebuild may reread source bytes but may not create duplicate
   source/events or be advertised as zero work.
8. Build lexical, dense, hierarchy, and graph projections as versioned
   releases from a named event watermark. Candidate projections remain
   invisible until validation and atomic activation.
9. Bound graph degree, candidate set, traversal depth, visited nodes, and time.
10. Preserve source-byte/citation recovery after compression and projection.

A valid checkpoint contains at minimum:

- schema version and checkpoint ID;
- source commit/tree, lockfile, policy, corpus, transform, model, and hardware
  digests;
- base snapshot digest and base event watermark;
- delta manifest root and next source position;
- last committed event ID/sequence and event hash-chain root;
- attempted/accepted/rejected/failed counts;
- database snapshot or page-set identity and WAL state;
- active/candidate projection IDs and their input watermark;
- timestamp, process/run identity, and previous-checkpoint digest; and
- checksum/signature over the complete checkpoint object.

### Wave D3 - scale diagnostics and go/no-go

Run non-certifying checkpoints at 250K, 500K, and 750K total documents using
the real ordered delta and production code paths. Pre-register at least one
mid-batch interruption before each checkpoint and one projection interruption.

At each checkpoint, compare observed versus predicted:

- accepted unique documents and event continuity;
- bytes/document, atoms/document, edges/document, vectors/document;
- ingestion/projection throughput and backlog;
- RSS/VRAM, paging, CPU, I/O, storage, WAL, and temporary build peak;
- checkpoint/resume work and duplicate/reprocessing audit;
- cold/warm retrieval quality and latency on a fixed diagnostic query subset;
- graph budgets and timeout/error rates; and
- projected full-run time, cost, disk reserve, and independent-rebuild reserve.

Proceed to the frozen 1M candidate only if the 750K measurements remain inside
the Gate D envelope with the same readiness margins used at 100K. Otherwise
issue a bounded repair packet; do not improvise the final run.

### Wave E - frozen 1M candidate execution

| Phase | Required operation | Evidence produced |
| --- | --- | --- |
| E-01 Freeze | Pin clean code, base snapshot, 1M corpus/query/policy/transform/model locks, environment, hardware, commands, fault schedule, and result root. | `identity.json`, lock digests, clean-tree receipt, preflight. |
| E-02 Base validation | Open immutable base copy and prove its Gate C2 identity, 100K membership, counts, event watermark, and integrity. | Base-validation receipt. |
| E-03 Delta ingestion | Append exactly 900K unique records with continuous telemetry and planned restart drills. | Batch/event/source logs, checkpoints, resource telemetry, error ledger. |
| E-04 Projection | Build candidate lexical/dense/graph releases from the final watermark; validate before activation. | Projection manifests, build telemetry, bounds, activation/rollback receipt. |
| E-05 Core evaluation | Execute complete frozen retrieval, graph, citation, abstention, performance, lifecycle, and cost protocols read-only. | Per-query Top-20+, citations, timings, exclusions/errors, raw lifecycle/fault traces. |
| E-06 Recovery/rebuild | Recover from planned faults and rebuild all declared derived state in a fresh location solely from canonical events/source objects. | Full counts and canonical state hashes for source and derived structures. |
| E-07 Seal | Quiesce, checkpoint WAL, integrity-check, snapshot DB and sidecars, inventory all bytes, and finalize Merkle manifest. | Immutable candidate bundle with status `candidate_complete` or `candidate_failed`. |

The candidate must report failures exactly. An incomplete query, provider
error, missing source object, timeout, or interrupted phase cannot disappear
from a denominator.

### Wave F - independent 1M verification and Human Gate F2

The verifier operates from a fresh pinned worktree, independent data copy or
immutable read-only mount, fresh caches where the protocol requires them, and
a new result root.

It independently verifies:

- exactly 1,000,000 unique admitted content hashes and native IDs;
- exact base/delta disjointness and preservation of all 100K base records;
- no duplicate ingestion events for the first 100K during delta append;
- monotonic/contiguous declared event ranges and checkpoint-chain validity;
- database integrity, counts, WAL disposition, object/file hashes, projection
  watermarks, and complete storage accounting;
- all emitted citations against canonical source bytes;
- every retrieval/abstention aggregate from raw query records;
- quality floors, no-regression confidence intervals, latency percentiles,
  graph bounds, resource/cost limits, and error denominators;
- planned fault/restart results, complete rebuild, and state-hash parity; and
- candidate immutability and absence of hidden fallback, seeded evidence,
  candidate writes during evaluation, or verifier repair.

The verifier emits exactly one of:

- `INDEPENDENTLY_VERIFIED` with a narrow limitation statement;
- `VERIFICATION_FAILED` with invariant/threshold violations; or
- `VERIFICATION_ERROR` when verification could not be completed.

Only `INDEPENDENTLY_VERIFIED` can be submitted to Human Gate F2. The human
owner then chooses `approve_1m_core`, `repair`, `reject`, or `defer` and binds
the decision to all artifact digests.

## 6. Acceptance matrices

### 6.1 Gate C2 minimum acceptance

| Dimension | Required result |
| --- | --- |
| Identity/custody | Clean pinned code; frozen policy/data/query/model/environment; immutable candidate and verifier roots. |
| Scale | Exactly 100,000 unique admitted D records in manifest and persistent state. |
| Provenance | 100% required hashes/offsets recover; 0 drift; 0 orphan active atoms. |
| Replay/lifecycle | Full declared event-driven rebuild parity; update/revocation/erasure behavior; repeat erasure delta zero. |
| Evaluation integrity | Complete declared query cohort, Top-20 telemetry, no label leakage, independent recomputation. |
| Retrieval/abstention | All frozen quality floors and grounded-abstention rules pass. |
| Bounded work | All accepted latency, graph, RSS/VRAM, throughput, storage, paging, and error-rate limits pass. |
| Verification | Separate verifier accepts exact candidate without patching or shared mutable state. |
| Authority | Human decision names candidate, verifier, policy, and limitation digests. |

### 6.2 Gate F2 minimum acceptance

Gate F2 includes every Gate C2 dimension plus:

| Dimension | Required result |
| --- | --- |
| 1M membership | Exactly 1,000,000 unique D; base=100,000; delta=900,000; empty intersection; full union proof. |
| Incremental truth | No duplicate source/event insertion for the accepted base; checkpoint resumes omit and duplicate nothing. |
| Scale architecture | All projections correspond to the final committed watermark and enforce declared bounds. |
| Added-corpus utility | Frozen queries with gold evidence in the new 900K are evaluated, not only old 100K regression queries. |
| Quality stability | Accepted absolute floors plus pre-registered no-regression confidence rule versus Gate C2. |
| Capacity | Gate D hardware/resource/cost envelope passes with all candidate, sidecar, WAL, cache, temp, and rebuild files counted. |
| Recovery | Planned 1M process/WAL/projection faults recover; fresh full rebuild matches canonical state. |
| Claim scope | Approval is limited to the exact local profile and does not imply 10M, distributed production, or general cognition. |

## 7. Optional G1M-HYBRID gate

G1M-HYBRID starts only after G1M-CORE is independently verified. It uses the
accepted 1M release read-only and has its own provider/model/consent/cost lock.

Minimum requirements:

- a pre-registered answerable and unanswerable judgment set large enough for
  per-lane uncertainty reporting; six prompts are diagnostic only;
- retrieval and synthesis measured separately;
- every answer claim linked to retrieved evidence and independently validated
  source-byte anchors;
- unsupported claims, citation errors, timeouts, provider failures, and schema
  failures retained as failures;
- no benchmark-authored landmark facts or writes to the evaluated Spine;
- no keyword-presence grading as a substitute for claim support;
- no universal "zero hallucination" statement; report the measured rate and
  confidence interval on the frozen set; and
- a separate verifier and human decision if a promoted hybrid claim is wanted.

Failure of this optional gate does not erase a valid G1M-CORE result, and a
hybrid pass cannot repair a failed core result.

## 8. Evidence bundle and custody layout

The owner must choose explicit roots; unset roots fail preflight. No runner may
default to an old DB, `:memory:`, a repository fixture, or the current working
directory.

Recommended separation:

```text
Git repository
  schemas, policy/query/corpus root manifests, code, tests, decision records

candidate artifact root (writeable only by run operator until sealed)
  run identity, DB/sidecars, raw telemetry, snapshots, evidence manifest

verifier artifact root (writeable only by verifier)
  recomputation, rebuild, negative checks, attestation/limitation report

source object root (immutable/read-only during candidate and verification)
  canonical corpus objects and chunk manifests
```

Each finalized bundle contains or immutably references:

1. source/tree/lock/runner/verifier identities and clean-status receipts;
2. policy, corpus, query/qrels, transform, and model locks;
3. command, environment, dependency, OS, CPU, RAM, disk, GPU, and clock profile;
4. preflight and every structured failure;
5. complete raw telemetry and query/fault/lifecycle traces;
6. DB/sidecar snapshot hashes, integrity checks, counts, WAL record, projection
   watermarks, and storage inventory;
7. evidence-manifest Merkle root and an actual signer identity if the artifact
   is called signed; a plain SHA-256 binding must be called a digest, not a
   signature;
8. independent verifier output and limitations; and
9. the later human decision as a separate record.

## 9. Repair routing and anti-procrastination rules

Every failed rehearsal/candidate is classified into exactly one primary route:

| Failure class | Repair owner | Examples |
| --- | --- | --- |
| `MEASUREMENT_INVALID` | Evaluator/verifier | Missing raw rows, stale manifest, metric mismatch, label leakage, verifier exception. |
| `DATA_INVALID` | Data steward | Duplicate D, absent gold, rights/provenance gap, contaminated split. |
| `RETRIEVAL_DEFICIT` | Retrieval engineer | Honest quality below floor with valid qrels. |
| `STORAGE_DEFICIT` | Storage architect | Page/file accounting exceeds accepted profile. |
| `PERFORMANCE_DEFICIT` | Performance engineer | Latency/RSS/throughput/paging breach. |
| `DURABILITY_DEFICIT` | Data-plane engineer | Resume, replay, WAL, lifecycle, or parity failure. |
| `POLICY_CONFLICT` | Human owner/architect | Contradictory or physically incoherent accepted requirements. |
| `CUSTODY_INVALID` | Coordinator/custody owner | Dirty identity, mutable root, wrong DB, missing digest/signature. |

Operating rules:

- one qualifying candidate may be active at a time;
- one repair packet changes one primary mechanism where practical, preserving
  paired before/after evidence;
- do not rerun an unchanged candidate hoping for a better score;
- after two consecutive repairs hit the same architectural bottleneck, stop
  tuning and issue an architecture or policy decision brief;
- never edit frozen qrels, exclusions, thresholds, or denominators in the same
  lineage after seeing candidate results;
- diagnostic PASS means only that the diagnostic met its declared scope;
- preserve negative results and raw evidence; and
- status reports must distinguish `implemented`, `tested_on_fixture`,
  `diagnostic_measured`, `candidate_complete`, `independently_verified`, and
  `human_approved`.

## 10. Ordered dispatch and critical path

| Order | Packet | Begins when | Ends with |
| --- | --- | --- | --- |
| 1 | C2-POL-01 | Plan accepted for preparation | One prospective policy lock/decision brief; no candidate. |
| 2 | R2.2-01 through R2.2-06 | Policy direction and current inventory available | Clean measuring-system source candidate and negative tests. |
| 3 | R2.2-07/R2.2-08 | Clean code/data/query identity frozen | Fresh 100K measurement result and independent recomputation, pass or fail. |
| 4 | R3A/R3B | Measurement integrity proven | Bounded retrieval/storage/performance repairs with paired evidence. |
| 5 | R3C | Selected architecture is stable | 1K/10K/25K/100K rehearsals and candidate-readiness review. |
| 6 | R4 | Readiness review passes | Frozen 100K candidate, verifier packet, Gate C2 dossier. |
| 7 | Human Gate C2 | Candidate and verifier packet complete | `promote_100k`, `repair`, `reject`, or `defer`. |
| 8 | D0 plus D1 design/feasibility | Only after `promote_100k`; no acquisition or build yet | 1M capacity, source-feasibility, corpus-contract, and protocol dossier. |
| 9 | Human Gate D | Dossier complete | Specific 1M pilot authorization or denial. |
| 10 | D1 acquisition/freeze plus D2/D3 | Gate D authorizes | Frozen 1M capsule, implemented incremental path, and passing 250K/500K/750K diagnostics. |
| 11 | E | 750K go/no-go passes | Frozen 1M candidate bundle, pass or fail. |
| 12 | F | Candidate bundle sealed | Independent result and F2 dossier. |
| 13 | Human Gate F2 | Independent verification complete | Narrow 1M core decision. |
| 14 | Optional G1M-HYBRID | Only after verified G1M-CORE | Separate hybrid evidence and decision. |

The immediate permitted technical packet is **C2-POL-01 plus R2.2 source and
test reconciliation**. The next permitted empirical action is a fresh
non-promoting 100K measurement run after those identities are clean and frozen.
Retrieval tuning should not begin from the stale 500-query telemetry because it
does not represent the R2.1 protocol.

## 11. Completion language

Use only the statement matching the attained state:

| State | Allowed language |
| --- | --- |
| Code/tests exist | "The scale runner/verifier implementation is ready for a frozen diagnostic." |
| Candidate completed | "A frozen 100K/1M candidate run completed with the attached measured outcome." |
| Independent verification passed | "The verifier independently accepted the named candidate under the named protocol." |
| Human gate approved | "The human owner approved the named 100K/1M core claim for the frozen corpus, implementation, hardware, and protocol." |

Never substitute "committed," "sealed," "all tests passed," "cryptographic,"
or an LLM-generated summary for the final two states.
