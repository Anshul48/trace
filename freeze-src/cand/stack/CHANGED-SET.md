# Stack fork changed-set (vs speed freeze `dd543d0e…`)

Base: `sup/runs/20261012T144657Z/speed-candidate/`
(`SOURCEFREEZE.json` sha256 `dd543d0e2a12c82539bc9381c0fa76f3dd8f713e2138b7690da32de2b8be604b`,
schema `sup-speed-candidate-v1`, 205 files). Parent copy:
`/tmp/stack-fork/SOURCEFREEZE.speed-parent.json`.
Method: fresh-dir + overlay (fix-1 VM precedent); freeze-with-parent
(new freeze records `parent_speed_freeze_sha256`, drift `[]`).

## Frozen-file changes (new freeze: 207 entries)

Modified (5):

| File | Fix | Scope |
|---|---|---|
| `tools/product_pilot.py` | 1 + 3 | fix-1 overlay (5 hunks, VM pin `6bc6b387…`) + fix-3 `--drain-budget-s` / `--drain-unbatched` / `resolve_drain_budget` / `drain_all` budget threading / `service_config(batched_drain)` / `result['drain_all_budget_s'/'drain_mode']` |
| `fork/tl-sys/tlsys/org_publication.py` | 6 | `pending_order` cutoff-tie bound (`heapq.nsmallest`, +6/-2) + default `fast_pending_topk` False→True (`__init__` + `pending_search` fallback); `fast=False` branch byte-identical |
| `fork/tl-sys/tlsys/serving/generation.py` | 2 + 5 | fix-2 `verify_suffix_against_source` + `verify_against_source` suffix-attempt/fallback + additive `verify_mode`/`chain_ok` keys; fix-5 `publish_generation(..., gc_keep, gc_pinned)` post-pointer GC hook |
| `fork/tl-sys/tlsys/serving/view.py` | 2 | `ViewPool.publish_generation` lock split (build locked / verify unlocked / swap locked + recheck + orphan rule) + `_needs_full_verify`/`_suffix_streak` + quarantine/cold recovery flags + `gc_keep`/`gc_pinned` wiring |
| `tests/test_publication.py` | meta | `FlagOffIdentity` changed-set: `generation.py` joins `changed`, `gen_gc.py` joins `added` (same per-fork adaptation precedent as the existing "Combined-fork adaptation" comment; guard logic untouched) |

Added + frozen (2, runtime closure):

| File | Fix | Scope |
|---|---|---|
| `tools/drain_instrument.py` | 1 + 3 | fix-1 overlay (VM pin `107f64c6…`) + fix-3 `run_drain_loop(..., max_documents=4096, budget_seconds=60)` params + `derive_budget_candidate` / `derive_budget_from_cycles_file` (`ceil(2×max_measured_wall)`) |
| `fork/tl-sys/tlsys/serving/gen_gc.py` | 5 | NEW: `collect(serving_dir, keep, pinned)` + `eligible_generations` (contract-exact GC) |

## Unfrozen sidecars (NOT in freeze, fix-1 precedent)

- `fix1/canary.py`, `fix1/tests/` — fix-1 overlay as shipped to VM (byte-identical to `/tmp/fix1stage/up/`).
- `stack/CHANGED-SET.md` (this file), `stack/tests/` — stack changed-set doc + default-path identity tests.

Freeze rule: frozen = runtime-closure files only (what the pilot/serving
imports at runtime). Sidecar checks/canaries/docs ride unfrozen, exactly as
fix-1's `fix1/` rode unfrozen in the VM fix-1 freeze (206 = 205 + 1).

## Default-path identity (what OFF/default must preserve)

- Fix-1 OFF (no flag/env): no jsonl file; drain loop executes the base
  statements; reports/pins/atoms/commits identical (`fix1/tests/`).
- Fix-3 absent (no flag/env): budget 60, batched mode; `drain_all` calls
  `s.drain(max_documents=4096, budget_seconds=60)` exactly as before; probe
  drains keep literal 60; configured product value 60 unchanged
  (contract §3.1); `tlsys.org_service.ServiceConfig` source untouched.
- Fix-6: `fast=False` branch byte-identical full sort; default ON rows are
  exactly the full-sort rows (parity fuzz, incl. ties/NaN/Inf).
- Fix-2 full mode: legacy 5 verify keys byte-identical values (+2 additive);
  rebase path (no `prev_root`) behavior-identical; first/fresh-pool publish
  is always full; any chain break falls back to full, receipted.
- Fix-5: `gc_keep=None` (rebase path) = no GC keys at all; ≤K dirs =
  list-and-no-op; `gen-broken-*` never touched; pinned never deleted.

## Deliberately NOT changed

- `tools/{child_crash_drain,preserve_deletes,real_prefix,vm_driver}.py`,
  `check_repair_correction.py`, `runtime.sh`, all of
  `fork/tl-candidate-batch/`, `fork/tl-sys/tlsys/{org_service,proj,ingest,…}.py`
  except the files above: byte-identical to the speed freeze.
- `release()` (no I/O; retire-when-unpinned is automatic at next GC pass).
- `background_rebase_publish` (private pool: no lock split needed; full
  verify as before + additive keys).
- Cycle-record schema (`CYCLE_KEYS`/`PHASE_KEYS` unchanged).
- No product defaults, acceptance, F1, fault, SIGKILL, oracle, or reader
  semantics change. No new dependencies (stdlib `heapq`/`math` only).
