# TR2 Successor Outline — Temporal Truth, Source Lifecycle, and Revocation Baseline

> **Proposed Task ID:** TR2
> **Role:** Trace Engineer
> **Status:** Proposed Successor Packet Outline (Do NOT execute or mutate code in T1)
> **Prerequisites:** TR1 Implementation Handoff, Accepted Human Decision on P-004, Clean Worktree Lease

---

## 1. Objective

Implement the temporal truth and source lifecycle model chosen in P-004, distinguishing system event time from real-world valid time, supporting source supersession and revocation, implementing historical Cortex Release selection, and ensuring compliance-grade redaction.

---

## 2. In-Scope Surfaces & Interfaces

| Component Surface | Target Changes |
| :--- | :--- |
| **Migrations** | Forward-only SQL migration (`migrations/006_temporal_and_revocation_baseline.sql`):<br>- Add `valid_from_utc TIMESTAMPTZ` and `valid_to_utc TIMESTAMPTZ` to `trace_node_versions`<br>- Add `status TEXT CHECK (status IN ('active', 'superseded', 'revoked', 'deleted'))` to `trace_node_versions`<br>- Add event offset watermarks to `trace_cortex_releases` (`activated_at_event_offset`, `superseded_at_event_offset`) |
| **Data Models** | Update `src/trace/v2/models.py`:<br>- `QueryRequest`: add `valid_at: datetime \| None`, `valid_interval: tuple[datetime, datetime] \| None`<br>- Evidence bundle models: add `temporal_status`, `revocation_reason`, `release_id` |
| **Store Implementations** | Update `src/trace/v2/store.py` and `src/trace/v2/production.py`:<br>- Historical Cortex Release resolver: `effective_historical_release(workspace_id, as_of_event)`<br>- Event handlers for `atom.revoked`, `ingestion.revoked`, `atom.deleted`<br>- Valid-time interval filtering in queryable atom methods |
| **Retrieval Engine** | Update `src/trace/v2/retrieval.py`:<br>- Pass historical release ID to all projection readers when `as_of_event` is specified<br>- Filter out revoked atoms on current queries; tag as revoked on historical queries |
| **Service Layer** | Update `src/trace/v2/service.py`:<br>- Enforce compliance redaction workflow (zeroing raw text and attachments while preserving event offsets and cryptographic hashes) |
| **Tests** | Add comprehensive temporal & revocation tests in `tests/test_v2_temporal_revocation.py` |

---

## 3. Explicitly Forbidden Work

- **No Alteration of Cortex Release Root Architecture:** Must cleanly build on TR1.
- **No Deletion of Event History:** Spine events remain strictly immutable and append-only.
- **No Evaluation Gate Threshold Changes:** Foundation gates remain governed by charter.

---

## 4. Acceptance Criteria & Negative Test Matrix

1. **Historical Release Resolution:** A query with `as_of_event = E` resolves the exact Cortex Release that was active at event offset `E`, retrieving historical hierarchy and affinity states rather than current states.
2. **Revocation Exclusion:** Ingested atoms marked revoked via `atom.revoked` are excluded from all current retrieval results with zero latency.
3. **Historical Revocation Attribution:** An `as_of_event` query at offset `E < E_revocation` returns the atom; at `E >= E_revocation` it returns the atom tagged as `revoked` in the evidence bundle.
4. **Valid Time Interval Filtering:** Queries targeting real-world time interval `[T_start, T_end]` match only atoms whose `[valid_from_utc, valid_to_utc]` overlaps the requested window.
5. **Compliance Redaction Integrity:** Content erasure replaces sensitive raw text with `[REDACTED_BY_COMPLIANCE_POLICY]` while keeping event cryptographic hash chains intact.

---

## 5. Independent Verifier Integration

- Verifier Packet: `V1b` (Temporal Conformance).
- Verifier tests will validate bitemporal query accuracy, revocation propagation, and historical evidence bundle attribution.
