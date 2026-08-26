# Execution DAG

> **Status:** Draft foundation-first DAG. It defines dependency order and
> proof gates; it does not claim that any listed capability is implemented or
> verified.

## 1. Governing execution rule

The program first establishes a trustworthy, reproducible, finite foundation
release for Trace-Lite, Trace, and the separately versioned benchmark suite.
Only then does it open broad architecture work, deep research, and speculative
retrieval mechanisms.

Independent construction lanes may run in parallel. The following are always
sequential and human-gated: decisions, certification, promotion, scale
advancement, and downstream adoption.

```text
current-state records
       │
       ▼
parallel foundation construction
       │
       ▼
independent verification and repair
       │
       ▼
Foundation Complete gate
       │
       ▼
deep research and bounded experiments
       │
       ▼
promotion → 100K → 1M → consumer shadowing
```

## 2. Stage 0: Control plane and current-state re-anchor

No product code, raw data, benchmark claim, or architecture promotion is
authorized by this stage.

| Node | Output | Hard dependencies | Unblocks |
| --- | --- | --- | --- |
| C0 | Charter, invariants, contracts, prompts, templates, decision/risk logs. | Human direction. | All packets. |
| F0a / E1-refresh | Current benchmark/evaluation audit pinned to the current TL and benchmark-suite revisions. | C0. | B1, V1. |
| F0b / D1-refresh | Durable dataset-record closure: source, license, version, staging, checksum procedure, query/evidence mapping. | C0. | P-001, B2. |
| F0c | Current Trace/TL repository-boundary and dirty-state record. | C0. | All mutable packets. |

F0a and F0b are read-only packet types. A benchmark-suite move is recorded as
a repository-boundary change, not treated as evidence of an implementation
defect without inspecting both repositories.

## 3. Stage 1: Parallel foundation construction

Start only packets whose inputs and authority are concrete. Every mutable task
uses an isolated worktree and one implementation owner.

```text
             ┌─ B1 benchmark integrity ──────┐
F0a/F0b/F0c ─┼─ L1 Trace-Lite lifecycle ──────┼─> F1 verification/repair
             ├─ T1/T2 Trace release foundation┤
             └─ V1 independent verifier ──────┘
```

| Lane | Node | Output | Hard dependencies |
| --- | --- | --- | --- |
| Benchmark | B1 / E2a | Fail-closed runner mode, explicit preflight, error receipts, and no-fallback assertions. | F0a. |
| Benchmark | B2 / D2 | Authorized real-data staging and immutable run inputs. | F0b, accepted P-001, source-specific download authority. |
| Benchmark | B3 / E2b | Certification manifest for admitted data only. | B1, B2, accepted P-005. |
| TL | L1 / TL1 | Candidate/active lifecycle isolation, staged derived state, atomic handover, rollback path. | F0a, F0c. |
| TL | L2 / TL2 | Safe bounded graph/PPR baseline; no unbounded co-occurrence expansion. | L1, accepted P-002. |
| TL | L3 / TL3 | Source coverage, rebuild/replay, provenance, and incremental/full parity evidence. | L1. |
| Trace | T1 | Current Cortex Release audit and concrete migration design. | F0c. |
| Trace | T2 / TR1 | Unified Cortex Release implementation and active-read isolation. | T1, accepted P-003. |
| Trace | T3 / TR2 | Temporal, revocation, and valid-time baseline contract/implementation. | T2, accepted P-004. |
| Verification | V1 / V1a | Independent negative integrity suite for the runner and release receipts. | F0a, B1. |
| Verification | V2 / V1b | Candidate leakage, rollback, stale-edge, and temporal conformance tests. | L1, L2, T2, T3. |

P-001 through P-005 remain human decisions. An agent may prepare evidence or
alternatives, but may not treat a proposal as an accepted gate value.

## 4. Stage 2: Foundation verification and repair

| Node | Output | Hard dependencies | Unblocks |
| --- | --- | --- | --- |
| F1 | Consolidated independent verification report for B1, L1/L3, T2/T3, and V1/V2. | Completed relevant packets. | F2. |
| RPR | Narrow repair packet for a reproduced failure. | F1 or verifier failure evidence. | Re-verification only. |
| F2 / Foundation Complete | Human-reviewed baseline release record: pinned source revisions, data/evaluator identities, capability matrix, known exclusions, and evidence boundary. | F1; B2/B3 only for any certification claim. | R2, X2, baseline 100K planning. |

Foundation Complete is not an external-SOTA or scale claim. It means the
baseline system is reproducible, its supported behavior is explicitly bounded,
and its release/evaluation machinery fails closed.

## 5. Stage 3: Deep research and architecture work

Broad research begins against a trustworthy baseline rather than against
ambiguous implementation state.

| Node | Output | Hard dependencies | Unblocks |
| --- | --- | --- | --- |
| R2 | Architecture research memos and mechanism cards: sparse assembly/hypergraph association, temporal truth, routing, hierarchy, economics, policy-aware retrieval. | F2. | X2. |
| X2 | Bounded prototype in a disposable candidate Cortex, with fixed baseline and ablation plan. | R2, B3 when real evaluation is required. | V3, P1. |
| V3 | Independent experiment verification: quality, safety, provenance, recovery, resource, and cost checks. | X2. | P1. |
| P1 | Promotion dossier: promote, reject, or investigate. | R2, X2, V3. | Human promotion decision only. |

Research may yield a negative result. That is retained as evidence and does
not require a product rewrite.

## 6. Stage 4: Real-corpus scale and promotion

| Node | Output | Hard dependencies | Unblocks |
| --- | --- | --- | --- |
| G100-TL | Trace-Lite real-corpus 100K proof report. | B3, L1-L3, V1-V3, any promoted mechanism. | P1 and Trace adaptation. |
| G100-Trace | Trace 100K release evidence. | T2-T3, accepted P1 where applicable, B3, V2/V3. | G1M. |
| G1M | 1M pilot report. | Accepted G100-TL and G100-Trace. | Larger-scale architecture decision. |

No synthetic fallback, mock provider, forced flat retrieval, hidden query
fallback, or substituted dataset may certify a scale gate.

## 7. Stage 5: Downstream shadowing and selective adoption

| Node | Output | Hard dependencies | Unblocks |
| --- | --- | --- | --- |
| I1 | Reflex/Entorhinal fake-client and conformance report. | V1/V2 and stable evidence-bundle contract. | Shadow readiness review. |
| I2 | Shadow/advisory consumer report. | Accepted relevant 100K gate, I1, human decision P-006. | Selective production adoption. |

Consumers never receive canonical-truth or action authority merely because a
retrieval service is available.

## 8. Immediate dispatch order

1. Prepare and run F0a/E1-refresh, F0b/D1-refresh, and F0c.
2. Review their durable artifacts and make any needed P-001 through P-005
   decisions or explicitly defer dependent work.
3. Start B1, L1, T1, and V1 in separate worktrees where their packet inputs
   are concrete.
4. Start B2, L2, T2, and T3 only after their listed decision or authority
   prerequisites are accepted.
5. Finish F1 and F2 before opening broad R2 architecture work.

## 9. Task-state machine and update rules

```text
proposed
  -> scoped
  -> prepared
  -> assigned
  -> in_progress
  -> handed_off
  -> independently_verified
  -> accepted | repair_requested | rejected | deferred
```

Update this DAG whenever current-state evidence invalidates a packet, a new
hard dependency appears, a decision is accepted, or a failure changes the
foundation/research boundary. Record the affected nodes and regenerate stale
packets rather than silently reusing them.

## 10. Binding DAG amendment - 2026-08-19

The initial broad DAG is refined by this dependency graph. It controls where it
differs from an earlier simplified diagram.

~~~text
C0
 |
 +-- F0a evaluation/source re-anchor -----------+
 |                                               |
 +-- F0b data record closure --> P-001 --> B2 ---+--> B3
 |                                               |
 +-- F0c component records ----------------------+--> coordinator synthesis
                                                        |
                           +----------------------------+------------------------+
                           |                            |                        |
                           v                            v                        v
                        P-007                          T1                       V0
                           |                            |                        |
                        P-008                            +--> P-003 --> TR1 --> V1b lifecycle
                           |                                           |
                           +--> B1 --> V1a                             +--> P-004 --> TR2 --> V1b temporal
                                                |
                                                +--> B2 + P-005 --> B3

F0c + clean accepted TL base --> L1 --> L3
                                      |
                                      +--> P-002 --> L2 --> V1b lifecycle
~~~

### Amendment interpretation

- F0c contains Trace-Lite, Trace, and trace-bench component records plus a
  coordinator synthesis. Missing any component means F0c is incomplete.
- V0 is read-only verifier planning. V1a executes evaluator integrity after
  B1. V1b executes lifecycle/temporal conformance after implementation.
- B1 requires P-007 and P-008 as well as F0a. Code cannot make an unpinned
  evaluator source or ambiguous integration boundary certifying.
- L1 is candidate/active lifecycle only. Graph DF, degree, PPR, latency, and
  memory policies remain blocked on P-002/TL2.
- TR1 is unified Cortex Release only. Temporal/revocation work remains blocked
  on P-004/TR2.
- B2 is the only acquisition/staging packet and requires P-001 plus
  source-specific authority. B3 requires B1, B2, and P-005.

### Foundation-gate correction

F2 has distinct readiness levels in FOUNDATION_GATE_DOSSIER. It cannot unlock
100K, 1M, or consumer shadow just because infrastructure exists. G100 nodes
remain blocked until B3, P-005, component verification, and human review.
