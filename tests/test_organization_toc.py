"""WP3 Acceptance Tests: L2 Macro-Topology (TOC-DAG) & Drift Monitor.

Scope:
- Deterministic bisecting spherical 2-means on |members| > 64.
- Diametrical seeds: s1 = argmax (1 - h . c0), s2 = argmax (1 - h . s1).
- Sorted-ID tie-breaking: bit-identical partitions across seeded/shuffled runs.
- Fan-out <= 64 strictly enforced on all leaf TOC nodes.
- Cohesion deadlock: intra-cluster Jaccard < 0.08 reassigns to neighbor or assigns to DIVERSE_OVERFLOW (cohesion_floor 0.0, STALE_CENTROID).
- Overflow node excluded from Tier 2 beam candidacy.
- Hyperspherical cosine drift monitor: flag STALE_CENTROID when 1 - (c0 . c_new) > 0.25 * R0_eff.
- Newborn holon 7-day apoptosis grace: age_days < 7 strictly exempt.
- Real SQLite storage integration with no mocks.
"""

from __future__ import annotations

import math
from pathlib import Path
import random
import sys
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from trace.v2.organization import (
    COHESION_FLOOR,
    DRIFT_EPSILON,
    MAX_TOC_FANOUT,
    MIN_EFFECTIVE_RADIUS,
    NEWBORN_APOPTOSIS_GRACE_DAYS,
    OVERFLOW_APOPTOSIS_DAYS,
    NODE_TYPE_DIVERSE_OVERFLOW,
    NODE_TYPE_STANDARD,
    TOC_STATUS_ACTIVE,
    TOC_STATUS_STALE_CENTROID,
    HolonMember,
    TOCNode,
    TOCPartitionManager,
    bisecting_spherical_2means,
    check_cohesion,
    detect_centroid_drift,
    evaluate_holon_energy,
    is_candidate_for_beam,
    is_newborn_apoptosis_exempt,
    is_overflow_orphan_apoptosis_eligible,
    normalize_holon_member,
    resolve_cohesion_deadlocks,
)
from trace.v2.store import SqliteEventStore


def _generate_synthetic_vector(seed: int, dim: int = 384) -> list[float]:
    """Generate deterministic unit vector on S^{dim-1}."""
    rng = random.Random(seed)
    raw = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


class TestDeterministicBisectingSpherical2Means:
    """Verify deterministic bisecting spherical 2-means and fan-out <= 64 enforcement."""

    def test_fanout_bound_enforced_on_large_cluster(self) -> None:
        """Clusters with |members| > 64 are bisected until all partitions satisfy fanout <= 64."""
        # Generate 150 members (requiring at least 3 leaf partitions to stay <= 64)
        members = []
        for i in range(150):
            members.append(
                HolonMember(
                    id=f"holon_{i:04d}",
                    centroid=_generate_synthetic_vector(seed=i),
                    lex_sig=["database", "index", f"term_{i % 5}"],
                )
            )

        partitions = bisecting_spherical_2means(members, max_fanout=64)
        assert len(partitions) >= 3

        total_members_partitioned = 0
        for p in partitions:
            # Non-negotiable structural bound: fan-out <= 64
            assert len(p.members) <= 64, f"Node {p.id} breached fanout bound: {len(p.members)}"
            assert len(p.members) > 0
            assert p.r0 >= MIN_EFFECTIVE_RADIUS
            total_members_partitioned += len(p.members)

        assert total_members_partitioned == 150

    def test_seeded_runs_bit_identical_across_shuffles(self) -> None:
        """Members iterated in strictly sorted-ID order guarantees bit-identical results."""
        # Create 80 members with distinct terms
        base_members = [
            HolonMember(
                id=f"h_{i:03d}",
                centroid=_generate_synthetic_vector(seed=i + 1000),
                lex_sig=["system", f"sig_{i % 4}"],
            )
            for i in range(80)
        ]

        # Run 1: natural order
        run1 = bisecting_spherical_2means(base_members, max_fanout=64)

        # Run 2: reversed order
        reversed_members = list(reversed(base_members))
        run2 = bisecting_spherical_2means(reversed_members, max_fanout=64)

        # Run 3: pseudo-random shuffle
        shuffled_members = list(base_members)
        random.Random(42).shuffle(shuffled_members)
        run3 = bisecting_spherical_2means(shuffled_members, max_fanout=64)

        assert len(run1) == len(run2) == len(run3)

        for p1, p2, p3 in zip(run1, run2, run3, strict=True):
            assert p1.id == p2.id == p3.id
            assert p1.members == p2.members == p3.members
            assert p1.r0 == p2.r0 == p3.r0
            assert p1.c0_bytes == p2.c0_bytes == p3.c0_bytes

    def test_boundary_within_capacity_not_split(self) -> None:
        """Clusters with |members| <= 64 remain a single partition."""
        members = [
            HolonMember(
                id=f"h_{i:02d}",
                centroid=_generate_synthetic_vector(seed=i + 50),
                lex_sig=["engine", "cortex"],
            )
            for i in range(64)
        ]
        partitions = bisecting_spherical_2means(members, max_fanout=64)
        assert len(partitions) == 1
        assert len(partitions[0].members) == 64


class TestCohesionDeadlockAndOverflowGovernance:
    """Verify Appendix A Row 4 & 12: Cohesion deadlock resolution & DIVERSE_OVERFLOW governance."""

    def test_cohesion_check_intra_cluster_jaccard(self) -> None:
        """Intra-cluster Jaccard affinity >= 0.08 and min 1 shared term."""
        # Cohesive cluster: all share terms
        cohesive = [
            HolonMember("m1", _generate_synthetic_vector(1), lex_sig=["apple", "banana", "cherry"]),
            HolonMember("m2", _generate_synthetic_vector(2), lex_sig=["banana", "cherry", "date"]),
            HolonMember("m3", _generate_synthetic_vector(3), lex_sig=["cherry", "date", "fig"]),
        ]
        valid, score = check_cohesion(cohesive)
        assert valid is True
        assert score >= COHESION_FLOOR

        # Disjoint/deadlocked cluster: zero shared terms
        deadlocked = [
            HolonMember("m1", _generate_synthetic_vector(1), lex_sig=["alpha", "beta"]),
            HolonMember("m2", _generate_synthetic_vector(2), lex_sig=["gamma", "delta"]),
        ]
        valid, score = check_cohesion(deadlocked)
        assert valid is False
        assert score == 0.0

    def test_cohesion_deadlock_routes_to_overflow(self) -> None:
        """Deadlocked members with no compatible neighbor route to DIVERSE_OVERFLOW."""
        # 2 partitions: Node 1 is cohesive, Node 2 violates cohesion
        members = {
            "c1": HolonMember("c1", _generate_synthetic_vector(10), lex_sig=["token", "embedding"]),
            "c2": HolonMember("c2", _generate_synthetic_vector(11), lex_sig=["token", "embedding"]),
            "d1": HolonMember("d1", _generate_synthetic_vector(20), lex_sig=["alien", "mars"]),
            "d2": HolonMember("d2", _generate_synthetic_vector(21), lex_sig=["quantum", "physics"]),
        }

        # Node 1: cohesive
        node1 = TOCNode(
            id="toc_1",
            parent="root",
            c0=_generate_synthetic_vector(10),
            r0=0.1,
            members=["c1", "c2"],
            boundary={"cohesion_floor": 0.08},
        )
        # Node 2: deadlock (d1 and d2 have 0 term overlap and disjoint from Node 1)
        node2 = TOCNode(
            id="toc_2",
            parent="root",
            c0=_generate_synthetic_vector(20),
            r0=0.5,
            members=["d1", "d2"],
            boundary={"cohesion_floor": 0.08},
        )

        resolved = resolve_cohesion_deadlocks([node1, node2], members, parent_id="root", max_fanout=64)

        # Expect node1 retained, and a DIVERSE_OVERFLOW node created
        node_types = [n.node_type for n in resolved]
        assert NODE_TYPE_STANDARD in node_types
        assert NODE_TYPE_DIVERSE_OVERFLOW in node_types

        overflow_nodes = [n for n in resolved if n.node_type == NODE_TYPE_DIVERSE_OVERFLOW]
        assert len(overflow_nodes) == 1
        assert overflow_nodes[0].boundary["cohesion_floor"] == 0.0
        assert overflow_nodes[0].status == TOC_STATUS_STALE_CENTROID
        assert set(overflow_nodes[0].members) == {"d1", "d2"}

    def test_overflow_node_beam_exclusion(self) -> None:
        """Appendix A Row 12: DIVERSE_OVERFLOW nodes are strictly excluded from beam search."""
        standard_node = TOCNode(
            id="toc_std", parent="root", c0=[0.0] * 384, r0=0.1, members=["h1"],
            boundary={"cohesion_floor": 0.08}, node_type=NODE_TYPE_STANDARD,
        )
        overflow_node = TOCNode(
            id="toc_ovf", parent="root", c0=[0.0] * 384, r0=0.5, members=["h2"],
            boundary={"cohesion_floor": 0.0}, status=TOC_STATUS_STALE_CENTROID,
            node_type=NODE_TYPE_DIVERSE_OVERFLOW,
        )

        assert is_candidate_for_beam(standard_node) is True
        assert is_candidate_for_beam(overflow_node) is False

        # Dictionary format compatibility
        assert is_candidate_for_beam(standard_node.to_dict()) is True
        assert is_candidate_for_beam(overflow_node.to_dict()) is False


class TestHypersphericalDriftMonitor:
    """Verify Hyperspherical Cosine Drift Monitor: 1 - (c0 . c_new) > 0.25 * R0_eff."""

    def test_drift_flag_triggered_on_substantial_movement(self) -> None:
        """When centroid drifts by more than 0.25 * R0_eff, STALE_CENTROID is flagged."""
        v0 = _generate_synthetic_vector(100)
        # Create drifted vector v_new
        v_new = _generate_synthetic_vector(101)  # Orthogonal/drifted random vector

        r0_eff = 0.20
        # 1 - (v0 . v_new) ~ 1.0 > 0.25 * 0.20 = 0.05
        is_stale, delta_cos, thresh = detect_centroid_drift(v0, v_new, r0=r0_eff, drift_epsilon=DRIFT_EPSILON)

        assert is_stale is True
        assert thresh == pytest.approx(0.05)
        assert delta_cos > thresh

    def test_drift_flag_not_triggered_on_minor_perturbation(self) -> None:
        """Centroid updates within 0.25 * R0_eff remain ACTIVE without stale flag."""
        v0 = _generate_synthetic_vector(200)
        # Slight perturbation: 0.999 * v0 + 0.001 * noise
        noise = _generate_synthetic_vector(201)
        v_pert = [v0[i] * 0.999 + noise[i] * 0.001 for i in range(len(v0))]
        norm = math.sqrt(sum(x * x for x in v_pert))
        v_new = [x / norm for x in v_pert]

        is_stale, delta_cos, thresh = detect_centroid_drift(v0, v_new, r0=0.10, drift_epsilon=DRIFT_EPSILON)
        assert is_stale is False
        assert delta_cos <= thresh


class TestNewbornHolonApoptosisGrace:
    """Verify Appendix A Row 9: 7-day newborn apoptosis grace and energy floor."""

    def test_energy_formula_floored_at_zero(self) -> None:
        """energy = max(0.0, 1.0*hits_7d + 0.5*centrality - 0.02*age_days)."""
        # Old holon with zero hits: 0 + 0 - 0.02 * 100 = -2.0 -> floored at 0.0
        energy = evaluate_holon_energy(hits_7d=0.0, centrality=0.0, age_days=100.0)
        assert energy == 0.0

        # Active holon
        energy_active = evaluate_holon_energy(hits_7d=5.0, centrality=0.4, age_days=10.0)
        assert energy_active == pytest.approx(5.0 + 0.2 - 0.2)

    def test_newborn_grace_period_exemption(self) -> None:
        """Holons with age_days < 7 are strictly exempt from apoptosis pruning."""
        newborn = HolonMember("newborn", [0.0] * 384, age_days=3.0, energy=0.0)
        mature = HolonMember("mature", [0.0] * 384, age_days=14.0, energy=0.0)

        assert is_newborn_apoptosis_exempt(newborn, grace_days=NEWBORN_APOPTOSIS_GRACE_DAYS) is True
        assert is_newborn_apoptosis_exempt(mature, grace_days=NEWBORN_APOPTOSIS_GRACE_DAYS) is False


class TestRealSqliteStorageIntegration:
    """Verify real SQLite database integration for L2 TOC nodes and partition manager (no mocks)."""

    def test_partition_manager_persists_to_sqlite(self, tmp_path: Path) -> None:
        """TOCPartitionManager partitions members and writes valid TOC rows to SQLite."""
        db_path = tmp_path / "toc_test.db"
        store = SqliteEventStore(str(db_path))

        manager = TOCPartitionManager(store=store, max_fanout=64)

        # 70 members requiring bisection
        members = [
            {
                "id": f"h_{i:03d}",
                "centroid": _generate_synthetic_vector(seed=i + 500),
                "lex_sig": ["kernel", "driver", f"mod_{i % 3}"],
                "hits_7d": 1.0,
                "centrality": 0.1,
                "age_days": 2.0,
            }
            for i in range(70)
        ]

        nodes = manager.partition_members(members, parent_id="root_toc")
        assert len(nodes) == 2
        for n in nodes:
            assert len(n.members) <= 64
            # Verify persisted in SQLite
            persisted = store.get_toc_node(n.id)
            assert persisted is not None
            assert persisted["id"] == n.id
            assert persisted["parent"] == "root_toc"
            assert len(persisted["members"]) == len(n.members)

        # Test drift checking via store
        is_stale, delta_cos, thresh = manager.check_drift(
            toc_id=nodes[0].id,
            new_centroid=_generate_synthetic_vector(seed=9999),  # heavily drifted
        )
        assert is_stale is True

        # Verify status in store updated to STALE_CENTROID
        updated = store.get_toc_node(nodes[0].id)
        assert updated is not None
        assert updated["status"] == TOC_STATUS_STALE_CENTROID

        store.close()

    def test_beam_exclusion_with_raw_sqlite_boundary_json(self) -> None:
        """is_candidate_for_beam must not crash on raw string boundary JSON and stale centroid."""
        row_overflow = {
            "id": "toc_ovf",
            "status": TOC_STATUS_STALE_CENTROID,
            "boundary": '{"cohesion_floor": 0.0, "node_type": "DIVERSE_OVERFLOW"}',
        }
        assert is_candidate_for_beam(row_overflow) is False

        row_standard = {
            "id": "toc_std",
            "status": TOC_STATUS_ACTIVE,
            "boundary": '{"cohesion_floor": 0.08, "node_type": "STANDARD"}',
        }
        assert is_candidate_for_beam(row_standard) is True

    def test_newborn_grace_period_from_created_at(self) -> None:
        """normalize_holon_member and is_newborn_apoptosis_exempt calculate age from created_at."""
        old_item = {"id": "old", "created_at": "2026-08-01T00:00:00Z", "centroid": [0.0] * 384}
        old_m = normalize_holon_member(old_item)
        assert old_m.age_days > 20.0
        assert is_newborn_apoptosis_exempt(old_m) is False

        new_item = {"id": "new", "created_at": "2026-09-06T00:00:00Z", "centroid": [0.0] * 384}
        new_m = normalize_holon_member(new_item)
        assert new_m.age_days < 5.0
        assert is_newborn_apoptosis_exempt(new_m) is True

    def test_overflow_orphan_apoptosis_30_day_policy(self) -> None:
        """DIVERSE_OVERFLOW nodes are subject to 30-day orphan apoptosis policy."""
        old_ovf = {
            "node_type": NODE_TYPE_DIVERSE_OVERFLOW,
            "created_at": "2026-08-01T00:00:00Z",
        }
        young_ovf = {
            "node_type": NODE_TYPE_DIVERSE_OVERFLOW,
            "created_at": "2026-09-05T00:00:00Z",
        }
        std_node = {
            "node_type": NODE_TYPE_STANDARD,
            "created_at": "2026-08-01T00:00:00Z",
        }

        # Mature orphan overflow node is eligible
        assert is_overflow_orphan_apoptosis_eligible(old_ovf, is_orphaned=True) is True
        # Young overflow node is not eligible
        assert is_overflow_orphan_apoptosis_eligible(young_ovf, is_orphaned=True) is False
        # Non-orphaned overflow node is not eligible
        assert is_overflow_orphan_apoptosis_eligible(old_ovf, is_orphaned=False) is False
        # Standard node is not eligible
        assert is_overflow_orphan_apoptosis_eligible(std_node, is_orphaned=True) is False

    def test_deadlock_neighbor_reassignment_maintains_sort_and_boundary(self) -> None:
        """Reassigning deadlocked member preserves sorted ID order and updates boundary."""
        members = {
            "m1": HolonMember("m1", [1.0, 0.0], lex_sig=["shared", "alpha"]),
            "m2": HolonMember("m2", [1.0, 0.0], lex_sig=["shared", "beta"]),
            "m0": HolonMember("m0", [1.0, 0.0], lex_sig=["shared", "gamma"]),
            "m_dead": HolonMember("m_dead", [0.0, 1.0], lex_sig=["unrelated"]),
        }
        node1 = TOCNode(
            id="n1", parent="root", c0=[1.0, 0.0], r0=0.1, members=["m1", "m2"],
            boundary={"cohesion_floor": 0.08, "radius": 0.1, "cohesion_score": 0.5},
        )
        node2 = TOCNode(
            id="n2", parent="root", c0=[0.0, 1.0], r0=0.1, members=["m0", "m_dead"],
            boundary={"cohesion_floor": 0.08, "radius": 0.1, "cohesion_score": 0.0},
        )

        res = resolve_cohesion_deadlocks([node1, node2], members, max_fanout=64)
        n1_res = [n for n in res if n.id == "n1"][0]
        # Must be sorted by ID: m0 before m1, m2
        assert n1_res.members == ["m0", "m1", "m2"]
        assert n1_res.boundary["cohesion_score"] > 0.0

    def test_empty_members_bisecting(self) -> None:
        """bisecting_spherical_2means returns empty list when given no members."""
        assert bisecting_spherical_2means([], max_fanout=64) == []

