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

from .models import QueryRequest
from .model_gateway import ModelGatewayPolicy, ModelPolicy
from .store import ALLOWED_RELATIONS, STRUCTURAL_RELATIONS


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
    deep: float = 0.0
    score: float = 0.0
    paths: list[dict[str, Any]] = field(default_factory=list)


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
        deep_model = os.environ.get("TRACE_DEEP_MODEL")
        local_files_only = os.environ.get("TRACE_MODEL_LOCAL_FILES_ONLY", "true").lower() != "false"
        self.dense_embedder = dense_embedder or (
            SentenceTransformerDenseEmbedder(model_name, local_files_only=local_files_only) if model_name else HashingDenseEmbedder()
        )
        self.reranker = reranker or (
            SentenceTransformerCrossEncoderReranker(reranker_name, local_files_only=local_files_only) if reranker_name else DeterministicEvidenceReranker()
        )
        self.deep_navigator = deep_navigator or (LiteLLMDeepNavigator(deep_model) if deep_model else HeuristicDeepNavigator())
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
            embedded = self.dense_embedder.embed([atom["content"] for atom in missing])
            fresh = {atom["atom_version_id"]: vector for atom, vector in zip(missing, embedded, strict=True)}
            try:
                store.upsert_dense_vectors(
                    workspace_id=workspace_id, provider_id=self.dense_embedder.provider_id,
                    vectors=fresh, index_revision=index_revision,
                )
            except TypeError:
                store.upsert_dense_vectors(
                    workspace_id=workspace_id, provider_id=self.dense_embedder.provider_id, vectors=fresh,
                )
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
        for edge in store.current_edges(workspace_id, as_of_event):
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

    def _hierarchy_candidates(self, *, store: Any, request: QueryRequest) -> list[Candidate]:
        if not request.workspace_id:
            return []
        wanted = set(tokens(request.query))
        candidates: list[Candidate] = []
        latest_by_logical_key: dict[str, dict[str, Any]] = {}
        unkeyed: list[dict[str, Any]] = []
        for node in store.current_nodes(request.workspace_id, request.as_of_event):
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
    ) -> RetrievalOutcome:
        if not request.workspace_id or not atoms:
            return RetrievalOutcome([], "insufficient_evidence", {"reason": "no_visible_atoms"})
        query_terms = tokens(request.query)
        if not query_terms:
            return RetrievalOutcome([], "insufficient_evidence", {"reason": "no_query_terms"})
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
        if graph_applied:
            atom_by_node = {atom["node_id"]: atom for atom in atoms}
            graph, paths = self._graph_scores(
                store=store, workspace_id=request.workspace_id, as_of_event=request.as_of_event, direct=candidates,
                atom_by_node=atom_by_node, seed_limit=budget.graph_seed_limit, iterations=budget.graph_iterations,
            )
            # PPR is already non-negative and meaningful at its floor; max
            # normalization preserves a one-hop neighbor's activation instead
            # of turning the least-scored reachable node into an artificial 0.
            maximum_graph = max(graph.values(), default=0.0)
            normalized = {atom_id: value / maximum_graph for atom_id, value in graph.items()} if maximum_graph else {}
            for atom_id, value in normalized.items():
                if atom_id not in candidates:
                    candidates[atom_id] = Candidate(atom=atom_by_id[atom_id])
                candidates[atom_id].graph = value
                candidates[atom_id].paths = paths.get(atom_id, [])
                candidates[atom_id].score += budget.graph_weight * value
        ordered = sorted(candidates.values(), key=lambda item: (-item.score, item.atom["atom_version_id"]))
        top_raw = ordered[:budget.candidate_limit]
        hierarchy_applied = profile in {"hierarchy", "deep"} or (profile == "auto" and budget.mode in {"hierarchy", "deep"})
        hierarchy = self._hierarchy_candidates(store=store, request=request) if hierarchy_applied else []
        preliminary = sorted([*top_raw, *hierarchy], key=lambda item: (-item.score, item.atom["atom_version_id"]))
        raw_gap = abs(top_raw[0].score - top_raw[1].score) if len(top_raw) > 1 else 1.0
        preliminary_state = "answerable" if top_raw else "insufficient_evidence"
        if len(query_terms) > 1 and len(top_raw) > 1 and raw_gap < 0.015:
            preliminary_state = "ambiguous"
        deep_applied = profile == "deep" or (profile == "auto" and budget.mode == "deep") or (
            profile == "auto" and budget.allow_deep_escalation and preliminary_state in {"ambiguous", "insufficient_evidence"} and bool(hierarchy)
        )
        deep_trace: dict[str, Any] | None = None
        if deep_applied and hierarchy:
            hierarchy_payload = [
                {
                    "atom_version_id": item.atom["atom_version_id"],
                    "content": item.atom["content"],
                    "source_atom_version_ids": item.atom.get("source_atom_version_ids", []),
                }
                for item in hierarchy
            ]
            selected_ids, deep_trace = self.deep_navigator.select(
                query=request.query, candidates=hierarchy_payload, max_nodes=budget.deep_max_nodes, token_budget=budget.deep_token_budget,
            )
            selected_hierarchy = [item for item in hierarchy if item.atom["atom_version_id"] in set(selected_ids)]
            anchor_ids = [anchor for item in selected_hierarchy for anchor in item.atom.get("source_atom_version_ids", [])]
            for atom in store.atom_versions(anchor_ids):
                atom_id = atom["atom_version_id"]
                if atom_id not in candidates:
                    candidates[atom_id] = Candidate(atom=atom, deep=1.0, score=0.04)
                else:
                    candidates[atom_id].deep = 1.0
                    candidates[atom_id].score += 0.04
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
                "deep_navigator": self.deep_navigator.provider_id if deep_applied else None,
                "stage_counts": {"atoms": len(atoms), "lexical": len(lexical_rank), "dense": len(dense_rank), "fused": len(fused_ids), "hierarchy": len(hierarchy)},
                "graph_applied": graph_applied,
                "hierarchy_applied": hierarchy_applied,
                "deep_applied": deep_applied,
                "deep_trace": deep_trace,
            },
        )
