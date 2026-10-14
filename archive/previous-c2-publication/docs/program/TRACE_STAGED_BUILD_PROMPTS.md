# Trace Cortical Substrate V1.1 — Staged Build Plan (agy builder + musecode critic)

## Goal

Build Cortical Substrate V1.1 in `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace` packet by packet (WP0 calibration → WP6 qualification) using agy CLI sessions as coordinator + builders and musecode CLI sessions as the blind critic. Every packet ships only on builder evidence + critic APPROVED.

## Success Criteria

- WP0 fixtures committed; Appendix A priors fitted and frozen.
- WP1 aliasing engine live; zero cross-document clusters in assembly.
- WP2 schema + epoch RCU live; total-hot ≤ 3.0x measured on disk (not estimated).
- WP3 fan-out ≤ 64, deterministic across seeded runs; WP4 PPR zero NaN/Inf, ≤ 35 ms.
- WP5 retrieval p95 ≤ 65 ms, negation inversions 100% rejected, Tier 2 still SHADOW.
- WP6 live psutil/on-disk metrics, paired ablation dossier; Tier 2 promotes to default iff 95% bootstrap CI > 0, else stays SHADOW.
- No existing test in `tests/` regresses at any packet boundary.

## Context And Current Facts

Verified in the workspace this session (not taken on trust):

- Governing spec: `docs/program/CORTICAL_SUBSTRATE_V1_PLAN.md` (GOVERNING v1.1, DEC-CAP-012) with Appendix A (13 binding residuals). Packets WP0–WP6 defined in `docs/program/00_GLOBAL_CONTEXT_CORTICAL_SUBSTRATE.md` §§4–5.
- `tests/` contains NO WP0 files yet (`test_atomizer_aba_aliasing.py`, `test_grounding_polarity.py`, `test_windows_generation_leases.py`, `test_two_pass_ppr.py` are all greenfield). Existing suite is scaffold + `test_v2_*`/`test_scale_*`/`test_phase1_*`. No `conftest.py`; pytest 8 + pytest-asyncio; CPython 3.12.
- `src/trace/v2/atomizer.py` is text-first and offset-preserving (`normalize_text` touches line endings only) — a sound base for byte-exact provenance.
- `benchmarks/assemble_10k_clusters.py` still builds contiguous N=3 cross-document triples (`triple_atoms = raw_atoms[c_idx*3:...]`, ~line 208).
- `benchmarks/run_100k_qualification.py:171-188` still carries hardcoded mock scores and storage bytes for all three profiles.
- `src/trace/v2/index_manager.py` does not exist — WP2 creates it.
- `src/trace/v2/store.py` is an event-sourced store (events/outbox/ingestions/nodes/edges…); atom/holons/toc/leases tables are absent — WP2 is an additive migration, not a rewrite.
- `src/trace/v2/organization.py` is an extractive hierarchy/summary builder; no TOC bisecting 2-means — WP3 is additive.
- Working tree is dirty (modified program docs + `src/trace/v2/model_gateway.py`; untracked `AUDIT_10K.md`, assemble scripts, `benchmarks/data/`).

## Constraints And Non-goals

- Human-gated, never delegated: merges to main, L3 schema promotion, Tier 2 default promotion, any Appendix A prior change after WP0 freeze (per `02_EXECUTION_DAG.md` lane 1 and plan D4).
- Additive only on `store.py` / `organization.py`: existing public behavior and the current `tests/` suite stay green; new tables and TOC logic land alongside, behind their own tests.
- New tests use real temp SQLite DBs and real subprocesses; no mocks of domain or storage logic, no silent fallbacks (`except: pass`, `return []` swallowing).
- Tier 2 beam search stays SHADOW until the WP6 uplift gate passes.
- Non-goals: L3 schema mining, 1M scale-out, porting STC worktree machinery into trace.

## Key Decisions

1. Packet order WP0 → WP1 → WP2 → (WP3 ‖ WP4) → WP5 → WP6. WP3 (`organization.py`) and WP4 (`cortex.py`) touch disjoint files and run parallel; everything else is sequential.
2. WP1 splits into WP1a lexical draft (needs no model) then WP1b embedding consolidation (needs `intfloat/e5-small-v2` locally). If the model is unreachable, WP1a still ships and WP1b waits — never block the pipeline on a download.
3. Isolation is one git branch per packet (`wp0-calibration`, `wp1-aliasing`, …) cut from the step-0 commit; the critic diffs branch-vs-base. Trace has no lease system; branches are the boundary.
4. Step 0 (coordinator, before any builder): commit or stash the current dirty tree so every packet diff is clean and reviewable.
5. Critic runs blind in a fresh musecode session per delivery: diff + test output + acceptance row only, never builder chat.

## Recommended Approach

Run the paste pack below in order: A once → per packet: C → B → D-packet → E. Do not stack two packets in one builder session; each packet starts from the previous critic-approved commit.

### Paste A — readiness gate (fresh agy session, repo root, run once)

```
You are the Trace WP0 readiness checker. Repo root: C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace. Read-only. Do NOT write code.
Verify by RUNNING, report PASS/FAIL with evidence:
1. Baseline: `pytest tests/ -q` exit code + counts (record, do not require green — pre-existing failures are the baseline, list them).
2. Governing docs present: CORTICAL_SUBSTRATE_V1_PLAN.md header says GOVERNING v1.1, Appendix A has 13 rows, 00_GLOBAL_CONTEXT_CORTICAL_SUBSTRATE.md defines WP0-WP6, 06_DECISION_LOG.md contains DEC-CAP-012.
3. Greenfield confirmed: tests/test_atomizer_aba_aliasing.py, tests/test_grounding_polarity.py, tests/test_windows_generation_leases.py, tests/test_two_pass_ppr.py are all ABSENT; src/trace/v2/index_manager.py is ABSENT.
4. Debt confirmed: assemble_10k_clusters.py still slices N=3 cross-doc triples; run_100k_qualification.py:171-188 still hardcodes mock scores/storage.
5. Tree state: `git status --short` — if dirty, step 0 (commit/stash) is required before WP0; name the dirty paths.
Return EXACTLY: READY (five evidence lines) or NOT READY (which item, why, what first). If NOT READY, WP0 does not start.
```

### Paste B — BUILDER opener (every agy builder session)

```
You are a Trace Cortical Substrate builder. Repo root as above. Work ONLY on your packet branch.
Read first: CORTICAL_SUBSTRATE_V1_PLAN.md (your packet's section + Appendix A row), 00_GLOBAL_CONTEXT_CORTICAL_SUBSTRATE.md (your WP only), 01_INVARIANTS.md. Confirm scope in one line before coding.
Hard rules (violation = rejected):
- Your WP's Target Files ONLY. Never edit another packet's files; never loosen an Appendix A constant — report blockers to the coordinator.
- Additive on store.py / organization.py: existing behavior and tests keep passing; new schema/logic alongside, never a rewrite.
- Byte-exact provenance everywhere: text == normalized[start:end]; BLAKE3/SHA-256 per span.
- No mocks of domain/storage in tests (real tmp SQLite, real subprocesses). No silent fallbacks. Preserve CRLF where the file uses it.
Deliver back: (1) files changed + one line each, (2) test output YOU ran (`pytest <your tests> -v` plus full `pytest tests/ -q` regression counts vs baseline), (3) what you could NOT verify. No self-certification — the critic judges.
```

### Paste C — COORDINATOR (agy coordinator session, one per packet)

```
You are the Trace build coordinator. You do not write product code.
Step 0 (once): commit or stash the dirty tree so packet diffs are clean.
Per packet: (1) cut branch wp<N>-<slug> from the last approved commit, (2) spawn ONE agy builder session on it with Paste B + the D-packet task, (3) collect diff vs base + test outputs, (4) open a FRESH musecode critic session with Paste E + diff + outputs + acceptance row, (5) on APPROVED ask the human to merge; on QUARANTINED/REJECTED delete the branch after logging the refutation, max 3 attempts per packet, then halt to human. Never merge without human sign-off. WP3+WP4 may run concurrently on separate branches; all else sequential.
```

### Paste D0 — WP0 task (calibration fixtures; first builder session)

```
WP0 — Calibration Fixtures & Prior Fitting. Target: tests/test_atomizer_aba_aliasing.py, tests/test_grounding_polarity.py, tests/test_windows_generation_leases.py (+ tests/test_two_pass_ppr.py skeleton if trivial).
Deliver the five fixtures from 00_GLOBAL_CONTEXT §WP0 (aba_split expects exactly 2 holons not 3; boilerplate_trap shares 30% vocab and must NOT alias; small_doc aliases without ZeroDivisionError; negation inversion FAILS grounding; windows_concurrency spawns real reader processes holding mmaps during a pointer swap with 0 WinError 32). Fit and record the Appendix A row-7 priors (lexical floor 2.0, Jaccard 0.30, centroid 0.70 / pairwise 0.55 / coherence 0.60, beta 1.0, RRF floor 0.012, drift eps 0.25, lease grace 120 s, batch 250). Fixtures may assert against CURRENT code where the engine lands later — mark engine-dependent asserts xfail with the WP id that unblocks them.
Acceptance: all fixtures committed; engine-independent asserts pass; priors recorded and frozen.
```

### Paste D1 — WP1 task (aliasing engine)

```
WP1 — Ingestion & Intra-Doc Aliasing. Target: src/trace/v2/atomizer.py, benchmarks/assemble_10k_clusters.py.
WP1a (no model needed): smoothed additive IDF, disjunctive P_lex OR P_entity aliasing, max 8 spans/holon, multi-span byte provenance; purge assemble_10k N=3 cross-doc slicing, assemble strictly within doc boundaries. WP1b (needs e5-small-v2 local): cosine diameter caps (centroid >= 0.70, pairwise >= 0.55, coherence norm >= 0.60) + async consolidation. Report model availability first; if unreachable, ship WP1a and park WP1b explicitly.
Acceptance: test_atomizer_aba_aliasing.py passes (un-xfail); span invariant holds on every span; zero cross-doc clusters.
```

### Paste D2 — WP2 task (storage + RCU)

```
WP2 — Storage Schema & Epoch RCU. Target: src/trace/v2/store.py (ADDITIVE migration), CREATE src/trace/v2/index_manager.py.
Tables: atom (canonical text), fts_atoms external-content FTS5 (content='atom', content_rowid='id', zero text duplication), holons (int8 blob + lex_sig JSON top-32 strings + spans/energy/tier/status), toc, edges, active_reader_leases(pid, lease_id, epoch), active_generation(single-row pointer). RCU: compactions write generations/gen_{epoch}_{timestamp}/, pointer swap is one atomic row update, readers hold SQLite leases, retired generations unlink after 120 s grace + zero leases.
Acceptance: total-hot <= 3.0x MEASURED on disk; test_windows_generation_leases.py passes under multiprocess load; full tests/ regression clean.
```

### Paste D3/D4 — WP3 + WP4 tasks (parallel branches)

```
WP3 — L2 TOC & Drift (organization.py, ADDITIVE): deterministic bisecting spherical 2-means on |members| > 64, diametrical seeds, sorted-ID tie-breaks, cohesion deadlock -> neighbor else DIVERSE_OVERFLOW (cohesion_floor 0.0, STALE_CENTROID); drift flag when 1-(c0.c_new) > 0.25*R0_eff; 7-day newborn apoptosis grace; OVERFLOW excluded from beam candidacy. Acceptance: fan-out <= 64 enforced, seeded runs bit-identical.
WP4 — Two-Pass PPR (cortex.py): pass 1 excitatory power iteration (<= 20 iters, <= 2500 steps, non-negative W only); pass 2 rectification max(0, s+ - beta*max|w-|*s+(u)); divide-by-zero fallback to s+; renormalize. Acceptance: test_two_pass_ppr.py passes, zero NaN/Inf, <= 35 ms.
```

### Paste D5 — WP5 task (retrieval)

```
WP5 — 3-Tier Retrieval. Target: src/trace/v2/retrieval.py.
Tier 1 lexical short-circuit (<= 5 ms, quoted/UPPER_SNAKE/traceback/backtick triggers over fts_atoms + lex_sig); Tier 2 top-down beam (<= 35 ms, K <= 20 TOC probes, OVERFLOW excluded) -> L1 filter -> two-pass PPR, SHADOW wiring only (never default); Tier 3 flat hybrid fallback (<= 25 ms, dense kNN + BM25 RRF). 3-stage grounding verifier (polarity parity, entity containment + recall >= 0.80, sampled NLI cross-encoder/nli-deberta-v3-small). Never return insufficient_evidence before Tier 3 runs.
Acceptance: p95 <= 65 ms; no recall cliffs off-beam; negations 100% rejected; Tier 2 provably non-default.
```

### Paste D6 — WP6 task (qualification)

```
WP6 — Live Qualification. Target: benchmarks/run_100k_qualification.py.
Purge mock score/storage constants (lines ~171-188); instrument psutil RSS + on-disk bytes + admitted-UTF-8 denominator with live hot multiplier; 1,000-query paired ablation (BM25 / dense / hybrid RRF / +graph / +TOC beam), seed 42, 10k resamples; Tier 2 promotes to default IFF 95% bootstrap CI of uplift over Tier 3 excludes 0. Export qualification dossier.
Acceptance: storage gate verified on disk; Top-20 metrics emitted; uplift verdict recorded (promote or remain SHADOW, either is a pass if the statistics say so).
```

### Paste E — CRITIC (fresh musecode session per delivery, blind)

```
You are the Trace blind auditor. Independent: no builder chat, never ask for it. Pasted evidence is your ENTIRE basis.
You receive: (1) branch-vs-base diff, (2) builder test outputs (packet tests + full-suite regression vs baseline), (3) the WP acceptance row + governing Appendix A rows.
Probe: (1) mocks of domain/storage in new tests, (2) silent fallbacks and swallowed errors, (3) Appendix A tampering (constants loosened, gates weakened), (4) scope (every changed path inside the WP target list; store.py/organization.py changes additive, existing tests untouched in behavior), (5) provenance (new spans carry offsets + hashes; no text duplication in FTS5).
Return EXACTLY:
VERDICT: APPROVED | QUARANTINED | REJECTED
VIOLATIONS: rule, filepath, line, snippet (or NONE)
REASONING: max two sentences.
Missing evidence -> QUARANTINED naming it. Never assume.
```

## Work Plan

| Unit | Files | Acceptance |
|---|---|---|
| Step 0 | tree | clean base commit; baseline `pytest tests/ -q` recorded |
| WP0 | 3–4 new test files | fixtures committed; priors frozen |
| WP1a → WP1b | `atomizer.py`, `assemble_10k_clusters.py` | A-B-A tests pass; 0 cross-doc clusters |
| WP2 | `store.py` + new `index_manager.py` | hot ≤ 3.0x on disk; leases test passes |
| WP3 ‖ WP4 | `organization.py` ‖ `cortex.py` | fan-out ≤ 64 deterministic ‖ 0 NaN, ≤ 35 ms |
| WP5 | `retrieval.py` | p95 ≤ 65 ms; Tier 2 SHADOW |
| WP6 | `run_100k_qualification.py` | live metrics; uplift verdict recorded |

## Validation Plan

- WP0: `pytest tests/test_atomizer_aba_aliasing.py tests/test_grounding_polarity.py tests/test_windows_generation_leases.py -v` (+ full `pytest tests/ -q` vs baseline at every packet).
- WP1: above + span-invariant check + assembly run showing zero cross-doc clusters.
- WP2: leases test under multiprocess load + `du`-style on-disk hot/admitted ratio ≤ 3.0.
- WP3: seeded double-run bit-compare of partitions + fan-out assertion.
- WP4: `tests/test_two_pass_ppr.py -v` + NaN/Inf scan + timing.
- WP5: latency p95 harness + negation suite 100% reject + Tier-2-default-absent grep.
- WP6: dossier file exists with live RSS/bytes + bootstrap CI for uplift.
- Highest-risk validation: WP2's measured (not modeled) storage gate — the original 7.54x failure mode returns if FTS5 duplicates text.

## Risks / Rollback

- e5-small-v2 unreachable offline → WP1b parks; WP1a + all downstream lexical paths proceed (mitigation built into D1).
- WP2 migration breaks legacy store tests → additive-only rule + rollback is branch deletion; schema additions are new tables, never altered legacy columns.
- Uplift gate fails → Tier 2 remains SHADOW; Tier 3 default still ships — a negative result is a passing WP6.
- Windows-only WinError 32 flakes → WP0 fixture pins the failure signature; WP2 grace period is the Appendix A 120 s constant, tunable only by amendment.
- Rollback per packet is branch deletion; merged packets roll back by revert of the merge commit.

## Open Questions

None blocking. Assumption carried: `e5-small-v2` and `cross-encoder/nli-deberta-v3-small` availability is unknown until WP1/WP5 builders probe locally — both packets degrade gracefully (lexical-only paths) and the builder must report availability as first evidence.
