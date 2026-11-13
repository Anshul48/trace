<!-- SPDX-License-Identifier: Apache-2.0 -->
# Verify TRACE in 5 minutes (for judges and reviewers)

Every command below was run from a fresh clone and its output is pasted
verbatim (clone of branch `overnight/item0-judges-verify` at 9adb48d for the
first pass, VM full clone for confirmation, 2026-11-12; docs-only changes
since cannot affect the outputs). Total measured time: about 2 minutes
including the one download. You need only Python 3 and git; the unit tests
need two packages (one install line, marked below).

Folder names inside `paper/evidence` (for example `claude-sci`) are the
workspaces of the AI coding agents that produced the runs, and three notes
name the lane that ran them (`glass-pavo`). Both are left as written: the
files are hash-pinned evidence.

## 0. Clone

```bash
git clone --depth 1 https://github.com/Anshul48/trace && cd trace
```

(Clone verified from a fresh clone of main at 36b8ef9 on 2026-11-12:
147 MB in 9 seconds on a fast link; a sparse partial clone works too and
is what was used locally.)

## 1. Repo checks (Python 3 only, no downloads)

```bash
python3 tools/verify_freeze.py
python3 tools/check_receipts.py
python3 tools/verify_20k.py
```

Real output (all exit 0):

```text
entries=207 ok=207 missing=0 mismatch=0
receipts ok: gates, both probe modes, matched work, caps, freeze digest
IDENTICAL
```

Shows: the 207 frozen code files are unchanged since they were tested, and
the recorded check results are intact. Does not show: the 100M-token
numbers, which need the unpublished library.

## 2. Paper receipt checker (Python 3 only, no downloads)

Start with the wrapper, from the repo root. It runs the checker and sorts
the result: exit 0 with one OK line only if every problem is the known
withheld file; anything else prints the checker's own output and exits 1.

```bash
python3 tools/verify_paper_public.py
```

Real output (exit 0):

```text
PUBLIC CHECK OK: 70 of 81 receipted spans verified against published files; 11 spans cite 1 withheld file (contains a server address); 0 other problems
```

The raw checker, for the full detail (exits 1 here, on purpose: 15
missing-file problems, all the same withheld file, nothing else fails):

```bash
cd paper
python3 check_receipts.py writeup-arxiv.html --receipts receipts.json --banned banned.txt
```

Real output (exit 1):

```text
FAIL: 15 problem(s) in writeup-arxiv.html
 - RECEIPT corpus-shortfall: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT corpus-tokens: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT e1a-k10: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT e1a-n50: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT e1a-recall-09985: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT e1a-units-812545: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT numd-verbatim-10: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT numd-plan100-100: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT numd-fiqa7-7: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT numd-scifact24-24: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT numd-nf90-90: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT numd-nf28-28: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT numd-nf97-97: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT numd-nf55-55: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
 - RECEIPT numd-stand95-95: file does not exist: evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md
```

All 15 problems are the same missing file. A span is one number in the
paper's text; a receipt names the file, the hash and the line that number
came from. 15 receipts point to the withheld file and 11 spans use them, so
70 of the 81 spans check out end to end (file present, SHA-256 matches,
value found in the file) and 11 cannot be checked here. Run `cd ..` to
return to the repo root before step 3.

Shows: each receipted number printed in the paper matches its pinned file.
Does not show: that the experiment behind the number was done correctly
(the paper: "It confirms values and hashes only").

With the author's full files (all evidence present, paper pipeline), the same
command prints `OK: writeup-arxiv.html (81 receipted spans, 272 text segments
clean)` and exits 0.

Withheld files (1):

- `evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md` —
  withheld (contains infrastructure address: a server IP and login line).
  11 of 81 spans cite it and cannot verify from this repo alone.

The spans that cannot be checked from this repo include the paper's main
positive result (0.9985 of the exact top ten kept, 50 searches, top 10) and
the store size (812,545 passages). The other result in that sentence of the
paper, 0.79 percent of rows scored, does verify from the public files
(`evidence/.../shard-fraction-all/per_shard.tsv`). The two lines of the
withheld file that these receipts point to are copied, unchanged, in
`evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.excerpt.md`.
An excerpt cannot match the receipt's hash; it is there so the values can
be read.

Published evidence files keep their original `/home/...` build paths inside
(they cannot be changed without breaking the pinned hashes); they are build
paths, not secrets. `receipts.json` here is a copy of the author's original
file with only the `file` paths rewritten to repo-relative form; every other
field is identical and every shipped evidence hash matches.

## 3. Unit tests (needs numpy + blake3: the only download)

```bash
python3 -m pip install numpy blake3
CAND="$PWD/freeze-src/cand"
export PYTHONPATH="$CAND/tools:$CAND/fork/tl-sys:$CAND/fork/tl-candidate-batch/candidate:$CAND/fork/tl-sys/tlsys/serving/tests:$CAND/tests"
for t in test_default_path_identity test_fix3_knob test_fix6_parity test_fix2_suffix test_fix5_gc; do
  python3 -B "freeze-src/cand/stack/tests/$t.py"
done
```

Real output (all exit 0, 14 seconds; we ran these inside a virtual
environment made with `uv` because this box has no pip; the test commands
are the same):

```text
PASS test_default_path_identity
PASS test_fix3_knob
PASS test_fix6_parity
PASS test_fix2_suffix
PASS test_fix5_gc
```

Shows: the five stack unit tests pass on this checkout. Does not show: the
demo-app, synthetic-demo or fix1 suites (full CI runs those; see
`.github/workflows/ci.yml`). (`test_changed_set` is excluded, as in CI: its
final assert compares against the original build host's path.)

## 4. Organiser smoke test

From a fresh clone:

```
cd experiments/organiser-on-code
python3 -I -B -W error::ResourceWarning -m unittest discover -s tests
python3 -I run.py
```

Shows: the tests print `OK` (18 tests, a few seconds). The second command
prints the module-grouping table; on CPython 3.12.3 it is byte-identical to
`EXPECTED_OUTPUT.txt` (mean module ARI: organiser 0.228, k-means told 12:
0.245). Does not show: other Python versions print slightly different
numbers because the standard-library text differs (shape unchanged); the
0.27-against-0.30 table needs a vectors file that is not published yet (see
the experiment's README).

## What you can and cannot verify from this repo alone

- CAN: the paper's numbers pinned to shipped evidence (checker above, minus
  the 1 withheld file); the frozen code, the recorded gates and the 20k
  reproduction (step 1); the unit tests (step 3); the organiser
  experiment's tests and one-command table (step 4, with the
  Python-version caveat stated there).
- CANNOT here: the sealed-store runs themselves (they need the author's
  machine; the evidence files above are provided instead); the 11 numbers
  whose receipts point to the withheld file.
