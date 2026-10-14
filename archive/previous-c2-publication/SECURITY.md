# Security Policy

Trace is designed as an evidence-preserving, fail-closed cognitive retrieval system. Security and data integrity are fundamental architectural priorities.

---

## Supported Versions

Only the latest stable release and the current `main` branch receive security updates:

| Version | Supported |
| :--- | :--- |
| `0.1.x` (main) | :white_check_mark: Supported |
| `< 0.1.0` | :x: End of Life |

---

## Security Architecture & Invariants

Trace adheres to the following core security principles:

1. **Local-First & Zero Telemetry**:
   - Trace core runs completely local to the operator's machine.
   - Trace never sends document contents, hashes, queries, or execution telemetry to any external cloud service or analytics server by default.

2. **Immutable Source Atoms & Cryptographic Provenance**:
   - Ingested records are stored as immutable source atoms.
   - Text spans are indexed by explicit byte offsets and cryptographic content hashes (BLAKE3 or SHA-256).
   - In auxiliary indexes, data is cross-referenced using external-content pointers (`content='atom'`), preventing out-of-sync or malicious mutation of source groundings.

3. **Fail-Closed Execution**:
   - Missing tables, corrupt data structures, unverified tokens, or tampered Merkle manifests trigger immediate failure (`PreflightFailure` or `IntegrityError`).
   - Under no circumstances does Trace degrade to insecure, unverified, or hallucinatory fallbacks.

4. **Secret Handling**:
   - Trace does not parse or inspect secret files automatically.
   - Operators are advised to configure data directory permissions appropriately:
     ```bash
     chmod 700 /path/to/trace-data
     ```

---

## Reporting a Vulnerability

If you discover a security vulnerability in Trace, please report it responsibly:

- **Email**: Contact maintainers at `security@trace-retrieval.org` or open a confidential security advisory via GitHub Security Advisories.
- **Please Include**:
  - Detailed description of the issue and potential impact.
  - Minimal reproducible example or proof-of-concept script.
  - Information on your operating system (Linux / Windows) and Python version.

### Response Timeline

- **Initial Acknowledgment**: Within 48 hours.
- **Status & Assessment**: Within 5 business days with triage results.
- **Remediation & Patch**: Security patches are released as high-priority hotfixes and credited in the release notes (unless anonymity is requested).

Please do **not** disclose vulnerabilities publicly in public GitHub issues until a coordinated advisory and patch have been published.
