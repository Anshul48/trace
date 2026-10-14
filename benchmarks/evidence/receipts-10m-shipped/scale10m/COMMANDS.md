# 10M rung phase-1 command log (reproducibility)

All commands from workspace root
`/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace-architecture`
unless noted. Env for venv runs:
`HF_HOME=/tmp/tl-bench-env-20260927/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0`.

## 1. Owned dirs

```bash
mkdir -p tl-eval/evidence/scale10m-2026-10-04 /tmp/tl-scale10m-2026-10-04
```

## 2. Corpus vector check (stdlib, no model)

```bash
python3 tl-eval/evidence/scale10m-2026-10-04/corpus_check.py \
  | tee tl-eval/evidence/scale10m-2026-10-04/corpus_check.json
```

Verifies against `/tmp/tl-tok-10m-s2-2026-09-29/tok-10m-s/records/doc_manifest.json`:
file shas, per-doc id/sha/tok/cumsum (13,081 docs), minimality, doc_id
uniqueness, tuning-gold coverage. Result: 10,003,381 TOK-v1, minimality
holds, gold 565/565, 809 tuning qids (see BUILD-REPORT.md for the two
benign anomalies: curated FILE sha drift with corpus_text pin intact;
3 scifact docs whitespace-only sha diff from the run_quality .strip()).

## 3. WP census (tokenizer only, local cache)

```bash
HF_HOME=/tmp/tl-bench-env-20260927/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0 \
tl-sys/.venv/bin/python tl-eval/evidence/scale10m-2026-10-04/tok_wp_prefix.py \
  | tee tl-eval/evidence/scale10m-2026-10-04/tok_wp_prefix.json
```

Result: 15,412,007 WP (scifact 1,737,313 / curated 2,561 / delta 13,672,133).

## 4. Driver smoke test (imports + loader only, no ingest)

```bash
tl-sys/.venv/bin/python -c "
import sys; sys.path.insert(0,'tl-eval/evidence/scale10m-2026-10-04')
import driver_10m as D
docs,q,qr = D.load_scale10m()
print('docs', len(docs), 'queries', len(q))
"
```

Result: `docs 13081 queries 1109`.

## 5. Phase-1 ingest + index + 1-query smoke (THE run)

```bash
HF_HOME=/tmp/tl-bench-env-20260927/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0 \
tl-sys/.venv/bin/python tl-eval/evidence/scale10m-2026-10-04/driver_10m.py \
  --phase ingest --out /tmp/tl-scale10m-2026-10-04/phase-out \
  >>/tmp/tl-scale10m-2026-10-04/ingest.log 2>&1
```

Store: `/tmp/tl-scale10m-2026-10-04/stores/scale10m`.
Progress: heartbeats every 60 s in `ingest.log` +
`/tmp/tl-scale10m-2026-10-04/phase-out/progress.jsonl`.
Small summary mirrored to `tl-eval/evidence/scale10m-2026-10-04/phase1.json`.

## 6. Phase-2 command (GATED -- run only on coordinator go)

```bash
HF_HOME=/tmp/tl-bench-env-20260927/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0 \
tl-sys/.venv/bin/python tl-eval/evidence/scale10m-2026-10-04/driver_10m.py \
  --phase queries --out /tmp/tl-scale10m-2026-10-04/phase-out \
  >>/tmp/tl-scale10m-2026-10-04/queries.log 2>&1
```

## 7. run_quality.py diff

NONE -- run_quality.py untouched (driver imports it). `git status` /
`git diff --stat` recorded in BUILD-REPORT.md at completion.
