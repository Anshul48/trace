# RESULT — c-fuse-1: route candidate export + admission ceilings (stage 1)

## Verdict

CEILING PASSES: 45/50 >= 41/50; stage 2 may proceed

## What was done

- Exported C_route (rows admitted for scoring per query) from a read-only
  offline copy of the guided router: top-3000 parents/shard by centroid score
  (profile-Q table), members via filed assign files. No live-service, engine,
  or model change; no network; label-blind export for all 555 X0 + 50 old.
- C_pool (S=1600 2-bit shortlist) is NOT exportable without an engine edit
  (no dump flag; receipt carries only topk). Proceeded with C_route only.

## Validation (STEP 2 gate: >=45/50)

- Exact dense top-10 restricted to C_route vs recorded live top-10
  (`trace-100m-hier-lift/raw_F10_tr.jsonl`): **50/50 agree (set+order)** → ACCEPT.
- Exact-recipe cross-check (my f32 exact top-100 vs `raw_exact_top100.jsonl`):
  50/50 order. Live-in-C: 10/10 rows on all 50 queries.
- Recorded top-10 == d1-profile Pass B `stages-50.tsv` ordinals: 50/50.
- Per-query table: `validation.json`, `validate.log`.

## Ceilings

Old 50 (label = source ordinal):
- admission (source in C_route): 45/50 (s8-probe 7/10, authored 38/40)
- keyword top-10: 41/50 (published 82% reproduced); exact/final top-10: 26/50
- keyword-success admission (BM25-top10 AND in C): 38/50; keyword hits
  admitted: 38/41 (missed: q13, s8-100, s8-180)
- given admitted: exact top-10 26/45, keyword top-10 38/45
- failure split (24 final-misses): absent from C 5 (q13, q23, s8-80, s8-100,
  s8-180) / outside pool n/a (C_pool unobservable) / in C below cutoff 19
- boundary robustness: max admitted source-parent rank 2614 (386 below the
  3000 cutoff); only miss near boundary is q23 (3091). Verdict robust to
  small nomination perturbations. s8-80 is a deep miss (rank 21000).

X0 DEV only (167; TEST labels never touched, 388 TEST ids excluded, 0 used):
- admission: 167/167 (style0 question 51/51, style1 keyword 47/47,
  style2 description 69/69)
- keyword top-10: 118/167 (37/51, 16/47, 65/69); exact top-10: 125/167
  (42/51, 23/47, 60/69); keyword-success admission 118/167
- failure split vs exact-top-10 proxy (42 misses): absent from C 0 / in C
  below cutoff 42.
- BM25/dense lists reused from x1 `raw_B/raw_D.jsonl` (filed index, lucene
  k1=1.2 b=0.75, k=100 — params verified in `params.index.json`).

## Could not observe / deviations

- Engine-internal nomination centroids/float/tie rule UNVERIFIED (binary-only);
  store has no centroid file so they are store-derived (build audit cos≥0.9999
  vs filed centroids); validation consequence tested 50/50.
- Backend 5-parent nomination is display-only, not the routing (see ROUTE-SPEC).
- X0 DEV "final top-10" = x1 exact-dense proxy (stated before computing; no
  routed top-10 exists for X0, live service not queried).
- Old-50 "style" split reported by kind (s8/authored): old searches have no
  question/keyword/description styles.
- Export run-1 hit a save-path bug (savez suffix); data verified complete and
  renamed, counts rebuilt deterministically (see `export.log`).

## Integrity

- 36 input hashes before==after (sha-before.txt/sha-after.txt): unchanged.
- Q555.f32.npy sha256 80150bde…da08acc; candidates.npz sha256
  1e87fedba41425235c5bc63694e056ba6688548ff59d15b1b2d86b9ded2ef5c2.
- candidates.npz: 605 keys, sorted int32, 65,999,257 ordinals, ~264 MB.
- Live :8495/:8496/:8497 untouched (no queries sent); originals never edited.
- Load gate: export waited (3.06→1.95, unflagged); RAM ≥28 GB throughout.
- Tests: `test_cfuse1.py` 6/6 OK (venv python, `-W error::ResourceWarning`).

## Files (lease `/home/anshul/owner-hub/scratch/wave2/c-fuse-1`)

ROUTE-SPEC.md, export_candidates.py, validate.py, ceilings.py,
test_cfuse1.py, candidates.npz, counts.jsonl, validation.json,
ceilings.json, export.log, validate.log, ceilings.log, boundary.log,
test.log, sha-before.txt, sha-after.txt, RESULT.md.
