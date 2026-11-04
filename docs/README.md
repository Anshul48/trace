<!-- SPDX-License-Identifier: Apache-2.0 -->
# Documentation index

The website lives in this folder and is served by GitHub Pages at https://anshul48.github.io/trace/. Its pages are generated from [`../docs-src/`](../docs-src/) by `python3 tools/build_site.py`; do not edit the generated `index.html` files by hand.

## Read first

| | |
|---|---|
| [Website: home](https://anshul48.github.io/trace/) | What TRACE is, the scale ladder, the measured result and the limits. |
| [Try it](https://anshul48.github.io/trace/try/) | Five ways in, from a browser click to a Python run. |
| [How it works](https://anshul48.github.io/trace/how-it-works/) | The idea in plain words, with an animation. |
| [Evidence and limits](https://anshul48.github.io/trace/evidence/) | Every number with its scope, the harder comparisons, the earlier larger tests, the corrections. |
| [Verify it yourself](https://anshul48.github.io/trace/verify/) | What each check proves, and what it does not. |
| [META-USE.md](META-USE.md) | Which Meta products and models we used and did not use. |

## Machine-readable files the site is built from

| File | What it decides |
|---|---|
| [`status.json`](status.json) | Every "Working today", "Prototype" and "Not built yet" badge, on the site and in the README. A capability may be `built` only if its `evidence` file exists (`tools/check_links.py` checks). |
| [`demos/films.json`](demos/films.json) | Every film on the site: the swap list. Set `youtube` on the `main` entry to publish the 3-minute film. |

## Technical record

These documents were written for an earlier, smaller experiment (a 10-million-token build and its qualification run). Their numbers can differ from the website's; where they differ, the website and the root README are current. They are kept because the records they cite are real.

| Document | What it is |
|---|---|
| [README-technical.md](README-technical.md) | The earlier full README, including how to reproduce a small run on your own computer. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | The design, in technical terms. |
| [BENCHMARKS.md](BENCHMARKS.md) | The measurement records of the earlier build. |
| [REPRO.md](REPRO.md) | Reproduction commands and environment pins. |
| [CODE-TOUR.md](CODE-TOUR.md) | A walk through the 207 tested files. |
| [SCALE-AND-MEMORY.md](SCALE-AND-MEMORY.md) | The earlier scale and build-memory runs, with their raw records. |
| [ABOUT.md](ABOUT.md) | The repository's description, topics and social preview, for the maintainer. |

## Records and tools

- [`../receipts/`](../receipts/): the records of our runs (the folder is named *receipts*): `earlier-runs/` (the 504.5M and 310.5M builds and the build-memory runs), `order-measure/` (the measurement of how ordered the groups are).
- [`../tools/`](../tools/): `verify_freeze.py`, `check_receipts.py`, `check_links.py`, `build_site.py`, `run-trace.sh`.
- [`../repro-20k/`](../repro-20k/README.md): a small reproduction for your own computer.
