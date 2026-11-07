<!-- SPDX-License-Identifier: Apache-2.0 -->
# TRACE quickstart

TRACE is search that shows its work: it finds nearly the same passages as
exact meaning-based search while looking at under 1% of the library, and
every result comes with a checkable record of where it came from.

You need: Linux or WSL, git, Python 3.8 or newer, and a web browser. This
shallow clone currently has about 63 MB of packed Git data and about 74 MB
of checked-out files, plus Git metadata. After cloning, the replay needs no
additional packages or data downloads. Clone time depends on the connection.
(Sizes measured 2026-11-07 at 0d54088.)

## Two commands

```bash
git clone --depth 1 https://github.com/Anshul48/trace && cd trace
python3 run_explorer.py --dataset 20k
```

The second command serves the explorer from your own clone and opens it in
your browser on the recorded-search replay page. It prints the explorer
address, the Inside
TRACE address, and `Dataset: 20k prefix shipped in this repo.` Press Ctrl+C
to stop. On a machine with no browser, add `--no-browser` and open the
printed address yourself.

## What ships: the 20k prefix

The only dataset in the clone is the small 20k sample, the first 88
documents of our source text: 88 documents,
20,030 tokens, 144 passages with vectors, under
`docs/reproduction/repro-20k/`. The explorer serves that plus a replay of
144 real searches TRACE answered on our own server, each result with a
checkable record your browser can re-check. Everything is served from your
clone; the command downloads nothing.

## Check it yourself

```bash
python3 tools/verify_freeze.py
python3 tools/check_receipts.py
```

Expected: `entries=207 ok=207 missing=0 mismatch=0` and
`receipts ok: gates, both probe modes, matched work, caps, freeze digest`.
`python3 tools/verify_20k.py` should print exactly one line: `IDENTICAL`
(selected sample counts and statuses agree, and the explorer data files
match the hashes pinned in this checker). The engine-file check above
compares the 207 engine files with the published manifest. These checks do
not establish that the explorer export and shipped pilot record are the same
run. It does not prove anything about search quality
or about the big library, which ran on our server.

## Honest limits

- Only `--dataset 20k` ships. `--download 10m` and `--download 100m` stop
  with exit 2 and say no such kit exists: there is no 10M or 100M download
  yet. Planned, not built.
- The public live service is switched off, and a download for the whole
  library is planned, so there is no size or hardware list to give yet.
- The headline result is ours, on our library, over 50 test searches:
  scoring 0.79% of rows on one of four nearly equal library parts while
  keeping 0.9985 of exact meaning-based search's top ten (about 127 times
  less passage-scoring work; choosing and building the groups are separate
  costs). The sealed library holds 812,545 passages
  and 99,891,846 tokens, 0.11% short of the 100M target. No outside party
  has checked any of it.
- Ordinary keyword search put the right source passage in its top ten for
  82% of the 50 test searches; TRACE did for 52%, and exact search by
  meaning also got 52%, so the gap is meaning versus keywords, not our
  shortcut. Keyword search also took less search-stage time (6 ms against
  our 1.2 s; the recorded setups differ, and we make no speed claim).
  TRACE is meaning-based search you can verify, not a
  keyword-search replacement.
- The small 20k run runs the earlier frozen engine's protocol on a small
  sample; it does not reproduce the measured library's vector-only search;
  its numbers are not the sealed-library numbers.
- The headline result is for our library and our method only and was not
  reproduced on public data. The measured search is vector search only,
  with no keyword part combined in.
- Everything you need is in the clone (about 63 MB of packed Git data,
  about 74 MB checked out, plus Git metadata).
  After the clone there is nothing else to download, no account, no upload.

## One next step

Open the Inside TRACE address the server printed and switch to the Library
tab: 1,430 real sample passages in 884 real groups across the 4 library
parts, where a recorded question lights its top 10 while the counter runs
to the recorded aggregate (about 1,600 of 203,137 rows on one part, 0.79%).
For the full judge path with every caveat, see the
[judge on-ramp](https://anshul48.github.io/trace/judge/).

## Where each number comes from

- 88 documents / 20,030 tokens / 144 vectors: `docs/reproduction/repro-20k/README.md:19,53-54`
- Only 20k ships; 10m/100m missing; `--no-browser`; Python 3.8+: `run_explorer.py:61,78,99-103,154-162` (`MIN_PYTHON`, line 32)
- Printed `Dataset: 20k prefix` line: `run_explorer.py:189`
- 144 recorded searches: `docs/status.json:14`; `docs/explorer/inside.html:234-235`
- 207 files + expected outputs: `tools/verify_freeze.py:5`; `tools/check_receipts.py:82`
- 50 searches / 0.79% / 0.9985 / ~127x: `docs/status.json:51`; `docs/source/pages/explorer.html:85`
- 812,545 passages / 99,891,846 tokens / 0.11% short: `docs/status.json:42`; `docs/explorer/inside.html:45`
- 82% / 52% / 52%, 0.74 vs 0.42, 6 ms vs 1.2 s: `docs/source/pages/evidence.html:136-137`
- Public service off / whole-library download planned / no outside check: `docs/status.json:117-128,135-138`
- Vector search only, nothing combined: `docs/source/pages/evidence.html:33`
- Small-run numbers are not the big-run numbers: `docs/reproduction/repro-20k/README.md:10-12`
- Not reproduced on public data: `docs/status.json:55`
- 1,430 passages / 884 groups / 4 parts; 1,600 of 203,137: `docs/explorer/inside.html:85-89`; `docs/explorer/library.js:26,30`
