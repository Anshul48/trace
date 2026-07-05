import litellm
from typing import List
from trace.core.schemas import CanonicalEntity

class WriterAgent:
    def __init__(self, model_name: str = None):
        import os
        self.model_name = model_name or os.environ.get("WRITER_MODEL", "gemini/gemma-4-31b-it")
        
    async def generate_document(self, entity: CanonicalEntity, project_id: str = "") -> str:
        prompt = f"""
System: You are an expert technical editor. Your job is to compile raw architectural notes into a highly cohesive, fluent Markdown document for the module: {entity.canonical_name}.

CRITICAL RULES:
1. LOSSLESS WEAVING: Maintain the technical grit, constraints, and exact rationale. Do not hallucinate. Do not act as an author; act as an editor stitching blocks together.
2. ANCHOR INJECTION: You MUST wrap the compiled text for each trace block in exact HTML comments containing the trace ID, like so:
   <!-- trace_id: the-trace-id-here -->
   Your cohesive paragraph here.
   <!-- end_trace_id -->
3. Do not add conversational fluff (e.g., "Here is the document..."). Output ONLY the compiled markdown.

Here are the raw traces and their source texts for this module:
"""
        
        for trace in entity.traces:
            prompt += f"\n--- TRACE: {trace.trace_id} ---\n"
            prompt += f"Raw Source Context:\n{trace.raw_source_text}\n"
            prompt += f"Extracted Anchor: {trace.anchor_concept}\n"
            prompt += f"Extracted Status: {trace.status}\n"
            prompt += f"----------------------\n"
            
        max_retries = 3
        timeout_duration = 60
        
        for attempt in range(max_retries):
            try:
                print(f"WriterAgent: Generating content for {entity.canonical_name} (Attempt {attempt+1}/{max_retries}, timeout={timeout_duration}s)...")
                try:
                    response = await litellm.acompletion(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        timeout=timeout_duration
                    )
                except Exception as api_err:
                    print(f"Primary model {self.model_name} failed: {api_err}. Falling back to gemini/gemini-3.1-flash-lite.")
                    response = await litellm.acompletion(
                        model="gemini/gemini-3.1-flash-lite",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        timeout=timeout_duration
                    )
                output_content = response.choices[0].message.content
                
                # Emit LLMCall Event
                from trace.core.schemas import LLMCallPayload
                from trace.events.bus import event_bus, Event
                import asyncio
                
                await event_bus.publish(Event(
                    name="LLMCall",
                    payload=LLMCallPayload(
                        project_id=project_id,
                        agent_name="WriterAgent",
                        model_name=self.model_name,
                        prompt=prompt,
                        response=output_content
                    )
                ))
                
                # Since we are inside an async method, we can await event_bus.publish, but event_bus might not be imported at the top.
                # I will import it at the top of the file to avoid circular issues, or just here.
                # Actually, event_bus is safe to import.
                # Let's emit the event.
                # The payload can be a dictionary for simplicity or a custom schema. A simple dict is fine.
                payload = {"entity_id": entity.id, "name": entity.canonical_name, "content": output_content}
                
                # We need to await it, but we can just use asyncio.create_task if we don't want to block, or just await it.
                await event_bus.publish(Event(name="DocumentWritten", payload=payload))
                
                print(f"\n--- Generated Content for {entity.canonical_name} ---\n{output_content}\n---------------------------------------\n")
                return output_content
            except Exception as e:
                print(f"WriterAgent Attempt {attempt+1}/{max_retries} Failed on {entity.canonical_name}: {e}")
                if attempt == max_retries - 1:
                    return f"# {entity.canonical_name}\n\n*Error generating content for this module after {max_retries} attempts.*"

writer_agent = WriterAgent()
