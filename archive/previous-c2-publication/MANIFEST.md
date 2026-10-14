# MANIFEST.md — TRACE candidate manifest (A2 review contract)

## Identity

| role | SHA |
|---|---|
| remote-old main | `a24a937009fec41e6dcb6d2ca31d3c1783ac97f7` (tree `bc5134725425ff56b9fae434cdd77f1a9b7a0a60`) |
| content commit C1 | `6e931b433b51a6e2f5eeb6530e0c95d9f6e1800d` (tree `88dfc874ebc1adaf97bc90b4582e88c0fcc983e9`) |
| candidate commit C2 | `c0eede02255f9418fe8c0cef6411945f9c80c862` (tree `d4544ae5bfb498c3ac1701b6baca8cae793ccfd2`): C1 + this file only — HOLD per A51 (old data verifier) |
| successor commit C3 | C2 + corrected verifier adoption only (A50–A53; `git diff C2 C3 --stat` proves it; SHA/tree reported in channel W2.md + W2-requests.md; REVIEW-APPROVED names repo + commit before any push) |
| successor commit C4 | C3 + benchmark-CLI contract repair only (A56/A58/A60/A61; `git diff C3 C4 --stat` proves it; SHA/tree reported in channel W2.md + W2-requests.md; REVIEW-APPROVED names repo + commit before any push) |

C1's parent is remote-old: push fast-forwards, preserving existing
remote work. No history rewritten, no force. Local commits only (gate).

## Candidate family

C2-10M freeze-v2 qualified release, SHIP 2026-10-08 (READ10M 7/7 PASS),
store pin `ee06a4e4-83f7-4315-9e23-bd6e5034cccb:0:95436`, producer freeze
`c2-b100m-producer-freeze-002`, **89/89 entries + 44/44 closure verified**.
Channel provenance: `provenance/CANDIDATE.md` (READY) + `REPRO.md`,
`producer-recovery/` (85 code), `data-recovery/` (4 inputs),
`data-public-package/` (adopted bundle + notices, A47; verifier
corrected per A52 after the A50 alias/atomic fix).

## Source hashes (re-verified by packager before copy)

Serving (7): dossier `93871fb3…`, relquery `0fe79c50…`, relserve
`61b69a84…`, query (pre-176) `d7756e72…`, index `b8bc1390…`, generation
`92970939…`, prodstate `e7a4370c…` (full: `c10m/README.md`).
Policy: CRITERIA `e7d0139a…`, requirements `cf63c41a…`, anchors
`9728129b…`; budgets M80-P100-A40. Producer: 85/85 byte-exact
(+ `fuse.py` `53cdd338…`); full table `c10m/PINS.sha256` (110 entries,
105→106→110 as data/bundle landed; `sha256sum -c` 110/110 OK).
Data: small inputs `e56ac0a9…`/`c255a52f…`/`fef3ec6a…`, derivation
`1343550c…`, preflight `6bddf685…`, curated `210a20a4…`; corpora
`c098fdac…` (622471790 B) + `04bbbb3e…` (64291035 B); bundle
`31002b8c…` (21787645 B, deterministic `gzip -n -9`, re-run identical).
Harness: wheel `3c11d3ed…` (440383 B), adapters `0f6e7bc3…`/`07606fea…`/
`0ceb3670…`/`06b279cd…` (lane-final 162-fix S1; staging record's
pre-fix `dfa113b8…` preserved verbatim, not shipped as code),
upstream-links `e5fb424a…`. Receipts: ship-record `c092ff7b…`/
`2518a520…`/`a8b00b0b…`/`64c0b8e0…`; scale10m `679575e4…`/`c08b2b77…`/
`5222b2e5…` (48 MB by hash record); _186 verdict `febc3010…` (214953 B),
pins file `6ae0df4b…` (17/17 OK at source); eval `77336d62…`/`ece682c7…`.
Big RUN.json/TREC set: 20 files hash-inventoried
(`benchmarks/evidence/ARTIFACT-INVENTORY.md`), smoke lane bundled whole.

## Verification commands + exits (observed 2026-10-14; full: TEST-REPORT.md)

```text
(cd c10m && sha256sum -c PINS.sha256)                          rc=0  110/110 OK
python demos/demo_c10m_narrow.py --quiet                       rc=0  DEMO PASS 0.83s offline
python c10m/data/reconstruct_inputs.py --out-dir … --from-bundle rc=0 RECONSTRUCT PASS (via corrected verifier; cmp byte-identical)
python c10m/data/reconstruct_inputs.py --out-dir … --scifact … --delta … rc=0 RECONSTRUCT PASS (both corpora exact; C2 run, path untouched by C3)
python c10m/data/bundle/verify_docs_10m.py --out …             rc=0  VERIFY PASS (corrected A52 verifier)
python c10m/data/bundle/verify_docs_10m.py --self-test         rc=0  SELF-TEST 7/7 (C3 focused; + 5/5 disposable-copy negatives, see TEST-REPORT.md)
python benchmarks/evidence/repro-fixture/verify_smoke_receipts.py rc=0 SMOKE-VERIFY PASS
pytest tests/test_c10m_demo.py tests/test_w2_demo_smoke.py -q  rc=0  7 passed
pytest tests/test_organization_toc.py -q -k "grace_period or 30_day" rc=0 3 passed
pytest tests/test_100k_qualification_scaffold.py -q            rc=0  17 passed
pytest tests/ -q -p no:cacheprovider -rf                       rc=1  6 failed / 503 passed / 3 xpassed (672s):
   4x test_p4_ballot_pack — PRE-EXISTING (commit a9b4d3b… absent from clone history; fails identically at base)
   2x scaffold — TRANSIENT (run during experimental db removal; 17/17 green after restore; converges to 4/507)
python benchmarks/evidence/live/run_live_lane.py --dataset smoke rc=0  LIVE-LANE PASS (C4; real pinned encoder: smoke row EXACT, 7/7 serving shas self-authenticated)
python benchmarks/evidence/live/run_live_lane.py --dataset curated rc=0 LIVE-LANE PASS (C4; curated row EXACT, 0 failures)
python …/adapters/stage_pinned.py --manifest … --cache …      rc=0  STAGE-PINNED: DONE (C4; 8 files verified, round-trip identical)
python benchmarks/evidence/live/prepare_emb_cache.py (tiny fixture) rc=0 EMB-CACHE PARTIAL + STRICT-SERVE OK (C4; control flow only, no 10M run)
```

Install: `uv sync` + `uv lock` + `uv sync --extra c10m --extra test`
rc=0 (numpy 2.5.1, blake3 0.4.1, pytest 9.1.1). Secret scan: CLEAN
(SECRET-SCAN.md; larger files + wheel + db strings incl.).

## Diff summary (remote-old → C1)

208 files changed, +113654/−160. 203 added, 5 modified, 0 deleted.

Modified (5): `README.md` (C2-10M lead; legacy separate),
`docs/BENCHMARKS.md` (legacy-scope banner), `pyproject.toml` (`c10m`
extra), `tests/test_organization_toc.py` (frozen clock, test-only),
`uv.lock` (resolved extras).
Deleted (0): `scale_100k.db*` was experimentally removed, then
RESTORED to HEAD bytes — live dependency of the legacy runner default
path + 2 scaffold tests (removal flipped them red, restore green);
sensitive tables empty, strings scan 0 hits, provenance in co-shipped
packet → ruling: needed + not shown private → kept. Hashes:
db `2465f0cf…` (6467584 B), shm `75f25efb…` (32768 B), wal `7124c4fb…`
(20656 B).

C2 → C3 (successor, A50–A53): 6 files modified, 0 added/deleted —
verifier adoption only. `c10m/data/bundle/verify_docs_10m.py`
replaced byte-exact with the corrected package script (`20bfbbf9…`);
`c10m/data/reconstruct_inputs.py` `--from-bundle` delegates to it
(unsafe inline `gzip` copy removed); `c10m/PINS.sha256` repinned (3
entries); `c10m/data/DATA-README.md`, `TEST-REPORT.md`, `MANIFEST.md`
updated. Asset `docs-10m.jsonl.gz` byte-unchanged (`31002b8c…`,
21787645 B).

C3 → C4 (successor, A56/A58/A60/A61): 6 files added, 12 modified,
0 deleted — benchmark-CLI contract repair (B1–B8) + audit F2/F3 doc
accuracy only. Added: `benchmarks/evidence/live/` wrappers/config
(`assemble_runtime.py`, `fetch_weights.py`, `run_live_lane.py`,
`prepare_emb_cache.py`, `README.md`, `STORE-BUILD.md` — outside
pinned sources). Modified: `docs/C2-10M-REPRO-APPENDIX.md` (§0 pins
form + §2 extraction note + §4 live rewrite),
`benchmarks/evidence/repro-fixture/README.md` (Layer 2 rewrite),
`benchmarks/evidence/harness/README.md` (protocol + binding),
`benchmarks/evidence/pins/PINS.md` (tested install),
`benchmarks/evidence/CANDIDATE-PINS.md` (F2: 105→110),
`docs/C2-10M-PUBLICATION.md` (F2: 105→110), `c10m/README.md` (F2/B8
pins form; repinned), `c10m/data/DATA-README.md` (§7 recipe pointer;
repinned), `c10m/PINS.sha256` (2 doc entries repinned),
`SECRET-SCAN.md` (F3 db wording), `TEST-REPORT.md` (C4 §),
`MANIFEST.md` (this file). Zero frozen-byte changes: all 89
producer/serving entries, the wheel, and the 4 adapters verify
identical to C3.

## Shipped files (203 added)

- `.gitattributes`
- `SECRET-SCAN.md`
- `TEST-REPORT.md`
- `W2B-LEASE.md`
- `W2C-LEASE.md`
- `assets/hero/README.md`
- `assets/hero/placeholder.svg`
- `benchmarks/evidence/ARTIFACT-INVENTORY.md`
- `benchmarks/evidence/CANDIDATE-PINS.md`
- `benchmarks/evidence/README.md`
- `benchmarks/evidence/harness/README.md`
- `benchmarks/evidence/harness/adapters/c2_bench10m.py`
- `benchmarks/evidence/harness/adapters/c2_rekey.py`
- `benchmarks/evidence/harness/adapters/c2_store_probe.py`
- `benchmarks/evidence/harness/adapters/stage_pinned.py`
- `benchmarks/evidence/harness/vendor/SHA256SUMS`
- `benchmarks/evidence/harness/vendor/trace_bench-0.3.0-py3-none-any.whl`
- `benchmarks/evidence/harness/vendor/upstream-links.json`
- `benchmarks/evidence/pins/PINS.md`
- `benchmarks/evidence/provenance/CONFIG.md`
- `benchmarks/evidence/provenance/CONFIRM-INPUTS.v3-10m.json`
- `benchmarks/evidence/provenance/DATASETS.md`
- `benchmarks/evidence/provenance/queries-10m.json`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/REPORT.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/SCOPE.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/adoption-162.log`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/c2-bench10m-source-record.json`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/curated/compare-shipped-vs-bm25.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/curated/compare-shipped-vs-dense.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/curated/compare-shipped-vs-k100.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/nfcorpus.log`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/nfcorpus/compare-shipped-vs-bm25.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/nfcorpus/compare-shipped-vs-dense.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/nfcorpus/compare-shipped-vs-k100.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/pony-162.log`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/pony-collision-162.log`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/pony/compare-shipped-vs-bm25.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/pony/compare-shipped-vs-dense.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/pony/compare-shipped-vs-k100.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/run-nfcorpus.sh`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/scifact/compare-shipped-vs-bm25.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/scifact/compare-shipped-vs-dense.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/scifact/compare-shipped-vs-k100.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/smoke-a1/compare-shipped-vs-bm25.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/smoke-a1/run_20261008_182558_693806.0_bm25.trec`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/smoke-a1/run_20261008_182558_693806.1_python_c2_bench10m_C2Bench10MShipped.trec`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/smoke-a1/run_20261008_182558_693806.json`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/snapshot-before-mutation.md`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/store-probe-162.json`
- `benchmarks/evidence/receipts-10m-shipped/lane-BENCH10M/store-probe.json`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/BUILD-REPORT.md`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/COMMANDS.md`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/PHASE2-REPORT.md`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/corpus_check.json`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/corpus_check.py`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/driver_10m.py`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/metrics.json`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/phase1.json`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/queries.log`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/rows.jsonl`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/tok_wp_prefix.json`
- `benchmarks/evidence/receipts-10m-shipped/scale10m/tok_wp_prefix.py`
- `benchmarks/evidence/receipts-10m-shipped/ship-record/BUILD-RECEIPT.json`
- `benchmarks/evidence/receipts-10m-shipped/ship-record/C2-10M-UPLOAD.json`
- `benchmarks/evidence/receipts-10m-shipped/ship-record/READ10M-REPORT.md`
- `benchmarks/evidence/receipts-10m-shipped/ship-record/c2-10m-SHIPPED.md`
- `benchmarks/evidence/receipts-186/DISTURBANCES-ARCHITECT-SIDE.md`
- `benchmarks/evidence/receipts-186/NEGATIVE-RESULTS.md`
- `benchmarks/evidence/receipts-186/RESULT-10M-186.md`
- `benchmarks/evidence/receipts-186/RULINGS-186-ADDENDUM-1.md`
- `benchmarks/evidence/receipts-186/RULINGS-186.md`
- `benchmarks/evidence/receipts-186/WINDOW-RELEASED-186.md`
- `benchmarks/evidence/receipts-186/pins-186.sha256`
- `benchmarks/evidence/receipts-186/release-sha256.txt`
- `benchmarks/evidence/receipts-186/verdict-7b40af139e59488c8b2ebf195a132d48-20261011T022927.150701Z.json`
- `benchmarks/evidence/repro-fixture/README.md`
- `benchmarks/evidence/repro-fixture/verify_smoke_receipts.py`
- `c10m/PINS.sha256`
- `c10m/README.md`
- `c10m/data/DATA-README.md`
- `c10m/data/bundle/ATTRIBUTION.md`
- `c10m/data/bundle/LICENSE-DATA.md`
- `c10m/data/bundle/docs-10m.jsonl.gz`
- `c10m/data/bundle/provenance.json`
- `c10m/data/bundle/verify_docs_10m.py`
- `c10m/data/inputs/INPUTS-REPORT.md`
- `c10m/data/inputs/corpus-manifest-10m.json`
- `c10m/data/inputs/derivation.json`
- `c10m/data/inputs/prefix-doc-ranges.json`
- `c10m/data/inputs/preflight-100m.json`
- `c10m/data/inputs/relations-10m.json`
- `c10m/data/reconstruct_inputs.py`
- `c10m/data/upstream/trace_engineering_curated.json`
- `c10m/policy/CRITERIA.v3.json`
- `c10m/policy/relations-10m.anchors-v1.json`
- `c10m/policy/requirements.v4.json`
- `c10m/producer/coordination/c2-work-20261006T1925Z/lane-G/counters.py`
- `c10m/producer/coordination/c2-work-20261006T1925Z/lane-G/profile.py`
- `c10m/producer/inputs/anchors-derivation.json`
- `c10m/producer/inputs/c2-profile-100m.json`
- `c10m/producer/inputs/relations-10m.anchors-v1.json`
- `c10m/producer/lane-RELAUNCH/b100m_build_c2.py`
- `c10m/producer/lane-RELAUNCH/b100m_build_ref.py`
- `c10m/producer/lane-RELAUNCH/b100m_diff10m.py`
- `c10m/producer/lane-RELAUNCH/b100m_freeze.py`
- `c10m/producer/lane-RELAUNCH/b100m_preflight.py`
- `c10m/producer/lane-RELAUNCH/b100m_rekey.py`
- `c10m/producer/tl-candidate-batch/candidate/approval.py`
- `c10m/producer/tl-candidate-batch/candidate/committer.py`
- `c10m/producer/tl-candidate-batch/candidate/common.py`
- `c10m/producer/tl-candidate-batch/candidate/excommon.py`
- `c10m/producer/tl-candidate-batch/candidate/executor.py`
- `c10m/producer/tl-candidate-batch/candidate/intake.py`
- `c10m/producer/tl-candidate-batch/candidate/pintable.py`
- `c10m/producer/tl-candidate-batch/candidate/preflight.py`
- `c10m/producer/tl-candidate-batch/candidate/recovery.py`
- `c10m/producer/tl-candidate-batch/candidate/replay.py`
- `c10m/producer/tl-candidate-batch/candidate/stage_b_common.py`
- `c10m/producer/tl-candidate-batch/candidate/stage_c_common.py`
- `c10m/producer/tl-candidate-batch/candidate/store.py`
- `c10m/producer/tl-candidate-batch/candidate/w6.py`
- `c10m/producer/tl-candidate-batch/candidate/w7.py`
- `c10m/producer/tl-candidate-batch/candidate/w8.py`
- `c10m/producer/tl-candidate-batch/candidate/w9.py`
- `c10m/producer/tl-eval/gate_runner/gate_lib.py`
- `c10m/producer/tl-eval/gate_runner/run_integrated_gate.py`
- `c10m/producer/tl-eval/gpu_encode/__init__.py`
- `c10m/producer/tl-eval/gpu_encode/cache.py`
- `c10m/producer/tl-eval/gpu_encode/chunking.py`
- `c10m/producer/tl-eval/gpu_encode/config.py`
- `c10m/producer/tl-eval/gpu_encode/consume.py`
- `c10m/producer/tl-sys/tests/test_c2_p2_keyed_ops.py`
- `c10m/producer/tl-sys/tests/test_c2_p3_birth.py`
- `c10m/producer/tl-sys/tests/test_c2_p_routing.py`
- `c10m/producer/tl-sys/tests/test_c2_p_sidecar.py`
- `c10m/producer/tl-sys/tlsys/__init__.py`
- `c10m/producer/tl-sys/tlsys/catalog.py`
- `c10m/producer/tl-sys/tlsys/dossier.py`
- `c10m/producer/tl-sys/tlsys/export.py`
- `c10m/producer/tl-sys/tlsys/fuse.py`
- `c10m/producer/tl-sys/tlsys/hierserve.py`
- `c10m/producer/tl-sys/tlsys/hnsw_candidates.py`
- `c10m/producer/tl-sys/tlsys/identity.py`
- `c10m/producer/tl-sys/tlsys/index.py`
- `c10m/producer/tl-sys/tlsys/ingest.py`
- `c10m/producer/tl-sys/tlsys/lifecycle.py`
- `c10m/producer/tl-sys/tlsys/maint.py`
- `c10m/producer/tl-sys/tlsys/place.py`
- `c10m/producer/tl-sys/tlsys/prodstate.py`
- `c10m/producer/tl-sys/tlsys/proj.py`
- `c10m/producer/tl-sys/tlsys/query.py`
- `c10m/producer/tl-sys/tlsys/relations.py`
- `c10m/producer/tl-sys/tlsys/relquery.py`
- `c10m/producer/tl-sys/tlsys/relserve.py`
- `c10m/producer/tl-sys/tlsys/serving/__init__.py`
- `c10m/producer/tl-sys/tlsys/serving/checkpoints.py`
- `c10m/producer/tl-sys/tlsys/serving/compact.py`
- `c10m/producer/tl-sys/tlsys/serving/counters.py`
- `c10m/producer/tl-sys/tlsys/serving/delta.py`
- `c10m/producer/tl-sys/tlsys/serving/dense.py`
- `c10m/producer/tl-sys/tlsys/serving/digest.py`
- `c10m/producer/tl-sys/tlsys/serving/faults.py`
- `c10m/producer/tl-sys/tlsys/serving/generation.py`
- `c10m/producer/tl-sys/tlsys/serving/lexical.py`
- `c10m/producer/tl-sys/tlsys/serving/manifest.py`
- `c10m/producer/tl-sys/tlsys/serving/provisional.py`
- `c10m/producer/tl-sys/tlsys/serving/segments.py`
- `c10m/producer/tl-sys/tlsys/serving/tests/__init__.py`
- `c10m/producer/tl-sys/tlsys/serving/tests/fixture.py`
- `c10m/producer/tl-sys/tlsys/serving/tests/test_serving_compact.py`
- `c10m/producer/tl-sys/tlsys/serving/tests/test_serving_counters_profile.py`
- `c10m/producer/tl-sys/tlsys/serving/tests/test_serving_digest_d3.py`
- `c10m/producer/tl-sys/tlsys/serving/tests/test_serving_facade_d1.py`
- `c10m/producer/tl-sys/tlsys/serving/tests/test_serving_faults_fi.py`
- `c10m/producer/tl-sys/tlsys/serving/tests/test_serving_parity_seeds.py`
- `c10m/producer/tl-sys/tlsys/serving/tests/test_serving_pool.py`
- `c10m/producer/tl-sys/tlsys/serving/tests/test_serving_repair.py`
- `c10m/producer/tl-sys/tlsys/serving/tombstones.py`
- `c10m/producer/tl-sys/tlsys/serving/view.py`
- `c10m/producer/tl-sys/tlsys/store_if.py`
- `c10m/producer/tl-sys/tlsys/validate_export.py`
- `c10m/serving/tl-sys/tlsys/dossier.py`
- `c10m/serving/tl-sys/tlsys/index.py`
- `c10m/serving/tl-sys/tlsys/prodstate.py`
- `c10m/serving/tl-sys/tlsys/query.py`
- `c10m/serving/tl-sys/tlsys/relquery.py`
- `c10m/serving/tl-sys/tlsys/relserve.py`
- `c10m/serving/tl-sys/tlsys/serving/generation.py`
- `demos/README.md`
- `demos/c10m_inspector.html`
- `demos/c10m_tutorial.md`
- `demos/demo_c10m_narrow.py`
- `demos/demo_phase1_api.py`
- `demos/fixtures/c10m_synth_docs.jsonl`
- `demos/fixtures/demo_docs.jsonl`
- `docs/ACCESSIBILITY.md`
- `docs/C2-10M-PUBLICATION.md`
- `docs/C2-10M-REPRO-APPENDIX.md`
- `docs/RELEASE-SUMMARY.md`
- `docs/figures/c10m-attach-cost.svg`
- `docs/figures/c10m-lanes-ndcg.svg`
- `tests/test_c10m_demo.py`
- `tests/test_w2_demo_smoke.py`
