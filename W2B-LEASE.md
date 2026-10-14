# SINGLE-WRITER LEASE — trace-release/

Holder: W2b (replacement TRACE publication worker).
Effective: 2026-10-14T10:25Z.
Predecessor W2 stalled (no output 35+ min, no live compute, stop RPCs time out).
If W2 revives, it MUST STAND DOWN on sight of this marker and make no further writes.

W2b is the ONLY writer to trace-release/ + worker-status/W2.md + W2-requests.md.
HARD GATE: NEVER push. No push before channel REVIEW-APPROVED.md names repo + candidate commit.
