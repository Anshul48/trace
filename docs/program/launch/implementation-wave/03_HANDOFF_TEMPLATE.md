# Implementation Wave Handoff Template

Copy this template into the packet-local `evidence/handoff.md` and fill every
section. Do not replace missing information with “N/A” when the missing item
is a gate dependency; use `blocked` and explain why.

## 1. Identity

```yaml
packet_id: "<packet identifier>"
session: "<S0-S7>"
role: "<role>"
status: "in_progress|completed|blocked|needs_review"
authority_level: "C0|C1|C2|C3|C4"
started_utc: "<timestamp>"
completed_utc: "<timestamp or null>"
worktree_path: "<absolute path or read-only root>"
worktree_lease_id: "<lease or null>"
base_commit: "<full hash>"
verifier_id: "<id or pending>"
```

## 2. Summary

State the outcome in five sentences or fewer. Say whether the packet produced
implementation, data, evidence, a decision brief, or only an audit.

## 3. Inputs and provenance

| Input | Absolute path/URL | Version/hash | Purpose | Freshness check |
| --- | --- | --- | --- | --- |
| | | | | |

Include repository status, source-manifest hash, dataset manifest hash,
configuration/model fingerprints, and any external service identity.

## 4. Scope and authority

### Allowed paths

-

### Protected/forbidden paths

-

### Authority actually exercised

-

### Authority intentionally not exercised

-

## 5. Observed facts

List facts directly supported by source inspection or captured runtime output.
Include file/line anchors where useful. Do not mix proposals or assumptions
into this section.

## 6. Changes or artifacts

| Artifact | Path | Change type | Hash/identity | Reversible? |
| --- | --- | --- | --- | --- |
| | | | | |

For code changes, include the commit hash and a concise file-level summary.
For datasets, include raw archive, extraction, and normalized-manifest hashes.

## 7. Verification

| Test/check | Exact command | Environment | Result | Evidence path |
| --- | --- | --- | --- | --- |
| | | | pass/fail/blocked | |

Record test count, duration, skipped cases, expected negative cases, cleanup
status, and any unavailable capability. A failed setup or cleanup is not a
passing test.

## 8. Invariant checks

- [ ] Source truth was not mutated by a projection operation.
- [ ] Candidate projections were invisible before validation/activation.
- [ ] Previous validated release remains recoverable.
- [ ] Exact evidence/provenance survived the change.
- [ ] No certification fallback or synthetic substitution was used.
- [ ] Policy/authorization boundaries were preserved.
- [ ] Incremental/full or replay/rebuild parity was checked where required.

Explain every unchecked item.

## 9. Risks, decisions, and blockers

| ID | State | Evidence | Impact | Owner/next packet |
| --- | --- | --- | --- | --- |
| | open/contained/blocked | | | |

Explicitly list any decision that must be made by the human owner. Never mark
P-002, P-004, or P-005 as accepted from an agent recommendation alone.

## 10. Claim boundary

State what this handoff proves and what it does not prove. Use one of C0-C4
from the common protocol. In particular, do not call an internal fixture,
synthetic corpus, source inspection, or unit suite external certification.

## 11. Next dependency

```yaml
next_packet: "<packet or null>"
hard_dependencies:
  - "<exact artifact/decision/verifier>"
recommended_action: "<one sentence>"
safe_default: "<what remains unchanged if no action is taken>"
```

## 12. Handoff integrity

```text
Handoff writer:
Handoff file hash:
Input-manifest hash:
Commands log path:
Verifier receipt path:
Coordinator review state:
```
