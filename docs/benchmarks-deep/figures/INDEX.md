# Figure index (one page)

All figures are self-contained SVG (no external fetch; the only URL is the
required SVG namespace). Each is labeled REAL RUN or RECORDED-DATA and cites
its receipt in its caption. Generator: [`gen_figures.py`](gen_figures.py)
(stdlib only; run it from anywhere — it resolves the repo root from its own
location). Each SVG ships with a same-name `.png` preview (prebuilt rendering
of the SVG). Used by [`../../BENCHMARKS-DEEP.md`](../../BENCHMARKS-DEEP.md)
as `![alt](benchmarks-deep/figures/x.svg)`.

| Figure | Kind | What it shows | Receipt |
|---|---|---|---|
| [`tree-route.svg`](tree-route.svg) | REAL RUN | The 20k group tree (81 leaves) with query atom #0's route lit at leaf budget 8: 8 opened leaves, 16 atoms scored, recall@10 0.90 | tree [`../../explorer/local_20k_data.json`](../../explorer/local_20k_data.json); route [`../results/run_20k.json`](../results/run_20k.json) |
| [`scored-fraction.svg`](scored-fraction.svg) | REAL RUN | Per-query scored fraction at leaf budget 8: one bar per each of 144 atom-queries, mean 14.8 rows (10.30%); y-axis 0-15% | [`../results/run_20k.json`](../results/run_20k.json) routing.leaf_L8.per_query |
| [`abstention-curve.svg`](abstention-curve.svg) | REAL RUN | Risk-coverage: false-answer rate vs coverage for top-1-score and margin signals over 336 synthetic queries; preregistered points marked | [`../results/run_20k.json`](../results/run_20k.json) abstention_curves + abstention_prereg |
| [`ram-build.svg`](ram-build.svg) | mixed, labeled per bar | Log-scale build-memory peaks only: this job 23.9 MiB REAL; 20k pilot 136.6, seam12a 8489.1, G5 22565.5 MiB RECORDED | per-bar source printed on the bar; scopes in caption |
| [`per-query-time.svg`](per-query-time.svg) | mixed, labeled per bar | Log-scale per-query times only: this job exact 4.63 / leaf-8 2.67 ms REAL; BEIR FiQA 9.883 / 0.742 ms, replay p50 1198.8 / 1288.1 ms RECORDED | per-bar source printed on the bar; scopes in caption |
