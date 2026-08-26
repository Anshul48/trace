"""Replaceable Cortex primitives.

This module deliberately has no database or model-provider dependency.  The
Spine owns facts and source anchors; these helpers only operate on bounded,
already-authorized projection rows supplied by a repository.
"""

from __future__ import annotations

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
