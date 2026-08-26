# Prepared Packet: S1 Data — Real Benchmark and 100K Corpus Portfolio

> **State:** Prepared, unassigned
> **Role:** Data steward
> **DAG nodes:** D1, P-001
> **Mutation authority:** Research and registry artifacts only. Do not download
> any dataset until a separate packet explicitly grants source-specific authority.

## Objective

Create an admission-ready candidate portfolio of real, downloadable,
license-aware datasets and corpora for:

1. public retrieval evaluation;
2. multi-hop, temporal/revision, hierarchy, and abstention query classes;
3. a real 100K source-atom corpus;
4. an externally staged, reviewer-frozen downstream pack design.

The task does not declare any source benchmark-ready or download it.

## Required inputs

- Dataset registry and protocol documents/templates.
- Shared evaluation protocol, claim levels, risks, and decision P-001.
- Existing Trace-Lite benchmark README, matrix, adapters, runner, and fixtures.
- Workstream briefs for data and evaluation.

## Required audit

For every existing adapter or fixture that may be considered:

- inspect actual acquisition behavior rather than README labels;
- label it real, sample, synthetic, regression-only, incomplete, or unsupported;
- identify default fallback behavior and whether it could contaminate a release
  run;
- record source rights, version stability, query/judgment availability, and
  likely transform burden.

## Portfolio design

Propose a minimal balanced portfolio. For each candidate, fill a dataset-record
draft with:

- official source/version/license;
- intended evidence lane and query classes;
- source/judgment availability and identifier stability;
- reproducible staging approach and expected size;
- transform/atomization considerations;
- expected contribution to the 100K gate if relevant;
- known limitations and disallowed claims.

At least one candidate must be evaluated specifically as a real source corpus
capable of yielding 100K atoms under a declared transform; do not assume a
retrieval benchmark corpus will automatically meet that purpose.

## Required output

1. An adapter/fixture truth table.
2. A ranked candidate portfolio matrix.
3. One draft dataset record per candidate.
4. A proposed external cache/staging layout.
5. A download authorization queue with exact source, license, expected size,
   checksum method, and reason for acquisition.
6. A list of sources rejected or deferred and why.

## Acceptance criteria

- No raw data is downloaded or committed.
- Every proposed source has a clear primary source and license status.
- Dataset roles are not duplicated without an explicit reason.
- A missing/unavailable source has a fail-closed behavior.
- The portfolio distinguishes public evaluation, private held-out, and scale
  evidence rather than blending them.

## Stop conditions

Stop on unclear rights, PII/retention ambiguity, unavailable official source,
or a need to substitute synthetic/sample data for a stated certification role.

## Handoff

Return the registry drafts and a recommendation for the first one-to-three
source-specific download packets.
