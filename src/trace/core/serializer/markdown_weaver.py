import os
from typing import List, Dict
from trace.core.schemas import CanonicalEntity, GraphEdge
from trace.agents.writer_agent import writer_agent

class MarkdownWeaver:
    def __init__(self, output_dir: str = "repo_out"):
        self.output_dir = output_dir

    async def write_repository(self, entities: List[CanonicalEntity], edges: List[GraphEdge], global_toc: str):
        # Create base directories
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "01-concepts"), exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "02-versions"), exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "03-ideas", "active"), exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "03-ideas", "parked"), exist_ok=True)
        
        # Mapping from entity ID to file path (relative to repo root)
        entity_to_path: Dict[str, str] = {}
        for entity in entities:
            entity_to_path[entity.id] = self._determine_path(entity)
            
        # Write individual markdown files
        for entity in entities:
            await self._write_entity_file(entity, edges, entity_to_path)
            
        # Write global README
        readme_path = os.path.join(self.output_dir, "README.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("# Project Trace Repository\n\n")
            f.write(global_toc)
            f.write("\n\n## Index\n")
            for entity in sorted(entities, key=lambda x: x.canonical_name):
                rel_path = entity_to_path[entity.id].replace("\\", "/")
                f.write(f"- [[{entity.canonical_name}]] (./{rel_path})\n")
                
    def _determine_path(self, entity: CanonicalEntity) -> str:
        # Determine directory based on artifact type and status
        artifact_type = entity.traces[0].artifact_type if entity.traces else "core_concept"
        
        if artifact_type == "core_concept":
            base = "01-concepts"
        elif artifact_type == "version_milestone":
            base = "02-versions"
        else: # technical_idea, architecture_decision
            base = os.path.join("03-ideas", "active" if entity.status == "active" else "parked")
            
        return os.path.join(base, f"{entity.id}.md")
        
    async def _write_entity_file(self, entity: CanonicalEntity, edges: List[GraphEdge], entity_to_path: Dict[str, str]):
        abs_path = os.path.join(self.output_dir, entity_to_path[entity.id])
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        # Generate the compiled markdown body using the WriterAgent
        compiled_markdown = await writer_agent.generate_document(entity)
        
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(f"---\n")
            f.write(f"id: {entity.id}\n")
            f.write(f"status: {entity.status}\n")
            f.write(f"---\n\n")
            
            f.write(f"# {entity.canonical_name}\n\n")
            
            f.write(compiled_markdown)
            
            f.write("\n\n## Relationships\n")
            outgoing = [e for e in edges if e.source_id == entity.id]
            for edge in outgoing:
                target_path = entity_to_path.get(edge.target_id)
                if target_path:
                    rel = edge.relation_type
                    target_name = edge.target_id.replace("_", " ").title()
                    # wikilink with relative path
                    f.write(f"- {rel}: [[{target_name}]]\n")
