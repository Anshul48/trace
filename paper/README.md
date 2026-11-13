<!-- SPDX-License-Identifier: Apache-2.0 -->
# paper/

When coding agents write a system's code, run its experiments and also
write the reports on those experiments, how does anyone know which of the
reported results are true? The reports can agree with the code and both
still be wrong. We describe a small audit procedure for agent-built
software and apply it to our own system, TRACE, a memory store for coding
agents that answers a query by scoring only a small, routed shortlist of
stored passages instead of the whole store. The procedure records whether
each study had a plan fixed before it ran, ties every reported number to
an evidence file, and has a separate analyst recompute selected findings.
One result held: routing scored 0.79 percent of rows on every shard
(partition) and, averaged over 4 shards, kept 0.9985 of the exact top ten
results (scoring work only, not speed; no plan file). Several did not:
search by meaning found fewer labelled sources than plain keyword search
(26/50 vs 41/50); two refinements did not beat keyword search; and the
live service was far slower than a standard index. When we planted 18
errors in a copy of this paper, the automated check caught 10 and missed
8: it catches wrong values and misses wrong meanings. The results concern
one project; downstream coding performance and the general effectiveness
of the procedure were not evaluated.

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

Check commands, from the repo root:

```bash
python3 -m unittest discover -s paper/tests
python3 tools/verify_paper_public.py
(cd paper && python3 check_receipts.py writeup-arxiv.html --receipts receipts.json --banned banned.txt)
```

The first must print `OK` (3 tests); the second prints one `PUBLIC CHECK
OK` line; the third exits 1 here, listing only the withheld file (it must
run inside `paper/`: receipt paths resolve from the working directory).
