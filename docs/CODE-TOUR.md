<!-- SPDX-License-Identifier: Apache-2.0 -->
# Code tour — the frozen 207-file candidate

Every path below is inside the exact qualified snapshot. **Do not edit
anything under `freeze-src/`**: `python3 tools/verify_freeze.py` must keep
printing `entries=207 ok=207 missing=0 mismatch=0`. New code goes in
wrappers outside the freeze (`tools/`, `demo/`, `demo-app/`).

## Entry points

| Path | Role |
|---|---|
| [freeze-src/cand/tools/product_pilot.py](../freeze-src/cand/tools/product_pilot.py) | The qualification pilot: ingest → organize/drain → bounded repair → fault injection + SIGKILL restore → repair-to-zero → guided/flat evaluation. Harness pin `9f516288…b8d9b1a0` in [receipts/source-pin.json](../receipts/source-pin.json). |
| [freeze-src/cand/tools/drain_instrument.py](../freeze-src/cand/tools/drain_instrument.py) | Per-cycle drain instrumentation (stack Fix 1+3) feeding the drain-cycle record. |
| [freeze-src/cand/tools/real_prefix.py](../freeze-src/cand/tools/real_prefix.py) · [vm_driver.py](../freeze-src/cand/tools/vm_driver.py) · [child_crash_drain.py](../freeze-src/cand/tools/child_crash_drain.py) · [preserve_deletes.py](../freeze-src/cand/tools/preserve_deletes.py) | Corpus-prefix preparation, VM driving, crash-drain child, and delete preservation used by the pilot. |
| [freeze-src/run_all.sh](../freeze-src/run_all.sh) · [freeze-src/cand/runtime.sh](../freeze-src/cand/runtime.sh) | Local synthetic/unit test runner (`stack|fix1|existing|all`) and its runtime environment (`SUP_PYTHON`, `PYTHONPATH`). |
| [freeze-src/BUILD-REPORT.md](../freeze-src/BUILD-REPORT.md) · [freeze-src/cand/stack/CHANGED-SET.md](../freeze-src/cand/stack/CHANGED-SET.md) | How the 5-fix stack was built on the 205-file speed parent, file by file. |

## Store and serving (`freeze-src/cand/fork/tl-sys/tlsys/`)

| Module | Role |
|---|---|
| [ingest.py](../freeze-src/cand/fork/tl-sys/tlsys/ingest.py) · [index.py](../freeze-src/cand/fork/tl-sys/tlsys/index.py) · [catalog.py](../freeze-src/cand/fork/tl-sys/tlsys/catalog.py) | Document intake, atom indexing, and the catalog the organizer drains. |
| [org_service.py](../freeze-src/cand/fork/tl-sys/tlsys/org_service.py) · [org_publication.py](../freeze-src/cand/fork/tl-sys/tlsys/org_publication.py) | Self-organization service and publication (stack Fix 6: sort bound tie + default on, latency-only). |
| [place.py](../freeze-src/cand/fork/tl-sys/tlsys/place.py) · [proj.py](../freeze-src/cand/fork/tl-sys/tlsys/proj.py) · [identity.py](../freeze-src/cand/fork/tl-sys/tlsys/identity.py) | Atom placement into the two-level hierarchy, projection, and stable identity. |
| [query.py](../freeze-src/cand/fork/tl-sys/tlsys/query.py) · [hierserve.py](../freeze-src/cand/fork/tl-sys/tlsys/hierserve.py) · [hnsw_candidates.py](../freeze-src/cand/fork/tl-sys/tlsys/hnsw_candidates.py) · [fuse.py](../freeze-src/cand/fork/tl-sys/tlsys/fuse.py) | Guided (hierarchy-routed) and flat query paths, candidate generation, and fusion. These produce the matched-work recall rows in [BENCHMARKS.md](BENCHMARKS.md). |
| [relserve.py](../freeze-src/cand/fork/tl-sys/tlsys/relserve.py) · [relquery.py](../freeze-src/cand/fork/tl-sys/tlsys/relquery.py) · [relations.py](../freeze-src/cand/fork/tl-sys/tlsys/relations.py) | Relation serving and querying over organized atoms. |
| [serving/generation.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/generation.py) · [serving/view.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/view.py) · [serving/gen_gc.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/gen_gc.py) | Generation lifecycle, ViewPool build/verify/swap (Fix 2), suffix-verify + GC hook (Fix 2+5), newest-K pinned-skip collection (Fix 5). Correct and unit-proven, dormant on the org-pilot path — see [ARCHITECTURE.md](ARCHITECTURE.md). |
| [serving/manifest.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/manifest.py) · [serving/digest.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/digest.py) · [serving/segments.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/segments.py) · [serving/compact.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/compact.py) · [serving/delta.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/delta.py) | Serving-store manifest, digests, segments, compaction, and deltas under the derived ledger caps. |
| [serving/dense.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/dense.py) · [serving/lexical.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/lexical.py) · [serving/provisional.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/provisional.py) · [serving/checkpoints.py](../freeze-src/cand/fork/tl-sys/tlsys/serving/checkpoints.py) | Dense and lexical access, provisional state, and checkpoints. |
| [local_repair.py](../freeze-src/cand/fork/tl-sys/tlsys/local_repair.py) · [repair_hook.py](../freeze-src/cand/fork/tl-sys/tlsys/repair_hook.py) · [repair_metrics.py](../freeze-src/cand/fork/tl-sys/tlsys/repair_metrics.py) · [maint.py](../freeze-src/cand/fork/tl-sys/tlsys/maint.py) · [lifecycle.py](../freeze-src/cand/fork/tl-sys/tlsys/lifecycle.py) | Bounded repair (the recorded `repair_to_zero` cost is a headline negative finding) and maintenance/lifecycle. |
| [dossier.py](../freeze-src/cand/fork/tl-sys/tlsys/dossier.py) · [export.py](../freeze-src/cand/fork/tl-sys/tlsys/export.py) · [validate_export.py](../freeze-src/cand/fork/tl-sys/tlsys/validate_export.py) · [store_if.py](../freeze-src/cand/fork/tl-sys/tlsys/store_if.py) · [prodstate.py](../freeze-src/cand/fork/tl-sys/tlsys/prodstate.py) | Evidence dossiers, validated export, the store interface, and production state. |

## Candidate batch (`freeze-src/cand/fork/tl-candidate-batch/candidate/`)

[committer.py](../freeze-src/cand/fork/tl-candidate-batch/candidate/committer.py),
[intake.py](../freeze-src/cand/fork/tl-candidate-batch/candidate/intake.py),
[approval.py](../freeze-src/cand/fork/tl-candidate-batch/candidate/approval.py),
[executor.py](../freeze-src/cand/fork/tl-candidate-batch/candidate/executor.py),
[preflight.py](../freeze-src/cand/fork/tl-candidate-batch/candidate/preflight.py),
[recovery.py](../freeze-src/cand/fork/tl-candidate-batch/candidate/recovery.py),
[replay.py](../freeze-src/cand/fork/tl-candidate-batch/candidate/replay.py),
[store.py](../freeze-src/cand/fork/tl-candidate-batch/candidate/store.py),
[pintable.py](../freeze-src/cand/fork/tl-candidate-batch/candidate/pintable.py):
batched candidate intake, commit, approval, crash recovery and replay —
the durability behaviour exercised by the pilot's kill/restart phase.

## Tests shipped in the freeze

- [freeze-src/cand/stack/tests/](../freeze-src/cand/stack/CHANGED-SET.md) —
  stack changed-set tests (default-path identity, Fix-2 suffix, Fix-3 knob,
  Fix-5 GC, Fix-6 parity).
- [freeze-src/cand/fix1/](../freeze-src/cand/fix1/canary.py) — Fix-1 overlay
  reference and its falsifier/schema/self-validation tests.
- [freeze-src/cand/tests/](../freeze-src/cand/tests/test_publication.py) —
  pilot-level suites (publication, pending top-k, pool reuse, repair,
  crash idempotency, harness caps, supervisor acceptance, shared prefetch).
- `freeze-src/cand/fork/tl-sys/tests/` and
  `freeze-src/cand/tests/upstream/` — store/serving unit suites. Names
  containing `c2` in these frozen test files are internal implementation
  names of this exact snapshot; they stay byte-exact.

## Outside the freeze (maintained wrappers)

| Path | Role |
|---|---|
| [tools/verify_freeze.py](../tools/verify_freeze.py) | Rehash all 207 frozen files against `SOURCEFREEZE.json`. |
| [tools/check_receipts.py](../tools/check_receipts.py) | Validate staged receipt JSON shape and the recorded gate values quoted in the docs. |
| [tools/check_links.py](../tools/check_links.py) | Check relative Markdown links in the maintained docs resolve. |
| [demo/synthetic_recall.py](../demo/synthetic_recall.py) | Illustrative synthetic guided-vs-flat shape demo; not a benchmark. |
| [receipts/](../receipts/result.json) | Staged VM records, verbatim; the only source for benchmark numbers. |
