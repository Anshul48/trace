# 10M retrieval rung — Phase-1 build report

Date: 2026-10-04. Owner dir: `tl-eval/evidence/scale10m-2026-10-04/`.
Status: **phase 1 DONE** (corpus + ingest + index + 1-query smoke).
Phase 2 (809-query campaign) is GATED — awaiting coordinator go.

## 1. Corpus construction (exact TOK-10M vector, token-identical)

Frozen order `[scifact file order][curated file order][wikipedia_delta
file order]`, smallest whole-doc prefix ≥ 10M TOK-v1:

| Part | docs | TOK-v1 | WP | Source |
|---|---|---|---|---|
| scifact-full | 5,183 | 1,167,874 | 1,737,313 | `/tmp/tl-bench-env-20260927/cache/scifact/corpus.jsonl` |
| curated paras | 100 | 1,748 | 2,561 | trace-bench `trace_engineering_curated.json` |
| wikipedia delta lines 0..7797 | 7,798 | 8,833,759 | 13,672,133 | `trace-scale-data/staged_1m/wikipedia_delta.jsonl` |
| **prefix total** | **13,081** | **10,003,381** | **15,412,007** | terminal doc `wikipedia:2372` (line ix 7797) |

Minimality verified: `cumsum[n-1] = 9,999,603 < 10,000,000 ≤ cumsum[n] =
10,003,381` (matches the manifest assert verbatim).

Vector provenance: `/tmp/tl-tok-10m-s2-2026-09-29/tok-10m-s/records/` —
`doc_manifest.json` (13,081 rows), `token_boundary.json`,
`phase1.json` (`vector_sha256 d181dd80…21ae741`, seed 20260928010,
terminal `wikipedia:2372`). Verification: `corpus_check.py` (stdlib) →
`corpus_check.json`; WP method = scale-stage WP census
(`BertTokenizerFast`, vocab 30522, `add_special_tokens=False`) →
`tok_wp_prefix.py` → `tok_wp_prefix.json`.

Per-doc verification (13,081/13,081): id 0 mismatches, tok_count 0,
cumsum 0, sha 3 — all three explained (below). Doc_ids unique.

Two deliberate/benign deviations from the manifest, both 0-token-impact:
1. Curated paras ingest under run_quality's `para-N` ids (NOT the
   manifest's `cur-NNN`) so the S2/S3 gold mapping stays valid against
   this index. Token bytes identical (0 curated sha mismatches).
   Note: the curated FILE sha drifted (`210a20a4…` vs manifest
   `39acf569…`) but the `corpus_text` pin matches exactly (`e8bd5f8d…`)
   — cases/metadata drift, counted bytes intact. Scifact (`dec31c81…`)
   and delta (`ffe48544…`) file shas match the manifest.
2. Three scifact docs (ranks 1629/2626/2730 — ids 9291668, 16461149,
   17422777) were counted un-stripped in the manifest but ingest
   `.strip()`ed per `_load_beir`. Whitespace-only: tok identical,
   verified both shas. Ingest text follows run_quality (the retrieval
   contract), not the manifest bytes, for these 3 docs.

Delta counted-text convention was resolved empirically (4 candidates
tested against the manifest's first delta sha): BEIR-style
`(title + "\n" + text).strip()` — identical to `_load_beir`, so the
ingest path and the token vector agree byte-for-byte on all 7,798
delta docs.

## 2. Ingest (run_quality path, run_quality.py UNTOUCHED)

Standalone driver `driver_10m.py` imports run_quality machinery
(`load_scifact`, `load_curated`, `metrics_for`) + frozen tlsys. No
edits to `run_quality.py` or `tl-sys/` (import-only; no diff to
record). Ingest contract = combined/full config verbatim: encoder
`sentence-transformers/all-MiniLM-L6-v2`, `emb()` batch_size=64,
`lease_owner="quality-campaign"`, `store_id="quality-scale10m"`,
`place_xdoc=True`, `place_t=None`, `tl_cfg={}`.
Env: `HF_HOME=/tmp/tl-bench-env-20260927/hf-cache HF_HUB_OFFLINE=1
PYTHONHASHSEED=0`, venv `tl-sys/.venv/bin/python`.

| Measure | Value |
|---|---|
| ingest_s (wall) | 9,451.9 (~2.63 h; encode-bound, within the 2.5–3.5 h estimate) |
| atoms / holons / xholon ops | 63,441 / 13,081 / 18,523 (0 skipped, 0 deferred, backlog empty) |
| index-build s (NarrowIndex) | 203.3 (~3.4 min; within the 2–5 min estimate) |
| index atoms / holons | 63,441 / 19,817 (= 13,081 per-doc + 6,736 xdoc latest versions) |
| store | 1,050.8 MB at `/tmp/tl-scale10m-2026-10-04/stores/scale10m` |
| peak RSS | 1,649 MB (`ru_maxrss`; VmHWM heartbeats agree: 1,649,440 KB) |
| pin | `18869b2e-662c-462d-a695-5bf593e48cbf:0:95045` |

Cross-check: 63,441 + 13,081 + 18,523 = 95,045 commits = pinned seq
95045. ✓

Store density: 105 B/TOK-v1 (scifact-full was 120) — same regime.
Ingest rate: ~1,058 TOK-v1/s (~6.7 atoms/s) — same encode-bound order
as §2 (880–1,140 TOK-v1/s).

## 3. Gold-coverage check (the §4 query trick)

`corpus_check.py` §5: 809 tuning qids (train.tsv), 565 distinct gold
docs with score ≥ 1 → **565/565 in the prefix, 0 missing**. The driver
independently rebuilt the run_quality scifact task list: **809 tuning
tasks with rels**. The 809 S1/tuning queries stay valid against the
10M superset index. ✓

## 4. Smoke (1 query, all 5 systems — phase-1 allowance only)

First tuning task (qid `0`): every system served 10 results, 0 errors.
Quality values are n=1 and NON-evaluative (no tuning, no conclusions):

| System | ms (cached-encode, independent-v2) |
|---|---|
| tl | 2,694.4 |
| tl-unpruned | 2,753.8 |
| bm25 | 2,134.7 |
| dense | 367.0 |
| hybrid | 2,447.2 |

No other query runs. No tuning of any kind against the new index.

## 5. Phase-2 readiness

- Index built, pinned, committed store quiescent. Trace:
  `/tmp/tl-scale10m-2026-10-04/phase-out/trace-scale10m.json`.
- 809 tuning tasks confirmed servable.
- Exact phase-2 command (run from workspace root, same env as §2):

```bash
HF_HOME=/tmp/tl-bench-env-20260927/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0 \
tl-sys/.venv/bin/python tl-eval/evidence/scale10m-2026-10-04/driver_10m.py \
  --phase queries --out /tmp/tl-scale10m-2026-10-04/phase-out \
  >>/tmp/tl-scale10m-2026-10-04/queries.log 2>&1
```

Phase-2 cost projection from the smoke: ~10.4 s/query across 5 systems
→ **~2.3 h for 809 queries** (plus cached batch-encode of 809 queries
up front, minutes). Longer than the §4 10–20 min guess: per-query BM25
full-scans 63,441 atoms (BM25 leg ~2.1 s of every system's time except
dense).

§4 acceptance pre-check: (a) ingest + index 0 errors, store 1.05 GB <
5 GB ✓, RSS 1.65 GB < 8 GB ✓; (b)/(d) phase 2; (c) **flag**: smoke TL
~2.7 s/query suggests TL p50 at 10M will exceed the provisional < 1 s
gate — per §4 that outcome is the finding "superlinear latency
regime" (BM25-scan-dominated), not a failure. Dense leg stays fast
(0.37 s).

Blockers: **none**. Caveat: the shell tool began failing with runtime
auth errors after ingest completed, so `git status`/`du` re-verification
was unavailable at report time; no writes were made outside the owned
dir + `/tmp/tl-scale10m-2026-10-04/` (all other access was read-only),
and `run_quality.py`/`tl-sys` were never edited. Owned dir contents
(~35 KB total): `BUILD-REPORT.md`, `COMMANDS.md` (every command),
`corpus_check.py/.json`, `tok_wp_prefix.py/.json`, `driver_10m.py`,
`phase1.json`.

**Readiness: phase 1 DONE. Built index + report complete. Awaiting the
phase-2 go — the query campaign will NOT run without it.**
