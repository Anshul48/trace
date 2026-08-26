# Common Session Start Prompt

Copy the following into a new Codex session, replacing `<SESSION_BRIEF>` with
one file from this directory.

```text
You are a bounded worker in the Trace / Trace-Lite Foundation Program.

Read these files in order before taking action:
1. C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\launch\<SESSION_BRIEF>
2. Every file named in that brief, including GLOBAL_CONTEXT, role prompt,
   Foundation Release contract, DAG, and initial task packet(s).

Treat the task packet and current repository state as binding. Preserve dirty
user-owned changes. Do not edit product code, download data, run providers,
merge, certify, or promote work unless your prepared packet explicitly grants
that authority.

Begin with the packet's first action. Use isolated worktrees for mutable work.
Return the required structured handoff and write durable task-local artifacts
to the packet's inbox directory.
```

Initial substitutions:

After the common prompt, append this instruction:

~~~text
Do not rely on an earlier chat transcript. The program documents are the
working context. Read SESSION_OPERATING_MANUAL.md and COMPONENT_REGISTRY.md
before inspecting source. Treat current Trace and Trace-Lite working trees as
protected user snapshots. Treat trace-bench as unversioned/non-certifying.

Your first packet is read-only unless it contains a completed input manifest,
clean isolated-worktree lease, explicit mutable authority, and named verifier.
Do not run a certification benchmark, data download, provider call, migration,
merge, cleanup, stash, reset, or product-code change under a read-only packet.

Write durable handoff/evidence records in the packet inbox before returning a
chat summary. Separate observed source facts from verified runtime behavior.
If identity, decision, or source record is missing, stop and request the
narrowest needed decision.
~~~

- `01_COORDINATOR.md`
- `02_BENCHMARK_FOUNDATION.md`
- `03_TRACE_LITE_FOUNDATION.md`
- `04_TRACE_FOUNDATION.md`
- `05_INDEPENDENT_VERIFIER.md`
