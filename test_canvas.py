import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from trace.core.schemas import CanonicalEntity, HippocampalTrace, GraphEdge
from trace.core.serializer.obsidian_canvas import ObsidianCanvasGenerator

def test_canvas():
    entities = [
        CanonicalEntity(
            id="1", 
            canonical_name="Test Concept", 
            status="active",
            traces=[HippocampalTrace(anchor_concept="Test Concept", artifact_type="core_concept", status="active", summary_trace="", relations=[], raw_source_text="")]
        )
    ]
    edges = [("1", "2", "depends_on")]
    
    output_dir = "test_output"
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        canvas_edges = []
        for source_id, target_id, relation_type in edges:
            canvas_edges.append(GraphEdge(source_id=source_id, target_id=target_id, relation_type=relation_type))
        
        import re
        entity_to_path = {e.id: f"{re.sub(r'[\\\\/*?:\"<>|]', '', e.canonical_name)}.md" for e in entities}
        
        canvas_gen = ObsidianCanvasGenerator(output_dir)
        canvas_gen.generate(entities, canvas_edges, entity_to_path)
        print("Success")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

test_canvas()
