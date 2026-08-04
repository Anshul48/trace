import json
import litellm
from trace.core.schemas import Event, DocumentChunkedPayload, TraceExtractedPayload, RollingStateBuffer, LLMCallPayload
from trace.events.bus import event_bus
from trace.agents.utils import safe_acompletion

class MicroExtractor:
    def __init__(self, model_name: str = "deepseek/deepseek-chat"):
        # For litellm, deepseek/deepseek-chat can be used for deepseek-v4 flash/pro
        self.model_name = model_name
        self.states = {}
        self.semaphore = None

    async def handle_document_chunked(self, event: Event):
        if event.name != "DocumentChunked":
            return
        
        payload: DocumentChunkedPayload = event.payload
        
        thread_id = getattr(payload, "thread_id", "default")
        state_key = f"{payload.project_id}_{thread_id}"
        if state_key not in self.states:
            self.states[state_key] = RollingStateBuffer()
        current_state = self.states[state_key]
        
        chronological_heuristic = ""
        if getattr(payload, "is_chronological", False):
            chronological_heuristic = "\n        5. Chronological Order: These chunks are provided in strict chronological order. Later chunks represent newer architectural states. If a concept in the current chunk contradicts the Historical Context State, assume the current chunk supersedes the old state."
            
        # Minify state for LLM
        llm_state = {
            "active_version": current_state.active_version,
            "active_hypotheses": [h for h, energy in current_state.active_hypotheses.items() if energy > 0]
        }

        prompt = f"""
        System: You are an episodic memory engine extracting a knowledge graph. Process the current text chunk sequentially.
        
        Historical Context State: {json.dumps(llm_state)}
        
        Current Text Chunk (File: {payload.meta.filename}, Index: {payload.meta.chunk_index}):
        \"\"\"{payload.chunk_text}\"\"\"
        
        CRITICAL INSTRUCTIONS:
        1. Identify State Transitions: If an item in the active_hypotheses list is abandoned, omit it.
        2. Minimize Redundancy: Extract only concepts that shape the project's architecture, dependencies, or history.
        3. Link Graph Vertices: Ensure relations use clean naming for target_concept.
        4. If the chunk contains only conversational fluff and no architectural concepts, set "trace" to null.
        5. Output a JSON object exactly matching this structure:
        {{
          "project_id": "string",
          "trace": {{
            "anchor_concept": "string",
            "artifact_type": "core_concept | technical_idea | architecture_decision",
            "status": "active | rejected",
            "summary_trace": "string",
            "relations": [{{"target_concept": "string", "relation_type": "depends_on | supersedes | implements"}}]
          }},
          "updated_state": {{
            "active_version": "string",
            "active_hypotheses": ["string"]
          }}
        }}{chronological_heuristic}
        """
        
        if self.semaphore is None:
            import asyncio
            self.semaphore = asyncio.Semaphore(100)
            
        async with self.semaphore:
            try:
                from tenacity import retry, stop_after_attempt, wait_exponential
                import asyncio
                from pydantic import ValidationError
                
                litellm.suppress_debug_info = True
                
                messages = [{"role": "user", "content": prompt}]
                
                @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
                async def _call_llm_and_parse():
                    # Ensure provider prefix for litellm if missing
                    model_to_use = self.model_name
                    if "gemini" in model_to_use.lower() and "/" not in model_to_use:
                        model_to_use = f"gemini/{model_to_use}"
                    elif "deepseek" in model_to_use.lower() and "/" not in model_to_use:
                        model_to_use = f"deepseek/{model_to_use}"
                        
                    print(f"Calling LLM ({model_to_use}) for chunk {payload.meta.chunk_index} of {payload.meta.filename}...")
                    resp = await safe_acompletion(
                        model=model_to_use,
                        messages=messages,
                        response_format={"type": "json_object"},
                        temperature=0.3
                    )
                    content = resp.choices[0].message.content
                    
                    # Clean up markdown code blocks if the LLM wrapped the JSON
                    cleaned_content = content.strip()
                    if cleaned_content.startswith("```json"):
                        cleaned_content = cleaned_content[7:]
                    elif cleaned_content.startswith("```"):
                        cleaned_content = cleaned_content[3:]
                    if cleaned_content.endswith("```"):
                        cleaned_content = cleaned_content[:-3]
                    cleaned_content = cleaned_content.strip()
                    
                    try:
                        extracted = TraceExtractedPayload.model_validate_json(cleaned_content)
                        return extracted, content
                    except (ValidationError, json.JSONDecodeError) as e:
                        print(f"Validation error in chunk {payload.meta.chunk_index}, retrying... Error: {e}")
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": f"The previous output failed validation with error:\n{e}\nPlease correct the JSON and ensure it strictly conforms to the schema."})
                        raise e
                    
                extracted, content = await _call_llm_and_parse()
                await asyncio.sleep(0.5) # Prevent rate limits
                
                # Apply Hebbian Decay
                new_hypotheses = {}
                for h, energy in current_state.active_hypotheses.items():
                    new_energy = energy - 0.2
                    if new_energy > 0:
                        new_hypotheses[h] = new_energy
                        
                if extracted.updated_state and extracted.updated_state.active_hypotheses:
                    for h in extracted.updated_state.active_hypotheses:
                        new_hypotheses[h] = 1.0
                        
                current_state.active_version = extracted.updated_state.active_version
                current_state.active_hypotheses = new_hypotheses
                self.states[state_key] = current_state
                
                # Emit LLMCall Event
                model_to_use = self.model_name
                if "gemini" in model_to_use.lower() and "/" not in model_to_use:
                    model_to_use = f"gemini/{model_to_use}"
                elif "deepseek" in model_to_use.lower() and "/" not in model_to_use:
                    model_to_use = f"deepseek/{model_to_use}"
                    
                await event_bus.publish(Event(
                    name="LLMCall",
                    payload=LLMCallPayload(
                        project_id=payload.project_id,
                        agent_name="MicroExtractor",
                        model_name=model_to_use,
                        prompt=prompt,
                        response=content
                    )
                ))
                
                if extracted.trace:
                    extracted.project_id = payload.project_id
                    extracted.trace.source_meta = payload.meta
                    extracted.trace.raw_source_text = payload.chunk_text
                    
                    from trace.core.db import db
                    block_id = payload.meta.block_id if payload.meta else ""
                    db.upsert_trace(
                        trace_id=extracted.trace.trace_id,
                        project_id=payload.project_id,
                        block_id=block_id,
                        anchor_concept=extracted.trace.anchor_concept,
                        artifact_type=extracted.trace.artifact_type,
                        status=extracted.trace.status,
                        summary_trace=extracted.trace.summary_trace,
                        chronological_marker=extracted.trace.chronological_marker,
                        raw_source_text=extracted.trace.raw_source_text,
                        metadata=extracted.trace.model_dump_json()
                    )
                    print(f"Extracted trace: {extracted.trace.anchor_concept} from {payload.meta.filename}")
    
                # Publish event
                await event_bus.publish(Event(
                    name="TraceExtracted",
                    payload=extracted
                ))

                
            except Exception as e:
                # cleanly display the actual error rather than tenacity RetryError wrapping it
                print(f"Error in MicroExtractor processing {payload.meta.filename}:\n{type(e).__name__}: {str(e)}")

# Global instance initialization
import os
micro_extractor = MicroExtractor(model_name=os.environ.get("PLANNER_MODEL", "gemini/gemini-3.1-flash-lite"))
event_bus.subscribe("DocumentChunked", micro_extractor.handle_document_chunked)
