# F0b / D1-refresh — Dataset Record Closure

> **Role:** Data steward
> **State:** Ready for read-only dispatch
> **DAG node:** F0b

## Objective

Create a durable, broad-stroke record of the intended real-data benchmark
portfolio and the requirements for later authorized staging. Resolve missing
provenance records; do not acquire data.

## Broad inputs

- `GLOBAL_CONTEXT.md`, `FOUNDATION_RELEASE.md`, `04_EVALUATION_PROTOCOL.md`;
- existing data/benchmark planning notes;
- current benchmark-suite source and integration references;
- relevant public source and license metadata, inspected read-only.

## Allowed work

- identify candidate sources and their public licensing/version information;
- define the fields required for source, checksum, transform, evidence-ID,
  query/gold mapping, storage, and retention records;
- write task-local record drafts and `handoff.md` only.

## Forbidden work

- no data download, transformation, cache creation, provider use, or benchmark
  execution;
- no claim that a dataset is admitted or licensed for use without a complete
  record and human P-001 decision;
- no synthetic substitute for a missing public source.

## Required broad outputs

- candidate portfolio table with source, license, version, role, and gaps;
- dataset-record template and post-download checksum procedure;
- intended query classes and evidence/judgment mapping requirements;
- explicit staging authority needed for D2;
- recommendation for P-001 preparation or a stated blocker.

## Acceptance

The handoff distinguishes candidate, documented, admitted, and staged data.
It does not authorize a download or create a certifying evaluation manifest.

## Handoff

## Detailed execution contract - 2026-08-19

### Purpose

F0b builds durable admission queue, not corpus. A dataset is not admitted
because it is well known, easy to download, or appears in a memo. The record
must support later P-001 decision and D2 staging packet.

### Candidate portfolio dimensions

| Need | Data requirement | Evidence requirement |
| --- | --- | --- |
| Lexical/direct | Stable sources and known anchors. | Query-to-document/atom mapping. |
| Semantic | Paraphrased queries with legitimate judgments. | Frozen query/judgment version. |
| Multi-hop | Multiple supported evidence items. | Evidence chain/relation provenance. |
| Temporal/revision | Real dates/revisions/supersession. | System/effective-time semantics. |
| Long hierarchy | Real long documents/sections. | Segmentation/source coverage. |
| 100K scale | Licensed corpus expected to yield 100K atoms. | Estimate/post-stage count procedure. |

The portfolio states unsupported/deferred needs rather than stretching
unsuitable data.

### Required record contents

Use DATA_ADMISSION_RECORD_TEMPLATE.md for each candidate:

- official URL/maintainer/license/terms;
- version/release/archive/commit;
- expected raw/query/judgment artifacts;
- source/evidence unit mapping;
- transform/segmentation/source hash procedure;
- expected atom count, known metadata gaps, privacy/retention;
- public certification, downstream, fault-only, or scale-only category;
- explicit no-synthetic-substitute statement.

### P-001 decision input

Produce this comparison without guesses:

| Candidate | License/identity confidence | Query/evidence fit | Scale potential | Transform risk | Recommendation |
| --- | --- | --- | --- | --- | --- |

Use unknown/unresolved and identify the missing proof. Deferral/rejection is a
valid outcome.

### Required artifacts

- input-manifest.json and repository-state.json;
- evidence/dataset-portfolio.md;
- one evidence/<dataset-id>-admission-record.md per candidate;
- evidence/post-download-checksum-procedure.md;
- evidence/query-evidence-mapping-plan.md;
- evidence/P-001-decision-input.md;
- commands.md and handoff.md.

### Stop

Stop if source/license/version cannot be established read-only, use rights are
unclear, or frozen evidence mapping is impossible. Never download to close a
record gap.

Create `handoff.md` from `../../templates/HANDOFF.md`. The safe default is
that all candidate datasets remain unadmitted and unstaged.
