<!-- SPDX-License-Identifier: Apache-2.0 -->
# Benchmarks

Every number on this page links to the record it came from, with the line
number. Losses come first. Nothing here has been checked by anyone outside
this project.

**Read this before the tables.**

- **The 100M-token numbers are ours.** Our library (812,545 passages), our
  method, 50 test searches, measured on our own server. The library is not
  published yet, so you **cannot re-run them**. You can read the records. The
  things you *can* run yourself are in [section D](#d-checks-you-can-run-yourself).
- **50 searches is small.** A 95% confidence interval on a rate measured over
  50 searches is about +/- 11 to 13 points.
- **One column says what kind of record backs each row.**

| Status | Meaning |
|---|---|
| **RECEIPTED** | A record of the run is in this repo and you can open it. |
| **FILED** | A result summary is in this repo ([`receipts/filed-summaries/`](receipts/filed-summaries/README.md)). The raw per-query files stay on our server, so the summary is readable but not re-runnable. |
| **RE-RUN** | You can run it from a clone. The command and the output we got are given. |
| **STATED** | Stated in this repo, with no run record shipped. |

Older and deeper pages: [docs/BENCHMARKS-DEEP.md](docs/BENCHMARKS-DEEP.md) (more
measurements, same discipline) and [docs/BENCHMARKS.md](docs/BENCHMARKS.md)
(the earlier, smaller build; its numbers can differ from this page).

Links below use these shorthand names:
`RESULTS` = [receipts/benchmarks-deep/RESULTS.md](receipts/benchmarks-deep/RESULTS.md),
`LOAD` = [receipts/benchmarks-deep/LOAD.md](receipts/benchmarks-deep/LOAD.md),
`H2H` = [receipts/filed-summaries/head-to-head-100m-RESULT.md](receipts/filed-summaries/head-to-head-100m-RESULT.md),
`APPEND` = [receipts/filed-summaries/append-vs-rebuild-RESULT.md](receipts/filed-summaries/append-vs-rebuild-RESULT.md),
`OUT1` = [receipts/order-measure/out-1-test-searches-pairs-balance.txt](receipts/order-measure/out-1-test-searches-pairs-balance.txt).

## Setup shared by every 100M row

| Fact | Value | Receipt | Status |
|---|---|---|---|
| Passages in the library | 812,545 | [OUT1 line 3](receipts/order-measure/out-1-test-searches-pairs-balance.txt#L3) | RECEIPTED |
| Four nearly equal parts | 203,137 + 203,136 + 203,136 + 203,136 | [OUT1 line 3](receipts/order-measure/out-1-test-searches-pairs-balance.txt#L3) | RECEIPTED |
| Groups per part | 22,995 | [OUT1 line 4](receipts/order-measure/out-1-test-searches-pairs-balance.txt#L4) | RECEIPTED |
| Tokens | 99,891,846, which is 0.11% short of 100 million | [docs/status.json line 42](docs/status.json#L42) | STATED (from our service's own count; the library is not published) |
| Embedding model and size | all-MiniLM-L6-v2, 384 numbers per passage | [RESULTS lines 9-10](receipts/benchmarks-deep/RESULTS.md#L9-L10) | RECEIPTED |
| The 50 test searches | 40 questions we wrote + 10 taken from passage openings | [RESULTS lines 11-13](receipts/benchmarks-deep/RESULTS.md#L11-L13) | RECEIPTED |
| Machine | one shared Azure VM, 4 vCPU (details in the records) | [LOAD lines 1-9](receipts/benchmarks-deep/LOAD.md#L1-L9), [H2H line 5](receipts/filed-summaries/head-to-head-100m-RESULT.md#L5) | RECEIPTED |

## A. Where TRACE loses

| # | Claim | Scope and caveat | Receipt | Status |
|---|---|---|---|---|
| A1 | The live search service answered in a **median of 1,236 ms**. The best standard-index setting that matched its hit rate (HNSW, `efSearch=128`) answered in **0.66 ms**. That is **about 1,880 times** slower (exact ratio 1883.53). Both hit the right source passage for 26 of 50 searches. | **Not like for like.** The index timing is search only, ids only, one thread. The service timing is end to end: it starts fresh engine processes and returns passages. If the embedding time is added to the index side, the same record's own end-to-end ratio is **85.76**. One shared VM, 50 searches. | [H2H line 20](receipts/filed-summaries/head-to-head-100m-RESULT.md#L20) (service 1236.16), [line 13](receipts/filed-summaries/head-to-head-100m-RESULT.md#L13) (HNSW 0.66), [line 29](receipts/filed-summaries/head-to-head-100m-RESULT.md#L29) (ratios) | FILED |
| A2 | Over 50 varied questions the service took **p50 1,238 ms, p95 1,276 ms, max 1,306 ms** end to end. The four-part search alone took p50 1,218 ms. | Same machine, one question at a time. A separate timing of the same search stage gives p50 1,217.6 ms. | [LOAD lines 31, 33](receipts/benchmarks-deep/LOAD.md#L31-L33); [RESULTS line 51](receipts/benchmarks-deep/RESULTS.md#L51) | RECEIPTED (aggregate; per-query files absent) |
| A3 | An exact scan of every passage averaged **about 87.5 ms** per search (50 searches batched together). Keyword search (BM25) took **p50 6.1 ms**. | The setups differ: the exact scan is batched, keyword is one search at a time and retrieval only. Read these as "TRACE is not faster", not as a ranking. | [RESULTS lines 53-54](receipts/benchmarks-deep/RESULTS.md#L53-L54) | RECEIPTED |
| A4 | **Keyword search found the right source passage in its top ten for 82% of the 50 searches. TRACE found it for 52%.** Exact meaning-based search also scored 52%. | 41 of 50 (0.82 x 50) vs 26 of 50. 95% confidence intervals (Wilson) are 69% to 90% and 39% to 65%, so about +/- 10.5 and +/- 13.3 points (derived by [the one-liner in section D](#d-checks-you-can-run-yourself); inputs are the receipt's counts). The gap is meaning search versus keywords, not TRACE's shortcut. The probes share distinctive words with their sources, which favours keywords. This is not a claim that keyword search beats meaning search in general. | [RESULTS lines 35, 37, 38](receipts/benchmarks-deep/RESULTS.md#L35-L38) (rates); [RESULTS lines 87-91](receipts/benchmarks-deep/RESULTS.md#L87-L91) (why keywords win here); [H2H line 20](receipts/filed-summaries/head-to-head-100m-RESULT.md#L20) (26/50) | RECEIPTED |
| A5 | On a rank-aware score (nDCG@10) the gap is **0.74 for keyword against 0.42 for TRACE**. | Same 50 searches. The target is one designated source passage, not human relevance judgments. Never read this as the 82/52 pair. | [RESULTS lines 35, 38](receipts/benchmarks-deep/RESULTS.md#L35-L38) | RECEIPTED |
| A6 | **TRACE's search store is bigger than the exact vectors it approximates:** 2.279 GB against 1.248 GB (plain vectors) and 0.507 GB (keyword index). | Bytes on disk (`du -sb`), not memory in use, and excluding the 810 MB of passage text that every system needs ([line 73](receipts/benchmarks-deep/RESULTS.md#L73)). The spare structure costs bytes to save scored rows. We claim no memory win and draw no memory comparison. | [RESULTS lines 70-79](receipts/benchmarks-deep/RESULTS.md#L70-L79) | RECEIPTED |
| A7 | A fresh service process took **8.8 s** to start. | The page cache was warm. A truly cold boot may be slower (the record says so). | [LOAD lines 13-17](receipts/benchmarks-deep/LOAD.md#L13-L17) | RECEIPTED |

## B. What the method does

| # | Claim | Scope and caveat | Receipt | Status |
|---|---|---|---|---|
| B1 | Per search, TRACE scored **1,600 of 203,137 rows: 0.79%**, about 127 times less passage-scoring work than scoring every row. | **One of the four parts (the first)**, 50 searches. Work, not time: choosing the groups and building them are separate costs, and the service is slower, not faster (see A1 to A3). No work figures for the other three parts are recorded in this repo. | [RESULTS lines 62-66](receipts/benchmarks-deep/RESULTS.md#L62-L66); the note on wall time is at [lines 58-60](receipts/benchmarks-deep/RESULTS.md#L58-L60) | RECEIPTED |
| B2 | TRACE **kept 0.9985 of exact meaning-based search's top ten**, averaged over 200 question-part pairs (50 searches x 4 parts). | "Exact" means exact vector search, not keyword search. 0.9985 measures agreement with exact vector search, **not** answer quality. Standard deviation 0.0122. In the 160 pairs from questions we wrote, the worst pair kept 0.90. | [RESULTS lines 23-29](receipts/benchmarks-deep/RESULTS.md#L23-L29) | RECEIPTED |
| B3 | The merged top ten from TRACE was **identical to exact vector search on 50 of 50 searches.** | Same 50 searches. Because dense retrieval is capped at 52% on these probes (A4), identical lists also mean identical misses. | [RESULTS lines 41-42](receipts/benchmarks-deep/RESULTS.md#L41-L42) | RECEIPTED |

## C. What the extra time buys

| # | Claim | Scope and caveat | Receipt | Status |
|---|---|---|---|---|
| C1 | **Appending** new passages took **18.9 s and 17.6 s** (two runs). **Rebuilding** the same store took **291.1 s**. Recall after appending was **not worse than after rebuilding** (0.9917 against 0.9927 and 0.9970 against 0.9966; the margin we allowed was 0.02). | One shared VM, **one run, one shard-sized base of 203,137 passages**, real vectors. Not tested at 812,545 passages, with several writers, with a cold disk, or on text queries. | [APPEND lines 23-24, 26](receipts/filed-summaries/append-vs-rebuild-RESULT.md#L23-L26) (times); [line 35](receipts/filed-summaries/append-vs-rebuild-RESULT.md#L35) (recall); [line 46](receipts/filed-summaries/append-vs-rebuild-RESULT.md#L46) (scope) | FILED |
| C2 | In the same test, TRACE's append (18.3 s) was about **4.7 times faster than adding the same passages to an HNSW index** (85.2 s). | Same caveats as C1. One run. The time to build the HNSW base index (about 148 s) is not counted in the 85.2 s. | [APPEND lines 38-39, 42](receipts/filed-summaries/append-vs-rebuild-RESULT.md#L38-L42) | FILED |
| C3 | **Crash-safe append: 3 of 3 drills.** After each kill, the store verified with zero bad rows and an unchanged digest. | Three kill drills, one store. Not a durability proof. | [APPEND line 40](receipts/filed-summaries/append-vs-rebuild-RESULT.md#L40) | FILED |
| C4 | **A checkable record per result.** Each result carries the article, the character span, the licence and a SHA-256 fingerprint of the exact text. Your browser recomputes it. | The fingerprint shows the text matches what we published. It does not show that the search found the best passage. The 207-file check in section D covers the frozen code and records, not each result one by one. | Where it is declared: [docs/status.json lines 20-25](docs/status.json#L20-L25) (code: [docs/explorer/app.js](docs/explorer/app.js)); try it in the [explorer](https://anshul48.github.io/trace/explorer/) | STATED (mechanism); try it in your browser |

## D. Checks you can run yourself

Run on 2026-11-09 from a fresh `git clone --depth 1` of this repository, Python
3.12.3 on Linux (WSL2). Times vary with your machine.

| Check | Command | Output we got | Status |
|---|---|---|---|
| The 207 frozen files match the published list | `python3 tools/verify_freeze.py` | `entries=207 ok=207 missing=0 mismatch=0` | RE-RUN |
| The recorded gates match their receipts | `python3 tools/check_receipts.py` | `receipts ok: gates, both probe modes, matched work, caps, freeze digest` | RE-RUN |
| The small explorer data matches its pinned hashes | `python3 tools/verify_20k.py` | `IDENTICAL` | RE-RUN |
| The 20k demo (88 documents, 20,030 tokens, 144 passages) | `python3 run_explorer.py --dataset 20k` | Explorer served; pages answered HTTP 200 | RE-RUN |
| Small reproduction of the earlier protocol (needs `numpy` and `blake3`) | [docs/reproduction/repro-20k/README.md](docs/reproduction/repro-20k/README.md) | `FREEZE PASS 207/207`, `VERIFY PASS`, and a pilot `PASS` in 45 s here (recorded: 41.9 s, [result.json](docs/reproduction/repro-20k/pilot-20k-out2/result.json)) | RE-RUN |
| Confidence intervals in row A4 | `python3 -c "from math import sqrt as s;z=1.96;[print(k,round((k/50+z*z/100-z*s(k/50*(1-k/50)/50+z*z/10000))/(1+z*z/50),3),round((k/50+z*z/100+z*s(k/50*(1-k/50)/50+z*z/10000))/(1+z*z/50),3)) for k in (26,41)]"` | `26 0.385 0.652` and `41 0.692 0.902` | RE-RUN |

The small reproduction runs the frozen engine's earlier protocol on 20,030
tokens. Its numbers are **not** the 100M numbers above.
Downloading the library is **not** possible yet:
`python3 run_explorer.py --download 100m` exits with code 2 and says why.

## E. Larger builds and what we do not claim

| Fact | Scope and caveat | Receipt | Status |
|---|---|---|---|
| An earlier, larger build: **504,480,146 tokens in 13 sealed pieces**, 7.65 GB stored. | The machine is shut down. We claim **no search results** from it here, and it cannot be re-run. It is a record that the build completed, not part of the 50-search numbers above. | [RECEIPT-RUNG-500M.txt lines 31-34](receipts/earlier-runs/RECEIPT-RUNG-500M.txt#L31-L34) | RECEIPTED |

**Not measured, and not claimed:**

- TRACE on public benchmarks (BEIR, LongMemEval, LoCoMo). Not run.
- Any result checked by someone outside this project.
- A memory comparison against another system.
- Search speed at any scale. The one speed comparison we have (A1) is a loss.
- A resident (always-on) search server. It is designed, not built, and we state no speed number for it.
- Searching a library of a billion tokens end to end.
- Cross-session recall in ANIMA's prototype memory link. We make no such claim.

**Found a number that does not hold?** That is the most useful report we can
get. [Open a claim-check issue](https://github.com/Anshul48/trace/issues/new?template=claim_check.yml)
and name the row.
