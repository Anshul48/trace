# Attempt 1 — 1-cluster pilot (FAILED, preserved as evidence)

These five files are byte copies of the `docs/program/inbox/cap-mod01/`
artifacts as filed by the first bake-off attempt (2026-09-04), BEFORE the
redo's Phase A 100-cluster run overwrote the live copies.

Why preserved: the MOD02 dossier requires a negative-results ledger
including this failed attempt. Do not edit; do not use for selection.

Known defects (audit verdict: FAIL, do not advance):
- Coverage 1/100 frozen clusters; all local CIs degenerate width-0.
- `gemma4:12b` / `qwen3.8:27b`: `invalid_cluster_count` 1/1 yet faithfulness
  0.9444 (fallback-control scoring leak, fixed fail-closed in redo runner).
- `deepseek-v4-flash` row + 9-point ablation ladder were hardcoded literals
  in the runner, never measured. No DeepSeek key was ever used.
- Tier 5 `gemma4:26b` ran outside authorization; excluded from redo.
- Receipt PASS was self-asserted integrity-only (no completeness check).
