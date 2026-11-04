# Changelog

## 0.2.0 (2026-11-04)

A new front door. No change to the tested engine: `freeze-src/` is untouched and
`python3 tools/verify_freeze.py` still prints `entries=207 ok=207 missing=0 mismatch=0`.

- New website in `docs/`, generated from `docs-src/` by `tools/build_site.py`
  (stdlib only, `--check` mode, committed plain HTML): home, try it, how it works,
  evidence and limits, demos, verify, about, how this was built, and the explorer
  restyled with the shared design (light and dark, phone width, no outside requests).
- New `README.md`, generated from `docs-src/README.src.md`.
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
