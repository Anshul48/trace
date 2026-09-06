# COORD Addendum 2026-09-03: Linux-session repair pattern + R-RET02 pin root cause

- **Session:** COORD resume (Muse coordinator, Linux mount session)
- **Prior blocker cleared in part:** this session CAN write the parent checkout
  (`/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace`) and `/tmp`,
  and the repo git storage is writable.
- **New constraint found:** `/mnt/c/Users/anshu/AppData/Local/trace-worktrees/*`
  is READ-ONLY here (`touch` → `Read-only file system`). Round-1 R-RET02 and
  R-JOB01 specialists correctly stopped without committing. The P0 Windows
  venv-fix commands still stand for a Windows session; they do not apply here.
- **Repair pattern for this session (applies to all five R-* repairs):**
  1. `git worktree add --detach /tmp/trace-wt/<name> <branch>` (writable path)
  2. Repair + project `.venv` in the worktree (export
     `UV_CACHE_DIR=/tmp/uv-cache-coord`; `/home/anshul/.cache` is read-only);
     reuse `/tmp/trace-ret02-venv` + `HF_HOME=/tmp/hf-cache-coord` where useful.
  3. Literal acceptance pytest per packet. Commit on detached HEAD.
  4. `git update-ref refs/heads/<branch> <newsha>` (record old → new SHA).
     Note: the branch stays checked out in the read-only linked worktree, whose
     files will read stale until a write-capable session resets it — harmless;
     verification always uses the new tip detached.
  5. Delete worktree `.venv`, `git worktree remove --force /tmp/trace-wt/<name>`.
  6. Handoff notes: edit `docs/program/inbox/<node>/handoff.md` in the parent
     checkout, leave UNCOMMITTED, report.
- **R-RET02 root cause (beyond the fix-spec):** fallback was NOT caused by
  missing local deps — `/tmp/trace-ret02-venv` has torch 2.14.0+cpu + ST 6.0.1,
  yet the adapter stays `deterministic-fallback`. Coordinator proved
  `PINNED_MODEL_REVISION e4ce9877abf3ed5223c6a46944e9514f7b60a2d2` 404s on
  huggingface.co (all files `.no_exist`) while `main` resolves; verified full
  `SentenceTransformer` load (384-dim) at `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`.
  Round-2 repair = re-pin adapter `:27` + test `:241` to that SHA, then re-run
  39/39 with `is_fallback=false` required.
- **R-JOB01 round-1 carry-over:** HEAD `c853f43`, base `a9255b4` ancestor OK;
  bug reproduced live (omitted receipt ACCEPTED as validated). Round 2 applies
  the fix-spec unchanged via the pattern above. R-JOB02 stays gated on landing.
- **R-CRX02 round 1** still running (read-only probes: byte-parity ground truth
  etc. remain useful); re-dispatch via pattern above if it reports blocked.
