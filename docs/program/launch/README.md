# Foundation Session Launch Kit

For the cognitive-architecture correction and Cortex/Core lane split,
use the [TRACE-CAP-001 Execution DAG](../CAP_001_EXECUTION_DAG.md) and the
comprehensive [TRACE-CAP-001 session prompt pack](CAP_001_SESSION_PROMPTS.md). It
provides full copy-paste ready prompts for coordinators, critiques, workers,
verifiers, and human decision gates across Waves A through G. Mutable implementation
and scale sessions remain gated by Human Owner decisions. The foundation prompts below
are retained for historical foundation program records.

Start **five independent Codex sessions** for the foundation program. If the
human owner performs coordination directly, start the other four.

Each session reads its named brief first. The brief points to the common global
context, one role prompt, first packet(s), authority boundary, and stop rule.
Do not paste the entire prior conversation when these files are available.

Use [START_PROMPT.md](START_PROMPT.md) as the common copy-paste opener, then
substitute the appropriate session-brief path.

| Session | Brief | Owns | Must not own |
| --- | --- | --- | --- |
| 1 | [01_COORDINATOR.md](01_COORDINATOR.md) | packets, DAG, decisions, handoffs | product implementation or self-certification |
| 2 | [02_BENCHMARK_FOUNDATION.md](02_BENCHMARK_FOUNDATION.md) | benchmark suite, manifests, data records | TL/Trace product changes |
| 3 | [03_TRACE_LITE_FOUNDATION.md](03_TRACE_LITE_FOUNDATION.md) | TL lifecycle and safe graph baseline | Trace, benchmark evaluator policy |
| 4 | [04_TRACE_FOUNDATION.md](04_TRACE_FOUNDATION.md) | Trace releases, temporal foundation | TL runtime, evaluation policy |
| 5 | [05_INDEPENDENT_VERIFIER.md](05_INDEPENDENT_VERIFIER.md) | negative verification and conformance | repairing a candidate under review |

All sessions share:

1. `../prompts/GLOBAL_CONTEXT.md`;
2. `../FOUNDATION_RELEASE.md`;
3. `../02_EXECUTION_DAG.md`;
4. the relevant role prompt and task packet;
5. current repository state named by the packet.

One session may use subagents, but each mutable subagent still needs one work
packet, one isolated worktree, and one implementation owner. Verification must
remain independent from implementation.

## Exact first dispatch

| Start | Brief name | First packet(s) | Initial authority |
| --- | --- | --- | --- |
| 1 Coordinator | 01_COORDINATOR.md | F0c | Read-only control-plane records |
| 2 Benchmark | 02_BENCHMARK_FOUNDATION.md | F0a and F0b | Read-only evaluator/data records |
| 3 Trace-Lite | 03_TRACE_LITE_FOUNDATION.md | F0c TL record; L1 review | Read-only TL inspection |
| 4 Trace | 04_TRACE_FOUNDATION.md | F0c Trace record; T1 | Read-only Trace inspection/design |
| 5 Verifier | 05_INDEPENDENT_VERIFIER.md | V0 | Read-only integrity-plan review |

These sessions may work in parallel because their first packets only produce
documentation/evidence records. Do not begin B1, L1, TR1, TR2, B2, or any
data/provider task merely because a first packet completed.

## What the human pastes

1. Start a new Codex session with access to local repositories.
2. Paste the complete Common Session Start Prompt.
3. Replace its session-brief placeholder with the brief filename above.
4. Send it without other context.

When local paths are inaccessible, paste the named launch brief, Global
Context, Session Operating Manual, current packet, and only source excerpts
the packet requires. Do not substitute a chat summary for the packet manifest.

Every session writes a durable task-local handoff before a chat summary. The
coordinator gathers outputs; no session declares a gate passed.
