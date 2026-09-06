# Cortical Substrate V1 — Frozen Decisions & Build Plan

> Status: GOVERNING v1.1 — Promoted 2026-09-06 per CAP-D012 with Appendix A Tracked Residuals & Calibration Register.
> Authority: derives from `DEC-CAP-001`, `DEC-CAP-012`, `01_INVARIANTS.md`, `COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md`.
> Ratified by: Human Project Owner.

## 0. Frozen v1 decisions

### D1. Storage gate: total-hot <= 3.0x (promotion gate), durable <= 1.6x (health signal)
- Denominator = admitted UTF-8 raw content bytes (frozen per candidate).
- Report 4 numbers: durable / retrieval-hot / cortex-hot / total-hot. Gate on total-hot.
- Rationale: operator pays hot state; durable-only hid the 7.54x F2 failure.
- Tunable only by prospective policy amendment with measured per-component model, never post-hoc.
- Architectural storage allocation (estimated model; empirical proof required at P2 qualification gate):
  - Durable Cold (Spine): chunked block zstd (level 6) on raw events/atoms = 0.45x - 0.55x (passes <= 1.6x).
  - Retrieval-Hot (L0 Atom Table): single canonical copy in SQLite B-Tree = 1.05x.
  - Retrieval-Hot (FTS5 Index): external content table (`content='atom'`, `content_rowid='id'`) storing inverted postings `%_data` only with zero text duplication = 0.50x.
  - Cortex-Hot (L1 Holons): 384-d int8 unit vectors (384 B) + top-32 string tokens `lex_sig` + metadata = 0.75x.
  - Cortex-Hot (L2 TOC & Graph): compact CSR uint32 arrays + TOC centroids = 0.15x.
  - Operational Indexes: SQLite B-tree indices on `(file_id, start_byte)` and hashes = 0.10x.
  - Total-Hot Operational Footprint: estimated ~2.55x - 3.00x admitted bytes (must verify <= 3.0x gate empirically at P2).

### D2. Embedding pin: e5-small-v2 primary, MiniLM-L6-v2 control
- Primary: `intfloat/e5-small-v2`, 384-d, `local_files_only`, deterministic batching, int8 indexed.
- Metric space: strictly hyperspherical ($\mathbb{S}^{383}$). Centroids must be Fréchet-renormalized to unit length ($\|\mathbf{c}\|_2 = 1.0$) prior to int8 quantization and cosine similarity evaluation.
- Revision pin procedure: at freeze, record `model_rev` = HF commit sha + tokenizer/pooling config hash into `scale_policy.lock.json`; runner and verifier both load by digest and refuse on mismatch (no silent fallback to MiniLM or hash-vectors).
- Prefixes frozen (`passage: ` docs / `query: ` queries); prefix-strip/mismatch is a validation error, not a fallback.
- Control/fallback: `all-MiniLM-L6-v2` for ablations + degraded mode (no prefix).

### D3. Forgetting: three admission modes, one audit rule
- `archival` (default): admit all, immutable Spine, Cortex apoptosis only (hot forget, cold retain).
- `salient-only`: pre-Spine triage admits iff $S_{admit} = 0.70 \cdot \text{Novelty} + 0.30 \cdot \text{Utility} \ge \theta_{admit}$ (frozen $\theta_{admit} = 0.20$; note: supersedes legacy 0.15 multiplicative rule).
  - Novelty = prediction error $\Delta_{nov} = 1.0 - \max_{h \in L1} \cos(\mathbf{e}_{new}, \mathbf{c}_h)$.
  - Utility = Bayesian prior $\text{Utility}(d) = \gamma(N) \cdot 0.50 + (1 - \gamma(N)) \cdot U_{empirical}(d)$, where $\gamma(N) = \exp(-N / 1000)$ over corpus query count $N$.
  - Cold-start guard: first 1000 docs receive `PROBATIONARY_ADMIT` (bypassing triage) to establish baseline topology; high-novelty documents ($\Delta_{nov} \ge 0.29$) admit unconditionally on novelty alone.
  - Ignored docs recorded in `admission_log(doc_id, decision, reason, scores)`.
  - Reason codes (closed set): LOW_NOVELTY | LOW_UTILITY | POLICY_DENY | QUOTA_RING_EVICT.
- `streaming` (robot mind): bounded ring (default 10k docs or 1GB, frozen per profile), evict-lowest-energy with tombstone erasure event + consolidated L1 summary retained. Spine erasure only via auditable erasure event, never silent mutation.
- Invariant holds: no silent rewrite of history in any mode; drop/ignore counts reconcile against intake counts exactly.

### D4. L3 schemas: human-promoted, always
- SHADOW -> CANDIDATE -> PROMOTED by Human Owner only. Min bar: >=5 instantiations across >=3 docs + uplift/shadow evidence. Concrete nodes link to schema, never replaced.

## 1. Records (facet slots, no big vector)

No concatenated `[semantic|functional|topological]` vector. Each facet has its own store, clock, and engine. A micro rename touches L0 only; L1/L2 never flinch.

### L0 atom — episodic ground, immutable, cold NVMe / warm SSD
`atom(id INTEGER PRIMARY KEY, doc_id TEXT, file_id TEXT, start_byte INT, end_byte INT, content_hash BLOB, text TEXT)`
- Invariant: `text == normalized[start_byte:end_byte]`; BLAKE3/SHA-256 per span.
- Order is implicit: `WHERE file_id=? ORDER BY start_byte` — zero NEXT rows.
- Index: `(file_id, start_byte)`, `content_hash`. No embeddings at L0.
- External Content Lexical Index:
  `CREATE VIRTUAL TABLE fts_atoms USING fts5(text, content='atom', content_rowid='id', tokenize='porter unicode61 remove_diacritics 1');`
  Postings stored in `%_data`; text column NEVER duplicated in FTS5 shadow tables.

### L1 holon — operational unit, warm SSD
`holon(id, parent_toc, centroid_int8[384], lex_sig[top32_strings], spans[(file_id,s,e)*], energy, tier, status, version, anchor_model, anchor_prompt_hash, created_at)`
- `centroid_int8`: spherical Fréchet mean $\mathbf{c}_{unit} = \frac{\bar{\mathbf{c}}}{\|\bar{\mathbf{c}}\|_2}$ over member span embeddings ($\mathbf{e}_i \in \mathbb{S}^{383}$), symmetrically quantized: $\mathbf{q} = \operatorname{clip}(\operatorname{round}(\mathbf{c}_{unit} \times 127), -127, 127) \in \operatorname{int8}^{384}$.
- Centroid norm guard: pre-normalization norm $\frac{1}{|H|}\|\sum \mathbf{e}_i\|_2 \ge 0.60$; mergers causing vector cancellation below 0.60 are rejected.
- `lex_sig`: top-32 string tokens (stored as JSON array of strings to eliminate vocabulary registry drift).
- `spans[]`: bounded array for aliasing; maximum 8 spans per holon ($|spans| \le 8$).
- `energy = max(0.0, 1.0*hits_7d + 0.5*centrality - 0.02*age_days)` (weights frozen per profile).
- Newborn apoptosis grace: holons with `age_days < 7` are strictly exempt from apoptosis pruning (they remain subject to working-memory governor eviction).
- `version`: monotonic int per record, bumped on each rebuild; `status`: ACTIVE | DORMANT | DIRTY_CONTRACT; `tier`: nav (auto) vs factual (human).
- Grounding bar for auto-nav: 3-stage proposition verifier:
  1. Stage 1 (Deterministic Polarity): parity of negation markers ($\mathcal{N}$) and directionality antonym alignment; mismatch fails immediately (`POLARITY_INVERSION`).
  2. Stage 2 (Entity & Quantity Containment): all entities, symbols, and numbers in proposition $\Pi$ must satisfy $\mathcal{E}(\Pi) \subseteq \mathcal{E}(A)$; salient token recall $\ge 0.80$.
  3. Stage 3 (Sampled NLI Audit): local cross-encoder audit (`cross-encoder/nli-deberta-v3-small` pinned, local CPU execution, $0.00$ GPU cost) on 10% stratified sample; require $P(\text{contradiction}) < 0.01$ and $P(\text{entailment}) \ge 0.70$.

### L2 TOC node — routing partition, warm SSD + cached centroid
`toc(id, parent, c0_float[384], R0, members[L1*], boundary, status, version)`
- `c0` = unit centroid on $\mathbb{S}^{383}$; `R0` = max cosine distance $1.0 - (\mathbf{c}_0 \cdot \mathbf{h})$ over members, floored at $R_{0,eff}^{cos} = \max(R0, 0.05)$.
- `boundary`: centroid + radius + cohesion floor (intra-cluster Jaccard affinity $\ge 0.08$; min 1 shared salient term).
- Fan-out bound: members $\le 64$ per TOC node (strictly enforced non-negotiable structural bound).
- Splitting mechanics: when $|members| > 64$, partition via deterministic bisecting spherical 2-means. Seeds chosen by diametrical opposition ($\mathbf{s}_1 = \arg\max (1 - \mathbf{h} \cdot \mathbf{c}_0)$, $\mathbf{s}_2 = \arg\max (1 - \mathbf{h} \cdot \mathbf{s}_1)$) with members iterated in strictly sorted-ID order to guarantee deterministic tie-breaking.
- Cohesion deadlock resolution: if a split partition violates cohesion ($< 0.08$), reassign members to available neighbor TOC nodes; if no neighbor satisfies capacity and cohesion, assign to a `DIVERSE_OVERFLOW` TOC node under parent with `cohesion_floor = 0.0` and status `STALE_CENTROID`.
- `DIVERSE_OVERFLOW` governance: excluded from Tier 2 beam routing except as last resort prior to Tier 3 fallback; given first priority for re-splitting each sleep cycle; subject to a 30-day orphan apoptosis policy. Fan-out $\le 64$ is NEVER violated.

### L3 schema — grammar, hot RAM, shadow until promoted
`schema(id, slots, actions, invariants, transitions, instantiations[], support, status)` with `status`: SHADOW | CANDIDATE | PROMOTED (human only).
- Concrete L1/L2 nodes LINK to schema; never replaced by slot bindings.

### Edges — explicit non-contiguous only, CSR lean
`edge(src, dst, type, w)` where type in COMPILED_FROM | REFERENCES | SEE_ALSO | SUBSUMES | INSTANTIATES | MUTUALLY_EXCLUSIVE.
- $w \in [0, 1]$ conductance (Hebbian-updated).
- MUTUALLY_EXCLUSIVE edges stored with absolute weight $|w^-| \in [0, 1]$.
- Graph traversal engine implements Two-Pass Excitatory-Inhibitory Lateral Rectification PPR:
  - Pass 1: Excitatory diffusion over non-negative edges $E^+$ via power iteration ($\mathbf{p}^{(t+1)} = \alpha \mathbf{p}^{(t)} P^+ + (1 - \alpha) \mathbf{p}_0$). Guaranteed $\rho(P^+)=1$ and monotonic convergence.
  - Pass 2: Lateral inhibitory suppression: $s_{rect}(v) = \max(0, s^+(v) - \beta \cdot \max_{(u, v) \in E^-} (|w^-_{uv}| \cdot s^+(u)))$ with $\beta = 1.0$.
  - Rectification Divide-by-Zero Guard: if $\|\mathbf{s}_{rect}\|_1 \le 0$ (all candidates inhibited), fall back to excitatory baseline $\mathbf{s}^+$ (or return `insufficient_evidence` if confidence drops below threshold).
  - Rectified scores re-normalized: $\mathbf{s}_{final} = \mathbf{s}_{rect} / \|\mathbf{s}_{rect}\|_1$.
  - Zero matrix singularities; zero ghost activations; non-negative activations guaranteed.
- Degree cap 50 per node per type, 128 total per node across types. Flow (`NEXT/PRECEDES`) stays implicit in byte order.

## 2. Dynamics

### A. Intra-doc A-B-A aliasing (two-pass: fast lexical draft + async embedding refinement)
Per doc paragraphs $P_i$. Salient set $S_i$: len >= 3, not in english-stop, para-freq $\le \max(2, 0.4 \cdot n_{paras})$.
Smoothed Additive IDF (strictly positive, non-zero):
$$\operatorname{idf}_{doc}(t) = \ln\left(1 + \frac{n_{paras} - df_t + 0.5}{df_t + 0.5}\right) + 1.0$$
Fast Lexical Draft (Ingest Path):
Alias paragraph $P_i$ and $P_k$ iff:
`[score_lex(i, k) >= 2.0 AND |S_i ∩ S_k| >= 2] OR [HasSharedEntityOrSig(P_i, P_k) AND Jaccard(P_i, P_k) >= 0.30]`
where $\operatorname{score}_{lex}(i, k) = \sum_{t \in S_i \cap S_k} \operatorname{idf}_{doc}(t)$.
Async Embedding Refinement (Consolidation Pass):
Post-embedding, enforce complete-linkage & bounded diameter constraints:
- Maximum spans per holon: $|spans(H)| \le 8$.
- Centroid distance cap: $\cos(e(P_k), \mathbf{c}_H) \ge 0.70$.
- Pairwise diameter bound: $\min_{P_j \in spans(H)} \cos(e(P_k), e(P_j)) \ge 0.55$.
- Norm coherence floor: $\frac{1}{|H|+1}\|\sum_{P \in H \cup \{P_k\}} e(P)\|_2 \ge 0.60$.
Transitive closure is strictly prohibited; spans failing diameter or centroid bounds spawn a new holon linked via `SEE_ALSO`.

### B. Drift gate (no LLM)
On L1 update: compute hyperspherical cosine drift:
$$\Delta_{cos} = 1.0 - (\mathbf{c}_0 \cdot \mathbf{c}_{new})$$
where $\mathbf{c}_0$ and $\mathbf{c}_{new}$ are unit-normalized Fréchet means on $\mathbb{S}^{383}$.
Flag STALE_CENTROID iff $\Delta_{cos} > 0.25 \times R_{0,eff}^{cos}$ (where $R_{0,eff}^{cos} = \max(1.0 - \min_{h \in TOC}(\mathbf{c}_0 \cdot \mathbf{h}), 0.05)$); re-center in sleep.
L0 edit -> re-embed L1 -> check 3-stage proposition support: pass stops propagation; fail marks DIRTY_CONTRACT + queues immediate L2 parent only.
Track %STALE L2/week as boiling-frog monitor; alert iff weekly delta exceeds 5pp.

### C. Dual-dispatch routing (3-Tier Cascade & Promotion Gate)
Worst-case p95 latency budget: $\le 65\text{ms}$ ($5\text{ms} + 35\text{ms} + 25\text{ms}$).
1. **Tier 1 (Lexical Short-Circuit, <=5ms):**
   Trigger: quoted string | UPPER_SNAKE >= 3 | traceback | backticks.
   Action: query FTS5 on `fts_atoms` + holon `lex_sig` top-20.
   Success: hits >= 3 with BM25 score >= $\theta_{lex}$ -> expand L0 and return.
   Fallthrough: hits < 3 -> proceed to Tier 2.
2. **Tier 2 (Top-Down Hierarchical Beam, <=35ms):**
   Action: encode query via e5-small-v2 -> probe L2 TOC beam $K \le 20$ (excluding `DIVERSE_OVERFLOW`) -> filter candidate L1s -> Two-Pass PPR ($\le 2500$ steps).
   Success: confident candidates >= 3 with $\cos \ge 0.65$ -> expand L0 and return.
   Fallthrough: beam miss / candidates < 3 -> proceed to Tier 3.
   **Tier 2 Promotion Gate:** Tier 2 operates in SHADOW mode during v1 qualification and promotes to default path IF AND ONLY IF paired evaluation shows statistically significant uplift over Tier 3 flat hybrid with 95% bootstrap CI excluding 0.
3. **Tier 3 (Global Flat Hybrid Fallback, <=25ms):**
   Action: global dense kNN over all L1 centroids unioned with global BM25 over `fts_atoms`.
   Fusion: Reciprocal Rank Fusion $\operatorname{RRF}(d) = \frac{1}{60 + \operatorname{rank}_{dense}(d)} + \frac{1}{60 + \operatorname{rank}_{sparse}(d)}$.
   Success: top candidate has $\operatorname{RRF} \ge 0.012$ (or dense cosine $\ge 0.40$) -> expand L0 and return.
   Terminal: if Tier 3 also fails to find candidates passing $\theta_{floor}$ -> return explicit `insufficient_evidence` (never invent).
Governor caps retrieved set at 8-20 concepts. Mixed queries run short-circuit first, union with top-down L1s, capped at 20.

### D. Generations (Windows-Safe Epoch RCU)
- Immutable Generation Directories: compacted generations written to `generations/gen_{epoch}_{timestamp}/` containing `vectors.bin`, `fts_atoms.db`, `graph.csr`. Files are NEVER overwritten in-place.
- Authoritative SQLite Pointer Swap: active generation governed by single SQLite ACID table `active_generation(lock_id=1, epoch, gen_dir, promoted_at)`.
- Cross-Process SQLite Reader Leases: readers register active lease in SQLite table `active_reader_leases(pid INT, lease_id TEXT, epoch INT, acquired_at TIMESTAMP)`, preventing cross-process `WinError 32` file locking on active mmaps.
- Deferred Unlinking & WinError 32 Mitigation: retired generations enter `DORMANT_RETIRED` state for grace period $T_{grace} = 120\text{s}$ AND until active reader leases query count reaches zero. Unlink failures (`WinError 32`) are caught and deferred to next startup garbage sweep.
- Micro-Batched Ingestion Pipeline:
  - Commit batch size: $N = 250$ docs (or 1000 atoms / 100ms timeout), keeping write transactions $< 15\text{ms}$.
  - Bounded Ingest Queue: `maxsize = 16` batches between 8 parsers and single committer with cooperative backpressure.
  - Active WAL Checkpoint Throttling: passive checkpoint every 10 commits; if WAL $> 16\text{MB}$, pause intake up to 50ms and run `PRAGMA wal_checkpoint(RESTART)`; if WAL $> 64\text{MB}$, halt intake and run `PRAGMA wal_checkpoint(TRUNCATE)`.
  - Worker Staging DBs: 8 parsers write to thread-local staging DBs; single committer attaches and bulk inserts, eliminating concurrency lock contention.

## 3. Phases + acceptance gates

- P0 fixtures:
  - A-B-A doc (expect 2 holons, not 3).
  - Boilerplate-trap doc (Intro/Conclusion share 30% vocab, must NOT alias).
  - Small doc fixture ($n_{paras}=2$, exact entity match, must alias without zero-division).
  - Negation inversion trap doc ("strictly prohibits" vs "strictly permits", proposition verifier must FAIL).
  - Windows concurrency fixture (concurrent reader mmap during generation pointer swap must succeed without WinError 32).
  - Calibration register calibration run (fit Appendix A uncalibrated constants).
  - Symbol-vs-concept query pack.
- P1 (`atomizer.py`, `assemble_10k_clusters.py:185-205`):
  - Aliasing engine with smoothed IDF + complete-linkage diameter cap (max 8 spans, cosine >= 0.70, pairwise >= 0.55).
  - Spans provenance (`content==normalized[s:e]` per span) + zero cross-doc slices.
  - Centroid coherence norm check ($\ge 0.60$).
- P2 (`organization.py:225,237-238,255`, retrieval):
  - Deterministic bisecting spherical 2-means TOC splitting with diametrical seeds and sorted-ID tie breaking.
  - Cohesion deadlock fallback handling (fanout bound $\le 64$ strictly verified; `DIVERSE_OVERFLOW` excluded from beam).
  - Two-Pass Non-Negative Excitatory-Inhibitory PPR with divide-by-zero suppression guard.
  - 3-Tier Dual-Dispatch retrieval engine (Tier 1 <=5ms, Tier 2 <=35ms, Tier 3 fallback <=25ms, p95 <= 65ms).
  - Windows-Safe Epoch RCU generation swapping with SQLite lease tracking and deferred unlinking.
  - Storage Gate Verification: total-hot <= 3.0x admitted bytes measured empirically; durable Spine <= 1.6x.
- P3 (shadow):
  - Schema induction (|V|<=5, >=5 insts/>=3 docs).
  - Bayesian salient-only admission triage with cold-start probationary quota.
  - Tier 2 paired uplift certification vs Tier 3 control (95% bootstrap CI > 0).
  - Qualification runner with psutil + real disk bytes (mocks completely removed).
- Eval locks per candidate: bootstrap seed 42 with 10k resamples; ablation matrix BM25-only / dense-only / RRF / +graph / +TOC with paired 95% CIs; thresholds frozen in `scale_policy.lock.json`.
- Spec versioning: any threshold/schema change mints a new plan version + migration note; old candidates stay bound to their frozen policy digest.
- Each phase: frozen inputs -> isolated run -> detached verification -> decision.

---

## Appendix A: Tracked Residuals & Calibration Register

The following 13 items are binding governance invariants, tracking uncalibrated prior constants, edge-case guards, and promotion criteria across the build phases:

| # | Item / Subsystem | Phase Owner | Prior Value / Policy | Hard Acceptance & Calibration Criteria |
|---|---|---|---|---|
| **1** | **PPR Suppression Divide-by-Zero** | P2 (Retrieval) | $\|\mathbf{s}_{rect}\|_1 \le 0$ fallback | If all nodes suppressed by inhibition, engine must fall back to excitatory baseline $\mathbf{s}^+$ without throwing NaN or division-by-zero. |
| **2** | **Cross-Process Windows Leases** | P2 / P3 (Storage) | In-memory refcount $\to$ SQLite table | Leases tracked in `active_reader_leases(pid, lease_id, epoch)`. Multi-process stress test must verify 0 `WinError 32` crashes on Windows NTFS during generation swaps. |
| **3** | **Two-Pass Aliasing Order** | P1 (Atomizer) | Lexical fast-path $\to$ Async embedding | Ingestion path runs lexical draft (smoothed IDF + entity match); cosine diameter bounds ($\ge 0.70$ centroid, $\ge 0.55$ pairwise) enforce during async consolidation. |
| **4** | **`DIVERSE_OVERFLOW` Governance** | P2 / P3 (Cortex) | Cohesion 0.0 overflow policy | Excluded from Tier 2 beam search; re-split attempted first during each sleep cycle; pruned after 30 days if orphaned. |
| **5** | **Explicit Latency SLO** | P2 (Retrieval) | Unstated worst-case $\to$ $\le 65\text{ms}$ | Enforce strict p95 $\le 65\text{ms}$ across full 3-tier cascade under benchmark load. |
| **6** | **Stage-3 NLI Model & Budget** | P2 / P3 (Grounding) | Pinned CPU cross-encoder | `cross-encoder/nli-deberta-v3-small` pinned; 10% stratified sample; budgeted at $\le 15\text{ms}$/doc on CPU ($0.00$ GPU spend). |
| **7** | **Calibration Register (Priors)** | P0 (Calibration) | ~12 uncalibrated priors | P0 fixture pack must fit: lexical score floor (2.0), Jaccard (0.30), centroid/pairwise cosines (0.70/0.55/0.60), $\beta=1.0$, RRF floor (0.012), drift $\epsilon=0.25$, lease grace (120s), batch size (250). |
| **8** | **D3 Admission Threshold Semantics** | P3 (Admission) | $\theta=0.15$ (mult) $\to$ $\theta=0.20$ (add) | Formally record legacy 0.15 multiplicative threshold as superseded by $0.70 \cdot \text{Nov} + 0.30 \cdot \text{Util} \ge 0.20$. |
| **9** | **Newborn Holon Apoptosis Grace** | P2 / P3 (Cortex) | Zero initial energy starvation | Energy formula floored at 0.0; newborn holons granted 7-day immunity from apoptosis pruning. |
| **10** | **`lex_sig` String Representation** | P1 / P2 (Storage) | uint16 IDs $\to$ top-32 strings | Stored as JSON array of top-32 strings to prevent vocabulary ID registry drift. |
| **11** | **Tier 2 Uplift Promotion Gate** | P3 (Qualification) | Shadow until uplift proven | Tier 2 hierarchical beam search promotes to default path IF AND ONLY IF paired evaluation proves statistically significant uplift over Tier 3 flat hybrid (95% CI > 0). |
| **12** | **Overflow Node Beam Exclusion** | P2 (Retrieval) | Diffuse centroid routing bias | Tier 2 beam probe explicitly excludes `DIVERSE_OVERFLOW` nodes from candidate beam paths. |
| **13** | **Deterministic 2-Means Tie-Breaks** | P2 (Organization) | Arbitrary dict order $\to$ Sorted ID | Bisecting spherical 2-means iterates members in strictly sorted `holon_id` order to eliminate non-deterministic partition drift. |
