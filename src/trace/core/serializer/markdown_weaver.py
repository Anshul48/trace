import os
from typing import List, Dict, Tuple
from trace.core.schemas import CanonicalEntity, GraphEdge
from trace.agents.writer_agent import writer_agent
import re

class MarkdownWeaver:
    def __init__(self, output_dir: str = "repo_out"):
        self.output_dir = output_dir

    def parse_toc_for_mappings(self, toc_str: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        entity_parts = {}
        entity_chapters = {}
        current_part = "Uncategorized"
        current_chapter = "General"
        if not toc_str:
            return entity_parts, entity_chapters
            
        for line in toc_str.split('\n'):
            line = line.strip()
            if line.startswith("## "):
                current_part = line[3:].strip()
                current_chapter = "General"
            elif line.startswith("### "):
                current_chapter = line[4:].strip()
            elif line.startswith("* [[") and line.endswith("]]"):
                entity_name = line[4:-2]
                entity_parts[entity_name] = current_part
                entity_chapters[entity_name] = current_chapter
        return entity_parts, entity_chapters

    async def write_repository(self, entities: List[CanonicalEntity], edges: List[GraphEdge], global_toc: str, part_guidance: Dict[str, str] = None):
        if part_guidance is None: part_guidance = {}
        os.makedirs(self.output_dir, exist_ok=True)
        
        entity_parts, entity_chapters = self.parse_toc_for_mappings(global_toc)
        
        if global_toc:
            valid_entities = []
            for e in entities:
                if e.canonical_name.lower() in global_toc.lower():
                    valid_entities.append(e)
            entities = valid_entities
            
        # Mapping from entity ID to file path (relative to repo root)
        entity_to_path: Dict[str, str] = {}
        for entity in entities:
            entity_to_path[entity.id] = self._determine_path(entity, entity_parts, entity_chapters)
            
        # Write individual markdown files
        for entity in entities:
            await self._write_entity_file(entity, entities, edges, entity_to_path, entity_parts, part_guidance)
            
        # Write global README / TOC
        readme_path = os.path.join(self.output_dir, "TOC.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("# Project Trace Repository\n\n")
            if global_toc:
                f.write(global_toc)
            f.write("\n\n## Index\n")
            for entity in sorted(entities, key=lambda x: x.canonical_name):
                f.write(f"- [[{entity.canonical_name}]]\n")
                
        # Generate consolidated document
        try:
            consolidated = global_toc or ""
            for entity in entities:
                name = entity.canonical_name
                pattern = r'\* \[\[' + re.escape(name) + r'\]\]'
                consolidated = re.sub(pattern, f"* [[#{name}]]", consolidated, flags=re.IGNORECASE)
                
            consolidated += "\n\n---\n\n"
            
            for entity in entities:
                abs_path = os.path.join(self.output_dir, entity_to_path[entity.id])
                if os.path.exists(abs_path):
                    with open(abs_path, "r", encoding="utf-8") as f:
                        ent_content = f.read()
                    consolidated += ent_content + "\n\n---\n\n"
                    
            with open(os.path.join(self.output_dir, "_consolidated.md"), "w", encoding="utf-8") as f:
                f.write(consolidated)
        except Exception as e:
            print("Failed to generate Consolidated Doc:", e)

        # Generate canvas
        try:
            from trace.core.serializer.obsidian_canvas import ObsidianCanvasGenerator
            
            hierarchy = {}
            if global_toc:
                current_part = -1
                current_chapter = -1
                current_topic = 0
                for line in global_toc.split("\n"):
                    line = line.strip()
                    if line.startswith("## "):
                        current_part += 1
                        current_chapter = -1
                    elif line.startswith("### "):
                        current_chapter += 1
                        current_topic = 0
                    elif line.startswith("* [[") and line.endswith("]]"):
                        entity_name = line[4:-2]
                        hierarchy[entity_name] = (max(0, current_part), max(0, current_chapter), current_topic)
                        current_topic += 1
            
            canvas_gen = ObsidianCanvasGenerator(self.output_dir)
            edges_by_type = {}
            for e in edges:
                if e.relation_type not in edges_by_type:
                    edges_by_type[e.relation_type] = []
                edges_by_type[e.relation_type].append(e)
                
            for rel_type, type_edges in edges_by_type.items():
                connected_ids = set()
                for e in type_edges:
                    connected_ids.add(e.source_id)
                    connected_ids.add(e.target_id)
                connected_entities = [ent for ent in entities if ent.id in connected_ids]
                canvas_gen.generate(connected_entities, type_edges, entity_to_path, filename=f"_dag_{rel_type}.canvas", hierarchy=hierarchy)
            
            canvas_gen.generate(entities, edges, entity_to_path, filename="_dag_project_graph.canvas", hierarchy=hierarchy)
        except Exception as e:
            print("Failed to generate Obsidian Canvas:", e)
                
    def _determine_path(self, entity: CanonicalEntity, entity_parts: Dict[str, str], entity_chapters: Dict[str, str]) -> str:
        part_name = entity_parts.get(entity.canonical_name)
        chapter_name = entity_chapters.get(entity.canonical_name)
        
        safe_name = re.sub(r'[\\/*?:"<>|]', "", entity.canonical_name)
        
        if part_name and chapter_name:
            safe_part = re.sub(r'[\\/*?:"<>|]', "", part_name)
            safe_chapter = re.sub(r'[\\/*?:"<>|]', "", chapter_name)
            return os.path.join(safe_part, safe_chapter, f"{safe_name}.md")
        else:
            return os.path.join("Uncategorized", f"{safe_name}.md")
        
    async def _write_entity_file(self, entity: CanonicalEntity, entities: List[CanonicalEntity], edges: List[GraphEdge], entity_to_path: Dict[str, str], entity_parts: Dict[str, str], part_guidance: Dict[str, str]):
        abs_path = os.path.join(self.output_dir, entity_to_path[entity.id])
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        # Determine part guidance
        guidance_for_entity = ""
        part_name = entity_parts.get(entity.canonical_name)
        if part_name and part_guidance:
            guidance_for_entity = part_guidance.get(part_name, "")
            
        # Generate the compiled markdown body using the WriterAgent
        compiled_markdown = await writer_agent.generate_document(entity, part_guidance_text=guidance_for_entity)
        
        # Entity linking pass
        for other_entity in entities:
            if other_entity.id == entity.id:
                continue
            name = other_entity.canonical_name
            pattern = r'(?<!\[\[)\b' + re.escape(name) + r'\b(?!\]\])'
            compiled_markdown = re.sub(pattern, f"[[{name}]]", compiled_markdown, flags=re.IGNORECASE)
        
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
                    target_entity = next((e for e in entities if e.id == edge.target_id), None)
                    target_name = target_entity.canonical_name if target_entity else edge.target_id.replace("_", " ").title()
                    rel = edge.relation_type
                    f.write(f"- {rel}: [[{target_name}]]\n")
