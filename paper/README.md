<!-- SPDX-License-Identifier: Apache-2.0 -->
# paper/

Everything behind the preprint "Checkable memory for agents: an audit of
what an agent-built memory store can honestly claim", in one folder.

- `checkable-memory-for-agents.pdf` — the preprint itself.
- `writeup.txt` — the same text as plain text.
- `writeup-arxiv.html` + `paper.css` — the write-up as a page, with each
  number carrying its receipt.
- The checker trio: `check_receipts.py` (checks every receipted number
  against its file), `receipts.json` (number to file, hash and line),
  `banned.txt` (words the write-up must not contain).
- `evidence/` — the pinned files the receipts point to, with paths
  rewritten repo-relative (hashes unchanged). One file is withheld
  because it contains a server address; a two-line excerpt of its cited
  values is published instead (see JUDGES.md).
- `figures/` — the six story images: the problem (agents grading their
  own work), the TRACE pipeline (store, routing, scoring, answer), the
  audit, the results, the planted errors, the next steps.
- `video/` — the paper as a short video, with its narration script.
- `tests/` — smoke tests for this folder (public check passes, all files
  present, receipts resolve).

Build commands, from the repo root:

```bash
uv run python -m pytest paper/tests -q
cd paper && python3 check_receipts.py writeup-arxiv.html --receipts receipts.json --banned banned.txt
python3 tools/verify_paper_public.py
```

The first must print `3 passed`; the second exits 1 here, listing only the
withheld file (it must run inside `paper/`: receipt paths resolve from the
working directory); the third prints one `PUBLIC CHECK OK` line. (The plan
draft had the checker line without `cd paper`; that form reports all 174
receipts missing and is wrong.)
