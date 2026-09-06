# Wave C3 Global Context: Cortical Substrate Implementation & Subagent Execution Guide

> **Date:** 2026-09-06  
> **Status:** ACTIVE EXECUTION — GOVERNING STANDARD  
> **Governing Standard:** `docs/program/CORTICAL_SUBSTRATE_V1_PLAN.md` (v1.1 Governing, `DEC-CAP-012`)  
> **Target Scale:** 100,000 to 1,000,000 Documents  
> **Target Gate:** Gate CAP-GE Qualification & Level 1 Scale Certification  

---

## 1. Executive Charter & Architectural Mission

This global context document is the authoritative onboarding and execution blueprint for autonomous subagents implementing the **Cortical Substrate V1.1** architecture. 

The legacy architecture relied on arbitrary 1200-character regex chunking, cross-document contiguous triple slicing ($N=3$), uncompressed raw text triplication ($7.54\times$ bloat), and monolithic vector dumps. The Cortical Substrate replaces this with a multi-scale, biologically inspired, silicon-efficient cognitive memory system:

```
[Ingest Stream] ──► [Habituation / Salience Gate] ──► (Discard / Attenuate if redundant)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ L0: EPISODIC GROUND (Spine WAL - Cold NVMe)                                 │
│ • Immutable byte-exact spans [file_id:start:end] + BLAKE3 hash              │
│ • Narrative Flow = ORDER BY start_byte ASC (O(1) physical, zero NEXT edges) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Fast Lexical Draft + Async Consolidation
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ L1: OPERATIONAL HOLONS (Warm SSD - Segmented HNSW)                         │
│ • e5-small-v2 int8[384] Fréchet unit vector + Top-32 string tokens lex_sig  │
│ • Complete-linkage diameter cap (max 8 spans, pairwise cos >= 0.55)         │
│ • Explicit CSR Graph: COMPILED_FROM, REFERENCES, SEE_ALSO, SUBSUMES        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Deterministic Bisecting Spherical 2-Means
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ L2: MACRO-TOPOLOGY / TOC-DAG (Warm SSD + Hot Centroid Cache)                │
│ • Unit Centroid c0[384] + Effective Radius R0 + Fanout bound <= 64          │
│ • Hyperspherical Cosine Drift Monitor: Δ_cos = 1 - (c0 · c_new) > 0.25*R0   │
│ • DIVERSE_OVERFLOW node for diffuse partitions (excluded from beam search)   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Subgraph Isomorphism (>=5 matches)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ L3: INVARIANT SCHEMATA (Hot RAM - <5MB - Generative Scaffolds)             │
│ • Parametric Grammars: ⟨Slots, Actions, Invariants, State Transitions⟩     │
│ • Status: SHADOW -> CANDIDATE -> PROMOTED (Human Owner Sign-Off Only)      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Binding Architectural Invariants (Non-Negotiable)

Every subagent working on this codebase must strictly observe these rules:

1. **Byte-Exact Provenance (`01_INVARIANTS.md`):**
   Every L0 atom and every span in an L1 holon must satisfy:
   $$\text{text} == \text{normalized\_source}[\text{start\_byte} : \text{end\_byte}]$$
   Never mutate, trim, or re-encode text in place without re-verifying slice exactness.
2. **Storage Ceiling Gate D1 ($\le 3.0\times$ Hot, $\le 1.6\times$ Durable):**
   - No raw text duplication in SQLite FTS5. All FTS5 tables must use `content='atom', content_rowid='id'`.
   - Spine event payloads must be compressed with chunked `zstd` (level 6).
   - Total-hot state on disk must remain $\le 3.0\times$ admitted UTF-8 text bytes.
3. **Hyperspherical Vector Space ($\mathbb{S}^{383}$):**
   - Centroids are spherical Fréchet means: $\mathbf{c} = \bar{\mathbf{c}} / \|\bar{\mathbf{c}}\|_2$.
   - Pre-normalization coherence norm must satisfy $\frac{1}{|H|}\|\sum \mathbf{e}_i\|_2 \ge 0.60$.
   - Quantize symmetrically to `int8`: $\operatorname{clip}(\operatorname{round}(\mathbf{c} \times 127), -127, 127)$.
4. **Two-Pass Non-Negative Lateral Rectification PPR:**
   - Adjacency matrix $W$ contains only non-negative weights ($w \ge 0$).
   - `MUTUALLY_EXCLUSIVE` edges are stored with positive magnitude $|w^-| \in [0, 1]$.
   - Negative weights are strictly prohibited in the transition matrix. Lateral inhibition is applied as a post-walk rectification pass with a divide-by-zero guard.
5. **Windows-Safe Epoch RCU (No `WinError 32`):**
   - Generations (`generations/gen_{epoch}_{timestamp}/`) are immutable. Never overwrite active indices in-place.
   - Readers register active leases in the SQLite `active_reader_leases` table.
   - Compactions perform atomic SQLite pointer updates; retired generations are unlinked only after a 120s grace period and zero active leases.
6. **3-Tier Dual-Dispatch Retrieval Cascade:**
   - Tier 1: Lexical Short-Circuit ($\le 5\text{ms}$).
   - Tier 2: Top-Down Hierarchical Beam ($\le 35\text{ms}$).
   - Tier 3: Global Flat Hybrid Fallback (Dense HNSW + FTS5 RRF, $\le 25\text{ms}$).
   - Worst-case p95 latency budget $\le 65\text{ms}$. Never abort with `insufficient_evidence` until Tier 3 fails.
7. **L3 Schemas & Tier 2 Routing Promotion Gates:**
   - L3 Schemas require $\ge 5$ instantiations across $\ge 3$ docs and explicit Human Owner sign-off.
   - Tier 2 hierarchical beam routing remains in `SHADOW` mode until paired ablation proves statistically significant uplift over Tier 3 (95% bootstrap CI > 0).

---

## 3. Directory Layout & Module Responsibility Map

```text
C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\
├── docs/program/
│   ├── CORTICAL_SUBSTRATE_V1_PLAN.md      # Governing v1.1 Plan
│   ├── 00_GLOBAL_CONTEXT_CORTICAL_SUBSTRATE.md # This subagent guide
│   ├── 01_INVARIANTS.md                   # Core system invariants
│   └── 06_DECISION_LOG.md                 # Project decision registry
├── src/trace/v2/
│   ├── atomizer.py                        # L0 atomization & intra-doc A-B-A aliasing
│   ├── store.py                           # SQLite tables (atoms, holons, toc, leases)
│   ├── organization.py                    # L2 TOC bisecting spherical 2-means & drift
│   ├── cortex.py                          # CSR graph & Two-Pass Rectified PPR
│   ├── retrieval.py                       # 3-Tier Dual-Dispatch retrieval engine
│   └── index_manager.py                   # Windows-Safe Epoch RCU generation manager
├── benchmarks/
│   ├── assemble_10k_clusters.py           # Cluster assembly (no N=3 cross-doc slices)
│   ├── run_100k_qualification.py          # Qualification harness (live psutil & bytes)
│   └── policies/scale_policy.lock.json    # Frozen candidate policy digests
└── tests/
    ├── test_atomizer_aba_aliasing.py      # P0 aliasing, small doc, boilerplate tests
    ├── test_grounding_polarity.py         # P0 negation inversion trap tests
    ├── test_windows_generation_leases.py  # P0 Windows concurrent mmap swap tests
    └── test_two_pass_ppr.py               # P0 Two-Pass PPR convergence tests
```

---

## 4. Phased Subagent Work Packets (Build Execution DAG)

The build is partitioned into 6 isolated, sequential and parallel work packets. Subagents must operate within their assigned packet boundary and verify all phase acceptance criteria.

```
       ┌──────────────┐
       │   WP0: P0    │ ── Calibration Fixtures & Prior Constants
       └──────┬───────┘
              ▼
       ┌──────────────┐
       │   WP1: P1    │ ── Ingestion & Intra-Doc Aliasing Engine
       └──────┬───────┘
              ▼
       ┌──────────────┐
       │   WP2: P2-A  │ ── SQLite Storage Schema, External FTS5 & Epoch RCU
       └──────┬───────┘
              ├──────────────────────────────┐
              ▼                              ▼
       ┌──────────────┐               ┌──────────────┐
       │   WP3: P2-B  │               │   WP4: P2-C  │
       │  L2 TOC-DAG  │               │  Two-Pass    │
       │ 2-Means &    │               │  Rectified   │
       │ Drift Gate   │               │  PPR Engine  │
       └──────┬───────┘               └──────┬───────┘
              └──────────────┬───────────────┘
                             ▼
                      ┌──────────────┐
                      │   WP5: P2-D  │ ── 3-Tier Dual-Dispatch Retrieval Engine
                      └──────┬───────┘
                             ▼
                      ┌──────────────┐
                      │   WP6: P3    │ ── Live Qualification & Ablation Matrix
                      └──────────────┘
```

---

### Work Packet 0 (WP0): Calibration Fixtures & Parameter Fitting
- **Target Files:** `tests/test_atomizer_aba_aliasing.py`, `tests/test_grounding_polarity.py`, `tests/test_windows_generation_leases.py`.
- **Deliverables:**
  1. Create test doc fixtures:
     - `fixture_aba_split.txt`: Document with topic A in Para 1, topic B in Para 2, topic A resumes in Para 3. Expect exactly 2 holons, not 3.
     - `fixture_boilerplate_trap.txt`: Intro and Conclusion sharing 30% vocabulary (`client`, `timeout`, `error`, `config`). Must NOT alias.
     - `fixture_small_doc.txt`: 2-paragraph document with shared code signature `def process_tx(): ...`. Must alias without division-by-zero.
     - `fixture_negation_inversion.txt`: Source: *"System strictly prohibits unencrypted storage"*; Hypothesis: *"System strictly permits unencrypted storage"*. Grounding verifier must FAIL.
     - `fixture_windows_concurrency.py`: Spawns concurrent reader processes holding active mmap handles while pointer swap executes. Must verify 0 `WinError 32` crashes.
  2. Calibrate Appendix A priors against dev pack:
     - Fit lexical score threshold ($\ge 2.0$), Jaccard ($\ge 0.30$), centroid/pairwise cosines ($\ge 0.70 / \ge 0.55$).
- **Acceptance Gate:** All P0 test fixtures committed and passing.

---

### Work Packet 1 (WP1): Ingestion & Intra-Doc Aliasing Engine
- **Target Files:** `src/trace/v2/atomizer.py`, `benchmarks/assemble_10k_clusters.py`.
- **Deliverables:**
  1. Refactor `src/trace/v2/atomizer.py`:
     - Implement Smoothed Additive IDF: $\operatorname{idf}_{doc}(t) = \ln(1 + \frac{n_{paras} - df_t + 0.5}{df_t + 0.5}) + 1.0$.
     - Implement Disjunctive Aliasing: $\mathcal{P}_{lex} \lor \mathcal{P}_{entity}$.
     - Enforce Bounded Complete-Linkage: max 8 spans per holon, cosine $\ge 0.70$ to centroid, pairwise $\ge 0.55$, coherence norm $\ge 0.60$.
     - Maintain multi-span byte provenance: `spans = [(start, end), ...]`.
  2. Fix `benchmarks/assemble_10k_clusters.py`:
     - Purge lines 185–205 (flattened contiguous $N=3$ cross-doc slicing).
     - Assemble clusters strictly within document boundaries using aliased holon candidates.
- **Acceptance Gate:** `test_atomizer_aba_aliasing.py` passes; `content == normalized[start:end]` invariant verified across all spans; 0 cross-doc frankenstein clusters.

---

### Work Packet 2 (WP2): Storage Schema Migration & Windows Epoch RCU
- **Target Files:** `src/trace/v2/store.py`, `src/trace/v2/index_manager.py`.
- **Deliverables:**
  1. Refactor SQLite database schema in `src/trace/v2/store.py`:
     - Create `atom` table (canonical L0 raw text).
     - Create `fts_atoms` as an **external content FTS5 table** (`content='atom', content_rowid='id'`).
     - Create `holons` table (384-byte int8 blob, JSON array `lex_sig` top-32 strings, spans JSON, energy, tier, status).
     - Create `toc` table (c0 float32 blob, R0 float, members JSON, boundary JSON).
     - Create `edges` table (src, dst, type, weight).
     - Create `active_reader_leases` table (`pid`, `lease_id`, `epoch`, `acquired_at`).
     - Create `active_generation` table (`lock_id=1`, `epoch`, `gen_dir`, `promoted_at`).
  2. Implement Windows-Safe Epoch RCU in `src/trace/v2/index_manager.py`:
     - Compaction writes to `generations/gen_{epoch}_{timestamp}/`.
     - Pointer swap is an atomic single-row SQLite update.
     - Reader lease registration and deferred asynchronous unlinking with 120s grace period.
- **Acceptance Gate:** Storage footprint verified $\le 3.0\times$ hot state; `test_windows_generation_leases.py` passes under multi-process load.

---

### Work Packet 3 (WP3): Macro-Topology (L2 TOC) & Drift Monitor
- **Target Files:** `src/trace/v2/organization.py`.
- **Deliverables:**
  1. Implement Deterministic Bisecting Spherical 2-Means:
     - Partition clusters when $|members| > 64$.
     - Seed using diametrically opposed member vectors.
     - Break ties deterministically by sorting member IDs.
     - Cohesion deadlock handling: fallback to neighbor TOCs or `DIVERSE_OVERFLOW` node.
  2. Hyperspherical Cosine Drift Monitor:
     - Compute $\Delta_{cos} = 1.0 - (\mathbf{c}_0 \cdot \mathbf{c}_{new})$.
     - Flag `STALE_CENTROID` if $\Delta_{cos} > 0.25 \times R_{0,eff}^{cos}$.
     - Enforce newborn holon 7-day apoptosis grace period.
- **Acceptance Gate:** Fanout $\le 64$ strictly verified; zero non-deterministic partition drift across seeded test runs.

---

### Work Packet 4 (WP4): Two-Pass Lateral Rectification PPR Engine
- **Target Files:** `src/trace/v2/cortex.py`.
- **Deliverables:**
  1. Implement Two-Pass Non-Negative PPR:
     - Pass 1: Excitatory diffusion over non-negative edges $E^+$ via power iteration ($\le 20$ iterations, $\le 2500$ steps). Guaranteed $\rho(P^+)=1$.
     - Pass 2: Lateral inhibitory suppression: $s_{rect}(v) = \max(0, s^+(v) - \beta \cdot \max_{(u,v) \in E^-}(|w^-_{uv}| \cdot s^+(u)))$.
     - Divide-by-zero guard: if $\|\mathbf{s}_{rect}\|_1 \le 0$, fall back to $\mathbf{s}^+$.
     - Renormalize: $\mathbf{s}_{final} = \mathbf{s}_{rect} / \|\mathbf{s}_{rect}\|_1$.
- **Acceptance Gate:** `test_two_pass_ppr.py` passes; 0 NaN/Inf scores; monotone convergence $\le 35\text{ms}$; 0 ghost activations.

---

### Work Packet 5 (WP5): 3-Tier Dual-Dispatch Retrieval Engine
- **Target Files:** `src/trace/v2/retrieval.py`.
- **Deliverables:**
  1. Implement 3-Tier Retrieval Cascade:
     - Tier 1 (Lexical Short-Circuit, $\le 5\text{ms}$): Triggers on quoted strings, `UPPER_SNAKE`, tracebacks, backticks. Queries `fts_atoms` + `lex_sig`.
     - Tier 2 (Top-Down Hierarchical Beam, $\le 35\text{ms}$): Probes L2 TOC centroids ($K \le 20$, excluding `DIVERSE_OVERFLOW`) $\to$ filters L1s $\to$ Two-Pass PPR.
     - Tier 3 (Global Flat Hybrid Fallback, $\le 25\text{ms}$): Global dense kNN + global BM25 fused via Reciprocal Rank Fusion (RRF).
  2. Implement 3-Stage Proposition Grounding Verifier:
     - Stage 1: Deterministic polarity and negation marker parity ($\mathcal{N}$).
     - Stage 2: Entity & quantity containment $\mathcal{E}(\Pi) \subseteq \mathcal{E}(A)$ + token recall $\ge 0.80$.
     - Stage 3: Sampled local NLI audit (`cross-encoder/nli-deberta-v3-small`).
- **Acceptance Gate:** Latency p95 $\le 65\text{ms}$; zero recall cliffs on out-of-beam queries; negation inversions 100% rejected.

---

### Work Packet 6 (WP6): Qualification Runner, Live Telemetry & Uplift Certification
- **Target Files:** `benchmarks/run_100k_qualification.py`.
- **Deliverables:**
  1. Purge hardcoded mock RAM strings (lines 171–188).
  2. Instrument live measurement:
     - `psutil.Process().memory_info().rss`
     - Physical on-disk byte footprint via `os.path.getsize()` / `Path.stat()`.
     - Measure raw admitted UTF-8 denominator and compute live hot multiplier.
  3. Paired Ablation Matrix:
     - Run 1,000 queries with bootstrap seed 42 (10,000 resamples).
     - Ablation matrix: BM25-only, Dense-only, Hybrid RRF, +Graph CSR, +TOC Beam.
     - Assert Tier 2 paired uplift vs Tier 3 control (95% bootstrap CI > 0).
- **Acceptance Gate:** Hard storage gate $\le 3.0\times$ verified on disk; live Top-20 metrics emitted; qualification dossier exported.

---

## 5. Subagent Operating Instructions & Guardrails

When invoked to execute any Work Packet:
1. **Never edit files outside your assigned packet boundary.** If you discover a dependency in another module, report it back to the parent coordinator.
2. **Preserve comments and docstrings.** Never prune existing codebase documentation unless explicitly directed.
3. **Always run tests locally after editing:**
   ```powershell
   pytest tests/ -v
   ```
4. **Emit structured execution receipts:** Upon completing a work packet, emit a JSON receipt summarizing:
   - Modified files and git diff statistics.
   - Test execution logs (passed, skipped, failed).
   - Invariant verification checks.
