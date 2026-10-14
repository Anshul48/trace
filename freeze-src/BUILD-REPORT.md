# Stack fork BUILD REPORT — fix-1+2+3+5 (+fix-6) on the speed candidate

Builder: Muse (subagent). Date: 2026-10-12/13 UTC. Method: fresh-dir +
overlay (fix-1 VM precedent); freeze-with-parent. All writes under
`/tmp/stack-fork/`; `/home` read-only; no VM contact; synthetic/unit
tests only (no corpus locally; nothing ≥50k tokens run here).

## Base pins (verified)

- Speed candidate: `sup/runs/20261012T144657Z/speed-candidate/`
- `SOURCEFREEZE.json` (parent): `dd543d0e2a12c82539bc9381c0fa76f3dd8f713e2138b7690da32de2b8be604b`
  (schema `sup-speed-candidate-v1`, 205 files; copy at
  `/tmp/stack-fork/SOURCEFREEZE.speed-parent.json`, sha identical).
- `BASELINE-SOURCEFREEZE.json`: `9cdbc2a48d0ffb84d53c8a3f25012cd352cde7eaf340296441a3ce13ddc55d78`
- Base `tools/product_pilot.py`: `b25195ba41f7fea01c12f8d0e1d6e4cf8d07af3c1c39e0a31ae189e32bd16df7`
  (matches the VM fix-1 report's pre-diff base pin).

## Stack freeze (new)

- `cand/SOURCEFREEZE.json`: `38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54`
- Schema `sup-speed-candidate-v1+fix12356-stack`, 207 entries, drift `[]`,
  `parent_speed_freeze_sha256` = parent above.
- Rule (fix-1 precedent): frozen = runtime-closure files only; `fix1/` +
  `stack/` sidecars ride unfrozen.

## Changed-set (5 modified + 2 added; details in `cand/stack/CHANGED-SET.md`)

| File | Fix | Diff vs speed | Stack sha (short) |
|---|---|---|---|
| `tools/product_pilot.py` | 1+3 | 84 lines (fix-1 38 + fix-3 46) | `9f516288…` |
| `tools/drain_instrument.py` | 1+3 | NEW 323 lines (fix-1 285 + fix-3 44) | `636be48a…` |
| `fork/tl-sys/tlsys/org_publication.py` | 6 | 16 lines (tie bound + default ON) | `a0fdddc2…` |
| `fork/tl-sys/tlsys/serving/generation.py` | 2+5 | 177 lines (suffix verify + GC hook) | `53130f41…` |
| `fork/tl-sys/tlsys/serving/view.py` | 2 | 123 lines (lock split + orphan + flags + GC wire) | `903f1fd7…` |
| `fork/tl-sys/tlsys/serving/gen_gc.py` | 5 | NEW 98 lines | `e3dccd4f…` |
| `tests/test_publication.py` | meta | 10 lines (FlagOffIdentity set adaptation) | `9cb67027…` |

Fix-1 overlay applied as-is first (shas matched VM pins `6bc6b387…` /
`107f64c6…` before stacking fix-3 on top); `fix1/` sidecar byte-identical
to `/tmp/fix1stage/up/`. Unfrozen sidecars: `fix1/`, `stack/`.

## What each fix does in the stack

- **Fix-1**: VM overlay unchanged in behavior; `run_drain_loop` gained
  `max_documents=4096, budget_seconds=60` params (defaults = old literals).
- **Fix-2** (contract serving layer): `verify_suffix_against_source`
  (prefix O(ranges) chain check + O(suffix) proof + O(retired) tombstone
  union sub-span; global op-hash identical to from-zero); `verify_against_source`
  falls back to FULL receipted on any chain break; `ViewPool.publish_generation`
  splits build(locked)/verify(unlocked)/swap(locked+recheck) with the
  no-progress orphan rule; periodic full every Kth (K=`retained_generations_K`);
  fresh-pool/quarantine/cold-fallback first publish always full; own-tmpdir
  cleanup on orphan/exception. Rebase path unchanged (private pool, full).
- **Fix-3**: `--drain-budget-s` (default 60 = current; env
  `PILOT_DRAIN_BUDGET_S`; fail-closed) threaded through `drain_all` only;
  probe drains stay literal 60; `--drain-unbatched` enables contract arm A
  (default batched); `result['drain_all_budget_s'/'drain_mode']` receipted;
  `derive_budget_candidate`/`derive_budget_from_cycles_file` implement
  `ceil(2×max_measured_wall)` (965 from 482.006 verified).
- **Fix-5**: `gen_gc.collect` (newest-K + pinned-skip + broken-immunity +
  noop/over-cap receipts) runs inside `publish_generation` strictly after
  the pointer write when `gc_keep` is set; `ViewPool` passes pool K + live
  pins; rebase path (`None`) has zero GC keys. `release()` untouched
  (retire-when-unpinned is automatic at the next pass).
- **Fix-6**: partition sort default ON (`__init__` + `pending_search`
  fallback); tie-degenerate bound via `heapq.nsmallest` (adopted from the
  prior fix-6 fork, parity-proven); `fast=False` branch byte-identical.

## Test results (all local synthetic/unit; `bash /tmp/stack-fork/run_all.sh`)

- **stack/ 6/6 PASS**: changed-set (5+2+0, drift [], markers, AST),
  default-path identity (OFF/60/batched/4096/60, sort-OFF==literal 60/60),
  fix-3 (resolve/flag>env, fail-closed 6/6, derive 965/163, forwarding),
  fix-6 (ON==literal 324/324 + NaN/Inf/-0/k==n + search-level parity),
  fix-2 (chain F/S/S/F/S; independent from-zero re-verify 7/7 incl.
  op-hash+tombstones; suffix scanned strictly fewer rows; straddle +
  quarantine fallback/selected fulls; orphan ×2 with no swap + tmpdir
  clean; K=1 always-full), fix-5 (units: window/pinned/broken/noop/
  over-cap/determinism/idempotence; integration: 6-pub chain,
  straggler survived then collected, retained≤K).
- **fix1/ 4/4 PASS** on the stack (identity-OFF, schema 3 records,
  selfvalidation exit 0 VALID = 12-doc canary shape, falsifier NO-GO).
- **Existing targeted**: `test_pending_topk` 2/2, `test_publication`
  15/15, `test_pool_reuse` 22/22, `test_serving_pool` PASS.
- **Broader `tests/`**: 150/150 (excl. two vendored upstream dirs whose
  collection error is identical on the pristine base — pre-existing
  stdlib-`profile` shadowing).
- **Serving modules**: compact/digest/faults/pool PASS; counters/facade/
  repair FAIL identically on the pristine base (pre-existing, same test
  names); parity-seeds silent-within-budget on both trees (touches none
  of the changed paths; skipped with reason).
- **Negative controls**: adapted `FlagOffIdentity` FAILS on an
  undocumented-drift copy (guard live); fix-1 falsifier NO-GOs.
- **Secret scan**: clean (only tokenizer/BM25 prose matches).
- 12-doc canary shape: covered by fix1 selfvalidation (VALID, no corpus
  needed). No corpus-gated test was runnable locally; none attempted.

## Known gaps / findings (read before the treatment arm)

1. **Fix-2/5 engagement**: on the current org-pilot path, serving-layer
   `publish_generation`/`verify_against_source`/GC have no product callers
   (verified by call-graph: only `checkpoint_now`→checkpoint, which has no
   product callers, plus tests; `background_rebase` only fires for gen
   views, which require a pre-existing `generation/` dir). Fix-2/5 are
   correct and unit-proven but DORMANT on the pilot path; they engage
   wherever serving publishes occur. The treatment arm's per-cycle-slope
   movement at 500k→1M is expected from **fix-3** (live lever) + fix-6
   (latency-only). If markers implicate org-layer `verify_prepared`
   instead, the prior `work/forks/fix-2-suffix-verify` (opt-in org-layer
   suffix) is the candidate — deliberately NOT stacked (out of contract).
2. **Suffix alignment**: suffix engages iff a range boundary aligns at
   F_prev (sealed steady state); rebase-style never-sealed views always
   fall back to full (correct, receipted). Off-lock benefit applies to
   serving-pool publishes (M0 shrink); rebase uses a private pool.
3. **`FlagOffIdentity` adaptation**: the test's hardcoded changed-set is
   per-fork metadata (its own "Combined-fork adaptation" precedent); the
   stack fork extends it (`generation.py`→changed, `gen_gc.py`→added) with
   guard logic untouched and a passing negative control. Surfaced here as
   the required contract-change record. (Local-only test: reads
   `/mnt/c/…`, errors on VM for the base tree too — pre-existing.)
4. **Prior-fork divergences noted**: fix-3 reuses `--drain-budget-s` naming
   from `work/forks/fix-3-drain-knob`; fix-6 adopts that fork's tie bound
   AND flips the default ON (prior kept default OFF); fix-2 follows the
   contract (serving layer), not the prior fork (org layer).
5. **Strays (no deletions per rule)**: `/tmp/guard-check-stack/` (negative
   control copy), `/tmp/pytest-cache-stack-stray/`, `/tmp/stack-probe-fix25.py`
   (scratch probe; superseded by `stack/tests/`).

## VM handoff (for REQUEST-FOR-CLAUDE, not run here)

- Tarball `/tmp/stack-fork.tar.gz` unpacks to `stack-fork/`
  (`cand/` + parent freeze + `run_all.sh` + this report).
  Machine-readable pin: `/tmp/stack-fork.tar.gz.sha256` (beside the
  tarball; `sha256sum -c` verifiable).
- Pilot asserts the new freeze (`frozen source drift` otherwise).
- Arms on identical 500k prefix: control `--drain-budget-s 60` (default,
  batched) vs candidate `--drain-budget-s <derived>` (derive via
  `derive_budget_from_cycles_file` on the control's `drain-cycles.jsonl`,
  `--drain-instrument` on both) vs unbatched `--drain-unbatched` control.
  Compare per-cycle slopes + publication series + F1 cadence per §3.3–3.4.
