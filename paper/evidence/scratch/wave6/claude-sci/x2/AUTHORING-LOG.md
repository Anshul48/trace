# X2 authoring log (claude-sci, 2026-11-06)
- 02:30:16Z PREREG14 frozen (sha dc20f5e1...). Sources sha 85fef3e8... sampled on the VM before the freeze; disjointness checked locally.
- ~02:30Z round 1: Muse briefs x2-author-m-1/2 (150 passages each, wave2 leases) and three Haiku calls (100 each; model parameter haiku; outputs author/queries_raw_h{1,2,3}.jsonl). Haiku authors reported hand-checking only (no script).
- ~02:38Z lint.py unchanged: H 300 in, 179 accepted, 121 rejected (all overlap>0.80; styles 1/0/2 = 81/37/3); M 300 in, 173 accepted, 127 rejected (all overlap>0.80; styles 85/38/4).
- 02:39Z regeneration round: Muse brief x2-regen-m (127 rejects) and one Haiku call (121 rejects, authoring_prompt_regen.md + 40% outside-vocabulary instruction as in xf-regen).
- ~02:45Z regen: Haiku 121/121 accepted; Muse 127/127 accepted (lint.py unchanged).
- 2026-11-06T02:50:30Z both sets frozen BEFORE any retrieval: X2H 300 queries sha 0bba2a98..., X2M 300 queries sha 77c620cf... (FREEZE-X2H.txt, FREEZE-X2M.txt). Both valid (>=200). Retrieval brief c-fuse-5 filed.
Query overlap (lint definition) on frozen X2 sets, computed before retrieval results: X2M mean 0.355 median 0.444; X2H mean 0.444 median 0.483 (XF 0.381, XG 0.506).
