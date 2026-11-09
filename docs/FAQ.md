<!-- SPDX-License-Identifier: Apache-2.0 -->
# FAQ: the hard questions

These are the questions we would ask. Answers are short, say where we lose, and
link to the record. Numbers come from [BENCHMARKS.md](../BENCHMARKS.md) and
nothing here goes past it. If an answer is wrong or out of date,
[open a claim-check issue](https://github.com/Anshul48/trace/issues/new?template=claim_check.yml).

**Contents:**
[Speed](#speed-and-the-competition) ·
[The numbers](#the-numbers) ·
[Reproducing](#reproducing-it) ·
[What it is](#what-it-is-and-is-not) ·
[Trust](#trust-and-the-record) ·
[People and licence](#people-and-licence)

## Speed and the competition

### Why not just use HNSW or FAISS?

For raw speed you should. In our same-store head-to-head the best standard-index
setting that matched TRACE's hit rate answered in 0.66 ms against TRACE's
median of 1,236 ms, about 1,880 times faster, with the same 26 of 50 hit rate
([A1](../BENCHMARKS.md#a-where-trace-loses)). TRACE does not exist to be faster.
It exists to make the *record* of each result checkable, to scan fewer rows,
and to append without a rebuild
([section C](../BENCHMARKS.md#c-what-the-extra-time-buys)). If you do not need
those, use the index.

### Is that 1,880x comparison fair?

Partly, and the record says so. The index timing is search only, ids only, one
thread. TRACE's is end to end: it starts engine processes and returns passages.
Adding the encoding time to the index side, the same record's own end-to-end
ratio is 85.76 ([H2H line 29](../receipts/filed-summaries/head-to-head-100m-RESULT.md#L29)).
The record's headline ratio is the larger one (1,883.53), so we report it first.
86 times slower is still a loss.

### Why is a search so slow?

Because the service starts the compiled engine fresh, once for each of four
parts, for every question. Starting processes and mapping files dominate; the
arithmetic does not. A resident server that opens each part once is designed
and **not built**. We state no speed number for it
([EXPLAINER, section 6](EXPLAINER.md#6-why-it-is-slow)).

### Why not Postgres with pgvector, or Elasticsearch?

We have not compared against either, and make no claim about them. The only
head-to-head we ran is against FAISS indexes and keyword search (BM25) on one
library.

### Do you beat Mem0, Letta, Zep or other agent-memory systems?

We have not compared against any of them and do not claim to. TRACE is search
over a fixed, sealed library. We have not run LongMemEval, LoCoMo or any public
agent-memory benchmark ([not measured](../BENCHMARKS.md#e-larger-builds-and-what-we-do-not-claim)).

## The numbers

### Why does keyword search beat TRACE?

On our 50 test searches, keyword search put the right source passage in its top
ten for 82% of them, and TRACE for 52% (about +/- 11 and +/- 13 points, 95%
interval). Exact meaning-based search also scored 52%, so the gap is meaning
search against keywords, not TRACE's shortcut
([A4](../BENCHMARKS.md#a-where-trace-loses)). The test searches were written from
the source passages, so they share distinctive words with their targets, which
favours keywords
([RESULTS lines 87-91](../receipts/benchmarks-deep/RESULTS.md#L87-L91)). We
are not claiming keyword search beats meaning search in general. For exact
words, use keyword search.

### Could a better embedding model fix the 52%?

Possibly. We used all-MiniLM-L6-v2, a small encoder. A comparison with a second,
stronger encoder (bge) was planned and was **not run**
([RESULTS lines 3-4](../receipts/benchmarks-deep/RESULTS.md#L3-L4) and
[line 94](../receipts/benchmarks-deep/RESULTS.md#L94)). We have no measurement
for a stronger model on these 50 searches.

### What does "0.79% of rows" mean? Is that a speed claim?

No. In one of the four library parts, a search scored 1,600 rows where exact
search scores 203,137 ([B1](../BENCHMARKS.md#b-what-the-method-does)). That is
scoring *work*. Choosing the groups and building them are separate costs, and
the service is slower than a plain scan on this library. We have no per-part
figures for the other three parts in this repo.

### What does "99.85% of exact top ten" mean?

On average over 200 question-part pairs, TRACE's top ten per part contained
99.85% of the ten passages that exact vector search returned
([B2](../BENCHMARKS.md#b-what-the-method-does)). It measures agreement with exact
vector search. It is not accuracy and not answer quality. In the 160 pairs from
questions we wrote, the worst pair kept 90%.

### Fifty test searches is tiny. Is this self-benchmarked?

Yes to both. Our library, our method, 50 searches, our server, no outside check.
A 95% interval on a rate over 50 searches is about +/- 11 to 13 points, and the
two intervals in A4 only just fail to overlap. The fidelity figure is an average
over 200 pairs built from the same 50 searches, so it is not 200 independent
samples. Treat all of it as a lead, not a settled result.

### Why do you call it a "100M-token library" if it is 99.9M?

It holds 99,891,846 tokens, which is 0.11% short of 100 million, and 812,545
passages ([setup table](../BENCHMARKS.md#setup-shared-by-every-100m-row)). The
token count is stated in the repo
([docs/status.json line 42](../docs/status.json#L42)), derived from our service's
own count; the library is not published.

### Is TRACE's store smaller or lighter than the alternatives?

No. Its search store takes more bytes on disk than the exact vectors it
approximates: 2.279 GB against 1.248 GB, plus 0.507 GB for a keyword index
([A6](../BENCHMARKS.md#a-where-trace-loses)). We draw no memory comparison. For
what the service needed in practice: its process peaked at about 1.03 GiB while
answering the 50 questions
([LOAD line 22](../receipts/benchmarks-deep/LOAD.md#L22)).

## Reproducing it

### Can I reproduce the 100M numbers?

Not yet. The library and its search store are not downloadable, and the raw
per-query files stay on our server. `python3 run_explorer.py --download 100m`
exits with code 2 and says so. You can read the records
([FILED and RECEIPTED rows](../BENCHMARKS.md)). What you can run is the frozen
code check, the 20k demo, and a small reproduction
([section D](../BENCHMARKS.md#d-checks-you-can-run-yourself)). A download of the
whole library is on the [roadmap](../README.md#roadmap) as planned and not
built.

### Where is the C code?

Not in this repository yet. The served search engine is a compiled C program on
our server. This repository contains the frozen **Python** candidate (207
files), the explorer, the records and the checks. There are no `.c` or `.h` files
here. The only mention of the engine is [LOAD.md line 7](../receipts/benchmarks-deep/LOAD.md#L7).
Publishing the engine source is under consideration (see the
[roadmap](../README.md#roadmap)). Until then, treat statements about the engine as
ours, not as something you can read.

### What does `verify_freeze.py` actually check?

That the 207 frozen code files match the published list of hashes. It does not
check each search result, and it does not show the code is correct. It shows the
code you can read is the code that produced the records.

### Does the demo send anything anywhere?

The clone is the only download. `run_explorer.py` uses only the Python standard
library and serves the explorer from your clone on `127.0.0.1` (your own
machine) by default. We searched the explorer's HTML and JavaScript for external
addresses on 9 November 2026 and found only links you can click, no external
scripts, fonts or data requests.

## What it is and is not

### Is this a memory for agents?

It is search over a fixed library, with a checkable record per result, which an
agent could use as memory. We have not measured whether it makes any agent
better, and we have not evaluated coding or task performance. ANIMA, a separate
prototype, uses TRACE as a *prototype memory link*. We make no claim that this
link recalls anything across sessions.

### Is it production-ready?

No. It is a research prototype under Apache-2.0. The public query service is
switched off, there is no download for the whole library, and no outside party
has checked it.

### The library is "sealed". How can it also append?

"Sealed" means the 812,545-passage library was fixed and fingerprinted when it
was built, so that measurements are repeatable. The append test used a separate
shard-sized base and left the sealed originals byte-for-byte unchanged (the
record compares hashes before and after). The result, 18 s to append against
291 s to rebuild at 203,137 passages, is from one run
([C1](../BENCHMARKS.md#c-what-the-extra-time-buys)), not from the full library.

## Trust and the record

### What is a "checkable record"? Is it cryptographic?

Each result carries the article, the character span, the licence and a SHA-256
fingerprint of the exact text. Your browser recomputes the fingerprint. A match
shows the text on the page is the text we published the fingerprint for. It does
**not** show that the search found the best passage, or that the source still
says the same. It is a consistency check, not an independent seal, so we do not
say "verifiable" or "cryptographically linked"
([EXPLAINER, section 4](EXPLAINER.md#4-the-record-on-every-result)).

### Why should I believe a project that publishes its own losses?

You should not take our word for anything. The point of publishing the losses is
that you can check them: the rows link to records, the checks are commands, and
the first thing a reader finds is where we lose. Where we cannot be checked (the
100M library), the README says so on the first screen.

## People and licence

### Who built this?

One person, directing AI coding agents: Claude as architect, Muse Code workers
for most jobs, and Codex. [docs/META-USE.md](META-USE.md) has the counts. The code
is Apache-2.0 ([LICENSE](../LICENSE)). The library text is English Wikipedia under
CC BY-SA 4.0, and each record names its article so you can credit it. Data and
model licences are listed in
[docs/reproduction/repro-20k/LICENSES-DATA-MODEL.md](reproduction/repro-20k/LICENSES-DATA-MODEL.md).

### What is Reflex, and does it use TRACE?

Reflex is a separate line of work on finding the right button on a screen. It
does not use TRACE and is not part of this project's claims.
