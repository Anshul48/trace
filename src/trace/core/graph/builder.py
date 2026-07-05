from typing import List
from trace.core.schemas import Event, TraceExtractedPayload, HippocampalTrace, GraphResolvedPayload, GraphEdge
from trace.core.graph.clustering import GraphClusterer
from trace.events.bus import event_bus

class GraphBuilder:
    def __init__(self):
        self.clusterer = GraphClusterer()

    async def handle_trigger_graph_build(self, event: Event):
        if event.name == "TriggerGraphBuild":
            project_id = event.payload.get("project_id")
            if not project_id:
                return
                
            from trace.core.db import db
            import json
            
            raw_traces = db.get_traces_by_project(project_id)
            traces = []
            for row in raw_traces:
                if row.get("metadata"):
                    try:
                        trace_obj = HippocampalTrace.model_validate_json(row["metadata"])
                        
                        # Apply user overrides if they exist
                        if row.get("user_concept"): trace_obj.anchor_concept = row["user_concept"]
                        if row.get("user_type"): trace_obj.artifact_type = row["user_type"]
                        # We would also parse user_relations here ideally
                        
                        traces.append(trace_obj)
                    except:
                        pass
                        
            # 1. Cluster traces into canonical entities
            entities = self.clusterer.cluster_traces(traces)
            
            # Create a lookup for anchor_concept to CanonicalEntity ID
            concept_to_id = {}
            for entity in entities:
                for trace in entity.traces:
                    concept_to_id[trace.anchor_concept] = entity.id
            
            # 2. Build edges based on relations in traces
            edges = []
            for entity in entities:
                for trace in entity.traces:
                    for rel in trace.relations:
                        # Find target ID
                        target_id = concept_to_id.get(rel.target_concept)
                        if not target_id:
                            # Simple substring fallback for unmapped concepts
                            for c_name in concept_to_id.keys():
                                if rel.target_concept.lower() in c_name.lower():
                                    target_id = concept_to_id[c_name]
                                    break
                        
                        if target_id and target_id != entity.id:
                            edges.append(GraphEdge(
                                source_id=entity.id,
                                target_id=target_id,
                                relation_type=rel.relation_type
                            ))
            
            # Remove duplicate edges
            unique_edges = []
            seen_edges = set()
            for e in edges:
                key = (e.source_id, e.target_id, e.relation_type)
                if key not in seen_edges:
                    seen_edges.add(key)
                    unique_edges.append(e)

            payload = GraphResolvedPayload(project_id=project_id, entities=entities, edges=unique_edges)
            await event_bus.publish(Event(name="GraphResolved", payload=payload))

# Global instance initialization
graph_builder = GraphBuilder()
event_bus.subscribe("TriggerGraphBuild", graph_builder.handle_trigger_graph_build)
