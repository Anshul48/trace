# Staging & Checksum Verification Receipt

**Execution Timestamp:** 2026-08-19T07:25:41.970188+00:00  
**Staging Root:** `C:\Users\anshu\AppData\Local\trace-bench-data`  
**Admission Authority:** `DEC-P-001`  
**Overall Result:** ALL 7 DATASETS PASSED  
**Total Datasets Evaluated:** 7  
**Passed:** 7  
**Failed:** 0  

## Dataset Verification Breakdown

| Dataset | Status | Files | Total Size | Checksums Manifest SHA-256 | Source Record SHA-256 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `beir-scifact` | **PASSED** | 12 | 12,838,733 B | `1e7212f8129b43c7...` | `f01c5974b4d8f614...` |
| `beir-nfcorpus` | **PASSED** | 13 | 12,572,932 B | `6addfda4000f76bb...` | `91999ba50512484d...` |
| `beir-fiqa` | **PASSED** | 13 | 77,017,521 B | `2f7f53270b99b3bc...` | `4f087ca889c392fa...` |
| `bright` | **PASSED** | 18 | 392,814,334 B | `571f263528aa4987...` | `dd9a1f59fe3197fc...` |
| `multihop-rag` | **PASSED** | 8 | 11,992,137 B | `03840769c0155839...` | `abed91a52423b236...` |
| `musique` | **PASSED** | 8 | 271,545,020 B | `f60784cba98436b2...` | `0bfe4bb550498ba2...` |
| `bigann` | **PASSED** | 12 | 745,092,679 B | `f1763d7fbe104d6f...` | `3093ec439b32b823...` |

## Verification Rules Checked

- [x] Strict TLS verification enforced during all network transfers (verify=True).
- [x] SHA-256 checksums computed and verified for 100% of archive and extracted files.
- [x] All 6 required layout elements present for each dataset (`raw/`, `source-record.json`, `checksums.json`, `LICENSE-or-rights-notice.txt`, `layout-observation.json`, `acquisition-log.md`).
- [x] Dangling 0-byte archive artifact `raw/scifact.zip` removed; clean 12-file layout verified.
- [x] Native document and query IDs preserved without mutation or synthetic substitution.
- [x] Zero product code or benchmark harness code modified.
- [x] Raw data staged exclusively in external storage outside Git.
