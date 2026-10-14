# Common Session Protocol

Every session follows this protocol in addition to its role-specific brief.
The protocol is a safety and reproducibility contract, not a suggestion.

## Mandatory read order

1. `00_GLOBAL_CONTEXT.md`.
2. This file.
3. `04_SUBAGENT_RULES.md`.
4. The role-specific session brief.
5. `docs/program/SESSION_OPERATING_MANUAL.md`, `COMPONENT_REGISTRY.md`,
   `00_CHARTER.md`, `01_INVARIANTS.md`, `03_SHARED_CONTRACTS.md`, and the
   current `06_DECISION_LOG.md`/`07_RISK_REGISTER.md`.
6. The packet, input manifest, lease record, and current handoffs named by the
   role brief.
7. Only then inspect or modify source files.

If a named file is absent, stale, unreadable, or inconsistent with the
checkout, stop and report the exact discrepancy. Do not substitute memory or a
chat excerpt silently.

## Session lifecycle

### 1. Preflight

Capture:

- absolute repository path;
- current branch and commit;
- tracked and untracked status;
- relevant file hashes or content-manifest hash;
- runtime/tool versions;
- worktree path and lease ID;
- packet ID and verifier ID;
- external roots for scratch, data, and results.

Do not mutate until this record is written to the packet-local evidence
directory.

### 2. Scope lock

Translate the packet into a short scope table:

| Category | Record |
| --- | --- |
| Objective | One measurable outcome |
| Allowed paths | Exact files/directories |
| Forbidden paths | Protected code, docs, data, and user worktrees |
| Inputs | Commit/data/config/provider identities |
| Authority | Read-only, implementation, measurement, or decision preparation |
| Acceptance | Tests, receipts, hashes, and handoff required |
| Stop conditions | Missing decision, identity drift, unsafe fallback, or failed invariant |

Do not expand the scope because a nearby defect is interesting. Create a
follow-up packet instead.

### 3. Isolated worktree

Mutable implementation work must use a dedicated absolute worktree path that
is outside the active user checkout and outside OneDrive where practical. The
coordinator validates that the path is unique and that its starting commit is
correct. Never use a command copied from an old handoff without re-resolving
the absolute path.

Use a fresh task database and external scratch directory for lifecycle tests.
SQLite or in-memory evidence must not be described as proof of PostgreSQL RLS,
external-index behavior, or distributed recovery.

### 4. Implementation

Make the smallest coherent change satisfying the packet. Preserve public
compatibility unless the packet explicitly authorizes a contract change. Keep
canonical evidence immutable. Add tests at the same time as behavior changes.

Do not:

- edit another session's allowed paths;
- rewrite a migration whose deployment state is unknown;
- remove a legacy surface before its replacement and regression boundary are
  documented;
- make a fallback “temporary” in a certification code path;
- change a numeric threshold without a decision record;
- claim a test passed if setup, cleanup, provider, or data acquisition failed.

### 5. Verification

Run focused tests first, then the packet's complete suite. Capture the exact
command, environment, exit status, duration, test count, and output location.
Use external scratch paths to avoid OneDrive locking. Record failures rather
than hiding them. If a test cannot run, its status is `blocked`, not `passed`.

For data and benchmarks, record source/archive/extraction hashes and the
manifest used. For projection lifecycles, record candidate ID, active release
before/after, crash point, validation result, rollback target, and visible
read set.

### 6. Handoff

Use `03_HANDOFF_TEMPLATE.md`. The handoff must distinguish:

- static source observations;
- tests executed and their limits;
- changed artifacts;
- unresolved risks and decisions;
- claims that are explicitly not justified.

The chat response is only a pointer to the durable handoff. A session is not
complete until the handoff exists on disk.

## Error and receipt protocol

An expected failure in a negative test is evidence only when the system emits a
structured receipt containing at least:

- stable error code;
- stage (`preflight`, `acquisition`, `index`, `query`, `validation`, or
  `activation`);
- human-readable redacted detail;
- input/manifest identity;
- candidate/release identity where applicable;
- fallback-forbidden assertion;
- timestamp and environment fingerprint.

Do not return an empty success-shaped result for an exception. Do not label a
query an abstention merely because a backend returned no candidates.

## Authority levels

Use one of these labels in every handoff:

- `C0`: planning or static observation;
- `C1`: local developer smoke/fault evidence;
- `C2`: internal regression evidence;
- `C3`: reproducible real-data evidence under a pinned manifest;
- `C4`: independently verified release/gate evidence.

No session may self-assign `C4`. The coordinator and independent verifier
jointly maintain gate status.
