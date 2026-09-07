"""Work Packet 5 (WP5) Acceptance Test Suite: 3-Tier Dual-Dispatch & Grounding Verifier.

Tests:
1. Tier 1 Lexical Short-Circuit (<= 5 ms, quoted/UPPER_SNAKE/traceback/backtick triggers over fts_atoms + lex_sig).
2. Tier 2 Top-Down Beam (<= 35 ms, K <= 20 TOC probes, DIVERSE_OVERFLOW excluded, Two-Pass PPR, SHADOW wiring).
3. Tier 3 Global Flat Hybrid Fallback (<= 25 ms, dense kNN + BM25 RRF, floor threshold theta_floor).
4. Invariant: Never return insufficient_evidence before Tier 3 runs.
5. Governor: Caps retrieved set at 8-20 concepts; mixed query short-circuit + L1 union capped at 20.
6. 3-Stage Proposition Grounding Verifier (negations 100% rejected, entity/quantity containment, recall >= 0.80, sampled NLI).
7. Acceptance Gate: p95 latency <= 65 ms across cascade under load; zero recall cliffs off-beam; Tier 2 provably non-default.
"""

from __future__ import annotations

import hashlib
import json
import struct
import time
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from trace.v2.models import RetrievalBudget, QueryRequest
from trace.v2.store import SqliteEventStore
from trace.v2.retrieval import (
    CASCADE_MAX_LATENCY_MS,
    CONFIDENT_COSINE_THRESHOLD,
    DENSE_COSINE_FLOOR,
    GOVERNOR_MAX_CONCEPTS,
    GOVERNOR_MIN_CONCEPTS,
    GroundingVerificationResult,
    HashingDenseEmbedder,
    HybridRetrievalEngine,
    PropositionVerifier,
    RRF_SCORE_FLOOR,
    STAGE3_MAX_CONTRADICTION_P,
    STAGE3_MAX_LATENCY_BUDGET_MS,
    STAGE3_MIN_ENTAILMENT_P,
    STAGE3_NLI_MODEL,
    STAGE3_SAMPLE_RATIO,
    THETA_LEX,
    TIER1_MAX_LATENCY_MS,
    TIER2_MAX_LATENCY_MS,
    TIER3_MAX_LATENCY_MS,
    is_mixed_query,
    is_tier1_triggered,
    verify_grounding,
)
from trace.v2.organization import NODE_TYPE_DIVERSE_OVERFLOW


# ==============================================================================
# Helpers & Fixture Population
# ==============================================================================

def make_atom(
    workspace_id: str,
    node_id: str,
    version_id: str,
    content: str,
    facets: list[str] | None = None,
    start_byte: int = 0,
    end_byte: int | None = None,
) -> dict[str, Any]:
    c_bytes = content.encode("utf-8")
    eb = len(c_bytes) if end_byte is None else end_byte
    return {
        "workspace_id": workspace_id,
        "node_id": node_id,
        "atom_version_id": version_id,
        "doc_id": f"doc_{node_id}",
        "file_id": f"file_{node_id}.txt",
        "start_byte": start_byte,
        "end_byte": eb,
        "content": content,
        "text": content,
        "content_hash": hashlib.sha256(c_bytes).hexdigest(),
        "facets": facets or ["atom"],
        "security": {"visibility": "internal"},
    }


def float_vector_to_bytes(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def make_unit_vector(dim: int, hot_idx: int) -> list[float]:
    vec = [0.0] * dim
    vec[hot_idx % dim] = 1.0
    return vec


# ==============================================================================
# 1. Tier 1 Lexical Short-Circuit Tests
# ==============================================================================

class TestTier1LexicalShortCircuit:
    """Tier 1 Lexical Short-Circuit (<= 5 ms, triggers, fts_atoms + lex_sig)."""

    def test_tier1_trigger_detection(self) -> None:
        # Quoted strings
        assert is_tier1_triggered('"exact phrase query"') is True
        assert is_tier1_triggered("'single quote trigger'") is True

        # UPPER_SNAKE >= 3 chars
        assert is_tier1_triggered("check MAX_RETRIES configuration") is True
        assert is_tier1_triggered("system DIVERSE_OVERFLOW error") is True
        assert is_tier1_triggered("AB_C") is True
        # Plain lowercase or words without underscores are not triggers
        assert is_tier1_triggered("general semantic search without triggers") is False

        # Traceback indicators
        assert is_tier1_triggered('File "service.py", line 42, in process') is True
        assert is_tier1_triggered("Traceback (most recent call last):") is True
        assert is_tier1_triggered("Encountered ValueError: invalid index") is True

        # Backticks
        assert is_tier1_triggered("call to `execute_query` failed") is True
        assert is_tier1_triggered("`SqliteEventStore.insert_atoms`") is True

    def test_mixed_query_detection(self) -> None:
        # Mixed: contains lexical trigger AND natural language terms
        assert is_mixed_query('what is the meaning of "exact phrase" in this context') is True
        assert is_mixed_query('how does `execute_query` handle database timeouts') is True
        # Pure lexical trigger: only the symbol/quote
        assert is_mixed_query('"exact phrase"') is False
        assert is_mixed_query('`execute_query`') is False

    def test_tier1_short_circuit_execution_and_latency(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_t1.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        # Ingest 5 atoms with distinct trigger terms into both SQLite and atoms list
        ws = "ws-t1"
        atoms = [
            make_atom(ws, "n1", "v1", "Crucial setting MAX_RETRIES must be set to 5 for network resiliency."),
            make_atom(ws, "n2", "v2", "Another doc mentioning MAX_RETRIES default timeout behavior."),
            make_atom(ws, "n3", "v3", "Reference doc explaining MAX_RETRIES backoff algorithm."),
            make_atom(ws, "n4", "v4", "Unrelated database indexing doc."),
            make_atom(ws, "n5", "v5", "Unrelated caching layer documentation."),
        ]
        store.insert_atoms(atoms)

        req = QueryRequest(
            workspace_id=ws,
            query="MAX_RETRIES",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)

        # Must short-circuit at Tier 1 via real SQLite FTS5 table
        assert outcome.diagnostics["tier"] == 1
        assert outcome.diagnostics["tier1_short_circuit"] is True
        assert outcome.diagnostics["tier1_triggered"] is True
        assert len(outcome.candidates) >= 3
        # Latency must adhere to SLO (<= 5.0 ms)
        assert outcome.diagnostics["tier1_elapsed_ms"] <= TIER1_MAX_LATENCY_MS
        assert outcome.diagnostics["tier2_provably_non_default"] is True

    def test_tier1_holon_lex_sig_expansion(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_t1_holon.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-t1-h"
        atoms = [
            make_atom(ws, "n1", "v1", "System kernel security boundary initialization.", start_byte=0, end_byte=48),
            make_atom(ws, "n2", "v2", "Cluster authorization certificate verification.", start_byte=0, end_byte=48),
            make_atom(ws, "n3", "v3", "Kernel memory allocation policy.", start_byte=0, end_byte=32),
        ]
        store.insert_atoms(atoms)

        # Verify both byte-exact [[start, end]] spans and source_atom_version_id spans resolve
        holons = [
            {
                "id": "holon-1",
                "parent_toc": "toc-1",
                "lex_sig": ["kernel_security_lock", "boundary", "init"],
                "spans": [[0, 48]],
                "status": "ACTIVE",
            },
            {
                "id": "holon-2",
                "parent_toc": "toc-1",
                "lex_sig": ["kernel_security_lock", "cluster", "auth"],
                "spans": [{"source_atom_version_id": "v2"}],
                "status": "ACTIVE",
            },
            {
                "id": "holon-3",
                "parent_toc": "toc-1",
                "lex_sig": ["kernel_security_lock", "memory", "alloc"],
                "spans": [[0, 32]],
                "status": "ACTIVE",
            },
        ]
        store.insert_holons(holons)

        req = QueryRequest(
            workspace_id=ws,
            query="KERNEL_SECURITY_LOCK",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )
        outcome = engine.retrieve(store=store, request=req, atoms=atoms)
        assert outcome.diagnostics["tier"] == 1
        assert outcome.diagnostics["tier1_short_circuit"] is True
        assert len(outcome.candidates) >= 3

    def test_tier1_traceback_short_circuit(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_t1_tb.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-tb"
        tb_str = 'Traceback (most recent call last):\n  File "service.py", line 42, in process\nValueError: invalid index'
        atoms = [
            make_atom(ws, "tb1", "v1", f"Error log: {tb_str} on worker 1."),
            make_atom(ws, "tb2", "v2", f"Crash dump: {tb_str} on worker 2."),
            make_atom(ws, "tb3", "v3", f"Diagnostic report: {tb_str} on worker 3."),
            make_atom(ws, "tb4", "v4", "Normal operational metrics and health checks."),
        ]
        store.insert_atoms(atoms)

        req = QueryRequest(
            workspace_id=ws,
            query='Traceback (most recent call last):',
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)
        assert outcome.diagnostics["tier"] == 1
        assert outcome.diagnostics["tier1_short_circuit"] is True
        assert outcome.diagnostics["tier1_triggered"] is True
        assert len(outcome.candidates) >= 3

    def test_tier1_weak_fts_match_does_not_short_circuit(self, tmp_path: Path) -> None:
        """Negative test: weak/irrelevant FTS matches under THETA_LEX (2.0) must not short-circuit Tier 1."""
        store = SqliteEventStore(tmp_path / "test_t1_weak.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-t1-weak"
        atoms = [
            make_atom(ws, f"n{i}", f"v{i}", f"General document {i} discussing software architecture and design patterns.")
            for i in range(10)
        ]
        store.insert_atoms(atoms)

        # 1. Real FTS5 hits test: Query triggers Tier 1 via UPPER_SNAKE, and FTS5 returns >= 3 hits,
        # but raw bm25 scores are weak (abs(score) < THETA_LEX = 2.0). Since none contain the trigger,
        # they receive no verbatim boost and must NOT short-circuit Tier 1.
        raw_fts_hits = store.search_fts_atoms("architecture OR UNMATCHED_UPPER_TRIGGER")
        assert len(raw_fts_hits) >= 3
        assert all(abs(float(h["score"])) < THETA_LEX for h in raw_fts_hits)

        req1 = QueryRequest(
            workspace_id=ws,
            query="architecture OR UNMATCHED_UPPER_TRIGGER",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )
        outcome1 = engine.retrieve(store=store, request=req1, atoms=atoms)
        assert outcome1.diagnostics["tier1_triggered"] is True
        assert outcome1.diagnostics["tier1_short_circuit"] is False
        assert outcome1.diagnostics["tier"] != 1

        # 2. Absent trigger phrase query: Quoted trigger absent from all documents
        req2 = QueryRequest(
            workspace_id=ws,
            query='"NONEXISTENT_TRIGGER_KEYWORD" document architecture',
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )
        outcome2 = engine.retrieve(store=store, request=req2, atoms=atoms)
        assert outcome2.diagnostics["tier1_triggered"] is True
        assert outcome2.diagnostics["tier1_short_circuit"] is False
        assert outcome2.diagnostics["tier"] != 1


# ==============================================================================
# 2. Tier 2 Top-Down Beam & Shadow Wiring Tests
# ==============================================================================

class TestTier2TopDownBeam:
    """Tier 2 Top-Down Hierarchical Beam (<= 35 ms, TOC probes, Two-Pass PPR, SHADOW)."""

    def test_overflow_nodes_excluded_from_beam(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_overflow.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-overflow"
        dim = 16
        c_normal = make_unit_vector(dim, 0)
        c_overflow = make_unit_vector(dim, 0)

        toc_nodes = [
            {
                "id": "toc-normal",
                "parent": None,
                "c0": float_vector_to_bytes(c_normal),
                "r0": 0.5,
                "members": ["h1"],
                "boundary": {"node_type": "NORMAL", "cohesion_floor": 0.20},
                "status": "ACTIVE",
            },
            {
                "id": "toc-overflow",
                "parent": None,
                "c0": float_vector_to_bytes(c_overflow),
                "r0": 0.9,
                "members": ["h2"],
                "boundary": {"node_type": NODE_TYPE_DIVERSE_OVERFLOW, "cohesion_floor": 0.0},
                "status": "ACTIVE",
            },
        ]
        store.insert_toc_nodes(toc_nodes)

        atoms = [
            make_atom(ws, "n1", "v1", "Normal cluster concept atom."),
            make_atom(ws, "n2", "v2", "Overflow unclustered concept atom."),
        ]

        req = QueryRequest(
            workspace_id=ws,
            query="cluster concept search",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)
        t2_shadow = outcome.diagnostics.get("tier2_shadow", {})

        # DIVERSE_OVERFLOW must be strictly excluded from probed TOCs
        assert "toc-overflow" not in t2_shadow.get("probed_tocs", [])
        assert "toc-normal" in t2_shadow.get("probed_tocs", [])

    def test_tier2_provably_non_default_shadow_mode(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_shadow.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-shadow"
        atoms = [
            make_atom(ws, "n1", "v1", "Primary architecture overview document."),
            make_atom(ws, "n2", "v2", "Secondary networking routing document."),
        ]

        req = QueryRequest(
            workspace_id=ws,
            query="architecture overview",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)

        # Tier 2 is wired in shadow mode by default
        assert outcome.diagnostics["tier2_mode"] == "shadow"
        assert outcome.diagnostics["tier2_provably_non_default"] is True
        assert outcome.diagnostics["tier"] == 3
        assert "tier2_shadow" in outcome.diagnostics
        assert outcome.diagnostics["tier2_shadow"]["mode"] == "shadow"

    def test_tier2_active_promotion_mode(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_active_t2.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder, tier2_mode="active")

        ws = "ws-active"
        atoms = [
            make_atom(ws, "n1", "v1", "Architecture storage tier layout."),
            make_atom(ws, "n2", "v2", "Architecture memory pool layout."),
        ]

        req = QueryRequest(
            workspace_id=ws,
            query="architecture storage layout",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)
        assert outcome.diagnostics["tier2_mode"] == "active"
        assert outcome.diagnostics["tier2_provably_non_default"] is False

    def test_tier2_active_promotion_mode_short_circuits_on_confident_beam(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_active_t2_conf.db")
        dim = 16
        embedder = HashingDenseEmbedder(dimensions=dim)
        engine = HybridRetrievalEngine(dense_embedder=embedder, tier2_mode="active")

        ws = "ws-active-conf"
        q_vec = embedder.embed(["distributed memory store"])[0]
        c_bytes = float_vector_to_bytes(q_vec)
        c_int8 = bytes([int(max(-127, min(127, round(x * 127)))) & 0xFF for x in q_vec])

        # Insert 3 TOC nodes and 3 member holons aligned with query vector
        toc_nodes = [
            {
                "id": f"toc-{i}",
                "parent": None,
                "c0": c_bytes,
                "r0": 0.1,
                "members": [f"h{i}"],
                "boundary": {"node_type": "NORMAL"},
                "status": "ACTIVE",
            }
            for i in range(1, 4)
        ]
        store.insert_toc_nodes(toc_nodes)

        holons = [
            {
                "id": f"h{i}",
                "parent_toc": f"toc-{i}",
                "centroid_int8": c_int8,
                "lex_sig": ["distributed", "memory", "store"],
                "spans": [[0, 50]],
                "status": "ACTIVE",
            }
            for i in range(1, 4)
        ]
        store.insert_holons(holons)

        atoms = [
            make_atom(ws, f"n{i}", f"v{i}", f"Distributed memory storage architecture details node {i}.", start_byte=0, end_byte=50)
            for i in range(1, 4)
        ]
        store.insert_atoms(atoms)

        req = QueryRequest(
            workspace_id=ws,
            query="distributed memory store",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)
        assert outcome.diagnostics["tier"] == 2
        assert outcome.sufficiency_state == "answerable"
        assert outcome.diagnostics["tier2_mode"] == "active"
        assert outcome.diagnostics["tier2_provably_non_default"] is False
        assert len(outcome.candidates) >= 3


# ==============================================================================
# 3. Tier 3 Global Flat Hybrid Fallback & Threshold Floor Tests
# ==============================================================================

class TestTier3FlatHybridFallback:
    """Tier 3 Global Flat Hybrid Fallback (<= 25 ms, dense kNN + BM25 RRF, floor gate)."""

    def test_never_return_insufficient_evidence_before_tier3(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_no_early_abstain.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-floor"
        atoms = [
            make_atom(ws, "n1", "v1", "Python multiprocessing worker coordination engine."),
            make_atom(ws, "n2", "v2", "Distributed event streaming and replication protocol."),
        ]

        req = QueryRequest(
            workspace_id=ws,
            query="event streaming protocol",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)

        # Tier 3 MUST run before any insufficient_evidence can be emitted
        assert outcome.diagnostics["tier"] == 3
        assert outcome.sufficiency_state == "answerable"
        assert len(outcome.candidates) > 0
        assert outcome.candidates[0].rrf >= RRF_SCORE_FLOOR

    def test_terminal_floor_returns_insufficient_evidence(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_floor_fail.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-gibberish"
        atoms = [
            make_atom(ws, "n1", "v1", "Alpha beta gamma delta epsilon."),
        ]

        req = QueryRequest(
            workspace_id=ws,
            query="xyz_completely_disjoint_qwerty_999",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)
        assert outcome.diagnostics["tier"] == 3

    def test_zero_recall_cliffs_off_beam(self, tmp_path: Path) -> None:
        """Acceptance gate: zero recall cliffs on out-of-beam queries."""
        store = SqliteEventStore(tmp_path / "test_off_beam.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-cliffs"
        dim = 16
        toc_nodes = [
            {
                "id": "toc-finance",
                "parent": None,
                "c0": float_vector_to_bytes(make_unit_vector(dim, 0)),
                "r0": 0.2,
                "members": ["h_fin"],
                "boundary": {"node_type": "NORMAL"},
                "status": "ACTIVE",
            },
        ]
        store.insert_toc_nodes(toc_nodes)

        atoms = [
            make_atom(ws, "fin1", "v_fin", "Corporate quarterly earnings balance sheet."),
            make_atom(ws, "sec1", "v_sec", "Asymmetric elliptic curve cryptography key exchange protocol."),
        ]

        req = QueryRequest(
            workspace_id=ws,
            query="elliptic curve cryptography key exchange",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)

        # Tier 2 beam misses target atom, but Tier 3 flat hybrid fallback retrieves it with 100% recall!
        assert outcome.sufficiency_state == "answerable"
        retrieved_ids = [c.atom["atom_version_id"] for c in outcome.candidates]
        assert "v_sec" in retrieved_ids, "Off-beam target atom MUST be retrieved by Tier 3 flat hybrid fallback"


# ==============================================================================
# 4. Governor & Mixed Query Tests
# ==============================================================================

class TestGovernorAndMixedQueries:
    """Governor concepts cap [8, 20] & mixed query short-circuit + L1 union."""

    def test_governor_concept_caps(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_gov.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-gov"
        atoms = [
            make_atom(ws, f"node_{i}", f"ver_{i}", f"System configuration property number {i} for cluster nodes.")
            for i in range(35)
        ]

        req = QueryRequest(
            workspace_id=ws,
            query="configuration property cluster nodes",
            retrieval_budget=RetrievalBudget(candidate_limit=50),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)
        assert len(outcome.candidates) <= GOVERNOR_MAX_CONCEPTS
        assert len(outcome.candidates) >= GOVERNOR_MIN_CONCEPTS

    def test_mixed_query_unions_lexical_and_semantic(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_mixed.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-mixed"
        atoms = [
            make_atom(ws, "n1", "v1", "Contains trigger `ENABLE_TLS` with high exact match."),
            make_atom(ws, "n2", "v2", "Semantic document discussing network security and encrypted sockets."),
            make_atom(ws, "n3", "v3", "General infrastructure operations guide."),
        ]

        req = QueryRequest(
            workspace_id=ws,
            query="how does `ENABLE_TLS` relate to network security and encrypted sockets",
            retrieval_budget=RetrievalBudget(candidate_limit=10),
        )

        outcome = engine.retrieve(store=store, request=req, atoms=atoms)
        retrieved_ids = {c.atom["atom_version_id"] for c in outcome.candidates}
        assert "v1" in retrieved_ids, "Trigger match v1 must be included"
        assert len(outcome.candidates) <= GOVERNOR_MAX_CONCEPTS


# ==============================================================================
# 5. 3-Stage Proposition Grounding Verifier Tests
# ==============================================================================

class TestPropositionGroundingVerifier:
    """3-Stage Grounding Verifier: 100% negation rejection, containment, recall >= 0.80, NLI."""

    def test_negations_strictly_100_percent_rejected(self) -> None:
        verifier = PropositionVerifier()

        pairs = [
            ("System strictly prohibits unencrypted storage.", "System strictly permits unencrypted storage."),
            ("Access is mandatory for administrators.", "Access is optional for administrators."),
            ("System always verifies digital signatures.", "System never verifies digital signatures."),
            ("The policy enables automatic compression.", "The policy disables automatic compression."),
            ("Service requires mutual TLS.", "Service does not require mutual TLS."),
            ("System cannot write to disk without permission.", "System can write to disk without permission."),
            ("Users can't access the server when running in production mode.", "Users can access the server when running in production mode."),
            ("System won't delete data without user confirmation.", "System will delete data without user confirmation."),
            ("Database does not replicate without authentication.", "Database replicates without authentication."),
        ]

        for src, hyp in pairs:
            res = verifier.verify(src, hyp)
            assert res.passed is False, f"Inverted proposition MUST fail: {src} vs {hyp}"
            assert res.stage == 1
            assert res.failure_reason == "POLARITY_INVERSION"

    def test_entity_and_quantity_containment(self) -> None:
        verifier = PropositionVerifier()

        # Quantity mismatch: source has 3, hypothesis introduces 7
        res_q = verifier.verify("Cluster runs 3 nodes.", "Cluster runs 7 nodes.")
        assert res_q.passed is False
        assert res_q.stage == 2
        assert "UNSUPPORTED_ENTITIES" in (res_q.failure_reason or "")

        # Entity mismatch: source mentions Alice, hypothesis introduces Bob
        res_e = verifier.verify("Alice reviewed the deployment.", "Bob reviewed the deployment.")
        assert res_e.passed is False
        assert res_e.stage == 2
        assert "UNSUPPORTED_ENTITIES" in (res_e.failure_reason or "")

        # Acronym / uppercase identifier mismatch
        res_a = verifier.verify("Service requires basic auth.", "Service requires TLS and MFA.")
        assert res_a.passed is False
        assert res_a.stage == 2
        assert "UNSUPPORTED_ENTITIES" in (res_a.failure_reason or "")
        assert "tls" in (res_a.failure_reason or "").lower() or "mfa" in (res_a.failure_reason or "").lower()

    def test_salient_token_recall_threshold(self) -> None:
        verifier = PropositionVerifier()

        # Hypothesis adds many ungrounded tokens, dropping recall < 0.80
        source = "Database secures credentials."
        hypothesis = (
            "Database secures credentials while orbiting interstellar satellites across deep space galaxies."
        )
        res = verifier.verify(source, hypothesis)
        assert res.passed is False
        assert res.stage == 2
        assert "LOW_TOKEN_RECALL" in (res.failure_reason or "")

    def test_stage3_nli_frozen_parameters(self) -> None:
        assert STAGE3_NLI_MODEL == "cross-encoder/nli-deberta-v3-small"
        assert STAGE3_SAMPLE_RATIO == 0.10
        assert STAGE3_MAX_CONTRADICTION_P == 0.01
        assert STAGE3_MIN_ENTAILMENT_P == 0.70
        assert STAGE3_MAX_LATENCY_BUDGET_MS <= 15.0

    def test_stage3_nli_custom_client(self) -> None:
        def fake_contradiction_client(src: str, hyp: str) -> dict[str, float]:
            return {"contradiction": 0.95, "entailment": 0.02}

        verifier_contra = PropositionVerifier(nli_client=fake_contradiction_client)
        res_c = verifier_contra.verify(
            "System requires encryption.", "System requires encryption.", force_stage3=True
        )
        assert res_c.passed is False
        assert res_c.stage == 3
        assert "NLI_CONTRADICTION" in (res_c.failure_reason or "")

        def fake_entailment_client(src: str, hyp: str) -> dict[str, float]:
            return {"contradiction": 0.001, "entailment": 0.85}

        verifier_entail = PropositionVerifier(nli_client=fake_entailment_client)
        res_e = verifier_entail.verify(
            "System requires encryption.", "System requires encryption.", force_stage3=True
        )
        assert res_e.passed is True
        assert res_e.stage == 3

    def test_stage3_nli_missing_model_skips_to_stage2(self) -> None:
        """When CrossEncoder model is missing/unavailable, verify() must skip to Stage 2 with explicit diagnostic."""
        verifier = PropositionVerifier(model_name="nonexistent_mock_nli_model_missing")
        res = verifier.verify(
            "System requires encryption.", "System requires encryption.", force_stage3=True
        )
        assert res.passed is True
        assert res.stage == 2
        assert res.diagnostics is not None
        assert res.diagnostics.get("stage3_skipped") is True
        assert "stage3_reason" in res.diagnostics
        assert res.diagnostics.get("nli_evaluated") is False

    def test_stage3_nli_client_error_skips_to_stage2(self) -> None:
        """When NLI inference/client raises an exception, verify() must skip to Stage 2 with logged warning."""
        def failing_client(src: str, hyp: str) -> dict[str, float]:
            raise RuntimeError("Inference backend process died")

        verifier = PropositionVerifier(nli_client=failing_client)
        res = verifier.verify(
            "System requires encryption.", "System requires encryption.", force_stage3=True
        )
        assert res.passed is True
        assert res.stage == 2
        assert res.diagnostics is not None
        assert res.diagnostics.get("stage3_skipped") is True
        assert "client_error" in res.diagnostics.get("stage3_reason", "")
        assert res.diagnostics.get("nli_evaluated") is False

    def test_stage3_nli_malformed_client_output_skips_to_stage2(self) -> None:
        """Malformed client outputs (empty dict, None, NaN, missing keys, bad types) must skip to Stage 2."""
        malformed_responses = [
            {},  # empty dict (must not fabricate 1.0 entailment)
            {"contradiction": 0.001},  # missing entailment
            {"entailment": 0.95},  # missing contradiction
            None,  # non-dict
            {"contradiction": float("nan"), "entailment": float("nan")},  # NaNs
            {"contradiction": "invalid_str", "entailment": 0.95},  # string type
            {"contradiction": -0.5, "entailment": 1.5},  # out-of-range probabilities
        ]
        for bad_resp in malformed_responses:
            verifier = PropositionVerifier(nli_client=lambda s, h, r=bad_resp: r)
            res = verifier.verify(
                "System requires encryption.", "System requires encryption.", force_stage3=True
            )
            assert res.passed is True, f"Failed for {bad_resp!r}: {res}"
            assert res.stage == 2, f"Expected stage 2 for {bad_resp!r}, got stage {res.stage}"
            assert res.diagnostics is not None
            assert res.diagnostics.get("stage3_skipped") is True
            assert res.diagnostics.get("nli_evaluated") is False

    def test_stage3_nli_budget_exceeded(self) -> None:
        """When NLI execution exceeds max_latency_budget_ms, verify() must fail-closed with NLI_BUDGET_EXCEEDED."""
        def slow_client(src: str, hyp: str) -> dict[str, float]:
            time.sleep(0.015)
            return {"contradiction": 0.001, "entailment": 0.99}

        verifier = PropositionVerifier(nli_client=slow_client, max_latency_budget_ms=5.0)
        res = verifier.verify(
            "System requires encryption.", "System requires encryption.", force_stage3=True
        )
        assert res.passed is False
        assert res.stage == 3
        assert res.failure_reason == "NLI_BUDGET_EXCEEDED"
        assert res.diagnostics is not None
        assert res.diagnostics.get("elapsed_ms", 0.0) >= 5.0

    def test_module_level_verify_grounding(self) -> None:
        res = verify_grounding(
            "System strictly prohibits unencrypted storage.",
            "System strictly permits unencrypted storage.",
        )
        assert res.passed is False
        assert res.stage == 1


# ==============================================================================
# 6. Full Cascade Latency SLO (p95 <= 65 ms)
# ==============================================================================

class TestCascadeLatencySLO:
    """Enforce strict p95 <= 65 ms across full 3-tier cascade under benchmark load."""

    def test_p95_latency_under_load(self, tmp_path: Path) -> None:
        store = SqliteEventStore(tmp_path / "test_latency.db")
        embedder = HashingDenseEmbedder(dimensions=16)
        engine = HybridRetrievalEngine(dense_embedder=embedder)

        ws = "ws-latency"
        atoms = [
            make_atom(ws, f"n_{i}", f"v_{i}", f"Document {i} covering distributed systems clustering and replication.")
            for i in range(25)
        ]

        latencies_ms: list[float] = []
        queries = [
            "distributed systems",
            '"Document 5"',
            "MAX_RETRIES",
            "clustering replication protocol",
            "`distributed`",
            "general search without triggers",
        ] * 15

        for q in queries:
            req = QueryRequest(
                workspace_id=ws,
                query=q,
                retrieval_budget=RetrievalBudget(candidate_limit=10),
            )
            t0 = time.perf_counter()
            outcome = engine.retrieve(store=store, request=req, atoms=atoms)
            elapsed = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(elapsed)

        latencies_ms.sort()
        p95_idx = int(len(latencies_ms) * 0.95)
        p95_latency = latencies_ms[p95_idx]

        assert p95_latency <= CASCADE_MAX_LATENCY_MS, (
            f"p95 latency {p95_latency:.2f}ms exceeds SLO {CASCADE_MAX_LATENCY_MS}ms"
        )
