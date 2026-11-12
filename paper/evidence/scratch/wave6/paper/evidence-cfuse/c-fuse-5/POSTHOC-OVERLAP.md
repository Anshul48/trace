# POST-HOC query-level overlap analysis (claude-sci, 2026-11-06 ~04:20Z; specified after seeing the data; exploratory, not preregistered)
Sets with local raw lists: XG (297), X2M (300), X2H (300); 897 queries pooled. Overlap = lint.py content-word overlap of query with its source passage. Split at overlap 0.45. Gain = hit@10(MMr) - hit@10(Dr) per query.
Per set, gain for overlap <0.45 vs >=0.45: XG +0.052 vs +0.110; X2M +0.000 vs +0.048; X2H -0.022 vs +0.117.
Pooled difference (high minus low): +0.087 [0.051,0.124] (5,000 query-level bootstrap resamples, rng 1; queries from X2M and X2H share passages, so resamples are not independent; high-overlap queries are also easier for both arms: Dr hit 0.87 vs 0.22 in the extreme bins).
Reading: within every author, the fusion gain is larger on higher-overlap queries. Consistent with overlap, not author, as the covariate; exploratory only, ceiling effects and non-independence not handled; X0/XF raw lists not local.
