# TRACE MASTER STAGE-WISE EXECUTION PLAN — v1.1

**Status:** `BALLOT-READY DRAFT v1.1` — not certified, not approved. Requires human ballot before any gate runs.
Supersedes v1.0 (REJECTED, 7 substantiated defects). Every remediation below is verified against the repo;
every Section-12 command was run with `--help` in this workspace before inclusion.

---

## 1. Preamble (binding)

1. **Single modular plan, stacked decoupled gates.** One document owns lineage, invariants, and stage boundaries
   (H0→H1→H2→H3/H4). Each horizon promotes only by its own explicit human ballot; a downstream NO-GO never
   invalidates an upstream PASS; an upstream PASS never certifies cognition.
2. **Spine vs projection (CAP-D004).** The SQLite WAL atom/event ledger is immutable truth. Embeddings, FTS
   indexes, TOC-DAGs, centroids, CSR graphs, router state, summaries, and dreams are rebuildable projections:
   droppable without touching one Spine byte (proven by the drop-and-rebuild invariance check at each gate).
3. **No cloud in the hot path (CAP-D003/CAP-D006).** Synchronous ingest and interactive retrieval are local-only
   with $0 API spend. Cloud/local-SLM work runs offline (bake-offs, comparators) or in the Tier-4 reasoning lane
   ([AMENDMENT]9647, explicit budget), never as a retrieval gatekeeper.
4. **Fail-closed (CAP-D011).** No synthetic scores, no swallowed errors, byte-exact provenance end to end.
   Missing data, unresolvable manifests, or phantom tooling abort the run — never degrade silently.
5. **No L3 auto-promotion (CAP-D007/CAP-D012).** Schemata stay SHADOW/CANDIDATE until a human ballot promotes them
   (bar: ≥5 instantiations across ≥3 documents).

---

## 2. Ratified law vs [AMENDMENT] proposals

Every number in this plan carries exactly one tag. Untagged numbers are ratified law with the citation given.
`[AMENDMENT]` numbers are proposals introduced by this plan and take effect only if the human ballot ratifies them.

### 2.1 Ratified law (do not re-litigate; cite, don't modify)

| # | Law | Source |
|---|-----|--------|
| L1 | Total-hot storage hard ceiling **≤3.0x** admitted UTF-8 bytes (breach = auto-fail, halt lane) | `CORTICAL_SUBSTRATE_V1_PLAN.md` D1; code: `HARD_STORAGE_GATE_MULTIPLIER = 3.0` in `benchmarks/run_100k_qualification.py` |
| L2 | Durable Spine health signal **≤1.6x** | `CORTICAL_SUBSTRATE_V1_PLAN.md` D1; code: `MAX_DURABLE_MULTIPLIER = 1.6` |
| L3 | Monotonic scale target **≤2.5x at 1M** (3.0→3.0→2.5x); prior 3.5x loosening permanently withdrawn | `06_DECISION_LOG.md:641` (Amendment B4) |
| L4 | Synchronous, local, model-free ingest floor **≥800 docs/sec** into SQLite WAL; dense/projection indexing carries its own separate batch SLO and is never conflated with ingest | `06_DECISION_LOG.md:497` (CAP-D003) |
| L5 | Working Memory Governor caps the **retrieved concept bundle at 8–20 concepts** | `CORTICAL_SUBSTRATE_V1_PLAN.md:139` |
| L6 | Eval lanes without LLM inference: BEIR floors + P95 tiers per `04_EVALUATION_PROTOCOL.md`; Tier-2 PROMOTE iff paired 95% CI > 0 (seed 42, 10k resamples) | `04_EVALUATION_PROTOCOL.md:74-82`, WP6 dossier |
| L7 | Abstention bar ≥90% with zero hallucination (measured 99.00% / 0.00% on 301 nulls) | `verifier_receipt_independent.json` |

### 2.2 [AMENDMENT] proposals (this plan; effective only on ballot ratification)

| # | Proposal | Rationale |
|---|----------|-----------|
| A1 | Internal hot-footprint sub-allocation: retrieval-hot ≤0.8x, cortex-hot ≤0.6x (diagnostic split under L1) | Early warning before the 3.0x wall; breach triggers diagnosis, never auto-fail |
| A2 | Investigative tripwire ≈0.35x total-hot (measured 0.0997x at 100K): crossing it triggers profiling, not quarantine | Catches index bloat / text duplication early |
| A3 | Raw candidate depth **k ∈ [10,100]** ahead of the L5 governor (multi-hop needs k=50–100 pooling before graph spreading); only the final delivered bundle is capped 8–20 | L5 governs the assembled set, not the candidate pool |
| A4 | Tier-4 reasoning lane: local-SLM HyDE/decomposition for BRIGHT-class queries, **P95 ≤800 ms** explicit budget; interactive Tiers 1–2 stay ≤50 ms | Query-time SLM expansion cannot meet 50 ms; it gets its own lane, not a waiver |
| A5 | Sleep-consolidation bounds ported to H4: micro-batch **N≤250 docs**, lock-hold **p100 <15 ms**, active set **8–20 holons** per dreaming cycle | Same lock-safety logic as ingest, applied to background commits |
| A6 | Conformal abstention calibration set **n_cal ≥ 100**; apoptosis half-life **30 days** (truth edges exempt); Cobweb ΔCU threshold deferred to Phase-2 calibration | Tuning parameters, not gates |

---

## 3. H0 — Adopt the 1M corpus contract (preflight; grants no scale claim)

**Objective:** Bind the already-staged 1M capsule as the frozen corpus contract, normalize its paths, and sign it
per gate. H0 confers preflight only — never promotion, never a scale claim.

**The artifact (exists; verified this session — do not re-invent):**
`docs/program/inbox/1m-02-corpus-capsule/evidence/1m_corpus_manifest.json`
(`contract_version 2.0.0`, `synthetic_data_used=false`):

| Partition | Composition | Docs | Bytes |
|-----------|-------------|------|-------|
| Base 100K | musique 80047, beir-fiqa 10575, beir-scifact 5178, beir-nfcorpus 3591, multihop-rag 609 | 100,000 | 65,394,921 |
| Delta 900K | bright_delta 643710, wikipedia_delta 137360, enron_delta 50000, beir-fiqa_delta 47015, musique_delta 21915 | 900,000 | 1,949,070,823 |
| Union | base ∩ delta = ∅ | **1,000,000** | **2,014,465,744** |

Merkle roots: base `23b99dfe…2e57e6e5b`, delta `9385407a…10dc30`, union `5039acef…f7a79a5f5`.

**Entry:** Human gate ballot authority for the gate exists (CAP-D012 for ≥10K).

**Work (all with real files):**

1. **Path normalization (WP-H0-1).** Capsule `source_file` entries are Windows-absolute
   (`/mnt/c/Users/anshu/AppData/...`). Resolve each to a content-hash-verified local staging path and record the
   mapping in the gate manifest. Fail closed on any unresolvable or hash-mismatched source.
2. **Gate signing (WP-H0-2).** Emit a per-gate signed manifest (source IDs, SHA-256 per shard, licenses, tokenizer
   identity, frozen workload vector, revision scope). Until signed, the `100K`/`1M` labels remain provisional and
   confer no scale claim. (No `trace-bench admit/sign` CLI exists — signing is a work-packet deliverable: a small
   auditable script plus human co-signature in `06_DECISION_LOG.md`, never a phantom command.)
3. **Checksum green.** `benchmarks/verify_dataset_checksums.py` enforces `manifest_id == beir_musique_frozen_v1`
   (line 56) for the BEIR/MuSiQue splits. The 1M union manifest is a different contract: extend the verifier (or add
   a sibling 1M check honoring the same fail-closed semantics) as part of WP-H0-2; do not hand-edit the frozen check.

**Exit-gate (H0 ballot, Corpus-Contract head):** PASS → H1 | HOLD on hash drift / unresolvable source / schema
conflict | ABORT on license/data blocker. No silent PASS.

**Evidence:**

```yaml
h0_gate: <gate-id>
capsule: docs/program/inbox/1m-02-corpus-capsule/evidence/1m_corpus_manifest.json
union_merkle_sha256: 5039acefca682c7ea1f5c466af7089104781081591ab6f5c2879da5f7a79a5f5
path_map: <gate-manifest>  # every source_file resolved + hash-verified
gate_manifest_signed: true  # script + human co-signature ref
```

**Risks:** unresolvable Windows-absolute sources → HOLD, re-stage; verifier extended sloppily → frozen BEIR check
must keep passing unmodified alongside the new 1M check.

---

## 4. H1 — G1M-CORE durability (Gate CAP-GF)

**Objective:** Prove the Spine holds 1M docs with bit-exact durability inside ratified storage law. No models in
the loop. No retrieval claim, no cognition claim.

**Entry:** H0 PASS recorded; union Merkle pinned; goal statement confirmed.

**Work (owner surfaces are real files):**

1. **Spine WAL ingest** (`src/trace/v2/store.py`, `atomizer.py`, `index_manager.py`): raw text + atomization +
   external FTS5 postings (zero text duplication) through the frozen 100K-base → +900K-delta lineage. Measure the
   **Spine WAL ingest rate against L4 (≥800 docs/sec)**; dense-embedding throughput is projection indexing with its
   own batch SLO (preflight-calibrated, never conflated).
2. **Replay parity:** independent rebuild from the event log — 100% table parity, SHA-256 match; 1000/1000
   byte-anchor spot proofs.
3. **4-number storage accounting** (every commit): durable-spine / retrieval-hot / cortex-hot / total-hot, each
   against its ceiling: L2 (≤1.6x), A1 (≤0.8x / ≤0.6x diagnostic), L1 (≤3.0x hard), L3 (≤2.5x target), A2 (≈0.35x
   tripwire → profile, don't quarantine).
4. **Flat retrieval baseline** (no uplift claim): extend the 100K paired pattern, don't copy its constants —
   `benchmarks/run_100k_qualification.py` hardcodes `EXPECTED_DOC_COUNT = 100000` and its capsule Merkle, so the
   **1M qualification runner is a work packet (WP-H1-1)**: parameterize counts/roots, keep seed-42/10k-bootstrap
   semantics and fail-closed telemetry. P95 ≤50 ms interactive tiers per L6.

**Exit-gate (CAP-GF ballot, CORE head):** GO requires all of: 1,000,000 admitted canonical docs, 100% replay
parity, L1+L2+L3 ceilings met, L4 ingest floor met, P95 tiers met, $0 hot-path spend. Anything less is NO-GO:
quarantine the candidate lineage (forensic-only, never topped up or relabeled), fix, re-enter fresh.

**Evidence:**

```yaml
h1_core:
  admitted_docs: 1000000
  replay_parity: 100%  # SHA-256 table match
  storage: {durable_spine: <x≤1.6>, retrieval_hot: <x>, cortex_hot: <x>, total_hot: <x≤3.0>, target_2_5: <met|miss>}
  ingest_docs_per_sec: <≥800>  # Spine WAL only
  p95_ms: {tier1: <≤50>, tier2: <≤50>}
  api_spend_hot_path: $0.00
```

**Risks:** storage amplification recurrence (the 7.54x lesson) → quarantine, not tune-in-place; dense-indexing
speed misread as ingest → separate SLOs, separate logs.

---

## 5. H2 — Cognitive retrieval (C1/C4/C2/B + Tier-4; G1M-CORTEX shadow track opens)

**Objective:** Staged, winners-only retrieval uplift over frozen H1 — each mechanism ships behind a flag and earns
the default path only on paired evidence. BRIGHT is attacked here first as a query-time adapter (shadow), because
zero-lexical-overlap failure is semantic, not storage.

**Entry:** H1 CAP-GF GO; frozen baseline + capsule hash replay 100%.

**Work (cognitive definitions restored; owners are real files):**

- **B — owned gating-head log pipeline** (`retrieval.py` + eval harness): log co-retrieved pairs (+1),
  retrieved-but-ignored pairs (−1), contradiction pairs (repulsive). Trains the tiny owned discovery-affinity head;
  foreign priors (MoE gates, SAE latents) may enter only as `W_ij(0)` behind a flag and only on beating the hashing
  baseline head-to-head (routing accuracy + synthesis nDCG). Association edges never enter truth families.
- **C1 — bridge-first retrieval** (TOC/meta-node layer over `organization.py`): queries hit cluster-bridge nodes
  first, expand into member atoms second. Kill bar: recall parity at ≤50% of candidate atoms scored on 100
  cross-module probes.
- **C4 — contradiction-aware merge** (`retrieval.py` grounding verifier + typed edges): `contradicts/supports`
  edges score separately from similarity; contradicted candidates downweighted, conflict pair surfaced. Detection
  and merge-weighting ship as separate flags (kill bar: ≥80% conflict recall, <5% false-flag).
- **C2 — difficulty-routed budget** (lightweight lexical/length/entity classifier, no LLM): easy queries take
  BM25+RRF only; predicted multi-hop takes graph+TOC beam. Kill bar: P95 −20% with zero hard-slice nDCG regression.
- **Tier-4 [A4]:** local-SLM HyDE/decomposition adapter for BRIGHT/MuSiQue-hard, P95 ≤800 ms explicit budget with
  token/compute accounting. Shadow-first; promotes only on paired delta with CI excluding 0. Never touches the ≤50 ms
  interactive tiers.
- **Sizing [A3]:** raw candidate depth k ∈ [10,100]; L5 governor (8–20) applies to the final delivered bundle only.

**Exit-gate (Retrieval head, per mechanism):** GO (promote winner) / PARTIAL (promote winners, drop losers) /
NO-GO (ship H1 stack). Cold-recall and warm-latency tracked as independent PASS tracks — never traded without an
explicit ballot + rollback.

**Evidence:** per-mechanism paired deltas vs H1 baseline (seed 42, 10k bootstraps), Tier-4 cost/quality table,
cold-recall + warm-latency tables, 4-number storage re-log, ballot + rollback pointer.

**Risks:** cloud reranker leaking into the hot path (fail-closed HOLD); co-retrieval popularity laundered into
truth (edge-family separation enforced in schema, not convention).

---

## 6. H3 — Synthesis router + H4 — Consolidation/dreaming loop (Gate CAP-GG)

**Objective:** Offline dreaming substrate with quality/safety gates; rebuildable projections only; warm-default
economics. H3/H4 can never retroactively fail H2.

**Entry:** H1 CAP-GF green; H2 ballot recorded (any outcome); dream corpus hash pinned.

**Work (real surfaces only — the phantom `ActivationRouter` is gone):**

- **H3 warm router:** extend the real `ActivationEngine` (`activate`/`activate_two_pass`) and `TwoPassPPREngine`
  (`FROZEN_PPR_PRIORS`) in `src/trace/v2/cortex.py`, or add a new router module beside them — stated as work packet
  WP-H3-1, never as an existing class. Warm-default routing (replay/cached dream traces on hash match + quality-guard
  pass); cold path only on drift/guard-fail/explicit ablation, each cold call logging its reason. Same trace schema
  (I1); `release_id`-scoped rows invisible until CAP-GG.
- **H4 dreaming loop [A5-bounded]:** offline synthesis over bounded changed neighborhoods with **N≤250-doc
  micro-batches, lock-hold p100 <15 ms, 8–20 active holons** per cycle. C3 consolidate-on-repeat (cold hit twice →
  promoted to warm with full provenance + decay); C8 sleep-time distillation of mature modules only (kill bar:
  nDCG drop ≤0.005 with ≥30% warm-byte reduction, versioned rollback mandatory).
- **Guards:** dream-quality + hallucination/faithfulness/abstention gates; L7 re-checked; generative bridge
  hypotheses (if tried) ship as flagged non-truth atoms requiring C4 machinery first — last in build order.

**Exit-gate (CAP-GG ballot, Dreaming+CORTEX head):** GO → active release; NO-GO → ship H2 winners, dreaming stays
experimental. No L3 auto-promotion without explicit vote (I5).

**Evidence:** CAP-GG criteria sheet; C3/C8 ablation deltas; guard logs; warm/cold hit-rate + cost table; Spine
invariance proof (dropping projections leaves zero Spine-byte delta); ballot + rollback.

**Risks:** hallucinated dreams polluting Spine (blocked structurally by I3 projection-only); cold-path cost overrun
(mitigated by warm-default + logged reason).

---

## 7. Crosscutting — gates, eval, risk

- **Certification:** verifier receipts + dossiers bound to code/data/policy/environment/database/projection
  identities; independent verifier recomputes from the immutable evidence manifest. No runner prints
  CERTIFIED/APPROVED — only the human ballot does.
- **Stacked-gate rule:** no phase retroactively gates a prior phase. Each promotes via human ballot only. A
  downstream NO-GO never invalidates an upstream PASS.
- **Latency tiers:** T1–T2 interactive P95 ≤50 ms (L6, no LLM); Tier-4 ≤800 ms [A4]. Report p50/p95 per tier.
- **$0 hot path:** embedded SQLite + local BM25 + local MiniLM; zero paid calls on ingest→index→retrieve.
- **Storage accounting:** per-layer bytes on every commit with ceilings L1/L2/L3 + diagnostics A1/A2.
- **Risk register:** synthetic fallback, lock-hold breach, top-k breach, dense drift, graph fan-out, L3
  auto-promotion, cold-cost overrun — each tied to its owning gate's ballot + rollback.

---

## 8. Build order (cognitive definitions, not boilerplate)

**B → C1 → C4 → C2 → C3 → C8**, each behind a flag, each promoted only on its kill bar:

1. **B** — owned gating-head log pipeline starts now (value compounds).
2. **C1** — bridge-first retrieval (unlocks cross-discipline hops).
3. **C4** — contradiction-aware merge (prerequisite for trustworthy synthesis).
4. **C2** — difficulty-routed budget (buys headroom for the rest).
5. **C3** — consolidate-on-repeat (bounds warm at scale).
6. **C8** — sleep-time distillation (only once modules mature).
7. **Spikes, time-boxed, last:** MoE-gate vs SAE head-to-head (one winner max), per-module backpressure actuation,
   curiosity scheduling, generative bridge hypotheses.

---

## 9. Non-goals

- No L3 auto-promotion; no cloud hot-path even if BRIGHT tempts it; no silent schema drift.
- No 100M distributed-systems work (web-telemetry detour); no whole-system Rust/Go rewrite (surgical PyO3 kernels
  only after 1M gates freeze contracts and profiling names a measured SLO violation).
- No downstream bypass/re-implementation of the CORE loop; no Spine mutation by projections.
- No threshold tightening/loosening outside §2; amendments never retroactively alter the H0 contract.

---

## 10. Open items (ratified values)

- **OI-1 Goal statement** — OPEN; confirmed at H0 exit before H1 build.
- **OI-2 Tier-4 SLA ≤800 ms** — [A4]; constrains Tier-4 expectations only.
- **OI-3 Truth-plane bounds N=250 / <15 ms** — [A5] for H4; H1 ingest bound per L4 + §4 method.
- **OI-4 Candidate depth k∈[10,100], final bundle 8–20** — [A3] + L5.
- **OI-5 Tag discipline** — every A-number carries its `[AMENDMENT]` tag wherever it appears.
- **OI-6 100K consumer** — Wave E `CAP-INT02` sole authorized 100K consumer.
- **OI-7 Capsule binding** — adopt (not re-author) the staged 1M capsule; path normalization + gate signing in H0.
- **OI-8 Model tiers** — bind `DEC-CAP-MOD01-MODEL-TIERS-UPDATE` names; local-SLM champion chosen empirically;
  DeepSeek-V4-Flash strictly budget-capped (≤$5) comparator.

---

## 11. Immediate next actions (verified commands only)

All commands below were run with `--help` in this workspace before inclusion. `PYTHONPATH=src` where imports apply.

1. **Checksum the frozen BEIR splits (H0):**
   `python3 benchmarks/verify_dataset_checksums.py --manifest benchmarks/manifests/beir_musique_frozen_v1.json --root .`
2. **Verify the frozen retrieval baseline receipt (H1):**
   `python3 benchmarks/run_frozen_retrieval_baseline.py --verify-receipt --manifest benchmarks/manifests/beir_musique_frozen_v1.json --dossier docs/program/inbox/cap-ret04/retrieval_baseline_dossier.json --receipt docs/program/inbox/cap-ret04/verification_receipt.json`
3. **Preflight the 100K qualification harness (H1 pattern reference):**
   `python3 benchmarks/run_100k_qualification.py --preflight --manifest docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json --bootstrap-resamples 10000 --bootstrap-seed 42 --out-dir docs/program/inbox/cap-int02`
   (Full run needs its staged corpus + `psutil` installed — this env currently lacks `psutil`, so `--help` itself
   errors at import; flags above are pinned from source. Fix env or vendor the dependency before the gate run.)
4. **Work packets (deliverables, NOT runnable commands):** WP-H0-1 path normalization, WP-H0-2 gate signing +
   1M-verifier extension, WP-H1-1 parameterized 1M qualification runner, WP-H3-1 warm router beside
   `ActivationEngine`, Tier-4 adapter [A4], B log pipeline, C1/C4/C2/C3/C8 behind flags.
5. **Ballot each gate independently** (human, in `06_DECISION_LOG.md`): H0 PASS → H1 CAP-GF → H2 → H3/H4 CAP-GG.
   Stacked, never retroactive.

---

*End of TRACE Master Plan v1.1 — candidate for human ballot. No auto-promotion.*
