# 10M evidence (populated from CANDIDATE.md READY pins, 89/89 verified)

`provenance/CANDIDATE.md` (coordinator channel) reports READY (freeze-v2,
SHIP 2026-10-08, pin `:0:95436`); every file below was re-verified by the
packager against those pins before copying. This file fixes the landing
layout so review can check completeness mechanically.

```text
benchmarks/evidence/
├── README.md               # this file
├── CANDIDATE-PINS.md       # source family + byte hashes + receipt identities
├── ARTIFACT-INVENTORY.md   # bundled bytes vs hash-recorded originals
├── harness/                # executable bench harness (pinned, runnable)
│   ├── README.md           # install + run protocol (REPORT.md §3)
│   ├── adapters/           # A1/A2/R1/A3/S1, lane-final bytes, hash-verified
│   └── vendor/             # TB 0.3.0 wheel + upstream-links.json + SHA256SUMS
├── pins/                   # dependency pins of record (PINS.md)
├── provenance/             # dataset provenance + licensing, config, run conditions
│   ├── DATASETS.md         # denominators, units, conditions, licensing per gate
│   ├── CONFIG.md           # budgets, protocol, deployment conditions, eval files
│   ├── queries-10m.json    # frozen 10M gate queries (77336d62…)
│   └── CONFIRM-INPUTS.v3-10m.json  # gate fixtures (ece682c7…)
├── receipts-10m-shipped/   # qualified freeze-v2 shipping receipts (verbatim)
│   ├── lane-BENCH10M/      # REPORT + SCOPE + compares + probes + logs + full smoke lane
│   ├── ship-record/        # SHIPPED + READ10M + BUILD-RECEIPT + UPLOAD
│   └── scale10m/           # frozen rung: metrics + 4045 rows + driver + reports
├── receipts-186/           # later campaign-186 receipts, ORIGINAL verdicts kept
│   └── NEGATIVE-RESULTS.md # F2 FAIL, fresh-reader p95, exceed counts (verbatim)
└── repro-fixture/          # cheap public-fixture reproduction (runs in minutes)
    ├── README.md           # commands + expected output; NOT 10M measurements
    └── verify_smoke_receipts.py  # receipt re-verifier (SMOKE-VERIFY PASS)
```

Rules: fixture scores are never substituted for 10M measurements; original
failures ship verbatim; no private datasets are labelled redistributable
without evidence; no secrets, absolute paths, or host identifiers in any file.
