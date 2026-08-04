import uuid
import json
import asyncio
from typing import List, Dict, Any
from trace.core.db import db
from trace.core.vector_db import vector_db
from trace.core.schemas import HippocampalTrace, ExtractedRelation
from trace.agents.utils import safe_acompletion
from trace.events.bus import event_bus, Event

class MergingEngine:
    def __init__(self, model_name: str = "gemini/gemini-3.5-flash", similarity_threshold: float = 0.4):
        self.model_name = model_name
        self.similarity_threshold = similarity_threshold

    async def merge_threads(self, target_project_id: str, source_project_ids: List[str]):
        """
        Merge one or more source projects into a target project.
        """
        for source_id in source_project_ids:
            await self._merge_single_thread(target_project_id, source_id)
            
        # After merging all sources, trigger graph rebuild for the target
        db.update_project_status(target_project_id, "synthesizing")
        await event_bus.publish(Event(name="TriggerGraphBuild", payload={"project_id": target_project_id}))

    async def _merge_single_thread(self, target_project_id: str, source_project_id: str):
        # 1. Fetch all source blocks
        source_blocks = db.get_blocks_by_project(source_project_id)
        if not source_blocks:
            return

        source_texts = [block['content'] for block in source_blocks]
        source_block_ids = [block['id'] for block in source_blocks]

        # 2. Vector Space Union & Collision Detection
        # Query target project vectors using source texts
        results = vector_db.query_similar_chunks(
            project_id=target_project_id,
            query_texts=source_texts,
            n_results=1  # We just care if there's at least one highly similar chunk
        )

        merge_tasks = []

        for i, (source_id, source_text) in enumerate(zip(source_block_ids, source_texts)):
            # results['distances'][i] is a list of distances for the i-th query
            distances = results.get('distances', [])[i] if results.get('distances') else []
            target_ids = results.get('ids', [])[i] if results.get('ids') else []
            
            collision_detected = False
            colliding_target_block_id = None
            
            if distances and len(distances) > 0:
                min_distance = distances[0]
                if min_distance < self.similarity_threshold:
                    collision_detected = True
                    colliding_target_block_id = target_ids[0]

            source_traces_raw = db.get_traces_by_block(source_id)
            source_traces = [self._parse_trace(row) for row in source_traces_raw]

            if collision_detected and colliding_target_block_id:
                # 3. Trace Graph Fusion (Identify Candidates)
                target_traces_raw = db.get_traces_by_block(colliding_target_block_id)
                target_traces = [self._parse_trace(row) for row in target_traces_raw]
                
                if source_traces and target_traces:
                    # 4. Synaptic Pruning
                    task = asyncio.create_task(
                        self._synaptic_prune_and_save(target_project_id, colliding_target_block_id, source_traces, target_traces)
                    )
                    merge_tasks.append(task)
                else:
                    # If one is missing traces for some reason, just copy source traces
                    self._copy_traces_to_target(source_traces, target_project_id, source_id, source_text)
            else:
                # No collision: pristine distinct knowledge
                # Copy block and its traces to target project
                self._copy_traces_to_target(source_traces, target_project_id, source_id, source_text)
                
        if merge_tasks:
            await asyncio.gather(*merge_tasks)

    def _parse_trace(self, row: dict) -> dict:
        metadata = row.get('metadata')
        if metadata:
            return json.loads(metadata)
        # Fallback if flat columns are used
        return {
            "trace_id": row.get("trace_id"),
            "anchor_concept": row.get("anchor_concept"),
            "artifact_type": row.get("artifact_type"),
            "status": row.get("status"),
            "summary_trace": row.get("summary_trace"),
            "relations": [], 
            "raw_source_text": row.get("raw_source_text", "")
        }

    def _copy_traces_to_target(self, source_traces: List[dict], target_project_id: str, source_block_id: str, source_text: str):
        # We need to upsert the block into the target project first
        db.upsert_block(source_block_id, target_project_id, source_text, sparse_vector=None)
        
        for trace in source_traces:
            new_trace_id = str(uuid.uuid4())
            db.upsert_trace(
                trace_id=new_trace_id,
                project_id=target_project_id,
                block_id=source_block_id,
                anchor_concept=trace.get('anchor_concept', 'Unknown'),
                artifact_type=trace.get('artifact_type', 'informational'),
                status=trace.get('status', 'active'),
                summary_trace=trace.get('summary_trace', ''),
                chronological_marker=trace.get('chronological_marker'),
                raw_source_text=trace.get('raw_source_text', source_text)
            )

    async def _synaptic_prune_and_save(self, target_project_id: str, target_block_id: str, source_traces: List[dict], target_traces: List[dict]):
        # LLM Synthesis
        # Minify for semantic merging
        target_minified = [{"anchor": t.get("anchor_concept"), "summary": t.get("summary_trace"), "status": t.get("status")} for t in target_traces]
        source_minified = [{"anchor": t.get("anchor_concept"), "summary": t.get("summary_trace"), "status": t.get("status")} for t in source_traces]
        
        prompt = f"""
        You are merging two knowledge bases (Thread A and Thread B). 
        Here are highly overlapping semantic Traces from both threads regarding similar concepts.
        
        Thread A Traces (Target):
        {json.dumps(target_minified, indent=2)}
        
        Thread B Traces (Source):
        {json.dumps(source_minified, indent=2)}
        
        Synthesize them into a single, comprehensive 'Mega-Trace' that perfectly captures the combined knowledge without redundancy. 
        Prune duplicates and merge complimentary facts.
        
        Output ONLY a JSON object representing the unified trace with this exact schema:
        {{
            "anchor_concept": "The canonical name for this merged concept",
            "artifact_type": "core_concept",
            "status": "active",
            "summary_trace": "The newly synthesized, comprehensive summary combining both",
            "chronological_marker": "Any combined or most recent version markers",
            "relations": []
        }}
        """

        try:
            resp = await safe_acompletion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            out = resp.choices[0].message.content
            cleaned = out.strip()
            if cleaned.startswith("```json"): cleaned = cleaned[7:]
            if cleaned.endswith("```"): cleaned = cleaned[:-3]
            mega_trace = json.loads(cleaned.strip())
            
            new_trace_id = str(uuid.uuid4())
            
            # Upsert the new Mega-Trace
            db.upsert_trace(
                trace_id=new_trace_id,
                project_id=target_project_id,
                block_id=target_block_id,
                anchor_concept=mega_trace.get('anchor_concept', 'Unknown'),
                artifact_type=mega_trace.get('artifact_type', 'informational'),
                status=mega_trace.get('status', 'active'),
                summary_trace=mega_trace.get('summary_trace', ''),
                chronological_marker=mega_trace.get('chronological_marker'),
                raw_source_text=f"MERGED FROM {len(source_traces)} source traces and {len(target_traces)} target traces."
            )
            
        except Exception as e:
            print(f"Error in Synaptic Pruning: {e}")
            for t in source_traces:
                self._copy_traces_to_target([t], target_project_id, target_block_id, "")

merging_engine = MergingEngine()
