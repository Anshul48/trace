# x1-headroom RESULT — PREREG7 (X1/X2 on frozen X0 queries)

Hand: x1-headroom, VM run 2026-11-05. Spec `inputs/PREREG7.md` (sha256
`65707819f52bf787f673d5bd9b3ddb6c5dfdbd9a2f5b8cdb2a88de30c092a095`; matches the
brief's `65707819f52bf787f673d5bd...` prefix).

CAVEAT (spec provenance): the brief's full-hash file
`~/owner-hub/scratch/wave6/claude-sci/x1/PREREG7.sha256` does not exist on this
VM (there is no `wave6/claude-sci/` tree), so the full-value comparison was
impossible; the prefix matches and `inputs/queries_frozen.jsonl` sha256 matches
the brief exactly (`fab1d5e8...a28b71`, see sha-before/after). Proceeded on the
prefix + exact query-hash match; full-spec-hash comparison UNVERIFIED.

Set: 555 queries (DEV 167 / TEST 388; styles 0 question / 1 keyword /
2 description), label = source unit ordinal. Store: sealed 812,545 units.

## Verdicts (TEST only, literal strings)

- X1: HEADROOM PRESENT (oracle - S = +0.068 macro, 95 % CI [0.044, 0.094])
- X2: FUSION ADDS (RRF vs D: +0.059, p_Holm=0.001818)
- X2: FUSION ADDS (MM vs D: +0.054, p_Holm=0.0001969)
- X2: NO DETECTABLE DIFFERENCE (PD vs D: +0.013, p_Holm=0.5758)
- X2: NO DETECTABLE DIFFERENCE (G vs D: -0.036, p_Holm=0.2177)
- STYLE REVERSAL (TEST winners: style0=D, style1=D, style2=B; flip is in
  style 2, and DEV showed the same style-2 pattern: B 0.9420 > D 0.8696)
- Overall: On TEST, dense wins style 0, dense wins style 1, BM25 wins style 2;
  macro dense wins; HEADROOM PRESENT (oracle - S = +0.068 macro, 95 % CI
  [0.044, 0.094]); FUSION ADDS (RRF vs D: +0.059, p_Holm=0.001818); FUSION ADDS
  (MM vs D: +0.054, p_Holm=0.0001969); NO DETECTABLE DIFFERENCE (PD vs D:
  +0.013, p_Holm=0.5758); NO DETECTABLE DIFFERENCE (G vs D: -0.036,
  p_Holm=0.2177).

## Gates and DEV-only choices (before any TEST scoring)

- Embedding self-test: 50 old probes (query-bench `questions.json` texts, ==
  baselines `probes-50.json` texts) vs stored h2h `embeds.f64.npy`:
  min cosine 1.0000000, mean 1.0000000, gate 0.9999 -> PASS (`selftest.json`).
- Encoder/model: staged `all-MiniLM-L6-v2`, CPU, `normalize_embeddings=True` +
  explicit L2; pooling config = mean, max_seq_length = 256 (read from model
  configs). venv: numpy 2.2.6, sentence-transformers 6.2.0, torch 2.11+cpu,
  scipy 1.18.1, bm25s 0.3.16 (workspace copy of filed pylibs); faiss absent
  (not needed: exact dense via numpy).
- BM25: filed `bm25_index` loaded read-only (`mmap=True`), k1=1.2 b=0.75
  method=lucene, tokenize lower=True stopwords=None, single-query k=100.
- `dev_choice.json` (sha256 `ab8fc92fa28f3f182b191b9ce06c567e5cdeb36c71b881f18e
  64790e7a6d9a9d`): S=D by DEV macro hit@10 (B 0.6693, D 0.7275; micro B 0.7066,
  D 0.7485, no tie); t = 16.747000 = p50 of DEV B top-1 scores (cands p10
  9.7262 / p25 12.2565 / p50 16.7470; DEV micro 0.7066 / 0.7186 / 0.7246, no
  tie; p50 also wins on DEV macro). TEST scoring ran only after this file +
  sha existed (asserted by `x1_score.py`, sha re-verified).

## Method notes (disambiguation decisions, all stated)

1. Dense D = exact f32 cosine: rows f32 L2-normalised (f64 norms), queries
   fp32-normalised, chunked f32 GEMM, per-query top-100 in exact
   (-score, ordinal) order (score-tied partition boundary resolved by smallest
   ordinal); per-shard top-100 merged globally by (-score, ordinal) (exact).
2. RRF k=60 over B/D top-100, order (-score, ordinal). MM: per-list min-max
   over its own 100 scores, 0.5/0.5, missing=0, order (-fused, ordinal),
   top-100; all-equal list -> 1.0 for present entries (lib_hl convention;
   triggered 0/1110 lists). PD: B top-100 pool reranked by f32 dense cosine,
   order (-dense, ordinal).
3. G: if B top-1 score < t, G = B[0:8] + top-2 of D not in B's full top-100 +
   B[10:100] (old B9/B10 dropped; scores: kept B scores, rescued D cosines).
   Fallback (keep B rank if <2 rescued) triggered 0 times; 311/555 gated; all
   G lists unique. Same `gate_g` function used for DEV choice and TEST.
4. Pool recall@K(P) := P(source in P's top-K), i.e. hit@K at deeper cutoffs
   (equals source-hit at K=10/20 by construction).
5. X2 d := TEST micro (per-query mean) hit@10 difference; macro d also
   reported; verdict thresholds applied to micro d. Exact two-sided sign test
   on discordant (b,c), Holm step-down over the 4 comparisons.
6. X1 CI: bootstrap over TEST documents (each query has a unique doc_id, so
   docs == queries here), 10,000 resamples, `numpy default_rng(20261109)`,
   style-macro recomputed per resample; 2.5/97.5 percentiles; 0 skipped.
7. STYLE REVERSAL iff style-1 winner differs from style-0 or style-2 winner
   (pairwise reading; ties do not trigger; winners always shown).
8. O (oracle) defined at hit@10 only: per-query max(B@10, D@10).
9. Overlap: lowercase `[a-z0-9]+` tokens; coverage |Q cap S|/|Q| (+ Jaccard);
   sources joined by id (all 555 found; 45 spare source rows unused).
10. Latency: not measured (batch compute), not claimed.

## Tables (generated from metrics.json by code/x1_tables.py)

n per split x style: DEV s0=51 s1=47 s2=69 (167); TEST s0=131 s1=139 s2=118 (388); styles 0=question 1=keyword 2=description

## TEST source-hit@10 by style x arm

| arm | s0 | s1 | s2 | micro | macro |
| --- | --- | --- | --- | --- | --- |
| B | 0.7557 | 0.3669 | 0.8898 | 0.6572 | 0.6708 |
| D | 0.8550 | 0.5108 | 0.8390 | 0.7268 | 0.7349 |
| RRF | 0.8702 | 0.5683 | 0.9492 | 0.7861 | 0.7959 |
| MM | 0.8855 | 0.5540 | 0.9322 | 0.7809 | 0.7906 |
| PD | 0.8244 | 0.5036 | 0.9237 | 0.7397 | 0.7506 |
| G | 0.7710 | 0.4532 | 0.8814 | 0.6907 | 0.7019 |
| O | 0.8855 | 0.5755 | 0.9492 | 0.7938 | 0.8034 |

## DEV source-hit@10 by style x arm

| arm | s0 | s1 | s2 | micro | macro |
| --- | --- | --- | --- | --- | --- |
| B | 0.7255 | 0.3404 | 0.9420 | 0.7066 | 0.6693 |
| D | 0.8235 | 0.4894 | 0.8696 | 0.7485 | 0.7275 |
| RRF | 0.8627 | 0.4255 | 0.9710 | 0.7844 | 0.7531 |
| MM | 0.8824 | 0.4681 | 0.9855 | 0.8084 | 0.7786 |
| PD | 0.8431 | 0.4468 | 0.9710 | 0.7844 | 0.7537 |
| G | 0.7255 | 0.4043 | 0.9420 | 0.7246 | 0.6906 |
| O | 0.9020 | 0.5532 | 0.9855 | 0.8383 | 0.8136 |

## TEST source-hit@1/5/20 by style x arm

| arm | k | s0 | s1 | s2 | micro | macro |
| --- | --- | --- | --- | --- | --- | --- |
| B | 1 | 0.5649 | 0.2014 | 0.6949 | 0.4742 | 0.4871 |
| B | 5 | 0.7023 | 0.3381 | 0.8390 | 0.6134 | 0.6265 |
| B | 20 | 0.7863 | 0.4101 | 0.9153 | 0.6907 | 0.7039 |
| D | 1 | 0.5802 | 0.2734 | 0.5847 | 0.4716 | 0.4794 |
| D | 5 | 0.8092 | 0.4388 | 0.8051 | 0.6753 | 0.6844 |
| D | 20 | 0.8779 | 0.6115 | 0.8983 | 0.7887 | 0.7959 |
| RRF | 1 | 0.6031 | 0.2734 | 0.6525 | 0.5000 | 0.5097 |
| RRF | 5 | 0.8092 | 0.4604 | 0.8729 | 0.7036 | 0.7142 |
| RRF | 20 | 0.8931 | 0.6259 | 0.9576 | 0.8170 | 0.8256 |
| MM | 1 | 0.6641 | 0.2950 | 0.7203 | 0.5490 | 0.5598 |
| MM | 5 | 0.8473 | 0.4964 | 0.8898 | 0.7345 | 0.7445 |
| MM | 20 | 0.8855 | 0.6331 | 0.9576 | 0.8170 | 0.8254 |
| PD | 1 | 0.5725 | 0.2590 | 0.6186 | 0.4742 | 0.4834 |
| PD | 5 | 0.7786 | 0.4460 | 0.8898 | 0.6933 | 0.7048 |
| PD | 20 | 0.8473 | 0.5540 | 0.9407 | 0.7706 | 0.7807 |
| G | 1 | 0.5649 | 0.2014 | 0.6949 | 0.4742 | 0.4871 |
| G | 5 | 0.7023 | 0.3381 | 0.8390 | 0.6134 | 0.6265 |
| G | 20 | 0.8015 | 0.4964 | 0.9068 | 0.7242 | 0.7349 |

## DEV source-hit@1/5/20 by style x arm

| arm | k | s0 | s1 | s2 | micro | macro |
| --- | --- | --- | --- | --- | --- | --- |
| B | 1 | 0.4118 | 0.2340 | 0.7826 | 0.5150 | 0.4761 |
| B | 5 | 0.6863 | 0.3191 | 0.9275 | 0.6826 | 0.6443 |
| B | 20 | 0.8235 | 0.4043 | 0.9710 | 0.7665 | 0.7329 |
| D | 1 | 0.6275 | 0.1489 | 0.5652 | 0.4671 | 0.4472 |
| D | 5 | 0.7451 | 0.3830 | 0.7536 | 0.6467 | 0.6272 |
| D | 20 | 0.9216 | 0.5745 | 0.9275 | 0.8263 | 0.8079 |
| RRF | 1 | 0.5686 | 0.2553 | 0.6957 | 0.5329 | 0.5065 |
| RRF | 5 | 0.8039 | 0.3404 | 0.9420 | 0.7305 | 0.6955 |
| RRF | 20 | 0.9216 | 0.5319 | 0.9855 | 0.8383 | 0.8130 |
| MM | 1 | 0.5686 | 0.2979 | 0.7536 | 0.5689 | 0.5400 |
| MM | 5 | 0.8431 | 0.3617 | 0.9420 | 0.7485 | 0.7156 |
| MM | 20 | 0.9020 | 0.6170 | 0.9855 | 0.8563 | 0.8348 |
| PD | 1 | 0.6471 | 0.1702 | 0.5942 | 0.4910 | 0.4705 |
| PD | 5 | 0.8431 | 0.3617 | 0.8841 | 0.7246 | 0.6963 |
| PD | 20 | 0.8627 | 0.4468 | 0.9710 | 0.7904 | 0.7602 |
| G | 1 | 0.4118 | 0.2340 | 0.7826 | 0.5150 | 0.4761 |
| G | 5 | 0.6863 | 0.3191 | 0.9275 | 0.6826 | 0.6443 |
| G | 20 | 0.8235 | 0.4681 | 0.9710 | 0.7844 | 0.7542 |

## TEST doc-level hit@10 by style x arm

| arm | s0 | s1 | s2 | micro | macro |
| --- | --- | --- | --- | --- | --- | --- |
| B | 0.8702 | 0.7194 | 0.9746 | 0.8479 | 0.8547 |
| D | 0.9237 | 0.7122 | 0.9153 | 0.8454 | 0.8504 |
| RRF | 0.9237 | 0.7770 | 0.9661 | 0.8840 | 0.8889 |
| MM | 0.9160 | 0.7914 | 0.9576 | 0.8840 | 0.8883 |
| PD | 0.9008 | 0.7338 | 0.9661 | 0.8608 | 0.8669 |
| G | 0.8931 | 0.7554 | 0.9661 | 0.8660 | 0.8715 |

## DEV doc-level hit@10 by style x arm

| arm | s0 | s1 | s2 | micro | macro |
| --- | --- | --- | --- | --- | --- | --- |
| B | 0.8824 | 0.7021 | 0.9855 | 0.8743 | 0.8567 |
| D | 0.9412 | 0.7447 | 0.9130 | 0.8743 | 0.8663 |
| RRF | 0.9020 | 0.7872 | 0.9855 | 0.9042 | 0.8916 |
| MM | 0.9216 | 0.7872 | 0.9855 | 0.9102 | 0.8981 |
| PD | 0.9216 | 0.7872 | 1.0000 | 0.9162 | 0.9029 |
| G | 0.8824 | 0.7660 | 0.9855 | 0.8922 | 0.8779 |

## TEST pool recall@10/20/50/100 for B and D (= hit@K, see defs)

| path | k | s0 | s1 | s2 | micro | macro |
| --- | --- | --- | --- | --- | --- | --- |
| B | 10 | 0.7557 | 0.3669 | 0.8898 | 0.6572 | 0.6708 |
| B | 20 | 0.7863 | 0.4101 | 0.9153 | 0.6907 | 0.7039 |
| B | 50 | 0.8321 | 0.5108 | 0.9576 | 0.7552 | 0.7668 |
| B | 100 | 0.8473 | 0.5755 | 0.9746 | 0.7887 | 0.7991 |
| D | 10 | 0.8550 | 0.5108 | 0.8390 | 0.7268 | 0.7349 |
| D | 20 | 0.8779 | 0.6115 | 0.8983 | 0.7887 | 0.7959 |
| D | 50 | 0.9084 | 0.7482 | 0.9407 | 0.8608 | 0.8658 |
| D | 100 | 0.9389 | 0.7842 | 0.9492 | 0.8866 | 0.8908 |

## DEV pool recall@10/20/50/100 for B and D (= hit@K, see defs)

| path | k | s0 | s1 | s2 | micro | macro |
| --- | --- | --- | --- | --- | --- | --- |
| B | 10 | 0.7255 | 0.3404 | 0.9420 | 0.7066 | 0.6693 |
| B | 20 | 0.8235 | 0.4043 | 0.9710 | 0.7665 | 0.7329 |
| B | 50 | 0.8824 | 0.4468 | 0.9855 | 0.8024 | 0.7716 |
| B | 100 | 0.9020 | 0.5106 | 0.9855 | 0.8263 | 0.7994 |
| D | 10 | 0.8235 | 0.4894 | 0.8696 | 0.7485 | 0.7275 |
| D | 20 | 0.9216 | 0.5745 | 0.9275 | 0.8263 | 0.8079 |
| D | 50 | 0.9412 | 0.6596 | 0.9420 | 0.8623 | 0.8476 |
| D | 100 | 0.9412 | 0.7447 | 0.9565 | 0.8922 | 0.8808 |

## Token overlap: query vs source text (lowercase [a-z0-9]+; cov=|Q cap S|/|Q|)

| split | style | n | cov_mean | cov_p25 | cov_p50 | cov_p75 | jac_mean |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TEST | 0 | 131 | 0.5392 | 0.4615 | 0.5714 | 0.6429 | 0.0766 |
| TEST | 1 | 139 | 0.3297 | 0.1429 | 0.2857 | 0.4286 | 0.0250 |
| TEST | 2 | 118 | 0.5678 | 0.5000 | 0.5714 | 0.6429 | 0.0857 |
| DEV | 0 | 51 | 0.5537 | 0.4667 | 0.5714 | 0.6471 | 0.0793 |
| DEV | 1 | 47 | 0.3139 | 0.1429 | 0.2857 | 0.4286 | 0.0226 |
| DEV | 2 | 69 | 0.5985 | 0.5385 | 0.5882 | 0.6667 | 0.0878 |
| ALL | 0 | 182 | 0.5432 | 0.4615 | 0.5714 | 0.6429 | 0.0773 |
| ALL | 1 | 186 | 0.3257 | 0.1429 | 0.2857 | 0.4286 | 0.0244 |
| ALL | 2 | 187 | 0.5791 | 0.5000 | 0.5714 | 0.6667 | 0.0865 |

## X2 detail (TEST hit@10, S=D; verdict uses micro d)

| fusion | d_micro | d_macro | b (fus-only) | c (S-only) | p | p_Holm | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RRF | +0.0593 | +0.0610 | 33 | 10 | 0.0006061 | 0.001818 | FUSION ADDS (RRF vs D: +0.059, p_Holm=0.001818) |
| MM | +0.0541 | +0.0556 | 24 | 3 | 4.923e-05 | 0.0001969 | FUSION ADDS (MM vs D: +0.054, p_Holm=0.0001969) |
| PD | +0.0129 | +0.0157 | 28 | 23 | 0.5758 | 0.5758 | NO DETECTABLE DIFFERENCE (PD vs D: +0.013, p_Holm=0.5758) |
| G | -0.0361 | -0.0331 | 26 | 40 | 0.1089 | 0.2177 | NO DETECTABLE DIFFERENCE (G vs D: -0.036, p_Holm=0.2177) |

X1 detail: gap_macro=0.0685 CI=[0.0438, 0.0939] n_boot=10000 skipped=0 rng=20261109

TEST winners by style: {'0': 'D', '1': 'D', '2': 'B'}; flag: STYLE REVERSAL
## Independent check (code/verify_x1.py, stdlib only, system python3)

```
verify_x1: B/D hit@10 recomputed from raw files
 B ALL=0.6721 DEV=0.7066 (macro 0.6693) TEST=0.6572 (macro 0.6708)
   DEV style0=0.7255 style1=0.3404 style2=0.9420
   TEST style0=0.7557 style1=0.3669 style2=0.8898
 D ALL=0.7333 DEV=0.7485 (macro 0.7275) TEST=0.7268 (macro 0.7349)
   DEV style0=0.8235 style1=0.4894 style2=0.8696
   TEST style0=0.8550 style1=0.5108 style2=0.8390
verify_x1: OK (matches metrics.json)
```

## Sealed-input integrity (sha256 before/after; identical)

```
--- sha-before.txt
86b7d04b6c845554e91008616201df9436e536ce2d27d9a29469c324a7e4329c  /home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines/bm25_index/data.csc.index.npy
91b52d208a1c4e8dca74fa11cffde66a7f19f18d816119d1b85d932a34105829  /home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines/bm25_index/indices.csc.index.npy
ab580141a95a5decd6d583e749f9c26a2216d17c0d1ff3f217ca0a50e150e1d9  /home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines/bm25_index/indptr.csc.index.npy
44bc0ca1aeb1067d2fc6f85dce61a4880a8a0954f3f24981d00ffa62a87b1fb9  /home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines/bm25_index/params.index.json
f62db7425584e07c7f5d1f161973830e0542e943843aa64a2b4f57cc51a59e63  /home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines/bm25_index/vocab.index.json
fab1d5e8996386520a0cb75c23b9f9f59f406245bb804d810fd0e60478a28b71  inputs/queries_frozen.jsonl
17c98cd12308c734c9d3ba78a867af78b461572b94361fbd03a2b504d5707301  /home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build/shard0-build/rows-shard0.f32.npy
2511e0cd1b40cc1518a9f2d2c3dc2cbc7710cbc759cbb7c9a077cf682c5e3902  /home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build/shard1-build/rows-shard1.f32.npy
1e9b49bc726c6b712a709abe0b6ec5bdda09df34f173747d898c6fd3fd36f9df  /home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build/shard2-build/rows-shard2.f32.npy
b9848479db509c814e351441c3edc6a6a5dbeef99a917081b3e7196f922961e9  /home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build/shard3-build/rows-shard3.f32.npy
--- sha-after.txt (diff vs before: no differences)
86b7d04b6c845554e91008616201df9436e536ce2d27d9a29469c324a7e4329c  /home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines/bm25_index/data.csc.index.npy
91b52d208a1c4e8dca74fa11cffde66a7f19f18d816119d1b85d932a34105829  /home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines/bm25_index/indices.csc.index.npy
ab580141a95a5decd6d583e749f9c26a2216d17c0d1ff3f217ca0a50e150e1d9  /home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines/bm25_index/indptr.csc.index.npy
44bc0ca1aeb1067d2fc6f85dce61a4880a8a0954f3f24981d00ffa62a87b1fb9  /home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines/bm25_index/params.index.json
f62db7425584e07c7f5d1f161973830e0542e943843aa64a2b4f57cc51a59e63  /home/anshul/owner-hub/scratch/wave2/vm-trace-sota-100m-baselines/bm25_index/vocab.index.json
fab1d5e8996386520a0cb75c23b9f9f59f406245bb804d810fd0e60478a28b71  inputs/queries_frozen.jsonl
17c98cd12308c734c9d3ba78a867af78b461572b94361fbd03a2b504d5707301  /home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build/shard0-build/rows-shard0.f32.npy
2511e0cd1b40cc1518a9f2d2c3dc2cbc7710cbc759cbb7c9a077cf682c5e3902  /home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build/shard1-build/rows-shard1.f32.npy
1e9b49bc726c6b712a709abe0b6ec5bdda09df34f173747d898c6fd3fd36f9df  /home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build/shard2-build/rows-shard2.f32.npy
b9848479db509c814e351441c3edc6a6a5dbeef99a917081b3e7196f922961e9  /home/anshul/owner-hub/scratch/wave3/trace-100m-vm/build/shard3-build/rows-shard3.f32.npy
```
--- sha-after.txt (diff: no differences)
```

## Ops (load before -> after each step; 1-min loadavg; gate 2.0)

- setup + sha-before: 5.05 -> 5.05 (hashing only, nice)
- selftest (600 s wait, still loaded -> FLAGGED): 4.92 -> 4.59; encoder cold
  15.6 s; PASS min_cos 1.0000000
- embed555 (180 s wait, ok at 1.77): 5.39 -> 2.06; cold 7.3 s; p50 14.0 ms
- B (no wait needed): 2.06 -> 1.66; p50 8.5 ms p90 32.6 ms; peak RSS 605 MB
- D (no wait needed): 1.66 -> 1.59; ~0.9 s load + ~8.2 s GEMM/topk per shard;
  peak RSS 1191 MB
- dev_choice: 1.47 -> 1.47
- score TEST (x2 runs incl. reversal-rule rerun): 1.24 -> 1.22; 1.48 -> 3.01
- sha-after: 3.65 -> 3.76
- RAM: 31 GB total, ~18 GB available throughout (free col ~0-1 GB +
  buff/cache ~18 GB); own peak ~1.2 GB; /dev/shm unused (0 B); workspace
  14 MB; live 8495 service untouched; no network; no installs; no git push.
- Note: score rerun (reversal pairwise rule) recomputed identical fusions and
  X1/X2; only the flag changed (documented in cmds.log).

## What is measured and not

Measured: source-unit retrieval (hit@1/5/10/20), doc-level hit@10, per-path
pool recall@10/20/50/100, query-source token overlap, on 555 model-authored
queries over one 812,545-unit Wikipedia-derived store with one embedding
model; fixed untrained fusions; TEST verdicts per PREREG7.
Not measured / not claimed: answer quality, latency (batch compute), other
corpora (ANIMA sets keep their own results), trained routers, TRACE guided
search, statistical significance of per-style winners. Label = source unit
only (conservative; other units may answer too). Authors and judge are one
model family (Muse); keyword queries were rewritten to lower lexical overlap,
which may reduce BM25's usual advantage on that style (observed: dense wins
keyword style on both DEV and TEST; BM25 wins description style on both).

## Files (workspace /home/anshul/owner-hub/scratch/wave2/x1-headroom)

- RESULT.md (this file; copied to coord/outbox/x1-headroom.result.md, mode 600)
- raw_B/D/RRF/MM/PD/G.jsonl: per-query {id, ret100:[[ordinal,score]] x100}
- Q555.f32.npy, Q555.f64.npy, qmeta.jsonl: frozen-query embeddings
- dev_choice.json + dev_choice.sha256 (written before TEST scoring)
- metrics.json, tables.md, selftest.json, verify_out.txt
- code/: x1common, x1enc, x1_selftest, x1_embed555, x1_B, x1_D, x1_dev,
  x1_score, x1_tables, verify_x1, test_x1 (+ trace_backend.py and
  gt_exact_ref.py reference copies, originals unmodified)
- pylibs/bm25s: workspace copy of the filed bm25s 0.3.16 (originals untouched)
- cmds.log, sha-before.txt, sha-after.txt
- inputs/: read-only copies as received (PREREG7.md, queries_frozen.jsonl,
  sources.jsonl, probe_ordinals.json)
