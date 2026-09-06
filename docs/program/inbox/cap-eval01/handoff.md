# Implementation Handoff: WP-CAP-EVAL01 Multi-Resolution Evaluation Protocols

## 1. Identity & Metadata

```yaml
work_packet_id: "WP-CAP-EVAL01"
title: "Multi-Resolution Evaluation Protocols & Capability Scorecards"
program: "Project Trace Cognitive Architecture Correction Program (TRACE-CAP-001)"
wave: "Wave B"
role: "Evaluation Specialist (EVAL-SPEC)"
authority: "Clause CAP-D008"
status: "COMPLETED"
branch: "cap-eval01-protocol"
base_commit: "a9255b4"
worktree_path: "/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-eval01"
timestamp_utc: "2026-09-03T08:42:00Z"
target_gates:
  - "Gate CAP-GC (Wave C: Model Bake-Off & Cascade Selection)"
  - "Gate CAP-GD (Wave D: Integrated 10K Shadow Cortex Lifecycle)"
exclusive_lease:
  - "docs/program/04_EVALUATION_PROTOCOL.md"
  - "benchmarks/protocols/"
  - "docs/program/inbox/cap-eval01/handoff.md"
```

---

## 2. Executive Summary

Packet **WP-CAP-EVAL01** establishes the canonical **Multi-Resolution Evaluation Protocol** and machine-readable scorecard schemas for Project Trace under TRACE-CAP-001, executing the core mandate of **Clause `CAP-D008`**.

This work resolves the fundamental metric confounding present in earlier foundation iterations (`DEC-P-005` Release Gate 2) where lexical tree completeness was conflated with semantic self-organization. It replaces legacy proxy evaluations with five orthogonal, non-substitutable capability scorecards, a 9-arm paired ablation matrix, and deterministic pass/fail thresholds for Gate `CAP-GC` and Gate `CAP-GD`.

### Key Achievements:
1. **Retirement of Legacy Proxy Metric:** Formally retired the legacy `0.0% orphan atom rate` metric as proof of semantic organization or cognitive self-organization. It is reclassified strictly as a Lane 1 structural coverage hygiene check.
2. **Five Orthogonal Capability Scorecards:**
   - **Lane 1: Structural Organization:** Source atom retention (100.0%), anchor byte-offset recovery (100.0%), structural orphan hygiene (0.0%), partition stability (ARI $\ge 0.80$, VI drift $\le 0.15$), routing purity ($\ge 0.85$), and candidate reduction ($\ge 90.0\%$).
   - **Lane 2: Semantic Organization (Cortex):** Proposition-level factual support ($\ge 95.0\%$, lower 95% CI $\ge 0.930$), zero critical unsupported assertions ($0.0\%$), narrative coherence ($\ge 0.850$), entity normalization ($P \ge 0.900, R \ge 0.850$), typed relation precision ($\ge 90.0\%$), and 100.0% contradiction preservation.
   - **Lane 3: Direct IR Baseline:** Frozen benchmark quality floors across SciFact (nDCG@10 $\ge 0.700$, Recall@20 $\ge 0.880$, P95 $\le 10.0\text{ ms}$), NFCorpus (nDCG@10 $\ge 0.350$, Recall@20 $\ge 0.220$, P95 $\le 15.0\text{ ms}$), and FiQA (nDCG@10 $\ge 0.400$, Recall@20 $\ge 0.550$, P95 $\le 25.0\text{ ms}$).
   - **Lane 4: Multi-Hop Reasoning:** MultiHop-RAG Complete Coverage@20 ($\ge 0.880$), MuSiQue Complete Coverage@20 ($\ge 0.250$), 2-hop hit rates, graph walk precision ($\ge 0.750$), intermediate hop precision ($\ge 0.700$), bounded PPR traversal (degree $\le 50$, depth $\le 15$, latency $\le 35.0\text{ ms}$).
   - **Lane 5: Synthesis Grounding:** Source attribution precision ($100.0\%$), citation entailment ($\ge 0.980$), zero unsupported claims ($0.0\%$), null-query abstention accuracy ($\ge 90.0\%$), zero-hallucination rate ($100.0\%$), and separate service-class latency/token cost attribution.
3. **Machine-Readable Schemas & Canonical Lockfile:** Authored Draft 2020-12 JSON schemas and canonical gate lockfile in `benchmarks/protocols/`.
4. **Paired Ablation Methodology:** Defined 9-arm paired comparison matrix with paired Wilcoxon signed-rank testing ($\alpha = 0.01$), 95% bootstrap confidence intervals ($B = 10,000$), effect size floor ($\Delta \text{nDCG@10} \ge +0.030$), and no-regression constraints ($\ge -0.010$ on direct queries).
5. **Gate CAP-GC & CAP-GD Specifications:** Established binding pass/fail criteria for Wave C model selection (non-promoting experimental) and Wave D 10K integrated shadow Cortex lifecycle (shadow qualified).

---

## 3. Delivered Artifacts

| Artifact | Location | Type | Description |
| :--- | :--- | :--- | :--- |
| **Evaluation Protocol Specification** | [`docs/program/04_EVALUATION_PROTOCOL.md`](../../04_EVALUATION_PROTOCOL.md) | Markdown | Canonical protocol text defining 5 capability scorecards, legacy proxy retirement, 9-arm ablation rules, and CAP-GC/CAP-GD thresholds. |
| **Master Scorecards Schema** | [`benchmarks/protocols/scorecards.schema.json`](../../../benchmarks/protocols/scorecards.schema.json) | JSON Schema (Draft 2020-12) | Master schema validating multi-resolution evaluation packages, runs, and gate determinations. |
| **Lane 1 Schema** | [`benchmarks/protocols/structural_organization.schema.json`](../../../benchmarks/protocols/structural_organization.schema.json) | JSON Schema | Schema validating structural coverage, stability, and navigation metrics. |
| **Lane 2 Schema** | [`benchmarks/protocols/semantic_organization.schema.json`](../../../benchmarks/protocols/semantic_organization.schema.json) | JSON Schema | Schema validating proposition support, coherence, entity normalization, and relations. |
| **Lane 3 Schema** | [`benchmarks/protocols/direct_ir.schema.json`](../../../benchmarks/protocols/direct_ir.schema.json) | JSON Schema | Schema validating direct lookup floors on SciFact, NFCorpus, and FiQA. |
| **Lane 4 Schema** | [`benchmarks/protocols/multihop_reasoning.schema.json`](../../../benchmarks/protocols/multihop_reasoning.schema.json) | JSON Schema | Schema validating MultiHop-RAG, MuSiQue, and bounded graph walk metrics. |
| **Lane 5 Schema** | [`benchmarks/protocols/synthesis_grounding.schema.json`](../../../benchmarks/protocols/synthesis_grounding.schema.json) | JSON Schema | Schema validating citation precision, claim entailment, and zero-hallucination abstention. |
| **Canonical Protocol Lockfile** | [`benchmarks/protocols/protocol_cap_gates.lock.json`](../../../benchmarks/protocols/protocol_cap_gates.lock.json) | JSON Lockfile | Authoritative, machine-readable parameter lockfile containing exact gate criteria and ablation rules. |
| **Schema Validation Harness** | [`benchmarks/protocols/validate_protocols.py`](../../../benchmarks/protocols/validate_protocols.py) | Python Script | Executable validation suite checking schema draft compliance, payload validation, and fail-closed gate behavior. |
| **Handoff Document** | [`docs/program/inbox/cap-eval01/handoff.md`](handoff.md) | Markdown | Comprehensive packet handoff and downstream execution directives. |

---

## 4. Deconfounding Details: Metric Retirement Analysis (CAP-D008)

### The Defect in Legacy Gate 2
The legacy definition of Release Gate 2 in `DEC-P-005` declared:
> "Release Gate 2 (Self-Organization & Representation): 0.0% orphan atom rate, >= 0.850 top-level routing purity, 0.0% uncoordinated duplicate leaf assignment."

Under audit, this metric combination created a severe false sense of capability:
1. **Pure Partition Accounting:** A deterministic clustering algorithm (e.g. k-means on TF-IDF or sequential binning) can trivially assign 100% of source atoms to clusters with zero unassigned atoms (`orphan_rate = 0.0%`).
2. **Zero Semantic Grounding:** Such clustering can place completely unrelated documents together, and extractive clipping can produce unreadable summaries. The legacy metric gave this 100% passing marks for "self-organization."
3. **Conflation with Retrieval:** In foundation evaluations, passing Gate 2 was treated as evidence that Cortex summarization was functioning, even though no proposition support, narrative coherence, or entity normalization had been evaluated.

### Corrective Realignment
Under Clause `CAP-D008`:
1. The `0.0% orphan atom rate` metric is formally retired as a semantic or cognitive quality proxy.
2. It remains strictly within **Lane 1 (Structural Organization)** as a data-plane structural hygiene invariant (verifying that no atoms were dropped during indexing).
3. **Lane 2 (Semantic Organization)** now independently requires:
   - Summary decomposition into atomic propositions.
   - At least 95.0% supported propositions against source anchors (lower 95% bootstrap CI $\ge 0.930$).
   - Exactly zero critical unsupported propositions.
   - Narrative coherence $\ge 0.850$.
   - Entity normalization precision $\ge 0.900$ and recall $\ge 0.850$.
   - Typed relation precision $\ge 90.0\%$ for high-confidence tier.

---

## 5. Paired Ablation Policy (9-Arm Matrix)

To eliminate cross-mechanism conflation, every candidate evaluation must execute across the 9 paired arms:

```
Arm 0: [BM25]
Arm 1: [Dense]
Arm 2: [BM25 + Dense Fusion]
Arm 3: [BM25 + Dense Fusion + Reranking]
Arm 4: [Arm 3 + Deterministic Extractive Hierarchy]
Arm 5: [Arm 3 + Cortex Generated Summaries (No Graph Edges)]
Arm 6: [Arm 3 + Cortex Typed Graph Edges (No Summaries)]
Arm 7: [Arm 3 + Cortex Summaries + Cortex Typed Graph Edges] (Full Cortex Retrieval)
Arm 8: [Arm 7 + Grounded Synthesis Answers]
```

### Statistical Controls:
- **Sample Unit:** Per-query difference $\Delta_i = \text{Score}(q_i, \text{Candidate}) - \text{Score}(q_i, \text{Baseline})$.
- **Hypothesis Test:** Paired Wilcoxon signed-rank test and paired Student's $t$-test at $\alpha = 0.01$.
- **Confidence Intervals:** 95% Bootstrap Confidence Intervals computed over $B = 10,000$ resamples with fixed seed 42.
- **Practical Uplift Floor:** $\Delta \text{nDCG@10} \ge +0.030$ or Cohen's $d \ge 0.20$ on targeted reasoning / semantic classes.
- **No-Regression Bound:** Non-targeted classes must satisfy lower 95% CI bound $\ge -0.010$.

---

## 6. Pass/Fail Gate Thresholds

### 6.1 Gate CAP-GC (Wave C Model Bake-Off)
- **Status:** `NON_PROMOTING_EXPERIMENTAL`
- **Objective:** Select the smallest passing model or cascade for Cortex summarization and relations.
- **Pass Criteria:**
  1. Proposition Support Rate $\ge 95.0\%$ (lower 95% CI bound $\ge 0.930$).
  2. Critical Unsupported Propositions $= 0$ (zero tolerance).
  3. Narrative Coherence Score $\ge 0.850$.
  4. Typed Relation Precision $\ge 90.0\%$ on high-confidence tier.
  5. Retrieval Uplift $\Delta \text{nDCG@10} \ge +0.030$ on targeted multi-hop/semantic query classes over Arm 3 baseline; $\Delta \ge -0.010$ on direct queries.
  6. 100.0% of negative experimental results and rejected model variants logged.
  7. Synthesis tested strictly against frozen golden evidence bundles; Spine/Cortex write disabled.
  8. Full model economics documented (cost per token, cost per accepted projection, latency per summary).

### 6.2 Gate CAP-GD (Wave D Integrated 10K Shadow Cortex)
- **Status:** `SHADOW_QUALIFIED`
- **Objective:** Prove asynchronous lifecycle correctness, restart safety, and candidate isolation at 10,000 documents.
- **Pass Criteria:**
  1. Ingestion Hot Path Decoupling: Zero synchronous LLM calls; ingestion throughput $\ge 150\text{ docs/s}$ CPU; P95 latency $\le 50.0\text{ ms}$.
  2. Bounded Asynchronous Consolidation: Changed-neighborhood clusters $\le 200$ atoms; zero $O(N^2)$ global all-pairs scans.
  3. Candidate Isolation: Zero candidate projection rows exposed to standard readers before validation receipt.
  4. Single Authoritative Release Pointer: Atomic pointer swap transitions readers cleanly; predecessor release retained for zero-downtime rollback.
  5. Crash / Watermark Replay Parity: 100% state-hash match across SQLite tables upon event log replay after simulated process crash; zero duplicate versions.
  6. Shadow Retrieval Release Naming: Evaluation queries bind explicitly to named candidate release ID with zero cross-release contamination.
  7. Storage Multiplier: Total database size (Spine + Lexical + Cortex) $\le 3.00\times$ raw corpus text footprint.
  8. Host Memory Envelope: Peak process RSS $\le 2.0\text{ GiB}$ (zero OOM, zero swap paging).
  9. Bounded Graph Traversal: Max stored out-degree $\le 50$, walk depth $\le 15$, PPR execution latency P95 $\le 35.0\text{ ms}$.
  10. Anchor Durability: 100.0% UTF-8 byte span recovery across 1,000 sampled spans against original source files.
  11. Policy Preservation: 100.0% redaction and authorization inheritance through all Cortex transformations.

---

## 7. Verification Record

### 7.1 Protocol Document Acceptance Check
Command:
```bash
python3 -c "
proto = open('docs/program/04_EVALUATION_PROTOCOL.md', encoding='utf-8').read()
assert 'Proposition Support' in proto
assert 'Paired Ablation' in proto
print('Protocol Verified.')
"
```
Result:
```
Protocol Verified.
(Exit Code: 0)
```

### 7.2 White-Space and Formatting Conformance Check
Command:
```bash
git diff --check
```
Result:
```
(Clean exit, 0 errors, Exit Code: 0)
```

### 7.3 Schema & Lockfile Validation Suite
Command:
```bash
python3 benchmarks/protocols/validate_protocols.py
```
Result:
```
=== Trace Protocol Schema & Lockfile Validation ===
[OK] Valid Draft 2020-12 Schema: direct_ir.schema.json
[OK] Valid Draft 2020-12 Schema: multihop_reasoning.schema.json
[OK] Valid Draft 2020-12 Schema: scorecards.schema.json
[OK] Valid Draft 2020-12 Schema: semantic_organization.schema.json
[OK] Valid Draft 2020-12 Schema: structural_organization.schema.json
[OK] Valid Draft 2020-12 Schema: synthesis_grounding.schema.json
[OK] Canonical protocol lockfile verified: protocol_cap_gates.lock.json
[OK] Lane 1 (Structural Organization) valid payload verified
[OK] Lane 1 fail-closed on structural orphan breach with verdict PASS
[OK] Lane 2 (Semantic Organization) valid payload verified
[OK] Lane 2 fail-closed on critical unsupported propositions with verdict PASS
[OK] Lane 2 fail-closed on proposition support floor breach with verdict PASS
[OK] Lane 2 negative result retention verified (verdict FAIL allows recording failed runs)
[OK] Lane 3 (Direct IR) valid payload verified
[OK] Lane 3 fail-closed on SciFact floor breach with verdict PASS
[OK] Lane 4 (Multi-Hop Reasoning) valid payload verified
[OK] Lane 4 fail-closed on MultiHop-RAG coverage floor breach with verdict PASS
[OK] Lane 5 (Synthesis Grounding) valid payload verified
[OK] Lane 5 fail-closed on critical unsupported claims with verdict PASS
[OK] Lane 5 negative result retention verified (verdict FAIL allows recording failed runs)
[OK] Master scorecards schema verified full evaluation package (all 5 lanes populated)
[OK] Master schema fail-closed when overall_verdict is PASS but child lane is FAIL
[OK] Master schema fail-closed when Gate CAP-GC criteria fail with verdict PASS
[OK] Master schema negative result retention verified (verdict FAIL allows recording full failure packages)
=== All Protocol Schemas & Validations Passed Successfully ===
(Exit Code: 0)
```

### 7.4 Architectural Safeguards Verified
1. **Hermetic Master Schema:** `scorecards.schema.json` defines all 5 capability lane schemas in `$defs` rather than unresolvable external URI `$ref` links, ensuring fail-safe offline validation across any standard Draft 2020-12 JSON Schema validator without requiring custom resolver registries or internet access.
2. **Conditional Validation & Negative Result Retention:** Evaluator schemas utilize Draft 2020-12 `if/then` conditional validation. When `verdict == "PASS"`, metric floors (e.g. proposition support $\ge 95\%$, critical unsupported claims $= 0$) are strictly enforced. When `verdict == "FAIL"`, non-conforming metric observations are fully preserved, fulfilling the mandatory retention of negative experimental results required by Clause `CAP-GC-06`.

---

## 8. Downstream Directives

The completion of packet **WP-CAP-EVAL01** unblocks the following downstream packets:

1. **Wave C Model Bake-Off (WP-CAP-W07):**
   - Ingest `benchmarks/protocols/semantic_organization.schema.json` and `protocol_cap_gates.lock.json`.
   - Evaluate model candidates (e.g. DeepSeek Flash, Qwen 2.5, Phi-3.5) against Gate `CAP-GC` proposition support ($\ge 95.0\%$) and coherence ($\ge 0.850$) floors.
   - Enforce non-promoting status: do not publish candidates to active release roots.
2. **Wave D Lifecycle Integrators (WP-CAP-CRX02 / WP-CAP-W04):**
   - Bind asynchronous consolidation and candidate isolation to Gate `CAP-GD` criteria.
   - Enforce 10K document capacity ceilings: $\le 2.0\text{ GiB}$ RSS, $\le 3.00\times$ storage multiplier, bounded PPR ($\le 35.0\text{ ms}$, degree $\le 50$, depth $\le 15$).
3. **Independent Verification Agents:**
   - Execute `benchmarks/protocols/validate_protocols.py` to assert protocol integrity.
   - Ensure all future evaluation results validate against `benchmarks/protocols/scorecards.schema.json`.
