# Original 13-Session Implementation-Wave Plan

Status: archival reference captured from the original orchestration request.

## Global rules

- Start every Codex session with the shared bootstrap prompt, then provide the session-specific prompt.
- Use one separate subagent/session for each numbered session.
- Do not combine implementation and verification sessions.
- Respect each session's start condition; do not start later sessions early.
- Human gates are decisions, not Codex sessions.
- Preserve handoffs and evidence from each session before starting dependent work.

Shared bootstrap prompt:

`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\00_SHARED_BOOTSTRAP.md`

## Ordered sessions

| Order | Session | Start condition | Session-specific prompt |
|---:|---|---|---|
| 1 | S0 R1 reconciliation | Start alone | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\01_S0_R1_RECONCILIATION.md` |
| 2 | S1 B1.1 benchmark identity | After Session 1 | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\02_S1_B11_BENCHMARK_IDENTITY.md` |
| 3 | S5 initial V1b verification | After Session 1; parallel with Session 2 | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\03_S5_INITIAL_V1B.md` |
| 4 | S5 V1a benchmark verification | After clean B1.1 from Session 2 | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\04_S5_V1A.md` |
| 5 | S4 D2b normalization | After clean B1.1 from Session 2; parallel with Session 4 | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\05_S4_D2B_NORMALIZATION.md` |
| — | Human gate A: decide P-002 and P-004 | After Sessions 3–5 | No Codex session |
| 6 | S2 TL2 bounded graph | After P-002 is recorded | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\06_S2_TL2.md` |
| 7 | S3 TR2 temporal/revocation | After P-004 is recorded; parallel with Session 6 | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\07_S3_TR2.md` |
| 8 | S5 final V1b verification | After Sessions 6 and 7 | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\08_S5_FINAL_V1B.md` |
| 9 | S6 real baselines and P-005 brief | After V1a, D2b, and final V1b | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\09_S6_BASELINES_P005.md` |
| — | Human gate B: decide P-005 thresholds | After Session 9 | No Codex session |
| 10 | S6 B3 and Foundation dossier | After P-005 is recorded | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\10_S6_B3_DOSSIER.md` |
| 11 | S0 Foundation Gate review | After Session 10 | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\11_S0_R2_FOUNDATION_GATE.md` |
| 12 | S7 real 100K gate | Only after the Foundation Gate passes | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\12_S7_REAL_100K.md` |
| — | Human gate C: decide whether to promote beyond 100K | After Session 12 | No Codex session |
| 13 | S7 1M pilot plan | Only after 100K promotion approval | `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\implementation-wave\next-wave-session-prompts\13_S7_1M_PILOT_PLAN.md` |

## Handoff rule

Each worker must leave a durable handoff and evidence in the repository's designated inbox or session-artifact location. Dependent workers consume those handoffs, and human gates record their decisions before the next gated wave begins.
