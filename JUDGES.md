<!-- SPDX-License-Identifier: Apache-2.0 -->
# JUDGES.md — verify TRACE in 5 minutes

Every command below was run from a fresh clone and its output is pasted
verbatim (clone of branch `overnight/item0-judges-verify` at 9adb48d,
2026-11-12; docs-only changes since cannot affect the outputs). Total measured
time: about 2 minutes including the one download. You need only Python 3 and
git; the unit tests need two packages (one install line, marked below).

## 0. Clone

```bash
git clone --depth 1 https://github.com/Anshul48/trace && cd trace
```

(Verified here with a sparse partial clone of the same branch, 11 seconds,
15 MB, then the identical commands below. A full clone downloads about
130 MB.)

## 1. Paper receipt checker (Python 3 only, no downloads)

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

What this means: all 15 problems are one missing file, and nothing else.
70 of the 81 receipted spans verify end to end from the public files (file
present, SHA-256 matches, value found in the file). The other 11 spans cite
the one withheld file below. No value mismatches, no bare numbers, no banned
words. Run `cd ..` to return to the repo root before step 2.

With the author's full files (all evidence present, paper pipeline), the same
command prints `OK: writeup-arxiv.html (81 receipted spans, 272 text segments
clean)` and exits 0.

Withheld files (1):

- `evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md` —
  withheld (contains infrastructure address: a server IP and login line).
  11 of 81 spans cite it and cannot verify from this repo alone.

Published evidence files keep their original `/home/...` build paths inside
(they cannot be changed without breaking the pinned hashes); they are build
paths, not secrets. `receipts.json` here is a copy of the lab file with only
the `file` paths rewritten to repo-relative form; every other field is
identical and every shipped evidence hash matches.

## 2. Repo checks (Python 3 only, no downloads)

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

## 3. Unit tests (needs numpy + blake3: the only download)

```bash
python3 -m pip install numpy blake3
CAND="$PWD/freeze-src/cand"
export PYTHONPATH="$CAND/tools:$CAND/fork/tl-sys:$CAND/fork/tl-candidate-batch/candidate:$CAND/fork/tl-sys/tlsys/serving/tests:$CAND/tests"
for t in test_default_path_identity test_fix3_knob test_fix6_parity test_fix2_suffix test_fix5_gc; do
  python3 -B "freeze-src/cand/stack/tests/$t.py"
done
```

Real output (all exit 0, 14 seconds; verified here via a `uv` venv because
this box has no pip; same test commands):

```text
PASS test_default_path_identity
PASS test_fix3_knob
PASS test_fix6_parity
PASS test_fix2_suffix
PASS test_fix5_gc
```

(`test_changed_set` is excluded, as in CI: its final assert compares against
the original build host's path. Full CI in `.github/workflows/ci.yml` also
runs the demo-app tests, the synthetic demo, the repro prep and the fix1
suites.)

## 4. Organiser smoke test

Lands with item 3 (`experiments/organiser-on-code/`), not yet merged.

## What you can and cannot verify from this repo alone

- CAN: the paper's numbers pinned to shipped evidence (checker above, minus
  the 1 withheld file); the frozen code, the recorded gates and the 20k
  reproduction (step 2); the stack unit tests (step 3).
- CANNOT here: the sealed-store runs themselves (they need the author's
  machine; the evidence files above are provided instead); the 11 spans
  pinned to the withheld FACTS register (infrastructure address).
