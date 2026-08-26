# Session 2 - S1 B1.1 Benchmark Identity Refresh

Read the shared bootstrap prompt first. Work only in the newly leased
trace-bench scope. This is a narrow reproducibility follow-up, not a feature
development session.

## Mission

Resolve the untracked uv.lock issue so V1a receives one clean, reproducible
benchmark source and dependency identity.

## Direction

- Begin from the refreshed B1 commit and capture the exact dirty-state report.
- Determine whether uv.lock is the authoritative resolved dependency state.
  The preferred outcome is a small B1.1 commit that tracks it.
- If it must remain excluded, prove deterministic clean-clone regeneration
  from pinned inputs, record the exact tool/runtime versions and output hash,
  and explain why exclusion is safe.
- Refresh the source/dependency manifest and handoff identity to match the
  chosen outcome.
- Verify a clean clone can reproduce the declared environment and run the
  existing B1 test suite without using unpinned/editable product imports.

## Boundaries

Do not redesign runner behavior, change metrics, download datasets, invoke
live providers, or modify Trace/Trace-Lite. Preserve historical B1 commits and
all unrelated files.

## Suggested subagents

Use read-only reviewers for packaging/lock reproducibility and manifest
coverage. Only the leased S1 writer may make the narrow identity change.

## Exit

Produce a superseding B1.1 handoff with a clean Git status, exact commit,
manifest hashes, clone verification evidence, and a frozen V1a input manifest.
If clean reproducibility cannot be proved, stop as blocked.

## Exact identity decision

Inspect uv.lock before deciding. Do not assume it is disposable merely
because Git did not track it. Resolve one of these two recorded branches:

### Preferred branch - commit the lock

Create a narrow follow-up commit that tracks uv.lock, refreshes the source
and dependency manifest, and names the lock hash, uv version, Python version,
platform, and package metadata identity. Preserve B1 commit 0b01de5... as the
historical implementation identity; do not rewrite it. Give V1a the new
superseding commit.

### Exceptional branch - reproducibly exclude the lock

Use this only when the project contract explicitly treats the lock as
generated. Prove, in a clean clone with no previous cache, that pinned
inputs and a pinned tool regenerate exactly the same lock bytes. Record the
generation command, tool version, input hashes, output hash, and why the
result is certification-equivalent. An unexplained .gitignore entry is not
an acceptable resolution.

## Suggested checks

Inspect Git status, tracked-file inventory, source-manifest coverage, package
metadata, lock metadata, clean-clone behavior, dependency resolution, and
the existing B1 unit/negative matrix. Keep caches and prior results outside
the source identity. If a check requires a network or provider that is not
available, record that as an environment limitation rather than substituting
another package or result.

## Handoff fields

The B1.1 handoff must include old and new identities, lock decision, source
and dependency hashes, clean-clone commands, test counts, skipped/unavailable
checks, Git status after the change, V1a input manifest, and a statement that
no dataset/provider/certification run occurred.
