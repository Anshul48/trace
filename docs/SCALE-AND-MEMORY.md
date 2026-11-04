<!-- SPDX-License-Identifier: Apache-2.0 -->

# Earlier scale and build-memory runs

These are earlier tests, by us. They are our own records, not outside-verified. The raw receipt files are in [receipts/earlier-runs/](../receipts/earlier-runs/).

The build figures quoted in [BENCHMARKS.md](BENCHMARKS.md) and [REPRO.md](REPRO.md) (9,494.9 s, 8,489.1 MiB) come from run seam12a. The `result.json` in [receipts/](../receipts/) is an older run. Both 10M runs used the same corpus (10,003,381 tokens).

| | Run seam12a ([receipt](../receipts/earlier-runs/seam12a-result.json)) | Older run ([receipt](../receipts/result.json)) |
|---|---|---|
| Peak memory while building (main process) | 8,489.1 MiB | 22,565.5 MiB |
| Wall time | 9,494.9 s | 12,973 s |
| Candidate source | approximate nearest-neighbour (hnsw) | not recorded in its receipt |
| Recall at top-10 (120 probes, agreement with an oracle, not relevance) | 0.7367 | 0.7300 |
| Stored size after the run | 3,058,624,883 bytes | 2,868,578,536 bytes |

- **10M runs.** Read the table as: one run each, different settings, not like-for-like, our own records, not outside-verified. These are peak memory while building, not memory while serving. Each run also had a child process with its own peak (seam12a 7,169.2 MiB, older run 15,668.8 MiB).
- **504.5M-token build** (around 28 Oct 2026, [RECEIPT-RUNG-500M.txt](../receipts/earlier-runs/RECEIPT-RUNG-500M.txt)). 504,480,146 tokens in 13 shards, 7,653,469,538 bytes stored size. Exact search matched the ground truth (1.0, 0 errors). With one shard down, recall fell from 1.0 to 0.885, with 0 wrong passages. Compressed search scored 0.994-0.998 at top-10, measured only on five of the 13 shards (the five newest). A 13-shard query took p50 6.86 s, with shards searched one at a time.
- **310.5M-token build** ([RECEIPT-RUNG-300M.txt](../receipts/earlier-runs/RECEIPT-RUNG-300M.txt)). 310,532,353 tokens in 8 shards, 4,709,827,408 bytes stored size. Exact search 1.0. With one shard down, recall 0.87, with 0 wrong passages. Compressed search 0.995-0.998 at top-10 on all 8 shards. An 8-shard query took p50 4.18 s, shards searched one at a time.
- **Cannot be re-run.** The cloud machine used was shut down, so this cannot be re-run; the receipt was written by a worker, the underlying files are gone.
- **What these are not.** These are build and scale tests, not the 812,545-passage sealed-library comparison; do not read them as the headline results. We did not run 1 billion tokens.
