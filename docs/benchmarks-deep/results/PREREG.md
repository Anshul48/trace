# PREREG — 20k routing / abstention / cost measurements

Written BEFORE running. All commands: stdlib `python3` only, `nice -n 19`,
each under 10 min, wrapped in `/usr/bin/time -v`. Seeds fixed below.
Results reported exactly as obtained, including weak ones.

## Dataset decision (recorded before measuring)

No public retrieval set was available to this job (its data was gone and no
network fetch was allowed). Per the fallback, Step 2 uses the repo's own 20k
reproduction set, read-only:

- Vectors: `../../reproduction/repro-20k/data-20k/emb_cache/` — 144 FP32
  vectors, dim 384, `sentence-transformers/all-MiniLM-L6-v2`, unnormalized
  (cosine normalizes at scoring, per repo PROTOCOL.md).
- Group tree: `../../explorer/local_20k_data.json` — the REAL tree from the
  frozen 20k run: 51 parents, 81 leaves, 144 atoms. Atom->row join on
  `chunk_sha256`; the run script asserts 144/144 join or aborts.
- Scope label on every new number: "20k prefix, 144 atoms, 88 docs,
  passages-as-queries". NOT a relevance benchmark: there are no human
  judgments. All quality numbers below are self-retrieval or fidelity to
  exact search, labeled as such.

## (a) Routing vs brute-force baseline

- Baseline (EXACT): brute-force cosine top-10/top-100 over the 144 vectors.
- Routed (LEAF, primary): score query against 81 leaf centroids (mean of
  member vectors, cosine), open top-L leaves, score member atoms only.
  Budgets L in {1,2,4,8,16,81}. L=81 must equal EXACT (sanity check).
- Routed (PARENT, secondary): score 51 parent centroids, open top-P parents,
  score all atoms under them. Budgets P in {1,2,4,8,51}.
- Queries: all 144 atoms as queries (self present in library).
- Metrics per budget: recall@10 = |routed top-10 cap exact top-10| / 10;
  recall@100 (k=100 over 144 rows); self-nDCG@10 (gain 1 for the query's own
  atom, 0 else; standard log2 discount, IDCG = 1.0); fidelity-nDCG@10
  (gains from EXACT ranking: gain 11-rank for exact top-10, 0 else);
  mean passages scored + mean incl. routing rows (centroids + atoms).
- Timing: perf_counter per query for EXACT and each budget; process peak RSS
  via resource.ru_maxrss + /usr/bin/time -v "Maximum resident set size".

## (b) ABSTENTION (first ever; strict self-match criterion, pessimistic by design)

- Answerable queries (144): atom vectors with self PRESENT; correct = top-1
  is the query's own atom, answered by EXACT top-1.
- Unanswerable queries (192): (i) 144 same vectors with self REMOVED from
  the library (nearest neighbour is the closest other atom); (ii) 48
  seeded Gaussian noise queries (seed 7, dim 384, normalized). Any answer
  to an unanswerable query counts as a FALSE ANSWER (strict: neighbour
  similarity is not credit — this is deliberately pessimistic and labeled).
- Signals: s1 = top-1 cosine score; s2 = margin = top-1 minus top-2.
- Rule: answer iff signal >= threshold, else abstain ("I don't know").
- Preregistered thresholds (chosen blind, before seeing scores):
  s1 in {0.85, 0.95, 0.99}; s2 in {0.02, 0.10, 0.25}.
- Reported at each of the 6 settings: coverage (answered/total over all 336
  queries), precision on answered (correct/answered), false-answer rate
  (incorrect answers/total queries). Plus the FULL risk-coverage curve:
  all distinct thresholds swept per signal, one row per threshold.
- Honest limits (preregistered): n=336 synthetic queries; unanswerable set
  is constructed, not real user questions; noise queries are trivially
  separable and flatter the curve — the held-out half is the harder test,
  so the curve is reported split (held-out vs noise) as well as pooled.

## (c) RAM and CPU/wall per query and per build step

- Build steps timed separately: load vectors, load tree JSON, build 81 leaf
  centroids + 51 parent centroids, join check.
- Per-query wall for EXACT and LEAF budgets; per-query rows scored.
- Whole-run /usr/bin/time -v log kept (wall + max RSS).

## Reproducibility

- Seeds: noise queries seed 7; no other randomness (deterministic data,
  deterministic centroids, ties broken by atom id ascending — preregistered
  tie rule).
- Scripts + commands + versions in `../REPRODUCE-DEEP.md`; raw JSON + logs
  in this directory.
