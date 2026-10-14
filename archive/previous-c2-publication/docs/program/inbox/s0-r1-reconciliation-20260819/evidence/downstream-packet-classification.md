# Downstream-Looking Packet Classification

**Method:** Read packet state/content, handoff presence, explicit historical
markers, and dependency statements. Directory names were not used as proof.

| Directory | Classification | Evidence basis | R1 disposition |
| --- | --- | --- | --- |
| `b1-e2a-fail-closed-runner` | active evidence | Completed handoff, live implementation commit, source manifest, and test receipt are present | Retain as implementation evidence; supersede identity through B1.1 |
| `l1-tl1-candidate-active-lifecycle` | active evidence | Completed handoff, clean `7ff40dc...` worktree, lifecycle evidence, and P-002 brief are present | Retain; send only TL lifecycle to initial V1b |
| `tr1-unified-cortex-release-20260819` | active evidence | Completed handoff, clean `454c5ae...` worktree, release tests, and P-004 brief are present | Retain; replace pending verifier assignment in R1 |
| `b2-authorized-data-staging-20260819` | active evidence | Completed D2a handoff, portfolio manifest, seven live roots, checksum receipt, and layout evidence are present | Retain as staged-data evidence; independent verifier receipt still absent |
| `v0-verifier-plan-20260819` | active evidence | Completed read-only handoff and frozen V1a/V1b matrices are present | Use as the verifier-plan authority; not runtime verification |
| `f0a-e1-refresh-20260819` | active evidence | Completed read-only audit and source-anchored fallback inventory | Use as historical input to B1/V1a; not current source identity |
| `f0b-d1-refresh-20260819` | active evidence | Completed candidate/admission records and mapping plan | Use as D2a provenance input; not proof of current raw files alone |
| `f0c-repository-boundary-20260819` | active evidence | Completed boundary record, but its identities are superseded by live R1 refresh | Retain for history; do not reuse its leases or snapshot |
| `d0-coordinator-20260819` | historical material | Completed launch record with one-day leases and pre-wave statuses | Retain; all D0 leases are expired and replaced by R1 |
| `v1a-runner-integrity-20260819` | unverified | Packet exists, explicitly blocked, and has no runtime handoff/receipt | Keep blocked on B1.1; assign fresh reserved lease |
| `v1b-lifecycle-temporal-verifier-20260819` | unverified | Packet exists, explicitly blocked, and has no runtime handoff/receipt | Split into four sub-gates; lease only the two executable sub-gates |
| `v1-v1a-integrity-verifier` | historical material | Earlier duplicate V1 packet says queued after B1 and is superseded by the dated V1a packet | Do not dispatch or use as current assignment |
| `tl2-bounded-association-20260819` | planning material | Packet explicitly says blocked on P-002 and lists required future evidence | Keep blocked; no lease or policy choice |
| `tl3-durable-provenance-proof-20260819` | planning material | Packet explicitly says blocked until L1 is independently verified | Keep behind independent L1/V1b evidence |
| `tr2-temporal-revocation-20260819` | planning material | Packet explicitly says blocked on TR1 and accepted P-004 | Keep blocked; no temporal semantics chosen |
| `b3-certification-manifest-20260819` | planning material | Packet explicitly says blocked on B1, B2, P-005, and clean identities | Keep gated behind B1.1, D2b, V1a, and human P-005 |
| `foundation-gate-20260819` | planning material | Packet explicitly says blocked until named evidence receives independent review | Keep Foundation Gate blocked |
| `trace-program-research-01` | historical material | `STATUS.md` explicitly labels it historical research/context only | Retain read-only; not assignment or source authority |
| `seed-packets` | planning material | README explicitly labels all entries unassigned starter context bundles | Do not dispatch or treat as current packet authority |

## Negative finding

No current runtime verifier handoff was found for V1a, V1b, or the D2a
`d2b-manifest-verification` identifier. The absence is recorded as a blocker,
not converted into a successful verification claim.
