# TRACE Master Plan v1.1 — Staged Execution Prompts (builder + critic harness)

Goal: execute `docs/program/TRACE_MASTER_STAGEWISE_EXECUTION_PLAN.md` (v1.1, ballot-approved) packet by packet
using agy CLI sessions as coordinator + builders and musecode CLI sessions as the blind critic.
Every packet ships only on builder evidence + critic APPROVED. Human gates: merges to main, L3 promotion,
Tier-2/Tier-4 default promotion, any Law (L1–L7) change, and the final CAP-GF / CAP-GG ballots.

Success criteria (from v1.1 §§3–6, abridged — the plan file rules on any conflict):

- P0: capsule adopted — union Merkle `5039acef…` re-verified from staged bytes, every `source_file` resolved +
  hash-checked, gate manifest signed, frozen BEIR check still green unmodified.
- P1: 1M runner rehabilitated or rebuilt on the current Spine schema; replay parity 100%; total-hot ≤3.0x and
  durable ≤1.6x measured on disk; Spine WAL ingest ≥800 docs/sec with dense-indexing logged separately.
- P2a: co-retrieval log pipeline + difficulty budget live behind flags; P95 down, hard-slice nDCG unregressed.
- P2b: bridge-first retrieval + contradiction-aware merge live behind flags; kill bars from v1.1 §5 met.
- P2c: Tier-4 HyDE adapter live in shadow (or explicitly PARKED if no local SLM); ≤800 ms budget metered.
- P3: warm router beside `ActivationEngine` (no phantom classes); sleep bounds N≤250 / <15 ms / 8–20 holons
  enforced; Spine-invariance proof (zero Spine-byte delta on projection drop); invisible until CAP-GG.
- No existing test in `tests/` regresses at any packet boundary.

Context and current facts (verified in the workspace — not taken on trust):

- Plan file: `docs/program/TRACE_MASTER_STAGEWISE_EXECUTION_PLAN.md` v1.1 §§1–11 with Law (L1–L7) vs
  `[AMENDMENT]` (A1–A6) tagging. Builders cite Law; only the human ballot may ratify Amendments.
- Corpus capsule: `docs/program/inbox/1m-02-corpus-capsule/evidence/1m_corpus_manifest.json`
  (contract 2.0.0, 1M docs, 2,014,465,744 bytes, union Merkle `5039acef…`; `source_file` paths are
  Windows-absolute and MUST be normalized per gate — never assumed portable).
- Real CLIs only: `trace` (init/ingest/query/status/verify/…) and `trace-v2` (serve/migrate/worker-once).
  There is NO `trace-bench` binary and NO `spine` package (`src/` holds `trace`, `trace_local` only).
- Verified script flags: `benchmarks/verify_dataset_checksums.py --manifest/--root` (hardcodes
  `manifest_id == beir_musique_frozen_v1`); `benchmarks/run_frozen_retrieval_baseline.py
  --verify-receipt/--manifest/--dossier/--receipt`; `benchmarks/run_100k_qualification.py
  --preflight/--compare-profiles/--verify-receipts/--manifest/--corpus-input/--db-path/--queries-manifest/--bootstrap-resamples/--bootstrap-seed/--out-dir`
  (hardcodes `EXPECTED_DOC_COUNT = 100000`, capsule Merkle `38d1a1cf…`; candidate lives under `benchmarks/runs/`).
- `scripts/run_1m_scale_gate.py` EXISTS (Sept-2-era, Lean-Schema lineage) — P1 surveys it first: rehabilitate
  only if compatible with the current atom/holons/toc Spine; otherwise rebuild on the 100K pattern. Legacy
  schema contamination = reject.
- Real cortex surfaces: `ActivationEngine` (`activate`, `activate_two_pass`), `TwoPassPPREngine`,
  `FROZEN_PPR_PRIORS`. There is NO `ActivationRouter` — P3 extends beside these, never invokes it.
- Env gap: `psutil` is NOT installed — `run_100k_qualification.py --help` errors at import. P1 fixes env or
  vendors the dependency before any gate run; flags meanwhile are pinned from source.
- Tree is dirty-ish (untracked: `.agents/`, `scratch/`, `tests/verification/`, `docs/program/research/`,
  this plan file). Step 0 cleans or records it before any packet branch.

Constraints and non-goals:

- Human-gated, never delegated: merges to main, L3 promotion, Tier-2/Tier-4 default promotion, any L1–L7 change,
  CAP-GF / CAP-GG ballots, Amendment ratification.
- Additive only on `store.py` / `organization.py` / `cortex.py` / `retrieval.py`: existing behavior and the
  current `tests/` suite stay green; new schema/logic lands alongside, behind its own tests.
- Verified-commands-only: every command a builder emits must ship with its live `--help` transcript from this
  workspace (`PYTHONPATH=src` where imports apply). A command that needs new scaffolding is a work-packet
  deliverable, never a runnable claim. Phantom command or flag = instant REJECT.
- New tests use real temp SQLite DBs and real subprocesses; no mocks of domain/storage, no silent fallbacks.
- Tier-2 beam and Tier-4 adapter stay SHADOW (never default) until their paired uplift gates pass.
- Non-goals: 100M distribution, whole-system Rust/Go rewrites, L3 schema mining, cloud hot-path.

Key decisions:

1. Packet order: Step 0 → P0 → P1 → P2a → P2b → P2c → P3 → P4. P2b ‖ P3 may run concurrently (disjoint files:
   `organization.py`+`retrieval.py` vs `cortex.py`+`jobs.py`/`worker.py`); everything else sequential.
2. P2c and any SLM-dependent work degrade gracefully: no local SLM ⇒ packet PARKED with evidence, pipeline proceeds.
3. Isolation is one git branch per packet (`p11-h0-adopt`, `p11-h1-core`, …) cut from the last approved commit;
   the critic diffs branch-vs-base. Max 3 attempts per packet, then halt to human.
4. The critic runs blind in a fresh musecode session per delivery: diff + test output + acceptance row +
   `--help` transcripts only, never builder chat.

---

## Paste A — readiness gate (fresh agy session, repo root, run once, read-only)

You are the Trace v1.1 readiness checker. Repo root: `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace`.
Read-only. Do NOT write code. Verify by RUNNING, report PASS/FAIL with evidence:

1. Plan: `docs/program/TRACE_MASTER_STAGEWISE_EXECUTION_PLAN.md` header says `BALLOT-READY DRAFT v1.1`, footer says
   `End of TRACE Master Plan v1.1`; §§2/11 exist (Law table + verified commands).
2. Capsule: `docs/program/inbox/1m-02-corpus-capsule/evidence/1m_corpus_manifest.json` parses; print
   `contract_version`, `target_unique_documents_d`, `total_raw_text_bytes`, `union_merkle_root_sha256`.
3. Baselines green: `python3 benchmarks/verify_dataset_checksums.py --manifest
   benchmarks/manifests/beir_musique_frozen_v1.json --root .` exit code + tail; `python3
   benchmarks/run_frozen_retrieval_baseline.py --verify-receipt --manifest
   benchmarks/manifests/beir_musique_frozen_v1.json --dossier
   docs/program/inbox/cap-ret04/retrieval_baseline_dossier.json --receipt
   docs/program/inbox/cap-ret04/verification_receipt.json` exit code + tail.
4. Tooling reality: `python3 -c "import psutil"` outcome; `ls src/` shows no `spine`; `which trace-bench` fails;
   `grep -c ActivationRouter src/trace/v2/cortex.py` is 0; `ls scripts/run_1m_scale_gate.py` outcome.
5. Tree state: `git status --short` — if dirty, Step 0 (commit/stash/record) is required before P0; name the paths.
6. Suite baseline: `pytest tests/ -q` exit code + counts (record, do not require green — pre-existing failures are
   the baseline, list them).

Return EXACTLY: READY (six evidence lines) or NOT READY (which item, why, what first). If NOT READY, P0 does not start.

## Paste B — BUILDER opener (every agy builder session)

You are a Trace v1.1 builder. Repo root as above. Work ONLY on your packet branch.
Read first: `TRACE_MASTER_STAGEWISE_EXECUTION_PLAN.md` (your horizon section + §2 Law table + §11), `01_INVARIANTS.md`.
Confirm scope in one line before coding.
Hard rules (violation = rejected):
- Your packet's Target Files ONLY. Never edit another packet's files; never loosen L1–L7 — Amendments (A1–A6) may be
  *used* where your packet names them, never widened. Blockers go to the coordinator.
- Additive on store/organization/cortex/retrieval: existing behavior and tests keep passing; new schema/logic
  alongside, never a rewrite. No `ActivationRouter`, no `trace-bench`, no `spine.*` imports — these do not exist.
- Verified-commands-only: paste the live `--help` transcript (run in this workspace, `PYTHONPATH=src` where needed)
  for EVERY command you emit. New scaffolding is a deliverable, not a runnable claim.
- Byte-exact provenance everywhere: text == span bytes; SHA-256 per span. No mocks of domain/storage in tests (real
  tmp SQLite, real subprocesses). No silent fallbacks.
Deliver back: (1) files changed + one line each, (2) test output YOU ran (packet tests `-v` plus full `pytest tests/
-q` regression counts vs baseline), (3) `--help` transcripts for every command cited, (4) what you could NOT verify.
No self-certification — the critic judges.

## Paste C — COORDINATOR (agy coordinator session, one per packet)

You are the Trace v1.1 build coordinator. You do not write product code.
Step 0 (once): settle the dirty tree (commit/stash/record untracked) so packet diffs are clean; record the base
commit and the Paste-A baseline.
Per packet: (1) cut branch `p11-<slug>` from the last approved commit, (2) spawn ONE agy builder with Paste B + the
D-packet task, (3) collect diff vs base + test outputs + `--help` transcripts, (4) open a FRESH musecode critic
session with Paste E + diff + outputs + transcripts + acceptance row, (5) on APPROVED ask the human to merge; on
QUARANTINED/REJECTED delete the branch after logging the refutation, max 3 attempts per packet, then halt to human.
Never merge without human sign-off. P2b ‖ P3 may run concurrently on separate branches; all else sequential. P2c
PARKED (no SLM) is a valid terminal state, not a failure — record and proceed to P3.

## Paste D0 — P0 task (capsule adopt; first builder session)

P0 — Adopt the 1M corpus contract. Targets: NEW `scripts/sign_gate_manifest.py` (or sibling), NEW
`benchmarks/verify_1m_checksums.py` (or verifier extension), NEW gate manifest under `docs/program/inbox/<gate>/`.
Do NOT modify the frozen BEIR verifier semantics.
Work: (1) normalize every Windows-absolute `source_file` in the capsule to a content-hash-verified local staging
path; record the mapping; fail closed on any unresolvable/mismatched source. (2) Recompute base/delta/union doc
counts, byte totals, and Merkle roots from staged bytes; assert equality with manifest claims (1M / 2,014,465,744 /
`5039acef…`). (3) Emit the signed per-gate manifest (source IDs, SHA-256/shard, licenses, tokenizer identity,
frozen workload vector, revision scope) + human co-signature placeholder for `06_DECISION_LOG.md`. (4) Prove the
frozen check still passes unmodified (Paste-A command 3, same output).
Acceptance: mapping 100% resolved; Merkle trio re-verified; gate manifest signed; frozen BEIR green unchanged.

## Paste D1 — P1 task (1M runner + H1 durability)

P1 — G1M-CORE runner and durability. Targets: `scripts/run_1m_scale_gate.py` (survey-then-rehabilitate ONLY if
schema-compatible with current atom/holons/toc Spine, else quarantine it forensic-only and CREATE
`benchmarks/run_1m_qualification.py` on the 100K pattern with parameterized counts/roots — same seed-42/10k-bootstrap
semantics, same fail-closed telemetry), plus env fix for `psutil`.
Work: (1) report the survey verdict first (rehabilitate vs rebuild, with schema evidence). (2) Instrument live
psutil RSS + on-disk bytes + admitted-UTF-8 denominator; log Spine WAL ingest docs/sec SEPARATELY from dense-index
batch throughput (L4 floor ≥800 applies to the former). (3) Emit the 4-number storage table per commit against
L1/L2/L3 + A1/A2 diagnostics. (4) Full replay-from-event-log parity proof.
Acceptance: 1M admitted docs; 100% replay parity; L1+L2+L3 met on disk; L4 met on the WAL path; $0 hot-path spend;
no legacy Lean-Schema contamination in the Spine.

## Paste D2a — P2a task (owned gating log + difficulty budget; no model needed)

P2a — B log pipeline + C2 budget router. Target: `src/trace/v2/retrieval.py` (+ harness logging), NEW tests.
Work: (1) emit co-retrieved (+1) / retrieved-but-ignored (−1) / contradiction (repulsive) training triples from the
live retrieval path behind a flag (default off). (2) Cheap difficulty classifier (lexical + length + entity-count
features only, never LLM judgments): easy → BM25+RRF only; predicted multi-hop → graph + TOC beam. (3) Log
per-decision routing traces for later head training.
Acceptance: P95 down ≥20% on the eval slice with zero hard-slice nDCG@10 regression; triple schema validated;
classifier retrains from router logs only.

## Paste D2b — P2b task (bridge-first + contradiction merge)

P2b — C1 + C4. Targets: `src/trace/v2/organization.py` (bridge/meta-node index), `src/trace/v2/retrieval.py`
(merge), NEW tests. (May run parallel with P3 — disjoint files.)
Work: (1) C1: TOC/meta-node first-class retrieval layer — queries hit bridge nodes, expand into member atoms;
version bridges to member sets, rebuild on mitosis (staleness guard). (2) C4: typed contradicts/supports edges
scored SEPARATELY from similarity; contradicted candidates downweighted, conflict pair surfaced; detection and
merge-weighting behind separate flags. Kill bars (v1.1 §5): C1 recall parity at ≤50% atoms scored on 100
cross-module probes; C4 ≥80% conflict recall at <5% false-flag rate.
Acceptance: kill bars met in shadow; truth/association edge families provably separate in schema.

## Paste D2c — P2c task (Tier-4 HyDE adapter; parks gracefully)

P2c — Tier-4 reasoning adapter [A4]. Target: NEW adapter module + wiring (never the hot path), NEW tests.
Work: (1) report local-SLM availability FIRST (names bound to DEC-CAP-MOD01 tiers). If unavailable: PARK the
packet with the probe evidence and stop — this is a pass-by-park, not a failure. (2) If available: HyDE /
decomposition adapter for BRIGHT-class queries in shadow, P95 ≤800 ms metered with token/compute accounting;
interactive tiers untouched (≤50 ms).
Acceptance: shadow paired delta with CI excluding 0 before ANY default-path discussion; budget table emitted; or a
clean PARK record.

## Paste D3 — P3 task (warm router + dreaming loop + sleep bounds)

P3 — H3/H4. Targets: `src/trace/v2/cortex.py` (ADDITIVE, beside `ActivationEngine`/`TwoPassPPREngine` — extend
them or add a new module; the name `ActivationRouter` is FORBIDDEN), `jobs.py`/`worker.py` (idle scheduling),
NEW tests. (May run parallel with P2b.)
Work: (1) warm-default router: replay/cached traces on hash match + quality-guard pass; cold path only on
drift/guard-fail/explicit ablation WITH logged reason; same trace schema; `release_id`-scoped, invisible until
CAP-GG. (2) Dreaming loop with [A5] bounds: N≤250 micro-batches, lock-hold p100 <15 ms, 8–20 active holons/cycle;
C3 consolidate-on-repeat (cold hit twice → warm promotion with provenance + decay); C8 distillation of mature
modules only (kill bar: nDCG drop ≤0.005 with ≥30% warm-byte cut, versioned rollback). (3) Spine-invariance proof:
drop projections → zero Spine-byte delta. (4) Guard logs (faithfulness/abstention/hallucination); L3 stays SHADOW.
Acceptance: bounds enforced under load; invariance proof green; invisibility pre-CAP-GG proven; NO-GO ships H2.

## Paste D4 — P4 task (ballot pack)

P4 — Evidence aggregation for the human ballot. Targets: NEW dossier assembly under `docs/program/inbox/<gate>/`
(scripts only, no new claims).
Work: (1) assemble the per-packet dossiers/receipts/manifests/router logs into one evidence manifest the
independent verifier can recompute from. (2) Draft the ballot rows (GO/PARTIAL/NO-GO per gate, rollback pointers,
cost/quality tradeoffs) for `06_DECISION_LOG.md` — draft only; the human signs. (3) Confirm no packet emitted
CERTIFIED/APPROVED anywhere (grep evidence).
Acceptance: manifest recomputable by a second party; ballot rows complete; zero self-certification strings.

## Paste E — CRITIC (fresh musecode session per delivery, blind)

You are the Trace blind auditor. Independent: no builder chat, never ask for it. Pasted evidence is your ENTIRE basis:
(1) branch-vs-base diff, (2) builder test outputs (packet tests + full-suite regression vs baseline),
(3) `--help` transcripts for every cited command, (4) the packet acceptance row + v1.1 §2 Law table.
Probe: (1) mocks of domain/storage in new tests, (2) silent fallbacks / swallowed errors, (3) Law tampering
(ceilings loosened, floors dropped, untagged numbers presented as law), (4) scope (every changed path inside the
packet target list; store/organization/cortex/retrieval changes additive; legacy behavior untouched),
(5) provenance (new spans carry offsets + hashes; no FTS5 text duplication), (6) PHANTOM TOOLING (every command
and flag exists in its transcript; `trace-bench` / `spine.*` / `ActivationRouter` anywhere = instant REJECT;
`run_1m` lineage must be current-Spine-native, not Lean-Schema), (7) evidence integrity (no CERTIFIED/APPROVED
strings; Amendment use within the packet's named scope, never widened).
Return EXACTLY:
VERDICT: APPROVED | QUARANTINED | REJECTED
VIOLATIONS: rule, filepath, line, snippet (or NONE)
REASONING: max two sentences.
Missing evidence -> QUARANTINED naming it. Never assume.

---

## Work plan

| Unit | Files | Acceptance |
|------|-------|------------|
| Step 0 | tree | clean base commit; Paste-A baseline recorded |
| P0 | NEW sign/verify scripts + gate manifest | Merkle trio re-verified; mapping 100%; frozen green unchanged |
| P1 | run_1m runner (rehab or rebuild) + env | 1M docs; replay 100%; ≤3.0x/≤1.6x on disk; WAL ≥800/s |
| P2a | retrieval.py logging + budget | P95 −20%, hard-slice parity; triple schema valid |
| P2b ‖ P3 | organization+retrieval ‖ cortex+jobs | kill bars (C1/C4); bounds + invariance (H3/H4) |
| P2c | NEW adapter (or PARK) | shadow delta CI>0 or clean park |
| P4 | dossier assembly | recomputable manifest; ballot rows drafted |

## Validation plan

- P0: Merkle recompute vs `5039acef…`; mapping completeness script; frozen commands re-run green.
- P1: replay parity report; `du`-style on-disk 4-number ≤ ceilings; ingest-rate log split WAL vs dense.
- P2a: eval-slice P95/nDCG A/B; triple-store spot audit.
- P2b: 100-probe C1 recall audit; 50-pair C4 conflict audit (<5% false-flag).
- P2c: budget meter + shadow CI; or park record with SLM probe.
- P3: bound-violation fault injection (N>250 / lock>15 ms / holons>20 must fail closed); projection-drop
  Spine-diff = 0 bytes; pre-CAP-GG invisibility grep.
- P4: second-party recompute; CERTIFIED-string grep empty.
- Highest-risk validation: P1's measured (not modeled) storage gate — the 7.54x failure returns if FTS5
  duplicates text or legacy schema leaks in.

## Risks / rollback

- SLM unreachable → P2c parks; lexical paths proceed (D2c).
- `run_1m_scale_gate.py` schema-incompatible → quarantine forensic-only; rebuild (D1 survey rule).
- Capsule sources unresolvable → H0 HOLD, re-stage; never synthesize substitutes.
- Uplift gates fail → SHADOW retained; weaker tiers still ship — negatives are passing results.
- Rollback per packet is branch deletion; merged packets roll back by revert of the merge commit.

## Open questions

None blocking. Carried assumptions: SLM availability unknown until P2c probes (parks gracefully); capsule
Windows-absolute paths normalize cleanly in P0 (HOLD if not); `psutil` fixed in P1 env work.

Saved to `docs/program/TRACE_STAGED_EXECUTION_PROMPTS_V11.md`. Reply Approve, Request changes, or Cancel.
On approval I stop here — you run the paste pack yourself; nothing is implemented until you dispatch Paste A.
