"""TL retrieval system (S-04 Narrow-first) on the accepted batch-storage candidate.

Contract index (all citations = sessions/S-04-CLOSURE.md unless noted):
  spec map .... tl-sys/SPEC-MAP.md
  Narrow path . Q2.1 dual-seed -> RRF k=60 -> top-M/2 -> widen (Q3.3) ->
                direct-descent/expand (Q7.2) -> select (Q10.2/Q11.1) ->
                receipt+disclosure (Q14) + citations (Q15)
  eval ........ Q16.1 frozen 4-slice protocol (see tl-eval freeze doc, forthcoming)

Revision pins (updated by maintenance; verified by test_identity_pins):
  CANDIDATE_TREE .... tl-candidate-batch/candidate @ 2382f878 (C-sibling fix)
  APPROVAL .......... d18a1676 (battery 9/9 PASS)
"""

CANDIDATE_REV = "2382f878"
CANDIDATE_APPROVAL = "d18a1676"
SPEC_SESSION = "S-04"
