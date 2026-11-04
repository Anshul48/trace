<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- GENERATED from docs-src/README.src.md by tools/build_site.py. Edit the source, then run: python3 tools/build_site.py -->
# TRACE: a memory that organizes itself

**TRACE is a research-prototype memory for AI systems. It sorts a growing library into groups from the passages themselves, so a question wakes only a small part of it, and every answer carries a record you can check.** It is for people who need answers they can verify, and for AI agents that need a memory they can audit. Open source, Apache-2.0.

| In 60 seconds | |
|---|---|
| **Try it** | **[Open the explorer](https://anshul48.github.io/trace/explorer/)**: a replay of 144 real searches that were recorded on our server. Nothing to install. Open a result's record and press "Check the fingerprint in my browser". |
| **The measured result** | On our library of 812,545 passages, a question scored **0.79% of the rows on one of four equal parts** (about **127 times less scoring work**) and kept **0.9985** of exact search's top ten. 50 test searches, our library and our method. |
| **The honest limits** | Ordinary keyword search found the right source more often than TRACE did (82% against 52%), a plain scan takes less time per search, and nobody outside our team has checked the results. [All the limits](#honest-limits). |
| **Meta tooling** | Muse Code was our main automated worker tool (670 recorded jobs). TRACE's search itself uses no Meta model. [What we used and did not use](docs/META-USE.md). |
| **The 3-minute film** | Being published on YouTube; the link will be added here. Until then: [working versions of the films](https://anshul48.github.io/trace/demos/). |

[Website](https://anshul48.github.io/trace/) · [How it works](https://anshul48.github.io/trace/how-it-works/) · [Evidence and limits](https://anshul48.github.io/trace/evidence/) · [Verify it yourself](https://anshul48.github.io/trace/verify/) · [Meta tooling](docs/META-USE.md)

<p align="center">
  <img src="docs/img/organizing-pile.png" alt="Illustration: 20,000 dots in four equal parts, sorted into groups. In the first part a question has lit 40 dots, with ten ringed as the best matches. All other dots are dim." width="100%">
</p>

*An illustration, not data: 20,000 dots stand in for the 812,545 passages. Where each dot sits and how many groups there are is drawn. What is real is the proportion: four equal parts, and a question waking 0.79% of one of them. The [website](https://anshul48.github.io/trace/how-it-works/) animates it.*

## The idea in three beats

1. **It sorts itself.** Passages that mean alike end up in the same group, and nobody adds labels. In our tests, a search's ten true best matches fall into about 7 groups on average, out of at most 10; groups made at random would give 10. *Scope:* 50 test searches, our library, one ordinary sorting run. We measured how ordered the finished groups are, not how they formed over time, and we have no growth curve yet.
2. **A question wakes a small part.** Only the groups most likely to hold the answer are searched: 0.79% of the rows on one of four equal parts, about 127 times less scoring work, with 0.9985 of exact search's top ten kept. This is what we call *sparse activation*, inspired by the idea that only a small part of a memory fires for a given cue. It is not a claim of being faster: see the limits.
3. **Every answer has a checkable record.** Each result shows its article, where in the article, its licence and a fingerprint (SHA-256) that your browser recomputes from the exact text. A match proves the text is what was sealed in the library. It does not prove the search found the best passage.

## How far it has been tested

| Size | Status | What was done | Caveats |
|---|---|---|---|
| **99.9M tokens** (812,545 passages) | ![Working today, our server](docs/badges/library-100m.svg) | The full measured pipeline: sorted into groups, searched, every answer with a checkable record, re-run on our own server. | Short of our 100M target by 0.11% (108,154 tokens). Our own library and method, not reproduced on public data, no outside check. |
| **310.5M tokens**, 8 pieces | ![Earlier test](docs/badges/build-310m.svg) | Exact search matched the ground truth. With one piece switched off it still found 0.87 of the exact results, with no wrong passages. | Earlier test, by us. Our own records. The cloud machine was shut down, so it cannot be re-run. A search took p50 4.18 s. [Raw record](receipts/earlier-runs/RECEIPT-RUNG-300M.txt). |
| **504.5M tokens**, 13 pieces (7.65 GB) | ![Earlier test](docs/badges/build-504m.svg) | Exact search matched the ground truth. With one piece switched off it still found 0.885 of the exact results, with no wrong passages. | Earlier test, by us. Our own records, not outside-verified, cannot be re-run, not served at that size. The compressed-search figure (0.994 to 0.998) was measured only on the five newest pieces. A 13-piece search took p50 6.86 s. [Raw record](receipts/earlier-runs/RECEIPT-RUNG-500M.txt). |
| **1.53B tokens**, 7.13M vectors | ![Separate test](docs/badges/routing-1b.svg) | A separate October test of group-picking only: opening 6.6% of the vectors kept 0.9947 of the exact top ten. | A different, larger collection. Not served through TRACE, no checkable records at that size, no billion-vector run. We have not run a billion tokens through TRACE. |

A token is a word-sized piece of text; a "piece" is one sealed part of a library. The details and the cost to build are on the [evidence page](https://anshul48.github.io/trace/evidence/).

## Try it, and check it

- **No install:** the [explorer](https://anshul48.github.io/trace/explorer/) in your browser. ![Working today](docs/badges/explorer-replay.svg) ![Working today](docs/badges/record-check.svg)
- **Run the explorer on your own computer** (Python 3, downloads nothing): `./tools/run-trace.sh` (Windows: `tools\run-trace.bat`). ![Working today](docs/badges/explorer-local.svg)
- **Check that the published code is the code we tested** (207 files): `python3 tools/verify_freeze.py` should end with `entries=207 ok=207 missing=0 mismatch=0`. ![Working today](docs/badges/freeze-verify.svg)
- **Run a small reproduction** (20,000 tokens, needs `numpy` and `blake3`): see [`repro-20k/README.md`](repro-20k/README.md). ![Working today](docs/badges/small-repro.svg)
- **What you cannot do yet:** query the whole library yourself, or download it. ![Not built yet](docs/badges/public-service.svg) ![Not built yet](docs/badges/local-kit.svg) Nobody outside our team has re-run our results. ![Not built yet](docs/badges/outside-check.svg)

## Honest limits

1. **Ordinary keyword search finds the source more often.** On our 50 test searches (40 written questions and 10 taken from passage openings) it put the right source passage in its top ten for 82% of them. TRACE did for 52%, and exact search by meaning also got 52%, so the gap is meaning versus keywords, not our shortcut. TRACE is for search by meaning that you can check, not a replacement for keyword search.
2. **A plain scan takes less time, and our stored size on disk is bigger.** Per search: keyword 6 ms, exact scan 88 ms, TRACE 1.2 s. Stored size on disk: 2.28 GB for TRACE, 1.25 GB for plain vectors, 0.51 GB for the keyword index. We have no like-for-like measure of memory in use. The one memory figure we measured is the live service's peak, 1.03 GiB, while answering the 50 test questions. We claim no speed or space advantage.
3. **The headline result is for our own library and method.** TRACE itself has not been run on public benchmarks. A simple stand-in of ours (not TRACE) on three small public sets needed 7% to 28% of passages scored to keep about 95% of exact search's top ten. So 0.79% at 0.9985 is not reproduced on public data.
4. **The groups come from an ordinary sorting step**, one run per quarter of the library. We measured how ordered the finished groups are (about 7 of at most 10 for a search's best matches, and 7.8 if passages are simply kept in arrival order), not how they formed. We make no claim about order at millions or billions of passages.
5. **Scale is not as far as it may sound.** We missed our 100M target by 0.11%. The 504.5M and 310.5M builds are earlier tests by us on a machine since shut down. The 1.53 billion item is a separate group-picking test.
6. **Nobody outside our team has checked these results.**
7. **No live public service, and no download yet.** The explorer is a replay of real recorded searches. A public backend was switched off after it failed its first test with many users.

## Where each thing stands

Generated from [`docs/status.json`](docs/status.json), the one file that also drives every badge on the website. A capability is marked "Working today" only if its evidence file exists in this repository.

| Capability | Status |
|---|---|
| Explorer: replay of 144 real recorded searches, each result with a checkable record | ![Working today](docs/badges/explorer-replay.svg) |
| Check a record in your own browser (the fingerprint is recomputed there) | ![Working today](docs/badges/record-check.svg) |
| Run the explorer on your own computer with Python 3 (tools/run-trace.sh) | ![Working today](docs/badges/explorer-local.svg) |
| A 100M-class sealed library (812,545 passages, 99,891,846 tokens), sorted into groups and searched on our own server | ![Working today, our server](docs/badges/library-100m.svg) |
| A question scores 0.79% of one of four equal parts and keeps 0.9985 of exact search's top ten (50 test searches, our library and method) | ![Measured by us](docs/badges/sparse-search.svg) |
| The finished groups hold a search's best matches together: about 7 groups out of at most 10, against 10 for random groups | ![Measured by us](docs/badges/groups-hold-matches.svg) |
| A small reproduction (20,000 tokens) that runs on your own computer | ![Working today](docs/badges/small-repro.svg) |
| Check that the published code is byte-for-byte what was tested (207 files) | ![Working today](docs/badges/freeze-verify.svg) |
| TRACE's own filing-and-repair store, with the records of an earlier qualification run (receipts/) | ![Prototype](docs/badges/self-organizing-store.svg) |
| Earlier build: 310,532,353 tokens in 8 pieces (our records, machine shut down) | ![Earlier test](docs/badges/build-310m.svg) |
| Earlier build: 504,480,146 tokens in 13 pieces (our records, machine shut down) | ![Earlier test](docs/badges/build-504m.svg) |
| Separate October test: 1,531,809,092 tokens encoded into 7,134,906 vectors, group-picking only | ![Separate test](docs/badges/routing-1b.svg) |
| TRACE as the shared memory for ANIMA coding agents | ![Prototype](docs/badges/anima-link.svg) |
| Reflex: a separate prototype that lets an assistant use a real web page | ![Prototype](docs/badges/reflex.svg) |
| A before-and-after measurement of the library's order as it grows | ![Not built yet](docs/badges/growth-curve.svg) |
| A public live service anyone can query | ![Not built yet](docs/badges/public-service.svg) |
| A download you run on your own computer for the whole library | ![Not built yet](docs/badges/local-kit.svg) |
| TRACE itself run on public benchmarks (BEIR) | ![Not built yet](docs/badges/public-benchmarks.svg) |
| Results checked by an outside party | ![Not built yet](docs/badges/outside-check.svg) |
| A billion tokens through TRACE, searchable, with checkable records | ![Not built yet](docs/badges/billion-run.svg) |
| The 3-minute film on YouTube | ![Not built yet](docs/badges/film-youtube.svg) |

## Also by this team

- **[ANIMA](https://github.com/Anshul48/anima-substrate)** ![Prototype](docs/badges/anima-link.svg): a harness around AI coding agents, with a hidden checker no agent can see, a ladder of helpers and a recorded chain of decisions. TRACE is its shared memory through a prototype link. Validated for one kind of job so far (fixing a bug against hidden tests).
- **Reflex** ![Prototype](docs/badges/reflex.svg): a separate prototype that lets an assistant use a real web page by reading the page's structure first. It has [its own short film](https://anshul48.github.io/trace/demos/#reflex).

## Where things are

| | |
|---|---|
| [`docs/`](docs/README.md) | The website, served by GitHub Pages, and the technical documents (see [`docs/README.md`](docs/README.md) for the index). |
| [`docs-src/`](docs-src/) | The sources the website is generated from (`python3 tools/build_site.py`). |
| [`freeze-src/`](freeze-src/) | The tested engine, 207 files. |
| [`receipts/`](receipts/) | The records of our runs (the folder is named *receipts*): the qualification run, the earlier larger builds, the order measurement. |
| [`repro-20k/`](repro-20k/README.md) | A small reproduction for your own computer. |
| [`tools/`](tools/) | The checks, the site generator and the local launcher. |
| [`archive/`](archive/README.md) | Earlier pages and notes, kept for the record. |

## Contributing, security, citation

[CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) · [CITATION.cff](CITATION.cff) · [CHANGELOG.md](CHANGELOG.md) · [Meta tooling used](docs/META-USE.md) · Questions or problems: [open an issue](https://github.com/Anshul48/trace/issues). License: Apache-2.0 ([LICENSE](LICENSE)). Passages in the library are English Wikipedia text under CC BY-SA 4.0.
