<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- GENERATED from docs/source/README.src.md by tools/build_site.py. Edit the source, then run: python3 tools/build_site.py -->
# TRACE: a memory that organizes itself

**Self-organizing memory prototype; demonstrated result: routed vector retrieval kept 0.9985 of exact top-ten results while scoring 0.79% of passages (50 test searches, one of four equal library parts).** TRACE sorts a growing library into groups from the passages themselves, so a question wakes only a small part of it, and every answer carries a record you can check. If you use an AI agent every day, you know it forgets. TRACE is an early answer: a memory an agent can search and check. Today it is a prototype you can try as a recorded replay, in your browser. Open source, Apache-2.0.

**Try it now: [open the explorer](https://anshul48.github.io/trace/explorer/) — a replay of 144 real recorded searches. Nothing to install.**

**Why it matters.** AI agents forget. The documents pile up and nobody files them. TRACE is the memory that sorts itself: the right passage at the right time, each with a record you can check.

## The library

**A 100M-token library (812,545 passages · 99.9 million tokens).** The library is fixed: every number here comes from the same frozen library, and every result carries a fingerprint your browser can re-check. Frozen engine: 207 files verified (`python3 tools/verify_freeze.py`). Measured on 50 test searches, one of four equal parts. Short of our 100M target by 0.11% (108,154 tokens).

<p align="center">
  <img src="docs/assets/library.svg" alt="A field of dots in four equal parts: a 100M-token library, frozen." width="640">
</p>

## The ecosystem

One builder, three projects. TRACE is at the front: the memory the other two are built to use. ANIMA and Reflex stand behind it, each with its own demo. The owner's profile is calibrated as a map of these projects: [github.com/Anshul48](https://github.com/Anshul48).

<p align="center">
  <img src="docs/assets/ecosystem.svg" alt="Diagram: TRACE in front as the memory, ANIMA and Reflex behind it, with lines from each to TRACE." width="640">
</p>

### TRACE: the memory, at the front

TRACE is a memory that sorts a huge pile of text into groups by itself, so a question opens only the few groups it needs, and every result comes with a record you can check. It is the vanguard of this ecosystem: the part the other two build on.

**Watch the demo:** [open the TRACE explorer](https://anshul48.github.io/trace/explorer/), a replay of 144 real recorded searches. Nothing to install.

### ANIMA: coding agents that remember

ANIMA is a layer that sits on top of the coding agent you already use (Muse Code first, then Claude Code, Codex), giving it memory, a checker it cannot see, and a screen to watch it work. Its memory is TRACE, joined by a prototype link with one small recorded test so far.

**Watch the demo:** [check ANIMA's record in your browser](https://anshul48.github.io/anima-substrate/demo/), a replay of a recorded nine-job run. [ANIMA on GitHub](https://github.com/Anshul48/anima-substrate).

### Reflex: an AI that finds the right button

Reflex is a line of work where an AI looks at a screen and finds the right button to press. The direction is SAM 3.1 with Muse Spark: in the early trial, SAM 3.1 cut made-up screens into pieces and Muse Spark read them and chose — an early trial, a direction, with small synthetic tests so far.

**Watch the demo:** [open the replay demo](https://anshul48.github.io/demo-trace-anima-reflex/) (no login, pick the Reflex sample) or [watch the short film](https://anshul48.github.io/trace/demos/#reflex). [Early trial results](docs/reflex.md).

{{statusline}}

| In 60 seconds | |
|---|---|
| **Try it** | **[Open the explorer](https://anshul48.github.io/trace/explorer/)**: a replay of 144 real searches that were recorded on our server. Nothing to install. Open a result's record and press "Check the fingerprint in my browser". |
| **The measured result** | On our library of 812,545 passages, a question scored **0.79% of the passages on one of four equal parts** (about **127 times less passage-scoring work**) and kept **0.9985** of exact vector search's top ten. 50 test searches, our library and our method. It measures how much of the exact answer was kept, not answer quality. |
| **The honest limits** | Ordinary keyword search found the right source more often than TRACE did (82% against 52%), a plain scan takes less time per search, and nobody outside our team has checked the results. [All the limits](#honest-limits). |
| **Meta tooling** | Muse Code was our main automated worker tool (670 recorded jobs). TRACE's search itself uses no Meta model. [What we used and did not use](docs/META-USE.md). |
| **The 3-minute film** | {{film}} |

[Website](https://anshul48.github.io/trace/) · [How it works](https://anshul48.github.io/trace/how-it-works/) · [Evidence and limits](https://anshul48.github.io/trace/evidence/) · [Verify it yourself](https://anshul48.github.io/trace/verify/) · [Meta tooling](docs/META-USE.md)

<p align="center">
  <img src="docs/img/organizing-pile.png" alt="Illustration: 20,000 dots in four equal parts, sorted into groups. In the first part a question has lit 40 dots, with ten ringed as the best matches. All other dots are dim." width="100%">
</p>

*An illustration, not data: 20,000 dots stand in for the 812,545 passages. Where each dot sits and how many groups there are is drawn. What is real is the proportion: four equal parts, and a question waking 0.79% of one of them. The [website](https://anshul48.github.io/trace/how-it-works/) animates it.*

## The idea in three beats

1. **It sorts itself.** Passages that mean alike end up in the same group, and nobody adds labels. In our tests, a search's ten true best matches fall into about 7 groups on average, out of at most 10; groups made at random would give 10. *Scope:* 50 test searches, our library, one ordinary sorting run. We measured how ordered the finished groups are, not how they formed over time, and we have no growth curve yet.
2. **A question wakes a small part.** Only the groups most likely to hold the answer are searched: 0.79% of the passages on one of four equal parts, about 127 times less passage-scoring work (routing and building the groups are separate costs), with 0.9985 of exact vector search's top ten kept. This is what we call *sparse activation*, inspired by the idea that only a small part of a memory fires for a given cue. It is not a claim of being faster: see the limits.
3. **Every answer has a checkable record.** Each result shows its article, where in the article, its licence and a fingerprint (SHA-256) that your browser recomputes from the exact text. A match proves the text is what was sealed in the library. It does not prove the search found the best passage.

## How far it has been tested

| Size | Status | What was done | Caveats |
|---|---|---|---|
| **100M-token library** (812,545 passages · 99.9M) | {{badge:library-100m}} | The full measured pipeline: sorted into groups, searched, every answer with a checkable record, re-run on our own server. Every number above is from this library. | Short of our 100M target by 0.11% (108,154 tokens). Our own library and method, not reproduced on public data, no outside check. |

Larger builds were earlier tests, shown separately under [Appendix: earlier tests](#appendix-earlier-tests-by-us) and never to be read together with the result above. A token is a word-sized piece of text. The details are on the [evidence page](https://anshul48.github.io/trace/evidence/).

## What a skeptic asks

- **Does it find the right source?** Not as often as keyword search. On our 50 test searches, ordinary keyword search put the right source in its top ten for 82% of them; TRACE and exact search by meaning each reached 52%. The 0.9985 measures how much of exact vector search's answer TRACE kept, not answer quality.
- **Does a matching fingerprint prove nothing relevant was skipped?** No. It proves the passage you were shown is the one that was stored, with its article and position. Whether the shortcut skipped something relevant is a different question, and the comparison with exact search measures it (0.9985 of the top ten kept).
- **Is 0.79% the whole cost?** No. It counts passage-scoring work only. A TRACE search took 1.2 s against 88 ms for an exact scan and 6 ms for keyword search.
- **Is the saving from self-organization, or from ordinary grouping?** We have not separated the two inside TRACE's own engine. We measured how ordered the finished groups are, not how they formed, and the order we measured showed up at every size we tested (10,000 to 200,000 passages in a controlled check, a flat band with no trend). We do not claim it improves with scale.
- **Does it work on public data?** TRACE has not been run there. A stand-in of ours (not TRACE) gave dataset-specific results: FiQA about 95% of exact search's top ten at 7% of passages scored, SciFact about 95% at 24%, NFCorpus 90% at 28% and 97% at 55%.
- **Has anyone outside your team checked it?** No. Outside verification is pending. What you can check yourself is under [Try it, and check it](#try-it-and-check-it).

## Questions judges ask

- **What does 0.79% mean?** For one question, TRACE read closely and ranked only 0.79% of the passages on one quarter of the library — about 127 times less passage-scoring work than scoring everything — and kept 0.9985 of exact search's top ten. It counts scoring work only, not the whole search.
- **Is this a live service?** No. The explorer replays 144 searches recorded on our server. The public backend is off, and a download you run yourself is planned.
- **How do I open the explorer?** [Click here](https://anshul48.github.io/trace/explorer/) — nothing to install. Or run it on your own computer: `git clone https://github.com/Anshul48/trace.git`, then `cd trace`, then `./tools/run-trace.sh` (Windows: `tools\run-trace.bat`).

## Try it, and check it

- **No install:** the [explorer](https://anshul48.github.io/trace/explorer/) in your browser. {{badge:explorer-replay}} {{badge:record-check}}
- **Run the explorer on your own computer** (Python 3, downloads nothing): `./tools/run-trace.sh` (Windows: `tools\run-trace.bat`). {{badge:explorer-local}}
- **Check that the published code is the code we tested** (207 files): `python3 tools/verify_freeze.py` should end with `entries=207 ok=207 missing=0 mismatch=0`. {{badge:freeze-verify}}
- **Run a small reproduction** (20,000 tokens, needs `numpy` and `blake3`): see [`repro-20k/README.md`](docs/reproduction/repro-20k/README.md). {{badge:small-repro}}
- **Planned:** query the whole library yourself, or download it. {{badge:public-service}} {{badge:local-kit}} Nobody outside our team has re-run our results. {{badge:outside-check}}

## Honest limits

1. **Keyword search finds the source more often, and a plain scan answers sooner.** On our 50 test searches the right source was in keyword search's top ten for 82% of them, against 52% for TRACE. Per search: 6 ms keyword, 88 ms exact scan, 1.2 s TRACE. TRACE is meaning-based search you can check, not a keyword replacement.
2. **Our library, our method.** 0.79% at 0.9985 is not reproduced on public data, and no outside party has checked our results.
3. **Ordinary grouping under the hood.** One sorting run per quarter of the library. The order was present at every size we checked (10,000 to 200,000 passages in a controlled check; the largest set we sorted holds 233,000 passages), with no claim it improves as the library grows.
4. **A replay, not a live service.** The explorer replays recorded searches. The public backend is off and the download is planned.

*Each limit above is expanded with numbers on the [evidence page](https://anshul48.github.io/trace/evidence/). The earlier larger builds are in the [appendix](#appendix-earlier-tests-by-us).*

## Where each thing stands

Generated from [`docs/status.json`](docs/status.json), the one file that also drives every badge on the website. A capability is marked "Working today" only if its evidence file exists in this repository.

{{statusmd}}

## Appendix: earlier tests, by us

Separate from the measured result above. These are earlier runs with their own records. They were not the sealed library, their numbers are never to be read together with the 99.9M-token result, and the machine they ran on was shut down.

| Size | Status | What was done | Caveats |
|---|---|---|---|
| **310.5M tokens**, 8 pieces | {{badge:build-310m}} | Exact search matched the ground truth. With one piece switched off it still found 0.87 of the exact results, with no wrong passages. | Our own records, not outside-verified. The cloud machine was shut down, so it cannot be re-run. A search took p50 4.18 s. [Raw record](receipts/earlier-runs/RECEIPT-RUNG-300M.txt). |
| **504.5M tokens**, 13 pieces (7.65 GB stored size on disk; memory use was not compared) | {{badge:build-504m}} | Exact search matched the ground truth. With one piece switched off it still found 0.885 of the exact results, with no wrong passages. | Our own records, not outside-verified, cannot be re-run, not served at that size. The compressed-search figure (0.994 to 0.998) was measured only on the five newest pieces. A 13-piece search took p50 6.86 s. [Raw record](receipts/earlier-runs/RECEIPT-RUNG-500M.txt). |
| **1.53B tokens**, 7.13M vectors | {{badge:routing-1b}} | A separate October test of group-picking only: opening 6.6% of the vectors kept 0.9947 of the exact top ten. | A different, larger collection. Not served through TRACE, no checkable records at that size, no billion-vector run. We have not run a billion tokens through TRACE. |

A "piece" is one sealed part of a library. The cost to build on a smaller test collection (one run each, not like-for-like) is on the [evidence page](https://anshul48.github.io/trace/evidence/#cost).

## Also by this team

- **[ANIMA](https://github.com/Anshul48/anima-substrate)** {{badge:anima-link}}: a harness around AI coding agents, with a hidden checker no agent can see, a ladder of helpers and a recorded chain of decisions. TRACE is its shared memory through a prototype link. Validated for one kind of job so far (fixing a bug against hidden tests).
- **Reflex** {{badge:reflex}}: a line of work where an AI looks at a screen and finds the right button to press (SAM 3.1 with Muse Spark). It has [its own short film](https://anshul48.github.io/trace/demos/#reflex) and [early trial results](docs/reflex.md).

## Where things are

| | |
|---|---|
| [`docs/`](docs/README.md) | The website, served by GitHub Pages, and the technical documents (see [`docs/README.md`](docs/README.md) for the index). |
| [`docs/source/`](docs/source/) | The sources the website is generated from (`python3 tools/build_site.py`). |
| [`freeze-src/`](freeze-src/) | The tested engine, 207 files. |
| [`receipts/`](receipts/) | The records of our runs (the folder is named *receipts*): the qualification run, the earlier larger builds, the order measurement. |
| [`docs/reproduction/repro-20k/`](docs/reproduction/repro-20k/README.md) | A small reproduction for your own computer. |
| [`tools/`](tools/) | The checks, the site generator and the local launcher. |

## Contributing, security, citation

[CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) · [CITATION.cff](CITATION.cff) · [CHANGELOG.md](CHANGELOG.md) · [Meta tooling used](docs/META-USE.md) · Questions or problems: [open an issue](https://github.com/Anshul48/trace/issues). License: Apache-2.0 ([LICENSE](LICENSE)). Passages in the library are English Wikipedia text under CC BY-SA 4.0.
