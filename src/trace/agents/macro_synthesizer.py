import litellm
from trace.core.schemas import Event, GraphResolvedPayload, TocGeneratedPayload, LLMCallPayload
from trace.core.serializer.markdown_weaver import MarkdownWeaver
from trace.events.bus import event_bus

class MacroSynthesizer:
    def __init__(self, model_name: str = "deepseek/deepseek-chat"):
        self.model_name = model_name
        self.weaver = MarkdownWeaver()

    async def handle_graph_resolved(self, event: Event):
        if event.name != "GraphResolved":
            return
        
        payload: GraphResolvedPayload = event.payload
        
        # Prepare a concise summary of the graph to feed to the LLM
        graph_summary = "Entities:\n"
        for ent in payload.entities:
            graph_summary += f"- {ent.canonical_name} (Status: {ent.status})\n"
            
        graph_summary += "\nEdges:\n"
        entities = payload.entities
        edges = payload.edges
        
        # Build prompt for TOC generation
        prompt = f"""
        System: You are the Chief Architect. You are given a resolved knowledge graph containing all technical entities, concepts, and versions of the project.
        
        Your task is to generate a strict Markdown Table of Contents (TOC) that will serve as the README for the repository.
        Organize the TOC logically (e.g., Global Context, Core Modules, Rejected Concepts).
        DO NOT write a long narrative summary. Output ONLY the markdown structure.
        
        Graph Entities:
        """
        for entity in entities:
            prompt += f"- {entity.canonical_name} (Type: {entity.traces[0].artifact_type if entity.traces else 'unknown'}, Status: {entity.status})\n"
            
        # Ensure provider prefix
        model_to_use = self.model_name
        if "gemini" in model_to_use.lower() and "/" not in model_to_use:
            model_to_use = f"gemini/{model_to_use}"
        elif "deepseek" in model_to_use.lower() and "/" not in model_to_use:
            model_to_use = f"deepseek/{model_to_use}"
            
        from tenacity import retry, stop_after_attempt, wait_exponential
        import asyncio
        
        try:
            @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
            async def _call_llm():
                return await litellm.acompletion(
                    model=model_to_use,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )
                
            response = await _call_llm()
            
            global_toc = response.choices[0].message.content
            
            await event_bus.publish(Event(
                name="LLMCall",
                payload=LLMCallPayload(
                    project_id=payload.project_id,
                    agent_name="MacroSynthesizer (TOC Gen)",
                    model_name=model_to_use,
                    prompt=prompt,
                    response=global_toc
                )
            ))
            
            
            print(f"\n--- Planner Agent TOC Generated ---\n{global_toc}\n-----------------------------------\n")
            
            # Save TOC to DB automatically
            from trace.core.db import db
            db.save_toc(payload.project_id, global_toc)
            
            # Emit TocGenerated instead of immediately weaving
            toc_payload = TocGeneratedPayload(
                project_id=payload.project_id,
                global_toc=global_toc,
                entities=event.payload.entities,
                edges=event.payload.edges
            )
            await event_bus.publish(Event(name="TocGenerated", payload=toc_payload))
        except Exception as e:
            print(f"Error in MacroSynthesizer: {e}")
            await event_bus.publish(Event(name="PipelineError", payload=f"MacroSynthesizer failed to generate TOC: {e}"))

    async def revise_toc(self, chat_history: list, entities: list, edges: list) -> str:
        # Build system prompt with the graph context
        system_prompt = "System: You are the Chief Architect refining a Markdown Table of Contents (TOC) for the repository based on user feedback.\n\nGraph Entities:\n"
        for entity in entities:
            system_prompt += f"- {entity.canonical_name} (Status: {entity.status})\n"
            
        system_prompt += "\nOutput ONLY the revised markdown structure for the TOC. Do not add conversational fluff."
        
        # Prepare messages
        messages = [{"role": "system", "content": system_prompt}]
        for msg in chat_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
            
        # Ensure provider prefix
        model_to_use = self.model_name
        if "gemini" in model_to_use.lower() and "/" not in model_to_use:
            model_to_use = f"gemini/{model_to_use}"
        elif "deepseek" in model_to_use.lower() and "/" not in model_to_use:
            model_to_use = f"deepseek/{model_to_use}"
            
        print(f"Planner Agent: Revising TOC based on chat feedback using {model_to_use}...")
        
        try:
            from tenacity import retry, stop_after_attempt, wait_exponential
            import asyncio
            
            @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
            async def _call_llm():
                return await litellm.acompletion(
                    model=model_to_use,
                    messages=messages,
                    temperature=0.2
                )
                
            response = await _call_llm()
            output = response.choices[0].message.content
            
            import json
            await event_bus.publish(Event(
                name="LLMCall",
                payload=LLMCallPayload(
                    agent_name="MacroSynthesizer (TOC Revision)",
                    model_name=model_to_use,
                    prompt=json.dumps(messages, indent=2),
                    response=output
                )
            ))
            
            return output
        except Exception as e:
            print(f"Error revising TOC: {e}")
            return chat_history[-1]["content"] if chat_history else "Error generating TOC."

# Global instance initialization
import os
macro_synthesizer = MacroSynthesizer(model_name=os.environ.get("PLANNER_MODEL", "gemini/gemini-3.1-flash-lite"))
event_bus.subscribe("GraphResolved", macro_synthesizer.handle_graph_resolved)
