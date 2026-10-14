# Workstream 02 — Real Data and Staged Benchmark Inputs

> **Owner:** Data steward
> **Status:** Draft outline

## Intended outcome

Create a trustworthy, license-aware registry of real datasets and corpora that
can support public retrieval evaluation, held-out downstream evaluation, and
the real-corpus 100K gate.

## First work packages

1. Inventory existing benchmark adapters and distinguish real support from
   declared/sample/fallback support.
2. Select candidate public datasets by query class: direct retrieval, multi-hop,
   temporal/revision, hierarchy/long context, abstention, and broad thematic.
3. Identify one or more real source corpora suitable for 100K source-atom
   ingestion, recovery, and resource tests.
4. Record licenses, official sources, versions, expected size, checksums,
   transforms, and local staging requirements.
5. Define an external cache layout and reproducible fetch verification.

## Required inputs

- evaluation protocol and required query classes,
- existing benchmark documentation and adapters,
- storage/privacy and redistribution constraints,
- explicit authorization before each actual download.

## Expected artifacts

- one dataset record per candidate,
- ranked selection matrix and exclusion rationale,
- approved fetch/staging instructions,
- transform/segmentation manifest outline,
- missing-access and license-risk report.

## Exit condition

The evaluation engineer receives reviewed, checksum-pinned inputs with no
ambiguous fallback path.

## Stop conditions

Stop on unclear licensing, unavailable primary source, private-data exposure,
or a proposed substitution that would weaken the certification lane.

## Staged acquisition program

### D1.1 — Existing-adapter truth audit

Inventory each current benchmark adapter and label it:

- real source with verified acquisition;
- real source but unverified/unfinished adapter;
- sample/development fixture;
- synthetic/fault-only generator;
- deprecated or unsupported.

This audit must inspect actual runner behavior, not only README claims.

### D1.2 — Public retrieval portfolio

Select a minimal portfolio where every chosen source has a distinct purpose.
Do not select many near-duplicate datasets merely to increase benchmark count.
For each candidate, record retrieval task, judgment quality, license, download
reliability, expected preprocessing burden, and baseline compatibility.

### D1.3 — Real 100K source corpus

Identify a real, legally usable source corpus that can produce at least 100K
atoms under the declared transform. The source should exercise ingestion,
organization, graph construction, recovery, and storage behavior rather than
only answer short retrieval queries.

### D1.4 — Held-out downstream pack

Define the metadata and review process for a small external, frozen downstream
pack. Do not commit raw private content. Record stable query/evidence IDs,
checksums, authorization owner, and whether the pack is regression-only or
eligible for a later gate.

## Dataset selection scorecard

Score candidates qualitatively before downloading:

| Dimension | Questions |
| --- | --- |
| Legal | Is use, download, caching, transformation, and reporting permitted? |
| Provenance | Is there an official version and stable checksum path? |
| Task fit | Which query classes and evidence behavior does it actually test? |
| Judgment fit | Are labels suitable for retrieval/evidence metrics? |
| Scale fit | Can it contribute to a real 100K source-atom workload? |
| Reproducibility | Can another developer stage it without manual hidden steps? |
| Cost | What are download, storage, parsing, and provider implications? |
| Risk | Does it contain PII, unstable access, unclear rights, or format drift? |

## Required staging verification

After any authorized download, record:

1. exact command/tool and download timestamp;
2. source/archive checksum and file size;
3. normalized data checksum and record counts;
4. parser/transform version and configuration hash;
5. source-to-atom mapping statistics;
6. local cache path policy without committing the absolute private path;
7. failures, exclusions, and retry behavior.

## Data workstream exit

The workstream does not end with a list of URLs. It ends when the evaluator can
consume reviewed records into a pinned manifest, and an independent reviewer can
reproduce the staging process or identify exactly why it is unavailable.
