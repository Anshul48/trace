# TL v3 input freeze + staging — REPORT (lane-v3-inputs)

Worker: TL v3 input-freeze (lane v3-inputs). **ACK: launch job v3
(`launch-20261006T1237Z/job.md`, task 3) + Codex CONDITIONAL-GO verdict
read and applied; task-3 scope only.** No product/gate source write, no
canonical-record write, no `encode-5050/` or `release/` write (both
read-only throughout; `encode-5050/` reads were hash/geometry only). The
superseded `df5b771b…` package was NOT staged as a launch candidate; the
repaired source package arrives via post-repair refreeze (task 4, not
this lane). W6 HELD observed — no confirmation runs, no gate runs, no
retrieval runs; all grounding below is static (source bytes) BEFORE
results. Resume note: prior worker cancelled by runtime; this worker
re-verified the slice (hash + row count + parent identity) before reuse.

## 1. Frozen binding files (all pins real, zero placeholders)

Dir: `tl-eval/evidence/m2-2026-10-06/coordination/launch-20261006T1237Z/lane-v3-inputs/`

| File | sha256 | Bytes |
|---|---|---|
| `docs-10m.jsonl` | `04bbbb3ea3425a49491559173b20280fb286edeeef49c8293aebc0b92bcce3fd` | 64291035 |
| `queries-10m.json` | `77336d62c117da5f6c8ed00ca2dbee52a5858cbb7ee4a1b9de40c0200cd2cf9a` | 8377 |
| `relations-10m.json` | `fef3ec6a200f12fce9cbdc6d90d041281921a25a86418a17fa40c098045ecdb5` | 1281 |
| `corpus-manifest-10m.json` | `e56ac0a940f5e7cc9d8f22a49c9e31c9c4d842835104dc882f2e178155367c1d` | 1164 |
| `CONFIRM-INPUTS.v3-10m.json` | `ece682c79fc05b3dbaf8835759295be9e3f7119641aab4cb679f5909d1ca72e9` | 168767 |
| `prefix-doc-ranges.json` | `c255a52ff85a7adaa629b51d9f0b5469fcf4edc756b59358093037fe677db0c6` | 148231 |
| `derivation.json` | `1343550c814d600bff7d6849382c4dcd16479440fe8bb493bd630fe61f348ff6` | 389409 |

Parent corpus: `tl-eval/evidence/m2-2026-10-06/encode-5050/docs-100m.jsonl`
`c098fdace3a73efc83f3c71a9e024b3cd77114fd0d7f2348c7c813995e6b0e09`
(30,927 docs / 569,330 chunks / 100,010,221 TOK-v1 — preflight pin,
reused, not re-hashed wholesale; slice identity proven below).

Criteria: `tl-eval/gate_runner/CRITERIA.v3.json`
`e7d0139a913bbe561d2ef0f5f96dd083cb5e6fc497cb3f9496635f05ce4b9cc1`
(re-hashed before use; G4 tol=0, G6 >=3x>=5, 8192 MiB worker cap).

Slice verification (this worker, read-only): sha256 `04bbbb3e…`
(64,291,035 bytes, 3,099 rows) re-hashed; **3,099/3,099 rows
byte-identical** (doc_id + text sha256) to parent `docs-100m.jsonl`
rows. The slice is NOT a file-order prefix (parent ordinals span
12..30919 non-contiguously; per-row parent ordinals in
`derivation.json`). Slice totals: **58,629 chunks / 8,707,790 ws-tokens
/ 10,327,998 TOK-v1** (owning chunker + TOK-v1). Sealed-cache coverage:
**58,629/58,629 slice chunk keys present** in `emb_cache/index.jsonl`
(strict file-backed lookup safe; 0 misses possible from coverage).

## 2. Seed geometry (G4 tol=0, exact)

Method: exhaustive exact-equal chain search over slice file order with
the OWNING chunker (`tlsys.ingest.chunk_text`, 200/50) and TOK-v1
(`[^\W_]+`), then a seeded choice
(`random.Random(20261006).choice`) among feasible chains. Result:
**exactly one feasible chain** — the choice is degenerate and fully
determined:

- P0 = slice docs 0:1009 (1,009 docs)
- P1 = slice docs 0:2033 (adds docs 1009:2033, 1,024 docs)
- P2 = slice docs 0:3099 (adds docs 2033:3099, 1,066 docs)
- Every append: **exactly 19,543 chunks + 3,442,666 TOK-v1** (tol=0,
  d_chunks=0.0, d_tokens=0.0). Doc counts (1009/1024/1066) disclosed,
  never an equality bar.

Frozen workload: `append_workload = {target_chunks: 19543,
target_tokens_tok_v1: 3442666}` in `CONFIRM-INPUTS.v3-10m.json`;
`prefix_doc_ranges` carries the three cumulative doc-id lists;
`seeded_bases = {seed: 20261006, bases: [1009, 2033, 3099]}`.
No branch repetition was needed (single exact chain covers the corpus);
the criteria's "compatible isolated seeded branches" clause is recorded
as not-invoked. The v1 `--plan-prefixes` tool (whitespace denominator)
is not applicable to the v3 TOK-v1 rule.

Verification (independent paths, all green):
(a) freeze-script fresh recompute with the owning chunker: appends
`[(19543, 3442666)] x 3`, exact;
(b) committed `gate_lib.plan_workload_appends` (bases 1009/2033,
tol=0): feasible, both post-base appends land exactly (d=0.0);
(c) `validate_source_pins` on the frozen envelope: 9/9 pins valid;
(d) recursive null scan of `full_tier_binding`: zero nulls;
`is_placeholder_sha` on all four file pins: all False;
(e) reload + runner-shape assertions on the final bytes (queries dict
with 5 non-empty classes; relations dict with `relations`/
`qual_signals`; all 19 cases' expected/bridge/pair docs and all
relation endpoints in the corpus; G0-equivalent: each file pin
re-hashed and matched). One self-caught freeze-script bug was fixed
before freezing (trailing comma emitting 1-tuples for two files);
regression-covered by (e).

## 3. Case grounding (source facts, frozen before results)

Grounding rule (asserted by the freeze script, fail-closed): every
expected doc is in P0 (hence queryable at EVERY prefix); every span is
a verbatim substring of an expected doc; every scored span sits fully
inside an owning-chunker chunk that also contains a query term
(len>=4) — 33/33 spans verified. The r2 bridge spans are the documented
exception (bridge arrives via traversal only, fixture-r2 shape). No
retrieval was run to author or tune these cases.

Per-class table (id, query, expected docs, spans; all docs P0):

narrow (retirement n1 first; tail probes outcome_only, labeled scope):
- n1 "Achaean League wars Romans conquer Greece" -> [35008, 18372,
  24516] (wikipedia:) :: "Achaean League"; "conquer the Achaean League
  and southern Greece becomes a Roman province". Retirement probe case.
- n2 "Agrippa king of Judea Marcus Vipsanius Rome" -> [34815, 34808,
  16032] :: "Claudius makes Agrippa king of Judea";
  "Marcus Vipsanius Agrippa".
- n3 "agglutination morphemes Uralic suffixes" -> [18077, 31715] ::
  "Agglutination, the compounding of morphemes into a single word";
  "extensive use of independent suffixes (agglutination)".
- n4 "airstrikes coalition Iranian positions" -> [14672, 14653, 11812]
  :: "conducting a series of airstrikes notably after the execution";
  "airstrikes were claimed to target Iranian positions".
- n5 "acivicin glutaminase inhibitor cancer cell viability" ->
  [20941] :: "acivicin, and CB-839 have been shown to inhibit
  glutaminase"; "reducing cancer cell viability".
- tail-gap-1 (SCOPE: diagnostic dense-gap probe, unscored,
  outcome_only; gap wikipedia:1029@33782 len 210) "pessimist
  philosophies Schopenhauer scientific materialism Herbert Spencer" ->
  [1029] :: "pessimist philosophies from Schopenhauer onward";
  "Scientific materialism, advanced by Herbert Spencer".
- tail-gap-2 (SCOPE: diagnostic, unscored; gap wikipedia:32901@35373
  len 348) "Magic in the Moonlight Allen airy concoction" -> [32901]
  :: "Magic in the Moonlight is Allen's most gratifyingly airy
  concoction".
- tail-gap-3 (SCOPE: diagnostic, unscored; gap wikipedia:5211@72695
  len 391) "initiatory rite baptismal candidates symbolically purified
  Family of God" -> [5211] :: "As an initiatory rite into membership
  of the Family of God, baptismal candidates are symbolically
  purified".

cross_topic:
- c1 "Actroid humanoid robot air servosystem actuator" topics
  [humanoid robots, pneumatic actuator servosystems] -> [713] ::
  "demonstrated the Actroid at Expo 2005";
  "originally is used for the actuator".
- c2 "Achaean League conquests and glutaminase inhibition in cancer"
  topics [Achaean League, glutaminase inhibition] -> [35008, 20941] ::
  "Achaean League"; "inhibit glutaminase".
- c3 "Uralic agglutination suffixes and F-35 airstrikes Iranian
  positions" topics [Uralic agglutination, F-35 airstrikes] ->
  [31715, 11812] :: "independent suffixes (agglutination)";
  "F-35Is in two attacks" (chunk-70 co-located with "airstrikes").

relational (paths):
- r1 "agglutination morphemes independent suffixes" (min_hops 1) ->
  [18077, 31715] :: same spans as n3. Edge 18077->31715 "links"
  (shared: agglutination, morphemes — verified both endpoints).
- r2 "acivicin glutaminase" bridge 14663842 (min_hops 1) -> [14663842]
  :: "IDH1 mutations alter citric acid cycle metabolism"; "increased
  oxidative tricarboxylic acid metabolism". Query terms are df=1 in P0
  (doc A=wikipedia:20941 only) and ABSENT from C (asserted); path
  A->B (20941->3954 Biochemistry; shared glutamine/gluconeogenesis/
  pyruvate) -> C (3954->14663842; shared glutamine/mitochondrial/
  metabolism). Fixture-r2 shape.

qualifier (pairs):
- q1 "kashrut observance pork abstinence" pair [27669, 16881] ::
  "Observing kashrut regulations" (27669 Spanish cuisine, affirm pole);
  "partially observe kashrut" (16881, limiting pole). Signals:
  27669 {negated False, topic kashrut-observance}, 16881 {negated True,
  same topic} (fixture-q1 shape; polarity grounded in the quoted
  passages; supplied-input path).

g2_probes (paths):
- g2a known-group "Agrippa Postumus Marcus Vipsanius Judea" ->
  [34815, 34808, 16032] :: "Agrippa".
- g2b long-multitopic "Norman Conquest White Tower ravens Ravenmaster"
  -> [31165] (77,127 chars) :: "Norman Conquest" (off ~1225); "At
  least six ravens are kept at the Tower at all times" (off ~62602).
- g2c overlap "humanoid robot Sorena airstrikes Khamenei" -> [14653]
  :: "humanoid robot Sorena 2"; "airstrikes" (n4 group x c1 topic).
- g2d rare-topic "Acnasol erythromycin brand" -> [10090] :: "Acnasol".
- g2e append-correction "acentrism Copernican principle humans center
  universe" -> [7327] :: "acentrism". Correction case (fixture-g2e
  shape): the runner's scratch exercise appends this query to corpus
  row 0 (wikipedia:31165) under a new id and serves it.

Queryability matrix (static: expected docs present in prefix):
all 8 scored narrow/cross-topic cases (n1-n5, c1-c3) + all 3 tail
probes + r1/r2 + q1 + g2a-g2e are queryable at P0, P1, AND P2 (every
expected doc is in P0; 11/11 narrow+cross_topic per prefix, requirement
>=5). G6 sampler feasibility: 11 servable narrow+cross_topic queries at
every prefix pin x 5 pins (3 prefixes + publication + hier) — the
seeded >=3x>=5 sample is structurally feasible at seed 20261006.

Tail/gap scope labels: tail-gap-1..3 carry `outcome_only: true`,
`scope: "diagnostic tail probe (dense-window gap passage); unscored;
outcome_only"`, and the exact `gap` record (doc/offset/length + source
audit file). They exercise gap-passage retrieval without touching any
frozen bar. Gap passages were extracted byte-exact (offset/length
asserted against the audit file and the doc text).

Validation summary: freeze script asserts (all pass): 33/33 spans
verbatim + chunk-sharing; 3/3 relation shared-term sets in both
endpoints; r2 zero query-term overlap with C; acivicin/glutaminase
df=1; unique ids per class; 11 narrow+cross_topic; tail gaps valid.

## 4. Cache / runtime / profile pins

Sealed cache (reused, re-verified read-only this session):
`gs://tl-m2-runs-d1995b06/m2/encode-5050/`, **17/17 objects,
1,233,576,691 bytes** (GCS recursive listing 2026-10-06; sizes match
the 09:52 UTC upload receipt exactly). Config `25989b870b5ccfee`
(FP32, dim 384, `tl-gpu-embcache-v1`), model
`sentence-transformers/all-MiniLM-L6-v2` rev
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41` (mean pooling, trunc 256,
no normalize). Local sha256 re-hash (read-only) of all 17 files —
chunk_manifest `39f04461…b768` (= lane-3's cited pin, corroborated),
run_meta `1c40c690…ab0`, preflight `6bddf685…082`, index
`885d31c0…23ed`, meta `e5f9c706…9761`, shards s00 `41cec4b0…59b`, s01
`1c8c2966…fdb`, s02 `50126e32…10`, s03 `b79ec780…c93`, s04
`3a10a153…7c`, s05 `62511ef2…664`, s06 `509e4605…1ed`, s07
`906231d8…80b`, s08 `f79d30fb…c2b`, s09 `530bcea2…a5e`, s10
`e8206002…fdf`, s11 `5e757427…feb` (full table:
`staging/SHA256SUMS.cache`). Encode counters (run_meta): 569,330
chunks / 525,357 truncated / 100,010,221 TOK-v1; chunker
`tlsys/ingest.py` pinned `fc78743a…` at encode time — the live tree
reads `016750f1…754` (lane-2 one-line `cached()` switch; lane-3
verified chunking byte-identical; this freeze used the live owning
chunker, the same authority the runner uses).

Runtime pins (freeze-time record; VM-venv re-verification deferred
to staging when capacity returns):
GPU-encode packages (run_meta, read this session): torch
2.14.0+cu130, sentence-transformers 2.7.0, transformers 4.57.6,
tokenizers 0.22.2. Lane-3 verified local pins (reused receipt):
python 3.12.3, numpy 2.5.3, blake3 1.0.10, huggingface_hub 0.36.2,
safetensors 0.8.0; HF snapshot `…/all-MiniLM-L6-v2/snapshots/
1110a243…/` (13 files). Env: `HF_HUB_OFFLINE=1`,
`HF_HOME=<repo>/local-data/hf-cache` (local) / `/srv/tl/weights` (VM),
`PYTHONHASHSEED=0`.

Production profile (frozen, from lane-3 §4 + CRITERIA.v3): tier full;
seed 20261006; `--oracle-as-mb 8192` (per-worker RUSAGE_SELF peak
recorded); `--place-xdoc`; `--drain-budget 2`; journal-enabled
intake; FP32 homogeneous descriptors; 10-op commits; strict
file-backed cache config `25989b870b5ccfee`; bounded serving cfg
(HIER_PARENT_BUDGET default 200; partition-IVF on both dense legs +
bounded hierarchy sidecar); `--oracle-timeout-s 300`. Exact invocation
in `staging/campaign-10m.sh` (fails closed on missing refreeze
artifacts / preflight PASS; this lane never launches it).

## 5. VM staging receipts

VM: `tl-m2-cpu`, project `project-d1995b06-980e-4def-afa`,
zone `us-central1-a`, shape `custom-12-65536` (12 vCPU / 64 GB RAM),
30 GB boot + 250 GB data disk (`tl-m2-data`).

Pre-action state: VM TERMINATED (verified 2026-10-06 before any
staging attempt); `/srv/tl/stores` partial-staging check requires a
running VM and could not be performed (see blocker).

BLOCKER (external limit, reported per job.md): `gcloud compute
instances start tl-m2-cpu` refused **6 times** over 16:25–16:45 UTC
(a 7th attempt was interrupted when the blocker was declared) with
`reason: resource_availability` — "The zone
'…/us-central1-a' does not have enough resources available to fulfill
the request" (custom-12-65536 shape). No project reservations exist
in us-central1-a (`reservations list`: 0 items), so nothing in this
lane's scope unblocks the start; no zone/shape change was made
(coordinator decision). Final state re-verified: **TERMINATED**,
**0 VM minutes** consumed by this lane, 0 cloud spend.

Delivered instead (all staging work that does not need a live VM):
`staging/` bundle — `SHA256SUMS.cache` (17 sealed hashes, locally
re-hashed read-only), `stage-cache.sh` (idempotent 17-object download
to `/srv/tl/stores/encode-5050/` + `sha256sum -c` + receipt),
`stage-verify.sh` (11 machine-readable checks -> `staging-verify.json`;
exit 0 only on zero FAILs; package-dependent checks report `blocked`
until refreeze), `campaign-10m.sh` (exact 10M invocation; refuses
without package + pinned inputs + suite record + preflight PASS +
fresh out dir), `README.md` (VM layout map). All three scripts pass
`bash -n`; all embedded pins match the §1 table. First action when
capacity returns: start VM, inspect `/srv/tl/stores` for partial
staging, run `stage-cache.sh`, upload this lane's inputs to
`/srv/tl/stores/inputs-10m-v3/` (+ `CRITERIA.v3.json` copy), run
`stage-verify.sh`, record minutes, stop when idle.

## 6. Open slots: ZERO

Every binding slot in `CONFIRM-INPUTS.v3-10m.json`
(`full_tier_binding`) is filled with a real pin (recursive null scan:
zero nulls; placeholder-sha check on all four file pins: all False):
docs_file (path+sha `04bbbb3e…` + bytes/docs/chunks/tokens),
queries_file (`77336d62…`), relations_file (`fef3ec6a…`),
corpus_manifest (`e56ac0a9…`), prefix_doc_ranges (3 cumulative lists,
1009/2033/3099), append_workload (19543/3442666), seeded_bases (seed +
method + bases), oracle_sample (3/5/20261006), source_pins (9/9 valid:
parent corpus, 10M slice, 3 upstream preflight pins, queries,
relations, manifest, criteria v3), cache_binding (bucket, 17 objects,
1,233,576,691 bytes, config/model/revision/precision/dim), criteria
binding (`e7d0139a…`). No skipped mandatory cells (no run was made or
skipped by this lane). The only post-freeze prerequisites live
OUTSIDE this lane: refreeze package + suite record + preflight PASS
(coordinator's next step).

## 7. Notes / risks / handoff

- Post-repair refreeze needs (coordinator): place the refrozen package
  at `/srv/tl/pkg` (repo layout), this lane's inputs at the
  ROOT-relative lane path (staged VM copy at
  `/srv/tl/stores/inputs-10m-v3/` is the transfer source), the bound
  green suite record at `/srv/tl/staging-v3/suite-record.json`, the
  source manifest at `/srv/tl/staging-v3/SOURCE-SHA256SUMS`, then run
  `stage-verify.sh` and produce `preflight.json`. `campaign-10m.sh`
  refuses until all of that (incl. preflight PASS) is present.
- The v3 inputs are repair-independent (criteria v3 + sealed cache +
  sealed corpus + grounded cases); no refreeze of THIS lane's files is
  expected — only placement.
- 30M/100M growth path: same freeze procedure (exact-equal chain
  search over the larger slice + P0-grounded cases + tail probes);
  exact-thirds geometry is slice-specific and will NOT transfer
  verbatim — re-run the search, keep seed 20261006, record the chain.
- Risk: zone capacity for `custom-12-65536` in us-central1-a (see
  §5). No shape/zone change was made (coordinator decision).
- Reused receipts (not re-created): 09:52 UTC cache upload receipt,
  lane-3 runtime pins + 36/36 suite, lane-1 fixture/small-full proofs,
  preflight-100m source pins. Re-verified this session: slice
  identity, cache object sizes (GCS), cache file hashes (local),
  manifest pin `39f04461…`, criteria v3 hash, geometry (two paths).
