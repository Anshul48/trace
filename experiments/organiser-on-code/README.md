<!-- SPDX-License-Identifier: Apache-2.0 -->
# organiser-on-code

Group Python functions and methods by their module, and compare a
streaming organiser (never told the number of groups) against baselines
that are told it. Two modes, one command each, standard library only.

## What it shows

Six standard-library packages (`logging`, `multiprocessing`, `wsgiref`,
`asyncio`, `xml`, `http`) are cut into atoms: one atom per top-level
function or per direct method of a top-level class, 3-200 lines.
Five fixed draws (seeds 61-65) take 4 packages x 3 modules x 15 atoms =
180 atoms each. Every draw is scored on module labels (12 modules):

- organiser v1, not told K (streaming average-link over unit directions,
  data-chosen distance threshold, closest-pair merges)
- k-means, told 12 (k-means++, 10 restarts, cosine distance)
- average-link agglomeration, told 12
- equal-size random partition into 12

The table reports per-seed module ARI, purity and the organiser's group
count, plus the mean row.

Result: the organiser scores below k-means told the number of groups in
both modes (0.228 against 0.245 with the one command; 0.265 against
0.295 with the precomputed vectors).

## The one command

From this directory:

```
python3 -I run.py
```

This builds TF-IDF vectors over identifier tokens from the running
interpreter's own standard library, then prints the table (about a
minute on a laptop; progress goes to stderr, the table to stdout).

`EXPECTED_OUTPUT.txt` is the real output on CPython 3.12.3. Numbers
vary by Python version because the standard-library text differs; the
shape (five draws, organiser untold vs baselines told 12) does not.

## Precomputed-vectors mode

The vectors file is not published yet, so this mode cannot be run from this repo today. `EXPECTED_OUTPUT_vectors.txt` is the recorded output of the run described below.

Python-only code cannot recompute MiniLM vectors, so the measured table
is kept as a small sidecar asset (NOT in this directory): 2250 atoms x
384 dims, float32, with the id list and package/module labels:

```
python3 -I run.py --vectors <path-to>/code-vectors-f32.bin
```

This reads only the asset file: it never touches the standard library.
`EXPECTED_OUTPUT_vectors.txt` is the real output. Mean module ARI over
seeds 61-65: organiser 0.265, k-means-12 0.295, avg-link-12 0.210,
random-12 -0.003. The float32 asset reproduces the float64 measurements
exactly at the printed precision.

Asset layout: 8-byte magic `ORGCODE1`, u32 LE count, dim and JSON-header
length, a JSON directory `{format, model, revision, count, dim, ids,
labels}` (vectors in `ids` order, `labels` maps id to
`[package, module]`), then count*dim float32 little-endian values.
Model: `sentence-transformers/all-MiniLM-L6-v2`, unit-normalised.

## Files

- `build_corpus.py` -- atoms from the running interpreter's stdlib
- `tfidf.py` -- identifier-token TF-IDF vectors (sparse + densify)
- `organiser_v1.py` -- the organiser kernel (three streaming levels)
- `baselines.py` -- k-means (dense/sparse), average-link, random, metrics
- `run.py` -- draws, scoring, both modes, the table
- `tests/test_smoke.py` -- fast hermetic checks (`python3 -W
  error::ResourceWarning -m unittest tests.test_smoke`, under 10 s)

## What it does NOT show

- Five draws, one shape: seeds 61-65 only; nothing is claimed about
  other seeds, other draw sizes, or other corpora.
- Development packages only: the six packages above; other packages
  were never built into a corpus here and none is evaluated.
- Told-K baselines: k-means and average-link are given the answer's
  size (12 groups) and the organiser is not; the organiser still
  scores below k-means.
- 18-23 groups for 12 modules: on the measured (vectors) table the
  organiser returns 18-23 level-1 groups per draw where the truth has
  12 modules; it over-splits.
- Package level unsolved: grouping the 12 modules into their 4
  packages is not scored here; the organiser's upper levels are
  reported as group counts only inside the kernel state.
- No held-out: every number above is on the development packages;
  there is no held-out evaluation anywhere in this package.

## Reproducibility

Output is byte-deterministic: no timings, no paths, fixed formatting.
Copy this directory anywhere and run either command twice; both runs
are byte-identical to each other and to the matching EXPECTED file
(on the same interpreter for the default mode).

License: Apache-2.0 (see the SPDX line atop every source file).
