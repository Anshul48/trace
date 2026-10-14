# R-CRX03 Repair Handoff (TRACE-CAP-001, CAP-CRX03)

- **Lease:** `lease-cap-crx03-linux-20260904` (32400s / 9h, issued 2026-09-04)
- **Branch:** `cap-crx03-activation`
- **Base (unchanged, no rebase):** `45c359118991bb6670092baf36cee3f573fc6454` (`cap-crx02-consolidator`)
- **Old tip:** `824222eed180679727398401adc92d9cfed25358`
- **New tip:** `97caace9b199ee666329e6563aab632a72579432`
- **Worktree:** detached `/tmp/trace-wt/crx03` at old tip (verified via rev-parse,
  clean); venv under worktree with `UV_CACHE_DIR=/tmp/uv-cache-coord`; `.venv`
  deleted and worktree removed (`--force`) after commit. No merge, no rebase.

## Files changed (in repair commit 97caace)

1. `docs/program/inbox/cap-crx03/crash_recovery_post_swap.jsonl` (NEW, 2 lines):
   one JSON object per runtime crash run (`crash_post_swap`, `crash_mid_swap`).
   Driver `/tmp/crx03_crash_runs.py` (outside repo, rerunnable): rel1 → active,
   rel2 (distinct `rev-lex-2`/`rev-dense-2`) via
   `service.activate_projection(rel2, simulate_crash_stage=<stage>)` with fake
   external alias adapters (activate/restore surface, no `promote_alias`), so the
   service compensation path (`service.py:3693-3713`) is genuinely exercised.
2. `docs/program/inbox/cap-crx03/handoff.md` (1 line): base claim corrected
   `45c3591942fc692c8427fbf0cf339bf4b3ca4254` → dispatch
   `45c359118991bb6670092baf36cee3f573fc6454`. Verified: old value fails
   `git cat-file -e` (exit 1, object absent); dispatch value passes (exit 0).

No `src/` changes: the crash log proves the existing predecessor-restore
rollback (`store.py:4176-4195`) and alias compensation behave as designed.

## Crash-log evidence (both runs, from committed artifact)

| run | exception contains | rel1 | rel2 | journal | aliases post==pre | dangling | predecessor_restoration |
|---|---|---|---|---|---|---|---|
| crash_post_swap | `simulated crash at post_swap` (service-wrapped: `external index alias promotion or activation failed: ...`) | active | failed | rolled_back (`simulated crash at post_swap`) | lexical `rev-lex-1`, dense `rev-dense-1` match | 0 | true |
| crash_mid_swap | `simulated crash at mid_swap` (same wrapper) | active | failed | rolled_back (`simulated crash at mid_swap`) | lexical `rev-lex-1`, dense `rev-dense-1` match | 0 | true |

Acceptance properties: `predecessor_restoration == true` AND
`dangling_alias_count == 0` on both lines. Note: the raised `InvariantViolation`
text is the service-layer wrap of the store's exact `simulated crash at <stage>`
error (journal `error_detail` keeps the exact string); consistent with the
existing in-process test's `assertIn` semantics.

## Acceptance tests

`PYTHONPATH=src .venv/bin/pytest tests/v2/test_cortex_activation.py -v`
→ **9 passed in 1.45s** (9/9), observed in the detached worktree before commit.

## Handoff status

This note is intentionally left UNCOMMITTED in the parent checkout inbox.
Repair commit is on `cap-crx03-activation`; rebase onto `cap-job02-recovery`
happens at merge time per D3 (JOB02 merges first). No blockers.
