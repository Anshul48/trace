# Wave, DAG, and Gate Matrix

This file is the execution order for the implementation wave. A dependency is
hard: downstream work must not begin merely because an upstream agent says it
is “mostly done.” The required handoff and verifier evidence must exist.

## DAG

```text
                                     ┌──────────────┐
                                     │ S0 / D0      │
                                     │ decisions    │
                                     │ leases       │
                                     └──────┬───────┘
                                            │
       ┌────────────────────────────────────┼────────────────────────────────────┐
       │                                    │                                    │
       ▼                                    ▼                                    ▼
┌──────────────┐                    ┌──────────────┐                    ┌──────────────┐
│ S1 B0        │                    │ S2 L1        │                    │ S3 T0        │
│ bench Git    │                    │ TL lifecycle │                    │ Trace freeze │
└──────┬───────┘                    └──────┬───────┘                    └──────┬───────┘
       │                                    │                                    │
       ▼                                    ▼                                    ▼
┌──────────────┐                    ┌──────────────┐                    ┌──────────────┐
│ S1 B1        │                    │ S2 TL3       │                    │ S3 TR1       │
│ fail-closed  │                    │ proof        │                    │ Cortex root  │
└──────┬───────┘                    └──────┬───────┘                    └──────┬───────┘
       │                                    │                                    │
       ▼                                    ▼                                    ▼
┌──────────────┐                    ┌──────────────┐                    ┌──────────────┐
│ S5 V1a       │                    │ P-002        │                    │ P-004        │
│ runner tests │                    │ human gate   │                    │ human gate   │
└──────────────┘                    └──────┬───────┘                    └──────┬───────┘
                                            │                                    │
                                            ▼                                    ▼
                                     ┌──────────────┐                    ┌──────────────┐
                                     │ S2 TL2       │                    │ S3 TR2       │
                                     │ bounded graph│                    │ temporal     │
                                     └──────┬───────┘                    └──────┬───────┘
                                            │                                    │
                                            └────────────────┬───────────────────┘
                                                             ▼
                                                   ┌────────────────┐
                                                   │ S5 V1b         │
                                                   │ lifecycle/Trace│
                                                   └───────┬────────┘
                                                           │
       ┌───────────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐       ┌──────────────┐       ┌────────────────┐
│ S4 D2a       │──────>│ S4 D2b       │──────>│ S6 P-005/B3    │
│ raw sources  │ B1    │ normalize    │       │ evidence/gate  │
└──────────────┘       └──────────────┘       └───────┬────────┘
                                                       │
                                                       ▼
                                             ┌────────────────────┐
                                             │ Foundation Gate     │
                                             └──────────┬─────────┘
                                                        │
                                                        ▼
                                             ┌────────────────────┐
                                             │ S7 real 100K gate  │
                                             └──────────┬─────────┘
                                                        │
                                                        ▼
                                             ┌────────────────────┐
                                             │ S7 1M pilot plan   │
                                             └────────────────────┘
```

## Waves

### Wave 0: control-plane preparation

S0 reconciles decisions, current source identities, protected paths, packet
states, worktree leases, and input manifests. It may write only program
control-plane artifacts.

### Wave 1: independent foundations

Start S1 B0, S2 L1, S3 T0, and S4 D2a after S0's handoff. They use disjoint
worktrees and directories. Data acquisition does not edit benchmark code.

### Wave 2: first implementations

S1 proceeds to B1 after B0. S3 proceeds to TR1 after T0. S4 continues raw
staging. S5 may begin V1a only after B1's implementation handoff and a fresh
verifier lease.

### Wave 3: measured and decision-gated work

S2 produces TL3 evidence and a P-002 measurement brief. S3 produces a P-004
brief after TR1. D2b begins only after B1 publishes the accepted manifest
contract. S5 runs the applicable V1b lifecycle sub-gates.

### Wave 4: release evidence

S6 prepares P-005 from real baseline data and assembles B3. The verifier closes
remaining V1b sub-gates. The coordinator decides whether the Foundation Gate
is complete.

### Wave 5: scale

S7 admits a real 100K text-memory corpus and measures correctness, recovery,
latency, resource use, and cost. A 1M pilot is planned only if 100K passes.

## Transition matrix

| Transition | Required evidence | Human/coordinator condition |
| --- | --- | --- |
| D0 -> Wave 1 | decision record, current input manifest, leases | S0 handoff accepted |
| B0 -> B1 | source-only Git commit, tag, clone test, identity record | P-007/P-008 recorded |
| B1 -> V1a | fail-closed modes, receipts, tests, pinned artifact plan | verifier receives clean lease |
| L1 -> TL3 | candidate isolation, predecessor retention, rollback, lifecycle tests | L1 handoff complete |
| TL3 -> TL2 | measured degree/work/resource data and options | P-002 explicitly decided |
| T0 -> TR1 | immutable Trace snapshot commit and diff manifest | original dirty checkout unchanged |
| TR1 -> TR2 | release-root tests, rollback, external alias behavior, decision brief | P-004 decided |
| D2a -> D2b | raw manifests, checksums, license records, layout validation | B1 manifest contract available |
| B1+D2b -> P-005 | real-data baseline runs with no fallbacks and query IDs | S6 prepares, owner decides |
| V1a+V1b+B3 -> Foundation Gate | independent receipts and complete dossier | coordinator/verifier jointly review |
| Foundation Gate -> 100K | gate dossier accepted and scale corpus admitted | S7 receives lease |
| 100K -> 1M | real-corpus correctness/recovery/resource evidence | separate 1M decision |

## Absolute blockers

Any of these blocks the affected lane:

- source identity drift or dirty worktree used as a clean base;
- missing worktree lease or verifier assignment;
- candidate rows visible to active reads;
- failed validation followed by activation;
- silent exception, synthetic substitution, or hidden fallback;
- absent source/license/checksum/evidence mapping;
- an agent choosing deferred thresholds or temporal semantics unilaterally;
- test evidence that depends on an unavailable provider or inaccessible data;
- a claim that exceeds the authority level recorded in the handoff.
