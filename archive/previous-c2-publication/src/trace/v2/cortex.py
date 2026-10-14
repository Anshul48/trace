"""Replaceable Cortex primitives.

This module deliberately has no database or model-provider dependency.  The
Spine owns facts and source anchors; these helpers only operate on bounded,
already-authorized projection rows supplied by a repository.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from .models import ActivationWeights


PROJECTION_RUN_STATUSES = frozenset({"queued", "running", "succeeded", "failed", "superseded", "active"})
ACTIVATION_FAMILIES = frozenset({"structural", "trusted_evidence", "affinity", "behavioral"})


def canonical_pair(left: str, right: str) -> tuple[str, str]:
    """Return a stable undirected affinity identity without losing endpoints."""

    if not left or not right or left == right:
        raise ValueError("an affinity pair requires two distinct non-empty atom-version IDs")
    return (left, right) if left < right else (right, left)


@dataclass(frozen=True)
class ActivationEdge:
    """One query-local, non-factual transition candidate."""

    source_id: str
    target_id: str
    family: str
    weight: float = 1.0
    edge_id: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ActivationResult:
    scores: dict[str, float]
    contributions: dict[str, dict[str, float]]
    traversed_edges: list[dict[str, Any]]
    transition_counts: dict[str, int]
    iterations: int


class AffinityCandidateProvider(Protocol):
    """Produces bounded, non-factual bridge candidates for a retrieval run."""

    provider_id: str

    def neighbors(
        self,
        *,
        workspace_id: str,
        atom_version_ids: Sequence[str],
        limit: int,
        index_revision: str | None = None,
    ) -> list[dict[str, Any]]: ...


class ActivationEngine:
    """Pure localized activation with explicit family caps and replayability.

    ``P`` is constructed only from the provided query-local edges.  Each row
    is normalized after assigning bounded family mass, so high-degree nodes
    cannot gain more energy merely by accumulating links.  No method here
    persists generated answers or changes evidence-edge strength.
    """

    def __init__(self, weights: ActivationWeights | Mapping[str, Any] | None = None) -> None:
        self.weights = weights if isinstance(weights, ActivationWeights) else ActivationWeights.model_validate(weights or {})

    @staticmethod
    def _family_mass(weights: ActivationWeights, family: str) -> float:
        if family == "structural":
            return weights.structural
        if family == "trusted_evidence":
            return weights.trusted_evidence
        if family == "affinity":
            return weights.affinity
        if family == "behavioral":
            return weights.behavioral
        return 0.0

    def _transitions(self, edges: Sequence[ActivationEdge]) -> tuple[dict[str, list[tuple[str, float, ActivationEdge | None]]], dict[str, int]]:
        grouped: dict[str, dict[str, list[ActivationEdge]]] = defaultdict(lambda: defaultdict(list))
        for edge in edges:
            if (
                edge.family not in ACTIVATION_FAMILIES
                or not edge.source_id
                or not edge.target_id
                or edge.source_id == edge.target_id
                or edge.weight <= 0
            ):
                continue
            grouped[edge.source_id][edge.family].append(edge)

        transitions: dict[str, list[tuple[str, float, ActivationEdge | None]]] = {}
        counts: dict[str, int] = {family: 0 for family in ACTIVATION_FAMILIES}
        for source, by_family in grouped.items():
            row: list[tuple[str, float, ActivationEdge]] = []
            # Degree is capped across families.  Stable sort guarantees replay.
            remaining = self.weights.max_degree
            for family in sorted(by_family):
                mass = self._family_mass(self.weights, family)
                if mass <= 0 or remaining <= 0:
                    continue
                family_edges = sorted(
                    by_family[family],
                    key=lambda item: (-float(item.weight), item.target_id, item.edge_id or ""),
                )[:remaining]
                denominator = sum(max(0.0, float(item.weight)) for item in family_edges)
                if denominator <= 0:
                    continue
                for edge in family_edges:
                    probability = mass * max(0.0, float(edge.weight)) / denominator
                    row.append((edge.target_id, probability, edge))
                    counts[family] += 1
                remaining -= len(family_edges)
            # Preserve the policy's family caps.  Unused local family mass is
            # a self-retention transition, not an opportunity to inflate one
            # present family.  This keeps every row normalized and prevents
            # energy from disappearing merely because no affinity/behavioral
            # edge was selected for this query.
            total = sum(item[1] for item in row)
            if total > 1.0:
                row = [(target, probability / total, edge) for target, probability, edge in row]
            elif total < 1.0:
                row.append((source, 1.0 - total, None))
            transitions[source] = row
        return transitions, counts

    def activate(
        self,
        *,
        seed_scores: Mapping[str, float],
        edges: Sequence[ActivationEdge],
    ) -> ActivationResult:
        seeds = {str(node_id): max(0.0, float(score)) for node_id, score in seed_scores.items() if float(score) > 0}
        if not seeds:
            return ActivationResult({}, {}, [], {family: 0 for family in ACTIVATION_FAMILIES}, 0)
        total_seed = sum(seeds.values())
        base = {node_id: score / total_seed for node_id, score in seeds.items()}
        transitions, counts = self._transitions(edges)
        nodes = set(base) | set(transitions) | {target for row in transitions.values() for target, _, _ in row}
        current = {node_id: base.get(node_id, 0.0) for node_id in nodes}
        contributions: dict[str, dict[str, float]] = {
            node_id: {family: 0.0 for family in ACTIVATION_FAMILIES} for node_id in nodes
        }
        traversed: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        damping = self.weights.damping
        completed_iterations = 0
        for iteration in range(self.weights.iterations):
            following = {node_id: (1.0 - damping) * base.get(node_id, 0.0) for node_id in nodes}
            for source in sorted(nodes):
                value = current.get(source, 0.0)
                row = transitions.get(source, [])
                if not row:
                    following[source] += damping * value
                    continue
                for target, probability, edge in row:
                    flow = damping * value * probability
                    following[target] = following.get(target, 0.0) + flow
                    if edge is None:
                        # Synthetic row-normalization retention has no signal
                        # family, provenance, or graph-path diagnostic.
                        continue
                    contributions.setdefault(target, {family: 0.0 for family in ACTIVATION_FAMILIES})[edge.family] += flow
                    key = (source, target, edge.family, edge.edge_id or "")
                    entry = traversed.setdefault(
                        key,
                        {
                            "from_atom_version_id": source,
                            "to_atom_version_id": target,
                            "family": edge.family,
                            "edge_id": edge.edge_id,
                            "provenance": dict(edge.provenance),
                            "activation_mass": 0.0,
                        },
                    )
                    entry["activation_mass"] += flow
            completed_iterations = iteration + 1
            delta = sum(abs(following.get(node_id, 0.0) - current.get(node_id, 0.0)) for node_id in nodes)
            current = following
            if delta < 1e-8:
                break
        return ActivationResult(
            scores=current,
            contributions={
                node_id: {family: value for family, value in values.items() if value > 0}
                for node_id, values in contributions.items()
            },
            traversed_edges=sorted(
                traversed.values(),
                key=lambda item: (-float(item["activation_mass"]), str(item["edge_id"] or "")),
            )[:512],
            transition_counts=counts,
            iterations=completed_iterations,
        )

    def activate_two_pass(
        self,
        *,
        seed_scores: Mapping[str, float],
        edges: Sequence[Any],
        nodes: Sequence[str] | None = None,
        priors: PPRPriors | None = None,
    ) -> TwoPassPPRResult:
        """Perform Two-Pass Non-Negative Lateral Rectification PPR."""
        engine = TwoPassPPREngine(priors=priors or FROZEN_PPR_PRIORS)
        if nodes is None:
            node_set = set(seed_scores.keys())
            for e in edges:
                if isinstance(e, Edge):
                    node_set.add(e.src)
                    node_set.add(e.dst)
                elif isinstance(e, ActivationEdge):
                    node_set.add(e.source_id)
                    node_set.add(e.target_id)
                elif isinstance(e, dict):
                    if "src" in e:
                        node_set.add(str(e["src"]))
                    if "dst" in e:
                        node_set.add(str(e["dst"]))
                    if "source_id" in e:
                        node_set.add(str(e["source_id"]))
                    if "target_id" in e:
                        node_set.add(str(e["target_id"]))
                elif isinstance(e, (list, tuple)) and len(e) >= 2:
                    node_set.add(str(e[0]))
                    node_set.add(str(e[1]))
            nodes = sorted(n for n in node_set if n)
        return engine.run(nodes, seed_scores, edges)


# ==============================================================================
# Two-Pass Lateral Rectification PPR: Appendix A Rows 1 & 7
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


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    edge_type: str  # COMPILED_FROM, REFERENCES, SEE_ALSO, SUBSUMES, INSTANTIATES, MUTUALLY_EXCLUSIVE
    weight: float   # w >= 0 for excitatory, |w^-| in [0, 1] for MUTUALLY_EXCLUSIVE


@dataclass
class TwoPassPPRResult:
    excitatory_scores: dict[str, float]
    rectified_scores: dict[str, float]
    final_scores: dict[str, float]
    suppression_fallback_triggered: bool
    iterations: int
    step_count: int = 0
    elapsed_ms: float = 0.0


class TwoPassPPREngine:
    """Two-Pass Non-Negative Lateral Rectification Personalized PageRank Engine.

    Pass 1: Excitatory diffusion over non-negative edges E+ via power iteration
            (<= 20 iters, <= 2500 steps, non-negative W only, rho(P+)=1).
    Pass 2: Lateral inhibitory suppression:
            s_rect(v) = max(0, s+(v) - beta * max_{(u, v) in E^-} (|w^-_{uv}| * s+(u)))
            with beta = 1.0.
    Rectification Divide-by-Zero Guard:
            If ||s_rect||_1 <= 0 (all candidates inhibited), fall back to excitatory baseline s+.
    Renormalize:
            s_final = s_rect / ||s_rect||_1.
    """

    def __init__(self, priors: PPRPriors = FROZEN_PPR_PRIORS) -> None:
        self.priors = priors

    def run(
        self,
        nodes: Sequence[str],
        seed_scores: Mapping[str, float],
        edges: Sequence[Any],
    ) -> TwoPassPPRResult:
        start_time = time.perf_counter()
        if not nodes:
            return TwoPassPPRResult({}, {}, {}, False, 0, 0, 0.0)

        node_set = set(nodes)
        node_list = list(dict.fromkeys(nodes))

        # Parse and filter edges with degree capping
        raw_by_src: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(lambda: defaultdict(list))

        for edge in edges:
            try:
                if isinstance(edge, Edge):
                    src, dst, edge_type, weight = edge.src, edge.dst, edge.edge_type, float(edge.weight)
                elif isinstance(edge, ActivationEdge):
                    src, dst, edge_type, weight = edge.source_id, edge.target_id, edge.family, float(edge.weight)
                elif isinstance(edge, dict):
                    src = str(edge.get("src", edge.get("source_id", "")))
                    dst = str(edge.get("dst", edge.get("target_id", "")))
                    edge_type = str(edge.get("edge_type", edge.get("type", edge.get("family", "REFERENCES"))))
                    weight = float(edge.get("weight", 1.0))
                elif isinstance(edge, (list, tuple)) and len(edge) >= 4:
                    src, dst, edge_type, weight = str(edge[0]), str(edge[1]), str(edge[2]), float(edge[3])
                else:
                    continue
            except Exception:
                continue

            if math.isnan(weight) or math.isinf(weight):
                continue

            if not src or not dst or src == dst or src not in node_set or dst not in node_set:
                continue
            raw_by_src[src][edge_type].append((dst, weight))

        # Degree capping per node: 50 per type, 128 total across types
        e_plus: dict[str, list[tuple[str, float]]] = {n: [] for n in node_list}
        e_minus: dict[str, list[tuple[str, float]]] = {n: [] for n in node_list}

        for src in node_list:
            by_type = raw_by_src.get(src, {})
            capped_per_src: list[tuple[str, str, float]] = []
            for etype in sorted(by_type.keys()):
                sorted_type_edges = sorted(
                    by_type[etype],
                    key=lambda item: (-abs(item[1]), item[0]),
                )[:self.priors.degree_cap_per_type]
                for dst, w in sorted_type_edges:
                    capped_per_src.append((etype, dst, w))

            capped_per_src.sort(key=lambda item: (-abs(item[2]), item[0], item[1]))
            capped_per_src = capped_per_src[:self.priors.degree_cap_total]

            for etype, dst, w in capped_per_src:
                if etype == "MUTUALLY_EXCLUSIVE":
                    # E- edges store positive magnitude |w^-| in [0, 1]
                    e_minus[dst].append((src, abs(w)))
                else:
                    if w > 0:
                        e_plus[src].append((dst, float(w)))

        # Normalize seed distribution p0 (zero ghost activations for unseeded graph)
        positive_seeds: dict[str, float] = {}
        for n in node_list:
            val = float(seed_scores.get(n, 0.0))
            if math.isnan(val) or math.isinf(val) or val <= 0.0:
                positive_seeds[n] = 0.0
            else:
                positive_seeds[n] = val

        seed_sum = sum(positive_seeds.values())
        if seed_sum <= 1e-9:
            return TwoPassPPRResult(
                excitatory_scores={n: 0.0 for n in node_list},
                rectified_scores={n: 0.0 for n in node_list},
                final_scores={n: 0.0 for n in node_list},
                suppression_fallback_triggered=False,
                iterations=0,
                step_count=0,
                elapsed_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        p0 = {n: val / seed_sum for n, val in positive_seeds.items()}

        # Build stochastic transition matrix P+
        transition: dict[str, list[tuple[str, float]]] = {}
        for src in node_list:
            out_edges = e_plus.get(src, [])
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
        total_steps = 0

        for it in range(self.priors.max_iterations):
            completed_iterations = it + 1
            following = {n: (1.0 - alpha) * p0[n] for n in node_list}
            for src in node_list:
                val = current[src]
                row = transition.get(src, [])
                if not row:
                    # Dangling node redistribution
                    following[src] += alpha * val
                    total_steps += 1
                    continue
                for dst, prob in row:
                    following[dst] += alpha * val * prob
                    total_steps += 1
                    if total_steps >= self.priors.max_steps:
                        break
                if total_steps >= self.priors.max_steps:
                    break

            delta = sum(abs(following[n] - current[n]) for n in node_list)
            current = following
            if delta < 1e-7 or total_steps >= self.priors.max_steps:
                break

        # Guarantee valid probability simplex normalization on s+ even if budget interrupted
        norm_plus = sum(current.values())
        if norm_plus > 1e-9:
            s_plus = {n: v / norm_plus for n, v in current.items()}
        else:
            s_plus = current

        # Pass 2: Lateral Inhibitory Suppression
        # s_rect(v) = max(0, s+(v) - beta * max_{(u, v) in E^-} (|w^-_{uv}| * s+(u)))
        beta = self.priors.beta_lateral_inhibition
        s_rect: dict[str, float] = {}

        for v in node_list:
            inhibitors = e_minus.get(v, [])
            if not inhibitors:
                s_rect[v] = max(0.0, s_plus[v])
            else:
                max_inhibition = max(abs(w_neg) * s_plus[u] for u, w_neg in inhibitors)
                s_rect[v] = max(0.0, s_plus[v] - (beta * max_inhibition))

        # Appendix A Row-1 Guard: Divide-by-Zero Rectification Check
        # If all candidates inhibited (including subnormal/near-zero residuals <= 1e-9),
        # fall back to excitatory baseline s+.
        norm_1 = sum(s_rect.values())
        fallback_triggered = False

        if norm_1 <= 1e-9:
            fallback_triggered = True
            norm_excitatory = sum(s_plus.values())
            if norm_excitatory <= 1e-9:
                s_final = {n: 0.0 for n in node_list}
            else:
                s_final = {n: s_plus[n] / norm_excitatory for n in node_list}
        else:
            s_final = {n: s_rect[n] / norm_1 for n in node_list}

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return TwoPassPPRResult(
            excitatory_scores=s_plus,
            rectified_scores=s_rect,
            final_scores=s_final,
            suppression_fallback_triggered=fallback_triggered,
            iterations=completed_iterations,
            step_count=total_steps,
            elapsed_ms=elapsed_ms,
        )
