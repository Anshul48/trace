# Changelog

## Unreleased (item 7: hygiene + repo settings)

Repo About box synced to the live settings (honest description, five
topics, Pages homepage). Hygiene verified: Apache-2.0 LICENSE present,
gitignore covers caches and venvs, no junk files in the 564-file tree.

## Unreleased (item 6: CI badge + experiment smoke)

CI `verify` job now also runs the paper bundle tests and the
series-compile demo + smoke suite (organiser smoke lands with item 3).
README carries the verify badge.

## Unreleased (item 5: paper figures + README)

`paper/figures/` carries the six story images, byte-identical, and
`paper/README.md` documents every build file with its build commands.
New `paper/tests/` smoke suite (public check passes, files present,
receipts resolve), green under pytest and unittest.

## Unreleased (item 2: design notes)

New `docs/design/`: five short notes (grouping, organiser, top-down guess,
repeated work to scripts, sleep), each with status, latest measured number,
what it does not show and what would prove it wrong. Status table: organiser
row names its baseline and limits; design-only row in plain words. Site home
title states what runs.

## Unreleased (0.79% scope: all four parts)

The 0.79% figure now reads "each of the four parts" on the README,
BENCHMARKS.md B1 and the site home page: the paper's evidence file
per_shard.tsv shows 1,600 rows scored on each part. Other pages still
give the narrower "one of four parts" scope.

## Unreleased (R5 wording follow-up)

ANIMA ecosystem text restored to "prototype memory link" wording; diagram
kicker and title state what runs; engine-source row states the engine runs
and only its source is unpublished; design section lead corrected.

## Unreleased (item 1: first screen)

README first screen reworked from the wording review: new hook and design
section in plain words, status and losses above the design goal, organiser
row with its miss stated, British spelling, "Demo videos" link label, engine
row noting the source is not yet published, and an architecture diagram.
Quickstart carries real output from a fresh clone of main.

## Unreleased (public check wrapper + paper video)

New `tools/verify_paper_public.py`: runs the paper receipt checker and
prints one OK line (exit 0) only when every problem is the known withheld
file, else the checker's own output (exit 1). JUDGES.md and the README
verify path lead with it. New `paper/video/`: the paper video (8.7 MB)
with its narration script.

## Unreleased (P0: reading-copy fix)

Replaced the full redacted reading copy of the withheld FACTS file (an
internal briefing that did not belong in public) with a two-line excerpt
of the cited values. JUDGES.md updated to match.

## Unreleased (item 4: series-compile experiment)

New `experiments/series-compile/`: a synthetic repeated-task-series demo
(detector, shadow check with controls, guard), runnable with one command
plus a smoke suite, with the honesty limits stated in its README. Root
README status row reworded: the script was run beside the recorded work, nothing was switched over.

## Unreleased

Judge-ready verification: `paper/` now ships the write-up HTML, the receipt
checker, receipts, the banned-word list and the pinned evidence files (one
file withheld: it contains a server address; a two-line excerpt of it is
included for reading), plus the final PDF and a text write-up. New `JUDGES.md` with the
exact verify commands and their real output, and a "Verify this in 5 minutes"
README section (wording reviewed). `tools/check_links.py` now also checks
`JUDGES.md`.

## Unreleased (2026-11-12)

Reframed front door around the self-organizing memory database, with an honest
status table. No change to the tested engine: `freeze-src/` is untouched and
`python3 tools/verify_freeze.py` still prints
`entries=207 ok=207 missing=0 mismatch=0`.

- `README.md` (generated from `docs/source/README.src.md`) reframed: what TRACE
  is becoming, a status table (runs today / experimental / design only), and a
  roadmap pointer. Loss-first section, quickstart, checks, benchmarks and
  limitations unchanged.
- New `docs/ROADMAP.md`: the design direction in one page; design, not promises.
- New `paper/checkable-memory-for-agents.pdf`: the final preprint, linked from
  the README (link line, roadmap, file index).
- `receipts/filed-summaries/`: two internal identifiers redacted in place
  (same line numbers; hashes below updated), so no working-tree path or worker
  name ships in the repo.

## Unreleased (2026-11-09)

A refresh of the front door for a public launch. No change to the tested engine:
`freeze-src/` is untouched and `python3 tools/verify_freeze.py` still prints
`entries=207 ok=207 missing=0 mismatch=0`.

- `README.md` (generated from `docs/source/README.src.md`) rewritten: one-line
  hook, where TRACE loses first, a quickstart that was run on a fresh clone,
  a how-it-works diagram, a benchmarks table with record links, plain
  limitations and a roadmap. The "670 worker jobs" tile and a sentence about
  Reflex's experiments were removed from the front page; `docs/META-USE.md` is
  still linked.
- New `BENCHMARKS.md`: every number with its scope and a line-level link to its
  record, losses first.
- New `docs/EXPLAINER.md` (the 10-minute walkthrough) and `docs/FAQ.md` (the hard
  questions).
- New `receipts/filed-summaries/`: two result summaries (head-to-head against
  standard indexes; append against rebuild), copied byte for byte, with hashes.
  Their raw per-query files are not published.
- `tools/check_links.py` now also checks `BENCHMARKS.md`.

## 0.2.0 (2026-11-04)

A new front door. No change to the tested engine: `freeze-src/` is untouched and
`python3 tools/verify_freeze.py` still prints `entries=207 ok=207 missing=0 mismatch=0`.

- New website in `docs/`, generated from `docs/source/` by `tools/build_site.py`
  (stdlib only, `--check` mode, committed plain HTML): home, try it, how it works,
  evidence and limits, demos, verify, about, how this was built, and the explorer
  restyled with the shared design (light and dark, phone width, no outside requests).
- New `README.md`, generated from `docs/source/README.src.md`.
- `docs/status.json`: one file that decides every "Working today", "Prototype" and
  "Not built yet" badge on the site and in the README.
- `docs/demos/films.json`: the single swap list for films; three 720p working
  versions with captions.
- `docs/META-USE.md`: which Meta products and models we used and did not use.
- `receipts/order-measure/`: scripts and raw output for the measurement of how
  ordered the groups are.
- The retired pages (`/play/`, `/recording/`, `/future/`), the old hero images, the
  large duplicate JSON files and the old videos were removed from `docs/`; all are
  in git history, and the records they duplicated are in `receipts/` and `freeze-src/`.
- Stored sizes are labelled as stored size on disk everywhere.
- Issue forms (bug, claim or number looks wrong, feature), refreshed
  CONTRIBUTING, SECURITY, CITATION.cff, and a docs index.

## 0.1.0 (2026-10-14)

Successor publication on the existing public history: the previous
publication is preserved byte-exact under `archive/previous-c2-publication/`
(see its `INVENTORY.md`), and the primary tree is the stack-fork candidate.

- Frozen candidate (`freeze-src/`, SOURCEFREEZE `38c66bef…`, 207 files,
  drift `[]`) + build report + run script, staged read-only from VM
  `trace-build500` `~/exec-claude-stack-20261013T0045Z/stack-fork/`.
- Staged VM receipts verbatim (`receipts/16 JSONs`): pilot result,
  source-pin, input, cap derivation, phase telemetry, manifest before/after,
  probes, acceptance PASS, verified-VM-receipt verdict, fresh-verifier
  concurrence record.
- README with measured benchmark tables, architecture tour, repro guide,
  hero/architecture/measured-chart SVGs; local synthetic demo; freeze
  rehash wrapper; CI.
