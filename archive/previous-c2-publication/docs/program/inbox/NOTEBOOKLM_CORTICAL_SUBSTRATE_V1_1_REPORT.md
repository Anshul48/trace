# Comprehensive Architectural Review, Codebase Audit & Finalized Google NotebookLM Curriculum Package (Cortical Substrate V1.1 Governing)

**To:** Parent Coordinator (`c1b6c7a8-c71f-4910-9e5b-f6a834befceb`)  
**From:** Independent Reviewer & Systems Subagent  
**Date:** 2026-09-06  
**Subject:** Critical Review of Prior Investigation, Codebase Verification, Theoretical Synthesis, and Finalized Google NotebookLM Curriculum for Cortical Substrate V1.1 (`DEC-CAP-012`)

---

## 1. Critical Audit of the Prior Investigation (What Was Wrong & What Was Corrected)

A rigorous, line-by-line verification of the codebase and project records reveals that while the prior investigator captured the high-level narrative of the `DEC-CAP-012` promotion, their report contains critical inaccuracies, misattributed code paths, incomplete mathematical explanations, and a fundamental violation of the user's primary prompt constraint.

### 1.1 Itemized Error & Verification Matrix

| # | Prior Investigation Claim | Evidence Cited | What the Codebase / History Actually Shows | Corrected Finding & Rationale |
|---|---|---|---|---|
| **1** | **NotebookLM Focus:** Dedicated Module 1 and Source 1 of the NotebookLM package to the abandoned local SLM bake-off (Gemma 26B, Qwen 27B, Ollama, laptop GPU bottlenecks). | Prior Attempt Section 3.1 & 3.2 | The user explicitly instructed: *"its important that googl notebook only focus on the finalized plans and not reiterate the old ones."* | **Violation of Core Prompt Directive.** Ingesting deprecated bake-offs and failed models into Google NotebookLM pollutes the generated audio overviews, study guides, and Q&A. Bespoke sources must be 100% dedicated to the finalized governing architecture (v1.1). |
| **2** | **SQLite Storage & FTS5 Bloat:** Claimed `src/trace/v2/store.py:30` duplicates text in standard SQLite FTS5 shadow tables, causing $7.54\times$ bloat. | `src/trace/v2/store.py:30` | A ripgrep search for `fts5` across `src/trace/v2/store.py` returns **0 results**. FTS5 does not exist in `store.py` yet. In `06_DECISION_LOG.md#L448` and `SCALE_100K_TO_1M_EXECUTION_PLAN.md#L74`, the $7.54\times$ bloat occurred in Gate F2 (14.14 GB database on 2.01 GB text) due to uncompressed event payloads and raw text triplication. | **Conflated Historical Gate F2 Failure with Current Code.** `store.py` currently has no FTS5 table. WP2 must proactively implement an *external content* FTS5 table (`content='atom'`, `content_rowid='id'`) to prevent introducing text duplication in the new index. |
| **3** | **Current Retrieval Implementation:** Described retrieval as "Single-tier hybrid RRF with hashing fallback embedder". | `src/trace/v2/retrieval.py:76-140` | In `src/trace/v2/retrieval.py:390-415`, `HybridRetrievalEngine._bm25()` executes in-memory Python `Counter` term tokenization over the entire atom set on every single query (`frequencies = {item["atom_version_id"]: Counter(tokens(item["content"]))}`). | **Severe Latency & Memory Bottleneck in Baseline.** Retrieval does not query an indexed engine; it performs dynamic dictionary BM25 in Python. Migrating to SQLite external FTS5 is essential to satisfy the Tier 1 $\le 5\text{ms}$ SLA. |
| **4** | **Intra-Doc Aliasing on Small Docs:** Described RSJ-IDF thresholding without explaining how 2-paragraph documents avoid zero-division or threshold starvation. | `CORTICAL_SUBSTRATE_V1_PLAN.md:100-105` | For $n_{paras}=2$ and $df_t=2$, $\operatorname{idf}_{doc}(t) = \ln(1 + \frac{2-2+0.5}{2+0.5}) + 1.0 = \ln(1.2) + 1.0 \approx 1.182$. A single shared term scores $1.182 < 2.0$ and fails the lexical threshold. | **Omitted Mathematical Synergy of Disjunctive Clause.** Aliasing on small documents succeeds because of the disjunctive second clause: `[HasSharedEntityOrSig(P_i, P_k) AND Jaccard(P_i, P_k) >= 0.30]`, bypassing the lexical score floor when entities match. |
| **5** | **Windows Epoch RCU Mechanics:** Stated that SQLite leases eliminate `WinError 32` without detailing the kernel-level locking mechanism or transaction lifecycle. | `CORTICAL_SUBSTRATE_V1_PLAN.md:141-145` | On Windows NTFS, `mmap` locks physical file pages at the OS kernel level. Calling `os.unlink()` raises `WinError 32`. SQLite WAL mode allows concurrent readers, but physical compaction file cleanup requires deferred grace periods and active lease refcounts. | **Incomplete Concurrency Analysis.** Explained below: compactor polls `active_reader_leases`, delays unlinking for $T_{grace}=120\text{s}$, catches `OSError(winerror=32)`, and defers remaining unlinks to startup GC sweeps. |
| **6** | **Omission of Critical Governing Systems:** Completely omitted the Working Memory Governor, the Boiling-Frog Stale TOC Monitor, and WAL Micro-Batching Invariants. | `CORTICAL_SUBSTRATE_V1_PLAN.md:120, 139, 146-150` | Plan v1.1 mandates an 8–20 concept working memory cap, a 5pp weekly delta alert on stale TOCs, commit batches of $N=250$ docs, and active WAL checkpoints at 16MB/64MB. | **Significant Architectural Omission.** Added to the unified architectural deconstruction and NotebookLM bespoke sources. |

---

## 2. Exhaustive Technical Deconstruction of Governing Architecture V1.1

### 2.1 The Holonic Brain Hierarchy (Koestlerian Holarchy)
*Theoretical Foundation:* Arthur Koestler (*The Ghost in the Machine*, 1967) introduced the concept of the **holon**—an entity that acts as an autonomous whole relative to its subparts, while simultaneously acting as an integrated part relative to its macroscopic container.
Project Trace organizes memory across 4 discrete physical and semantic strata:
1. **L0 Episodic Ground (Cold NVMe / Spine WAL):**
   - Schema: `atom(id INTEGER PRIMARY KEY, doc_id TEXT, file_id TEXT, start_byte INT, end_byte INT, content_hash BLOB, text TEXT)`.
   - Core Invariant: $\text{text} == \text{normalized\_source}[\text{start\_byte} : \text{end\_byte}]$.
   - Storage Mechanics: Narrative flow is preserved implicitly via `ORDER BY start_byte ASC`. Hardware performs sequential $O(1)$ block reads. Storing explicit `NEXT` pointer rows (such as `src/trace/v2/store.py:30`) is strictly prohibited.
   - Postings Index: External content SQLite FTS5 table (`content='atom', content_rowid='id'`). Postings reside in `%_data`; raw text is never duplicated.
2. **L1 Operational Holons (Warm SSD / Segmented Index):**
   - Schema: `holon(id, parent_toc, centroid_int8[384], lex_sig[top32_strings], spans[(file_id,s,e)*], energy, tier, status, version)`.
   - Metric Space: Embeddings live on the unit hypersphere $\mathbb{S}^{383}$. Centroids are calculated as spherical Fréchet means:
     $$\mathbf{c}_{unit} = \frac{\bar{\mathbf{c}}}{\|\bar{\mathbf{c}}\|_2} \quad \text{where } \bar{\mathbf{c}} = \frac{1}{|H|}\sum_{P \in H} \mathbf{e}(P)$$
   - Centroid Coherence Norm Floor: Mergers or additions must satisfy $\frac{1}{|H|}\|\sum \mathbf{e}_i\|_2 \ge 0.60$. If destructive vector cancellation drops the norm below 0.60, the merger is rejected.
   - Quantization: Symmetrically quantized to signed 8-bit integers:
     $$\mathbf{q} = \operatorname{clip}(\operatorname{round}(\mathbf{c}_{unit} \times 127), -127, 127) \in \operatorname{int8}^{384}$$
     Yields exactly 384 bytes per holon (a 75% reduction vs float32).
   - Lexical Signature: `lex_sig` is serialized as a JSON array of top-32 strings, preventing vocabulary ID table desynchronization across rebuilt generations.
   - Bounded Span Aliasing: Maximum 8 spans per holon ($|spans| \le 8$).
   - Hebbian Energy & Newborn Immunity:
     $$E(h) = \max(0.0, \, 1.0 \cdot \text{hits}_{7d} + 0.5 \cdot \text{centrality} - 0.02 \cdot \text{age}_{days})$$
     *Newborn Apoptosis Grace:* Holons with $\text{age}_{days} < 7$ are strictly exempt from background apoptosis pruning, ensuring new knowledge is not purged before query reinforcement can occur.
3. **L2 Macro-Topology (TOC-DAG / Warm SSD + Hot Centroid Cache):**
   - Schema: `toc(id, parent, c0_float[384], R0, members[L1*], boundary, status, version)`.
   - Structural Fanout Invariant: Every TOC node has $\le 64$ members.
   - Effective Cosine Radius: $R_{0,eff}^{cos} = \max(1.0 - \min_{h \in TOC}(\mathbf{c}_0 \cdot \mathbf{h}), \, 0.05)$.
   - Partitioning Mechanics: When $|members| > 64$, split via Deterministic Bisecting Spherical 2-Means. Seeds are chosen by diametrical opposition:
     $$\mathbf{s}_1 = \arg\max_{h \in TOC} (1 - \mathbf{h} \cdot \mathbf{c}_0), \quad \mathbf{s}_2 = \arg\max_{h \in TOC} (1 - \mathbf{h} \cdot \mathbf{s}_1)$$
     Tie-breaking iterates members in strictly sorted `holon_id` order to eliminate non-deterministic partition drift.
   - `DIVERSE_OVERFLOW` Governance: If a partition fails the cohesion floor (Jaccard affinity $< 0.08$) and neighbor TOCs lack capacity, members are placed in a `DIVERSE_OVERFLOW` node (`cohesion_floor = 0.0`, status `STALE_CENTROID`). These nodes are strictly excluded from Tier 2 beam probes, re-split first during sleep cycles, and pruned after 30 days if orphaned.
4. **L3 Invariant Schemata (Hot RAM / <5MB):**
   - Schema: $\langle \text{Slots}, \text{Actions}, \text{Invariants}, \text{State Transitions} \rangle$.
   - Human Owner Promotion Only: `SHADOW` $\to$ `CANDIDATE` $\to$ `PROMOTED`. Requires $\ge 5$ instantiations across $\ge 3$ distinct documents. Concrete L1/L2 nodes link to schemas; schemas never overwrite or erase episodic facts.

---

### 2.2 Event Segmentation Theory (EST) & Intra-Doc A-B-A Aliasing
*Theoretical Foundation:* Cognitive psychology (Zacks et al., 2007; Kurby & Zacks, 2008) demonstrates that human perception segments continuous reality into discrete event models. Boundaries are established when internal prediction error ($\Delta_{\text{error}}$) spikes.
- **The Defect in Legacy Trace:** Fixed 1200-character regex chunking (`src/trace/v2/atomizer.py:87-116`) combined with flattened contiguous triple slicing ($N=3$) across document boundaries (`benchmarks/assemble_10k_clusters.py:201-205`) created "Frankenstein clusters" that fused unrelated documents.
- **The Two-Pass Intra-Doc Aliasing Solution:**
  1. *Fast Lexical Draft (Ingestion Path):* Aliases paragraph $P_i$ and $P_k$ within the same document if and only if:
     $$[\operatorname{score}_{lex}(i, k) \ge 2.0 \land |S_i \cap S_k| \ge 2] \lor [\text{HasSharedEntityOrSig}(P_i, P_k) \land \operatorname{Jaccard}(P_i, P_k) \ge 0.30]$$
     where salient set $S_i$ includes non-stopword tokens of length $\ge 3$ with paragraph frequency $\le \max(2, 0.4 \cdot n_{paras})$, using Smoothed Additive Robertson-Spärck-Jones IDF:
     $$\operatorname{idf}_{doc}(t) = \ln\left(1 + \frac{n_{paras} - df_t + 0.5}{df_t + 0.5}\right) + 1.0$$
     The additive $+1.0$ guarantees strictly positive IDF ($\ge 1.0$) even when $df_t = n_{paras}$, preventing division by zero or negative weights on small documents.
  2. *Async Embedding Refinement (Consolidation Pass):* Complete-linkage diameter constraints ensure semantic tightness:
     - Maximum 8 spans per holon ($|spans(H)| \le 8$).
     - Centroid distance cap: $\cos(\mathbf{e}(P_k), \mathbf{c}_H) \ge 0.70$.
     - Pairwise diameter bound: $\min_{P_j \in spans(H)} \cos(\mathbf{e}(P_k), \mathbf{e}(P_j)) \ge 0.55$.
     - Coherence norm floor: $\frac{1}{|H|+1} \|\sum_{P \in H \cup \{P_k\}} \mathbf{e}(P)\|_2 \ge 0.60$.
  - *Strict Document Boundary:* Aliasing across document boundaries is strictly forbidden. Transitive chaining is prohibited. Spans violating diameter bounds spawn a new holon linked via `SEE_ALSO`.

---

### 2.3 Tripartite Cognitive Vectors & Decoupled Facet Slots
Plan v1.1 explicitly forbids monolithic concatenated `[semantic | functional | topological]` vectors:
1. **The Invalidation Domino Effect:** If lexical, functional, and semantic features are concatenated into a 576-d vector, a trivial code rename at L0 alters lexical hashes, shifting the entire vector and invalidating HNSW graph neighborhoods across the database.
2. **Metric Incompatibility:** Dense semantic cosine distance ($\mathbb{S}^{383}$), discrete graph hop distance, and BM25 term frequencies cannot be combined linearly without distorting metric spaces.
3. **Decoupled Facet Slots:**
   - **Lexical Facet:** Managed by external content SQLite FTS5 (`fts_atoms`).
   - **Semantic Facet:** Managed by Fréchet unit vectors on $\mathbb{S}^{383}$ (`e5-small-v2`).
   - **Topological Facet:** Managed by compact Compressed Sparse Row (CSR) adjacency arrays.
   - **Relational/Temporal Facet:** Managed by SQLite B-tree tables.
   An L0 edit updates FTS5 only; L1 centroids and L2 TOC nodes remain untouched.

---

### 2.4 Silicon-Native Sparsity & Windows-Safe Epoch RCU
1. **External Content FTS5 (`content='atom', content_rowid='id'`):** Eliminates SQLite's internal `%_content` shadow table, storing inverted postings `%_data` only. Reduces FTS index footprint to $\approx 0.50\times$ and completely avoids text duplication.
2. **Compact CSR Adjacency Graph:** Explicit edges (`COMPILED_FROM`, `REFERENCES`, `SEE_ALSO`, `SUBSUMES`, `INSTANTIATES`, `MUTUALLY_EXCLUSIVE`) are stored as contiguous uint32 arrays (`indptr`, `indices`, `data`). Caps degree at 50 per type, 128 total.
3. **Windows-Safe Epoch RCU (Eliminating `WinError 32`):**
   - Problem: On Windows NTFS, memory-mapped files (`mmap`) hold OS kernel locks. Calling `os.unlink()` or `shutil.rmtree()` on an active index file raises `WinError 32: The process cannot access the file because it is being used by another process`.
   - Solution: Compacted generations are written to immutable directories: `generations/gen_{epoch}_{timestamp}/`.
   - Pointer Swap: Atomic single-row transaction in SQLite: `active_generation(lock_id=1, epoch, gen_dir, promoted_at)`.
   - Reader Leases: Active readers register in SQLite: `active_reader_leases(pid, lease_id, epoch, acquired_at)`.
   - Deferred Unlinking: Retired generations transition to `DORMANT_RETIRED`. Compactor unlinks only when `SELECT count(*) FROM active_reader_leases WHERE epoch = ?` equals 0 AND grace period $T_{grace} \ge 120\text{s}$ has elapsed. Any caught `OSError` with `winerror == 32` is deferred to startup GC.
4. **Micro-Batched Ingestion Pipeline & WAL Throttling:**
   - Commit batch size: $N = 250$ docs (or 1,000 atoms / 100ms timeout), keeping transactions $< 15\text{ms}$.
   - Bounded Queue: `maxsize = 16` batches between 8 parsers and a single committer.
   - WAL Checkpoint Throttling: If WAL exceeds 16MB, pause intake up to 50ms and execute `PRAGMA wal_checkpoint(RESTART)`. If WAL exceeds 64MB, halt intake and execute `PRAGMA wal_checkpoint(TRUNCATE)`.
   - Worker Staging DBs: 8 parsers write to thread-local staging DBs; committer attaches and bulk-inserts, eliminating SQLite write lock contention.

---

### 2.5 The Holonic Lagrangian & Traversal Dynamics
Memory admission and graph diffusion are formalized as a constrained dynamic optimization:
$$\mathcal{L}_{holon} = \text{Utility}(H) - \lambda_{storage} \cdot \text{Cost}_{storage}(H) - \mu_{latency} \cdot \text{Cost}_{traversal}(H) - \nu \cdot \Delta_{drift}(H)$$
- $\lambda_{storage}$: Shadow price of storage capacity (escalates sharply as hot storage approaches the $3.0\times$ gate).
- $\mu_{latency}$: Shadow price of traversal latency (escalates as query time approaches the 65ms budget).
- $\nu$: Stability penalty against hyperspherical centroid drift.

1. **Bayesian Salient-Only Admission Triage:**
   Pre-Spine triage admits document $d$ if and only if:
   $$S_{admit} = 0.70 \cdot \text{Novelty} + 0.30 \cdot \text{Utility} \ge 0.20$$
   where $\Delta_{nov} = 1.0 - \max_{h \in L1} \cos(\mathbf{e}_{new}, \mathbf{c}_h)$, and $\text{Utility}(d) = \gamma(N) \cdot 0.50 + (1 - \gamma(N)) \cdot U_{empirical}(d)$ with $\gamma(N) = \exp(-N / 1000)$. First 1,000 documents receive `PROBATIONARY_ADMIT`; high novelty documents ($\Delta_{nov} \ge 0.29$) admit unconditionally.
2. **Hyperspherical Cosine Drift Gating:**
   When member atoms update, centroid drift is measured:
   $$\Delta_{cos} = 1.0 - (\mathbf{c}_0 \cdot \mathbf{c}_{new})$$
   If $\Delta_{cos} > 0.25 \times R_{0,eff}^{cos}$, the TOC node is marked `STALE_CENTROID` and scheduled for sleep-cycle re-centering.
   *Boiling-Frog Monitor:* Track `%STALE L2 / week`. Alert if weekly delta exceeds 5 percentage points.
3. **Two-Pass Excitatory-Inhibitory Lateral Rectification PPR:**
   Standard PPR with negative weights causes divergent power iterations and negative probabilities. Trace solves this with a two-pass algorithm:
   - *Pass 1 (Excitatory Diffusion):* Power iteration over non-negative edges $E^+$:
     $$\mathbf{p}^{(t+1)} = \alpha \mathbf{p}^{(t)} P^+ + (1 - \alpha) \mathbf{p}_0 \quad (\alpha = 0.85, \le 20 \text{ iterations}, \le 2500 \text{ steps})$$
     Guarantees spectral radius $\rho(P^+)=1$ and monotonic convergence.
   - *Pass 2 (Lateral Inhibitory Suppression):*
     $$s_{rect}(v) = \max\left(0, \, s^+(v) - \beta \cdot \max_{(u, v) \in E^-} (|w^-_{uv}| \cdot s^+(u))\right) \quad (\beta = 1.0)$$
   - *Rectification Divide-by-Zero Guard:* If all candidates are suppressed ($\|\mathbf{s}_{rect}\|_1 \le 0$), fall back to excitatory baseline $\mathbf{s}^+$ (or emit `insufficient_evidence`).
   - *Renormalization:* $\mathbf{s}_{final} = \mathbf{s}_{rect} / \|\mathbf{s}_{rect}\|_1$. Zero singularities, zero ghost activations.

---

### 2.6 3-Tier Dual-Dispatch Retrieval Cascade & Promotion Governance
Worst-case p95 latency budget: $\le 65\text{ms}$ ($5\text{ms} + 35\text{ms} + 25\text{ms}$).
1. **Tier 1 (Lexical Short-Circuit, $\le 5\text{ms}$):** Triggers on exact quotes, `UPPER_SNAKE` identifiers, tracebacks, or code syntax. Queries SQLite FTS5 `fts_atoms` + holon `lex_sig` top-20. If $\ge 3$ hits pass BM25 floor $\theta_{lex}$, expands L0 and returns.
2. **Tier 2 (Top-Down Hierarchical Beam, $\le 35\text{ms}$):** Encodes query via `e5-small-v2` (`query: ` prefix) $\to$ probes top-20 L2 TOC centroids (excluding `DIVERSE_OVERFLOW`) $\to$ filters member L1s $\to$ executes Two-Pass PPR. If $\ge 3$ candidates pass $\cos \ge 0.65$, expands L0 and returns.
   - *Tier 2 Promotion Gate:* Tier 2 operates in **SHADOW mode** during qualification. It promotes to default path IF AND ONLY IF paired evaluation proves statistically significant uplift over Tier 3 flat hybrid (95% bootstrap CI > 0).
3. **Tier 3 (Global Flat Hybrid Fallback, $\le 25\text{ms}$):** Global dense kNN over all L1 centroids unioned with global BM25 via Reciprocal Rank Fusion:
   $$\operatorname{RRF}(d) = \frac{1}{60 + \operatorname{rank}_{dense}(d)} + \frac{1}{60 + \operatorname{rank}_{sparse}(d)}$$
   If top candidate has $\operatorname{RRF} \ge 0.012$ (or dense $\cos \ge 0.40$), expands L0 and returns.
   - *Provable Abstention:* If Tier 3 fails to meet $\theta_{floor}$, emits `insufficient_evidence` and abstains. Never hallucinates.
4. **Working Memory Governor:** Caps final retrieved set to 8–20 concepts. Mixed queries union Tier 1 and Tier 2 results, strictly capped at 20 concepts.
5. **3-Stage Proposition Grounding Verifier:**
   - *Stage 1 (Deterministic Polarity):* Parity of negation markers ($\mathcal{N}$) and directionality antonym alignment. Mismatches fail immediately (`POLARITY_INVERSION`).
   - *Stage 2 (Entity & Quantity Containment):* All entities and numerical values in proposition $\Pi$ must satisfy $\mathcal{E}(\Pi) \subseteq \mathcal{E}(A)$; salient token recall $\ge 0.80$.
   - *Stage 3 (Sampled NLI Audit):* Local cross-encoder (`cross-encoder/nli-deberta-v3-small` running on CPU) audits a 10% stratified sample. Requires $P(\text{contradiction}) < 0.01$ and $P(\text{entailment}) \ge 0.70$. Budget: $\le 15\text{ms}$/doc on CPU.

---

## 3. Finalized Google NotebookLM Curriculum & Bespoke Sources (100% Finalized Plans)

Per the user's explicit directive (*"its important that googl notebook only focus on the finalized plans and not reiterate the old ones"*), this curriculum and source package is 100% focused on the governing Cortical Substrate V1.1 architecture. All deprecated local SLM sweeps and obsolete designs have been eliminated.

### 3.1 Course Syllabus

```text
================================================================================
COURSE SYLLABUS: PROJECT TRACE CORTICAL SUBSTRATE (V1.1 GOVERNING)
================================================================================
Target Audience: Advanced AI Systems Researchers, Cognitive Architects, Core Systems Engineers
Prerequisites: Differential Topology & Hyperspherical Spaces, Information Retrieval (BM25/RRF),
              Operating Systems (RCU, Page Cache, Memory-Mapped I/O), Spectral Graph Theory

MODULE 1: The Holonic Brain & Multi-Tier Memory Hierarchy
  - 1.1 Koestlerian Holarchy: The Janus Effect in Biological & Computational Cognitive Systems
  - 1.2 L0 Episodic Ground: Byte-Exact Spine WAL, Natural Hardware Ordering, and O(1) Sequential Scans
  - 1.3 L1 Operational Holons: Bounded Spans, int8 Quantization on S^383, and Hebbian Energy Landscapes
  - 1.4 L2 Macro-Topology: TOC Centroids, Effective Radii, and Strict Fanout Invariants (<= 64)
  - 1.5 L3 Invariant Schemata: Parametric State Grammars, Subgraph Isomorphism, and Human Governance

MODULE 2: Event Segmentation Theory (EST) & Intra-Document Aliasing
  - 2.1 The Cognitive Failure of Arbitrary Chunking: Prediction Error Boundaries vs Fixed Windows
  - 2.2 Mathematical Guarantee: Complete Elimination of Cross-Document Frankenstein Clusters
  - 2.3 Fast Lexical Draft: Smoothed Additive Robertson-Spärck-Jones IDF & Disjunctive Entity Aliasing
  - 2.4 Async Embedding Refinement: Complete-Linkage Diameter Constraints & Fréchet Norm Floors

MODULE 3: Tripartite Facets, Silicon-Native Compaction & Windows Epoch RCU
  - 3.1 Decoupled Cognitive Facets: Why Monolithic Concatenated Vectors Invalidate Indexes
  - 3.2 External Content SQLite FTS5: Zero Text Duplication & 0.50x Postings Storage
  - 3.3 Symmetric Fréchet Quantization on S^383: Compressing Vector State to Exactly 384 Bytes
  - 3.4 Windows-Safe Epoch RCU: Eliminating NTFS WinError 32 via SQLite Leases and Deferred Unlink
  - 3.5 Micro-Batched Ingestion Pipeline & Active WAL Checkpoint Throttling

MODULE 4: The Holonic Lagrangian & Dynamical Graph Traversal
  - 4.1 Memory Equilibrium: The Holonic Lagrangian Optimization Function & Shadow Prices
  - 4.2 Bayesian Salient-Only Admission Triage: Prediction Error Novelty & Prior Utility
  - 4.3 Deterministic Bisecting Spherical 2-Means: Diametrical Seeding & Sorted-ID Tie Breaking
  - 4.4 Hyperspherical Cosine Drift Gating & Boiling-Frog Stale TOC Monitoring
  - 4.5 Two-Pass Excitatory-Inhibitory Lateral Rectification PPR with Divide-by-Zero Suppression Guard

MODULE 5: 3-Tier Dual-Dispatch Retrieval Engine & Promotion Governance
  - 5.1 The 3-Tier Latency Cascade: Short-Circuit (<=5ms), Beam Search (<=35ms), Flat Fallback (<=25ms)
  - 5.2 Working Memory Governor: Cognitive Set Caps (8-20 Concepts) & Mixed Query Union
  - 5.3 3-Stage Proposition Grounding Verifier: Polarity Parity, Entity Containment, and Sampled CPU NLI
  - 5.4 Promotion Governance: Tier 2 Shadow Uplift Gate & The Appendix A Tracked Residuals Register
================================================================================
```

---

### 3.2 Bespoke Source 1: The Holonic Brain & Multi-Tier Memory Hierarchy
*(Copy and paste directly into Google NotebookLM)*

```markdown
# SOURCE 1: The Holonic Brain & Multi-Tier Memory Hierarchy
Project Trace Technical Architecture Archive — Document ID: TRACE-SRC-01
Governing Reference: CORTICAL_SUBSTRATE_V1_PLAN.md §0 (D1, D2, D4), §1

1. The Koestlerian Holon Principle in Cognitive Architecture
In biological and artificial cognitive architectures, scalable intelligence requires a structural balance between autonomy and integration. Arthur Koestler (1967) formalized this as the "holon"—an entity that exhibits a dual nature (the Janus effect): looking inward, it acts as an autonomous, self-contained whole; looking outward, it functions as an integrated, cooperative component of a larger macroscopic hierarchy (a "holarchy").

Project Trace rejects monolithic flat vector databases in favor of a 4-tier physical and semantic memory holarchy:

               [L3: Invariant Schemata]  <-- Hot RAM (<5MB), Parametric Grammars
                         ▲
                         │ Subgraph Isomorphism (>=5 matches across >=3 docs)
                         │
              [L2: Macro-Topology / TOC]  <-- Warm SSD + Hot Centroid Cache, Fanout <= 64
                         ▲
                         │ Bisecting Spherical 2-Means Partitioning
                         │
             [L1: Operational Holons]   <-- Warm SSD, S^383 int8 Fréchet Centroid, |spans| <= 8
                         ▲
                         │ Two-Pass Intra-Doc Aliasing (RSJ-IDF + Diameter Bounds)
                         │
             [L0: Episodic Ground]      <-- Cold NVMe / Spine WAL, Byte-Exact Spans

2. Tier 0: L0 Episodic Ground (Immutable Physical Reality)
The foundation of all memory in Trace is the raw, unadulterated source text.
- Physical Schema:
  CREATE TABLE atom (
      id INTEGER PRIMARY KEY,
      doc_id TEXT NOT NULL,
      file_id TEXT NOT NULL,
      start_byte INTEGER NOT NULL,
      end_byte INTEGER NOT NULL,
      content_hash BLOB NOT NULL,
      text TEXT NOT NULL
  );
  CREATE INDEX idx_atom_file_span ON atom(file_id, start_byte);
  CREATE INDEX idx_atom_hash ON atom(content_hash);
- Core Invariants:
  1. Slice Exactness: text == normalized_source[start_byte:end_byte] for all rows.
  2. Zero NEXT Pointers: Physical narrative order is preserved implicitly via ORDER BY start_byte ASC. Hardware disk controllers execute sequential reads at multi-gigabyte/sec throughput. Storing explicit NEXT pointer rows creates write-amplification and index corruption risk without adding information.
  3. External Content FTS5:
     CREATE VIRTUAL TABLE fts_atoms USING fts5(
         text,
         content='atom',
         content_rowid='id',
         tokenize='porter unicode61 remove_diacritics 1'
     );
     By designating 'atom' as the external content table, SQLite stores inverted postings in %_data only. Raw text is never duplicated in FTS shadow tables, eliminating raw text bloat.

3. Tier 1: L1 Operational Holons (The Unit of Semantic Thought)
An operational holon represents a coherent cognitive concept synthesized from up to 8 aliased episodic spans within a single document.
- Physical Schema:
  CREATE TABLE holon (
      id TEXT PRIMARY KEY,
      parent_toc TEXT,
      centroid_int8 BLOB NOT NULL,       -- 384 bytes, signed int8
      lex_sig TEXT NOT NULL,             -- JSON array of top-32 strings
      spans TEXT NOT NULL,               -- JSON array of [(file_id, start, end), ...]
      energy REAL NOT NULL,              -- Hebbian dynamic activation
      tier TEXT NOT NULL,                -- 'nav' (auto) or 'factual' (human)
      status TEXT NOT NULL,              -- 'ACTIVE', 'DORMANT', 'DIRTY_CONTRACT'
      version INTEGER NOT NULL,
      anchor_model TEXT NOT NULL,
      created_at TIMESTAMP NOT NULL
  );
- Mathematical Vector Quantization on S^383:
  Embeddings are generated via intfloat/e5-small-v2 (384 dimensions) with the 'passage: ' prefix. Member span embeddings reside on the unit hypersphere S^383.
  Centroids are computed as spherical Fréchet means:
  c_unit = (∑ e_i) / ||∑ e_i||_2
  Coherence Norm Check: The unnormalized sum must satisfy (1 / |H|) * ||∑ e_i||_2 >= 0.60. Mergers that cause vector cancellation below 0.60 are strictly forbidden.
  Symmetric int8 Quantization:
  q = clip(round(c_unit * 127), -127, 127) in int8^384
  This stores the vector in exactly 384 bytes (75% compression vs float32) while preserving cosine distance fidelity.
- Lexical Signature: lex_sig stores the top-32 salient string tokens as a JSON array, eliminating vocabulary registry drift across generations.
- Dynamic Hebbian Energy & Newborn Immunity:
  E(h) = max(0.0, 1.0 * hits_7d + 0.5 * centrality - 0.02 * age_days)
  Newborn Grace Invariant: Any holon with age_days < 7 is strictly immune to background apoptosis pruning, preventing fresh knowledge from being evicted before queries can reinforce it.

4. Tier 2: L2 Macro-Topology / TOC-DAG (Hierarchical Routing)
TOC (Table of Contents) nodes partition the operational holon space into a navigational DAG.
- Physical Schema:
  CREATE TABLE toc (
      id TEXT PRIMARY KEY,
      parent TEXT,
      c0_float BLOB NOT NULL,            -- 384 float32 unit vector (1536 B)
      R0 REAL NOT NULL,                  -- Max cosine distance to members
      members TEXT NOT NULL,             -- JSON array of holon IDs (len <= 64)
      boundary TEXT NOT NULL,            -- Cohesion metadata
      status TEXT NOT NULL,              -- 'ACTIVE', 'STALE_CENTROID', 'DIVERSE_OVERFLOW'
      version INTEGER NOT NULL
  );
- Non-Negotiable Fanout Invariant: |members| <= 64 per TOC node.
- Effective Radius: R0_eff = max(1.0 - min_{h in TOC}(c0 · h), 0.05).
- Partitioning Mechanics: When member count exceeds 64, bisect using Bisecting Spherical 2-Means (see Source 4).

5. Tier 3: L3 Invariant Schemata (Cognitive Grammars)
L3 schemata represent recurring topological and functional patterns across the corpus (e.g., API interfaces, diagnostic workflows, state transition loops).
- Structure: Parametric tuple <Slots, Actions, Invariants, State Transitions>.
- Footprint: Extremely lean (<5MB total), resident permanently in hot RAM.
- Promotion Gate: Schemata start in SHADOW status. Promotion to CANDIDATE and PROMOTED requires explicit Human Owner sign-off and empirical proof of >= 5 instantiations across >= 3 distinct documents.
- Invariant: Concrete L1 holons and L2 TOC nodes link to schemas via INSTANTIATES edges; schemas never erase or overwrite underlying episodic ground truth.
```

---

### 3.3 Bespoke Source 2: Event Segmentation Theory & Intra-Document Aliasing
*(Copy and paste directly into Google NotebookLM)*

```markdown
# SOURCE 2: Event Segmentation Theory & Intra-Document Aliasing
Project Trace Technical Architecture Archive — Document ID: TRACE-SRC-02
Governing Reference: CORTICAL_SUBSTRATE_V1_PLAN.md §1, §2A

1. The Cognitive Failure of Heuristic Regex Chunking
Conventional RAG and memory pipelines rely on arbitrary chunking heuristics: sliding 500-token windows, 1200-character regex splits, or fixed contiguous triples (N=3). In continuous information ingestion, these heuristics produce two fatal defects:
1. Sentence and Proposition Splattering: Complex propositions spanning across chunk boundaries are truncated, destroying semantic context.
2. Cross-Document Frankenstein Clusters: Flat array slicing frequently takes the tail of Document A and the head of Document B and binds them into a single cluster. This forces synthesis models to hallucinate artificial connections between unrelated texts.

2. Biological Grounding: Event Segmentation Theory (EST)
Human cognition does not experience reality as fixed-size byte windows. According to Event Segmentation Theory (Zacks et al., 2007; Kurby & Zacks, 2008), the perceptual system maintains an active internal "event model". As long as perceptual reality aligns with predictions generated by the event model, experience is perceived as continuous. When internal prediction error spikes (Delta_error > theta), the brain triggers an "event boundary", flushes working memory, and initiates a new event model.

In Project Trace, Event Segmentation is operationalized through a Two-Pass Intra-Document Aliasing Engine:

                       Incoming Document Paragraphs
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │ Pass 1: Fast Lexical Draft      │
                    │ - Smoothed RSJ-IDF Overlap      │
                    │ - Disjunctive Entity Matching   │
                    └────────────────┬────────────────┘
                                     │ Candidate Holon Clusters
                                     ▼
                    ┌─────────────────────────────────┐
                    │ Pass 2: Async Embedding Refine  │
                    │ - Hyperspherical Cosine Cap     │
                    │ - Bounded Complete-Linkage Diam │
                    │ - Coherence Norm Floor (>=0.60) │
                    └────────────────┬────────────────┘
                                     │
                                     ▼
                      Final Operational Holons (L1)
                      (Zero Cross-Doc Slicing)

3. Pass 1: Fast Lexical Draft (Ingestion Path)
During the high-throughput ingestion phase (>=800 docs/sec), paragraphs P_i and P_k within the SAME document are aliased if they meet either a statistical lexical overlap or a shared entity signature.
- Salient Token Set S_i: Tokens with length >= 3, not in English stopwords, and with paragraph frequency:
  df_t <= max(2, 0.4 * n_paras)
- Smoothed Additive Robertson-Spärck-Jones (RSJ) IDF:
  Standard RSJ-IDF can become negative or zero when document term frequencies are high or when n_paras is small. Trace enforces a smoothed, strictly positive formulation:
  idf_doc(t) = ln(1 + (n_paras - df_t + 0.5) / (df_t + 0.5)) + 1.0
  The additive +1.0 ensures that every salient term contributes at least 1.0 to the lexical score.
- Disjunctive Aliasing Rule:
  Paragraphs P_i and P_k are aliased into a holon candidate iff:
  [score_lex(i, k) >= 2.0 AND |S_i ∩ S_k| >= 2] OR [HasSharedEntityOrSig(P_i, P_k) AND Jaccard(P_i, P_k) >= 0.30]
  where score_lex(i, k) = ∑_{t in S_i ∩ S_k} idf_doc(t).
- Small Document Behavior: On a 2-paragraph document (n_paras=2), if df_t=2, idf_doc(t) = ln(1.2) + 1.0 ≈ 1.182. A single shared term scores 1.182 < 2.0. However, if the paragraphs share a named entity or code signature (def process_tx(): ...) with Jaccard >= 0.30, the disjunctive entity clause succeeds, preventing zero-division or threshold starvation.

4. Pass 2: Async Embedding Refinement (Consolidation Pass)
Post-embedding, the candidate clusters undergo complete-linkage diameter enforcement on the unit hypersphere S^383 using e5-small-v2 embeddings.
A candidate span P_k can join holon H iff ALL four bounding conditions hold:
1. Maximum Span Cap: |spans(H)| <= 8.
2. Centroid Distance Bound: cos(e(P_k), c_H) >= 0.70.
3. Complete-Linkage Pairwise Diameter Cap:
   min_{P_j in spans(H)} cos(e(P_k), e(P_j)) >= 0.55.
4. Fréchet Norm Coherence Floor:
   (1 / (|H| + 1)) * ||∑_{P in H ∪ {P_k}} e(P)||_2 >= 0.60.

5. Bounded Aliasing Guarantees
- Prohibition of Single-Linkage Chaining: Single-linkage clustering allows distant concepts to merge via chains of intermediate neighbors (A aliases with B, B aliases with C... leading to A merged with Z). Complete-linkage pairwise bounding (cos >= 0.55 between ALL pairs) strictly eliminates chaining.
- Strict Document Isolation: Holon formation operates strictly per-document. Cross-document merging is mathematically prohibited. Spans that fail diameter or norm bounds spawn a new holon linked via an explicit SEE_ALSO edge.
```

---

### 3.4 Bespoke Source 3: Tripartite Facets, Compaction & Windows Epoch RCU
*(Copy and paste directly into Google NotebookLM)*

```markdown
# SOURCE 3: Tripartite Facets, Compaction & Windows Epoch RCU
Project Trace Technical Architecture Archive — Document ID: TRACE-SRC-03
Governing Reference: CORTICAL_SUBSTRATE_V1_PLAN.md §0 (D1), §1, §2D

1. Decoupled Cognitive Facets vs Monolithic Vectors
A widespread architectural failure in early cognitive AI was the "monolithic big vector":
v = [ semantic_384d | code_ast_128d | graph_ppr_64d ]

Trace explicitly forbids concatenated representation for three reasons:
1. Invalidation Amplification: In a concatenated vector, an edit to a single variable name at L0 shifts the lexical and functional components. This alters the composite vector direction, invalidating the entire HNSW graph neighborhood and forcing massive re-indexing across unrelated documents.
2. Metric Space Contamination: Cosine distance on dense semantic spheres, Jaccard distance on discrete AST sets, and shortest path hop distance on graphs are mathematically incompatible. Linearly combining them creates distorted, uninterpretable topologies.
3. Independent Clocks: Different cognitive facets change at radically different frequencies. Lexical text updates frequently; semantic concepts update moderately; topological schemas update rarely.
Therefore, Trace decouples facets into dedicated physical stores:
- Lexical Facet: External content SQLite FTS5 index.
- Semantic Facet: Pinned e5-small-v2 unit vectors on S^383 quantized to int8.
- Topological Facet: Compressed Sparse Row (CSR) adjacency arrays.
- Relational/Temporal Facet: SQLite B-tree indices on (file_id, start_byte) and content_hash.

2. Silicon-Native Compaction on Developer Workstations
Trace is engineered to operate offline on commodity developer hardware (<4GB RAM footprint, 8GB VRAM). This demands extreme byte efficiency:
- External Content FTS5 Storage Elimination:
  Standard SQLite FTS5 tables duplicate the source text into internal %_content tables. Designating atom as the external content source (content='atom', content_rowid='id') forces FTS5 to store only inverted postings (%_data), cutting lexical index disk footprint to ~0.50x admitted bytes with zero text duplication.
- Symmetric int8 Fréchet Quantization:
  Unit centroids on S^383 are mapped to signed 8-bit integers:
  q = clip(round(c_unit * 127), -127, 127) in int8^384
  Storage per vector drops from 1,536 bytes (float32) to exactly 384 bytes (75% savings).
- Compact CSR Graph Arrays:
  Adjacency graphs are serialized as three contiguous uint32 binary arrays: indptr, indices, and weights. Node degrees are hard-capped at 50 edges per type, 128 total across types.
- Storage Gate D1:
  Total-Hot Operational Footprint <= 3.0x admitted UTF-8 raw text bytes (hard promotion gate).
  Durable Cold Spine Footprint <= 1.6x admitted bytes (chunked zstd level 6 block compression).

3. Windows-Safe Epoch RCU (Eliminating WinError 32)
On Windows NTFS, memory-mapped files (mmap) opened by reader processes lock the underlying file handles at the OS kernel level. If a background compaction task attempts to overwrite, rename, or unlink an active index file, Windows raises:
WindowsError: [Error 32] The process cannot access the file because it is being used by another process.
POSIX systems allow unlinking open files (the file persists until all file descriptors close); Windows NTFS strictly prohibits this.

Trace solves this via Windows-Safe Read-Copy-Update (RCU):

   [Background Compactor]                       [Reader Processes (PID 1..N)]
             │                                                │
    1. Write New Generation to:                               │
       generations/gen_002_timestamp/                         │
             │                                                │
    2. Atomic SQLite Pointer Swap:                            │
       UPDATE active_generation                               │
       SET epoch = 2, gen_dir = 'gen_002_...'                 │
             │                                                │
    3. Mark gen_001 as DORMANT_RETIRED                        │
             │                                                │
    4. Poll active_reader_leases ────────────────────────► 5. Readers hold leases:
       WHERE epoch = 1                                        active_reader_leases(pid, lease_id, epoch)
             │                                                │
    6. When lease count == 0 AND                              │
       T_grace >= 120s elapsed:                               │
       Execute safe asynchronous unlink.                      │
       If WinError 32 caught -> defer to startup sweep.

- Micro-Batched Ingestion Pipeline:
  Commit batches are bounded to N = 250 docs (or 1,000 atoms / 100ms timeout) to keep write transactions < 15ms.
  Queue depth between 8 parsing workers and the committer is capped at maxsize = 16 batches.
  Active WAL Checkpointing: If the SQLite WAL exceeds 16MB, intake pauses up to 50ms to run PRAGMA wal_checkpoint(RESTART). If the WAL exceeds 64MB, intake halts to run PRAGMA wal_checkpoint(TRUNCATE).
```

---

### 3.5 Bespoke Source 4: The Holonic Lagrangian & Dynamical Graph Traversal
*(Copy and paste directly into Google NotebookLM)*

```markdown
# SOURCE 4: The Holonic Lagrangian & Dynamical Graph Traversal
Project Trace Technical Architecture Archive — Document ID: TRACE-SRC-04
Governing Reference: CORTICAL_SUBSTRATE_V1_PLAN.md §0 (D3), §1, §2B, §2C

1. The Holonic Lagrangian: Memory Equilibrium
Autonomous cognitive architectures face a thermodynamic tension: unbounded retention leads to memory poisoning and prohibitive search latencies, while aggressive forgetting causes knowledge amnesia. Trace models memory admission, retention, and traversal as a constrained optimization problem—the Holonic Lagrangian:
L_holon = Utility(H) - λ_storage * Cost_storage(H) - μ_latency * Cost_traversal(H) - ν * Delta_drift(H)
where:
- Utility(H): Empirical query utility and topological centrality of holon H.
- λ_storage: Shadow price of storage (escalates sharply as total hot state approaches the 3.0x gate).
- μ_latency: Shadow price of query latency (escalates as p95 latency approaches 65ms).
- ν: Stability penalty against hyperspherical centroid drift.

2. Bayesian Salient-Only Admission Triage
Incoming documents must pass a pre-Spine triage filter before being admitted to the canonical WAL:
S_admit = 0.70 * Novelty + 0.30 * Utility >= 0.20
- Novelty (Prediction Error):
  Delta_nov = 1.0 - max_{h in L1} cos(e_new, c_h)
- Utility (Bayesian Query Prior):
  Utility(d) = γ(N) * 0.50 + (1 - γ(N)) * U_empirical(d), where γ(N) = exp(-N / 1000)
- Cold-Start Guard: The first 1,000 documents receive PROBATIONARY_ADMIT to establish initial corpus topology. High-novelty documents (Delta_nov >= 0.29) admit unconditionally on novelty alone.

3. Macro-Topology: Bisecting Spherical 2-Means
When an L2 TOC node exceeds 64 member holons, it must partition:
- Why Spherical k-Means? Euclidean k-means computes arithmetic averages, pulling centroids inward towards the origin (||c||_2 < 1.0) and distorting angular cosine relationships. Spherical k-means computes Fréchet unit means on S^383, maximizing cosine alignment.
- Diametrical Oppositional Seeding:
  Rather than random initialization (which introduces run-to-run non-determinism), seeds are chosen deterministically:
  s1 = argmax_{h in TOC} (1 - h · c0)     (the member furthest from cluster centroid)
  s2 = argmax_{h in TOC} (1 - h · s1)     (the member furthest from seed s1)
- Sorted-ID Tie Breaking: When a member is equidistant to both seeds (h · s1 == h · s2), membership assignment iterates through member holons in strictly sorted holon_id order, guaranteeing 100% bit-exact partition determinism.
- Cohesion Fallback & DIVERSE_OVERFLOW:
  If a split partition violates the cohesion floor (intra-cluster Jaccard affinity < 0.08), members are reassigned to available neighbor TOCs. If no neighbor has capacity, members are placed in a DIVERSE_OVERFLOW node. Overflow nodes have cohesion_floor = 0.0 and STALE_CENTROID status; they are excluded from Tier 2 beam searches, re-split first during sleep cycles, and pruned after 30 days if orphaned.

4. Hyperspherical Cosine Drift Gating
When member atoms are edited or added, centroid drift is evaluated:
Delta_cos = 1.0 - (c0 · c_new)
If Delta_cos > 0.25 * R0_eff, the node is flagged STALE_CENTROID and queued for re-centering during the next sleep cycle.
Boiling-Frog Monitor: The system monitors %STALE L2 / week. If the weekly stale ratio increases by more than 5 percentage points, an operational alert is triggered.

5. Two-Pass Excitatory-Inhibitory Lateral Rectification PPR
Personalized PageRank (PPR) models activation diffusion through associative networks. However, standard PPR assumes non-negative edge weights. When negative relations exist (e.g., MUTUALLY_EXCLUSIVE, CONTRADICTS), standard transition matrices lose their stochastic properties (spectral radius rho(P) != 1), causing power iterations to oscillate or diverge to -infinity.

Trace implements a biologically inspired Two-Pass Algorithm:
- Pass 1 (Excitatory Diffusion):
  Construct right-stochastic transition matrix P+ from non-negative edges E+ only (weights w >= 0).
  Iterate power diffusion with teleport vector p0:
  p^(t+1) = α * p^(t) * P+ + (1 - α) * p0    (α = 0.85, <= 20 iterations, <= 2500 steps)
  Because P+ is non-negative and row-normalized, rho(P+)=1 is guaranteed, ensuring monotonic convergence.
- Pass 2 (Lateral Inhibitory Suppression):
  Inhibitory edges E^- (stored with absolute positive magnitude |w^-|) apply lateral suppression post-walk:
  s_rect(v) = max(0, s+(v) - β * max_{(u, v) in E^-} (|w^-_{uv}| * s+(u)))   (with β = 1.0)
- Rectification Divide-by-Zero Guard:
  If an intensely contradictory query results in all candidates being suppressed (||s_rect||_1 <= 0), the engine falls back to excitatory baseline s+ (or emits insufficient_evidence if confidence falls below threshold).
- Final Renormalization:
  s_final = s_rect / ||s_rect||_1
  Guarantees non-negative probabilities, zero ghost activations, and zero division crashes.
```

---

### 3.6 Bespoke Source 5: 3-Tier Dual-Dispatch Retrieval & Grounding Verifier
*(Copy and paste directly into Google NotebookLM)*

```markdown
# SOURCE 5: 3-Tier Dual-Dispatch Retrieval & Grounding Verifier
Project Trace Technical Architecture Archive — Document ID: TRACE-SRC-05
Governing Reference: CORTICAL_SUBSTRATE_V1_PLAN.md §0 (D4), §2C, Appendix A

1. The 3-Tier Dual-Dispatch Retrieval Cascade
Trace enforces an end-to-end worst-case p95 query latency budget of <= 65ms across a 3-tier cascade:

                       Incoming Search Query
                                 │
                                 ▼
                 ┌───────────────────────────────┐
                 │ Tier 1: Lexical Short-Circuit │  <= 5ms
                 │ Exact Quotes, UPPER_SNAKE,    │
                 │ Tracebacks, Backticks         │
                 └───────────────┬───────────────┘
                                 │ Hits < 3
                                 ▼
                 ┌───────────────────────────────┐
                 │ Tier 2: Top-Down Beam Search  │  <= 35ms
                 │ L2 TOC Beam (K <= 20)         │  (SHADOW Mode
                 │ -> L1 Filter -> Two-Pass PPR  │   until Uplift)
                 └───────────────┬───────────────┘
                                 │ Candidates < 3 / Beam Miss
                                 ▼
                 ┌───────────────────────────────┐
                 │ Tier 3: Global Flat Hybrid    │  <= 25ms
                 │ Dense kNN + SQLite FTS5 BM25  │
                 │ Fused via RRF                 │
                 └───────────────┬───────────────┘
                                 │
                     Score >= theta_floor?
                    ├── YES ──► Expand L0 Source Spans & Return
                    └── NO  ──► Emit Provable 'insufficient_evidence'

- Tier 1 (Lexical Short-Circuit, <=5ms):
  Triggers on syntax-dense queries (quoted strings, UPPER_SNAKE >= 3, code backticks, stack traces). Probes SQLite FTS5 fts_atoms + holon lex_sig top-20. If >= 3 hits score above BM25 floor theta_lex, immediately expands L0 spans and returns, bypassing vector encoding completely.
- Tier 2 (Top-Down Hierarchical Beam, <=35ms):
  Encodes query via e5-small-v2 ('query: ' prefix). Probes top-20 L2 TOC centroids (strictly excluding DIVERSE_OVERFLOW nodes). Gathers member L1 holons and executes Two-Pass Rectified PPR (<= 2500 steps). If >= 3 confident candidates have cos >= 0.65, expands L0 spans and returns.
  Tier 2 Promotion Gate: Tier 2 operates in SHADOW mode during v1 qualification. It is promoted to the default production path IF AND ONLY IF paired bootstrap evaluation proves statistically significant uplift over Tier 3 flat hybrid (95% bootstrap CI > 0).
- Tier 3 (Global Flat Hybrid Fallback, <=25ms):
  Global dense kNN across all L1 centroids unioned with global BM25 over fts_atoms. Scores are fused via Reciprocal Rank Fusion:
  RRF(d) = 1 / (60 + rank_dense(d)) + 1 / (60 + rank_sparse(d))
  If top candidate has RRF >= 0.012 (or dense cos >= 0.40), expands L0 spans and returns.
- Provable Abstention: If Tier 3 fails to meet threshold theta_floor, the engine returns an explicit insufficient_evidence signal. It NEVER invents facts.
- Working Memory Governor: Final retrieved sets are capped at 8 to 20 concepts. Mixed queries union short-circuit and beam hits, bounded at 20.

2. 3-Stage Proposition Grounding Verifier
Autonomous navigation holons must pass a deterministic 3-stage grounding filter:
- Stage 1: Deterministic Polarity & Antonym Parity:
  Extracts negation markers N = {'not', 'never', 'neither', 'strictly prohibits', 'cannot'}. Checks parity between proposition Pi and source atom A. Tests directionality antonym pairs (permits vs prohibits, increases vs decreases). Any polarity inversion fails immediately (POLARITY_INVERSION).
- Stage 2: Entity & Quantity Containment:
  Extracts named entities, code symbols, and numerical values:
  E(Pi) ⊆ E(A)
  Requires salient token recall >= 0.80. A proposition cannot introduce novel entities or alter numerical metrics.
- Stage 3: Sampled Local CPU NLI Audit:
  A local cross-encoder (cross-encoder/nli-deberta-v3-small pinned, CPU execution, $0.00 GPU spend) audits a 10% stratified sample of propositions. Requires:
  P(contradiction) < 0.01  AND  P(entailment) >= 0.70
  Budget: <= 15ms/doc on CPU.

3. Appendix A Tracked Residuals & Calibration Register
Plan v1.1 binds all implementations to 13 non-negotiable governance invariants:
1. PPR divide-by-zero suppression fallback to s+.
2. Cross-process SQLite reader lease tracking eliminating WinError 32.
3. Two-pass aliasing order (lexical draft -> async complete-linkage diameter).
4. DIVERSE_OVERFLOW exclusion from Tier 2 beam probes.
5. Strict end-to-end p95 latency budget <= 65ms across full cascade.
6. Pinned CPU cross-encoder for Stage 3 NLI audit (<=15ms/doc).
7. Frozen P0 calibration priors (lexical floor 2.0, Jaccard 0.30, cosine 0.70/0.55).
8. D3 additive admission threshold: 0.70*Nov + 0.30*Util >= 0.20.
9. Newborn holon 7-day apoptosis immunity.
10. lex_sig stored as JSON array of top-32 strings.
11. Tier 2 paired uplift promotion gate (95% bootstrap CI > 0).
12. Overflow node beam exclusion.
13. Bisecting spherical 2-means deterministic sorted-ID tie breaking.
```

---

## 4. Codebase Audit & Subagent Execution DAG (WP0 to WP6)

### 4.1 Verified File Audit Matrix

```
┌──────────────────────────────────────┬───────────────────────────────────────────┬────────────────────────────────────────────┐
│ Subsystem / File                     │ Current Implementation State              │ Target State (Cortical Substrate V1.1)     │
├──────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────────┤
│ Atomizer                             │ Legacy regex paragraph & bullet chunking  │ Refactor to Smoothed Additive RSJ-IDF +    │
│ src/trace/v2/atomizer.py:87-116      │ with arbitrary 1200-char splitting        │ Disjunctive Aliasing + Bounded Complete-   │
│                                      │                                           │ Linkage (max 8 spans, cos>=0.70, norm>=0.6)│
├──────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────────┤
│ Cluster Assembler                    │ Lines 201-205 slice raw atoms into        │ Purge contiguous N=3 slicing; assemble     │
│ benchmarks/assemble_10k_clusters.py  │ contiguous triples across doc boundaries  │ clusters strictly within intra-doc         │
│                                      │ (Frankenstein cross-doc clusters)         │ aliased holon boundaries                   │
├──────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────────┤
│ SQLite Storage Layer                 │ Explicit NEXT pointer relations           │ External content FTS5 table with zero text │
│ src/trace/v2/store.py:30             │ in STRUCTURAL_RELATIONS; no FTS5 table    │ duplication; purge NEXT rows; add SQLite   │
│                                      │ currently implemented                     │ active_reader_leases & active_generation   │
├──────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────────┤
│ Macro-Topology / Hierarchy           │ Greedy token-overlap clustering           │ Deterministic Bisecting Spherical 2-Means; │
│ src/trace/v2/organization.py:225,255 │ with arbitrary section_size slices        │ diametrical seeds; sorted-ID tie-breaking; │
│                                      │ (lines 225, 237-238, 255)                 │ fan-out <= 64; DIVERSE_OVERFLOW handling   │
├──────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────────┤
│ Graph Traversal Engine               │ Single-pass excitatory activation         │ Two-Pass Excitatory-Inhibitory Lateral     │
│ src/trace/v2/cortex.py:65-120        │ over positive weights only                │ Rectification PPR with divide-by-zero guard│
├──────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────────┤
│ Retrieval Engine                     │ Dynamic in-memory Python dict BM25;       │ 3-Tier Dual-Dispatch (Tier 1 <=5ms,        │
│ src/trace/v2/retrieval.py:390-415    │ single-tier hybrid RRF; hashing fallback  │ Tier 2 <=35ms, Tier 3 <=25ms, p95 <=65ms); │
│                                      │                                           │ 3-Stage Proposition Grounding Verifier     │
├──────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────────┤
│ Qualification Scaffold               │ Lines 171-188 contain hardcoded mock      │ Purge mock RAM/storage; measure live via   │
│ benchmarks/run_100k_qualification.py │ RAM strings and mock storage byte numbers │ psutil.virtual_memory() & Path.stat()      │
└──────────────────────────────────────┴───────────────────────────────────────────┴────────────────────────────────────────────┘
```

### 4.2 Subagent Execution Work Packets (WP0 to WP6)

Per `docs/program/00_GLOBAL_CONTEXT_CORTICAL_SUBSTRATE.md`, the pending work is partitioned into 6 isolated, verification-gated work packets:
- **WP0 (Calibration Fixtures & Parameter Fitting):**
  - *Target Files:* `tests/test_atomizer_aba_aliasing.py`, `tests/test_grounding_polarity.py`, `tests/test_windows_generation_leases.py`.
  - *Deliverables:* Create 5 test doc fixtures (`fixture_aba_split.txt`, `fixture_boilerplate_trap.txt`, `fixture_small_doc.txt`, `fixture_negation_inversion.txt`, `fixture_windows_concurrency.py`). Calibrate the 12 uncalibrated priors in Appendix A against the frozen dev slice.
- **WP1 (Ingestion & Intra-Doc Aliasing):**
  - *Target Files:* `src/trace/v2/atomizer.py`, `benchmarks/assemble_10k_clusters.py`.
  - *Deliverables:* Implement smoothed RSJ-IDF, disjunctive entity aliasing, and bounded complete-linkage diameter constraints. Purge lines 185–205 of `assemble_10k_clusters.py` to guarantee zero cross-doc slicing.
- **WP2 (SQLite Schema Migration & Windows Epoch RCU):**
  - *Target Files:* `src/trace/v2/store.py`, `src/trace/v2/index_manager.py`.
  - *Deliverables:* Implement external content FTS5 table `fts_atoms`. Add `active_reader_leases` and `active_generation` tables. Implement Windows Epoch RCU generation swapping with deferred unlinking and `WinError 32` error catching.
- **WP3 (Macro-Topology & Hyperspherical Drift Gating):**
  - *Target Files:* `src/trace/v2/organization.py`.
  - *Deliverables:* Implement Deterministic Bisecting Spherical 2-Means with diametrical seeds and sorted-ID tie breaking. Enforce $|members| \le 64$. Implement hyperspherical cosine drift monitor and boiling-frog stale ratio tracking.
- **WP4 (Two-Pass Lateral Rectification PPR Engine):**
  - *Target Files:* `src/trace/v2/cortex.py`.
  - *Deliverables:* Implement Two-Pass Non-Negative Excitatory-Inhibitory Lateral Rectification PPR with the divide-by-zero suppression guard and spectral radius $\rho(P^+)=1$ guarantee.
- **WP5 (3-Tier Dual-Dispatch Retrieval Engine):**
  - *Target Files:* `src/trace/v2/retrieval.py`.
  - *Deliverables:* Implement Tier 1 short-circuit ($\le 5\text{ms}$), Tier 2 beam ($\le 35\text{ms}$), Tier 3 flat fallback ($\le 25\text{ms}$), working memory governor (8–20 concepts), and the 3-stage proposition verifier (polarity, containment, CPU NLI).
- **WP6 (Live Qualification & Ablation Matrix):**
  - *Target Files:* `benchmarks/run_100k_qualification.py`.
  - *Deliverables:* Purge hardcoded mock RAM strings and storage bytes (lines 171–188). Instrument live `psutil` memory and `Path.stat()` disk bytes. Certify the $\le 3.0\times$ storage gate and Tier 2 paired uplift (95% bootstrap CI > 0).

---

## 5. Remaining Questions & Gaps

1. **Empirical Prior Calibration on Developer Workstation:**
   - *Unanswered Question:* What are the exact empirical optimal values for the 12 priors listed in Appendix A (lexical floor = 2.0, Jaccard = 0.30, centroid cosine = 0.70, pairwise cosine = 0.55, drift threshold $\epsilon = 0.25$)?
   - *Investigation Gap:* These constants were theoretically derived in Plan v1.1. They must be validated against the frozen dev slice during WP0 execution to ensure zero division errors on small documents while strictly preventing boilerplate aliasing.
2. **Multi-Process Windows NTFS Lease Concurrency Stress:**
   - *Unanswered Question:* Does the SQLite `active_reader_leases` table completely prevent `WinError 32` under intense multi-process concurrency on Windows NTFS?
   - *Investigation Gap:* Must be validated under multi-process load (e.g. 8 reader processes holding active `mmap` handles while the compactor executes generation pointer swaps and deferred unlinking).
3. **Stage 3 CPU NLI Throughput Optimization:**
   - *Unanswered Question:* Can `cross-encoder/nli-deberta-v3-small` maintain the $\le 15\text{ms}$/doc budget on an Intel/AMD laptop CPU under vanilla PyTorch?
   - *Investigation Gap:* While the 10% stratified sampling amortizes the cost, vanilla PyTorch CPU inference on a 44M-parameter model can experience latency spikes. If latency exceeds 15ms during qualification, ONNX Runtime with `int8` dynamic quantization (`quantize_dynamic`) must be integrated as the execution engine.
4. **Immediate Action for Next Worker:**
   - *Recommended Focus:* Authorize and execute **Work Packet 0 (WP0: Calibration Fixtures & Parameter Fitting)** to establish deterministic regression fixtures (`tests/test_atomizer_aba_aliasing.py`, `tests/test_grounding_polarity.py`, `tests/test_windows_generation_leases.py`) before modifying core algorithms in `src/trace/v2/`.

---
*Report completed and delivered.*
