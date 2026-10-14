"""WP4 Acceptance Tests: Two-Pass Lateral Rectification PPR.

Scope:
- Pass 1: Excitatory diffusion over non-negative edges E+ via power iteration (<= 20 iters, <= 2500 steps, non-negative W only).
- Pass 2: Lateral inhibitory suppression: s_rect(v) = max(0, s+(v) - beta * max_{(u, v) in E^-} (|w^-_{uv}| * s+(u))) with beta = 1.0.
- Divide-by-zero guard: if ||s_rect||_1 <= 0, fall back to excitatory baseline s+.
- Renormalize: s_final = s_rect / ||s_rect||_1.
- Degree caps: 50 per type, 128 total across types.
- Acceptance criteria: test_two_pass_ppr.py passes, zero NaN/Inf, <= 35 ms.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import time
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from trace.v2.cortex import (
    Edge,
    PPRPriors,
    FROZEN_PPR_PRIORS,
    TwoPassPPRResult,
    TwoPassPPREngine,
    ActivationEngine,
)


class TestTwoPassPPRCalibrationPriors:
    """Verify Appendix A priors and mathematical invariants of Two-Pass PPR."""

    def test_frozen_ppr_priors_immutability(self) -> None:
        """Appendix A Row 7 priors: beta=1.0, RRF floor=0.012, drift eps=0.25."""
        assert FROZEN_PPR_PRIORS.beta_lateral_inhibition == 1.0
        assert FROZEN_PPR_PRIORS.rrf_score_floor == 0.012
        assert FROZEN_PPR_PRIORS.drift_epsilon == 0.25
        assert FROZEN_PPR_PRIORS.max_iterations == 20
        assert FROZEN_PPR_PRIORS.max_steps == 2500
        assert FROZEN_PPR_PRIORS.damping_factor == 0.85
        assert FROZEN_PPR_PRIORS.degree_cap_per_type == 50
        assert FROZEN_PPR_PRIORS.degree_cap_total == 128

        # Invariant: Priors are immutable
        with pytest.raises(Exception):
            FROZEN_PPR_PRIORS.beta_lateral_inhibition = 0.5  # type: ignore

    def test_ppr_pass1_excitatory_diffusion_non_negative(self) -> None:
        """Excitatory diffusion over non-negative edges produces monotonic non-negative scores."""
        engine = TwoPassPPREngine()
        nodes = ["A", "B", "C"]
        edges = [
            Edge("A", "B", "REFERENCES", 1.0),
            Edge("B", "C", "REFERENCES", 1.0),
        ]
        seeds = {"A": 1.0, "B": 0.0, "C": 0.0}

        result = engine.run(nodes, seeds, edges)
        assert result.iterations >= 1
        assert not result.suppression_fallback_triggered

        # Monotonicity & non-negativity
        for n in nodes:
            assert result.final_scores[n] >= 0.0
            assert not math.isnan(result.final_scores[n])
            assert not math.isinf(result.final_scores[n])

        assert math.isclose(sum(result.final_scores.values()), 1.0, rel_tol=1e-5)
        # Activation flows from A -> B -> C
        assert result.final_scores["A"] > 0.0
        assert result.final_scores["B"] > 0.0
        assert result.final_scores["C"] > 0.0

    def test_ppr_pass2_lateral_inhibition_suppression(self) -> None:
        """Pass 2 lateral inhibition suppresses node linked by MUTUALLY_EXCLUSIVE edge."""
        engine = TwoPassPPREngine()
        # A and B are alternative conflicting interpretations
        nodes = ["Seed", "Hypo_A", "Hypo_B"]
        edges = [
            Edge("Seed", "Hypo_A", "REFERENCES", 0.8),
            Edge("Seed", "Hypo_B", "REFERENCES", 0.2),
            # Hypo_A strongly inhibits Hypo_B
            Edge("Hypo_A", "Hypo_B", "MUTUALLY_EXCLUSIVE", 1.0),
        ]
        seeds = {"Seed": 1.0}

        result = engine.run(nodes, seeds, edges)

        # In Pass 1, Hypo_B has some positive excitatory flow from Seed
        assert result.excitatory_scores["Hypo_B"] > 0.0

        # In Pass 2, strong lateral inhibition from dominant Hypo_A suppresses Hypo_B to 0
        assert result.rectified_scores["Hypo_B"] == 0.0
        assert result.final_scores["Hypo_B"] == 0.0

        # Dominant candidate Hypo_A retains high activation
        assert result.final_scores["Hypo_A"] > 0.0
        assert math.isclose(sum(result.final_scores.values()), 1.0, rel_tol=1e-5)

    def test_ppr_suppression_divide_by_zero_fallback(self) -> None:
        """Appendix A Row 1 Acceptance:

        If all candidate nodes are suppressed by mutual inhibition (||s_rect||_1 <= 0),
        the engine must fall back to excitatory baseline s+ without throwing NaN or division-by-zero.
        """
        engine = TwoPassPPREngine()
        nodes = ["X", "Y"]
        # Both nodes mutually inhibit each other with overwhelming weight
        edges = [
            Edge("X", "Y", "MUTUALLY_EXCLUSIVE", 1.0),
            Edge("Y", "X", "MUTUALLY_EXCLUSIVE", 1.0),
        ]
        seeds = {"X": 0.5, "Y": 0.5}

        result = engine.run(nodes, seeds, edges)

        # Both nodes suppressed each other: s_rect = {X: 0.0, Y: 0.0}
        assert result.rectified_scores["X"] == 0.0
        assert result.rectified_scores["Y"] == 0.0

        # Row-1 Guard must trigger fallback
        assert result.suppression_fallback_triggered is True

        # Final scores fall back to excitatory baseline s+ (summing to 1.0, no NaNs)
        for n in nodes:
            assert not math.isnan(result.final_scores[n])
            assert not math.isinf(result.final_scores[n])
            assert result.final_scores[n] > 0.0

        assert math.isclose(sum(result.final_scores.values()), 1.0, rel_tol=1e-5)
        assert math.isclose(result.final_scores["X"], 0.5, rel_tol=1e-5)
        assert math.isclose(result.final_scores["Y"], 0.5, rel_tol=1e-5)

    def test_activation_engine_activate_two_pass_bridge(self) -> None:
        """ActivationEngine provides activate_two_pass() interface matching TwoPassPPREngine."""
        engine = ActivationEngine()
        edges = [
            {"src": "N1", "dst": "N2", "type": "REFERENCES", "weight": 1.0},
            {"src": "N2", "dst": "N3", "type": "MUTUALLY_EXCLUSIVE", "weight": 1.0},
        ]
        seeds = {"N1": 1.0, "N3": 0.2}

        result = engine.activate_two_pass(seed_scores=seeds, edges=edges)
        assert isinstance(result, TwoPassPPRResult)
        assert "N1" in result.final_scores
        assert "N2" in result.final_scores
        assert "N3" in result.final_scores
        assert result.final_scores["N3"] == 0.0  # inhibited by N2


class TestTwoPassPPREngineBoundariesAndSLO:
    """Verify performance SLO (<= 35 ms), iteration bound (<= 20 iters, <= 2500 steps), and degree caps."""

    def test_latency_slo_under_35ms(self) -> None:
        """WP4 Acceptance SLO: Two-Pass PPR execution completes in <= 35 ms."""
        engine = TwoPassPPREngine()
        # Create a 200-node graph with multiple edge types and cycles
        nodes = [f"node_{i:04d}" for i in range(200)]
        edges: list[Edge] = []
        for i in range(199):
            edges.append(Edge(nodes[i], nodes[i + 1], "REFERENCES", 0.9))
            if i % 3 == 0 and i + 5 < 200:
                edges.append(Edge(nodes[i], nodes[i + 5], "SEE_ALSO", 0.5))
            if i % 5 == 0 and i + 2 < 200:
                edges.append(Edge(nodes[i], nodes[i + 2], "MUTUALLY_EXCLUSIVE", 0.7))

        seeds = {nodes[0]: 1.0, nodes[10]: 0.5}

        # Warm up
        engine.run(nodes, seeds, edges)

        # Benchmark run
        start = time.perf_counter()
        result = engine.run(nodes, seeds, edges)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert elapsed_ms <= 35.0, f"Latency breached 35ms SLO: {elapsed_ms:.2f} ms"
        assert result.iterations <= 20
        assert result.step_count <= 2500
        for val in result.final_scores.values():
            assert not math.isnan(val)
            assert not math.isinf(val)
            assert val >= 0.0

    def test_degree_caps_enforced(self) -> None:
        """Verify per-type degree cap (50) and total degree cap (128) per node."""
        engine = TwoPassPPREngine()
        nodes = ["Hub"] + [f"Target_{i}" for i in range(200)]
        # Hub has 80 REFERENCES edges and 80 SEE_ALSO edges
        edges: list[Edge] = []
        for i in range(80):
            edges.append(Edge("Hub", f"Target_{i}", "REFERENCES", 1.0 - (i * 0.005)))
        for i in range(80, 160):
            edges.append(Edge("Hub", f"Target_{i}", "SEE_ALSO", 0.8 - ((i - 80) * 0.005)))

        seeds = {"Hub": 1.0}
        result = engine.run(nodes, seeds, edges)

        # REFERENCES was capped at 50, SEE_ALSO was capped at 50, total <= 128
        # Targets past 50 for REFERENCES should receive 0 score
        assert result.final_scores["Target_0"] > 0.0
        assert result.final_scores["Target_49"] > 0.0
        assert result.final_scores["Target_50"] == 0.0  # Excluded by degree cap of 50

    def test_step_budget_cap(self) -> None:
        """Step budget <= 2500 cap terminates iteration if exceeded."""
        priors = PPRPriors(max_steps=50, max_iterations=20)
        engine = TwoPassPPREngine(priors=priors)
        nodes = [f"N_{i}" for i in range(30)]
        edges = [Edge(nodes[i], nodes[j], "REFERENCES", 1.0) for i in range(30) for j in range(30) if i != j]
        seeds = {nodes[0]: 1.0}

        result = engine.run(nodes, seeds, edges)
        assert result.step_count <= 60  # Terminated within step budget
        assert result.iterations <= 20
        assert math.isclose(sum(result.final_scores.values()), 1.0, rel_tol=1e-5)

    def test_zero_ghost_activations(self) -> None:
        """Disconnected nodes with zero seed receive exactly 0.0 activation."""
        engine = TwoPassPPREngine()
        nodes = ["Connected_A", "Connected_B", "Isolated_Ghost"]
        edges = [Edge("Connected_A", "Connected_B", "REFERENCES", 1.0)]
        seeds = {"Connected_A": 1.0}

        result = engine.run(nodes, seeds, edges)
        assert result.final_scores["Isolated_Ghost"] == 0.0
        assert result.excitatory_scores["Isolated_Ghost"] == 0.0
        assert result.rectified_scores["Isolated_Ghost"] == 0.0

    def test_empty_nodes_and_seeds(self) -> None:
        """Empty node list returns safe empty result."""
        engine = TwoPassPPREngine()
        result = engine.run([], {}, [])
        assert result.iterations == 0
        assert result.final_scores == {}

    def test_subnormal_mutual_inhibition_fallback_triggered(self) -> None:
        """Floating point subnormal residuals in mutual inhibition must trigger divide-by-zero fallback."""
        engine = TwoPassPPREngine()
        nodes = ["X", "Y"]
        edges = [
            Edge("X", "Y", "MUTUALLY_EXCLUSIVE", 1.0),
            Edge("Y", "X", "MUTUALLY_EXCLUSIVE", 1.0),
        ]
        # Tiny numerical asymmetry simulating float subtraction noise
        seeds = {"X": 0.5 + 1e-16, "Y": 0.5}

        result = engine.run(nodes, seeds, edges)
        assert result.suppression_fallback_triggered is True
        assert not math.isnan(result.final_scores["X"])
        assert not math.isnan(result.final_scores["Y"])
        assert math.isclose(result.final_scores["X"], 0.5, rel_tol=1e-5)
        assert math.isclose(result.final_scores["Y"], 0.5, rel_tol=1e-5)

    def test_unseeded_nodes_zero_ghost_activations(self) -> None:
        """Unseeded graph queries must not manufacture activations out of thin air."""
        engine = TwoPassPPREngine()
        nodes = ["A", "B", "C"]
        edges = [Edge("A", "B", "REFERENCES", 1.0)]
        result = engine.run(nodes, {}, edges)

        assert result.iterations == 0
        for n in nodes:
            assert result.final_scores[n] == 0.0
            assert result.excitatory_scores[n] == 0.0
            assert result.rectified_scores[n] == 0.0

    def test_nan_and_inf_resilience(self) -> None:
        """NaN and Inf in seeds or edge weights are safely filtered with zero NaN/Inf outputs."""
        engine = TwoPassPPREngine()
        nodes = ["A", "B", "C"]
        edges = [
            Edge("A", "B", "REFERENCES", float("nan")),
            Edge("B", "C", "REFERENCES", float("inf")),
            Edge("A", "C", "REFERENCES", 1.0),
        ]
        seeds = {"A": 1.0, "B": float("nan"), "C": float("-inf")}

        result = engine.run(nodes, seeds, edges)
        for n in nodes:
            assert not math.isnan(result.final_scores[n])
            assert not math.isinf(result.final_scores[n])
            assert result.final_scores[n] >= 0.0

    def test_step_budget_interruption_preserves_simplex(self) -> None:
        """Dense graph power iteration truncated mid-iteration preserves probability simplex on s+."""
        priors = PPRPriors(max_steps=4, max_iterations=20)
        engine = TwoPassPPREngine(priors=priors)
        nodes = ["A", "B", "C", "D"]
        edges = [Edge(u, v, "REFERENCES", 1.0) for u in nodes for v in nodes if u != v]
        seeds = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}

        result = engine.run(nodes, seeds, edges)
        assert math.isclose(sum(result.excitatory_scores.values()), 1.0, rel_tol=1e-5)
        assert math.isclose(sum(result.final_scores.values()), 1.0, rel_tol=1e-5)

