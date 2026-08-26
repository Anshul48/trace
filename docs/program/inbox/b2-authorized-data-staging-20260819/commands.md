# Execution Commands Log — S4 Real-Data Staging (B2 / D2a)

**Session:** S4  
**Packet:** `b2-authorized-data-staging-20260819`  
**Lease ID:** `lease-s4-d2a-20260819`  
**Date:** 2026-08-19  

## 1. System & Capacity Preflight
```powershell
Get-PSDrive C
python --version
uv --version
Test-Path "C:\Users\anshu\AppData\Local\trace-bench-data"
```
**Result:** Drive C: has 370.14 GB free capacity. Staging root exists and is writeable.

## 2. Dataset Acquisition & Layout Parsing
```powershell
python scratch/stage_all_admitted_datasets.py
```
**Result:**
- Acquired and verified BEIR SciFact (5,183 docs, 1,109 queries, 1,280 judgments).
- Acquired and verified BEIR NFCorpus (3,633 docs, 3,237 queries, 134,294 judgments).
- Acquired and verified BEIR FiQA (57,638 docs, 6,648 queries, 17,110 judgments).
- Acquired and verified BRIGHT coding and math subsets (928,750 docs, 752 queries across 6 subsets).
- Acquired and verified MultiHop-RAG (609 docs, 2,556 multi-hop queries, 6,104 evidence links).
- Acquired and verified MuSiQue (2,417 dev queries, 19,938 train queries with full decompositions).
- Acquired and verified BigANN / SIFT1M (1,000,000 base vectors, 10,000 query vectors, binary fvecs/ivecs).
- Enforced strict TLS verification (verify=True) across 100% of network requests.

## 3. Staging Integrity & Checksum Verification
```powershell
python scratch/verify_staging_integrity.py
```
**Result:**
- 7/7 datasets PASSED 100% checksum verification and structural file existence checks.
- Zero missing files, zero 0-byte files, zero checksum mismatches.
- Generated `evidence/portfolio-staging-manifest.json`.
- Generated `evidence/checksum-verification-receipt.md`.
- Generated `evidence/capacity-report.md`.
- Generated `evidence/layout-summary.md`.
