# ARTIFACT-INVENTORY.md — bundled bytes vs hash-recorded originals

Rule: small verdict-bearing files are bundled verbatim; multi-MB run
dumps stay at their source/archive paths and are pinned here by
byte size + sha256 (all hashes computed by the packager from the
read-only sources on 2026-10-14). Nothing is re-measured or rescored.

## Bundled in this tree

- `harness/`: 4 adapters + TB 0.3.0 wheel + upstream-links.json +
  SHA256SUMS (pins in `CANDIDATE-PINS.md`).
- `receipts-10m-shipped/lane-BENCH10M/`: REPORT.md, SCOPE.md,
  snapshot-before-mutation.md, c2-bench10m-source-record.json,
  store-probe.json, store-probe-162.json, adoption-162.log,
  pony-collision-162.log, logs (nfcorpus.log, pony-162.log,
  run-nfcorpus.sh), per-lane `compare-shipped-vs-{bm25,dense,k100}.md`
  (smoke: bm25 only — 2-arm lane), and the FULL smoke lane
  (RUN.json `19d96e62…` 62177 B + 2 trecs).
- `receipts-10m-shipped/ship-record/`: c2-10m-SHIPPED.md,
  READ10M-REPORT.md, BUILD-RECEIPT.json, C2-10M-UPLOAD.json.
- `receipts-10m-shipped/scale10m/`: metrics.json, rows.jsonl (4045
  rows), driver_10m.py, BUILD/COMMANDS/PHASE2 reports, queries.log,
  corpus_check + tok_wp_prefix pairs, phase1.json.
- `receipts-186/`: RESULT, RULINGS ×2, WINDOW, DISTURBANCES,
  pins-186.sha256, release-sha256.txt, machine verdict JSON.
- `provenance/`: DATASETS.md, CONFIG.md, queries-10m.json,
  CONFIRM-INPUTS.v3-10m.json.

## Hash-recorded originals (not bundled)

Source root `TA/coordination/c2-work-20261006T1925Z/lane-BENCH10M/evidence/`:

| file | bytes | sha256 |
|---|---|---|
| curated/run_20261008_183840_882679.json | 11621445 | `a584099eeafe9245e25149e01de547b2fb7325d24aeb0c9b68b9743421d3362a` |
| curated/….0_bm25.trec | 834417 | `74bee29f6acad024b5322957dc25a64cd651804d13f2e31c49eaa367f79bcd41` |
| curated/….1_dense.trec | 1567680 | `0059d15bf6f2bd11d7c25de3de2f4d3987297c04a33bc2a582b8db4db9ba6307` |
| curated/….2_…_C2Bench10MShipped.trec | 1016649 | `213b988328d4673d6c1271bfc4c4b0dd500697b67d52c197504e66f0c2893664` |
| curated/….3_…_C2Bench10MK100.trec | 1474858 | `65855ecf6b6d80e29d559e71cdd9eb14637801f391c25ec05765af15435e4f6a` |
| scifact/run_20261008_183927_899309.json | 14331201 | `adcf3bbe33562ec92d40a55b8899fcc2fc14def3925ab6a91a8e93905aecd880` |
| scifact/….0_bm25.trec | 800209 | `67ff30cc0d1f820bb59798e636366dd03e3aa3a62d1c394eda97a5f4ff5e73c4` |
| scifact/….1_dense.trec | 830133 | `dbaf10e0d0c95ce711d7a7420978a8f9a4bff3eb57cb9389d50044ef7bc377e0` |
| scifact/….2_…_C2Bench10MShipped.trec | 613409 | `bd4f2161384da30e8150ef8c96bb3abe3432434aedf8ead43709c850c213f959` |
| scifact/….3_…_C2Bench10MK100.trec | 990801 | `66451daf9784838461d4de3918bf3c18faaf9cc10199a7f3098aa275ff86980d` |
| nfcorpus/run_20261008_192345_041319.json | 15661398 | `78c2d9f06847c16cdb35fba1a651939ff141d9ae3fc6f364cf2648103fb1b5cb` |
| nfcorpus/….0_bm25.trec | 726267 | `6fe79a35ba621028a71807075fd276d9cdeea8888b4532eeda8bd1a1eba5b51b` |
| nfcorpus/….1_dense.trec | 1113194 | `90ecfd0003c7bb2f0d44afea79004a240828176faa2e679873835579e8ffcb12` |
| nfcorpus/….2_…_C2Bench10MShipped.trec | 688703 | `e3bf450590b9337bda725c36496f21ef159ff6414814337ff5298b78f11bf02f` |
| nfcorpus/….3_…_C2Bench10MK100.trec | 954373 | `3b0707547f10e84e04a0839222bd17386d12381f88ba11e75704ff5e4a933188` |
| pony/run_20261009_012143_577818.json | 7529538 | `45f1cc3560200033255859b1f4f0e1fbfe65af7a13156d1857bf9b0eee43f86d` |
| pony/….0_bm25.trec | 517197 | `da64d328be9c2539831d265d8e414837fdd00605d32e8929cd7203c2bb624806` |
| pony/….1_dense.trec | 553411 | `acbb1ccac10d33b64ec9d56fb15dca21043053b077eeaa3b3c4743081cbb4398` |
| pony/….2_…_C2Bench10MShipped.trec | 331891 | `3e63447758965fd7e2120a43c161c17dec2ab55859a670c5bb147e94a7fd4575` |
| pony/….3_…_C2Bench10MK100.trec | 594283 | `55d25d39ca31be7645ba03e24812a799f6d261253a20c25a8d554662ebb33561` |

Frozen rung queries: `TA/tl-eval/evidence/scale10m-2026-10-04/
trace-scale10m-queries.json`, 48754883 B, `5222b2e5…`.

Campaign-186: `receipts/` 31 dirs (`r000-004` … `r120-124`, 1984
receipts total per the verdict) + `vm-green/` (`green.log`,
`cap03-battery-green.json`, `cap03-battery-red-curated.json`,
`vm-sha256.txt`) at `/home/anshul/trace-ops/campaign-186/`; small
evidence + code mirrored at
`gs://tl-m2-runs-d1995b06/m2/lane-bench10m/` (reported location).
