<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- GENERATED from docs/source/README.src.md by tools/build_site.py. Edit the source, then run: python3 tools/build_site.py -->
# TRACE

**A memory database for coding agents, becoming a store that organizes itself: use reshaping structure, slow deliberate work compiling into fast replay. What runs today is a sealed, checkable store; self-organizing memory is the design goal, not yet tested. This README says which is which.**

Research prototype · Apache-2.0 · **[Open the explorer](https://anshul48.github.io/trace/explorer/)** (no install) · [Paper](paper/checkable-memory-for-agents.pdf) · [Benchmarks](BENCHMARKS.md) · [FAQ](docs/FAQ.md) · [How it works](docs/EXPLAINER.md) · [Roadmap](docs/ROADMAP.md) · {{film}}
<!-- PAPER: in-repo PDF linked above; swap to the Zenodo DOI URL once the preprint is public, then rebuild with tools/build_site.py -->

<p align="center">
  <a href="https://anshul48.github.io/trace/explorer/"><img src="docs/img/explorer.png" alt="The TRACE explorer: a replay of real searches, each result with a checkable record. The page says it is a replay and that no search is running live." width="100%"></a>
</p>
<!-- GIF-SLOT: replace the screenshot above with docs/img/explorer-lit.gif (8-12 s, a question lights a few groups) when the cut is delivered. Keep the link and the alt text. -->

*The explorer replays real searches we ran on our server. No search runs live behind it.* [60-second tour (video)](docs/media/tour-60s.mp4).

## What TRACE is becoming

The design we are building toward, in four parts:

- **A self-organizing ontology.** The library is broken into small atoms of meaning; atoms gather into clusters, clusters gather under centroids, and every atom keeps its links upward. The same atom can belong to more than one parent, and use reshapes the structure: travelled edges gain energy, unused ones decay.
- **A plastic layer.** Outcomes strengthen or weaken links, with rollback when a change hurts. Small toys only so far.
- **Sleep consolidation.** Offline replay that compresses, distills and decays the store, behind a commit gate that can reject a bad proposal. Designed; a benefit is shown nowhere yet.
- **System 2 to System 1 trace-to-skill.** Slow, correct, deliberate work is recorded, verified, and compiled into fast structure that replays without the slow path. As a capability this is not shown anywhere yet.

## Status: what runs, what is experimental, what is design

| Area | State | Evidence |
|---|---|---|
| Sealed store: 812,545 passages / 99,891,846 tokens, fingerprinted | Runs today | Quickstart below, [BENCHMARKS.md](BENCHMARKS.md) |
| Routed dense search: 0.79% of rows scored in one of four parts, 0.9985 of exact search's top ten kept | Runs today | [B1, B2](BENCHMARKS.md#b-what-the-method-does) |
| Receipts and audit tooling: frozen-code check, receipt gates, small reproduction | Runs today | The three check commands below |
| Benchmark numbers: 50 searches, our library, our server | Runs today, self-measured | [BENCHMARKS.md](BENCHMARKS.md) |
| Bottom-up organiser v1: module agreement 0.27 against 0.30 for k-means told K, on real code | Experimental | Reported 12 Nov; record not yet filed in this repo |
| Skill compile on one card series: 23 of 23 shadow match, one series only | Experimental | Reported 12 Nov; record not yet filed in this repo |
| Plastic layer beyond toys, sleep with measured benefit, society of cortexes, ontology at scale | Design only | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Resident server, whole-library download, public benchmarks, outside check | Not built | [docs/ROADMAP.md](docs/ROADMAP.md) |

## Where it loses (read this first)

- **Speed.** In our same-store head-to-head, TRACE's live service answered in a median of **1,236 ms**. The best standard index that matched its hit rate (HNSW) answered in **0.66 ms**: about **1,880 times** faster, with the same 26 of 50 hits. The comparison is not like for like (the index returns ids only; the service starts engine processes and returns passages), but it is still a loss. [BENCHMARKS A1](BENCHMARKS.md#a-where-trace-loses)
- **Keywords.** On the same 50 test searches, plain keyword search put the right source passage in its top ten for **82%**; TRACE for **52%** (about +/- 11 and +/- 13 points). Exact meaning-based search also got 52%, so the gap is meaning versus keywords, not our shortcut. If you need exact words, use BM25. [A4](BENCHMARKS.md#a-where-trace-loses)
- **You cannot re-run our 100M numbers.** The library, its search store and the C engine source are **not published**. The 100M figures are ours, from our own server, with no outside check. What you can run is below.

## Quickstart

```bash
git clone --depth 1 https://github.com/Anshul48/trace && cd trace
python3 run_explorer.py --dataset 20k
```

Needs Python 3.8 or newer and a browser; nothing else is installed or downloaded after the clone (about 130 MB with Git data; on our connection the clone took 16 to 36 seconds and the server was up in under a second). This serves the explorer from your clone at `http://127.0.0.1:8000/explorer/`. It is **demo scale**: a replay of 144 recorded searches plus a 20k-token sample (88 documents). It is not a live search of the 100M library. Add `--no-browser` on a machine without a browser.

Then check us:

```bash
python3 tools/verify_freeze.py    # entries=207 ok=207 missing=0 mismatch=0
python3 tools/check_receipts.py   # receipts ok: gates, both probe modes, matched work, caps, freeze digest
python3 tools/verify_20k.py       # IDENTICAL
```

These re-check the frozen code and the recorded gates (the first takes well under a second). A small reproduction of the earlier protocol (needs `numpy` and `blake3`, about a minute) is in [docs/reproduction/repro-20k](docs/reproduction/repro-20k/README.md). `python3 run_explorer.py --download 100m` exits with code 2: no whole-library download exists yet.

## How it works

```mermaid
flowchart LR
    subgraph BUILD["Once, when the library is built"]
        A["812,545 passages"] --> B["Embed each passage<br/>384 numbers"] --> C["Sort into groups by meaning<br/>4 parts, about 23,000 groups each"] --> D["Seal and fingerprint"]
    end
    subgraph ASK["Every question"]
        Q["Question"] --> F["Open only the few<br/>groups likely to hold the answer"] --> G["Score the passages inside them,<br/>then re-score the shortlist"] --> H["Top ten, each with a<br/>checkable record"]
    end
    D -.-> F
```

TRACE sorts a library into groups by meaning. A question opens only a few groups and scores only the passages inside them: **1,600 of 203,137 rows (0.79%)** in one of the four library parts, keeping **0.9985 of exact search's top ten** ([B1, B2](BENCHMARKS.md#b-what-the-method-does)). That is less scoring work, not less time. Every result comes with its article, character span, licence and a SHA-256 fingerprint that your browser can recompute. The 10-minute walkthrough is [docs/EXPLAINER.md](docs/EXPLAINER.md).

## Benchmarks

Every number links to a record. Our library of **812,545 passages / 99,891,846 tokens** (0.11% short of 100 million), our method, **50 test searches**, our server. Full table with scope and caveats: **[BENCHMARKS.md](BENCHMARKS.md)**.

| What | Number | Record |
|---|---|---|
| Served latency, median, against HNSW | 1,236 ms against 0.66 ms (about 1,880x slower; same 26/50 hits) | [A1](BENCHMARKS.md#a-where-trace-loses) |
| Right source in top ten: keyword against TRACE | 82% against 52% (50 searches) | [A4](BENCHMARKS.md#a-where-trace-loses) |
| Search store size on disk | 2.279 GB, bigger than the 1.248 GB of exact vectors it approximates | [A6](BENCHMARKS.md#a-where-trace-loses) |
| Rows scored per search, one of four parts | 1,600 of 203,137 (0.79%): work, not time | [B1](BENCHMARKS.md#b-what-the-method-does) |
| Agreement with exact search's top ten | 0.9985 on average; merged lists identical on 50 of 50 | [B2, B3](BENCHMARKS.md#b-what-the-method-does) |
| Append against rebuild, 203,137 passages | about 18 s against 291 s, recall not worse; one run | [C1](BENCHMARKS.md#c-what-the-extra-time-buys) |

## Limitations, plainly

- **Not faster.** It does less scoring work and takes more time. The served path starts a fresh engine process for each of four parts on every search; a resident server is designed, not built.
- **Loses to keyword search** on our 50 searches, and has not been run on any public benchmark (BEIR, LongMemEval, LoCoMo).
- **Self-benchmarked.** 50 searches, our library, our method, no outside check, not reproduced on public data. The measured arm is vector search only, with no keyword part.
- **Not checkable at 100M.** The library, its store, the raw per-query files and the C engine source are not published. This repository holds the frozen Python candidate (207 files), the explorer, the records and the checks.
- **Bigger, not smaller.** Its search store takes more disk than the exact vectors. We claim no memory win.
- **Demo scale only.** The explorer is a replay; the public query service is switched off.
- **Append is one run.** One shard-sized base of 203,137 passages, not the full library.
- **A checkable record is a consistency check,** not an independent seal. It shows the text matches what we published, not that the search found the best passage.
- **Not an agent product.** We have not measured whether TRACE makes any agent better. ANIMA's link to it is a prototype memory link, and we make no cross-session recall claim.

More in the [FAQ](docs/FAQ.md) and in [BENCHMARKS.md, "Not measured"](BENCHMARKS.md#e-larger-builds-and-what-we-do-not-claim).

## Roadmap

Design direction, not promises: no dates, and most of it does not exist yet. Full page: **[docs/ROADMAP.md](docs/ROADMAP.md)**.

- **The self-organizing store**: ontology, organiser, top-down prediction, plastic layer, sleep, trace-to-skill. Experimental pieces and design; see the status table above.
- **A download of the whole library**, so anyone can re-run the 100M numbers. Not built.
- **A resident search server** (open each part once, answer many questions). Designed; no speed number is claimed for it.
- **TRACE on public benchmarks** (BEIR first) with full-run records, and **an outside check** of our numbers.
- **A preprint**, ["Checkable memory for agents: an audit of what an agent-built memory store can honestly claim"](paper/checkable-memory-for-agents.pdf), on the audit method and these results.

## The ecosystem

One builder, three projects. TRACE is the memory at the front; ANIMA brings that memory into coding work through a prototype link; Reflex is a separate line of work on screens and buttons.

| Project | Repository | Demo |
|---|---|---|
| TRACE | [Repository](https://github.com/Anshul48/trace) | [Explorer](https://anshul48.github.io/trace/explorer/) |
| ANIMA | [Repository](https://github.com/Anshul48/anima-substrate) | [Recorded replay](https://anshul48.github.io/anima-substrate/demo/) |
| Reflex | [Demo repository](https://github.com/Anshul48/demo-trace-anima-reflex) | [Replay](https://anshul48.github.io/demo-trace-anima-reflex/) |

ANIMA is a prototype for one job type (fix a bug, judged by a hidden checker). It is a prototype layer on top of the coding agent you already use, giving it memory (a prototype link), a checker it cannot see, and a screen to watch it work. The Muse Code, Claude Code and Codex adapters are prototypes, and the screen shows the recorded state tree of a run (UI preview). See the companion repository for its installation status. Reflex does not use TRACE.

## Where everything is

| Destination | What lives there |
|---|---|
| [BENCHMARKS.md](BENCHMARKS.md) | Every number, its scope and its record. |
| [Paper](paper/checkable-memory-for-agents.pdf) | The preprint: what an agent-built memory store can honestly claim. |
| [docs/EXPLAINER.md](docs/EXPLAINER.md) · [docs/FAQ.md](docs/FAQ.md) | The 10-minute walkthrough and the hard questions. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Where the design is headed; design, not promises. |
| [Checkable records](receipts/) | The records of our runs: the qualification run, the earlier larger builds, the order measurement, the [filed summaries](receipts/filed-summaries/README.md). |
| [Reproduce](https://anshul48.github.io/trace/verify/) | The commands that re-check the code and the records, and a [small reproduction](docs/reproduction/repro-20k/README.md). |
| [Architecture](docs/ARCHITECTURE.md) | The design in technical terms, plus a [walk through the 207 files in the tested snapshot](docs/CODE-TOUR.md). |
| Research notes | [In-depth benchmarks](docs/BENCHMARKS-DEEP.md), the [scale and build-memory runs](docs/SCALE-AND-MEMORY.md), and [how the code was written](docs/META-USE.md). |
| [Status](https://anshul48.github.io/trace/built/) | Every capability with its Working today / Prototype / Planned badge, driven by [status.json](docs/status.json). |

{{statusline}}

**Found a number that does not hold?** That is the most useful report we can get: [open a claim-check issue](https://github.com/Anshul48/trace/issues/new?template=claim_check.yml).

[Contributing](.github/CONTRIBUTING.md) · [Security](.github/SECURITY.md) · [Cite](docs/CITATION.cff) · [Changelog](docs/CHANGELOG.md) · [Open an issue](https://github.com/Anshul48/trace/issues). License: Apache-2.0 ([LICENSE](LICENSE)). Passages in the library are English Wikipedia text under CC BY-SA 4.0.
