# Demos

All demos exercise **installed real code**, run **fully offline**, and exit
nonzero on any failed check. Keyboard-operated (plain terminal, no mouse,
no animation); see [ACCESSIBILITY](../docs/ACCESSIBILITY.md).

## 1. C2-10M shipping-candidate demo (primary)

Runs the **pinned C2-10M freeze-v2 serving stack** (SHIP 2026-10-08,
store pin `:0:95436`) on a small synthetic corpus: pin verification ->
runtime assembly (producer + serving overlay) -> ingest 6 docs -> Narrow
index -> 3 queries at adopted budgets M80-P100-A40 -> receipt checks.

```bash
pip install -e .[c10m]
python demos/demo_c10m_narrow.py
```

Expected tail output:

```text
DEMO PASS: pinned C2-10M serving stack ran offline (6 synth docs, 3 queries, budgets M80-P100-A40).
```

Options: `--data-dir DIR` (reuse a store), `--keep`, `--quiet` (verdict
only), `--out FILE` (results JSON).
Fixture: [c10m_synth_docs.jsonl](fixtures/c10m_synth_docs.jsonl) (synthetic,
public-domain placeholder text).

Rendered walkthroughs (same content, pre-rendered from a real run):

- [c10m_inspector.html](c10m_inspector.html) — offline static page (no
  scripts, no network): skip link, keyboard navigable, reduced-motion
  aware, labeled diagram, sufficient contrast.
- [c10m_tutorial.md](c10m_tutorial.md) — static Markdown equivalent.

Encoder note: the shipped stack encodes with MiniLM-L6-v2 (weights + torch,
not vendored). The demo substitutes a deterministic SHA-256 token-hash
encoder and says so. Scores and ranking here are NEVER 10M measurements;
what the demo proves is that the pinned ingest/index/query code paths run
end to end. The 10M evidence lives under `benchmarks/evidence/`; the exact
input-reconstruction recipe under `c10m/data/`.

## 2. Phase 1 local-API demo (additional, small scope)

End-to-end `trace_local` SDK round-trip on a 3-document bundled fixture:
open store -> ingest -> answerable query -> fail-closed refusal ->
integrity verify. This exercises the legacy Phase 1 surface only; it says
nothing about the C2-10M candidate above.

```bash
pip install -e .
python demos/demo_phase1_api.py
```

Expected tail output:

```text
DEMO PASS: init/ingest/query/refuse/verify round-trip succeeded (offline).
```

Options: `--data-dir DIR` (reuse a store), `--keep`, `--quiet` (verdict only).
Fixture: [demo_docs.jsonl](fixtures/demo_docs.jsonl).

## CLI equivalent (Phase 1 path)

The same Phase 1 path via the installed CLI:

```bash
trace init --data-dir /tmp/trace-demo
trace ingest --data-dir /tmp/trace-demo demos/fixtures/demo_docs.jsonl
trace query --data-dir /tmp/trace-demo "reader leases mmap"
trace verify --data-dir /tmp/trace-demo
```
