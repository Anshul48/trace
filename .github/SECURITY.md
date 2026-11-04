# Security policy

## Reporting a vulnerability

Report privately to the repository owner through a GitHub private vulnerability report (Security tab, "Report a vulnerability"). Include the file, the revision, reproduction steps and the impact. Please do not open a public issue for a vulnerability.

A wrong number or an overstated claim is not a security issue: use the "A claim or number looks wrong" issue form instead.

## What is in scope

- The website in `docs/` is static: plain HTML, CSS and JavaScript, with no server, no cookies and no analytics, and it loads nothing from outside its own folder. The explorer runs entirely in your browser.
- `freeze-src/` is a frozen research snapshot. Its dependency versions are pinned by the freeze manifest and are not curated for current vulnerability reports. The pilot is a batch experiment harness, not a service: do not expose it to untrusted input or networks.
- `receipts/` holds measurement records, not configuration. Re-running the larger recorded builds needs billed hardware and a corpus cache that is not in this repository.
- `tools/run-trace.sh` serves `docs/` on `127.0.0.1` only.

## Secrets

No keys, tokens or private corpora belong in this repository, and CI scans file names for obvious ones. If you find a real key, token or private corpus in the tree, report it as above and do not quote it in a public issue.
