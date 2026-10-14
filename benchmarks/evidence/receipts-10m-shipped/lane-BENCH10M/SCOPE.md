# lane-BENCH10M SCOPE (2026-10-08)

## 1. How trace-bench consumes a system (read from the harness)

- Contract: `BaseRetriever` (`../trace-bench/docs/RETRIEVER_CONTRACT.md`).
  One backend instance per run: `index(documents)` once (timed
  separately), then `retrieve(query, top_k)` per query (latency
  measured per call). Optional hooks: `retrieve_with_outcome`
  (receipts/abstention), `preserved_document_ids`,
  `organization_snapshot`, `configuration`,
  `implementation_identity` (TB auto-records wrapper hash +
  our reported product bytes).
- Built-in `trace_narrow`/`tl_narrow` (`src/trace_bench/baselines/
  trace_narrow_retriever.py`) builds a FRESH disposable Narrow
  store per dataset from the bench corpus (`ingest_docs` +
  `NarrowIndex`), loads MiniLM-L6-v2 rev `1110a243…` once per
  run (resident across that run's queries, one process), and
  answers via `NarrowQuery` with `query_config` +
  `MAX_ENTRIES=top_k`. It does NOT serve a prebuilt store.
- Comparability (`compare`): same dataset version, corpus,
  indexed docs, queries, judgments, split, K, concurrency,
  warmup. Protocol: `--top-k 100` default; concurrency 1
  default; custom backends default NOT thread-safe
  (concurrency>1 is a preflight error without an explicit
  opt-in — we stay at 1).
- Acquisition: `setup --dataset X` freezes test split + full
  corpus + native IDs + checksums into the TB cache.
  - BEIR scifact/nfcorpus: legacy UKP-zip path, UNPINNED, no
    hash check. Short-circuit: existing `corpus.jsonl` reused.
  - BEIR fiqa only: pinned HF path with bytes+sha256 verify.
  - BRIGHT: `hf_hub_download` at LIVE HEAD unless staged;
    short-circuit: existing
    `cache/bright/raw/{documents,examples}/<task>-*.parquet`
    reused without network.
  The delegation requires pinned-link pulls with hash verify,
  so we pre-stage pinned bytes into those short-circuit
  layouts (no harness edits): BEIR jsonl converted from
  pinned parquet (equivalence cross-checked), BRIGHT pinned
  parquets placed verbatim.

## 2. Key scoping consequence

The shipped C2-10M store's corpus (docs-100m 10M subset,
3,099 docs) has NO public qrels, so no scored TB benchmark
can run against the prebuilt store. Scored numbers come from
fresh-store adapters serving with the SHIPPED SERVING STACK
(7 files, shas match local tree — see snapshot) + ADOPTED
budgets (seat-sweep cfg: `M_REGIONS=80, PRUNE_CAP=100,
MAX_ENTRIES=40`). The fetched shipped store supports a
deployment-condition probe (persistent process + resident
encoder, read-only at pin `:0:95436`), not scored quality.

## 3. Adapter inventory (all NEW files in this lane; no TB/tlsys edits)

| id | file | kind | what |
|---|---|---|---|
| A1 | `adapters/c2_bench10m.py` (`C2Bench10MShipped`) | TB backend (`python:…`) | fresh Narrow store; shipped stack; cfg M80-P100-A40; resident encoder; PRIMARY arm |
| A2 | same module (`C2Bench10MK100`) | TB backend | identical, `MAX_ENTRIES=100`; isolates the A40 cutoff effect at K=100; diagnostic |
| A3 | `adapters/c2_store_probe.py` | standalone probe (not a TB backend) | opens GCS-fetched store copy read-only at `:0:95436`; K sequential NarrowQuery @M80-P100-A40; records walls |
| S1 | `adapters/stage_pinned.py` | staging helper | pulls pinned links on VM, verifies bytes+sha256 vs manifest, writes TB cache layouts; BEIR parquet→jsonl with equivalence check |
| refs | built-in `bm25`, `dense` | TB baselines | reference arms; dense = same MiniLM rev (query-encoding latency included per TB) |

TB auto-records per-run `implementation_identity`
(candidate rev, product source shas) + our `configuration()`
(budgets, chunking, K-disclosure for A1).

## 4. Benchmark set (10M tier ∩ TB `ready_frozen`)

| lane | TB dataset | split | docs | queries | pull (pinned) |
|---|---|---|---|---|---|
| smoke | smoke (bundled) | fixture | 6 | 6 | none (adapter smoke) |
| curated | curated (bundled) | fixture | 100 | 320 | none |
| scifact | beir-scifact | test | 5,183 | 300 | 3 files ≈4.5 MB |
| nfcorpus | beir-nfcorpus | test | 3,633 | 323 | 3 files ≈3.5 MB |
| pony | bright-pony | — | 7,894 | 112 | 2 files ≈1.2 MB |

Total pull ≈ 9 MB + MiniLM weights (~90 MB; reuse
`/srv/tl/weights` on VM if present). EXCLUDED with cause:
multihop-rag (TB `manual`, no ready lane), musique (no TB
lane), fiqa/leetcode/etc (100M tier, out of scope), W1–W4
(self-org, not retrieval quality), HV (TB-baseline-only).

## 8. Scope change 2026-10-08: bright-pony DROPPED (blocked)

The pinned pony "corpus" file
(`xlangai/BRIGHT@3066d29c…/documents/pony-00000-of-00001.parquet`,
1,125,040 B, sha verified) does NOT contain a document pool:
it holds the 112-row EXAMPLES table (query/reasoning/id/
excluded_ids/gold_ids_long/gold_ids/gold_answer), row-equal
to the pinned examples file. TB 0.3.0 `BrightAdapter.
load_corpus` requires `id`/`content` columns and raises
`KeyError: 'content'`; `setup --dataset bright-pony` fails.
The HEAD verification (12/12) checked resolvers/hashes, not
schemas. Substituting another upstream commit would violate
the pinned-links requirement, so the pony lane is dropped
with cause. Scored set: scifact + nfcorpus + curated (+
bundled smoke for adapter validation). Recommendation for
larger rungs: schema-check every pinned corpus file (row
counts + required columns) before staging.

## 5. Run plan (≈18 runs, protocol fixed)

- Per lane: `trace-bench run --dataset D --baselines
  bm25,dense,python:c2_bench10m:C2Bench10MShipped,
  python:c2_bench10m:C2Bench10MK100 --top-k 100
  --concurrency 1` (+ `--limit` smoke first).
  Smoke lane: A1+bm25 only.
- Then `trace-bench compare` per lane (A1 vs bm25, A1 vs
  dense, A1 vs A2) with seeded bootstrap CI.
- A3 probe: 5 sequential requests on the store copy,
  persistent process, resident encoder; plus 1 storage-cold
  sample if cheap (drop_caches NOT authorized — record
  condition honestly instead).
- Indexing ≈ 16.8k docs MiniLM-embedded (CPU minutes);
  ≈1,055 queries × 4 backends ≈ 4.2k executions, small
  stores (sub-second Narrow expected). Estimate 1–2 h
  end-to-end incl. staging.

## 6. Success criteria

1. All runs `success`; query failures (if any) recorded as
   failures with cause — never fabricated (d7 spirit).
2. RUN.json + TREC + compare outputs captured per lane;
   walls, conditions (process/encoder/store/pin), TB +
   weights + product-byte versions recorded.
3. REPORT.md: top finding first, per-benchmark numbers with
   conditions, adapter inventory, blockers for larger rungs.
4. No SHIP claims, criterion changes, waivers (measurement).

## 7. Rulings / constraints honored

- seat-rulings: M80-P100-A40 adopted as-served; bench does
  not re-tune or re-litigate seating.
- d7: no invented values on miss/failure; aborts classify.
- FORBID: product/harness/criteria edits; C1 contact;
  frozen/live-build-dir writes (bench uses new
  `/srv/tl/lane-bench10m/`; frozen trees at most read-only
  sources for a `cp -a` workspace copy, never imported
  in place); local-PC bulk transfers (corpora/store pulled
  on VM; only small evidence + code transit GCS); anything
  resembling the confirmation campaign.
