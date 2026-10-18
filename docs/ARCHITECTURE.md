# TRACE stack-fork architecture (freeze `38c66bef`)

This repo publishes one thing: the **stack-fork candidate** (`freeze-src/`,
SOURCEFREEZE `38c66bef71fb…a43a0d54`, 207 files) that produced the first
receipt-backed 10M qualification (`receipts/`). See
[REPRO.md](REPRO.md) for pins and [BENCHMARKS.md](BENCHMARKS.md) for numbers.

## What TRACE does

TRACE ingests a token corpus into a two-level self-organizing store
(`seg_parent` / `seg_leaf` / `xdoc` holons over atoms), drains it through
publication cycles (prepare → durable commit → ViewPool publish), then serves
guided (hierarchy-routed) and flat (brute-force) similarity queries over the
same vectors. The 10M receipt asserts the store stayed converged
(`pending_documents 0`, `repair_to_zero.final_debt 0`), the ledger stayed
under derived caps, and guided recall beat flat at matched scoring work.

## The stack: 5 fixes on the speed candidate

Base = speed freeze `dd543d0e…` (205 files). The stack changes 5 files and
adds 2 (full report: `freeze-src/BUILD-REPORT.md`, changed set:
`freeze-src/cand/stack/CHANGED-SET.md`):

| File | Fix | What it changes |
|---|---|---|
| `cand/tools/product_pilot.py` | 1+3 | pilot params `max_documents=4096, budget_seconds=60`; `--drain-budget-s` (default 60, env `PILOT_DRAIN_BUDGET_S`, fail-closed); `--drain-unbatched` arm; budget receipts |
| `cand/tools/drain_instrument.py` | 1+3 | NEW: per-cycle drain instrumentation feeding `drain-cycles.jsonl` |
| `cand/fork/tl-sys/tlsys/org_publication.py` | 6 | sort bound tie + default ON (latency-only) |
| `cand/fork/tl-sys/tlsys/serving/generation.py` | 2+5 | suffix-verify + GC hook (contract serving layer) |
| `cand/fork/tl-sys/tlsys/serving/view.py` | 2 | ViewPool build/verify/swap lock split, orphan rule, GC wire |
| `cand/fork/tl-sys/tlsys/serving/gen_gc.py` | 5 | NEW: newest-K + pinned-skip + broken-immunity collection |
| `cand/tests/test_publication.py` | meta | FlagOffIdentity adaptation (10 lines) |

Fix-2/5 are correct and unit-proven but **dormant on the org-pilot path**
(call-graph verified: serving publish/verify/GC have no product callers on
that path). The measured 10M gain comes from Fix-3 (fewer publications via
bigger budget) + Fix-6 (latency-only). The named next candidate for org-layer
work is the opt-in suffix-verify fork — deliberately not stacked.

## Runtime layout (`freeze-src/cand/`)

- `tools/product_pilot.py` — the pilot: ingest → organize/drain → bounded
  repair → fault injection + SIGKILL restore → repair-to-zero → guided eval.
- `fork/tl-sys/tlsys/` — store + serving (commit, ViewPool, query, dossier,
  relquery/relserve, index, generation).
- `fork/tl-candidate-batch/candidate/` — candidate batch (committer, approval).
- `fix1/`, `stack/` — unfrozen sidecars (fix-1 overlay reference; stack tests
  + CHANGED-SET). `fix1/` is byte-identical to the VM fix-1 precedent.
- `tests/` — existing suites (publication 15/15, pool_reuse 22/22,
  pending_topk 2/2, broader 150/150 at build time).
- `run_all.sh` — local synthetic/unit runner (`stack|fix1|existing|all`).

## Known shape limits (measured in seam12a run `o94-scale10m`, not fixed here)

- Drain dominates the wall: initial drain (999.4 s) plus remaining drain
  under readers (4,654.4 s, ~0.36 s/doc at 10M) together take ~60% of the
  9,494.9 s wall. The second level is a flat parent scan per guided query.
  Drain throughput — not publication — is the scaling risk toward 100M.
- `repair_to_zero` cost 1,162.1 s (12% of wall) across 6 bounded iterations
  (debt 5,847 → 0); reader phases carry contention overhead on drain.
- Constant-factor fixes do not bend the curve (cosine cache: no gain).
