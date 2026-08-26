# Subagent and Delegation Rules

Subagents are allowed to reduce latency and improve review quality, but they
do not dilute ownership or authority. The primary session remains responsible
for the final code, data, tests, and handoff.

## General rules

1. Give each subagent one written micro-task with a bounded output.
2. Pass the relevant global context, packet, base identity, and forbidden paths.
3. Require a short durable report or message containing commands, observations,
   limitations, and artifact hashes.
4. Never assign two writers the same file or schema migration.
5. Do not let a subagent silently expand the parent packet.
6. A subagent may recommend a decision but cannot record human acceptance.
7. A verifier subagent cannot edit the implementation under test.
8. Download workers may write only their reserved dataset directory and its
   temporary files; the primary data session owns the manifest.

## Safe subagent roles

### Repository observer

Read-only identity/status/source mapping. It may calculate hashes and list
protected paths. It must not clean, reset, stash, or edit.

### Test designer

Drafts cases and expected receipts from the packet. It may run read-only or
isolated tests, but does not alter production code.

### Implementation helper

May edit a disjoint, explicitly leased path only when the parent packet allows
it. The parent must review the diff and own the final commit.

### Data acquisition worker

Downloads one named official source to a reserved external directory using
strict TLS. It records source metadata and stops on checksum/license ambiguity.

### Evidence reviewer

Checks query IDs, source mappings, statistics, and claim wording. It cannot
promote a run or modify a release manifest.

## Session-specific delegation budgets

| Session | Recommended helpers | Forbidden delegation |
| --- | --- | --- |
| S0 | packet/state observer; dependency reconciler | any product-code writer |
| S1 | fallback audit; packaging/test-matrix reviewer | dataset downloader or Trace/TL editor |
| S2 | lifecycle test designer; source-anchor reviewer | graph-budget setter or Spine editor |
| S3 | snapshot integrity reviewer; migration/schema reviewer | original dirty checkout editor |
| S4 | one worker per disjoint dataset directory; license/checksum reviewer | benchmark source editor |
| S5 | independent case runners and receipt parser | implementation repair |
| S6 | query-class/statistics reviewers | threshold approver or self-certifier |
| S7 | corpus partitioner; resource observer | premature 1M/10B claim writer |

## Concurrency rules

- Parallel work is safe only when paths, databases, ports, provider identities,
  and output directories are disjoint.
- One session must serialize migrations, release-pointer activation, Git
  initialization, and manifest publication.
- Test databases and caches must use unique external paths and names.
- Do not run two workers against one mutable SQLite file or one active release
  pointer.
- If a helper reports a conflict, stop and return the conflict to the parent;
  do not resolve it by deleting files.

## Required parent review

Before accepting subagent output, the parent checks:

- the helper used the declared base and environment;
- no forbidden path changed;
- claims match the evidence level;
- hashes and IDs are reproducible;
- failures and unavailable capabilities were not hidden;
- the result is integrated into the packet handoff.
