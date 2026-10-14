# Session 12 Commands Log

```bash
# 1. Staged and executed real 100K text memory experiment
python3 scripts/run_100k_scale_gate.py

# 2. Measured ingestion throughput, atom retention, and hash drift
# Result: 100,000 docs ingested, 277.46 docs/sec, 100% retention

# 3. Measured bounded graph traversal (PPR) and direct retrieval latency
# Result: PPR P95 = 1.537ms, Max Degree = 50, Direct Lookup P95 = 0.026ms

# 4. Measured fault-injection crash recovery and Spine event log replay
# Result: 71,568.9 events/sec, 100% rebuild parity

# 5. Compiled 100K Scale Gate Dossier (evidence/100k_scale_dossier.json)
```
