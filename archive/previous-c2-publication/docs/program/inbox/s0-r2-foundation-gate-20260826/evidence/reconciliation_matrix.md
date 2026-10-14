# Foundation Gate Reconciliation Matrix

| Gate / Sub-Gate | Target / Candidate | Verifier / Evidence | Status |
| :--- | :--- | :--- | :--- |
| **F-G0 Identity** | Runner `c0ea9fbf`, TL `3e7e9f0e`, Trace `f7bd96e9` | P-007 / P-008, Git tags, SHA-256 manifests | **PASS** |
| **F-G1 Runner Integrity** | `trace-bench` @ `c0ea9fbf` | Gate V1a (26/26 tests, offline cache, non-editable) | **PASS** |
| **F-G2 TL2 Graph** | Trace-Lite @ `3e7e9f0e` (Tree `ef83211...`) | Gate V1b-TL (34/34 tests, 8/8 boundary cases, 100K log) | **PASS** |
| **F-G3/4 Trace Temporal** | Trace @ `f7bd96e9` (Tree `91d93da...`) | Gate V1b-Trace (66/66 tests, migrations 001-007, Ed25519) | **PASS** |
| **F-G5 Data Staging** | 7 normalized datasets (D2b) | Gate D2b (134-file checksum map, round-trip verified) | **PASS** |
| **F-G6 Baselines & Floors** | 36,620 queries / 100K vectors | S6 Baselines, DEC-P-005 release floors, p < 0.01 | **PASS** |
| **F-G7 100K Readiness** | BigANN SIFT100K + Scale fetchers | 7,336 vec/s, 817.8 QPS, 1.22ms P95, >390GB headroom | **PASS** |
