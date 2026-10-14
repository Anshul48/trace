# Host-A disturbances during timed campaign _186 caused by architect-side subagents (recorded 2026-10-10 ~19:45Z)
Disclosed by the B-ann fix-round subagent (model report; times from file mtimes = observed, rest reported):
1. ~19:12Z-19:24Z: 520-doc flag-off differential, one core, nice -n 19, ~12 min, evidence/fix-round-1/flag-off-diff-520 (beam-exp/B-ann). Overlaps campaign chunk 17 (started ~19:05Z, observed chunk 16 start 18:31:56Z). Violated the 'tiny tests only' instruction I gave (I required >=500-doc differential in PROOF-PROTOCOL-V2 without saying where to run it: architect-side defect).
2. Before ~19:12Z, time UNKNOWN: a whole-filesystem `find / -iname "*hnswlib*"` reached /mnt/c (heavy IO), backgrounded then killed by the subagent.
3. A-beam fix rounds (codex1): tiny tests only (reported).
Effect on campaign timing: UNKNOWN; treat chunk 17 (and neighbours) timing as potentially perturbed in any timing analysis; chunk logs/receipts are authoritative. Lesson: the >=500-doc differentials and I1/I7 suites run on the VM, not host A.
