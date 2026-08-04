import json
import uuid
import os
from typing import List, Dict
from trace.core.schemas import HippocampalTrace, CanonicalEntity, GraphEdge, ConflictResolutionResult
from trace.agents.utils import safe_acompletion

class ConflictResolutionAgent:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.environ.get("PLANNER_MODEL", "gemini/gemini-3.5-flash")

    async def resolve_island(self, island_traces: List[HippocampalTrace], blocks_dict: Dict[str, dict]) -> ConflictResolutionResult:
        if len(island_traces) == 1:
            t = island_traces[0]
            canonical_name = t.anchor_concept
            c_id = canonical_name.lower().replace(" ", "_").replace("-", "_")
            return ConflictResolutionResult(
                resolved_entities=[CanonicalEntity(id=c_id, canonical_name=canonical_name, traces=[t], status=t.status)],
                new_edges=[]
            )
            
        # Chronological sort (by chunk_index or textual metadata)
        sorted_traces = sorted(island_traces, key=lambda t: t.source_meta.chunk_index if t.source_meta else 0)
        
        prompt = """You are a Conflict Resolution Agent verifying a cluster of architectural traces.
These traces were grouped by a vector algorithm and are presented in chronological order (oldest to newest).

Task A (Identity): Do these traces represent the exact same core concept? If the vector search incorrectly grouped distinct concepts (e.g., 'User Auth' and 'User UI'), separate them into multiple Canonical Entities.
Task B (Paradox Resolution): If they ARE the same concept, check for contradictions. If Trace 1 says X and Trace 2 says Y, use the chronological order to determine the ultimate truth (newer supersedes older). 
IMPORTANT: If the text does not explicitly resolve the conflict, DO NOT hallucinate. Admit ignorance by marking the status as 'conflicted' and creating a 'paradox' relation.

You MUST provide a strict Chain of Thought with exact substring quotes proving your resolution.
Output ONLY a JSON object matching this schema exactly:
{
    "resolved_entities": [
        {
            "id": "concept_id",
            "canonical_name": "Unified Concept Name",
            "traces": [{"trace_id": "original_trace_id"}],
            "status": "active" | "legacy" | "conflicted" | "informational"
        }
    ],
    "new_edges": [
        {
            "source_id": "concept_id_A",
            "target_id": "concept_id_B",
            "relation_type": "supersedes" | "paradox",
            "resolution_quote": "exact quote from the raw text proving this"
        }
    ]
}

Traces:
"""
        for t in sorted_traces:
            prompt += f"- Trace ID: {t.trace_id} | Anchor: {t.anchor_concept} | Summary: {t.summary_trace} | Raw Text: {t.raw_source_text}\n"

        try:
            resp = await safe_acompletion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            out = resp.choices[0].message.content
            cleaned = out.strip()
            if cleaned.startswith("```json"): cleaned = cleaned[7:]
            if cleaned.endswith("```"): cleaned = cleaned[:-3]
            result_json = json.loads(cleaned.strip())
            
            # Anti-hallucination Citation Check
            valid_edges = []
            for edge in result_json.get("new_edges", []):
                quote = edge.get("resolution_quote", "")
                if not quote:
                    edge["relation_type"] = "paradox"
                    
                # Verify quote exists in raw texts
                if quote:
                    quote_found = False
                    for t in sorted_traces:
                        if t.raw_source_text and quote in t.raw_source_text:
                            quote_found = True
                            break
                    if not quote_found:
                        # Hallucination detected! Force paradox.
                        edge["relation_type"] = "paradox"
                        # Force all associated entities to conflicted
                        for re in result_json.get("resolved_entities", []):
                            if re.get("id") in [edge.get("source_id"), edge.get("target_id")]:
                                re["status"] = "conflicted"
                    
                valid_edges.append(GraphEdge(
                    source_id=edge.get("source_id", ""),
                    target_id=edge.get("target_id", ""),
                    relation_type=edge.get("relation_type", "paradox")
                ))
                
            entities = []
            for e in result_json.get("resolved_entities", []):
                # Reconstruct trace objects
                e_traces = []
                for t_dict in e.get("traces", []):
                    t_id = t_dict.get("trace_id")
                    for st in sorted_traces:
                        if st.trace_id == t_id:
                            # Update status based on LLM output
                            st.status = e.get("status", st.status)
                            e_traces.append(st)
                            break
                entities.append(CanonicalEntity(
                    id=e.get("id", str(uuid.uuid4())),
                    canonical_name=e.get("canonical_name", "Unknown"),
                    traces=e_traces,
                    status=e.get("status", "informational")
                ))
                
            return ConflictResolutionResult(resolved_entities=entities, new_edges=valid_edges)

        except Exception as e:
            print(f"Error in ConflictResolutionAgent: {e}")
            # Fallback: keep them as one entity if possible, informational
            fallback_entity = CanonicalEntity(
                id=sorted_traces[0].anchor_concept.lower().replace(" ", "_"),
                canonical_name=sorted_traces[0].anchor_concept,
                traces=sorted_traces,
                status="informational"
            )
            return ConflictResolutionResult(resolved_entities=[fallback_entity], new_edges=[])
