# Wave B Directives (Human-Approved 2026-09-03)

> **Authority:** Human Owner approvals given on the benchmark-annex review.
> Coordinator applies these to packets, leases, and dispatch order.
> **Placement note:** drafted in `launch/`; file the substance in the owning
> docs (packets, lease map, EVAL02 manifest task) with a control-plane relock.

## D1. SciFact count — verify at acquisition, default test/300

`WP-CAP-EVAL02` text "SciFact (1,000 queries)" is superseded. EVAL02 task:
download the canonical BEIR `scifact` archive, verify MD5
`5f7d1de60b170fc8027bb7898e2efca1`, assert test-split counts
(300 queries), and record actual counts in `beir_musique_frozen_v1.json`.
Any count mismatch is `data_prerequisite_failed`. The "1,000" figure must
not reappear unless a different named split/version totalling 1,000 is
pinned with its own checksum. Same verification applies to NFCorpus/323
(`a89dba18a62ef92f7d323ec890a0d38d`) and FiQA/648
(`17918ed23cd04fb15047f73e6c3bd9d9`) per the methodology annex §1.1.

## D2. Methodology annex binds EVAL02/EVAL03 now

`CAP_001_BENCHMARK_METHODOLOGY_ANNEX.md` §§1–5 are binding guidance for the
undispatched EVAL02 (frozen manifests + count rule) and EVAL03 (validator
calibration: adversarial rejection, ≥200-proposition dual adjudication with
κ ≥ 0.70, generator-independent NLI) packets. Ratified floors are unchanged;
only the measurement discipline is added. EVAL03 calibration receipts are
required before CRX03 or MOD01 consume the validator. Amendment items B1–B6
(annex §6) remain proposals for the CAP-GB human decision, not in force.

## D3. Lease order — JOB02 before CRX03

`service.py` / `store.py` overlap between WP-CAP-JOB02 and WP-CAP-CRX03 is
resolved by serialization: dispatch JOB02 first (branch
`cap-job02-recovery` from `cap-job01-pipeline`); CRX03 (`cap-crx03-activation`
from `cap-crx02-consolidator`) dispatches only after JOB02 merges or its
lease is formally released. Concurrent execution on these paths stays
forbidden per the lease map §3.2. The coordinator records lease
issue/release timestamps in the handoff.
