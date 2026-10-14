# REFERENCE — grounding for manual Gemini image generation (FINAL, stack `38c66bef`)

This folder (`docs/gemini-prompts/`) is the integrated prompt set and supersedes earlier drafts (preserved outside this repo) and all
older C2-era prompt packs. Generate manually in the Gemini browser UI
(API free-tier image quota was 0 / `429 RESOURCE_EXHAUSTED` when checked
2026-10-14; no automated generation is claimed). Every fact below was
inspected in the frozen source or its receipts on 2026-10-14.

## The actual subject

**TRACE stack fork, freeze `38c66bef`** — a frozen self-organizing retrieval
candidate. SOURCEFREEZE.json SHA256
`38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54` (207 files;
a content hash of the freeze manifest, **not** a git commit), parent speed
freeze `dd543d0e…be604b` (205 files), drift `[]`. Five stacked fixes on that
base (5 modified + 2 added frozen files):

1. **Fix-1** — pilot parameters + drain instrumentation (`tools/product_pilot.py`,
   `tools/drain_instrument.py`).
2. **Fix-3** — main-drain budget knob (`--drain-budget-s`, budget derived as
   ⌈2× max measured cycle wall⌉); the measured performance gain of the stack.
3. **Fix-6** — partition-sort tie bound in `org_publication.pending_order`
   (`heapq.nsmallest`, default ON); latency-only, result-identical.
4. **Fix-2** — suffix verification in serving (`generation.verify_suffix_against_source`,
   `view.ViewPool` build/verify/swap lock split + orphan rule); falls back to
   full verification on any chain break.
5. **Fix-5** — generation garbage collection (`serving/gen_gc.collect`:
   newest-K + pinned-skip), runs after the generation pointer write.

Actual architecture (frozen tree `fork/tl-sys/tlsys/` + `fork/tl-candidate-batch/`):
ingest chunks documents into **atoms** (whitespace windows, 200 tokens /
50 overlap) committed as `ACCEPT_ATOMS` ops through a candidate-batch
pipeline (intake → preflight → approval → executor → committer, with
pintable/replay/recovery); atoms are organized into per-document **holons**
and a hierarchy (parents/children, segment leaves/parents); a serving layer
publishes verified **generations** (segments, dense vectors, lexical index,
tombstones, checkpoints) that pinned readers query. Lifecycle stages in the
qualification harness: ingest-visible → organize/**drain** → bounded repair →
publish faults + SIGKILL restart → repair-to-zero → pinned guided evaluation.

Queries: **guided** (hierarchical: score parents → children → atoms) versus
**matched-flat** control (same scoring-row budget, no hierarchy), scored
against an exact float64 cosine oracle over cached FP32 vectors
(384-dim, `sentence-transformers/all-MiniLM-L6-v2`, unnormalized; cosine
normalizes at scoring). Probes: 120 cached structural probes
(40 chunk + 40 noisy + 40 cross), each run all-sources and
leave-source-out (LSO) = 240 oracle rows.

## The recorded qualification (captions only — never inside images)

10M run on VM `trace-build500` (n2-highmem-16, shared VM,
**experimental derived caps** — derived cap 669,436 delta entries):
10,003,381 TOK_V1 tokens / 13,081 complete docs / 63,441 atoms / 0 cache
misses / 166,457 commits; wall 12,973 s; PASS + acceptance PASS +
independent readonly oracle replay 240/240 exact (store digest unchanged).
Harness recall@10 (oracle agreement, **not** semantic relevance/nDCG):
all-sources guided 0.730 vs matched-flat 0.056; LSO guided 0.476 vs flat
0.048. Costs kept visible: drain ≈85%+ of wall (~N^1.5 per-doc growth),
repair-to-zero 2,234 s (~17%), readers ≈2× drain penalty.
A small exact-prefix reproduction (88 docs / 20,030 tokens, actual cache
bytes) runs the same frozen harness locally to PASS in ~42 s
(`repro-staging/`); it is a protocol reproduction, not the 10M record.

## ANIMA (for the ecosystem image)

Five independently installable Python components, no shared runtime/server/
wiring; `anima.*` modules are same-object import aliases only:
substrate (persistent project worlds, stdlib-only), sst (dialectic MCTS
heuristic search), stc (spec-to-code), entorhinal (advisory temporal
context), reflex (perception/vision for computer use). Apache-2.0.

## Hard rules for every generated bitmap

- **No quantitative content inside images**: no numbers, percentages, axes,
  bar lengths, or chart geometry carrying meaning. Measured charts exist
  as authored SVGs and are never replaced by generated images.
- **No text inside images** except where a prompt explicitly allows one
  short plain tag (`anima.*`). Generated lettering is unreliable; all
  captions/labels are added in README/HTML next to the image.
- One style family across the set: light off-white `#F7F9FC` background,
  flat modern technical illustration, navy/slate/blue palette (`#0B5CAD`
  primary, `#5B7FA6` secondary, `#222` ink), generous whitespace, high
  contrast (accessible), no photorealism, no dark/cyber/grunge aesthetics,
  no people, no brand logos, no fake screenshots or fake UI text.
- Export PNG 16:9 at the highest available resolution (≈2560×1440) using
  the filename each prompt suggests; keep the prompt file beside the PNG.
- Truthfulness: convey structure (layers, lifecycle, evidence chain,
  independence) schematically. Never depict a 10M-scale claim, a neural
  "AI brain", clouds/servers the project does not run, or integration
  between ANIMA components.

## Prompt inventory

| File | Subject | Suggested PNG |
|---|---|---|
| `prompt-01-trace-stack-hero.txt` | Five fixes fused on one frozen core; audited receipt | `trace-stack-hero-16x9.png` |
| `prompt-02-trace-lifecycle.txt` | Ingest → drain → repair → fault/restart → repair-to-zero → eval | `trace-lifecycle-16x9.png` |
| `prompt-03-trace-serving-generations.txt` | Atoms → holons → hierarchy; verified generations + pinned readers; guided vs flat paths | `trace-serving-generations-16x9.png` |
| `prompt-04-trace-evidence-chain.txt` | Freeze manifest → receipts → acceptance → independent oracle seal | `trace-evidence-chain-16x9.png` |
| `prompt-05-trace-small-repro.txt` | Small exact prefix on a laptop vs the recorded large run kept separate | `trace-small-repro-16x9.png` |
| `prompt-06-anima-ecosystem.txt` | Five independent ANIMA component cards, alias tag only | `anima-ecosystem-16x9.png` |

`GEMINI_BROWSER_PROMPTS.txt` concatenates all six copy-blocks for one-pass
manual generation. Suggested README captions (text, outside images) are in
`CAPTIONS.md`.
