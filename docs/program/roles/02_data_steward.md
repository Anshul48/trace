# Role 2 — Data Steward

## Mission

Acquire or prepare real benchmark sources in a reproducible, license-aware
way, without allowing unavailable sources to degrade into synthetic
certification data.

## Primary outputs

- dataset records and license summaries,
- checksum-pinned acquisition instructions,
- local staging-layout proposals,
- transform and segmentation manifests,
- source-quality and access-risk notes.

## Broad workflow

1. Translate an evaluation need into explicit dataset requirements.
2. Verify official source, license, version, access method, and expected size.
3. Download only when a task packet authorizes the specific source.
4. Store raw material in an approved external cache, never as an implicit Git
   artifact.
5. Emit hashes, source metadata, transformations, and failure diagnostics.
6. Hand off a verified manifest to the evaluation engineer.

## Boundary conditions

- A missing download is a failed prerequisite, not permission to substitute a
  tiny sample or synthetic corpus.
- Private downstream data remains external and is referenced by path/checksum
  only.
- License, redistribution, PII, and retention questions are escalated before
  use.

## Prohibited actions

- Do not alter retrieval code to make a dataset fit.
- Do not publish or commit raw restricted data.
- Do not label an unverified adapter or unavailable source as benchmark-ready.

## Handoff standard

Return one dataset record per source plus a reproducible staging report and
known limitations.

## Dataset admission workflow

1. Receive a target query class and proof lane from the evaluation packet.
2. Identify official source locations and compare candidate versions/licenses.
3. Verify that corpus, queries, and judgments can be linked without inventing
   relevance labels.
4. Define a deterministic acquisition and staging procedure.
5. Download only after packet authority is explicit.
6. Compute archive and normalized-content hashes.
7. Record transform/segmentation details and expected counts.
8. Hand the record to the evaluation engineer for acceptance or exclusion.

## Required dataset record fields

| Group | Required detail |
| --- | --- |
| Identity | Stable ID, official name, source URL, release/version, maintainer. |
| Rights | License, attribution, redistribution, access, privacy/PII, retention. |
| Content | Archive checksum, normalized checksum, expected documents/queries/judgments. |
| Staging | Approved external cache path, fetch command, verification command, timestamp. |
| Transform | Parser, cleaning, segmentation, atomization, mapping to source anchors. |
| Evaluation | Query classes, metric suitability, baseline relevance, exclusions. |
| Risks | Availability, format drift, licensing uncertainty, known bias/limitations. |

## Staging layout

Use an explicit external root selected by the packet, conceptually:

~~~text
<benchmark-data-root>/
  downloads/<dataset-id>/<version>/
  normalized/<dataset-id>/<transform-hash>/
  manifests/<dataset-id>/<version>/
  logs/<dataset-id>/<acquisition-run-id>/
~~~

The version-controlled registry stores identifiers and hashes, never a hidden
dependency on the developer's absolute path.

## Candidate-portfolio balance

The initial portfolio should cover distinct claims rather than maximize the
number of adapters:

- lexical and semantic retrieval;
- multi-hop evidence assembly;
- temporal/revision or update behavior;
- hierarchy/long-context organization;
- abstention and no-evidence cases;
- a real source corpus for 100K recovery and resource evidence;
- a small, reviewer-frozen downstream pack kept external to the repository.

## Data-steward acceptance and stop criteria

Accept a source for evaluator use only when source, rights, checksum, transform,
and intended evidence lane are explicit. Stop and escalate when a license is
ambiguous, a source has disappeared, a corpus cannot support its claimed query
type, or an adapter would need a synthetic/sample fallback to appear usable.
