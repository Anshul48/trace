# Trace public release summary

Status: **staged candidate, pre-review**. Remote old main `a24a937`;
candidate commit recorded in `MANIFEST.md` at commit time; no push
before channel `REVIEW-APPROVED.md` names this repo + commit. This file
links the runnable proof.

## The release: C2-10M freeze-v2 (SHIP 2026-10-08)

The last receipt-backed successful old 10M candidate: independent
lane-READ10M review 7/7 PASS, shipped store pin `:0:95436`, producer
freeze `c2-b100m-producer-freeze-002` with **89/89 bytes recovered and
verified**. Full pins: [c10m](../c10m/README.md) (`PINS.sha256`, 110
entries). Claims + figures: [C2-10M-PUBLICATION](C2-10M-PUBLICATION.md).
Exact repro commands: [C2-10M-REPRO-APPENDIX](C2-10M-REPRO-APPENDIX.md).

## Run it (offline, <1 s)

```bash
pip install -e .[c10m]
python demos/demo_c10m_narrow.py
```

Runs the pinned serving stack (TLStore → ingest → NarrowIndex →
NarrowQuery, M80-P100-A40) over a 6-doc synthetic corpus. Ends in
`DEMO PASS`. Walkthroughs: [inspector](../demos/c10m_inspector.html)
(static offline page) and [tutorial](../demos/c10m_tutorial.md) (text
equivalent). Details: [demos/README](../demos/README.md); accessibility
notes: [ACCESSIBILITY](ACCESSIBILITY.md).

Reproduce the exact build inputs (hash-gated, verified `RECONSTRUCT
PASS`): [c10m/data](../c10m/data/DATA-README.md). Dataset-specific
licenses/attribution live there — not blanket Apache.

## Benchmarks and evidence

- 10M candidate evidence: [benchmarks/evidence](../benchmarks/evidence/)
  — executable harness (TB 0.3.0 + 4 pinned adapters), dependency pins,
  dataset provenance/licensing, config, original denominators/units/
  resource conditions, negatives, and a cheap public-fixture
  reproduction (`SMOKE-VERIFY PASS`). Fresh-store scores are never
  presented as 10M measurements; campaign-186 receipts ship separately
  with their original F2 FAIL, not as a promoted build.
- Legacy 100K qualification runner
  (`benchmarks/run_100k_qualification.py`, methodology:
  [BENCHMARKS](BENCHMARKS.md)) belongs to the older TraceV2 surface; it
  does not certify the C2-10M candidate.

## What ships

Exact pinned candidate source (89/89) + input-reconstruction recipe +
reproducible bench/evidence + runnable demos + publication record
(claims, figures, repro appendix). Code license and attribution
unchanged (Apache-2.0); third-party corpus texts carry their own
dataset-specific terms (see `c10m/data/DATA-README.md`). Push
fast-forwards remote main. Legacy Phase 1 / TraceV2 surfaces remain
explicitly separate (see README).
