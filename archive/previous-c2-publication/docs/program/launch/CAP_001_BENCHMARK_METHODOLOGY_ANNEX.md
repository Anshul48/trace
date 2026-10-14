# TRACE-CAP-001 Benchmark Methodology Annex (Research-Grade)

> **Document ID:** `TRACE-CAP-001-BENCH-ANNEX`
> **Status:** Prospective annex. It does NOT amend any ratified threshold.
> Threshold or scope changes listed in §6 require an explicit Human Owner
> decision (`CAP-D012`) followed by a control-plane relock (`CAP-A03` pattern).
> **Placement note:** drafted in `launch/` (writable scope); promote to
> `docs/program/` via coordinator with relock. No locked file is modified
> by this annex.

## 0. What "research-grade" means here

Every benchmark claim must survive three independent challenges:
(1) exact dataset identity (version + checksum + verified counts),
(2) a statistical plan written before the run (paired tests, intervals,
multiplicity, power), and (3) a validated judge (the faithfulness validator
is itself measured before it grades anyone). The frozen floors in
`04_EVALUATION_PROTOCOL.md` §6 stay as-is until a human amends them; this
annex makes passing them *mean* something.

## 1. Dataset identity and count verification

### 1.1 BEIR (Thakur et al., NeurIPS 2021 Datasets & Benchmarks)

Source: [BEIR paper](https://huggingface.co/papers/2104.08663)
(Heterogeneous zero-shot IR benchmark, 18 datasets, standard metric
nDCG@10); canonical archives at
`https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/`
with per-dataset MD5s in the official table
([source](https://raw.githubusercontent.com/beir-cellar/beir/main/README.md)).

| Dataset | Split | Canonical test queries | Archive MD5 |
|---|---|---|---|
| SciFact | test | 300 | `5f7d1de60b170fc8027bb7898e2efca1` |
| NFCorpus | test | 323 | `a89dba18a62ef92f7d323ec890a0d38d` |
| FiQA-2018 | test | 648 | `17918ed23cd04fb15047f73e6c3bd9d9` |

**Count-verification rule (binds EVAL02):** after download, the manifest
builder asserts exact query/corpus/qrel counts against the table above and
records the *actual* counts plus archive MD5 in
`beir_musique_frozen_v1.json`. Any mismatch is `data_prerequisite_failed`,
never a silent redefinition of the split.

**Known defect flagged:** `WP-CAP-EVAL02` and the handoff state
"SciFact (1,000 queries)". The canonical BEIR SciFact *test* split has
300 queries. EVAL02 must either (a) adopt test/300 and correct the
plan text, or (b) name a different exact split/version totalling 1,000
with its own checksum — decided by the human before EVAL02 executes
(see §6, item B1).

### 1.2 MuSiQue (Trivedi et al., TACL 2022)

Source: [MuSiQue](https://arxiv.org/abs/2108.00573v1) — ~25K 2–4 hop
questions built by single-hop composition (MuSiQue-Ans), plus MuSiQue-Full
(~50K answerable/unanswerable contrast pairs).

The plan's "MuSiQue (500)" is a **frozen 500-question subset**, sampled once
under a recorded seed, stratified by hop count (2/3/4) and composition
structure, with question IDs pinned in the manifest. Resampling is forbidden
after first evaluation contact (peeking retires the pack, per protocol §12).
For the abstention lane, prefer contrast pairs in the MuSiQue-Full style
(answerable + matched unanswerable) over ad-hoc null queries, and record
which variant each null case came from.

### 1.3 What the manifest stores per dataset

Archive URL + MD5, download timestamp, split name, query/corpus/qrel counts
as observed, transform/segmentation ID, anchor-mapping method, license and
access constraint, and lane assignment (dev / qualification / promotion-sealed).

## 2. Metrics and the two latency regimes

Primary retrieval metric is **nDCG@10** (the BEIR reporting standard),
with Recall@20 / Complete Gold Coverage@20 as inclusion metrics and
citation precision where anchors are returned. This matches protocol §11;
no metric is replaced here.

**Latency reconciliation (resolves the open DEC-P-005 vs R2.1 conflict):**
two regimes coexist and a candidate passes *both* —

- *Local-index P95* (protocol §6: 15/20/25/50 ms per class; PPR ≤ 10 ms):
  raw retrieval serving path on the reference host.
- *End-to-end lane caps* (decision log, certified Level 2:
  domain_semantic ≤ 1,000 ms, multi-hop ≤ 2,000 ms, semantic_qa ≤ 3,500 ms,
  direct_lookup ≤ 25,000 ms, complex ≤ 60,000 ms): full pipeline including
  consolidation state, rerank, and evidence materialization.

`C2-POL-01` must name which regime binds each gate and record per-lane
budgets derived from the 100K run. Until then, report both; a pass in one
regime never excuses a breach in the other.

## 3. Statistical discipline (binds MOD01 through GE)

1. **Paired by default.** Every comparison is per-query paired on frozen IDs.
   Preferred: permutation/randomization test; the Wilcoxon named in CAP-GE
   is acceptable for skewed score distributions. Unpaired comparison is
   exploratory, never causal.
2. **Intervals, not points.** Report 95% bootstrap confidence intervals
   (≥10,000 resamples, seed recorded) for every floor comparison and every
   uplift claim (the +0.030 practical-effect rule).
3. **Multiplicity control.** Four suites ⇒ Holm step-down at α = 0.05 across
   the suite family before any promotion claim. Single-suite "wins" without
   correction are bake-off signals, not qualifications.
4. **Power floor.** No pass claim on a suite under 200 queries without a
   pre-registered equivalence margin (this binds NFCorpus at 323: report CI
   width; a floor pass with a CI spanning >0.10 is `investigate`, not `pass`).
5. **Promotion pass rule.** A gate floor passes only if the point estimate
   clears the floor *and* the lower 95% bound clears floor − 0.02.
   Bake-off admission (GC) may use point estimates; qualification (GE) and
   1M gates (GF/GG) use the full rule.
6. **Denominators are complete.** Failures, timeouts, empty outputs, and
   provider errors stay in every denominator (protocol §13); exclusions are
   listed with counts and reasons.

## 4. Validating the validator (binds EVAL03 before CRX03/MOD01 use)

The faithfulness gate (NLI τ = 0.95, proposition support ≥ 95%) is a
measuring instrument and must be calibrated before it judges:

1. **Adversarial rejection:** 100% rejection on a frozen hallucination set
   (unsupported entities, invented numbers, cross-atom splices).
2. **Human adjudication:** dual-adjudicated sample of ≥ 200 propositions
   from real candidate outputs, with Cohen's κ reported; κ < 0.70 sends the
   extractor back, not the threshold down.
3. **No single-model judging:** the NLI model never shares weights, data, or
   provider revision with any generator under test; disagreements are
   retained as raw judgments, not majority-smoothed away.

## 5. Ablation ladder (binds MOD01, INT01–03)

Report, on identical frozen inputs: lexical-only, dense-only, fusion,
fusion+rerank, control summaries, model summaries without relations,
relations without summaries, full Cortex retrieval without synthesis, and
synthesis on the identical bundle. A mechanism that cannot show its marginal
contribution keeps experimental status (promotion rubric §6).

## 6. Proposed amendments to locked files (human decision required)

Exact texts for approval + relock. Nothing below is in force.

- **B1 (EVAL02 packet + protocol §6.3):** replace "SciFact (1,000 queries)"
  with the count-verification rule of §1.1 (default: test/300).
- **B2 (Gate matrix, CAP-GB row):** add additive sub-clearances GB-SAFE
  (GW01-03, CRX01, EVAL01/03) and GB-RET (RET01-04, EVAL02) so safety policy
  can advance while retrieval finishes — no node rescoped.
- **B3 (Lease map + DAG):** serialize JOB02 before CRX03 on
  `service.py`/`store.py` (or split by file section with merge order);
  concurrent execution on overlapping leases stays forbidden.
- **B4 (Scale plan §3.2 + gate matrix GD/GE/GF):** monotonic storage profile
  proposal — 3.0x (10K) → 3.0x (100K) → 2.5x (1M) — plus a mandatory
  per-component lower-bound model (Spine/FTS/vectors/graph/reserve) before
  the next candidate freeze. Current 3.5x mid-ladder loosening is withdrawn.
- **B5 (Gate matrix, CAP-GG row):** add the 0.01%-rate sampling plan
  requirement (adjudicated sample sized for a 0.01% rate with 95% CI;
  no GG invocation without it).
- **B6 (C2-POL-01):** adopt the two-regime latency rule of §2.

## 7. Praxist hook

Once Trace is running, benchmark *optimization* (fusion weights, PPR bounds,
cascade thresholds, atomization) moves to the Praxist loop defined in
`CAP_001_PRAXIST_OPTIMIZATION_LOOP.md`. This annex defines the measuring
stick; Praxist moves the needle without touching the stick: promotion sets
stay sealed, the evaluator stays immutable, and threshold changes stay human.
