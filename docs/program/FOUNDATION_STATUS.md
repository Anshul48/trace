# Foundation Program Status

> **Status:** Gate A recorded 2026-08-23; implementation completion remains separate
> from independent verification and human gate acceptance.

## Current objective

Create the finite, trustworthy, reproducible Foundation Release described in
`FOUNDATION_RELEASE.md`. Broad architecture research begins after the human
reviews the Foundation Complete record.

## Program State

`scale_certification_recovery_level_1 (Level 1 100K Requalification Complete & Verified; Submitted for Gate C2 Review)`

Following the lead auditor audit findings and Wave R0 containment, Level 1 has been fully executed under `SCALE_CERTIFICATION_RECOVERY_PLAN.md`:
- **L1-01 100K Gap Analysis:** Sealed in `docs/program/inbox/l1-01-100k-reconciliation-20260828/`.
- **L1-02 Corpus Capsule Freeze:** Exactly 100,000 unique records frozen with selection Merkle root `5467c64a...` across 5 licensed corpora (`docs/program/inbox/l1-02-corpus-capsule-20260828/`).
- **L1-03 Runner Contract:** Specification sealed in `docs/program/inbox/l1-03-runner-contract-20260828/`.
- **L1-04 Truthful Runner Implementation:** Quarantined, fail-closed canonical runner implemented in `scripts/run_100k_scale_gate.py` with zero score floors and true full-event replay.
- **L1-05 Calibration Diagnostics:** 1K and 10K diagnostic calibrations verified.
- **L1-06 Candidate Execution:** 100,000 document run completed (202,334 atoms, 100.0% anchor slice recovery, 16.03 ms P95 graph PPR latency, 100% full-event replay).
- **L1-07 Independent Verification:** Independent verifier audited all raw telemetry, verified 6-table SHA-256 state-hash parity, and signed attestation receipt (`docs/program/inbox/l1-07-verifier-attestation-20260828/`).
- **L1-08 Gate C2 Dossier:** Consolidated master dossier assembled in `docs/program/inbox/l1-08-gate-c2-dossier-20260828/` for Human Owner promotion review (`promote_100k`).

## Active Task Board (Level 1 Complete / Gate C2 Review Ready)

| Node | Packet | State | Owner / Session | Next Condition / Hard Dependency |
| --- | --- | --- | --- | --- |
| **R0-01** | `r0-01-claim-inventory-20260828` | **CLOSED (PASS)** | Audit Specialist | Claim inventory and git object ledger sealed. |
| **R0-02** | `scripts/` (quarantine) | **CLOSED (PASS)** | Quarantine Specialist | Unsound runners fail closed; `--diagnostic` enforced. |
| **R0-03** | `r0-03-forensic-manifest-20260828` | **CLOSED (PASS)** | Forensics Specialist | Read-only SQLite & corpus manifest sealed. |
| **R0-04** | `r0-04-reconciliation-20260828` | **CLOSED (PASS)** | S0 Coordinator | Governance records aligned. |
| **R0-06** | `tests/test_scale_recovery_quarantine.py` | **CLOSED (PASS)** | Verifier Specialist | Negative integrity fixtures passing 9/9. |
| **L1-01** | `l1-01-100k-reconciliation` | **CLOSED (PASS)** | Data Steward | Level 1 100K gap analysis sealed. |
| **L1-02** | `l1-02-100k-corpus-capsule` | **CLOSED (PASS)** | Data Steward | Deduplicated 100K corpus & judgment freeze sealed. |
| **L1-03** | `l1-03-runner-contract` | **CLOSED (PASS)** | Scale Architect | Fail-closed runner interface and threshold contract sealed. |
| **L1-04** | `l1-04-runner-repair` | **CLOSED (PASS)** | Implementer | Truthful 100K runner rewrite with zero score floors. |
| **L1-05** | `100k_scale (1k/10k)` | **CLOSED (PASS)** | Scale Architect | 1K and 10K diagnostic calibrations verified. |
| **L1-06** | `100k_scale (100k run)` | **CLOSED (PASS)** | Scale Implementer | 100,000 document run completed and raw telemetry sealed. |
| **L1-07** | `l1-07-verifier-attestation` | **CLOSED (PASS)** | Independent Verifier | 6-table SHA-256 state-hash parity audited and attestation signed. |
| **L1-08** | `l1-08-gate-c2-dossier` | **CLOSED (PASS)** | Coordinator | Master Gate C2 Dossier assembled and submitted. |
| **Gate C2** | `Human Gate C2 (Requalification)` | **READY FOR REVIEW** | Human Owner | Human promote/repair/reject decision (`promote_100k`). |
| **Gate D** | `Human Gate D (1M Pilot Plan)` | **BLOCKED** | Human Owner | Blocked pending Gate C2 promotion decision. |
| **Gate F2** | `Human Gate F2 (1M Certification)` | **BLOCKED** | Human Owner | Blocked pending Level 2 execution and Gate F2 verification. |

## Human Decision Status

- **P-001 (Accepted):** Core real-data portfolio admitted (SciFact, NFCorpus, FiQA, BRIGHT, MultiHop-RAG, MuSiQue; BigANN ops-only).
- **P-002 (Accepted 2026-08-23):** Option B Balanced Bounding; binding contract is in the TL2 decision record and `DEC-P-002`.
- **P-003 (Accepted):** Unified Cortex Release root architecture (Option A: Release Root with Carried-Forward Components).
- **P-004 (Accepted 2026-08-23):** Option A Full Bitemporal Contract; repeat-erasure addendum accepted 2026-08-25.
- **P-005b (Accepted 2026-08-26):** Large-Token Retrieval Readiness Thresholds, Hardware Profiles & Resource Budgets (`DEC-P-005b` at Human Gate B2).
- **Gate C2 (Reclassified 2026-08-28):** Real 100K Scale Gate Reclassified as Unconfirmed (`DEC-GATE-C2-PASS-REMEDIATED` -> `UNCONFIRMED`).
- **1M Claims (Revoked 2026-08-28):** Revocation of 1M scale claims and invalidation of `b9b03f3` (`DEC-1M-SCALE-REVOKED`).
- **P-007 (Accepted):** `trace-bench` initialized as independent Git repository in-place under B0.
- **P-008 (Accepted):** `trace-bench` designated as sole canonical certification runner.

## Non-negotiable boundaries

- no certification from mock, synthetic, forced, hidden-fallback, or insecure
  evaluation paths;
- no data download until source-specific authority and P-001;
- no mutable packet without a pinned base, allowed paths, acceptance evidence,
  and independent verifier;
- no broad deep research/architecture program before Foundation Complete;
- no 100K, 1M, or consumer-shadow claim before its DAG dependencies pass.

## Update protocol

The coordinator changes a state only after a worker writes a durable handoff
and the relevant verifier/human review occurs. Keep failed and blocked states
visible; create a repair packet rather than overwriting the history.

## Updated packet dependencies

| Packet | Exact state | Minimum prerequisite |
| --- | --- | --- |
| D0 | completed | P-001/P-003/P-007/P-008 recorded, leases issued |
| S1 (B0/B1) | completed | Pinned on canonical `main` at `c0ea9fbf...` with tracked `uv.lock` |
| S1 (B1.1) | completed | Pinned on canonical `main` at `c0ea9fbf...` |
| S2 (L1) | completed / verified | Commit `7ff40dc...` in clean worktree `trace-lite-l1` |
| S3 (T0/TR1) | completed / verified | Candidate `f7bd96e...` in clean worktree `temporal-r5-successor-final8` |
| S4 (D2a) | completed | Seven live roots; portfolio and metadata hashes match |
| S5 (V1a) | CLOSED (PASS) | Clean candidate `c0ea9fbf...`; 26/26 tests passed offline |
| S5 (V1b-TL lifecycle) | CLOSED (PASS) | Candidate `3e7e9f0...` (tree `ef83211...`) |
| S5 (V1b-Trace release) | CLOSED (PASS) | Candidate `f7bd96e...` (tree `91d93da...`) |
| S5 (V1b-TL graph) | CLOSED (PASS) | Candidate `3e7e9f0...` (tree `ef83211...`); R4 verified 34/34 tests, 8/8 boundary cases, true limit breaches, 100K raw measurement log |
| S5 (V1b-Trace temporal) | CLOSED (PASS) | Successor `f7bd96e...` (tree `91d93da...`); R5 verified 66/66 tests, migrations 001-007, BYPASSRLS=false, real container stoppage, MinIO 404, delta=0 repeat writes, Ed25519 signed |
| S4 (D2b) | completed / accepted | Corrected candidate and independent D2b receipt accepted |
| S2 (TL2) | completed / independently verified | Graph evidence verified and sealed under R4 |
| S3 (TR2) | completed / independently verified | Temporal successor verified and sealed under R5 |

| S6 (P-005/B3) | unblocked / executable | V1a + D2b + V1b CLOSED (PASS); ready for real baseline execution |
| Foundation Gate | gated / blocked | V1a + V1b + B3 dossiers accepted |
| S7 (100K/1M) | gated / blocked | Foundation Gate complete |

## 2026-08-25 Gate V1b-R5 Independent Verification & Attestation (CLOSED - PASS)

Gate V1b-R5 was executed and independently audited with final verdict **CLOSED (PASS)**:

1. **Graph Sub-Gate (V1b-TL-graph - PASS):**
   - **Candidate**: `3e7e9f0ee460e3af75f3935343f6d6f2089f9f7c` (Tree `ef83211ff9a52bce0706bda7b102639830b5a554`).
   - **Low-Level Boundary Topologies**: 8/8 canonical boundary cases passed.
   - **Negative Limit Breaches**: Actively exercised and enforced 35 ms wall time, 64 MiB memory, 512 max activated nodes, 2,500 max traversed edges, and top-100 rank truncation through product engine.
   - **100K Tool Measurement**: Real 100K graph measurement executed and logged unedited to `raw_logs/adversarial_budget_100k.log`.
   - **Test Suite**: 34/34 pytest suite passed cleanly in isolated detached worktree with 96 installed packages.
   - **Manifest**: 8/8 items sealed with 100% SHA-256 match.

2. **Temporal Sub-Gate (V1b-Trace-temporal - PASS):**
   - **Candidate**: `f7bd96e9c5e0f9326b53a074024e7ace889f6e36` (Tree `91d93da3a003dd062d76a4d1aa1cfd40412d831c`).
   - **Live PostgreSQL Stack**: 127.0.0.1 loopback-pinned stack (Postgres:16, OpenSearch:2.19.1, Qdrant:1.14.1, MinIO) with health checks, `docker version`, and `docker inspect` logs.
   - **Migrations Ledger**: Migrations 001–007 applied with verified idempotency and recorded SQL SHA-256 ledger.
   - **Tenant Security**: Strict RLS tenant isolation verified under non-superuser `BYPASSRLS=false`.
   - **Real Container-Loss Fault Injection**: Qdrant container physically stopped (`docker stop v1b-r5-temporal-final8-20260825-qdrant`) during alias swap; product caught connection refusal, executed multi-index rollback compensation (OpenSearch alias restored to `rev-1`), active DB release preserved, failed candidate recorded.
   - **Live Search & Filter Matrix**: Multi-tenant queries verified workspace isolation, temporal filters, and candidate release invisibility; raw JSON responses captured.
   - **Live Erasure & Zero-Write Repeat**: Projection objects and memberships purged; raw S3/MinIO object deleted and confirmed absent via HTTP 404; direct SQL tuple mutation counter verified $\Delta = 0$ writes on repeat requests.
   - **Test Suite**: 66/66 pytest suite passed cleanly.
   - **Cleanup**: 0 surviving verifier containers verified.

3. **Independent Reviewer Attestation:**
   - **Reviewer Lease**: `lease-temporal-r5-successor-final8.json`
   - **Acceptance Manifest**: `docs/program/inbox/v1b-lifecycle-temporal-verifier-20260819/evidence/r5/v1b_r5_reviewer_acceptance_manifest.json`
   - **Ed25519 Public Key**: `7148f27079158ce885d14c54a1367f1ef9a83f09004c6ff4a5f4a8ba92be09f3`
   - **Ed25519 Signature**: `dcebb7c73415dfb70a5454076a34236451db95fa416712014a9c8281423565b87512d994c1267f169184c2b45242da7646efd3564d6b3ad7462c85a3580fe106` (64 bytes cryptographic signature in `v1b_r5_reviewer_acceptance.sig`)

## 2026-08-25 Gate V1a Independent Runner Integrity Verification (CLOSED - PASS)

Gate V1a was executed and independently verified with final verdict **CLOSED (PASS)**:
- **Candidate Commit**: `c0ea9fbf37bc50c88336f198437be031c18d6f64` on canonical `main`.
- **Test Suite**: 26/26 tests passed (13 harness unit tests + 13 negative matrix fail-closed tests) with non-editable imports and 100% offline dependency wheel caching (`torch==2.13.0` resolved).
- **Receipts**: Complete structured error receipts and `certification_eligible: false` proofs recorded in `docs/program/inbox/v1a-runner-integrity-20260819/`.


