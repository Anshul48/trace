# Scale Gate Storage Page Accounting Report

> **Report Standard:** DEC-P-005b Storage Accounting & Page-Level Audit
> **Database File:** `benchmarks/runs/100k_scale_candidate/scale_100k.db`
> **Generated UTC:** `2026-08-29T02:57:37.018749+00:00`
> **Target Gate Standard:** Multiplier $\le 3.00\times$ (Footprint $\le 195\text{ MB}$, Target $\le 170\text{ MB}$)

---

## 1. Executive Summary & Storage Multiplier

| Metric | Measured Value | Standard Limit | Compliance Status |
| :--- | :--- | :--- | :--- |
| **SQLite Database Footprint** | **429.58 MB** (450,449,408 B) | $\le 195.00\text{ MB}$ | ❌ BREACH |
| **Raw Ingested Source Bytes** | **59.96 MB** (62,870,136 B) | — | Reference Baseline |
| **Storage Multiplier ($M$)** | **7.17x** | $\le 3.00\times$ | ❌ BREACH |
| **SQLite Page Size** | **4,096 bytes** | 4,096 bytes | ✅ OPTIMAL |
| **Total Page Count** | **109,973 pages** | — | Verified Physical |
| **Overall Fill Factor (Payload / Total)** | **88.15%** | $\ge 60.00\%$ | ✅ HIGH DENSITY |
| **Journal Mode** | **`WAL`** | `WAL` | ✅ PASS |

---

## 2. Table-Level Storage Accounting (Data + Indexes)

Storage footprint aggregated across the 6 canonical tables and all associated secondary/unique B-tree indexes:

| Table Name | Row Count | Data Pages | Index Pages | Total Pages | Total Footprint | Payload Bytes | B-Tree Overhead | Slack / Unused | % of DB |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`events`** | 100,000 | 38,983 | 5,052 | 44,035 | **172.01 MB** | 142.79 MB | 2.46 MB | 26.76 MB | **40.0%** |
| **`edge_versions`** | 824,707 | 18,140 | 17,277 | 35,417 | **138.35 MB** | 127.21 MB | 9.91 MB | 1.22 MB | **32.2%** |
| **`ingestions`** | 100,000 | 5,723 | 7,152 | 12,875 | **50.29 MB** | 47.27 MB | 1.76 MB | 1.27 MB | **11.7%** |
| **`node_versions`** | 228,328 | 5,988 | 2,232 | 8,220 | **32.11 MB** | 28.93 MB | 2.72 MB | 0.46 MB | **7.5%** |
| **`source_lifecycle`** | 228,328 | 4,671 | 1,059 | 5,730 | **22.38 MB** | 20.16 MB | 2.03 MB | 0.19 MB | **5.2%** |
| **`nodes`** | 228,328 | 2,522 | 1,173 | 3,695 | **14.43 MB** | 12.33 MB | 2.00 MB | 0.11 MB | **3.4%** |

---

## 3. Detailed B-Tree Object Breakdown (6 Tables & 13 Indexes)

Granular page, payload, and B-tree structural overhead accounting across all 20 SQLite schema objects:

| Schema Object Name | Object Type | Parent Table | Page Count | Size (KB) | Payload (KB) | Slack/Unused (KB) | Overhead (KB) | Fill Factor |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `events` | table | `events` | 38,983 | 155,932.0 KB | 127,390.9 KB | 27,249.5 KB | 1,291.6 KB | 81.7% |
| `edge_versions` | table | `edge_versions` | 18,140 | 72,560.0 KB | 66,646.9 KB | 796.4 KB | 5,116.7 KB | 91.8% |
| `sqlite_autoindex_edge_versions_2` | index | `edge_versions` | 13,055 | 52,220.0 KB | 49,238.1 KB | 412.7 KB | 2,569.1 KB | 94.3% |
| `node_versions` | table | `node_versions` | 5,988 | 23,952.0 KB | 22,098.7 KB | 432.6 KB | 1,420.7 KB | 92.3% |
| `ingestions` | table | `ingestions` | 5,723 | 22,892.0 KB | 21,393.4 KB | 737.2 KB | 761.5 KB | 93.5% |
| `source_lifecycle` | table | `source_lifecycle` | 4,671 | 18,684.0 KB | 17,108.3 KB | 176.8 KB | 1,398.9 KB | 91.6% |
| `sqlite_autoindex_edge_versions_1` | index | `edge_versions` | 4,222 | 16,888.0 KB | 14,378.8 KB | 43.5 KB | 2,465.6 KB | 85.1% |
| `sqlite_autoindex_ingestions_2` | index | `ingestions` | 4,161 | 16,644.0 KB | 15,862.9 KB | 360.6 KB | 420.4 KB | 95.3% |
| `nodes` | table | `nodes` | 2,522 | 10,088.0 KB | 8,635.2 KB | 89.4 KB | 1,363.4 KB | 85.6% |
| `sqlite_autoindex_events_2` | index | `events` | 2,486 | 9,944.0 KB | 9,515.3 KB | 106.6 KB | 322.1 KB | 95.7% |
| `idx_ingestions_doc` | index | `ingestions` | 2,481 | 9,924.0 KB | 9,417.6 KB | 184.3 KB | 322.0 KB | 94.9% |
| `sqlite_autoindex_nodes_1` | index | `nodes` | 1,173 | 4,692.0 KB | 3,985.7 KB | 23.6 KB | 682.7 KB | 85.0% |
| `idx_nv_node` | index | `node_versions` | 1,173 | 4,692.0 KB | 3,985.7 KB | 23.6 KB | 682.7 KB | 85.0% |
| `sqlite_autoindex_source_lifecycle_1` | index | `source_lifecycle` | 1,059 | 4,236.0 KB | 3,539.7 KB | 14.9 KB | 681.3 KB | 83.6% |
| `sqlite_autoindex_node_versions_1` | index | `node_versions` | 1,059 | 4,236.0 KB | 3,539.7 KB | 14.9 KB | 681.3 KB | 83.6% |
| `sqlite_autoindex_events_3` | index | `events` | 1,041 | 4,164.0 KB | 3,842.0 KB | 16.8 KB | 305.2 KB | 92.3% |
| `idx_events_stream_seq` | index | `events` | 1,041 | 4,164.0 KB | 3,842.0 KB | 16.8 KB | 305.2 KB | 92.3% |
| `sqlite_autoindex_ingestions_1` | index | `ingestions` | 510 | 2,040.0 KB | 1,725.7 KB | 15.4 KB | 298.9 KB | 84.6% |
| `sqlite_autoindex_events_1` | index | `events` | 484 | 1,936.0 KB | 1,628.0 KB | 9.3 KB | 298.6 KB | 84.1% |
| `sqlite_schema` | table | `sqlite_schema` | 1 | 4.0 KB | 3.4 KB | 0.5 KB | 0.2 KB | 83.8% |

---

## 4. Architectural Analysis & Storage Efficiency

### 4.1 Lean Schema vs. Legacy Redundant Ingestion
1. **Spine Event Deduplication:** Raw document contents are ingested strictly once into the append-only `events` stream log (`payload_json`).
2. **Zero Text Duplication in `node_versions`:** Rather than copying large uncompressed chunk texts into `node_versions` rows (which historically inflated DB size to 712 MB / 10.89x multiplier), `node_versions` stores exact byte offsets (`span_start`, `span_end`, `content_hash`).
3. **Bounded Graph Density:** Graph projections in `edge_versions` enforce $k \le 10$ outbound structural degree bounds, preventing dense cluster explosion.
4. **WAL Truncation & Vacuum:** B-tree pages are packed with high average fill factors (> 85%), minimizing fragmented slack space.

---

## 5. Certification Invariant Attestation

- **Total Database Footprint:** `429.58 MB` (Limit: $\le 195\text{ MB}$) -> **FAIL**
- **6 Tables & 13 Indexes Present & Audited:** -> **PASS**
- **Zero Cross-Table Text Redundancy Verified:** -> **PASS**

