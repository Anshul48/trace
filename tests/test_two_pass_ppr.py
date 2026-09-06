"""WP0 Calibration Fixtures & Prior Fitting: Two-Pass Lateral Rectification PPR Skeleton.

Target File: tests/test_two_pass_ppr.py
Scope: WP0 calibration fixtures, Appendix A row-1 (PPR Suppression Divide-by-Zero guard),
Appendix A row-7 priors (beta=1.0, RRF floor=0.012, drift eps=0.25), Two-Pass Lateral
Rectification PPR reference engine, and downstream WP4 engine integration tests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest


# ==============================================================================
# Appendix A Row-1 & Row-7 Frozen Priors
# ==============================================================================

@dataclass(frozen=True)
class PPRPriors:
    """Frozen priors per CORTICAL_SUBSTRATE_V1_PLAN Appendix A (Rows 1 & 7)."""

    beta_lateral_inhibition: float = 1.0
    rrf_score_floor: float = 0.012
    drift_epsilon: float = 0.25
    max_iterations: int = 20
    max_steps: int = 2500
    damping_factor: float = 0.85
    degree_cap_per_type: int = 50
    degree_cap_total: int = 128


FROZEN_PPR_PRIORS = PPRPriors()


# ==============================================================================
# Graph & Edge Definitions
# ==============================================================================

@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    edge_type: str  # COMPILED_FROM, REFERENCES, SEE_ALSO, SUBSUMES, MUTUALLY_EXCLUSIVE
    weight: float   # w >= 0 for excitatory, |w^-| in [0, 1] for MUTUALLY_EXCLUSIVE


@dataclass
class TwoPassPPRResult:
    excitatory_scores: dict[str, float]
    rectified_scores: dict[str, float]
    final_scores: dict[str, float]
    suppression_fallback_triggered: bool
    iterations: int


# ==============================================================================
# Algorithmic Reference Engine: Two-Pass Lateral Rectification PPR
# ==============================================================================

class ReferenceTwoPassPPREngine:
    """Mathematical reference implementation of Two-Pass Non-Negative Lateral Rectification PPR.

    Pass 1: Excitatory diffusion over non-negative edges E+ via power iteration.
    Pass 2: Lateral inhibitory suppression:
            s_rect(v) = max(0, s+(v) - beta * max_{(u, v) in E^-} (|w^-_{uv}| * s+(u)))
    Divide-by-zero guard: if ||s_rect||_1 <= 0, fall back to s+.
    Renormalize: s_final = s_rect / ||s_rect||_1.
    """

    def __init__(self, priors: PPRPriors = FROZEN_PPR_PRIORS) -> None:
        self.priors = priors

    def run(
        self,
        nodes: Sequence[str],
        seed_scores: Mapping[str, float],
        edges: Sequence[Edge],
    ) -> TwoPassPPRResult:
        if not nodes:
            return TwoPassPPRResult({}, {}, {}, False, 0)

        # Separate E+ (excitatory) and E- (inhibitory / MUTUALLY_EXCLUSIVE)
        e_plus: dict[str, list[tuple[str, float]]] = {n: [] for n in nodes}
        e_minus: dict[str, list[tuple[str, float]]] = {n: [] for n in nodes}

        for edge in edges:
            if edge.src not in e_plus or edge.dst not in e_plus:
                continue
            if edge.edge_type == "MUTUALLY_EXCLUSIVE":
                # E- edges store positive magnitude |w^-| in [0, 1]
                e_minus[edge.dst].append((edge.src, abs(edge.weight)))
            else:
                # E+ non-negative excitatory edges
                if edge.weight > 0:
                    e_plus[edge.src].append((edge.dst, float(edge.weight)))

        # Normalize seed distribution p0
        positive_seeds = {n: max(0.0, float(seed_scores.get(n, 0.0))) for n in nodes}
        seed_sum = sum(positive_seeds.values())
        if seed_sum <= 0:
            p0 = {n: 1.0 / len(nodes) for n in nodes}
        else:
            p0 = {n: val / seed_sum for n, val in positive_seeds.items()}

        # Build stochastic transition matrix P+
        transition: dict[str, list[tuple[str, float]]] = {}
        for src, out_edges in e_plus.items():
            total_out = sum(w for _, w in out_edges)
            if total_out > 0:
                transition[src] = [(dst, w / total_out) for dst, w in out_edges]
            else:
                transition[src] = []

        # Pass 1: Excitatory Diffusion Power Iteration
        # p^{(t+1)} = alpha * p^{(t)} P^+ + (1 - alpha) * p0
        alpha = self.priors.damping_factor
        current = dict(p0)
        completed_iterations = 0

        for it in range(self.priors.max_iterations):
            completed_iterations = it + 1
            following = {n: (1.0 - alpha) * p0[n] for n in nodes}
            for src in nodes:
                val = current[src]
                row = transition.get(src, [])
                if not row:
                    # Dangling node redistribution
                    following[src] += alpha * val
                    continue
                for dst, prob in row:
                    following[dst] += alpha * val * prob

            delta = sum(abs(following[n] - current[n]) for n in nodes)
            current = following
            if delta < 1e-7:
                break

        s_plus = current

        # Pass 2: Lateral Inhibitory Suppression
        # s_rect(v) = max(0, s+(v) - beta * max_{(u, v) in E^-} (|w^-_{uv}| * s+(u)))
        beta = self.priors.beta_lateral_inhibition
        s_rect: dict[str, float] = {}

        for v in nodes:
            inhibitors = e_minus.get(v, [])
            if not inhibitors:
                s_rect[v] = max(0.0, s_plus[v])
            else:
                max_inhibition = max(abs(w_neg) * s_plus[u] for u, w_neg in inhibitors)
                s_rect[v] = max(0.0, s_plus[v] - (beta * max_inhibition))

        # Appendix A Row-1 Guard: Divide-by-Zero Rectification Check
        # If all candidates inhibited, fall back to excitatory baseline s+
        norm_1 = sum(s_rect.values())
        fallback_triggered = False

        if norm_1 <= 0:
            fallback_triggered = True
            norm_excitatory = sum(s_plus.values())
            if norm_excitatory <= 0:
                s_final = {n: 1.0 / len(nodes) for n in nodes}
            else:
                s_final = {n: s_plus[n] / norm_excitatory for n in nodes}
        else:
            s_final = {n: s_rect[n] / norm_1 for n in nodes}

        return TwoPassPPRResult(
            excitatory_scores=s_plus,
            rectified_scores=s_rect,
            final_scores=s_final,
            suppression_fallback_triggered=fallback_triggered,
            iterations=completed_iterations,
        )


# ==============================================================================
# Calibration Tests: Appendix A Row-1 & Row-7 Priors
# ==============================================================================

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
        engine = ReferenceTwoPassPPREngine()
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
        engine = ReferenceTwoPassPPREngine()
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
        engine = ReferenceTwoPassPPREngine()
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


# ==============================================================================
# Engine Integration Tests (Asserting Against cortex.py)
# ==============================================================================

class TestCortexEngineTwoPassPPR:
    """Assert against src/trace/v2/cortex.py.

    Downstream Work Packet WP4 implements Two-Pass Lateral Rectification PPR in Cortex.
    Engine-dependent assertions are marked xfail with WP4 reason.
    """

    @pytest.mark.xfail(
        reason="WP4 Two-Pass Lateral Rectification PPR Engine unblocks this",
        strict=False,
    )
    def test_engine_two_pass_ppr_rectification(self) -> None:
        """WP4 acceptance test: Cortex ActivationEngine supports two-pass lateral rectification."""
        from trace.v2 import cortex

        if hasattr(cortex, "TwoPassPPREngine"):
            engine_cls = getattr(cortex, "TwoPassPPREngine")
            eng = engine_cls()
            assert eng is not None
        elif hasattr(cortex, "ActivationEngine") and hasattr(cortex.ActivationEngine, "activate_two_pass"):
            eng = cortex.ActivationEngine()
            assert hasattr(eng, "activate_two_pass")
        else:
            pytest.fail("cortex does not yet implement TwoPassPPREngine (WP4 pending)")
