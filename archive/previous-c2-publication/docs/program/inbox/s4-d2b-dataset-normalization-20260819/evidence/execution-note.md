# S4 D2b execution note

## Objective

Build a new, versioned external normalized-data candidate for the seven
DEC-P-001 staged datasets. Preserve source truth and native identifiers,
produce reversible judgment/evidence maps, and stop or exclude records when
the source cannot support the requested mapping.

## Allowed mutation

- `C:\Users\anshu\AppData\Local\trace-bench-data\normalized\d2b-20260819\`
- `C:\Users\anshu\AppData\Local\trace-bench-data\verification\d2b-20260819\`
- This packet-local inbox directory for handoff/evidence only.

Raw directories, source metadata, Trace, Trace-Lite, trace-bench, and global
program-control documents are protected.

## Inputs pinned

- B1.1 successor: `dcd32396f6430e6865176f053a3ce57112db6df3`.
- B1 dataset schema: `schema.py`, SHA-256
  `a08918851cdeb32badbc2e732608d61763c3befd303291724fa86064218ae831`.
- D2a portfolio manifest: SHA-256
  `4e594992929c233ec4c95ad0541c09ae54a4e4e0b2d34c48d5ca910dcb0d41c5`.
- Raw metadata root: expected SHA-256
  `872102e2edfa41954f80dd55ce592a4bdfa5937ce2c58aec6480aa094504c2df`.

## Planned outputs

Each text dataset receives a manifest, normalized corpus/query records,
native-ID maps, judgment/evidence maps, split/query-class records,
normalization configuration, content hashes, duplicate/malformed/ambiguity
reports, exclusions, retention review, and reproduction log. BigANN receives
an operations/vector-only manifest and file/hash inventory; it does not enter
text evidence evaluation.

## Acceptance and stop conditions

Validate raw hashes, schema, uniqueness, split leakage, duplicates, malformed
records, rights, mappings, and round trips. No atom IDs are emitted because no
named ingest/chunking artifact exists in the pinned inputs. A source without a
usable document-level or source-provided segment mapping is explicitly
excluded or blocked. Any output-root collision, raw drift, or failed
reproduction stops the packet without activating or deleting anything.

## Delegation

No write subagents are used for the first pass. Dataset workers would require
disjoint output directories and a parent review; the primary normalization
runner owns all manifests and reconciliation.
