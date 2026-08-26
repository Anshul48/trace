# Independent Verifier: Worktree, Environment, and Evidence Requirements

> **Packet:** V0 — Independent Verifier Plan and Packet-Integrity Review  
> **Role:** Independent Verifier / Integration Reviewer  
> **Status:** Mandatory Verification Architecture Standard  
> **Governing Documents:** `01_INVARIANTS.md` (Invariants 7, 8), `SESSION_OPERATING_MANUAL.md` (Section 5), `04_EVALUATION_PROTOCOL.md`, `FOUNDATION_RELEASE.md`

---

## 1. Principle of Verification Independence

In accordance with Program Invariant 8 and the Session Operating Manual, an independent verifier must test candidate implementations from outside the implementer's execution context.

The verifier is bound by four absolute constraints:
1. **Never Execute in Implementer Worktree:** The verifier must operate in an isolated, clean worktree leased specifically for verification.
2. **Never Repair Candidate Code:** If a test fails, the failure is documented as an error receipt and returned for implementation repair. The verifier never edits candidate source code to make a test pass.
3. **Never Relax Acceptance Criteria or Invariants:** High retrieval scores or developer convenience never excuse unhandled fallbacks, candidate leakage, or broken rollback paths.
4. **Never Overstate Evidence Strength:** An in-memory, fake, or SQLite test must never be cited as proof of PostgreSQL transaction safety, Row-Level Security (RLS), external-index alias atomicity, or production crash recovery.

---

## 2. Worktree & Lease Requirements

### 2.1 Clean Verifier Worktree
- For any mutable verification task (V1a, V1b), the verifier creates a dedicated worktree directly from the immutable implementation commit submitted in the worker handoff:
  ```powershell
  git worktree add -b verifier/<task-id>-<timestamp> <worktree-path> <implementation-commit>
  ```
- The verifier worktree must be verified clean (`git status --porcelain` is empty) before any test execution.
- The verifier operates strictly on its own leased branch and never touches the implementer's active branch or working tree.

### 2.2 Worktree Lease Record
Every verifier worktree must maintain a valid `worktree-lease.json` (conforming to `templates/WORKTREE_LEASE_TEMPLATE.json`) containing:
- `lease_id`: Unique lease identifier.
- `holder_role`: `independent_verifier`.
- `source_commit`: Exact implementation commit under test.
- `leased_path`: Absolute path to the isolated worktree.
- `allowed_operations`: `["read", "test_execution", "fault_injection", "evidence_capture"]`.
- `forbidden_operations`: `["product_code_mutation", "merge", "rebase", "git_clean"]`.

---

## 3. Environment & Storage Requirements

### 3.1 External Local Scratch Root (R-14 Mitigation)
- **Windows / OneDrive Safeguard:** In accordance with Risk R-14 (`07_RISK_REGISTER.md`), SQLite database files, temporary test repositories, and high-frequency lockfiles must **NOT** be stored in cloud-synchronized folders (such as OneDrive) to avoid background file-locking and spurious I/O errors.
- **Dedicated Test Root:** All transient runtime directories, disposable databases, and candidate artifacts during verification must use an external local directory (e.g. `C:\trace-verify-tmp\<task-id>\` or OS temporary directory).

### 3.2 Environment Capture
Every verification report must capture and record:
- Operating system version, architecture, and build.
- Python runtime version, virtual environment path, and lockfile SHA-256 (`uv.lock` or `pyproject.toml`).
- Database engine version (e.g. SQLite version, PostgreSQL container version).
- Hardware capture (CPU cores, RAM, storage type).
- Network isolation status (confirming no unexpected outbound calls).

---

## 4. Fixture Ownership & Decoupling

1. **Independent Test Harnesses:** Verification tests (e.g. `tests/verifier/`) must be maintained independently or pinned as immutable verification assets. The verifier does not rely solely on developer unit tests.
2. **Adversarial & Negative Fixtures:** The verifier maintains dedicated negative fixtures designed specifically to stress failure boundaries:
   - Corrupted dataset archives (invalid checksums).
   - Incomplete manifests (missing licenses, unpinned models).
   - High-degree hub terms (testing graph co-occurrence explosion).
   - Malformed hierarchy graphs (topological cycles, orphaned atoms).
   - Expired or revoked source documents.
3. **No Developer Mock Substitution:** A passing developer mock test is non-certifying. The verifier tests the system's ability to reject mocks in certification mode.

---

## 5. Boundaries of Fake / In-Memory Evidence

To preserve rigorous truthfulness across all program claims, test environments are strictly categorized by capability:

| Environment Level | What It CAN Prove (Valid Scope) | What It CANNOT Prove (Mandatory Exclusion) | Claim Classification |
| :--- | :--- | :--- | :--- |
| **In-Memory / Fake** | - Logical schema validation<br>- State machine transitions (`building -> validating -> active`)<br>- In-process error receipt emission<br>- Interface contract compliance | - Process crash survival<br>- Concurrency / race conditions<br>- Disk I/O durability<br>- Real network transport / TLS | `C1 — Local Behavior` (Non-certifying) |
| **SQLite (In-Process / File)** | - SQLite ACID transaction semantics<br>- File-based candidate isolation in Trace-Lite<br>- Local pointer rollback<br>- Local graph degree/PPR work budgets | - Multi-tenant Row-Level Security (RLS)<br>- PostgreSQL MVCC / WAL replay<br>- Distributed index alias atomicity<br>- Production server recovery | `C1 / C2 — Regression Evidence` (Local TL only) |
| **Disposable PostgreSQL (Isolated)** | - PostgreSQL table schema & constraints<br>- Multi-tenant workspace isolation & RLS<br>- Atomic release pointer swaps via DB transactions<br>- Cortex Release rollback under concurrent reads | - External vector DB cluster crash recovery<br>- Cloud network partitions<br>- Large-scale (100K/1M) IOPS / memory limits | `C3 / C4 — Operational Evidence` (Trace release baseline) |
| **PostgreSQL + External Vector Index Adapter** | - End-to-end multi-modal Cortex Release lifecycle<br>- Atomic vector alias compensation on DB failure<br>- Real query-time multi-modal retrieval | - Production scale without 100K dataset load run<br>- Cloud provider SLA guarantees | `C4 / C5 — Governed Infrastructure` |

### Absolute Rule:
**Under no circumstances may a SQLite or in-memory test be cited as proof of PostgreSQL RLS enforcement, external index alias safety, or production-grade durability.**

---

## 6. Evidence Retention & Checksum Standards

Every verification run must produce an immutable evidence bundle stored under the corresponding task inbox directory (`docs/program/inbox/<task-id>/evidence/`):

1. **`verification-report.md`:** Formatted according to `templates/VERIFICATION_REPORT_TEMPLATE.md`.
2. **`receipts/`:** Individual JSON files for every negative case, strictly validating against `templates/ERROR_RECEIPT.schema.json`.
3. **`logs/`:** Raw execution logs with redacted secrets and correlation IDs.
4. **`checksums.json`:** SHA-256 cryptographic digests of all inputs, manifests, test scripts, stdout/stderr logs, and generated receipts.

```json
{
  "contract_version": "1.0",
  "verification_task_id": "V1a-20260819",
  "captured_at_utc": "2026-08-19T00:00:00Z",
  "files": {
    "receipt_V1A-SRC-001.json": "sha256:...",
    "receipt_V1A-PRV-001.json": "sha256:...",
    "verification_report.md": "sha256:...",
    "pytest_stdout.log": "sha256:..."
  }
}
```
