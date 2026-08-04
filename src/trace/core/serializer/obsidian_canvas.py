import json
import os
import uuid
from typing import List, Dict

from trace.core.schemas import CanonicalEntity, GraphEdge

class ObsidianCanvasGenerator:
    def __init__(self, output_dir: str = "repo_out"):
        self.output_dir = output_dir

    def generate(self, entities: List[CanonicalEntity], edges: List[GraphEdge], entity_to_path: Dict[str, str], filename: str = "project_graph.canvas", vault_prefix: str = "", hierarchy: Dict[str, tuple] = None):
        try:
            import networkx as nx
        except ImportError:
            nx = None
            
        canvas_data = {
            "nodes": [],
            "edges": []
        }

        node_width = 400
        node_height = 200

        # Calculate coordinates
        positions = {}
        if nx and edges and entities:
            G = nx.DiGraph()
            for entity in entities:
                G.add_node(entity.id)
            for edge in edges:
                G.add_edge(edge.source_id, edge.target_id)
            
            # Remove cycles for layout purposes
            layout_G = G.copy()
            while True:
                try:
                    cycle = nx.find_cycle(layout_G, orientation="original")
                    layout_G.remove_edge(cycle[0][0], cycle[0][1])
                except nx.NetworkXNoCycle:
                    break
            
            generations = list(nx.topological_generations(layout_G))
            layer_width = 800
            node_height_offset = 300
            
            for gen_idx, generation in enumerate(generations):
                # Center the nodes vertically within the layer
                total_height = len(generation) * node_height_offset
                start_y = -total_height / 2
                for node_idx, node_id in enumerate(generation):
                    x = gen_idx * layer_width
                    y = start_y + node_idx * node_height_offset
                    positions[node_id] = (int(x), int(y))
        elif hierarchy and entities:
            # Layout by hierarchy
            part_width = 600
            chapter_height_offset = 300
            topic_height_offset = 250
            
            for entity in entities:
                pos = hierarchy.get(entity.canonical_name)
                if pos:
                    part_idx, chap_idx, topic_idx = pos
                    x = part_idx * part_width
                    y = chap_idx * chapter_height_offset * 3 + topic_idx * topic_height_offset
                    positions[entity.id] = (x, y)
                else:
                    # Fallback if not in hierarchy
                    positions[entity.id] = (0, 0)
        else:
            # Fallback to grid
            nodes_per_row = 5
            padding_x = 150
            padding_y = 150
            for idx, entity in enumerate(entities):
                row = idx // nodes_per_row
                col = idx % nodes_per_row
                x = col * (node_width + padding_x)
                y = row * (node_height + padding_y)
                positions[entity.id] = (x, y)

        for entity in entities:
            x, y = positions.get(entity.id, (0, 0))
            rel_path = entity_to_path.get(entity.id, f"{entity.id}.md").replace("\\", "/")
            if vault_prefix:
                rel_path = f"{vault_prefix.rstrip('/')}/{rel_path}"

            canvas_data["nodes"].append({
                "id": entity.id,
                "type": "file",
                "file": rel_path,
                "x": x,
                "y": y,
                "width": node_width,
                "height": node_height
            })

        for edge in edges:
            edge_id = str(uuid.uuid4())
            canvas_data["edges"].append({
                "id": edge_id,
                "fromNode": edge.source_id,
                "fromSide": "right",
                "toNode": edge.target_id,
                "toSide": "left",
                "label": edge.relation_type
            })

        abs_path = os.path.join(self.output_dir, filename)
        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(canvas_data, f, indent=2)

