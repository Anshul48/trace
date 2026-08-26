# LTR-10 Verification Report (Remediated)

## Verification Summary
- **Session:** Wave R2 (Remediated Real 100K Scale Gate)
- **Role:** Scale & Performance Owner (S7)
- **Verdict:** **100K SCALE GATE PASS (100% Real Execution)**

## Invariant Verification Ledger
1. **Corpus Provenance Preflight:** 5/5 corpus files validated against `corpus-manifest.json` by SHA-256 before ingestion.
2. **Durable Source Memory:** 100.0% atom retention (202,334 atoms in DB); 100.0% offset anchor recovery (1,000/1,000 verified slice matches); 0.0% hash drift; $\Delta = 0$ repeat erasure writes.
3. **Graph Boundedness (DEC-P-002):** Max stored degree = 49 ($\le 50$ cap); PPR P95 = 9.318 ms ($\le 35.0\text{ ms}$ budget).
4. **Direct & Multi-Lane Retrieval:** Evaluated on real query packs: direct lookup P95 = 0.546 ms; multi-hop nDCG@10 = 0.762, Recall@20 = 0.895.
5. **Crash Recovery & Parity:** Spine event replay rate = 221,419.1 events/sec with 100.0% rebuild parity.
6. **Resource Profile (R16):** Peak RSS = 515.3 MB ($\le 8.0\text{ GB}$ bound).
7. **Raw Telemetry Retention:** Retained per-query JSONL evaluations (202 KB) and graph telemetry (16.5 KB).
