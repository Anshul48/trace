# Changelog

## 0.1.0 (2026-10-14)

Successor publication on the existing public history: the previous
publication is preserved byte-exact under `archive/previous-c2-publication/`
(see its `INVENTORY.md`), and the primary tree is the stack-fork 10M candidate.

- Frozen candidate (`freeze-src/`, SOURCEFREEZE `38c66bef…`, 207 files,
  drift `[]`) + build report + run script, staged read-only from VM
  `trace-build500` `~/exec-claude-stack-20261013T0045Z/stack-fork/`.
- Staged VM receipts verbatim (`receipts/16 JSONs`): pilot result,
  source-pin, input, cap derivation, phase telemetry, manifest before/after,
  probes, acceptance PASS, `VERIFIED_VM_10M_RECEIPT`, fresh-verifier
  concurrence record.
- README with measured benchmark tables, architecture tour, repro guide,
  hero/architecture/measured-chart SVGs; local synthetic demo; freeze
  rehash wrapper; CI.
