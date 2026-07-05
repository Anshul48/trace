import json
import litellm
from trace.core.schemas import Event, DocumentChunkedPayload, TraceExtractedPayload, RollingStateBuffer, LLMCallPayload
from trace.events.bus import event_bus

class MicroExtractor:
    def __init__(self, model_name: str = "deepseek/deepseek-chat"):
        # For litellm, deepseek/deepseek-chat can be used for deepseek-v4 flash/pro
        self.model_name = model_name
        self.state = RollingStateBuffer()

    async def handle_document_chunked(self, event: Event):
        if event.name != "DocumentChunked":
            return
        
        payload: DocumentChunkedPayload = event.payload
        
        prompt = f"""
        System: You are an episodic memory engine extracting a knowledge graph. Process the current text chunk sequentially.
        
        Historical Context State: {self.state.model_dump_json()}
        
        Current Text Chunk (File: {payload.meta.filename}, Index: {payload.meta.chunk_index}):
        \"\"\"{payload.chunk_text}\"\"\"
        
        CRITICAL INSTRUCTIONS:
        1. Identify State Transitions: If an item in the active_hypotheses list is abandoned, output status='rejected'.
        2. Minimize Redundancy: Extract only concepts that shape the project's architecture, dependencies, or history.
        3. Link Graph Vertices: Ensure relations use clean naming for target_concept.
        4. You MUST output a SINGLE valid JSON object conforming exactly to this JSON schema:
        {json.dumps(TraceExtractedPayload.model_json_schema(), indent=2)}
        """
        
        try:
            from tenacity import retry, stop_after_attempt, wait_exponential
            import asyncio
            
            litellm.suppress_debug_info = True
            
            @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
            async def _call_llm():
                # Ensure provider prefix for litellm if missing
                model_to_use = self.model_name
                if "gemini" in model_to_use.lower() and "/" not in model_to_use:
                    model_to_use = f"gemini/{model_to_use}"
                elif "deepseek" in model_to_use.lower() and "/" not in model_to_use:
                    model_to_use = f"deepseek/{model_to_use}"
                    
                messages = [{"role": "user", "content": prompt}]
                print(f"Calling LLM ({model_to_use}) for chunk {payload.meta.chunk_index} of {payload.meta.filename}...")
                resp = await litellm.acompletion(
                    model=model_to_use,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.3
                )
                return resp
                
            response = await _call_llm()
            await asyncio.sleep(0.5) # Prevent rate limits
            
            content = response.choices[0].message.content
            
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
            
            # Clean up markdown code blocks if the LLM wrapped the JSON
            cleaned_content = content.strip()
            if cleaned_content.startswith("```json"):
                cleaned_content = cleaned_content[7:]
            elif cleaned_content.startswith("```"):
                cleaned_content = cleaned_content[3:]
            if cleaned_content.endswith("```"):
                cleaned_content = cleaned_content[:-3]
            cleaned_content = cleaned_content.strip()
            
            extracted: TraceExtractedPayload = TraceExtractedPayload.model_validate_json(cleaned_content)
            
            extracted.project_id = payload.project_id
            extracted.trace.source_meta = payload.meta
            extracted.trace.raw_source_text = payload.chunk_text
            
            from trace.core.db import db
            block_id = payload.meta.block_id if payload.meta else ""
            db.upsert_trace(extracted.trace.trace_id, payload.project_id, block_id, extracted.trace.anchor_concept, extracted.trace.model_dump_json())

            self.state = extracted.updated_state
            
            # Publish event
            await event_bus.publish(Event(
                name="TraceExtracted",
                payload=extracted
            ))
            print(f"Extracted trace: {extracted.trace.anchor_concept} from {payload.meta.filename}")
            
        except Exception as e:
            # cleanly display the actual error rather than tenacity RetryError wrapping it
            print(f"Error in MicroExtractor processing {payload.meta.filename}:\n{type(e).__name__}: {str(e)}")

# Global instance initialization
import os
micro_extractor = MicroExtractor(model_name=os.environ.get("PLANNER_MODEL", "gemini/gemini-3.1-flash-lite"))
event_bus.subscribe("DocumentChunked", micro_extractor.handle_document_chunked)
