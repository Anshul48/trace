# PREREG15 — C-FUSE stage 6 (X3): overlap-controlled test, one author, two overlap conditions on the same fresh passages (claude-sci, 2026-11-06; frozen BEFORE any X3 query is authored; sha in PREREG15.sha256)
Trigger: referee-v4 and the lead's own check. After five query sets the fixed fusion (MMr) cleared its source-hit bar over dense (Dr) on X0, XG, X2H and missed on XF, X2M. Author does NOT separate these (X0 was worker-written and cleared); mean query-source content-word overlap (lint.py definition) does: cleared 0.460, 0.506, 0.444; missed 0.381, 0.355. Post-hoc query-level look: gain larger at overlap >= 0.45 in every set. All post-hoc. This test asks the question prospectively.
## Question
On the SAME 300 fresh passages, with the SAME author (Muse hands, as X0/XF/X2M), does asking for queries that reuse more of the passage's own words (condition H) produce a larger fusion gain over routed dense than asking for queries that avoid the passage's words (condition L)?
## Fresh set X3
- Sources: scratch/wave6/claude-sci/x3/sources_x3.jsonl (sha256 db36f071d314fdeb8a169e04b557acef589222b36f1f32014e0a475a449be0e7), 300 passages, 75 per shard, 100 per style, seed 20261110, sampler sample_fresh4.py (= sample_fresh3.py with seed/prefix changed). Own check 2026-11-06: 300 unique docs and ordinals; zero doc/ordinal overlap with X0 queries and 600-row sample, XF queries and sources, XG sources, X2 sources, and the 50 probes.
- Same style per passage in both conditions (0 question, 1 keyword, 2 description); paired by passage.
## Authoring
- Author: Muse hands via laptop briefs, one brief pair per condition (L: 2x150, H: 2x150), independently; no author sees the other condition's output. Prompts saved before the briefs. Family by launch parameter only.
- L rules: the xf-author rules (as in X0/XF/X2M) plus: at least 40 percent of content words must NOT appear in the passage.
- H rules: the same rules except: reuse the passage's own distinctive words and names; at least 60 percent of content words must appear in the passage. Still no run of 6 or more consecutive copied words, no copy of the first sentence, no banned words, 3-30 words.
- Lint: lint_band.py (lint.py rules unchanged; ONLY the overlap rule is replaced by a band): L accepted iff overlap <= 0.45; H accepted iff 0.55 <= overlap <= 0.90. ONE regeneration round per condition for rejects (same author); remaining rejects dropped, not edited. Each condition is valid iff >= 200 queries survive; the paired analysis uses passages surviving in both. Both files frozen (sha256 + timestamp) BEFORE any retrieval.
- Manipulation check (computed before retrieval, lint definition): mean overlap H minus L on common passages must be >= 0.20; otherwise "INVALID: manipulation".
## Arms, gates, metrics
Exactly PREREG14: c-fuse-5 code unchanged (Dr, Br, MMr, RRFr), gates G1/G2 >= 95 %, G3 same C; one run per condition, attempts 1; style-macro; bootstrap over doc_id, 10,000 resamples, default_rng(20261109).
## Verdicts
- Per condition: P1 as PREREG14 (MMr-Dr: d_hit >= +0.04, d_mrr >= +0.03, lower CIs > 0) and P2 (MMr-Br: d_hit >= +0.03, d_mrr >= +0.02, lower CIs > 0).
- PRIMARY (co-primary C): paired contrast on common passages D = d_hit(MMr-Dr | H) - d_hit(MMr-Dr | L): "OVERLAP SUPPORTED" iff manipulation check passes AND D >= +0.03 AND lower CI bound > 0 AND G1-G3 pass for both. Otherwise "OVERLAP NOT SUPPORTED (D ..)". INVALID if a condition has < 200 queries or a gate fails.
## Pre-written readings (written now)
1. SUPPORTED with H passing P1 and L failing: fusion's source-hit gain depends on how much of the passage's wording the query reuses, at least for this author and style mix; the paper states overlap as the working explanation, still synthetic.
2. SUPPORTED with both passing, or H larger but L also passing: overlap modulates the size of the gain; the stage-3/X2M misses are not explained by absence of gain alone.
3. NOT SUPPORTED with both failing P1: the earlier passes are not reproduced by raising overlap with this author; overlap is withdrawn as an explanation and the five-set pattern is reported as unexplained.
4. NOT SUPPORTED with both passing: the gain here does not depend on the overlap condition; the five-set pattern is unexplained by overlap.
5. NOT SUPPORTED with L passing and H failing: reported as is; the post-hoc overlap explanation is withdrawn.
## Secondary (no gate)
RRFr; per-style tables; per-condition Br, Dr macros; source-outside-C; per-condition mean/median overlap; whether H queries remain natural (a small manual sample of 20 per condition by the lead, descriptive only).
## Scope
Synthetic, model-written (one author family), one store, one embedding model, Dr is exact dense over C. H queries are not a model of user behaviour; they test a mechanism. The instruction changes more than overlap (it changes how much of the passage's vocabulary and names appear), so a positive result supports "reuse of passage wording" not an isolated lexical variable. No human-written queries, no latency or memory claim, not a deployed hybrid.
## Caps
As PREREG14. Retrieval hand on the VM (c-fuse-6). Briefs write only inside their lease.
