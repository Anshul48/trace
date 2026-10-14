# Security policy

## Reporting a vulnerability

Report privately to the repository owner via a GitHub private vulnerability
report. Include the file, the frozen (or wrapper) revision, reproduction
steps, and impact. Do not open a public issue for vulnerabilities.

## Scope notes

- `freeze-src/` is a frozen research snapshot: dependency versions are
  pinned by the freeze manifest, not curated for current CVEs. The pilot is
  a batch experiment harness, not a service; do not expose it to untrusted
  input or networks.
- `receipts/` are measurement records, not executable config: re-running the
  recorded commands requires billed VM hardware and the VM-side corpus cache.
- If you find a real key, token, or private corpus in the tree, report it as
  above and do not quote it in a public issue.
