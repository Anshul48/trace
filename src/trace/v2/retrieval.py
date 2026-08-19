"""Bounded, evidence-first retrieval algorithms for Trace V2.

The module deliberately separates algorithm interfaces from persistence.  The
embedded service supplies deterministic local implementations, while a
deployment can inject BGE-M3, a cross-encoder, or a policy-approved cloud
navigator without changing evidence bundle semantics.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

from .models import ActivationWeights, DeepNavigationPlan, QueryRequest
from .model_gateway import ModelGatewayPolicy, ModelPolicy
from .store import ALLOWED_RELATIONS, STRUCTURAL_RELATIONS
from .cortex import ActivationEdge, ActivationEngine


_TOKEN = re.compile(r"[\w][\w'-]*", re.UNICODE)
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on",
    "or", "that", "the", "to", "with", "what", "which", "where", "when", "why", "how",
})


def tokens(text: str) -> list[str]:
    return [item for item in _TOKEN.findall(text.lower()) if item not in _STOPWORDS]


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("dense vectors have incompatible dimensions")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


class DenseEmbedder(Protocol):
    """Local embedding provider. Implementations must be deterministic per version."""

    provider_id: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class Reranker(Protocol):
    """Scores query/document pairs after hybrid candidate generation."""

    provider_id: str

    def score(self, query: str, documents: Sequence[str]) -> list[float]: ...


class DeepNavigator(Protocol):
    """Selects a bounded subset of hierarchy candidates for evidence expansion."""

    provider_id: str

    def select(
        self,
        *,
        query: str,
        candidates: Sequence[dict[str, Any]],
        max_nodes: int,
        token_budget: int,
    ) -> tuple[list[str], dict[str, Any]]: ...


class HashingDenseEmbedder:
    """Dependency-free local embedding fallback with stable feature hashing.

    It is intentionally called a hashing embedder rather than a semantic model
    in diagnostics.  Production configurations should set ``TRACE_DENSE_MODEL``
    to a local BGE-M3-compatible SentenceTransformer model.
    """

    provider_id = "hashing-dense-v1"

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            terms = tokens(text)
            # Bigrams provide a modest order signal without leaking corpus text
            # into an external service or requiring a model download.
            features = terms + [f"{left}\x1f{right}" for left, right in zip(terms, terms[1:])]
            for feature in features:
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(item * item for item in vector))
            vectors.append([item / norm for item in vector] if norm else vector)
        return vectors


class SentenceTransformerDenseEmbedder:
    """Lazy local SentenceTransformer/BGE adapter.

    The model is never downloaded or contacted until a deployment explicitly
    configures it.  ``local_files_only`` defaults to true for predictable,
    privacy-safe production startup.
    """

    def __init__(self, model_name: str, *, local_files_only: bool = True) -> None:
        self.model_name = model_name
        self.local_files_only = local_files_only
        self.provider_id = f"sentence-transformers:{model_name}"
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:  # pragma: no cover - optional deployment adapter
                raise RuntimeError("sentence-transformers is required for the configured dense model") from error
            self._model = SentenceTransformer(self.model_name, local_files_only=self.local_files_only)
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        encoded = self._load().encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        return [[float(item) for item in vector] for vector in encoded]


class DeterministicEvidenceReranker:
    """Transparent local reranker used until a cross-encoder is configured."""

    provider_id = "deterministic-evidence-reranker-v1"

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        query_terms = tokens(query)
        wanted = set(query_terms)
        scores: list[float] = []
        for document in documents:
            document_terms = tokens(document)
            available = set(document_terms)
            coverage = len(wanted & available) / max(1, len(wanted))
            phrase = 1.0 if query.lower() in document.lower() else 0.0
            proximity = 0.0
            positions = [index for index, term in enumerate(document_terms) if term in wanted]
            if len(positions) > 1:
                proximity = 1.0 / (1 + max(positions) - min(positions))
            # A deterministic, explainable score is a safe control path, not a
            # claim that this is a learned cross-encoder.
            scores.append((0.72 * coverage) + (0.20 * phrase) + (0.08 * proximity))
        return scores


class SentenceTransformerCrossEncoderReranker:
    """Lazy local cross-encoder adapter, e.g. BAAI/bge-reranker-v2-m3."""

    def __init__(self, model_name: str, *, local_files_only: bool = True) -> None:
        self.model_name = model_name
        self.local_files_only = local_files_only
        self.provider_id = f"cross-encoder:{model_name}"
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as error:  # pragma: no cover - optional deployment adapter
                raise RuntimeError("sentence-transformers is required for the configured reranker") from error
            self._model = CrossEncoder(self.model_name, local_files_only=self.local_files_only)
        return self._model

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        predicted = self._load().predict([(query, document) for document in documents], show_progress_bar=False)
        return [float(value) for value in predicted]


class HeuristicDeepNavigator:
    """Bounded local stand-in for LATTICE-style hierarchy traversal."""

    provider_id = "heuristic-hierarchy-navigator-v1"

    def select(
        self,
        *,
        query: str,
        candidates: Sequence[dict[str, Any]],
        max_nodes: int,
        token_budget: int,
    ) -> tuple[list[str], dict[str, Any]]:
        query_terms = set(tokens(query))
        scored: list[tuple[float, str, int]] = []
        consumed = 0
        for candidate in candidates:
            text = str(candidate.get("content", ""))
            token_count = len(tokens(text))
            overlap = len(query_terms & set(tokens(text))) / max(1, len(query_terms))
            anchor_count = len(candidate.get("source_atom_version_ids", []))
            scored.append((overlap + min(anchor_count, 8) * 0.01, candidate["atom_version_id"], token_count))
        selected: list[str] = []
        for _, node_id, token_count in sorted(scored, key=lambda item: (-item[0], item[1])):
            if len(selected) >= max_nodes or consumed + token_count > token_budget:
                continue
            selected.append(node_id)
            consumed += token_count
        return selected, {"provider": self.provider_id, "visited_nodes": len(selected), "estimated_tokens": consumed}


class CallableDeepNavigator:
    """Policy wrapper for a configured stronger local/cloud hierarchy selector.

    The callable receives summaries and anchor identifiers only. It never sees
    arbitrary attachments and must return selected hierarchy version IDs.
    """

    def __init__(self, provider_id: str, selector: Callable[..., Sequence[str]]) -> None:
        self.provider_id = provider_id
        self._selector = selector

    def select(
        self,
        *,
        query: str,
        candidates: Sequence[dict[str, Any]],
        max_nodes: int,
        token_budget: int,
    ) -> tuple[list[str], dict[str, Any]]:
        safe_candidates = [
            {
                "atom_version_id": candidate["atom_version_id"],
                "content": str(candidate.get("content", ""))[:4_000],
                "source_atom_version_ids": list(candidate.get("source_atom_version_ids", [])),
            }
            for candidate in candidates[:max_nodes * 4]
        ]
        selected = list(self._selector(query=query, candidates=safe_candidates, max_nodes=max_nodes, token_budget=token_budget))
        allowed = {candidate["atom_version_id"] for candidate in safe_candidates}
        selected = [item for item in selected if item in allowed][:max_nodes]
        return selected, {"provider": self.provider_id, "visited_nodes": len(selected), "estimated_tokens": sum(len(tokens(item["content"])) for item in safe_candidates if item["atom_version_id"] in selected)}


class LiteLLMDeepNavigator:
    """Explicitly configured cloud/local-model hierarchy selector.

    Only bounded derived summaries and opaque source-anchor IDs leave Trace.
    Raw attachments and unselected corpus text are never included in the
    prompt. Provider outages surface as errors rather than a hidden fallback.
    """

    def __init__(self, model: str, *, gateway_policy: ModelGatewayPolicy | None = None) -> None:
        self.model = model
        self.provider_id = f"litellm:{model}"
        self.gateway_policy = gateway_policy or ModelGatewayPolicy(
            ModelPolicy(
                allow_cloud=os.environ.get("TRACE_ALLOW_CLOUD_MODELS", "false").lower() == "true",
                token_budget=int(os.environ.get("TRACE_DEEP_TOKEN_BUDGET", "4000")),
            )
        )

    def select(
        self,
        *,
        query: str,
        candidates: Sequence[dict[str, Any]],
        max_nodes: int,
        token_budget: int,
    ) -> tuple[list[str], dict[str, Any]]:
        try:
            from litellm import completion
        except ImportError as error:  # pragma: no cover - optional deployment adapter
            raise RuntimeError("litellm is required for the configured deep navigator") from error
        safe_query, safe_candidates, audit = self.gateway_policy.prepare(
            provider=self.provider_id, purpose="deep_navigation", query=query,
            candidates=candidates[:max_nodes * 4], max_nodes=max_nodes * 4,
            token_budget=token_budget, cloud=True,
        )
        clipped = [
            {"id": candidate["atom_version_id"], "summary": candidate["content"], "anchors": candidate["source_atom_version_ids"]}
            for candidate in safe_candidates
        ]
        used = audit.estimated_tokens
        prompt = (
            "Select the smallest set of hierarchy summary IDs needed to retrieve evidence for the query. "
            "Do not answer the query. Return strict JSON: {\"selected_ids\":[...]}.\n"
            f"Query: {safe_query}\nCandidates: {json.dumps(clipped, ensure_ascii=False)}"
        )
        response = completion(model=self.model, messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=min(512, max(64, token_budget // 8)))
        content = response.choices[0].message.content or "{}"
        try:
            selected = json.loads(content).get("selected_ids", [])
        except json.JSONDecodeError as error:
            raise RuntimeError("deep navigator returned non-JSON output") from error
        allowed = {candidate["id"] for candidate in clipped}
        selected = [item for item in selected if isinstance(item, str) and item in allowed][:max_nodes]
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", used) or used)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        price_per_1k = float(os.environ.get("TRACE_DEEP_TOKEN_COST_PER_1K_USD", "0"))
        return selected, {
            "provider": self.provider_id,
            "visited_nodes": len(selected),
            "estimated_tokens": used,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cloud_token_cost_usd": (prompt_tokens + completion_tokens) * price_per_1k / 1_000,
            "cloud": True,
            "policy_audit": {
                **audit.as_dict(),
                "cloud_tokens": prompt_tokens + completion_tokens,
                "cost_usd": (prompt_tokens + completion_tokens) * price_per_1k / 1_000,
            },
        }


class ColBERTQualityTier(Protocol):
    """Optional separately indexed late-interaction quality tier.

    The first release keeps this disabled by default and never constructs a
    multi-vector index. A deployment may inject an already-built index behind
    an explicit feature flag later.
    """

    provider_id: str

    def search(self, *, workspace_id: str, query: str, limit: int, atom_ids: Sequence[str]) -> dict[str, float]: ...


@dataclass
class Candidate:
    atom: dict[str, Any]
    lexical: float = 0.0
    dense: float = 0.0
    rrf: float = 0.0
    rerank: float = 0.0
    graph: float = 0.0
    feedback: float = 0.0
    hierarchy: float = 0.0
    affinity: float = 0.0
    activation: float = 0.0
    deep: float = 0.0
    score: float = 0.0
    paths: list[dict[str, Any]] = field(default_factory=list)
    activation_contributions: dict[str, float] = field(default_factory=dict)


@dataclass
class RetrievalOutcome:
    candidates: list[Candidate]
    sufficiency_state: str
    diagnostics: dict[str, Any]


class HybridRetrievalEngine:
    """Hybrid retrieval with explicit, bounded stage transitions."""

    def __init__(
        self,
        *,
        dense_embedder: DenseEmbedder | None = None,
        reranker: Reranker | None = None,
        deep_navigator: DeepNavigator | None = None,
        lexical_index: Any | None = None,
        dense_index: Any | None = None,
        colbert_tier: ColBERTQualityTier | None = None,
    ) -> None:
        model_name = os.environ.get("TRACE_DENSE_MODEL")
        reranker_name = os.environ.get("TRACE_RERANK_MODEL")
        local_files_only = os.environ.get("TRACE_MODEL_LOCAL_FILES_ONLY", "true").lower() != "false"
        self.dense_embedder = dense_embedder or (
            SentenceTransformerDenseEmbedder(model_name, local_files_only=local_files_only) if model_name else HashingDenseEmbedder()
        )
        self.reranker = reranker or (
            SentenceTransformerCrossEncoderReranker(reranker_name, local_files_only=local_files_only) if reranker_name else DeterministicEvidenceReranker()
        )
        # A cloud navigator may only be constructed by ``TraceService`` from
        # the registered model gateway and a request authorization context.
        # Never let an environment model name turn a retrieval engine into an
        # unregistered direct LiteLLM client.
        self.deep_navigator = deep_navigator or HeuristicDeepNavigator()
        self.lexical_index = lexical_index
        self.dense_index = dense_index
        self.colbert_tier = colbert_tier
        self.colbert_enabled = bool(colbert_tier and os.environ.get("TRACE_COLBERT_ENABLED", "false").lower() == "true")

    @staticmethod
    def _bm25(query_terms: list[str], documents: Sequence[dict[str, Any]]) -> dict[str, float]:
        """Okapi BM25 over source atoms, with no query-time corpus mutation."""

        frequencies = {item["atom_version_id"]: Counter(tokens(item["content"])) for item in documents}
        document_frequency: Counter[str] = Counter()
        lengths: dict[str, int] = {}
        for atom_id, frequency in frequencies.items():
            document_frequency.update(frequency.keys())
            lengths[atom_id] = sum(frequency.values())
        average_length = sum(lengths.values()) / max(1, len(lengths))
        k1, b = 1.2, 0.75
        scores: dict[str, float] = {}
        for atom in documents:
            atom_id = atom["atom_version_id"]
            score = 0.0
            for term in query_terms:
                frequency = frequencies[atom_id][term]
                if not frequency:
                    continue
                inverse_frequency = math.log(1 + ((len(documents) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5)))
                denominator = frequency + k1 * (1 - b + b * lengths[atom_id] / max(1.0, average_length))
                score += inverse_frequency * ((frequency * (k1 + 1)) / denominator)
            if score > 0:
                scores[atom_id] = score
        return scores

    @staticmethod
    def _rank(scores: dict[str, float], limit: int) -> dict[str, int]:
        return {item: rank for rank, item in enumerate(sorted(scores, key=lambda key: (-scores[key], key))[:limit], start=1)}

    @staticmethod
    def _normalize(scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        high, low = max(scores.values()), min(scores.values())
        if high == low:
            return {key: 1.0 for key in scores}
        return {key: (value - low) / (high - low) for key, value in scores.items()}

    def _lexical_scores(
        self,
        *,
        request: QueryRequest,
        atoms: Sequence[dict[str, Any]],
        hits: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, float]:
        if self.lexical_index is None:
            return self._bm25(tokens(request.query), atoms)
        visibility = request.privacy_context.get("allowed_visibility")
        if hits is None:
            try:
                hits = self.lexical_index.search(
                    workspace_id=request.workspace_id or "",
                    query=request.query,
                    limit=request.retrieval_budget.lexical_limit,
                    visibility=visibility,
                    facets=request.facets,
                    as_of_event=request.as_of_event,
                    index_revision=os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
                )
            except TypeError:
                hits = self.lexical_index.search(
                    workspace_id=request.workspace_id or "",
                    query=request.query,
                    limit=request.retrieval_budget.lexical_limit,
                    visibility=visibility,
                    facets=request.facets,
                    as_of_event=request.as_of_event,
                )
        allowed = {atom["atom_version_id"] for atom in atoms}
        return {
            str(hit.get("atom_version_id")): float(hit.get("lexical_score", hit.get("score", 0.0)) or 0.0)
            for hit in hits
            if hit.get("atom_version_id") in allowed and float(hit.get("lexical_score", hit.get("score", 0.0)) or 0.0) > 0
        }

    def _dense_scores(
        self,
        *,
        store: Any,
        workspace_id: str,
        query: str,
        atoms: Sequence[dict[str, Any]],
        limit: int = 100,
        visibility: Sequence[str] | None = None,
        facets: Sequence[str] | None = None,
        as_of_event: int | None = None,
        hits: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, float]:
        if self.dense_index is not None:
            if hits is None:
                query_vector = self.dense_embedder.embed([query])[0]
                try:
                    hits = self.dense_index.search(
                        workspace_id=workspace_id, vector=query_vector,
                        limit=limit,
                        visibility=visibility,
                        facets=facets,
                        as_of_event=as_of_event,
                        index_revision=os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
                    )
                except TypeError:
                    # Keep compatibility with early injected index implementations
                    # while production adapters use the revision-aware contract.
                    hits = self.dense_index.search(
                        workspace_id=workspace_id, vector=query_vector,
                        limit=limit,
                        visibility=visibility,
                        facets=facets,
                        as_of_event=as_of_event,
                    )
            allowed = {atom["atom_version_id"] for atom in atoms}
            return {
                str(hit.get("atom_version_id")): float(hit.get("dense_score", hit.get("score", 0.0)) or 0.0)
                for hit in hits
                if hit.get("atom_version_id") in allowed
            }
        atom_ids = [atom["atom_version_id"] for atom in atoms]
        index_revision = os.environ.get("TRACE_INDEX_REVISION", "embedded-current")
        try:
            vectors = store.dense_vectors(self.dense_embedder.provider_id, atom_ids, index_revision=index_revision)
        except TypeError:
            vectors = store.dense_vectors(self.dense_embedder.provider_id, atom_ids)
        missing = [atom for atom in atoms if atom["atom_version_id"] not in vectors]
        if missing:
            # Retrieval must not turn a cache miss into a projection write.
            # Index workers own persistent vectors; a bounded embedded query
            # may compute ephemeral vectors solely for its current candidates.
            missing = missing[:max(1, min(int(limit), 1_000))]
            embedded = self.dense_embedder.embed([atom["content"] for atom in missing])
            fresh = {atom["atom_version_id"]: vector for atom, vector in zip(missing, embedded, strict=True)}
            vectors.update(fresh)
        query_vector = self.dense_embedder.embed([query])[0]
        return {atom_id: cosine(query_vector, vector) for atom_id, vector in vectors.items() if vector}

    def _graph_scores(
        self,
        *,
        store: Any,
        workspace_id: str,
        as_of_event: int | None,
        direct: dict[str, Candidate],
        atom_by_node: dict[str, dict[str, Any]],
        seed_limit: int,
        iterations: int,
    ) -> tuple[dict[str, float], dict[str, list[dict[str, Any]]]]:
        """Personalized PageRank over typed/structural evidence edges only."""

        ranked = [
            item for item in sorted(direct.values(), key=lambda item: (-item.score, item.atom["atom_version_id"]))
            if item.lexical > 0 or item.dense >= 0.20
        ][:seed_limit]
        if not ranked:
            return {}, {}
        max_score = max(item.score for item in ranked) or 1.0
        seeds = {item.atom["node_id"]: item.score / max_score for item in ranked if item.score / max_score >= 0.15}
        if not seeds:
            return {}, {}
        adjacency: dict[str, list[tuple[str, float, dict[str, Any]]]] = defaultdict(list)
        candidate_nodes = list(atom_by_node)[:500]
        edge_source = getattr(store, "neighbor_edges", None)
        if callable(edge_source):
            edges: list[dict[str, Any]] = []
            seen_edges: set[str] = set()
            # Candidate generation is already capped by the request budget.
            # Fetching only their neighbourhood avoids a graph-wide edge scan.
            for start in range(0, len(candidate_nodes), 128):
                remaining = max(0, 2_000 - len(edges))
                if not remaining:
                    break
                try:
                    batch = edge_source(
                        workspace_id, candidate_nodes[start:start + 128],
                        as_of_event=as_of_event, limit=remaining,
                    )
                except TypeError:
                    batch = edge_source(workspace_id, candidate_nodes[start:start + 128])
                for edge in batch:
                    edge_id = str(edge.get("edge_version_id", ""))
                    if edge_id and edge_id not in seen_edges:
                        edges.append(edge)
                        seen_edges.add(edge_id)
        elif os.environ.get("TRACE_PRODUCTION_MODE", "false").lower() != "true":
            edges = store.current_edges(workspace_id, as_of_event)
        else:
            edges = []
        for edge in edges:
            if edge["relation_type"] not in ALLOWED_RELATIONS or edge["confidence"] < 0.55:
                continue
            source, target = edge["source_node_id"], edge["target_node_id"]
            if source not in atom_by_node or target not in atom_by_node:
                continue
            relation_factor = 1.0 if edge["relation_type"] in STRUCTURAL_RELATIONS else 0.85
            weight = max(0.001, float(edge["weight"]) * float(edge["confidence"]) * relation_factor)
            adjacency[source].append((target, weight, edge))
            adjacency[target].append((source, weight, edge))
        nodes = set(atom_by_node)
        if not adjacency:
            return {}, {}
        total_seed = sum(seeds.values()) or 1.0
        personalization = {node: seeds.get(node, 0.0) / total_seed for node in nodes}
        current = dict(personalization)
        damping = 0.85
        for _ in range(iterations):
            following = {node: (1.0 - damping) * personalization[node] for node in nodes}
            for source, value in current.items():
                links = adjacency.get(source, [])
                if not links:
                    following[source] += damping * value
                    continue
                normalizer = sum(weight for _, weight, _ in links)
                for target, weight, _ in links:
                    following[target] += damping * value * weight / normalizer
            if sum(abs(following[node] - current.get(node, 0.0)) for node in nodes) < 1e-8:
                current = following
                break
            current = following
        version_scores = {atom_by_node[node]["atom_version_id"]: value for node, value in current.items() if node in atom_by_node}
        paths: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for seed in seeds:
            for target, _, edge in adjacency.get(seed, []):
                target_version = atom_by_node[target]["atom_version_id"]
                paths[target_version].append({
                    "edge_version_id": edge["edge_version_id"],
                    "relation_type": edge["relation_type"],
                    "from_node_id": seed,
                    "to_node_id": target,
                    "evidence_atom_version_ids": [anchor["source_atom_version_id"] for anchor in edge["evidence_anchors"]],
                })
        return version_scores, paths

    def _activation_scores(
        self,
        *,
        store: Any,
        workspace_id: str,
        as_of_event: int | None,
        direct: dict[str, Candidate],
        atoms: Sequence[dict[str, Any]],
        seed_limit: int,
        release_id: str | None = None,
    ) -> tuple[dict[str, float], dict[str, list[dict[str, Any]]], dict[str, dict[str, float]], dict[str, Any], dict[str, dict[str, Any]]]:
        """Run bounded activation and load selected endpoints outside seeds.

        Old PPR only retained nodes that happened to be in the first hybrid
        candidate set. This implementation deliberately reloads authorized
        one-hop structural/evidence and affinity endpoints before constructing
        the local transition matrix.
        """

        ranked = [
            item for item in sorted(direct.values(), key=lambda item: (-item.score, item.atom["atom_version_id"]))
            if item.lexical > 0 or item.dense >= 0.20 or item.rerank > 0
        ][:seed_limit]
        if not ranked:
            return {}, {}, {}, {"applied": False, "reason": "no_hybrid_seeds"}, {}
        policy_getter = getattr(store, "get_cognitive_policy", None)
        policy = policy_getter(workspace_id) if callable(policy_getter) else {}
        policy_data = policy.get("policy", {}) if isinstance(policy, dict) else {}
        try:
            weights = ActivationWeights.model_validate(policy_data.get("activation", {}))
        except Exception:
            weights = ActivationWeights()
        atom_by_node = {atom["node_id"]: atom for atom in atoms}
        atom_by_id = {atom["atom_version_id"]: atom for atom in atoms}
        seed_nodes = [item.atom["node_id"] for item in ranked]
        edge_source = getattr(store, "neighbor_edges", None)
        edge_rows: list[dict[str, Any]] = []
        if callable(edge_source):
            try:
                edge_rows = edge_source(workspace_id, seed_nodes, as_of_event=as_of_event, limit=seed_limit * 32)
            except TypeError:
                edge_rows = edge_source(workspace_id, seed_nodes)
        elif os.environ.get("TRACE_PRODUCTION_MODE", "false").lower() != "true":
            edge_rows = store.current_edges(workspace_id, as_of_event)
        endpoint_nodes = list(dict.fromkeys(
            node_id
            for edge in edge_rows
            if edge.get("relation_type") in ALLOWED_RELATIONS and float(edge.get("confidence", 0)) >= 0.55
            for node_id in (str(edge.get("source_node_id")), str(edge.get("target_node_id")))
            if node_id and node_id not in atom_by_node
        ))[:seed_limit * 16]
        endpoint_loader = getattr(store, "current_atom_versions_for_nodes", None)
        if endpoint_nodes and callable(endpoint_loader):
            try:
                loaded = endpoint_loader(workspace_id, endpoint_nodes, as_of_event=as_of_event)
            except TypeError:
                loaded = endpoint_loader(workspace_id, endpoint_nodes)
            for atom in loaded:
                atom_by_node[atom["node_id"]] = atom
                atom_by_id[atom["atom_version_id"]] = atom

        activation_edges: list[ActivationEdge] = []
        path_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edge_rows:
            relation = str(edge.get("relation_type", ""))
            source_node = str(edge.get("source_node_id", ""))
            target_node = str(edge.get("target_node_id", ""))
            if (
                relation not in ALLOWED_RELATIONS
                or float(edge.get("confidence", 0)) < 0.55
                or source_node not in atom_by_node
                or target_node not in atom_by_node
            ):
                continue
            family = "structural" if relation in STRUCTURAL_RELATIONS else "trusted_evidence"
            factor = 1.0 if family == "structural" else 0.85
            weight = max(0.001, float(edge.get("weight", 0)) * float(edge.get("confidence", 0)) * factor)
            edge_id = str(edge.get("edge_version_id") or "") or None
            provenance = {
                "relation_type": relation,
                "evidence_atom_version_ids": [anchor.get("source_atom_version_id") for anchor in edge.get("evidence_anchors", [])],
            }
            source_id = atom_by_node[source_node]["atom_version_id"]
            target_id = atom_by_node[target_node]["atom_version_id"]
            activation_edges.extend((
                ActivationEdge(source_id, target_id, family, weight, edge_id, provenance),
                ActivationEdge(target_id, source_id, family, weight, edge_id, provenance),
            ))
            path_rows[target_id].append({
                "edge_version_id": edge_id,
                "relation_type": relation,
                "from_node_id": source_node,
                "to_node_id": target_node,
                "evidence_atom_version_ids": provenance["evidence_atom_version_ids"],
            })

        affinity_source = getattr(store, "affinity_neighbors", None)
        affinity_rows: list[dict[str, Any]] = []
        if callable(affinity_source):
            try:
                affinity_rows = affinity_source(
                    workspace_id, [item.atom["atom_version_id"] for item in ranked],
                    release_id=release_id,
                    limit=max(0, min(128, seed_limit * 8)), index_revision=os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
                )
            except TypeError:
                try:
                    affinity_rows = affinity_source(workspace_id, [item.atom["atom_version_id"] for item in ranked], release_id=release_id, limit=seed_limit * 8)
                except TypeError:
                    affinity_rows = affinity_source(workspace_id, [item.atom["atom_version_id"] for item in ranked], limit=seed_limit * 8)
        affinity_ids = list(dict.fromkeys(
            endpoint
            for edge in affinity_rows
            for endpoint in (str(edge.get("left_atom_version_id", "")), str(edge.get("right_atom_version_id", "")))
            if endpoint and endpoint not in atom_by_id
        ))[:seed_limit * 16]
        if affinity_ids:
            for atom in store.atom_versions(affinity_ids):
                if atom.get("workspace_id") == workspace_id:
                    atom_by_id[atom["atom_version_id"]] = atom
                    atom_by_node[atom["node_id"]] = atom
        for edge in affinity_rows:
            left = str(edge.get("left_atom_version_id", ""))
            right = str(edge.get("right_atom_version_id", ""))
            if left not in atom_by_id or right not in atom_by_id:
                continue
            edge_id = str(edge.get("affinity_edge_id") or "") or None
            provenance = {"signal": edge.get("signal", {}), "expires_at": edge.get("expires_at")}
            activation_edges.extend((
                ActivationEdge(left, right, "affinity", max(0.001, float(edge.get("score", 0))), edge_id, provenance),
                ActivationEdge(right, left, "affinity", max(0.001, float(edge.get("score", 0))), edge_id, provenance),
            ))
            path_rows[right].append({"affinity_edge_id": edge_id, "relation_type": "affinity", "from_atom_version_id": left, "to_atom_version_id": right})
            path_rows[left].append({"affinity_edge_id": edge_id, "relation_type": "affinity", "from_atom_version_id": right, "to_atom_version_id": left})

        seed_scores = {item.atom["atom_version_id"]: max(item.score, 0.001) for item in ranked}
        prior_source = getattr(store, "activation_priors", None)
        priors: dict[str, list[dict[str, Any]]] = {}
        if callable(prior_source):
            try:
                priors = prior_source(workspace_id, list(atom_by_id), release_id=release_id)
            except TypeError:
                priors = prior_source(workspace_id, list(atom_by_id))
        for atom_id, values in priors.items():
            # Priors may add a small local baseline, but suppression can only
            # reduce it to zero. They do not mutate factual edge weights.
            effect = sum(float(value.get("score", 0.0)) for value in values)
            if effect > 0:
                seed_scores[atom_id] = seed_scores.get(atom_id, 0.0) + min(0.15, effect * 0.05)
            elif effect < 0 and atom_id in seed_scores:
                seed_scores[atom_id] *= max(0.0, 1.0 + max(-0.75, effect))
        result = ActivationEngine(weights).activate(seed_scores=seed_scores, edges=activation_edges)
        maximum = max(result.scores.values(), default=0.0)
        normalized = {atom_id: score / maximum for atom_id, score in result.scores.items() if maximum > 0}
        diagnostics = {
            "applied": bool(activation_edges),
            "policy_revision": policy.get("policy_revision") if isinstance(policy, dict) else None,
            "transition_counts": result.transition_counts,
            "iterations": result.iterations,
            "traversed_edges": result.traversed_edges,
            "affinity_bridge_ids": [edge.get("affinity_edge_id") for edge in affinity_rows if edge.get("affinity_edge_id")],
        }
        return normalized, path_rows, result.contributions, diagnostics, atom_by_id

    def _hierarchy_candidates(self, *, store: Any, request: QueryRequest) -> list[Candidate]:
        if not request.workspace_id:
            return []
        wanted = set(tokens(request.query))
        candidates: list[Candidate] = []
        # Prefer the active replaceable Cortex revision. Legacy derived nodes
        # remain a read-only rollback path while existing deployments backfill.
        frontier_source = getattr(store, "hierarchy_frontier", None)
        source_expander = getattr(store, "hierarchy_source_atom_ids", None)
        if callable(frontier_source) and callable(source_expander):
            try:
                frontier = frontier_source(
                    request.workspace_id, request.query,
                    limit=max(8, min(200, request.retrieval_budget.hierarchy_limit * 2)),
                    as_of_event=request.as_of_event,
                )
            except TypeError:
                frontier = frontier_source(request.workspace_id, request.query, limit=request.retrieval_budget.hierarchy_limit)
            for item in frontier:
                source_ids = source_expander(
                    request.workspace_id, [item["projection_object_id"]],
                    limit=min(512, request.retrieval_budget.hierarchy_limit * 16),
                )
                if not source_ids:
                    continue
                raw_sources = store.atom_versions(source_ids)
                if {str(source.get("atom_version_id")) for source in raw_sources} != set(source_ids):
                    # RLS or a stale projection withheld at least one source.
                    # A summary is navigational only and cannot bridge that
                    # authorization gap.
                    continue
                allowed_visibility = request.privacy_context.get("allowed_visibility")
                if allowed_visibility is None and "visibility" in request.privacy_context:
                    allowed_visibility = [request.privacy_context["visibility"]]
                if allowed_visibility is not None and any(
                    source.get("security", {}).get("visibility") not in set(allowed_visibility)
                    for source in raw_sources
                ):
                    # A navigation summary cannot reveal a source set that the
                    # caller could not expand to. It is not a factual shortcut.
                    continue
                overlap = len(wanted & set(tokens(item["content"]))) / max(1, len(wanted))
                if not overlap:
                    continue
                candidates.append(Candidate(
                    atom={
                        "node_id": item["projection_object_id"],
                        "atom_version_id": item["projection_object_id"],
                        "workspace_id": request.workspace_id,
                        "facets": ["summary", item.get("object_kind", "hierarchy")],
                        "security": raw_sources[0].get("security", {}) if raw_sources else {},
                        "content": item["content"],
                        "content_hash": item["content_hash"],
                        "properties": {
                            **item.get("properties", {}),
                            "projection_run_id": item.get("projection_run_id"),
                            "projection_revision": item.get("projection_revision"),
                        },
                        "source_atom_version_ids": source_ids,
                        "evidence_anchor_ids": [],
                        "projection_object_id": item["projection_object_id"],
                    },
                    hierarchy=overlap,
                    score=0.015 + 0.05 * overlap,
                ))
            if candidates:
                return sorted(candidates, key=lambda item: (-item.score, item.atom["atom_version_id"]))[:request.retrieval_budget.hierarchy_limit]
        latest_by_logical_key: dict[str, dict[str, Any]] = {}
        unkeyed: list[dict[str, Any]] = []
        node_source = getattr(store, "current_nodes_by_facet", None)
        if callable(node_source):
            nodes: list[dict[str, Any]] = []
            seen: set[str] = set()
            per_facet = max(8, min(256, request.retrieval_budget.hierarchy_limit * 4))
            for facet in ("section_summary", "topic_holon", "workspace_holon", "summary", "holon"):
                try:
                    batch = node_source(
                        request.workspace_id, facet, as_of_event=request.as_of_event, limit=per_facet
                    )
                except TypeError:
                    batch = node_source(request.workspace_id, facet)
                for node in batch:
                    identifier = str(node.get("atom_version_id", ""))
                    if identifier and identifier not in seen:
                        nodes.append(node)
                        seen.add(identifier)
        elif os.environ.get("TRACE_PRODUCTION_MODE", "false").lower() != "true":
            nodes = store.current_nodes(request.workspace_id, request.as_of_event)
        else:
            nodes = []
        for node in nodes:
            logical_key = node.get("properties", {}).get("hierarchy_logical_key")
            if not logical_key:
                unkeyed.append(node)
            elif logical_key not in latest_by_logical_key or node["created_event_offset"] > latest_by_logical_key[logical_key]["created_event_offset"]:
                latest_by_logical_key[logical_key] = node
        for node in [*latest_by_logical_key.values(), *unkeyed]:
            allowed = request.privacy_context.get("allowed_visibility")
            if allowed is None and "visibility" in request.privacy_context:
                allowed = [request.privacy_context["visibility"]]
            if allowed is not None and node.get("security", {}).get("visibility") not in set(allowed):
                continue
            facets = set(node.get("facets", []))
            if not ({"section_summary", "topic_holon", "workspace_holon", "summary", "holon"} & facets):
                continue
            anchors = node.get("evidence_anchors", [])
            if not anchors:
                continue
            overlap = len(wanted & set(tokens(node["content"]))) / max(1, len(wanted))
            if not overlap:
                continue
            candidate = Candidate(atom=node, hierarchy=overlap, score=0.015 + 0.05 * overlap)
            candidate.atom = {
                **node,
                "source_atom_version_ids": [anchor["source_atom_version_id"] for anchor in anchors],
                "evidence_anchor_ids": [anchor["anchor_id"] for anchor in anchors],
            }
            candidates.append(candidate)
        return sorted(candidates, key=lambda item: (-item.score, item.atom["atom_version_id"]))[:request.retrieval_budget.hierarchy_limit]

    def retrieve(
        self,
        *,
        store: Any,
        request: QueryRequest,
        atoms: list[dict[str, Any]],
        index_hits: dict[str, Sequence[dict[str, Any]]] | None = None,
        deep_navigator: DeepNavigator | None = None,
        release_id: str | None = None,
    ) -> RetrievalOutcome:
        if not request.workspace_id or not atoms:
            return RetrievalOutcome([], "insufficient_evidence", {"reason": "no_visible_atoms"})
        query_terms = tokens(request.query)
        if not query_terms:
            return RetrievalOutcome([], "insufficient_evidence", {"reason": "no_query_terms"})

        active_rel_getter = getattr(store, "get_active_cortex_release", None)
        active_rel = active_rel_getter(request.workspace_id) if callable(active_rel_getter) else None
        eff_release_id = release_id or (active_rel["release_id"] if active_rel else None)

        budget = request.retrieval_budget
        profile = request.retrieval_profile
        lexical = self._lexical_scores(request=request, atoms=atoms, hits=(index_hits or {}).get("lexical"))
        dense = {} if profile == "lexical" else self._dense_scores(
            store=store, workspace_id=request.workspace_id, query=request.query, atoms=atoms,
            limit=budget.dense_limit,
            visibility=request.privacy_context.get("allowed_visibility"), facets=request.facets,
            as_of_event=request.as_of_event,
            hits=(index_hits or {}).get("dense"),
        )
        # Feature hashing is a deterministic local control path, not a semantic
        # model.  It may collide on unrelated words, so it only augments sparse
        # evidence. A configured BGE/SentenceTransformer provider can surface
        # dense-only candidates normally.
        if isinstance(self.dense_embedder, HashingDenseEmbedder) and self.dense_index is None:
            dense = {atom_id: score for atom_id, score in dense.items() if atom_id in lexical}
        lexical_rank = self._rank(lexical, budget.lexical_limit)
        dense_rank = self._rank(dense, budget.dense_limit)
        fused_ids = set(lexical_rank) | set(dense_rank)
        atom_by_id = {atom["atom_version_id"]: atom for atom in atoms}
        candidates: dict[str, Candidate] = {}
        for atom_id in fused_ids:
            rrf = 0.0
            if atom_id in lexical_rank:
                rrf += 1.0 / (60 + lexical_rank[atom_id])
            if atom_id in dense_rank:
                rrf += 1.0 / (60 + dense_rank[atom_id])
            candidates[atom_id] = Candidate(atom=atom_by_id[atom_id], lexical=lexical.get(atom_id, 0.0), dense=dense.get(atom_id, 0.0), rrf=rrf, score=rrf)
        ordered = sorted(candidates.values(), key=lambda item: (-item.score, item.atom["atom_version_id"]))
        rerank_applied = profile in {"rerank", "hierarchy", "graph", "deep"} or (profile == "auto" and budget.mode != "fast")
        if rerank_applied:
            rerank_set = ordered[:budget.rerank_limit]
            model_scores = self.reranker.score(request.query, [item.atom["content"] for item in rerank_set])
            normalized = self._normalize({item.atom["atom_version_id"]: score for item, score in zip(rerank_set, model_scores, strict=True)})
            rrf_norm = self._normalize({item.atom["atom_version_id"]: item.rrf for item in rerank_set})
            for item in rerank_set:
                atom_id = item.atom["atom_version_id"]
                item.rerank = normalized[atom_id]
                item.score = (0.45 * rrf_norm[atom_id]) + (0.55 * item.rerank)
        colbert_scores: dict[str, float] = {}
        if self.colbert_enabled and self.colbert_tier is not None:
            colbert_scores = self.colbert_tier.search(
                workspace_id=request.workspace_id, query=request.query,
                limit=budget.rerank_limit, atom_ids=[item.atom["atom_version_id"] for item in ordered[:budget.rerank_limit]],
            )
            normalized_colbert = self._normalize(colbert_scores)
            for atom_id, score in normalized_colbert.items():
                if atom_id in candidates:
                    candidates[atom_id].score += 0.15 * score
        feedback = store.feedback_scores(request.workspace_id, list(candidates))
        if feedback:
            for atom_id, item in candidates.items():
                item.feedback = feedback.get(atom_id, 0.0)
                item.score += budget.feedback_weight * item.feedback
        graph_applied = profile in {"graph", "deep"} or (profile == "auto" and budget.mode in {"graph", "deep"})
        activation_diagnostics: dict[str, Any] = {"applied": False, "reason": "profile_disabled"}
        if graph_applied:
            graph, paths, contributions, activation_diagnostics, activation_atoms = self._activation_scores(
                store=store, workspace_id=request.workspace_id, as_of_event=request.as_of_event,
                direct=candidates, atoms=atoms, seed_limit=budget.graph_seed_limit,
                release_id=eff_release_id,
            )
            # Request budgets can reduce graph influence, never raise it past
            # the policy-safe ceiling. Family transition mass is exclusively
            # resolved from the persisted CognitivePolicy above.
            activation_mix = min(0.25, max(0.0, float(budget.graph_weight)))
            for atom_id, value in graph.items():
                atom = activation_atoms.get(atom_id)
                if atom is None:
                    continue
                if atom_id not in candidates:
                    candidates[atom_id] = Candidate(atom=atom)
                candidates[atom_id].graph = value
                candidates[atom_id].activation = value
                candidates[atom_id].affinity = float(contributions.get(atom_id, {}).get("affinity", 0.0))
                candidates[atom_id].activation_contributions = contributions.get(atom_id, {})
                candidates[atom_id].paths = paths.get(atom_id, [])
                candidates[atom_id].score += activation_mix * value
        ordered = sorted(candidates.values(), key=lambda item: (-item.score, item.atom["atom_version_id"]))
        top_raw = ordered[:budget.candidate_limit]
        hierarchy_applied = profile in {"hierarchy", "deep"} or (profile == "auto" and budget.mode in {"hierarchy", "deep"})
        hierarchy = self._hierarchy_candidates(store=store, request=request) if hierarchy_applied else []
        # Hierarchy summaries are navigation compression only. Every selected
        # holon is expanded back to raw atom versions before sufficiency or
        # synthesis can see it; summary text never becomes proof.
        if hierarchy:
            hierarchy_sources = list(dict.fromkeys(
                source_id
                for item in hierarchy[:budget.hierarchy_limit]
                for source_id in item.atom.get("source_atom_version_ids", [])
            ))[:max(budget.candidate_limit * 8, budget.hierarchy_limit)]
            for atom in store.atom_versions(hierarchy_sources):
                atom_id = atom["atom_version_id"]
                parent_score = max(
                    (item.hierarchy for item in hierarchy if atom_id in item.atom.get("source_atom_version_ids", [])),
                    default=0.0,
                )
                if atom_id not in candidates:
                    candidates[atom_id] = Candidate(atom=atom, hierarchy=parent_score, score=0.02 + 0.04 * parent_score)
                else:
                    candidates[atom_id].hierarchy = max(candidates[atom_id].hierarchy, parent_score)
                    candidates[atom_id].score += 0.04 * parent_score
            ordered = sorted(candidates.values(), key=lambda item: (-item.score, item.atom["atom_version_id"]))
            top_raw = ordered[:budget.candidate_limit]
        preliminary = sorted([*top_raw, *hierarchy], key=lambda item: (-item.score, item.atom["atom_version_id"]))
        raw_gap = abs(top_raw[0].score - top_raw[1].score) if len(top_raw) > 1 else 1.0
        preliminary_state = "answerable" if top_raw else "insufficient_evidence"
        if len(query_terms) > 1 and len(top_raw) > 1 and raw_gap < 0.015:
            preliminary_state = "ambiguous"
        deep_applied = profile == "deep" or (profile == "auto" and budget.mode == "deep") or (
            profile == "auto" and budget.allow_deep_escalation and preliminary_state in {"ambiguous", "insufficient_evidence"} and bool(hierarchy)
        )
        deep_trace: dict[str, Any] | None = None
        navigator = deep_navigator or self.deep_navigator
        if deep_applied and hierarchy:
            plans: list[dict[str, Any]] = []
            selected_hierarchy: list[Candidate] = []
            visited: set[str] = set()
            frontier = list(hierarchy)
            provider_trace: dict[str, Any] = {}
            child_source = getattr(store, "hierarchy_children", None)
            object_source = getattr(store, "hierarchy_objects", None)
            source_expander = getattr(store, "hierarchy_source_atom_ids", None)
            bridge_seed_ids = [
                candidate.atom["atom_version_id"]
                for candidate in sorted(candidates.values(), key=lambda item: (-item.affinity, item.atom["atom_version_id"]))
                if "atom" in candidate.atom.get("facets", []) and candidate.affinity > 0
            ][:min(100, budget.affinity_limit)]
            allowed_bridge_ids = {
                candidate.atom["atom_version_id"]
                for candidate in candidates.values()
                if "atom" in candidate.atom.get("facets", [])
            }
            try:
                for round_number in range(1, budget.deep_max_rounds + 1):
                    available = [item for item in frontier if item.atom["atom_version_id"] not in visited]
                    if not available:
                        plans.append(DeepNavigationPlan(stop_reason="no_frontier", round=round_number).model_dump(mode="json"))
                        break
                    allowed_ids = {item.atom["atom_version_id"] for item in available}
                    hierarchy_payload = [
                        {
                            "atom_version_id": item.atom["atom_version_id"],
                            "content": item.atom["content"],
                            "source_atom_version_ids": item.atom.get("source_atom_version_ids", []),
                        }
                        for item in available[:max(budget.deep_branch_width * 4, budget.deep_max_nodes)]
                    ]
                    selected_ids, provider_trace = navigator.select(
                        query=request.query, candidates=hierarchy_payload,
                        max_nodes=min(budget.deep_branch_width, budget.deep_max_nodes),
                        token_budget=max(128, budget.deep_token_budget // budget.deep_max_rounds),
                    )
                    stop_reason = "sufficient" if selected_ids else "no_frontier"
                    plan = DeepNavigationPlan(
                        frontier_ids=[item["atom_version_id"] for item in hierarchy_payload],
                        selected_ids=[str(item) for item in selected_ids], bridge_seed_ids=bridge_seed_ids,
                        stop_reason=stop_reason, round=round_number,
                    ).validated_against(
                        allowed_ids,
                        branch_width=min(budget.deep_branch_width, budget.deep_max_nodes),
                        allowed_bridge_ids=allowed_bridge_ids,
                    )
                    plans.append(plan.model_dump(mode="json"))
                    if not plan.selected_ids:
                        break
                    selected = [item for item in available if item.atom["atom_version_id"] in set(plan.selected_ids)]
                    selected_hierarchy.extend(selected)
                    visited.update(plan.selected_ids)
                    anchor_ids = list(dict.fromkeys(
                        anchor for item in selected for anchor in item.atom.get("source_atom_version_ids", [])
                    ))[:budget.deep_max_nodes * 64]
                    for atom in store.atom_versions(anchor_ids):
                        atom_id = atom["atom_version_id"]
                        if atom_id not in candidates:
                            candidates[atom_id] = Candidate(atom=atom, deep=1.0, score=0.04)
                        else:
                            candidates[atom_id].deep = max(candidates[atom_id].deep, 1.0)
                            candidates[atom_id].score += 0.04
                    # Traverse only registered parent/child membership IDs.
                    # The controller never invents a child or relation.
                    child_ids: set[str] = set()
                    if callable(child_source):
                        projection_ids = [item.atom.get("projection_object_id") for item in selected if item.atom.get("projection_object_id")]
                        for child in child_source(request.workspace_id, projection_ids, limit=budget.deep_branch_width * 8):
                            if child.get("child_kind") == "projection_object":
                                child_ids.add(str(child.get("child_id")))
                    next_frontier: list[Candidate] = []
                    if child_ids and callable(object_source):
                        child_objects = object_source(
                            request.workspace_id,
                            sorted(child_ids),
                            limit=budget.deep_branch_width * 8,
                        )
                        for child_object in child_objects:
                            projection_object_id = str(child_object["projection_object_id"])
                            if callable(source_expander):
                                source_ids = source_expander(
                                    request.workspace_id, [projection_object_id],
                                    limit=min(512, budget.deep_max_nodes * 64),
                                )
                            else:
                                source_ids = list(child_object.get("source_atom_version_ids", []))
                            raw_sources = store.atom_versions(source_ids)
                            allowed_visibility = request.privacy_context.get("allowed_visibility")
                            if allowed_visibility is None and "visibility" in request.privacy_context:
                                allowed_visibility = [request.privacy_context["visibility"]]
                            if not source_ids or {str(source.get("atom_version_id")) for source in raw_sources} != set(source_ids) or (
                                allowed_visibility is not None
                                and any(source.get("security", {}).get("visibility") not in set(allowed_visibility) for source in raw_sources)
                            ):
                                continue
                            next_frontier.append(Candidate(
                                atom={
                                    "node_id": projection_object_id,
                                    "atom_version_id": projection_object_id,
                                    "workspace_id": request.workspace_id,
                                    "facets": ["summary", child_object.get("object_kind", "hierarchy")],
                                    "security": raw_sources[0].get("security", {}) if raw_sources else {},
                                    "content": child_object["content"],
                                    "content_hash": child_object["content_hash"],
                                    "properties": {
                                        **child_object.get("properties", {}),
                                        "projection_run_id": child_object.get("projection_run_id"),
                                        "projection_revision": child_object.get("projection_revision"),
                                    },
                                    "source_atom_version_ids": source_ids,
                                    "evidence_anchor_ids": [],
                                    "projection_object_id": projection_object_id,
                                },
                                hierarchy=0.0,
                                score=0.01,
                            ))
                    by_projection = {
                        str(item.atom.get("projection_object_id")): item
                        for item in [*hierarchy, *next_frontier]
                        if item.atom.get("projection_object_id")
                    }
                    frontier = [by_projection[item] for item in sorted(child_ids) if item in by_projection]
                    if not frontier:
                        frontier = [item for item in hierarchy if item.atom["atom_version_id"] not in visited]
                    if round_number == budget.deep_max_rounds:
                        plans.append(DeepNavigationPlan(stop_reason="max_rounds", round=round_number).model_dump(mode="json"))
            except Exception as error:
                # Deep navigation is an optional escalation. Provider/plan
                # failure explicitly degrades to the already-computed lower
                # retrieval profile; it never fabricates an answer or writes.
                plans.append(DeepNavigationPlan(stop_reason="provider_unavailable", round=min(budget.deep_max_rounds, len(plans) + 1)).model_dump(mode="json"))
                provider_trace = {"provider": getattr(navigator, "provider_id", None), "error": str(error)[:500]}
            deep_trace = {
                **provider_trace,
                "plans": plans,
                "visited_nodes": len(visited),
                "bridge_seed_ids": bridge_seed_ids,
                "degraded": bool(plans and plans[-1].get("stop_reason") == "provider_unavailable"),
            }
            preliminary = sorted([*candidates.values(), *selected_hierarchy], key=lambda item: (-item.score, item.atom["atom_version_id"]))
        final = preliminary[:budget.candidate_limit]
        raw_results = [item for item in final if "atom" in item.atom.get("facets", [])]
        state = "answerable" if raw_results else "insufficient_evidence"
        if state == "answerable" and len(raw_results) > 1 and len(query_terms) > 1 and abs(raw_results[0].score - raw_results[1].score) < 0.015:
            state = "ambiguous"
        return RetrievalOutcome(
            candidates=final,
            sufficiency_state=state,
            diagnostics={
                "lexical_provider": "bm25-okapi-v1",
                "dense_provider": self.dense_embedder.provider_id,
                "lexical_index": getattr(self.lexical_index, "provider_id", None),
                "dense_index": getattr(self.dense_index, "provider_id", None),
                "colbert_enabled": self.colbert_enabled,
                "colbert_provider": getattr(self.colbert_tier, "provider_id", None) if self.colbert_enabled else None,
                "reranker_provider": self.reranker.provider_id if rerank_applied else None,
                "deep_navigator": navigator.provider_id if deep_applied else None,
                "stage_counts": {"atoms": len(atoms), "lexical": len(lexical_rank), "dense": len(dense_rank), "fused": len(fused_ids), "hierarchy": len(hierarchy)},
                "graph_applied": graph_applied,
                "activation": activation_diagnostics,
                "hierarchy_applied": hierarchy_applied,
                "deep_applied": deep_applied,
                "deep_trace": deep_trace,
                "deep_degraded": bool(deep_trace and deep_trace.get("degraded")),
                "active_cortex_release_id": eff_release_id,
                "active_cortex_release": {
                    "release_id": active_rel["release_id"],
                    "spine_event_watermark": active_rel.get("spine_event_watermark"),
                    "policy_revision": active_rel.get("policy_revision"),
                    "code_revision": active_rel.get("code_revision"),
                } if active_rel else None,
            },
        )
