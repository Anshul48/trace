# TRACE-CAP-001 Praxist Benchmark-Optimization Loop

> **Document ID:** `TRACE-CAP-001-PRAXIST-LOOP`
> **Status:** Prospective. Activates only after Trace is running on an
> accepted profile (100K paired qualification or an approved active release).
> Until then, no Praxist run starts under this plan.
> **Placement note:** drafted in `launch/`; promote to `docs/program/`
> via coordinator with relock.

## 1. Purpose

Separate *measuring* from *improving*. The methodology annex
(`CAP_001_BENCHMARK_METHODOLOGY_ANNEX.md`) is the immutable stick;
Praxist is the loop that moves the needle — tuning retrieval and Cortex
operating parameters against frozen benchmarks without touching the
evaluator, the promotion sets, or the thresholds.

## 2. Entry conditions (all required)

1. An accepted, independently verified 100K (or 10K shadow) result exists
   with sealed promotion query/qrel packs in independent custody.
2. The faithfulness validator has passed its own calibration (annex §4).
3. The human has authorized a bounded optimization budget: max GPU hours,
   max cloud spend ($0 default — local only), and the exact parameter
   envelope open for search (see §3).
4. A clean baseline dossier (lexical → dense → fusion → rerank → Cortex
   ablations per annex §5) is frozen as the loop's starting point.

## 3. Search envelope (initial proposal, human approves)

- RRF fusion constant k (bounded, e.g. 20–100; current frozen value k=60
  stays the gate value until a challenger wins under §4).
- PPR bounds: out-degree cap, walk depth, teleport α, timeout.
- Cascade escalation thresholds (uncertainty/novelty/disagreement signals).
- Atomization/chunking parameters (segmentation ID versioned per candidate).
- Dense-model choice **within** the human-admitted set only; no new
  downloads or provider calls without separate authorization.

Explicitly out of envelope: evaluator code, frozen query/qrel IDs,
faithfulness threshold τ, gate floors, promotion-set membership,
Spine schema, release/activation policy.

## 4. Loop rules (anti-Goodhart)

1. **Sealed promotion sets** never enter a tuning objective; optimization
   sees dev + qualification-readiness packs only. Touching promotion data
   retires it and invalidates the loop's results.
2. **Evaluator immutability:** the faithfulness validator, metric code, and
   bootstrap seeds are pinned for the loop's duration.
3. **Paired evidence:** every challenger is a paired ablation against the
   frozen baseline on identical inputs (annex §5 ladder); report CIs and
   Holm-corrected suite-family results, not single-suite point wins.
4. **Negative results ledger:** failed challengers are recorded with the
   same schema as wins (per GC's negative-results requirement) — a loop
   that only reports wins is treated as compromised.
5. **Human promotion:** the loop *recommends* (smallest passing
   configuration per CAP-D006); only a human decision promotes, and only
   through the normal gate dossier + independent verification.

## 5. Evidence language

Per the Praxist research skill: literature signals (papers, benchmark pages)
may propose directions; only measured task facts (evaluator output from the
frozen harness) support performance claims. Literature notes live in the
task's `assets/literature/`; they never enter the candidate lineage.

## 6. First instantiation (proposal)

Task: RRF + PPR operating-point search on the frozen 10K shadow profile
after CAP-GD. Budget proposal: local GPU only, ≤ 48 GPU-hours, population
≤ 32 configurations, success = paired +0.030 uplift class with no
regression slice and backlog/latency inside envelope.

## 7. Launch authority: Muse operates Praxist

Praxist runs are launched and operated by **Muse** (this agentic CLI),
not by the human directly. Division of responsibility:

- **Human:** authorizes each instantiation (task, envelope §3, budget)
  once, up front — a CAP-D012 spend/execution decision recorded in
  `06_DECISION_LOG.md`. Receives reports; takes promotion decisions.
- **Muse:** everything else, per the `praxist-control` skill —
  task-directory gate (`task.yaml` + `praxist resolve`), runtime gate
  (provider keys by name only, never printed), `praxist start --task-path
  <task> --daemonize --json`, confirmation via `praxist status --json`,
  ongoing `status`/`--monitor` reporting, and `stop`/`resume` as needed.
  `praxist` is on PATH (`/home/anshul/.local/bin/praxist`); use
  `--daemonize` for all launches so runs survive the shell.

Muse reports each control action as: run_id, run_dir, monitor command
(`praxist --monitor --run-id <run_id>`), status, and next check — and never
starts the monitor as a side effect. The human watches via the monitor
command; `Ctrl-C` exits only the monitor. No run starts without a recorded
human authorization; no threshold, evaluator, or promotion-set change ever
rides along with a run.
