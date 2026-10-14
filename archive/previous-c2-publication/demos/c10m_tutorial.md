# C2-10M Narrow demo tutorial

Static text equivalent of [c10m_inspector.html](c10m_inspector.html): the same
content as Markdown, for readers who prefer plain text or cannot render HTML.
It walks through the primary demo `demo_c10m_narrow.py` — the pinned C2-10M
freeze-v2 serving stack answering queries over a 6-document synthetic corpus.

## 1. Run it

```bash
pip install -e .[c10m]
python demos/demo_c10m_narrow.py
```

Expected verdict:

```text
DEMO PASS: pinned C2-10M serving stack ran offline (6 synth docs, 3 queries, budgets M80-P100-A40).
```

Linux/POSIX only (the pinned store uses `fcntl` locking). Fully offline and
deterministic; exits nonzero on any failed check. Options: `--data-dir DIR`
(reuse a store), `--keep`, `--quiet` (verdict only), `--out FILE` (results JSON).

## 2. Pipeline

1. Verify c10m pins — every packaged byte checked against `c10m/PINS.sha256`.
2. Assemble runtime — `c10m/producer/` plus the `c10m/serving/` overlay merged
   into a temp dir (serving `query.py` re-verified as `d7756e72…` at import).
3. Ingest 6 docs — pinned `TLStore` + `ingest_docs` over the fixture below.
4. Build Narrow index — pinned `NarrowIndex` on the fresh store pin.
5. Run 3 queries — pinned `NarrowQuery` at budgets M80-P100-A40.
6. Check receipts — every query must return `status=complete`; top-1 doc ids
   and score floors/ceilings asserted (fixture-specific harness checks).

## 3. Corpus

Fixture: [c10m_synth_docs.jsonl](fixtures/c10m_synth_docs.jsonl) (synthetic,
public-domain placeholder text written for this demo).

| doc_id  | text                                                                               |
|---------|------------------------------------------------------------------------------------|
| syn-001 | The wug test measures how children generalize plural rules to novel words.         |
| syn-002 | Photosynthesis in desert succulents uses crassulacean acid metabolism at night.    |
| syn-003 | The treaty of Tordesillas divided newly discovered lands between Portugal and Spain. |
| syn-004 | Quantum error correction protects logical qubits with redundant physical qubits.   |
| syn-005 | Sourdough starter fermentation relies on wild yeast and lactobacillus cultures.    |
| syn-006 | The wug experiment was designed by Jean Berko Gleason in nineteen fifty eight.     |

Observed ingest: `atoms=6 holons=6 skipped=[]`, store triple
`<birth-uuid>:0:18` (birth UUID is fresh per run; counts are deterministic).

## 4. Queries and receipts

Pre-rendered from a real run (see also `--out`). Every query returned
`status=complete`, `support=supported-results`.

Reproducibility note: doc ids, scores, spans, returned order, status, and
support are stable across fresh runs. The store birth UUID / pin and the
per-entry `atom_id` hashes are fresh-store identities: they vary run to
run, are preserved verbatim in saved `--out` JSON, and must be compared
semantically (per the stable fields above), never byte-compared.

Query 1: `Who designed the wug experiment?`

| rank | doc_id  | score  | span    |
|------|---------|--------|---------|
| 1    | syn-006 | 0.025  | [0, 78] |
| 2    | syn-003 | 0.0242 | [0, 84] |
| 3    | syn-001 | 0.0246 | [0, 74] |

Query 2: `What protects logical qubits?`

| rank | doc_id  | score  | span    |
|------|---------|--------|---------|
| 1    | syn-004 | 0.025  | [0, 80] |
| 2    | syn-001 | 0.0082 | [0, 74] |
| 3    | syn-002 | 0.0081 | [0, 79] |

Query 3 (off-topic): `completely unrelated zebra query about astrophysics`

| rank | doc_id  | score  | span    |
|------|---------|--------|---------|
| 1    | syn-001 | 0.0083 | [0, 74] |

Harness checks: topical top-1 doc ids (`syn-006`, `syn-004`), topical floor
0.020, off-topic ceiling 0.015. These thresholds are fixture-specific harness
checks, not product claims; the off-topic low score is recorded signal, not
an abstention verdict.

## 5. What this does not show

Encoder stand-in: the shipped stack encodes with MiniLM-L6-v2 (weights +
torch, not vendored); the demo uses a deterministic SHA-256 token-hash
encoder (384-dim raw counts, same "raw vectors, cosine downstream"
convention). Scores and ranking here are properties of the stand-in encoder
on a 6-doc fixture and are NEVER 10M measurements. What the demo proves is
that the pinned ingest/index/query code paths run end to end.

The 10M evidence (frozen Narrow rung, BENCH10M lanes, store probes, campaign
receipts) lives under `benchmarks/evidence/` with its original denominators,
units, and failures preserved. The full input-reconstruction recipe
(upstream fetch + selection maps reproducing the exact 64 MB build input)
lives under `c10m/data/` with its dataset-specific license notices.

Pinned bytes: serving `query.py`
`d7756e72e2de65814103e216edfc7d53650cc0fada34cefe7cf41411f03414ce`;
budgets M80-P100-A40. See `c10m/README.md` for full pins.
