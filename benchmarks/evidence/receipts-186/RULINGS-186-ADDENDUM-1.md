# RULINGS-186 ADDENDUM 1 — architect (Claude Sonnet 5.5), 2026-10-10 ~07:30Z, under the owner's delegation ("u decide")

Supplements RULINGS-186.md; where they differ this wins. RULINGS-186.md is unchanged.

## A1 Overlap reference (resolves J33 UNKNOWN #2)
OVERLAP_MANIFEST = `/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace-architecture/coordination/c2-work-20261006T1925Z/lane-CONFFIT/evidence/fit-preencode-s10-manifest.json`
observed sha256 `acb76e5a469adda35bb3ddd6febdee6f724e316178b28424d69517acfeda677d`, 7584 bytes, mtime 2026-10-08 18:34, 32 edits, edit-id set == {e-10M-D{1..4}-{add,correction}-r0000..r0003} (checked 07:28Z). Fields: action, class, edit_id, hits, lookup_s, misses, model_s, n_chunks, qvec_s.
Architect approves the STABLE-FIELD gate: edit_id, class, action, n_chunks, hits, misses must match the new pre-encode manifest for all 32; the *_s fields are newly measured and are not compared. The file's sha256 must still equal the value above at gate time.

## A2 Ordering relaxation for (c) only
Pre-encode (c) writes only new files under RUN_ROOT, is untimed, and its driver diff was read by the architect (ROOT/RUN_ROOT parameterization, no-overwrite, atomic writes; measured path untouched). It may start BEFORE the codex1 audit finishes. Fire condition (1) of RULINGS-186 for (d) is unchanged: audit PASS (after the fix round) is still required before any chunk. If the audit requires changes to confirm_preencode_full_186.py or confirm_io_186.py that could affect the encode-cache bytes, the encode-cache is re-derived or re-justified before (d).

## A3 Scheduling parity (architect directive to the fix round)
RULINGS R4 (nice 19 / ionice idle) governs AGENT work only. The campaign (chunk runs) must use exactly the `_185` scheduling: `nice -n 10`, no `ionice`. Pre-encode may keep `nice -n 19 ionice -c3` (untimed).

## A4 Crash recovery (owner reports WSL dies from OOM at times)
The fix round must add a documented, tested recovery path: after a killed session without a ledger failure event, `RECOVER=1 START=K` verifies chunks < K against the ledger, renames chunk K's dir/log to `quarantine/<utc>/` (never deletes), appends a ledger event naming the quarantine, then proceeds. No chunk ever re-runs into an existing directory. Pre-encode: after a kill, rename `encode-cache` to quarantine and rerun (no partial resume).

## A5 B communication
Git over the private repo, no new channel. B pushes only `machine/b*` branches, only after the owner's explicit "push" to B (standing permission may be given once by the owner). A fetches and reads; B's STATUS.md and job REPORTs are the record. Architect pushes `ops/campaign-186` (never main, no force). No secrets in git; B needs none from A.
