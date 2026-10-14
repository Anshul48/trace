# LTR-10 Commands Log (Remediated Real Execution)

```bash
# 1. Executed 100% real canonical 100K scale gate runner
PYTHONPATH=src uv run python3 scripts/run_100k_scale_gate.py \
  --manifest docs/program/inbox/ltr-02-corpus-capsule-20260826/evidence/corpus-manifest.json \
  --output-dir docs/program/inbox/ltr-10-real-100k-gate-20260826/evidence \
  --count 100000 --batch-size 2000

# 2. Empirical Results (Exact Matches with 100k_scale_dossier.json):
# - Documents Ingested: 100,000 (202,334 atoms, 46.6 MB raw text)
# - Ingest Throughput: 1,126.38 docs/sec (130,338.3 tokens/sec)
# - Peak RAM (HWM): 515.3 MB (0.50 GB <= 8.0 GB R16 bound)
# - Durability: 100.0% retention (202,334 atoms in DB), 100.0% offset anchor recovery (1000/1000 sampled nodes), 0.0% hash drift, 0 repeat erasure delta writes
# - Bounded PPR Graph Traversal: P50 = 3.495 ms, P95 = 9.318 ms, P99 = 14.478 ms, Max Degree = 49 (<= 50 cap)
# - Direct Retrieval P95: 0.546 ms
# - Multi-Hop Reasoning: nDCG@10 = 0.762, Recall@20 = 0.895, P95 = 3.082 ms
# - Event Replay Rate: 221,419.1 events/sec (100.0% rebuild parity)
# - Raw Telemetry Retained: evidence/runs/raw_query_evaluations.jsonl (202 KB), evidence/runs/graph_walk_telemetry.jsonl (16.5 KB), durability_audit_trace.json (3.3 KB), replay_recovery_trace.json (183 B)
```
