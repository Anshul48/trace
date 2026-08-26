# Risk Register

> **Status:** Draft. Risks are prompts for evidence and mitigation, not claims
> that the listed failure is currently present in every checkout.

| ID | Risk | Why it matters | Broad mitigation | Primary role |
| --- | --- | --- | --- | --- |
| R-01 | Candidate projection leakage | Partial derived state can distort retrieval. | Candidate isolation, validation, atomic activation, rollback tests. | TL / Trace |
| R-02 | Unbounded graph growth | Frequent-term co-occurrence can break scale budgets. | Degree/DF limits, deterministic edge policies, graph telemetry. | TL |
| R-03 | Benchmark fail-open behavior | Mock/synthetic/flat fallback invalidates release evidence. | Fail-closed manifests and negative fallback tests. | Evaluation |
| R-04 | Weak external evidence | Internal fixtures cannot support broad claims. | License-aware public data plus held-out downstream cases. | Data / Evaluation |
| R-05 | Source/projection confusion | Heuristics or summaries could be treated as fact. | Spine/Cortex contract, typed relations, provenance checks. | Trace |
| R-06 | Temporal/revocation gaps | Current retrieval may misrepresent historical truth. | Temporal Spine design and as-of/revocation tests. | Trace |
| R-07 | Agent-context drift | Workers can act on stale or conflicting assumptions. | Hashed packets, one canonical document set, scoped worktrees. | Coordinator |
| R-08 | Verification conflict | An implementer may unconsciously validate its own work. | Independent fixed evaluator and reviewer role. | Verifier |
| R-09 | Uncontrolled scale claims | Small tests may be extrapolated to 1M or larger. | Explicit 100K then 1M gates with resource/cost evidence. | Evaluation |
| R-10 | Premature consumer coupling | Downstream systems may inherit unstable internals. | Fakes, conformance, shadow mode, versioned service boundary. | Verifier |

## Risk handling policy

Each task packet references the risks it can create, discover, or reduce. A
worker reports a risk when it observes evidence, not merely when it speculates.
The coordinator assigns a status:

| Status | Meaning |
| --- | --- |
| Open | Known material uncertainty requires a planned mitigation. |
| Watching | A leading indicator is being measured. |
| Contained | A tested control reduces exposure but does not remove it. |
| Accepted | The human owner accepts the residual risk for a stated scope. |
| Closed | Evidence shows the risk no longer applies to the stated scope. |

Closing a risk requires a linked verification artifact; a passing happy-path
test is not enough.

## Detailed risk controls

| ID | Leading indicators | Required containment | Gate affected |
| --- | --- | --- | --- |
| R-01 | Candidate IDs appear in normal reads; failed build changes result set. | Revision-scoped writes, active-pointer reads, failure/rollback tests. | TL lifecycle, Trace release. |
| R-02 | Edge count or build time grows superlinearly; high-degree terms dominate. | DF/degree caps, deterministic policy, edge telemetry, adversarial corpus test. | TL 100K, Trace adaptation. |
| R-03 | Runner defaults to mock/sample/force mode; missing data still yields score. | Explicit release mode, assertion tests, non-certifying failure records. | Evaluation readiness. |
| R-04 | Dataset lacks license/hash/judgments or source access is unstable. | Admission record, archival plan if allowed, exclusion decision. | Public/100K gates. |
| R-05 | Summary/affinity is emitted as fact; unsupported answer lacks anchor. | Typed relations, evidence-bundle checks, review gates. | Promotion, consumer use. |
| R-06 | Current result cannot explain historical/revoked state. | Temporal model, as-of/revocation fixtures, policy review. | Trace readiness. |
| R-07 | Task uses stale docs or edits shared paths outside scope. | Input hashes, packet refresh, worktree isolation, coordinator review. | Every worker task. |
| R-08 | Only implementer-run tests are available. | Independent evaluator/clean-environment report. | Every release/gate. |
| R-09 | Throughput/latency asserted from small synthetic run only. | Real-corpus load manifest and per-class resource report. | 100K/1M gates. |
| R-10 | Consumer imports internals or treats memory output as authority. | Versioned service, fakes, advisory-only policy, conformance tests. | Shadow/production adoption. |

## Additional material risks

| ID | Risk | Broad mitigation | Primary role |
| --- | --- | --- | --- |
| R-11 | Provider or model behavior changes invalidate reproducibility. | Record provider/model fingerprints; retain input/output quality diagnostics; isolate model ablations. | Evaluation / TL |
| R-12 | Sensitive data leaks through diagnostics or evidence bundles. | Redaction policy, opaque IDs, negative privacy tests, log review. | Trace / Verifier |
| R-13 | Schema migrations lose rollback or source lineage. | Forward/backward migration plan, backup/replay drill, retained metadata. | Trace |
| R-14 | Worktree or OneDrive/Windows environment causes non-product test failures. | External writable test roots, environment capture, separate cleanup failures from product evidence. | Verifier |
| R-15 | Documentation turns assumptions into apparent facts. | Status labels, current-state audits, evidence links, claim-level reporting. | Coordinator |
| R-16 | Scale economics overwhelm local developer use. | Budget envelope, selective activation/model tiering, cost-per-query/build tracking. | Evaluation / Trace |

## Escalation triggers

Immediately pause the affected packet and request direction when:

- source truth, policy, tenant isolation, or deletion/revocation semantics may
  be weakened;
- a required real dataset cannot be used lawfully or reproducibly;
- a worker needs destructive data cleanup or broad migration authority;
- a performance result depends on an undisclosed fallback or changed evaluator;
- consumer integration would introduce action authority or direct storage access;
- an apparent implementation shortcut would bypass candidate validation or
  rollback.

## 2026-08-19 observed-risk update (D0 Reconciliation)

| ID | Updated state | Evidence boundary | Required next action |
| --- | --- | --- | --- |
| R-01 | Contained in design; Open in code. | Candidate affinity/priors write active without release scoping. P-003 accepted. | TR1 implementation of release-root & L1 candidate/active isolation; V1b verifier. |
| R-02 | Contained in L1 scope; Open in algorithm. | All-pairs co-occurrence has $O(n^2)$ term frequency behavior. Isolated from L1 scope. | TL3 empirical measurement brief; P-002 decision; TL2 implementation. |
| R-03 | Contained in governance; Open in runner. | Mock defaults, synthetic sample generation, TLS bypass, and empty-result metric inflation audited. P-007/P-008 accepted. | B0 Git bootstrap -> B1 fail-closed runner -> V1a independent verification. |
| R-04 | Contained in portfolio; Open in staging. | Admitted core portfolio (SciFact, NFCorpus, FiQA, BRIGHT, MultiHop-RAG, MuSiQue) accepted under P-001. | D2a raw acquisition with cryptographic checksums and layout validation. |
| R-05 | Contained in architecture. | Spine/Cortex separation enforced; summary nodes scoped to projection objects. | TR1 / L1 verification. |
| R-06 | Open, deferred to TR2. | Partial `as_of_event` does not resolve historical Cortex release or valid-time contracts. | S3 TR1 delivers P-004 decision brief; P-004 decision; S3 TR2 implementation. |
| R-07/R-15 | Contained. | Baseline repositories, commits, and diffs pinned across Trace, Trace-Lite, trace-bench, and Control Plane. | Worktree lease enforcement for all mutable sessions. |
| R-08 | Contained in planning. | V0 frozen negative matrices established for V1a and V1b. Verifier isolated from implementation. | S5 execution gated behind B1 and TR1/L1 handoffs. |
| R-09 | Contained. | S7 real 100K gated strictly behind Foundation Gate acceptance. Small-scale claims barred. | S7 execution after Foundation Gate. |
| R-14 | Contained. | Windows/OneDrive file-locking mitigated by mandating external scratch roots (`%LOCALAPPDATA%`). | Enforced in all worktree lease records. |

## 2026-08-19 observed-risk update (S0 R1 reconciliation)

| ID | Updated state | Evidence boundary | Required next action |
| --- | --- | --- | --- |
| R-01 | Open in implementation; independent verification pending. | L1/TR1 handoffs report candidate isolation, but no V1b runtime receipt exists. | Run separate V1b-TL lifecycle and V1b-Trace release sub-gates from fresh worktrees. |
| R-02 | Open and decision-blocked. | L1 includes a P-002 measurement brief; no human graph budget has been selected. | Preserve current graph behavior; human P-002 then TL2. |
| R-03 | Contained in implementation; open at source identity and certification boundary. | B1 reports 26/26 tests, but live head is `0b01de5e...`, the handoff's `0b01de5c...` full hash is absent, and `uv.lock` is untracked. | S1 B1.1 publishes a clean superseding identity; then S5 V1a verifies. |
| R-04 | Contained for raw staging; open for normalized evidence. | Seven D2a metadata sets match live external files; no D2b output or independent D2a verifier packet exists. | S4 D2b after B1.1 manifest/schema contract; raw roots remain immutable. |
| R-05 | Open at claim boundary. | Implementation evidence is not an independent release claim. | Keep the program label `implementation_complete / independent_verification_pending`. |
| R-06 | Open and decision-blocked. | TR1 supplied a P-004 brief; TR2 and temporal V1b are not executable. | Human P-004, then TR2 and final V1b temporal verification. |
| R-07 | Open in inherited records; contained for R1 dispatch. | D0 leases expired; the 103-file control-plane lock is stale against the live 213-file tree; B1 identity drift is recorded. | Use R1 input hashes, fresh leases, and the post-write control-plane lock. |
| R-08 | Contained by assignment boundaries; not verified. | Fresh separate V1b worktree/scratch leases exist; V1a remains blocked. | S5 owns verifier paths and may not repair candidate code. |
| R-09 | Contained. | 100K/1M nodes remain behind Foundation Gate and P-005. | Keep scale and consumer claims blocked. |
| R-14 | Contained for next sessions. | Fresh verifier scratch roots are outside OneDrive and were absent at lease time. | Create only within the assigned lease and record cleanup status. |
| R-15 | Open until current records are consumed. | Prior status called implementation nodes ready/unblocked without independent receipts. | Use the R1 status board and packet-local claim boundaries. |

R1 intentionally leaves **P-002**, **P-004**, and **P-005** deferred. No risk
state above is a human acceptance of residual policy or a gate closure.

## 2026-08-23 Human Gate A update

| ID | Updated state | Evidence boundary | Required next action |
| --- | --- | --- | --- |
| R-02 | Mitigation policy accepted; implementation open. | Human P-002 accepts bounded DF/degree/PPR/query limits recorded in `DEC-P-002`; this is not a 100K certification. | S2 TL2 implementation, adversarial high-DF measurements, and independent V1b graph verification. |
| R-06 | Temporal policy accepted; implementation open. | Human P-004 accepts the full bitemporal/revocation contract recorded in `DEC-P-004`; deployment and historical completeness remain unverified. | S3 TR2 implementation, temporal fault matrix, and independent V1b temporal verification. |

## 2026-08-23 Final V1b update

| ID | Updated state | Evidence boundary | Required next action |
| --- | --- | --- | --- |
| R-08 | V1b verification blocked by environment/infrastructure. | Graph low-level cases are partial C1; temporal checks are C0 static-only. Missing locked packages and unavailable PostgreSQL/RLS/external/deployment paths were recorded without fallback. | Provision exact supported verifier environments and direct required infrastructure, then rerun both immutable V1b sub-gates. |
| R-09 | Scale gate remains blocked. | Session 8 explicitly bars Session 9, P-005 closure, Foundation Gate, and 100K/1M claims. | Do not advance until V1b and subsequent real baseline gates pass. |
