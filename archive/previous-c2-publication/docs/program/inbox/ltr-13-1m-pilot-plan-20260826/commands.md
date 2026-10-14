# LTR-13 Commands Log

```bash
# 1. Re-anchored capacity model on certified 100K measurements (LTR-10 Dossier SHA-256: 9941639b9c0b04ae659d48745da333fed42a9dd1367849c7ef4cd2b9c8aad0cb)
# - Documents: 100,000 -> 1,000,000 (10x scaling factor)
# - Active Atoms: 202,334 -> ~2.02M atoms
# - Raw Source Text: 46.6 MB -> ~466 MB to 1.5 GB
# - Ingestion Throughput: 1,126.38 docs/sec baseline
# - Projected 1M Ingestion Runtime: ~14.8 minutes (single worker) / ~3.7 minutes (4 parallel workers)
# - Peak RAM Projection: ~4.8 GB (bounded by R16 profile <= 8.0 GB)
# - Replay Rate Baseline: 221,419.1 events/sec
```
