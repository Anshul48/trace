# Suggested captions (text lives OUTSIDE the images)

Paste-ready README/HTML captions for the generated PNGs. Quantitative
claims belong here and in the benchmark tables, never inside the bitmaps.

- `trace-stack-hero-16x9.png` — "TRACE stack fork `38c66bef`: five stacked
  fixes (pilot instrumentation, drain budget, sort bound, suffix-verified
  serving, generation GC) on one frozen 207-file base, qualified by a
  receipt-backed 10M-token run with independent oracle replay."
- `trace-lifecycle-16x9.png` — "Qualification lifecycle: ingest → budgeted
  drain → bounded repair → SIGKILL restart → repair-to-zero → pinned
  guided evaluation against a matched-work flat control (120 probes,
  all-sources + leave-source-out)."
- `trace-serving-generations-16x9.png` — "Atoms are committed, grouped into
  per-document holons, and organized into a hierarchy; verified serving
  generations are published for pinned readers, with guided hierarchical
  search compared against a matched flat scan at equal scoring work."
- `trace-evidence-chain-16x9.png` — "Evidence chain: 207-file source freeze
  → run receipts → hardened acceptance (PASS) → independent read-only
  oracle replay (240/240 exact, store unchanged). Costs (drain wall,
  repair, reader interference) are published with the result."
- `trace-small-repro-16x9.png` — "Small-scale reproduction: an exact
  88-document / 20,030-token prefix with its real cached vectors runs the
  same frozen harness locally to PASS; the 10M qualification remains the
  separate recorded receipt set."
- `anima-ecosystem-16x9.png` — "ANIMA: five independently installable
  components — substrate, sst, stc, entorhinal, reflex. `anima.*` modules
  are import aliases only; there is no shared runtime or wiring."

Alt-text rule: describe the schematic (glyphs/zones), then give the
caption above as visible text; do not put recall numbers in alt text
without the words "harness recall / oracle agreement" next to them in
the surrounding paragraph.
