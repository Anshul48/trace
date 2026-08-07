# Trace release benchmark intake

`technical-docs-v1.json` is a six-case deterministic development fixture. It
is deliberately marked `release_authority: false`; it cannot certify a
production release.

A release corpus must contain at least 300 reviewed in-domain cases spanning
direct lookup, multi-hop, dependency, contradiction, order, and out-of-scope
queries. Each gold atom-version ID must point to a frozen canonical evidence
snapshot. Set `release_authority: true` only after that review has happened and
run the benchmark with `release_gate: true`.

BRIGHT-derived coding cases are tracked in `bright-coding-v1.json` and must be
reported separately. Their licence approval and frozen source evidence are
operator-owned prerequisites; the checked-in fixture intentionally does not
assert either one.
