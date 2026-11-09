<!-- SPDX-License-Identifier: Apache-2.0 -->
# Filed result summaries

Two result summaries for runs on our own server, copied here byte for byte so
that the numbers quoted in [BENCHMARKS.md](../../BENCHMARKS.md) have a record
you can read. Line numbers in BENCHMARKS.md refer to these exact files.

| File | What it records | Copied from (our working tree) | SHA-256 of this file |
|---|---|---|---|
| [head-to-head-100m-RESULT.md](head-to-head-100m-RESULT.md) | Same-store comparison of TRACE's live search service against standard FAISS indexes (flat, HNSW, IVF-SQ8, IVF-PQ) on the 812,545-passage library, 50 test searches | `trace-100m-faiss-h2h.result.md`, run 2026-11-05 | `15b7a21601fa6b091324f68ce1af8742eff0700b79437be8625a4ac960569518` |
| [append-vs-rebuild-RESULT.md](append-vs-rebuild-RESULT.md) | Appending new passages to a store versus rebuilding it, with three crash drills, on one shard-sized base of 203,137 passages | `append/VM-RESULT.md`, run 2026-11-05 | `651b6c03f9fda781137a424c3d308a9fb55dff3130da978e399d083628a57eca` |

## What these are, and what they are not

- They are the **summaries**. The raw per-query files they list (per-query
  timings and result ids, index build logs, pre-registration files) are on our
  server, together with the sealed library. They are **not published**: the
  library is not downloadable yet. So you can read these files, but you cannot
  re-run them.
- Nothing was edited. The first line of the append summary (`7017 RESULT.md`)
  is a stray artefact of the original file and was left in so that the hash
  matches. The "Files" sections name directories in our own working tree.
- No outside party has checked either run.

To check that a file here is unmodified: `sha256sum receipts/filed-summaries/*.md`
and compare with the table above.
