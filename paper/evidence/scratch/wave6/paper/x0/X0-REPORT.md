# X0 REPORT — label-leak-free query set for the sealed 812,545-unit store (claude-sci, 2026-11-05 ~18:15Z; PREREG-X0 sha in PREREG-X0.sha256, frozen 15:23:37Z)

## VERDICT (literal): X0 SET VALID (n=555, DEV 167 / TEST 388)
Conditions (PREREG-X0 §Validity): n_final >= 300: 555. Independent re-lint (relint.py, own tokenizer and stopword list) on the frozen file: 0 six-gram copies. Doc ids unique: 555/555 (no duplicate doc, ordinal or query text). None of the 50 existing probes' docs: 0 overlap (probe ordinals mapped to doc_ids on the VM units file; 50 docs; none in the frozen set). Each shard 20-30 %: 25.2 / 25.2 / 24.7 / 24.9 %. FREEZE.txt (sha256 fab1d5e8996386520a0cb75c23b9f9f59f406245bb804d810fd0e60478a28b71, mtime 18:03:02Z) written before any retrieval was run on this set.
Tag: OBSERVED (my scripts, my reads). Files: queries_frozen.jsonl, FREEZE.txt, relint.py, X0-REPORT.md, AUDIT-30.md.

## Yields (reported, no verdict)
Stage: raw 600 -> lint round 1 accepted 399 (66.5 %; prereg expected 75-85 %) -> regeneration of the 201 rejected: 201/201 pass lint -> 600 lint-clean -> judge answerable=yes AND generic=no: 555 (92.5 %; prereg expected 85-95 %).
Per author hand (ids 0-199 / 200-399 / 400-599): lint-1 rejected 59 / 77 / 65; judge yes 185 / 185 / 185; final 185 / 185 / 185. (Equal counts by chance as far as I can tell: the 45 non-yes are 15 per hand with specific reasons in the judge's RESULT.md.)
Per style (0 question / 1 keyword / 2 description): lint-1 rejected 38 / 159 / 4; final 182 / 186 / 187. Keyword queries were the lint casualty (they name the passage's own entities), and 149 of the 186 keyword finals are regenerated rewrites. Judge outcome did not differ between rounds: 369/399 kept in round 1, 186/201 after regeneration (92.5 % both).
Judge counts: answerable yes 555 / partial 39 / no 6; generic yes 0 / no 600. The generic filter did NOT discriminate (the judge declared a deliberate all-no); treat 'not generic' as unchecked by the judge. The 6 'no' are degenerate source fragments (bare categories, blank tables).
Overlap (content tokens of the query that occur in the source), independent tokenizer: mean 0.464, p90 0.727, max 0.833 (ONE query exceeds 0.80 under this tokenizer, 0.50-0.60 under lint.py's; the verdict does not use overlap beyond the lint rule). Query length (words): mean 11.4, p10 7, p90 16.
Split: DEV 167 / TEST 388 (assigned at sampling).

## Limits (stated, not hidden)
- One model family authored and judged the queries (Muse); the judge is a plausibility filter, not human validation. A 30-query human audit sample is ready: AUDIT-30.md (seed 20261106); I offer it to the owner (about 10 minutes) - nothing in the verdict depends on it.
- Label = the source unit only. Other units (near-duplicate passages, other parts of the same article) may answer equally well, so any recall against these labels is a conservative lower bound, same as the 50 probes. Many sources are mid-article fragments with raw wiki markup.
- Keyword-style queries were rewritten to lower vocabulary overlap, so they are descriptive rather than literal keyword searches; BM25 has less lexical advantage on this set than on the 50 probes by design. Whether that is fair to BM25 is part of what the hybrid experiments must report (arms on the same set, per style).
- No retrieval has been run. Next: baseline arms (dense HNSW / BM25 / guided) on the frozen set under a new preregistration, per style and per split (DEV for any tuning, TEST once).
