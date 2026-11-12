<!-- SPDX-License-Identifier: Apache-2.0 -->
# Filed result summaries

Two result summaries for runs on our own server, copied here so
that the numbers quoted in [BENCHMARKS.md](../../BENCHMARKS.md) have a record
you can read. Line numbers in BENCHMARKS.md refer to these exact files.

| File | What it records | Copied from (our working tree) | SHA-256 of this file |
|---|---|---|---|
| [head-to-head-100m-RESULT.md](head-to-head-100m-RESULT.md) | Same-store comparison of TRACE's live search service against standard FAISS indexes (flat, HNSW, IVF-SQ8, IVF-PQ) on the 812,545-passage library, 50 test searches | `trace-100m-faiss-h2h.result.md`, run 2026-11-05 | `f3b12b9c793192ed86739f7d6a58adf397fef347129ba84cc3c150833355f598` |
| [append-vs-rebuild-RESULT.md](append-vs-rebuild-RESULT.md) | Appending new passages to a store versus rebuilding it, with three crash drills, on one shard-sized base of 203,137 passages | `append/VM-RESULT.md`, run 2026-11-05 | `651b6c03f9fda781137a424c3d308a9fb55dff3130da978e399d083628a57eca` |

## What these are, and what they are not

- They are the **summaries**. The raw per-query files they list (per-query
  timings and result ids, index build logs, pre-registration files) are on our
  server, together with the sealed library. They are **not published**: the
  library is not downloadable yet. So you can read these files, but you cannot
  re-run them.
- Two internal identifiers were redacted in place in the head-to-head summary
  (a worker name on line 5, a working-tree path on line 52); line numbers are
  unchanged and the hash above is of the redacted file. The first line of the
  append summary (`7017 RESULT.md`) is a stray artefact of the original file
  and was left in so that the hash matches.
- No outside party has checked either run.

To check that a file here is unmodified: `sha256sum receipts/filed-summaries/*.md`
and compare with the table above.
