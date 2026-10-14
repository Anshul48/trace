# P0 acceptance row + v1.1 §2 Law table (verbatim source for auditors)

Source: `docs/program/TRACE_MASTER_STAGEWISE_EXECUTION_PLAN.md` v1.1
(`BALLOT-READY DRAFT v1.1`), `docs/program/TRACE_STAGED_EXECUTION_PROMPTS_V11.md`.

## Packet P0 acceptance row

- Mapping 100% resolved (every `source_file` hash-verified; fail closed).
- Merkle trio re-verified (base / delta / union recomputed from staged
  bytes equal manifest claims: 1M / 2,014,465,744 / `5039acef…`).
- Gate manifest signed (script + human co-signature in `06_DECISION_LOG.md`).
- Frozen BEIR green unchanged (Paste-A command 3, same output).

Attempt-1 result: row NOT met (9 delta-side mismatches) → truthful HOLD,
critic QUARANTINED (no violations). Attempt-2 result: seal boundary
repaired and independently verified; corpus itself still UNADOPTED —
successor `H0-1M-SUCCESSOR-SEL-01` awaits human ballot → critic APPROVED
(no violations), P0 stays quarantined until ballot.

## §2.1 Ratified law (L1–L7; cite, don't modify)

- L1: total-hot storage hard ceiling ≤3.0x admitted UTF-8 bytes.
- L2: durable Spine health signal ≤1.6x.
- L3: monotonic scale target ≤2.5x at 1M.
- L4: synchronous local ingest floor ≥800 docs/sec into SQLite WAL.
- L5: retrieved concept bundle capped 8–20 concepts.
- L6: BEIR floors + P95 tiers; Tier-2 PROMOTE iff paired 95% CI > 0
  (seed 42, 10k resamples).
- L7: abstention bar ≥90% with zero hallucination.

## §2.2 Amendment proposals (A1–A6; effective only on ballot ratification)

A1 hot-footprint sub-allocation; A2 ≈0.35x investigative tripwire;
A3 raw candidate depth k∈[10,100]; A4 Tier-4 reasoning lane P95 ≤800 ms;
A5 sleep-consolidation bounds (N≤250, lock p100 <15 ms, 8–20 holons);
A6 conformal calibration n_cal ≥ 100, apoptosis half-life 30 days.
This packet claims NO Amendment use.
