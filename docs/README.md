<!-- SPDX-License-Identifier: Apache-2.0 -->
# Documentation index

The website lives in this folder and is served by GitHub Pages at https://anshul48.github.io/trace/. Its pages are generated from [`source/`](source/) by `python3 tools/build_site.py`; do not edit the generated `index.html` files by hand.

## Checkable records

- [`receipts/`](../receipts/): the records of our runs (the folder is named *receipts*).
- [`receipts/earlier-runs/`](../receipts/earlier-runs/): the earlier builds and the build-memory runs.
- [`receipts/order-measure/`](../receipts/order-measure/): the measurement of how ordered the groups are.
- [`receipts/filed-summaries/`](../receipts/filed-summaries/README.md): two result summaries (head-to-head against standard indexes, append against rebuild); raw files not published.
- [Evidence and limits](https://anshul48.github.io/trace/evidence/): every number with its scope, the harder comparisons and the corrections.
- [Verify it yourself](https://anshul48.github.io/trace/verify/): what each check proves, and what it does not.

## Reproduce

- [REPRO.md](REPRO.md): reproduction commands and environment pins.
- [`reproduction/repro-20k/`](reproduction/repro-20k/README.md): a small reproduction for your own computer.
- [Try it](https://anshul48.github.io/trace/try/): five ways in, from a browser click to a Python run.
- [`tools/`](../tools/): `verify_freeze.py`, `check_receipts.py`, `check_links.py`, `build_site.py`, `run-trace.sh`.
- [README-technical.md](README-technical.md): the earlier full README, including how to reproduce a small run. Its links to the retired play, recording and future pages no longer work.

## Architecture

- [How it works](https://anshul48.github.io/trace/how-it-works/): the idea in plain words, with an animation.
- [ARCHITECTURE.md](ARCHITECTURE.md): the design, in technical terms.
- [CODE-TOUR.md](CODE-TOUR.md): a walk through the 207 tested files.
- [SCALE-AND-MEMORY.md](SCALE-AND-MEMORY.md): the earlier scale and build-memory runs, with their raw records.
- [../BENCHMARKS.md](../BENCHMARKS.md): every current number, with its scope and a line-level link to its record. Start here.
- [EXPLAINER.md](EXPLAINER.md): how TRACE works, in a 10-minute read.
- [FAQ.md](FAQ.md): the hard questions, answered with links to the records.
- [ROADMAP.md](ROADMAP.md): where the design is headed; design, not promises.
- [design/](design/README.md): five short design notes, each with its status, latest number and falsifier.
- [BENCHMARKS.md](BENCHMARKS.md): the measurement records of the earlier build.
- [BENCHMARKS-DEEP.md](BENCHMARKS-DEEP.md): in-depth benchmarks (recall, nDCG, abstention, RAM and CPU time, inside views), every number with its scope and record.

These technical documents were written for an earlier, smaller experiment. Their numbers can differ from the website's; where they differ, the website and the root README are current.

## Research notes

- [`vision/`](vision/index.html): vision and open questions.
- [META-USE.md](META-USE.md): which Meta products and models we used and did not use.
- [Reflex: early trial results](reflex.md): what Reflex is, and the numbers from the early trial (SAM 3.1 with Muse Spark).

## Status

- [`status.json`](status.json): every "Working today", "Prototype" and "Planned" badge, on the site and in the README. A capability may be `built` only if its `evidence` file exists (`tools/check_links.py` checks).
- [`demos/films.json`](demos/films.json): every film on the site, the swap list.
- [CHANGELOG.md](CHANGELOG.md): what changed, newest first.
- [TEST-REPORT.md](TEST-REPORT.md): the publication verification record.

## Contribute

- [Contributing](../.github/CONTRIBUTING.md): the rules for changing this repository.
- [ABOUT.md](ABOUT.md): the repository's description, topics and social preview, for the maintainer.

## Demos and films

- [Website: home](https://anshul48.github.io/trace/): what TRACE is, the measured result and the limits.
- [TRACE explorer](https://anshul48.github.io/trace/explorer/): replay of real recorded searches.
- [Demo videos](https://anshul48.github.io/trace/demos/): the story and the working cuts.
- [ANIMA on GitHub](https://github.com/Anshul48/anima-substrate): a separate project, a prototype memory link for coding agents.
- [ANIMA recorded demo](https://anshul48.github.io/anima-substrate/demo/): a recorded nine-job run, replayed in your browser.
- [Reflex replay](https://anshul48.github.io/demo-trace-anima-reflex/): a separate project, an AI that finds the right button. No login.

The three projects are described in [the README's ecosystem section](../README.md#the-ecosystem).
