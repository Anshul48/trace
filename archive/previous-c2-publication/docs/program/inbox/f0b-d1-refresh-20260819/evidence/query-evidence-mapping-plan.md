# F0b Evidence — Query and Evidence Mapping Plan

## 1. Evidence Unit Hierarchy

To ensure cross-system comparability between Trace-Lite, Trace V2, and external baselines, benchmark datasets must explicitly define their target evidence units:

```text
Source Artifact (File / Document)
  └── Section / Chunk (HiChunk / Header Hierarchies)
        └── Evidence Atom (Self-contained 1-5 sentence segment, 100-300 chars)
              └── Token / Character Offset Range
```

---

## 2. Query Class Mapping Matrix

| Query Class | Target Evidence Unit | Ground Truth Structure | Success / Correctness Definition |
|---|---|---|---|
| **Direct Lookup / Needle** | Single Evidence Atom (`atom_id`) | Exactly 1 `gold_atom_id` | Gold atom appears in Top-K (K=5, K=10). |
| **Semantic Lookup** | 1 to 3 Evidence Atoms | List of relevant `gold_atom_ids` with optional graded scores | Evaluated via nDCG@10 and Recall@5. |
| **Broad Thematic** | Document or Section Summaries | Multi-atom set representing topic coverage | Evaluated via Complete Gold Coverage@10 and Coverage@20. |
| **Multi-Hop Inference** | Ordered or Unordered Evidence Chain | List of 2 to 4 distinct `gold_atom_ids` across multiple documents | **Complete Gold Coverage@10 == 1.0** (all supporting hops retrieved). |
| **Temporal / Revision** | Timestamped Evidence Atom | `gold_session_id` or atom with effective time metadata | Correct historical vs. current state retrieved based on `as_of` query intent. |
| **Contradiction** | Competing Claim Atoms | Paired opposing `gold_atom_ids` | Both conflicting claims retrieved and identified. |
| **Expected Abstention** | Empty Set (`[]`) | `expected_abstention: true`, `gold_atom_ids: []` | **Abstention Accuracy == 1.0** if and only if system explicitly abstains. Standard retrieval metrics (Recall/nDCG) remain 0.0 or N/A. |

---

## 3. Ground Truth Resolution & Offset Preservation

1. **Deterministic Atom ID Assignment**:
   When raw documents are atomized, each atom receives a deterministic ID:
   ```text
   atom_id = f"atom-{doc_index}-{paragraph_index}"
   ```
   Or a content-hash-based identifier matching Trace Spine contracts.
2. **Gold Evidence Mapping**:
   Every benchmark case must store:
   - `id`: Unique query identifier.
   - `category`: Exactly one of the 8 canonical query categories.
   - `query`: Raw query text.
   - `gold_atom_ids`: List of required evidence atom IDs.
   - `expected_abstention`: Boolean flag indicating whether the query is intentionally out-of-scope.
3. **Abstention Policy Enforcement**:
   - Empty retrieval on a positive query (`gold_atom_ids` non-empty) is a **retrieval failure** (`Recall = 0.0`).
   - Empty retrieval on an expected abstention query (`expected_abstention = True`) is an **abstention success** (`Abstention Accuracy = 1.0`), but must **never** set `Recall@K = 1.0` or `nDCG@K = 1.0`.
