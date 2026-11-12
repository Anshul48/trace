# RULING — 500M lineage and Path A vs A-prime (claude-sci, 2026-11-05 ~10:20Z)

Re-derived from surviving receipts only. The Nov-4 RULING-500M-1B.md and card 912 (lineage cos check) are LOST in the disk tear; nothing below leans on them except where marked REPORTED. Tags: OBSERVED = a receipt I read this session; REPORTED = quoted by another record, not re-opened; ARITHMETIC = my calculation from observed numbers; UNVERIFIED = open.

## 1. Evidence used

| # | Fact | Tag | Source |
|---|---|---|---|
| E1 | 100M seal live: 812,545 units, 99,891,846 tok_v1, 4 shards, MiniLM-L6-v2 rev 1110a24, embed_config_id 24e6c863…, uptime 97,750 s | OBSERVED (/health,/stats via ssh, 10:09Z) | probes/README-100M-QUERY-PROBES.md |
| E2 | 100M guided k=10: p50 1222.6 / p99 1408.5 ms (N=2000); my 26 probes p50 1232 ms, 0 non-200; 98.41% of latency in routing+retrieval | OBSERVED / REPORTED | probes.jsonl; outbox query-bench via ROUND3-PLAN.md:23-24; latency-attr via ROUND4-PLAN.md:51-53 |
| E3 | Same-store baseline on 50 probes: BM25 0.82/0.739 beats TRACE guided 0.52/0.418; TRACE keeps 0.9985 of exact at 0.79% rows | REPORTED | MISSION.md line 89 (tables VM-only) |
| E4 | RUNG-504.5M-tok: 13 sealed shards, 3,029,000 units, 504,480,146 tok_v1 (652.7M wp); embed_config_id 27e40d70… (fwedu-254 packs); seal 6.8-8.3 min/shard on 8 pinned cores; sealed bytes 7,653,469,538; all 5 new shards PASS acceptance; 13-way fanout recall 1.0 vs GT-union, s7-down 0.885; adapter warm p50 517-537 ms/shard | OBSERVED | /home/anshul/trace-ops/muse-coord/vmlane/RECEIPT-RUNG-500M §1-3 |
| E5 | Masters of E4 are on the shut-down GCE box /srv/tl; seal bytes/vectors/builder all ferry-bound; cannot re-run as-is | REPORTED | ROUND3-PLAN.md:41-42; FRONTIER-PLAN.md:30-33 |
| E6 | Laptop holding minilm_1b_int8: 7,134,906 int8 rows, 109 shards, 1,531,809,092 tok-units, recount exact; encoded Oct-16 on Colab GPUs in ~25 min | OBSERVED | outbox trace-1b-merge-probe-p1 / trace-7m-index-build / trace-1b-next-step |
| E7 | Full-N merge+partition index on that holding: build 174.6 s wall, 369 MB RSS; 200 self-queries p50 333.6 / p99 594.7 ms, RSS 2.70 GiB, top-1 200/200 (self-queries only; novel-query recall NOT measured) | OBSERVED | outbox trace-7m-index-build §2-3 |
| E8 | CPU encode 2323.4 ± 17.6 tok/s single thread (frozen MiniLM ONNX); no multi-thread or GPU rate on this machine | OBSERVED (REPORTED to me) | ROUND5-PLAN.md:58-61 |
| E9 | HF pre-embedded dataset: NEW lineage (paragraph chunker, rev unrecorded), survey says "feedstock text only, 86 GB, no encode-wall shortcut"; card 912 later reportedly matched our encoder (2000/2000 rows, min cos 0.99999987, cap-256) | REPORTED, mutually inconsistent, receipt of card 912 LOST | MISSION.md lines 86-87 |
| E10 | Disk: C: 22 GB free, falling ~5 GB/h; Linux writes cost C: 1:1 (WSL VHDX); VM disk ~29-60 GB free | OBSERVED / REPORTED | df; ROUND3-PLAN.md:7; memory note |

## 2. Lineage verdict

1. There are TWO distinct sealed lineages, not one: Wikipedia 100M (config 24e6c863…) and fwedu 504.5M rung (config 27e40d70…). Same model family, different pack/embed configuration identity. They must be presented as two labelled tiers (100M Wikipedia serving; 500M fwedu rung), never as "one store grown 5x". Any federation of the two is shard-level with a router and carries both config ids in its manifest. (ARITHMETIC-free; follows from E1 vs E4.)
2. The 7.13M int8 holding (E6) is a third lineage (Colab Oct-16 fw encodes, int8, unsealed). Whether its "tok-units" equal tok_v1 is UNVERIFIED; do not add it to E4's token count.
3. The HF pre-embedded dataset (E9) is a fourth, STANDALONE lineage. Its status is under-determined: the survey says text-only (no vectors), the Nov-4 ruling relied on a vector-match check whose receipt is lost. Until one receipt shows vectors present and matching, it is NOT a basis for any claim.

## 3. Ruling: Path A vs A-prime

Define terms by what they cost (the only thing the measured evidence can discriminate):
- Path A = reuse vectors that already exist; spend only seal/merge CPU.
- Path A-prime = re-cut text with our chunker (R2P) and re-encode.

Cost of A-prime on hardware we can actually use (ARITHMETIC from E8): 504.5M tok / 2323 tok/s = 217,000 thread-seconds = 60 thread-hours. On the VM (4 vCPU quota) that is ~15 h at ideal linear scaling (multi-thread rate UNMEASURED), ~60 h single-thread. GPU would be ~minutes (E6 ran 1.53B tok-units in ~25 min on Colab GPUs) but GPU access is not available under the no-spend / quota constraints today. A-prime therefore cannot land inside any near deadline without new compute authority.

Cost of Path A (ARITHMETIC from E4, E7): sealing existing vectors cost 6.8-8.3 min per 233k-unit shard on 8 cores; 13 shards ≈ 1.6 h on 8 cores, ~3 h on 4 vCPU if linear (UNMEASURED). Merge/partition of 7.1M int8 rows is minutes (E7).

**RULING: Path A over A-prime.** A-prime is a fallback only, and only if an owner-authorised GPU or many-core box appears. The existing sealed-and-accepted rung beats a fresh build on every axis we measured.

Concretely the 500M lineage is, in order of preference:
- **A1 (headline candidate): the Oct-28 RUNG-504.5M-tok masters (E4).** Already sealed and accepted with recall evidence (13-way fanout 1.0 vs GT-union). Needs one thing: ferry of the 7.65 GB sealed bytes from the shut-down GCE box to the **VM** (not the laptop: E10 forbids 7.65 GB on C:). Ferry is owner-order only (ROUND3-PLAN.md:45); this ruling asks for that order, it does not execute it.
- **A2 (no-ferry fallback, laptop): the 7.13M-row int8 holding (E6/E7).** It already builds and queries on the laptop (175 s build, p50 334 ms, 2.7 GiB). It is a real, measured, queryable point at 1.53B tok-units but is unsealed, self-query-only, and its recall on novel queries is unmeasured. Label it "largest queryable real index on hand", not "500M" or "1B".
- **Not a basis today: the HF pre-embedded set (E9)** until a receipt shows vectors + match.

## 4. What may and may not be said (FACTS-AND-RULES style)

May: "A 504.5M-token rung was sealed and accepted on 2026-10-28 on a since-shut-down cloud box (receipt in trace-ops); the masters are not currently serving." "A 7.13M-row (1.53B token-unit) int8 holding builds a queryable index in 175 s on a laptop; self-query p50 334 ms." "100M serves guided queries at p50 ~1.2 s on a shared VM."
May not: 500M or 1B served/live; "fast" or "sub-second" for any 100M query; that TRACE beats BM25 at 100M (E3 says the opposite on 50 source probes: its claim is ~127x less work at 0.9985 of exact recall, not accuracy); that the two sealed lineages are one store; any HF-dataset claim.

## 5. Conditions

C1 Owner order for the A1 ferry to the VM (target VM, ~7.65 GB, check `df` there first); until then A1 stays PARTIAL (receipt exists, masters unreachable).
C2 After ferry: sha-check masters against RECEIPT-RUNG-500M digests (e2bit digests listed in §1 table of that receipt) before anything serves; shards 0-7 masters never written.
C3 One federated query path must carry both embed_config_ids and refuse cross-config merges silently; report per-tier numbers separately.
C4 Latency honesty: per-shard adapter p50 ~520 ms (E4) × fanout means a 13-way query is not ~1.2 s; measure, don't extrapolate from E2.
C5 If A1 ferry is refused or fails, publish nothing about 500M beyond the Oct-28 receipt sentence; A2 stays the live scale point.
C6 Any claim that A-prime is needed must first show a multi-thread/GPU encode rate measured here (the open `trace-1b-encode-mt` item).

## 6. Open / unresolved (visible)
- Card 912 receipt and the HF vector/text-only contradiction (E9).
- tok_v1 vs tok-units equivalence for E6.
- Multi-thread encode rate; 4-vCPU seal wall.
- Whether the 3 GB index in scratch/wave2/trace-7m-index-build (on C: via WSL) should be removed to protect C: headroom — owner/steward call, I did not delete anything.

## 7. ADDENDUM 2026-11-05 ~10:40Z (supersedes the A-prime arithmetic in §3 and closes C6)
Source: VM workspace scratch/wave2/trace-1b-encode-mt/RESULT.md (OBSERVED by me via ssh read): 4-thread CPU encode 3279.5 ± 1159.0 tok/s (seeds 2259 / 3040 / 4540), 1.41x of the single-thread 2323.4, shared-VM contention (APPROXIMATE).
ARITHMETIC: 504.48M tok_v1 / 3279.5 = 153,800 s = 42.7 h on the 4-vCPU VM (range 30.9 h at the best seed to 62 h at the worst). My §3 "~15 h at ideal linear scaling" is WRONG for this hardware: measured scaling is 1.41x, not 4x. A-prime on CPU is therefore ~1.3-2.6 days of VM time, not hours. Ruling unchanged and stronger: Path A; A-prime only with a GPU or a many-core box the owner authorises. C6 is satisfied by this measurement (a better rate would need a quiet VM or more cores; one uncontended rerun is the only open measurement).
Also tightened: Path A seal estimate (~3 h on 4 vCPU) stays UNMEASURED; the 8-core 1.6 h figure is the observed receipt number.

## 8. ADDENDUM 2026-11-05 ~11:45Z — CORRECTION to A2 (supersedes §3 A2 wording and the §4 "may say" sentence about the 7.13M index)
OBSERVED (a2-novel-recall/novel_recall.py + run.log, numpy venv, 40 novel queries = first 40 rows of fw02 shard 0, never in the index; max top-1 cos to the corpus 0.90, none duplicate-like): the 7M index built by trace-7m-index-build partitions rows by blake2b of the row's own bytes (random, content-blind). Scanning a novel query's "own" partition gives partition-recall@10 = 0/40 (mean 0.0) and 0 of the exact top-10 lie in that partition (random expectation ~0.1%). The 334 ms p50 in that job measures a scan of ~7k random rows; it says nothing about retrieval. The job's own caveat said "approximate for novel queries"; the measured value is ~zero, so it is NOT an ANN index.
Also OBSERVED: exact numpy float32 scan of all 7,134,906 rows (chunked, 40 queries batched) 54.2 s wall, i.e. ~1.4 s/query amortised, max RSS 3.4 GB. Exact brute force is the honest A2 baseline today.
CONSEQUENCE: A2 = "largest real holding with a laptop-scale exact scan (about 1.4 s/query amortised, batch 40)", not "queryable index p50 334 ms". Remove the 334 ms sentence from any public wording. A real ANN index over this holding is not yet built; FAISS 1.15.1 is importable offline (uv cache DL515gyB3uMnfehq with ~/.venv-fwedu) — job ann-7m-126e commissioned to measure IVF-SQ8 / IVF-PQ recall@10 vs exact on novel queries.
Ruling on Path A vs A-prime is unchanged. C5 stands: A2 may be shown only with the corrected description.

## 9. ADDENDUM 2026-11-05 ~12:30Z — A2 REPAIRED with an adopted ANN (job ann-7m-126e, verified by claude-sci)
Tag BUILT-measured-on-laptop. 200 same-distribution novel queries (first 100 rows each of fw02 and fw03 shard 0; none duplicate-like), index recall = overlap of ANN top-10 with exact cosine top-10 over all 7,134,906 rows; NOT a TRACE retrieval/relevance result; single machine (16 threads available, latency below at threads=1); no 100M claim. Receipt: ann-7m/RECEIPT.md, run.log.
| index | recall@10 | p50 / p99 ms (1 thread) | RAM | build |
|---|---|---|---|---|
| IVF4096,SQ8 nprobe 16 | 0.9255 | 2.27 / 4.81 | RSS 4.1 GB | 172 s (train 49 + add 123) |
| IVF4096,SQ8 nprobe 64 | 0.9705 | 8.01 / 13.8 | same | same |
| IVF4096,PQ48 nprobe 16 + exact rerank of top-100 | 0.912 | 1.54 / 2.70 | RSS ~2.8 GB (rerank reads the int8 mmap) | 212 s |
| IVF4096,PQ48 nprobe 64 + rerank | 0.942 | 4.93 / 8.41 | same | same |
PQ48 alone tops out at ~0.54 recall; the exact rerank is what buys the recall. Persisted PQ48 file 387.5 MB (reload identical, search deterministic). Exact scan baseline 54 s / 40 queries (~1.4 s per query amortised). My independent check (40 queries, own exact GT, hand's ids match 1.0; persisted PQ index reloaded): rerank recall 0.918 @ nprobe16, 0.955 @ nprobe64.
CONSEQUENCE: A2 becomes a real queryable scale point: 7,134,906 rows, ANN index recall@10 0.91-0.97 vs exact at 1.5-8 ms p50 on a laptop (rows from the Oct-16 Colab encode; tok-unit equivalence to tok_v1 still UNVERIFIED). The §8 correction stands for the old hash-partition index; this supersedes the §8 "no ANN built" remark.
OBSERVED CONTRAST for the architect (not a verdict): the sealed 100M TRACE store holds 812,545 units and answers guided k=10 at p50 ~1.2 s (98.4% in routing+retrieval), while an adopted FAISS IVF index over 7.13M vectors answers at 1.5-8 ms. These are different paths (TRACE returns parents/path/text through hierarchy and routing; FAISS returns ids), different recall definitions, different machines, so they do not rank each other, but per-vector the 100M path is roughly 3 orders of magnitude slower and the AGENTS.md rule says adopt industry components behind a narrow interface. PROPOSAL (not enqueued, touches shared VM + sealed store): same-store head-to-head, FAISS IVF-SQ8/PQ over the 812,545 vectors of the sealed 100M store (vectors must be extractable from the e2bit shards or the source embeddings) vs the live guided path on the 50 recorded probes and exact GT; owner: glass-pavo (latency) with VM lane. Not a claim until run.
