# P0 independent-audit pack — how to use

You are auditing the Trace v1.1 P0 (H0 corpus-contract) packet work.
Nothing here is merged: `main` is at `0150fbc`; all packet files are
uncommitted on branch `p11-h0-seal-repair` (attempt-1 HOLD evidence also
present; sibling branch `p11-h0-adopt` preserves attempt 1 alone).

## Read in this order

1. `verdicts.md` — what was built, what each blind critic ruled, and why.
2. `../selection_reconciliation.md` — the three-way shard table
   (d14f1a2 vs HEAD vs staged-byte recompute) and the successor proposal.
3. The code: `benchmarks/verify_1m_checksums.py` (path 1),
   `benchmarks/verify_1m_independent.py` (path 2),
   `scripts/seal_1m_manifest.py` (atomic producer),
   `scripts/sign_gate_manifest.py` (attempt-1 gate signer).
4. Machine-readable claims: `../selection_record.json`
   (successor selection, PROPOSED-UNADOPTED),
   `../provisional_1m_manifest.json` (sha `4f4deb50…`, PROVISIONAL-UNADOPTED),
   `../gate_manifest.json` (attempt-1 HOLD, signed false).

## Re-verify with one command

`bash docs/program/inbox/h0-1m-corpus-contract/audit/reverify.sh`
runs, in order: clean-tree check (zero tracked edits expected), packet
tests (25), frozen BEIR checks, both `--help` smoke checks, the
independent checker on the provisional manifest, and the SHA inventory
below. Full suite (`pytest tests/ -q`, ~12 min) is left manual — see
the script tail for the exact command and the counts to expect
(494 passed, 3 xpassed).

## Open items (notin'scope for the audit to resolve)

- Successor-contract ballot for `H0-1M-SUCCESSOR-SEL-01` — drafted in
  `selection_reconciliation.md` §4, needs a human signature.
- Merge of `p11-h0-seal-repair` — deferred by the human until all
  stages complete. Attempt-1 branch `p11-h0-adopt` disposition pending.
- Full-suite re-run on your own checkout (counts above are ours).
