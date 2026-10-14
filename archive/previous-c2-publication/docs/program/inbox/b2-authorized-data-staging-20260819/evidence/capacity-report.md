# Staging Capacity Preflight & Allocation Report

**Timestamp:** 2026-08-19T07:25:41.997603+00:00
**Target Drive:** `C:\`
**Staging Directory:** `C:\Users\anshu\AppData\Local\trace-bench-data`

## Host Volume Free Space & Headroom Summary

| Metric | Bytes | Gigabytes | Status |
| :--- | :--- | :--- | :--- |
| **Total Host Volume Capacity** | 1,021,821,579,264 B | 951.65 GB | Nominal |
| **Pre-Acquisition Used Space** | 628,254,416,896 B | 585.11 GB | Nominal |
| **Pre-Acquisition Free Headroom** | 393,567,162,368 B | 366.54 GB | Available |
| **Total Staged Datasets Size (7 Datasets)** | 1,523,873,356 B | 1.42 GB (~1.20 GB payload) | Staged |
| **Post-Staging Free Headroom** | 392,043,288,902 B | 365.12 GB | Verified |
| **Headroom Utilization Rate** | 0.387% | Safe (< 1% of free space) | PASS |

## Staged Datasets Breakdown

| Dataset | File Count | Disk Size (Bytes) | Disk Size (MB) | Role / Admitted Lane |
| :--- | :--- | :--- | :--- | :--- |
| `beir-scifact` | 12 | 12,838,733 B | 12.24 MB | CC BY-NC 4.0 (SciFact) / Apache 2.0 (BEIR Benchmark) |
| `beir-nfcorpus` | 13 | 12,572,932 B | 11.99 MB | CC BY-SA 4.0 (NFCorpus) / Apache 2.0 (BEIR Benchmark) |
| `beir-fiqa` | 13 | 77,017,521 B | 73.45 MB | Research Evaluation License / CC BY-NC-SA 4.0 / Apache 2.0 (BEIR Benchmark) |
| `bright` | 18 | 392,814,334 B | 374.62 MB | CC BY 4.0 |
| `multihop-rag` | 8 | 11,992,137 B | 11.44 MB | ODC-By v1.0 |
| `musique` | 8 | 271,545,020 B | 258.97 MB | CC BY 4.0 |
| `bigann` | 12 | 745,092,679 B | 710.58 MB | CC0 1.0 Universal (Public Domain Dedication) |
| **Total** | **84** | **1,523,873,356 B** | **1,453.28 MB (~1.42 GB)** | **7 Admitted Datasets** |

## Assessment

Storage headroom is fully verified. Host volume free space prior to acquisition was 366.54 GB (393,567,162,368 B). The combined 7 staged datasets occupy 1,523,873,356 B (~1.42 GB uncompressed, ~1.20 GB payload), leaving >365.12 GB of free headroom on drive C: (<0.4% utilization). Staging completed safely with zero risk of resource starvation.
