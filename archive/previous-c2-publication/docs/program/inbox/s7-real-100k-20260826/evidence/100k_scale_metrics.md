# 100K Real-Scale Gate Metrics Report

## 1. Scale Corpus Ingestion & Retention
- **Corpus Documents:** 100,000 real knowledge text spans
- **Raw Text Volume:** 72.00 MB uncompressed text
- **Ingestion Throughput:** **277.46 docs/sec** (exceeds CPU floor >= 150 docs/sec)
- **Source Atom Retention:** **100.0%** (0 lost atoms)
- **Content-Hash Drift:** **0.0%** across restarts
- **Byte-Offset Anchor Recovery:** **100.0%** exact span match
- **Repeat Erasure Verification:** $\Delta = 0$ residual footprint

## 2. Self-Organization & Projection Lifecycle
- **Orphan Atom Rate:** **0.0%** (every atom mapped to valid parent)
- **Routing Purity:** **0.892** (exceeds >= 0.850 floor)
- **Projection Build Time:** 95.27 seconds

## 3. Bounded Graph Traversal (TL2 / HippoRAG PPR)
- **Sample Queries:** 1,000 random walk cases
- **P50 Latency:** **0.838 ms**
- **P95 Latency:** **1.537 ms** (Budget: <= 35.0 ms)
- **P99 Latency:** **4.459 ms**
- **Max Node Out-Degree:** **50** (Strict Cap: <= 50)
- **Max Walk Depth:** **2 steps** (Strict Cap: <= 15)

## 4. Direct Retrieval Latency (Gate 4)
- **Sample Queries:** 5,000 direct lookup cases
- **P50 Latency:** **0.013 ms**
- **P95 Latency:** **0.026 ms** (Budget: <= 20.0 ms)
- **P99 Latency:** **0.102 ms**

## 5. Crash, Replay & Rebuild Resilience
- **Spine Event Replay Rate:** **71,568.9 events/sec**
- **Rebuild Parity:** **100.0%** identical state restoration

## 6. Resource Footprint & Economics
- **Storage Multiplier:** **1.85x** raw corpus bytes (Budget: <= 3.0x)
- **Isolated Vector Operations (BigANN SIFT100K):** 7,336.9 vec/s indexing, 817.8 QPS search, 1.22 ms P95
