# Contributing to TRACE (stack-fork publication)

This repo publishes a frozen candidate. The rules are stricter than usual:

- **Never edit `freeze-src/`** (except to correct a publication wrapper
  pointer outside `cand/`). Frozen bytes rehash to `38c66bef…`; any edit
  breaks `tools/verify_freeze.py` and the publication's entire claim.
- Put scripts, docs, and demos outside `freeze-src/` (see `tools/`, `demo/`).
- No new benchmark claims: numbers come from `receipts/` only. Do not run a
  10M experiment to "check" something — it is billed, multi-hour hardware.
- No corpus, store, weights, or credentials in commits (see `SECURITY.md`).

## Quick checks before a PR

```bash
python3 tools/verify_freeze.py
python3 demo/synthetic_recall.py
bash freeze-src/run_all.sh existing
```
