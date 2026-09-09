# P0 verdict record (as received by the coordinator)

## Attempt 1 — branch `p11-h0-adopt` — QUARANTINED, no violations

Blind-critic reasoning (complete): all integrity probes clean — zero
tracked edits with only the four claimed new files, no mocks, no phantom
tooling, no silent PASS, forensic pass correctly non-certifying with a
truthful HOLD (signed false, exit 1, PENDING_HUMAN_BALLOT). Adoption
blocked because the strict Merkle trio FAILs with 9 delta-side errors, so
the acceptance row is not met and the corpus stays quarantined pending
reseal and human ballot.

Coordinator's live confirmation: packet tests 13/13; full suite 482
passed / 3 xpassed vs 469 / 3 xpassed baseline; frozen checks green;
mapping 10/10 resolved; strict verifier exit 1 with the 9 delta errors
embedded in `gate_manifest.json` (verdict HOLD, signed false).

## Attempt 2 — branch `p11-h0-seal-repair` — APPROVED, no violations

Blind-critic reasoning (ten probes, received truncated past
"…checker reimplements range parsing, scanning, and Mer…"; full text in
the session log cited below): zero tracked modifications with 11 additive
packet files, code-only phantom-tooling scan empty, statuses
PROPOSED-UNADOPTED / PROVISIONAL-UNADOPTED / PENDING_HUMAN_BALLOT with
null signature, `gate_manifest.json` still verdict HOLD, producer uses
tmp+fsync+rename with a genuine SIGKILL-during-stall test asserting no
publishable output.

Coordinator's live confirmation: packet tests 25/25 on plain invocation
(no PYTHONPATH); full suite 494 passed / 3 xpassed (+12 exactly, zero
regressions); frozen checks green; independent checker live
INDEPENDENT-PASS (100000 + 900000 = 1000000 docs, 2014465744 bytes,
union `5039acef…`, exit 0, still UNADOPTED). One delivery defect was
found and repaired inside the attempt: `test_h0_1m_seal.py` missed the
repo `sys.path` convention (plain-suite collection error); fix is a
two-line import-only edit, all else byte-identical.

## Provenance of these records

Verdicts arrived as subagent result envelopes in coordinator session
`01a08221-3b5b-7fc1-bbf7-9badd58759a2`; full child texts live in that
session's log, not in this pack. Everything else asserted here is
re-derivable via `reverify.sh` plus the manual full-suite command.
Corpus adoption and any merge remain human-gated and have NOT happened.
