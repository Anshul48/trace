"""Evidence-anchored hierarchy and schema-proposal projections."""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Protocol, Sequence

from .retrieval import tokens
from .model_gateway import ModelGatewayPolicy, ModelPolicy


def _key(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(map(str, parts)).encode("utf-8")).hexdigest()


def _excerpt(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[:limit - 1]}…"


def _extractive_summary(items: Sequence[dict[str, Any]], *, label: str, limit: int = 3) -> str:
    excerpts = [_excerpt(item["content"]) for item in items[:limit]]
    return f"{label}: " + " | ".join(excerpts)


def _coverage(atom_ids: Sequence[str], *, total_atoms: int | None = None) -> dict[str, Any]:
    unique = list(dict.fromkeys(atom_ids))
    denominator = total_atoms if total_atoms is not None else len(unique)
    return {
        "covered_atom_version_ids": unique,
        "covered_atom_count": len(unique),
        "source_atom_count": denominator,
        "coverage_ratio": len(unique) / max(1, denominator),
    }


class SummaryValidationError(ValueError):
    pass


class ExtractiveSummaryGenerator:
    """Deterministic local summary generator used as the factual fallback."""

    provider_id = "extractive-summary-v1"

    def generate(self, source_atoms: Sequence[dict[str, Any]], *, label: str, max_items: int = 3) -> str:
        if not source_atoms:
            raise SummaryValidationError("a summary requires source atoms")
        return _extractive_summary(source_atoms, label=label, limit=max_items)


class SummaryValidator:
    """Validate generated navigation text against its anchored source set."""

    @staticmethod
    def validate(summary: str, source_atoms: Sequence[dict[str, Any]], *, minimum_overlap: float = 0.05) -> dict[str, Any]:
        if not summary.strip() or not source_atoms:
            raise SummaryValidationError("summary and source atoms are required")
        source_terms = set(tokens(" ".join(str(atom.get("content", "")) for atom in source_atoms)))
        summary_terms = set(tokens(summary))
        overlap = len(source_terms & summary_terms) / max(1, len(summary_terms))
        if overlap < minimum_overlap:
            raise SummaryValidationError("summary is not sufficiently covered by its source atoms")
        return {"covered_atom_count": len(source_atoms), "coverage_ratio": 1.0, "term_overlap": overlap}


@dataclass
class HierarchyBuildResult:
    workspace_id: str
    generation_id: str
    section_summaries: list[dict[str, Any]]
    topic_holons: list[dict[str, Any]]
    workspace_holons: list[dict[str, Any]]

    def model_dump(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "generation_id": self.generation_id,
            "section_summaries": self.section_summaries,
            "topic_holons": self.topic_holons,
            "workspace_holons": self.workspace_holons,
        }


class EvidenceHierarchyBuilder:
    """Builds replaceable, extractive hierarchy projections from source atoms.

    The builder deliberately does not infer new facts. Every generated text is
    an extractive digest, every level lists its atom-version evidence, and
    containment edges are anchored to the same source evidence.
    """

    def __init__(self, store: Any) -> None:
        self.store = store

    def _existing(self, workspace_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
        by_key: dict[str, dict[str, Any]] = {}
        lineage: dict[str, list[str]] = {}
        for node in self.store.current_nodes(workspace_id):
            properties = node.get("properties", {})
            key = properties.get("hierarchy_key")
            logical_key = properties.get("hierarchy_logical_key")
            if key:
                by_key[key] = node
            if logical_key:
                lineage.setdefault(logical_key, []).append(node["node_id"])
        return by_key, lineage

    def _existing_for_keys(self, workspace_id: str, hierarchy_keys: Sequence[str]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
        """Fetch only materializations this delta may recreate.

        This is the online path used after ingestion.  It avoids the legacy
        full-workspace summary read while preserving idempotency for a retried
        input/configuration revision.
        """

        lookup = getattr(self.store, "current_nodes_by_hierarchy_keys", None)
        nodes = lookup(workspace_id, hierarchy_keys) if callable(lookup) else []
        by_key: dict[str, dict[str, Any]] = {}
        lineage: dict[str, list[str]] = {}
        for node in nodes:
            properties = node.get("properties", {})
            key = properties.get("hierarchy_key")
            logical_key = properties.get("hierarchy_logical_key")
            if key:
                by_key[str(key)] = node
            if logical_key:
                lineage.setdefault(str(logical_key), []).append(node["node_id"])
        return by_key, lineage

    def _materialize(
        self,
        *,
        workspace_id: str,
        facet: str,
        content: str,
        evidence: list[str],
        hierarchy_key: str,
        logical_key: str,
        parent_node_ids: list[str],
        coverage: dict[str, Any],
        model_version: str,
        actor: str,
        existing: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        if hierarchy_key in existing:
            node = existing[hierarchy_key]
            return {
                "node_id": node["node_id"], "atom_version_id": node["atom_version_id"],
                "evidence_anchor_ids": node.get("properties", {}).get("evidence_anchor_ids", []),
                "evidence_atom_version_ids": node.get("properties", {}).get("evidence_atom_version_ids", evidence),
                "content": node.get("content", content),
                "reused": True,
            }
        created = self.store.create_derived_node(
            workspace_id=workspace_id,
            facets=["summary", facet],
            content=content,
            properties={
                "resolution": facet,
                "hierarchy_key": hierarchy_key,
                "hierarchy_logical_key": logical_key,
                "coverage": coverage,
                "model_version": model_version,
                "prompt_version": os.environ.get("TRACE_SUMMARY_PROMPT_VERSION", "extractive-v1"),
                "index_revision": os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
                "source_checksum": coverage.get("source_checksum", _key(*evidence)),
                "generated_at": datetime.now(UTC).isoformat(),
                "regeneration_lineage": {
                    "generator": "evidence-hierarchy-v1",
                    "parent_generation_node_ids": parent_node_ids,
                    "supersedes_projection_ids": parent_node_ids,
                    "replaces_projection": bool(parent_node_ids),
                },
            },
            evidence_atom_version_ids=evidence,
            actor=actor,
        )
        existing[hierarchy_key] = {**created, "properties": {"evidence_anchor_ids": created["evidence_anchor_ids"], "evidence_atom_version_ids": evidence}}
        return {**created, "content": content, "reused": False}

    def _contain(self, workspace_id: str, parent: dict[str, Any], children: Sequence[dict[str, Any]], *, actor: str, model_version: str) -> None:
        for child in children:
            evidence = list(child.get("evidence_atom_version_ids", [child.get("atom_version_id")]))[:64]
            evidence = [item for item in evidence if item]
            if not evidence:
                continue
            self.store.create_edge(
                workspace_id=workspace_id,
                source_node_id=parent["node_id"],
                target_node_id=child["node_id"],
                relation_type="CONTAINS",
                evidence_atom_version_ids=evidence,
                actor=actor,
                model_version=model_version,
                confidence=1.0,
                weight=1.0,
                status="trusted",
                properties={"structural": True, "hierarchy": True},
            )

    @staticmethod
    def _topic_clusters(sections: Sequence[tuple[dict[str, Any], list[dict[str, Any]]]], size: int) -> list[list[tuple[dict[str, Any], list[dict[str, Any]]]]]:
        """Greedy local topic grouping using transparent term overlap."""

        clusters: list[list[tuple[dict[str, Any], list[dict[str, Any]]]]] = []
        profiles: list[set[str]] = []
        for section, source_atoms in sections:
            profile = set(tokens(section["content"]))
            if not clusters:
                clusters.append([(section, source_atoms)])
                profiles.append(profile)
                continue
            candidate_index, similarity = 0, -1.0
            for index, existing in enumerate(profiles):
                overlap = len(profile & existing) / max(1, len(profile | existing))
                if overlap > similarity:
                    candidate_index, similarity = index, overlap
            if similarity >= 0.08 and len(clusters[candidate_index]) < size:
                clusters[candidate_index].append((section, source_atoms))
                profiles[candidate_index] |= profile
            else:
                clusters.append([(section, source_atoms)])
                profiles.append(profile)
        return clusters

    def build(
        self,
        *,
        workspace_id: str,
        section_size: int = 8,
        local_topic_size: int = 6,
        actor: str = "system",
        model_version: str = "extractive-hierarchy-v1",
        model_id: str | None = None,
        **kwargs: Any,
    ) -> HierarchyBuildResult:
        if os.environ.get("TRACE_PRODUCTION_MODE", "false").lower() == "true" and os.environ.get("TRACE_ALLOW_FULL_HIERARCHY_REBUILD", "false").lower() != "true":
            raise RuntimeError("full-workspace hierarchy rebuild is disabled in production; use build_delta during ingestion")
        atoms = self.store.queryable_atoms(workspace_id)
        atoms.sort(key=lambda atom: (atom["properties"].get("ingestion_id", ""), atom["properties"].get("ordinal", 0), atom["atom_version_id"]))
        generation_id = _key(workspace_id, model_version, *(atom["atom_version_id"] for atom in atoms))[:24]
        existing, lineage = self._existing(workspace_id)
        by_ingestion: dict[str, list[dict[str, Any]]] = {}
        for atom in atoms:
            by_ingestion.setdefault(str(atom["properties"].get("ingestion_id", "unknown")), []).append(atom)
        section_records: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for ingestion_id, source_atoms in by_ingestion.items():
            for start in range(0, len(source_atoms), section_size):
                group = source_atoms[start:start + section_size]
                evidence = [atom["atom_version_id"] for atom in group]
                logical_key = f"section:{ingestion_id}:{start // section_size}"
                hierarchy_key = _key(logical_key, model_version, *evidence)
                section = self._materialize(
                    workspace_id=workspace_id,
                    facet="section_summary",
                    content=_extractive_summary(group, label=f"Source section {ingestion_id}:{start // section_size + 1}"),
                    evidence=evidence,
                    hierarchy_key=hierarchy_key,
                    logical_key=logical_key,
                    parent_node_ids=lineage.get(logical_key, []),
                    coverage={**_coverage(evidence), "source_checksum": _key(*(atom["content_hash"] for atom in group)), "ingestion_id": ingestion_id, "ordinal_start": group[0]["properties"].get("ordinal"), "ordinal_end": group[-1]["properties"].get("ordinal")},
                    model_version=model_version,
                    actor=actor,
                    existing=existing,
                )
                if not section["reused"]:
                    self._contain(workspace_id, section, group, actor=actor, model_version=model_version)
                section_records.append((section, group))
        topic_records: list[tuple[dict[str, Any], list[tuple[dict[str, Any], list[dict[str, Any]]]]]] = []
        for index, cluster in enumerate(self._topic_clusters(section_records, local_topic_size)):
            evidence = list(dict.fromkeys(atom["atom_version_id"] for _, source_atoms in cluster for atom in source_atoms))
            common = Counter(term for section, _ in cluster for term in tokens(section["content"])).most_common(4)
            label = ", ".join(term for term, _ in common) or f"topic {index + 1}"
            logical_key = f"topic:{index}:{label}"
            hierarchy_key = _key(logical_key, model_version, *evidence)
            topic = self._materialize(
                workspace_id=workspace_id,
                facet="topic_holon",
                content=_extractive_summary([section for section, _ in cluster], label=f"Local topic Holon ({label})"),
                evidence=evidence,
                hierarchy_key=hierarchy_key,
                logical_key=logical_key,
                parent_node_ids=lineage.get(logical_key, []),
                coverage={**_coverage(evidence), "source_checksum": _key(*(atom["content_hash"] for _, source_atoms in cluster for atom in source_atoms)), "member_section_count": len(cluster), "topic_terms": [term for term, _ in common]},
                model_version=model_version,
                actor=actor,
                existing=existing,
            )
            if not topic["reused"]:
                self._contain(workspace_id, topic, [section for section, _ in cluster], actor=actor, model_version=model_version)
            topic_records.append((topic, cluster))
        workspace_holons: list[dict[str, Any]] = []
        if topic_records:
            evidence = list(dict.fromkeys(atom["atom_version_id"] for _, cluster in topic_records for _, source_atoms in cluster for atom in source_atoms))
            # Keep the projection bounded. Coverage explains when a large corpus
            # has more source atoms than this workspace overview directly cites.
            anchored = evidence[:512]
            logical_key = "workspace:overview"
            workspace = self._materialize(
                workspace_id=workspace_id,
                facet="workspace_holon",
                content=_extractive_summary([topic for topic, _ in topic_records], label="Workspace Holon"),
                evidence=anchored,
                hierarchy_key=_key(logical_key, model_version, *anchored),
                logical_key=logical_key,
                parent_node_ids=lineage.get(logical_key, []),
                coverage={**_coverage(anchored, total_atoms=len(evidence)), "source_checksum": _key(*(atom["content_hash"] for _, cluster in topic_records for _, source_atoms in cluster for atom in source_atoms)), "member_topic_count": len(topic_records), "anchor_truncated": len(anchored) < len(evidence)},
                model_version=model_version,
                actor=actor,
                existing=existing,
            )
            if not workspace["reused"]:
                self._contain(workspace_id, workspace, [topic for topic, _ in topic_records], actor=actor, model_version=model_version)
            workspace_holons.append(workspace)
        return HierarchyBuildResult(
            workspace_id=workspace_id,
            generation_id=generation_id,
            section_summaries=[section for section, _ in section_records],
            topic_holons=[topic for topic, _ in topic_records],
            workspace_holons=workspace_holons,
        )

    def build_delta(
        self,
        *,
        workspace_id: str,
        source_atoms: Sequence[dict[str, Any]],
        section_size: int = 8,
        actor: str = "cognitive-worker",
        model_version: str = "extractive-hierarchy-v1",
    ) -> HierarchyBuildResult:
        """Create validated navigation summaries for one ingestion delta.

        Delta work is bounded by the submitted atom list and exact existing
        hierarchy keys. It does not build workspace-wide topic clusters,
        schemas, or graph topology; those require their own bounded candidate
        generators and review flows.
        """

        atoms = list(source_atoms)
        if not atoms:
            return HierarchyBuildResult(workspace_id=workspace_id, generation_id=_key(workspace_id, model_version, "empty")[:24], section_summaries=[], topic_holons=[], workspace_holons=[])
        if any(str(atom.get("workspace_id")) != workspace_id for atom in atoms):
            raise SummaryValidationError("delta atoms must belong to exactly one workspace")
        atoms.sort(key=lambda atom: (str(atom.get("properties", {}).get("ingestion_id", "")), int(atom.get("properties", {}).get("ordinal", 0)), atom["atom_version_id"]))
        grouped: dict[str, list[dict[str, Any]]] = {}
        for atom in atoms:
            grouped.setdefault(str(atom.get("properties", {}).get("ingestion_id", "unknown")), []).append(atom)
        plans: list[tuple[str, int, list[dict[str, Any]], str, str]] = []
        for ingestion_id, group in grouped.items():
            for start in range(0, len(group), section_size):
                section = group[start:start + section_size]
                evidence = [atom["atom_version_id"] for atom in section]
                logical_key = f"section:{ingestion_id}:{start // section_size}"
                hierarchy_key = _key(logical_key, model_version, *evidence)
                plans.append((ingestion_id, start // section_size, section, logical_key, hierarchy_key))
        existing, lineage = self._existing_for_keys(workspace_id, [plan[4] for plan in plans])
        summaries: list[dict[str, Any]] = []
        for ingestion_id, ordinal, group, logical_key, hierarchy_key in plans:
            evidence = [atom["atom_version_id"] for atom in group]
            content = _extractive_summary(group, label=f"Source section {ingestion_id}:{ordinal + 1}")
            validation = SummaryValidator.validate(content, group)
            section = self._materialize(
                workspace_id=workspace_id,
                facet="section_summary",
                content=content,
                evidence=evidence,
                hierarchy_key=hierarchy_key,
                logical_key=logical_key,
                parent_node_ids=lineage.get(logical_key, []),
                coverage={
                    **_coverage(evidence),
                    **validation,
                    "source_checksum": _key(*(atom["content_hash"] for atom in group)),
                    "ingestion_id": ingestion_id,
                    "ordinal_start": group[0]["properties"].get("ordinal"),
                    "ordinal_end": group[-1]["properties"].get("ordinal"),
                    "input_revision": _key(*evidence),
                },
                model_version=model_version,
                actor=actor,
                existing=existing,
            )
            if not section["reused"]:
                self._contain(workspace_id, section, group, actor=actor, model_version=model_version)
            summaries.append(section)
        return HierarchyBuildResult(
            workspace_id=workspace_id,
            generation_id=_key(workspace_id, model_version, *(atom["atom_version_id"] for atom in atoms))[:24],
            section_summaries=summaries,
            topic_holons=[],
            workspace_holons=[],
        )


class SchemaProposer(Protocol):
    provider_id: str

    def propose(self, atoms: Sequence[dict[str, Any]], max_schemas: int) -> list[dict[str, Any]]: ...


class DeterministicSchemaProposer:
    """Produces reviewable label candidates; it never accepts them itself."""

    provider_id = "local-schema-proposer-v1"

    def propose(self, atoms: Sequence[dict[str, Any]], max_schemas: int) -> list[dict[str, Any]]:
        document_frequency: Counter[str] = Counter()
        terms_by_atom: dict[str, set[str]] = {}
        for atom in atoms:
            terms = set(tokens(atom["content"]))
            terms_by_atom[atom["atom_version_id"]] = terms
            document_frequency.update(terms)
        candidates: list[dict[str, Any]] = []
        # Tiny reviewed corpora are common during initial schema bootstrapping;
        # do not suppress their only recurring technical term.
        maximum_df = max(2, math.ceil(len(atoms) * 0.7))
        for term, count in document_frequency.most_common():
            if count < 2 or count > maximum_df or len(term) < 3:
                continue
            supporting = [atom for atom in atoms if term in terms_by_atom[atom["atom_version_id"]]]
            contrasting = [atom for atom in atoms if term not in terms_by_atom[atom["atom_version_id"]]][:2]
            candidates.append({
                "label": term,
                "definition": f"Technical evidence concerning {term}.",
                "positive_examples": [_excerpt(atom["content"], 140) for atom in supporting[:3]],
                "exclusions": [_excerpt(atom["content"], 100) for atom in contrasting],
                "evidence_atom_version_ids": [atom["atom_version_id"] for atom in supporting[:8]],
                "confidence": min(0.85, 0.35 + 0.1 * count),
            })
            if len(candidates) >= max_schemas:
                break
        return candidates


class CallableSchemaProposer:
    """Adapter for a stronger local/cloud teacher under explicit policy control.

    The caller receives only bounded source excerpts and must return candidate
    dictionaries with label, definition, examples/exclusions, confidence, and
    source atom-version IDs. Trace still persists them as *pending* proposals.
    """

    def __init__(self, provider_id: str, proposer: Callable[[Sequence[dict[str, Any]], int], Sequence[dict[str, Any]]]) -> None:
        self.provider_id = provider_id
        self._proposer = proposer

    def propose(self, atoms: Sequence[dict[str, Any]], max_schemas: int) -> list[dict[str, Any]]:
        safe_atoms = [
            {"atom_version_id": atom["atom_version_id"], "content": _excerpt(atom["content"], 800)}
            for atom in atoms[:256]
        ]
        candidates = list(self._proposer(safe_atoms, max_schemas))[:max_schemas]
        allowed = {atom["atom_version_id"] for atom in safe_atoms}
        result: list[dict[str, Any]] = []
        for candidate in candidates:
            evidence = [item for item in candidate.get("evidence_atom_version_ids", []) if item in allowed]
            if evidence:
                result.append({**candidate, "evidence_atom_version_ids": evidence})
        return result


class LiteLLMSchemaProposer:
    """Explicit cloud/local teacher for bounded, review-only schema proposals."""

    def __init__(self, model: str, *, gateway_policy: ModelGatewayPolicy | None = None) -> None:
        self.model = model
        self.provider_id = f"litellm:{model}"
        self.gateway_policy = gateway_policy or ModelGatewayPolicy(
            ModelPolicy(
                allow_cloud=os.environ.get("TRACE_ALLOW_CLOUD_MODELS", "false").lower() == "true",
                token_budget=int(os.environ.get("TRACE_SCHEMA_TOKEN_BUDGET", "4000")),
            )
        )

    def propose(self, atoms: Sequence[dict[str, Any]], max_schemas: int) -> list[dict[str, Any]]:
        try:
            from litellm import completion
        except ImportError as error:  # pragma: no cover - optional deployment adapter
            raise RuntimeError("litellm is required for the configured schema proposer") from error
        _, prepared_atoms, audit = self.gateway_policy.prepare(
            provider=self.provider_id, purpose="schema_proposal", query="schema induction",
            candidates=[{"atom_version_id": atom["atom_version_id"], "content": atom["content"]} for atom in atoms[:128]],
            max_nodes=128, token_budget=int(os.environ.get("TRACE_SCHEMA_TOKEN_BUDGET", "4000")), cloud=True,
        )
        safe_atoms = [{"id": atom["atom_version_id"], "excerpt": atom["content"]} for atom in prepared_atoms]
        prompt = (
            "Propose technical-document schemas for human review. Do not make factual assertions. "
            "Return strict JSON {\"schemas\":[{\"label\":str,\"definition\":str,\"positive_examples\":[str],"
            "\"exclusions\":[str],\"confidence\":number,\"evidence_atom_version_ids\":[str]}]}. "
            f"Limit schemas to {max_schemas}; evidence IDs must come from this list: {json.dumps(safe_atoms, ensure_ascii=False)}"
        )
        response = completion(model=self.model, messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=2_000)
        try:
            value = json.loads(response.choices[0].message.content or "{}")
        except json.JSONDecodeError as error:
            raise RuntimeError("schema proposer returned non-JSON output") from error
        allowed = {atom["id"] for atom in safe_atoms}
        result: list[dict[str, Any]] = []
        for candidate in value.get("schemas", [])[:max_schemas]:
            if not isinstance(candidate, dict) or not isinstance(candidate.get("label"), str):
                continue
            evidence = [item for item in candidate.get("evidence_atom_version_ids", []) if item in allowed]
            if not evidence:
                continue
            result.append({
                "label": candidate["label"],
                "definition": str(candidate.get("definition", "")),
                "positive_examples": [str(item) for item in candidate.get("positive_examples", [])[:5]],
                "exclusions": [str(item) for item in candidate.get("exclusions", [])[:5]],
                "confidence": max(0.0, min(1.0, float(candidate.get("confidence", 0.0)))),
                "evidence_atom_version_ids": evidence,
            })
        return result


class GLiNERCandidateExtractor:
    """Local-only candidate span extractor for schema/entity proposals."""

    provider_id = "gliner-local-v1"

    def __init__(self, model_name: str | None = None, *, local_files_only: bool = True) -> None:
        self.model_name = model_name or os.environ.get("TRACE_GLINER_MODEL", "urchade/gliner_medium-v2.1")
        self.local_files_only = local_files_only
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from gliner import GLiNER
            except ImportError as error:  # pragma: no cover - optional local deployment dependency
                raise RuntimeError("GLiNER is required for the configured local span extractor") from error
            self._model = GLiNER.from_pretrained(self.model_name, local_files_only=self.local_files_only)
        return self._model

    def extract(self, text: str, labels: Sequence[str]) -> list[dict[str, Any]]:
        if not labels:
            return []
        entities = self._load().predict_entities(text[:8_000], list(labels))
        return [
            {"label": str(entity.get("label", "")), "text": str(entity.get("text", "")), "score": float(entity.get("score", 0.0))}
            for entity in entities
            if entity.get("text") and entity.get("label")
        ]


class GLiNERSchemaProposer:
    """Build reviewable schema candidates from local GLiNER spans."""

    provider_id = "gliner-local-schema-v1"

    def __init__(self, extractor: GLiNERCandidateExtractor | None = None) -> None:
        self.extractor = extractor or GLiNERCandidateExtractor()
        self.fallback = DeterministicSchemaProposer()

    def propose(self, atoms: Sequence[dict[str, Any]], max_schemas: int) -> list[dict[str, Any]]:
        labels = ["component", "technology", "concept", "operation"]
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        try:
            for atom in atoms[:256]:
                for entity in self.extractor.extract(atom["content"], labels):
                    normalized = str(entity["text"]).strip().lower()
                    if len(normalized) < 3:
                        continue
                    grouped.setdefault((str(entity["label"]), normalized), []).append(atom)
        except RuntimeError:
            return self.fallback.propose(atoms, max_schemas)
        candidates: list[dict[str, Any]] = []
        for (entity_label, normalized), supporting in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
            candidates.append({
                "label": normalized,
                "definition": f"Evidence span classified as {entity_label}.",
                "positive_examples": [_excerpt(atom["content"], 140) for atom in supporting[:8]],
                "exclusions": [],
                "evidence_atom_version_ids": [atom["atom_version_id"] for atom in supporting[:8]],
                "confidence": min(0.95, 0.45 + 0.05 * len(supporting)),
            })
            if len(candidates) >= max_schemas:
                break
        return candidates or self.fallback.propose(atoms, max_schemas)


class GovernedSchemaClassifier:
    """Soft classifier until a workspace has 8 positive and 8 negative reviews."""

    MIN_REVIEWED_POSITIVE = 8
    MIN_REVIEWED_NEGATIVE = 8

    @classmethod
    def training_ready(cls, schema: dict[str, Any]) -> bool:
        properties = schema.get("properties", {})
        # Teacher-generated examples are proposal material, not training data.
        # A reviewer must explicitly place examples in these lists before a
        # workspace-specific SetFit model is eligible to train.
        positive = properties.get("reviewed_positive_examples", [])
        negative = properties.get("reviewed_negative_examples", [])
        return len(positive) >= cls.MIN_REVIEWED_POSITIVE and len(negative) >= cls.MIN_REVIEWED_NEGATIVE

    @classmethod
    def classify(cls, atoms: Sequence[dict[str, Any]], schemas: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        ready = [schema for schema in schemas if cls.training_ready(schema)]
        if not ready:
            return SoftSchemaClassifier.classify(atoms, schemas)
        trained = SetFitSchemaClassifier.classify(atoms, ready)
        if trained is None:
            # Deterministic classification is the explicit unavailable-model
            # fallback; it is never silently used after a successful model
            # prediction.
            return SoftSchemaClassifier.classify(atoms, schemas)
        return trained


class SetFitSchemaClassifier:
    """Actual per-workspace binary SetFit training after reviewed examples.

    Each promoted schema receives its own tiny binary classifier. Cache keys
    include the workspace, schema identity, reviewed-example checksum, and
    configured base model so a changed review set creates a fresh model rather
    than mutating an unversioned in-memory classifier.
    """

    _cache: dict[str, Any] = {}
    _failed: set[str] = set()

    @classmethod
    def _training_rows(cls, schema: dict[str, Any]) -> tuple[list[str], list[int], str]:
        properties = schema.get("properties", {})
        positive = [str(item).strip() for item in properties.get("reviewed_positive_examples", []) if str(item).strip()]
        negative = [str(item).strip() for item in properties.get("reviewed_negative_examples", []) if str(item).strip()]
        if len(positive) < GovernedSchemaClassifier.MIN_REVIEWED_POSITIVE or len(negative) < GovernedSchemaClassifier.MIN_REVIEWED_NEGATIVE:
            raise ValueError("SetFit training requires eight reviewed positive and eight reviewed negative examples")
        texts = positive + negative
        labels = [1] * len(positive) + [0] * len(negative)
        revision = hashlib.sha256(
            json.dumps({"texts": texts, "labels": labels, "base": os.environ.get("TRACE_SETFIT_MODEL", "sentence-transformers/paraphrase-mpnet-base-v2")}, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return texts, labels, revision

    @classmethod
    def _key(cls, schema: dict[str, Any], revision: str) -> str:
        return ":".join((str(schema.get("workspace_id", "")), str(schema.get("node_id", schema.get("atom_version_id", ""))), revision))

    @classmethod
    def _train(cls, schema: dict[str, Any]) -> tuple[Any, str] | None:
        texts, labels, revision = cls._training_rows(schema)
        key = cls._key(schema, revision)
        if key in cls._cache:
            return cls._cache[key], revision
        if key in cls._failed:
            return None
        try:
            from setfit import SetFitModel
            try:
                from datasets import Dataset
            except ImportError:
                Dataset = None  # type: ignore[assignment]
            model = SetFitModel.from_pretrained(os.environ.get("TRACE_SETFIT_MODEL", "sentence-transformers/paraphrase-mpnet-base-v2"))
            # A small test/in-house adapter may expose ``fit`` directly. The
            # normal SetFit path uses the installed trainer API.
            if hasattr(model, "fit"):
                model.fit(texts, labels)
            else:
                if Dataset is None:
                    raise RuntimeError("datasets is required for SetFit training")
                train_dataset = Dataset.from_dict({"text": texts, "label": labels})
                try:
                    from setfit import Trainer
                    trainer = Trainer(model=model, train_dataset=train_dataset)
                except ImportError:  # pragma: no cover - older SetFit releases
                    from setfit import SetFitTrainer
                    trainer = SetFitTrainer(model=model, train_dataset=train_dataset)
                trainer.train()
            cls._cache[key] = model
            return model, revision
        except (ImportError, OSError, RuntimeError, ValueError, TypeError):
            # Model assets may be unavailable on a local worker. Record this
            # revision as unavailable and use the deterministic fallback until
            # the reviewed examples or configuration revision changes.
            cls._failed.add(key)
            return None

    @staticmethod
    def _prediction_values(model: Any, texts: list[str]) -> tuple[list[int], list[float]]:
        predicted = model.predict(texts)
        if hasattr(predicted, "tolist"):
            predicted = predicted.tolist()
        labels = [int(item) for item in list(predicted)]
        scores = [1.0 if item else 0.0 for item in labels]
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(texts)
            if hasattr(probabilities, "tolist"):
                probabilities = probabilities.tolist()
            values = list(probabilities)
            scores = [float(item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else item) for item in values]
        return labels, scores

    @classmethod
    def classify(cls, atoms: Sequence[dict[str, Any]], schemas: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]] | None:
        models: list[tuple[dict[str, Any], Any, str]] = []
        for schema in schemas:
            trained = cls._train(schema)
            if trained is None:
                return None
            model, revision = trained
            models.append((schema, model, revision))
        output: dict[str, list[dict[str, Any]]] = {atom["atom_version_id"]: [] for atom in atoms}
        texts = [atom["content"] for atom in atoms]
        for schema, model, revision in models:
            labels, scores = cls._prediction_values(model, texts)
            properties = schema.get("properties", {})
            label = str(properties.get("label") or properties.get("name") or schema["content"])
            for atom, predicted, score in zip(atoms, labels, scores, strict=True):
                if predicted:
                    output[atom["atom_version_id"]].append({
                        "label": label,
                        "confidence": round(max(0.0, min(1.0, score)), 6),
                        "schema_node_id": schema["node_id"],
                        "classifier": "setfit",
                        "training_revision": revision,
                    })
        for atom_id, labels in output.items():
            labels.sort(key=lambda item: (-item["confidence"], item["label"]))
        return output


class SoftSchemaClassifier:
    """Classifies accepted schemas as optional ranking features, never filters."""

    @staticmethod
    def classify(atoms: Sequence[dict[str, Any]], schemas: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        output: dict[str, list[dict[str, Any]]] = {}
        for atom in atoms:
            atom_terms = set(tokens(atom["content"]))
            labels: list[dict[str, Any]] = []
            for schema in schemas:
                properties = schema.get("properties", {})
                label = str(properties.get("label") or properties.get("name") or schema["content"])
                definition = set(tokens(str(properties.get("definition", schema["content"]))))
                positives = set(tokens(" ".join(map(str, properties.get("positive_examples", [])))))
                exclusions = set(tokens(" ".join(map(str, properties.get("exclusions", [])))))
                positive = len(atom_terms & (definition | positives)) / max(1, len(atom_terms))
                negative = len(atom_terms & exclusions) / max(1, len(atom_terms))
                confidence = max(0.0, min(1.0, positive - negative))
                if confidence:
                    labels.append({"label": label, "confidence": round(confidence, 6), "schema_node_id": schema["node_id"]})
            output[atom["atom_version_id"]] = sorted(labels, key=lambda item: (-item["confidence"], item["label"]))
        return output

    @staticmethod
    def query_alignment(query: str, labels: Sequence[dict[str, Any]]) -> float:
        wanted = set(tokens(query))
        return max((len(wanted & set(tokens(item["label"]))) / max(1, len(wanted))) * item["confidence"] for item in labels) if labels else 0.0


# ==============================================================================
# Work Packet 3 (WP3): L2 Macro-Topology (TOC-DAG) & Drift Monitor
# ==============================================================================

MAX_TOC_FANOUT = 64
COHESION_FLOOR = 0.08
DRIFT_EPSILON = 0.25
MIN_EFFECTIVE_RADIUS = 0.05
NEWBORN_APOPTOSIS_GRACE_DAYS = 7.0
OVERFLOW_APOPTOSIS_DAYS = 30.0

TOC_STATUS_ACTIVE = "ACTIVE"
TOC_STATUS_STALE_CENTROID = "STALE_CENTROID"
TOC_STATUS_DORMANT = "DORMANT"
TOC_STATUS_DIRTY_CONTRACT = "DIRTY_CONTRACT"

NODE_TYPE_STANDARD = "STANDARD"
NODE_TYPE_DIVERSE_OVERFLOW = "DIVERSE_OVERFLOW"


def _vector_dot(u: Sequence[float], v: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(u, v))


def _vector_norm(v: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _unit_norm(v: Sequence[float]) -> list[float]:
    n = _vector_norm(v)
    if n <= 1e-9:
        return [0.0] * len(v)
    return [x / n for x in v]


def _frechet_unit_centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    acc = [0.0] * dim
    for vec in vectors:
        for i, val in enumerate(vec):
            acc[i] += val
    return _unit_norm(acc)


def _dequantize_int8(data: bytes | Sequence[int]) -> list[float]:
    floats = []
    for b in data:
        val = b if b < 128 else b - 256
        floats.append(val / 127.0)
    return _unit_norm(floats)


def _effective_radius(c0: Sequence[float], member_vecs: Sequence[Sequence[float]]) -> float:
    """R0_eff = max(1.0 - min_{h in TOC}(c0 . h), 0.05)."""
    if not member_vecs:
        return MIN_EFFECTIVE_RADIUS
    max_dist = max(1.0 - _vector_dot(c0, mv) for mv in member_vecs)
    return max(max_dist, MIN_EFFECTIVE_RADIUS)


def evaluate_holon_energy(hits_7d: float = 0.0, centrality: float = 0.0, age_days: float = 0.0) -> float:
    """energy = max(0.0, 1.0*hits_7d + 0.5*centrality - 0.02*age_days)."""
    raw = 1.0 * float(hits_7d) + 0.5 * float(centrality) - 0.02 * float(age_days)
    return max(0.0, raw)


def is_newborn_apoptosis_exempt(holon: Any, *, grace_days: float = NEWBORN_APOPTOSIS_GRACE_DAYS, now: datetime | None = None) -> bool:
    """Holons with age_days < 7 are strictly exempt from apoptosis pruning."""
    if isinstance(holon, HolonMember):
        if holon.age_days > 0.0:
            age = holon.age_days
        elif holon.created_at:
            try:
                dt = datetime.fromisoformat(str(holon.created_at).replace("Z", "+00:00"))
                current_time = now or datetime.now(UTC)
                age = max(0.0, (current_time - dt).total_seconds() / 86400.0)
            except Exception:
                age = 0.0
        else:
            age = 0.0
    elif isinstance(holon, dict):
        if "age_days" in holon and holon["age_days"] is not None:
            age = float(holon["age_days"])
        elif "created_at" in holon and holon["created_at"]:
            created_str = str(holon["created_at"])
            try:
                dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                current_time = now or datetime.now(UTC)
                age = max(0.0, (current_time - dt).total_seconds() / 86400.0)
            except Exception:
                age = 0.0
        else:
            age = 0.0
    elif hasattr(holon, "age_days"):
        age = float(getattr(holon, "age_days"))
    else:
        age = 0.0

    return age < grace_days


@dataclass
class HolonMember:
    """L1 Holon member descriptor for L2 TOC partitioning."""

    id: str
    centroid: list[float]
    lex_sig: list[str] = field(default_factory=list)
    created_at: str | None = None
    hits_7d: float = 0.0
    centrality: float = 0.0
    age_days: float = 0.0
    energy: float = 0.0


def normalize_holon_member(item: Any, *, now: datetime | None = None) -> HolonMember:
    """Normalize input dict/dataclass into HolonMember."""
    if isinstance(item, HolonMember):
        return item
    if isinstance(item, dict):
        vec = item.get("centroid", item.get("centroid_int8", []))
        if isinstance(vec, bytes):
            vec = _dequantize_int8(vec)
        elif vec and isinstance(vec, (list, tuple)):
            vec = _unit_norm(vec)
        lex_sig = item.get("lex_sig", [])
        if isinstance(lex_sig, str):
            try:
                lex_sig = json.loads(lex_sig)
            except Exception:
                lex_sig = []
        hits_7d = float(item.get("hits_7d", 0.0))
        centrality = float(item.get("centrality", 0.0))
        created_at = item.get("created_at")

        if "age_days" in item and item["age_days"] is not None:
            age_days = float(item["age_days"])
        elif created_at:
            try:
                dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                current_time = now or datetime.now(UTC)
                age_days = max(0.0, (current_time - dt).total_seconds() / 86400.0)
            except Exception:
                age_days = 0.0
        else:
            age_days = 0.0

        energy = item.get("energy", evaluate_holon_energy(hits_7d, centrality, age_days))
        return HolonMember(
            id=str(item.get("id", item.get("node_id", ""))),
            centroid=list(vec),
            lex_sig=list(lex_sig),
            created_at=created_at,
            hits_7d=hits_7d,
            centrality=centrality,
            age_days=age_days,
            energy=float(energy),
        )
    raise TypeError(f"Cannot normalize member of type {type(item)}")


@dataclass
class TOCNode:
    """L2 TOC partition node."""

    id: str
    parent: str | None
    c0: list[float]
    r0: float
    members: list[str]
    boundary: dict[str, Any] = field(default_factory=dict)
    status: str = TOC_STATUS_ACTIVE
    version: int = 1
    node_type: str = NODE_TYPE_STANDARD
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        b = self.boundary
        if isinstance(b, str):
            try:
                b = json.loads(b)
            except Exception:
                b = {}
        elif isinstance(b, dict):
            b = dict(b)
        else:
            b = {}
        b.setdefault("node_type", self.node_type)

        return {
            "id": self.id,
            "parent": self.parent,
            "c0": self.c0_bytes,
            "r0": self.r0,
            "members": list(self.members),
            "boundary": b,
            "status": self.status,
            "version": self.version,
            "created_at": self.created_at,
            "node_type": self.node_type,
            "excluded_from_beam": self.excluded_from_beam,
        }

    @property
    def c0_bytes(self) -> bytes:
        return struct.pack(f"{len(self.c0)}f", *self.c0)

    @property
    def excluded_from_beam(self) -> bool:
        b = self.boundary
        if isinstance(b, str):
            try:
                b = json.loads(b)
            except Exception:
                b = {}
        elif not isinstance(b, dict):
            b = {}

        return (
            self.node_type == NODE_TYPE_DIVERSE_OVERFLOW
            or b.get("node_type") == NODE_TYPE_DIVERSE_OVERFLOW
            or b.get("cohesion_floor", COHESION_FLOOR) == 0.0
            or (self.status == TOC_STATUS_STALE_CENTROID and self.node_type == NODE_TYPE_DIVERSE_OVERFLOW)
        )


def is_candidate_for_beam(node: Any) -> bool:
    """DIVERSE_OVERFLOW nodes are excluded from Tier 2 beam candidacy."""
    if isinstance(node, TOCNode):
        return not node.excluded_from_beam
    if isinstance(node, dict):
        if node.get("node_type") == NODE_TYPE_DIVERSE_OVERFLOW:
            return False
        if node.get("excluded_from_beam") is True:
            return False

        boundary = node.get("boundary") or {}
        if isinstance(boundary, str):
            try:
                boundary = json.loads(boundary)
            except Exception:
                boundary = {}
        elif not isinstance(boundary, dict):
            boundary = {}

        if boundary.get("node_type") == NODE_TYPE_DIVERSE_OVERFLOW:
            return False
        if boundary.get("cohesion_floor") == 0.0:
            return False
        if node.get("status") == TOC_STATUS_STALE_CENTROID and (
            boundary.get("cohesion_floor") == 0.0 or node.get("node_type") == NODE_TYPE_DIVERSE_OVERFLOW
        ):
            return False
        return True
    return True


def is_overflow_orphan_apoptosis_eligible(
    node: Any,
    *,
    orphan_days: float = OVERFLOW_APOPTOSIS_DAYS,
    is_orphaned: bool = True,
    now: datetime | None = None,
) -> bool:
    """Evaluate 30-day orphan apoptosis policy for DIVERSE_OVERFLOW nodes.

    Per CORTICAL_SUBSTRATE_V1_PLAN Appendix A (Row 4):
    DIVERSE_OVERFLOW nodes are pruned after 30 days if orphaned.
    """
    if isinstance(node, TOCNode):
        node_type = node.node_type
        created_at = node.created_at
    elif isinstance(node, dict):
        node_type = node.get("node_type")
        boundary = node.get("boundary") or {}
        if isinstance(boundary, str):
            try:
                boundary = json.loads(boundary)
            except Exception:
                boundary = {}
        if not node_type and isinstance(boundary, dict):
            node_type = boundary.get("node_type")
        created_at = node.get("created_at")
    else:
        return False

    if node_type != NODE_TYPE_DIVERSE_OVERFLOW:
        return False

    if not is_orphaned:
        return False

    if not created_at:
        return False

    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        current_time = now or datetime.now(UTC)
        age_days = (current_time - dt).total_seconds() / 86400.0
        return age_days >= orphan_days
    except Exception:
        return False


def check_cohesion(
    members: Sequence[HolonMember],
    cohesion_floor: float = COHESION_FLOOR,
    min_shared_terms: int = 1,
) -> tuple[bool, float]:
    """Intra-cluster Jaccard affinity >= 0.08; min 1 shared salient term.

    Evaluates intra-cluster cohesion:
    1. For |members| <= 1: trivially satisfies cohesion.
    2. For |members| > 1: every member must share >= min_shared_terms with
       the union of terms in other cluster members, and the cluster average
       Jaccard affinity must satisfy >= cohesion_floor.
    """
    if len(members) <= 1:
        return True, 1.0

    member_terms = [set(m.lex_sig) for m in members]
    total_jaccard = 0.0

    for i, terms_i in enumerate(member_terms):
        other_terms: set[str] = set()
        for j, terms_j in enumerate(member_terms):
            if i != j:
                other_terms.update(terms_j)

        shared = terms_i & other_terms
        if len(shared) < min_shared_terms:
            return False, 0.0

        union = terms_i | other_terms
        jaccard = len(shared) / max(1, len(union))
        total_jaccard += jaccard

    avg_jaccard = total_jaccard / len(members)
    return avg_jaccard >= cohesion_floor, avg_jaccard


def detect_centroid_drift(
    c0: Sequence[float],
    c_new: Sequence[float],
    *,
    r0: float | None = None,
    members: Sequence[Any] | None = None,
    drift_epsilon: float = DRIFT_EPSILON,
) -> tuple[bool, float, float]:
    """Hyperspherical Cosine Drift Monitor:

    Delta_cos = 1.0 - (c0 . c_new)
    R0_eff = max(R0, 0.05) where R0 = max_{h in TOC}(1.0 - c0 . h)
    Flag STALE_CENTROID iff Delta_cos > 0.25 * R0_eff.
    Returns: (is_stale, delta_cos, threshold)
    """
    u_c0 = _unit_norm(c0)
    u_c_new = _unit_norm(c_new)
    delta_cos = max(0.0, 1.0 - _vector_dot(u_c0, u_c_new))

    if r0 is not None:
        r0_eff = max(float(r0), MIN_EFFECTIVE_RADIUS)
    elif members:
        member_vecs = [
            normalize_holon_member(m).centroid
            for m in members
            if normalize_holon_member(m).centroid
        ]
        r0_eff = _effective_radius(u_c0, member_vecs)
    else:
        r0_eff = MIN_EFFECTIVE_RADIUS

    threshold = drift_epsilon * r0_eff
    is_stale = delta_cos > threshold
    return is_stale, delta_cos, threshold


def bisecting_spherical_2means(
    members: Sequence[Any],
    *,
    parent_id: str | None = None,
    c0: Sequence[float] | None = None,
    max_fanout: int = MAX_TOC_FANOUT,
) -> list[TOCNode]:
    """Deterministic Bisecting Spherical 2-Means partitioning.

    When |members| > 64, bisect using diametrically opposed seeds:
      s1 = argmax (1.0 - h . c0)
      s2 = argmax (1.0 - h . s1)
    with members iterated in strictly sorted-ID order to guarantee deterministic tie-breaking.
    Recursively bisects child partitions until all partitions satisfy |members| <= 64.
    """
    norm_members = [normalize_holon_member(m) for m in members]
    norm_members.sort(key=lambda m: m.id)

    if not norm_members:
        return []

    if len(norm_members) <= max_fanout:
        member_vecs = [m.centroid for m in norm_members]
        c_unit = _frechet_unit_centroid(member_vecs) if member_vecs else (list(c0) if c0 else [0.0] * 384)
        r0 = _effective_radius(c_unit, member_vecs)
        valid, cohesion_score = check_cohesion(norm_members)
        node_id = f"toc_{_key(parent_id or 'root', *(m.id for m in norm_members))[:16]}"
        boundary = {
            "cohesion_floor": COHESION_FLOOR if valid else 0.0,
            "radius": r0,
            "cohesion_score": cohesion_score,
            "node_type": NODE_TYPE_STANDARD,
        }
        return [
            TOCNode(
                id=node_id,
                parent=parent_id,
                c0=c_unit,
                r0=r0,
                members=[m.id for m in norm_members],
                boundary=boundary,
                status=TOC_STATUS_ACTIVE,
                node_type=NODE_TYPE_STANDARD,
            )
        ]

    # |members| > 64: Bisect using diametrical seeds with sorted-ID tie breaking
    if c0 and any(c0):
        base_c0 = _unit_norm(c0)
    else:
        base_c0 = _frechet_unit_centroid([m.centroid for m in norm_members])

    # Seed 1: s1 = argmax_{h in members} (1.0 - h . c0) in sorted-ID order
    best_d1 = -1.0
    s1 = norm_members[0]
    for m in norm_members:
        d = 1.0 - _vector_dot(m.centroid, base_c0)
        if d > best_d1:
            best_d1 = d
            s1 = m

    # Seed 2: s2 = argmax_{h in members} (1.0 - h . s1) in sorted-ID order
    best_d2 = -1.0
    s2 = norm_members[0]
    for m in norm_members:
        d = 1.0 - _vector_dot(m.centroid, s1.centroid)
        if d > best_d2:
            best_d2 = d
            s2 = m

    if s1.id == s2.id and len(norm_members) > 1:
        s2 = norm_members[-1]

    c1 = list(s1.centroid)
    c2 = list(s2.centroid)
    part1: list[HolonMember] = []
    part2: list[HolonMember] = []

    for _ in range(25):
        part1 = []
        part2 = []
        for m in norm_members:
            sim1 = _vector_dot(m.centroid, c1)
            sim2 = _vector_dot(m.centroid, c2)
            if sim1 > sim2:
                part1.append(m)
            elif sim2 > sim1:
                part2.append(m)
            else:
                # Deterministic tie-break
                part1.append(m)

        # Degenerate partition guard
        if not part1 or not part2:
            mid = len(norm_members) // 2
            part1 = norm_members[:mid]
            part2 = norm_members[mid:]
            break

        new_c1 = _frechet_unit_centroid([m.centroid for m in part1])
        new_c2 = _frechet_unit_centroid([m.centroid for m in part2])
        if _vector_dot(new_c1, c1) > 1.0 - 1e-7 and _vector_dot(new_c2, c2) > 1.0 - 1e-7:
            c1, c2 = new_c1, new_c2
            break
        c1, c2 = new_c1, new_c2

    # Recursive bisection
    sub1 = bisecting_spherical_2means(part1, parent_id=parent_id, c0=c1, max_fanout=max_fanout)
    sub2 = bisecting_spherical_2means(part2, parent_id=parent_id, c0=c2, max_fanout=max_fanout)
    return sub1 + sub2


def resolve_cohesion_deadlocks(
    nodes: Sequence[TOCNode],
    all_members: Mapping[str, HolonMember],
    *,
    parent_id: str | None = None,
    max_fanout: int = MAX_TOC_FANOUT,
) -> list[TOCNode]:
    """Cohesion deadlock resolution:

    If a split partition violates cohesion (< 0.08), reassign members to
    available neighbor TOC nodes; if no neighbor satisfies capacity (<= 64)
    and cohesion (>= 0.08), assign to a DIVERSE_OVERFLOW TOC node under
    parent with cohesion_floor = 0.0 and status STALE_CENTROID.
    Fan-out <= 64 is strictly enforced across all nodes including overflow.
    """
    valid_nodes: list[TOCNode] = []
    deadlocked_members: list[HolonMember] = []

    for node in nodes:
        node_members = [all_members[mid] for mid in node.members if mid in all_members]
        valid, cohesion_score = check_cohesion(node_members)
        if valid:
            valid_nodes.append(node)
        else:
            deadlocked_members.extend(node_members)

    if not deadlocked_members:
        return list(nodes)

    # Sort deadlocked members by ID for deterministic processing
    deadlocked_members.sort(key=lambda m: m.id)
    overflow_members: list[HolonMember] = []

    for m in deadlocked_members:
        reassigned = False
        # Try available neighbor nodes
        for neighbor in valid_nodes:
            if len(neighbor.members) < max_fanout:
                cand_members = [all_members[mid] for mid in neighbor.members if mid in all_members] + [m]
                can_join, cand_score = check_cohesion(cand_members)
                if can_join:
                    neighbor.members.append(m.id)
                    neighbor.members.sort()
                    cand_vecs = [cm.centroid for cm in cand_members]
                    neighbor.c0 = _frechet_unit_centroid(cand_vecs)
                    neighbor.r0 = _effective_radius(neighbor.c0, cand_vecs)
                    if not isinstance(neighbor.boundary, dict):
                        neighbor.boundary = {}
                    neighbor.boundary["radius"] = neighbor.r0
                    neighbor.boundary["cohesion_score"] = cand_score
                    reassigned = True
                    break
        if not reassigned:
            overflow_members.append(m)

    if overflow_members:
        # Create DIVERSE_OVERFLOW node(s) with fanout <= 64
        for chunk_idx in range(0, len(overflow_members), max_fanout):
            chunk = overflow_members[chunk_idx : chunk_idx + max_fanout]
            chunk_vecs = [m.centroid for m in chunk]
            c_over = _frechet_unit_centroid(chunk_vecs)
            r0_over = _effective_radius(c_over, chunk_vecs)
            overflow_id = f"toc_overflow_{chunk_idx // max_fanout}_{_key(parent_id or 'root', *(m.id for m in chunk))[:12]}"
            overflow_node = TOCNode(
                id=overflow_id,
                parent=parent_id,
                c0=c_over,
                r0=r0_over,
                members=[m.id for m in chunk],
                boundary={
                    "cohesion_floor": 0.0,
                    "radius": r0_over,
                    "cohesion_score": 0.0,
                    "node_type": NODE_TYPE_DIVERSE_OVERFLOW,
                },
                status=TOC_STATUS_STALE_CENTROID,
                node_type=NODE_TYPE_DIVERSE_OVERFLOW,
                created_at=datetime.now(UTC).isoformat(),
            )
            valid_nodes.append(overflow_node)

    return valid_nodes


class TOCPartitionManager:
    """Governs L2 TOC macro-topology, deterministic bisecting spherical 2-means,

    cohesion deadlocks, DIVERSE_OVERFLOW nodes, and hyperspherical drift monitoring.
    """

    def __init__(
        self,
        store: Any = None,
        max_fanout: int = MAX_TOC_FANOUT,
        cohesion_floor: float = COHESION_FLOOR,
        drift_epsilon: float = DRIFT_EPSILON,
    ) -> None:
        self.store = store
        self.max_fanout = max_fanout
        self.cohesion_floor = cohesion_floor
        self.drift_epsilon = drift_epsilon

    def partition_members(
        self,
        members: Sequence[Any],
        parent_id: str | None = None,
        c0: Sequence[float] | None = None,
    ) -> list[TOCNode]:
        """Deterministically partition members into TOC nodes with fan-out <= 64."""
        norm_members = [normalize_holon_member(m) for m in members]
        norm_members.sort(key=lambda m: m.id)
        if not norm_members:
            return []

        by_id = {m.id: m for m in norm_members}

        raw_nodes = bisecting_spherical_2means(
            norm_members,
            parent_id=parent_id,
            c0=c0,
            max_fanout=self.max_fanout,
        )

        final_nodes = resolve_cohesion_deadlocks(
            raw_nodes,
            by_id,
            parent_id=parent_id,
            max_fanout=self.max_fanout,
        )

        for node in final_nodes:
            assert len(node.members) <= self.max_fanout, f"Fanout bound <= {self.max_fanout} breached: {len(node.members)}"

        if self.store is not None and hasattr(self.store, "insert_toc_nodes"):
            self.store.insert_toc_nodes([n.to_dict() for n in final_nodes])

        return final_nodes

    def check_drift(
        self,
        toc_id: str,
        new_centroid: Sequence[float] | None = None,
        members: Sequence[Any] | None = None,
    ) -> tuple[bool, float, float]:
        """Check if a TOC node has experienced hyperspherical drift."""
        node = None
        if self.store is not None and hasattr(self.store, "get_toc_node"):
            node = self.store.get_toc_node(toc_id)

        if node is not None:
            c0_data = node.get("c0")
            if isinstance(c0_data, bytes):
                c0 = list(struct.unpack(f"{len(c0_data)//4}f", c0_data))
            else:
                c0 = list(c0_data or [])
            r0 = float(node.get("r0") or MIN_EFFECTIVE_RADIUS)
        else:
            c0 = [0.0] * 384
            r0 = None

        if new_centroid is None and members:
            member_vecs = [
                normalize_holon_member(m).centroid
                for m in members
                if normalize_holon_member(m).centroid
            ]
            new_c = _frechet_unit_centroid(member_vecs)
        elif new_centroid is not None:
            new_c = list(new_centroid)
        else:
            return False, 0.0, 0.0

        is_stale, delta_cos, thresh = detect_centroid_drift(
            c0, new_c, r0=r0, members=members, drift_epsilon=self.drift_epsilon
        )
        if is_stale and node is not None and self.store is not None:
            node["status"] = TOC_STATUS_STALE_CENTROID
            if hasattr(self.store, "insert_toc_nodes"):
                self.store.insert_toc_nodes([node])

        return is_stale, delta_cos, thresh

