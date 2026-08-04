import litellm
from typing import List
from trace.core.schemas import Event, GraphResolvedPayload, TocGeneratedPayload, LLMCallPayload, CanonicalEntity, GraphEdge
from trace.core.serializer.markdown_weaver import MarkdownWeaver
from trace.events.bus import event_bus
from trace.agents.utils import safe_acompletion
import json
import re

class MacroSynthesizer:
    def __init__(self, model_name: str = "deepseek/deepseek-chat"):
        self.model_name = model_name
        self.weaver = MarkdownWeaver()

    async def handle_graph_resolved(self, event: Event):
        if event.name != "GraphResolved":
            return
        
        payload: GraphResolvedPayload = event.payload
        entities = payload.entities
        edges = payload.edges
        
        model_to_use = self.model_name
        if "gemini" in model_to_use.lower() and "/" not in model_to_use:
            model_to_use = f"gemini/{model_to_use}"
        elif "deepseek" in model_to_use.lower() and "/" not in model_to_use:
            model_to_use = f"deepseek/{model_to_use}"
            
        from tenacity import retry, stop_after_attempt, wait_exponential
        
        @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
        async def _call_llm(p, expect_json=False, agent_name=""):
            kwargs = {
                "model": model_to_use,
                "messages": [{"role": "user", "content": p}],
                "temperature": 0.2
            }
            if expect_json:
                kwargs["response_format"] = {"type": "json_object"}
                resp = await safe_acompletion(**kwargs)
            else:
                resp = await safe_acompletion(**kwargs)
                
            out = resp.choices[0].message.content
            await event_bus.publish(Event(
                name="LLMCall",
                payload=LLMCallPayload(
                    project_id=payload.project_id,
                    agent_name=agent_name,
                    model_name=model_to_use,
                    prompt=p,
                    response=out
                )
            ))
            return out

        try:
            # STEP 1: Gist Perception Meta-Step
            import networkx as nx
            G = nx.DiGraph()
            for e in entities:
                G.add_node(e.id, entity=e)
            for edge in edges:
                G.add_edge(edge.source_id, edge.target_id)
                
            if len(G.nodes) > 0:
                pagerank = nx.pagerank(G, alpha=0.85, max_iter=100)
                sorted_nodes = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)
                top_20_ids = [n[0] for n in sorted_nodes[:20]]
            else:
                top_20_ids = [e.id for e in entities[:20]]
                
            top_20_entities = [e for e in entities if e.id in top_20_ids]
            
            prompt_gist = "Here are the 20 most central architectural traces from an unknown codebase. Read them and output a 2-paragraph 'Gist Summary' that defines EXACTLY what this project is, its primary domain, its core technologies, and its overarching purpose. Do not list the traces; synthesize the soul of the project.\n\n"
            for e in top_20_entities:
                prompt_gist += f"- {e.canonical_name}\n"
                if e.traces and len(e.traces) > 0:
                    prompt_gist += f"  Summary: {e.traces[0].summary_trace}\n"
                    
            gist = await _call_llm(prompt_gist, agent_name="MacroSynthesizer (Gist Perception)")
            
            # STEP 2: Top-Down Prediction (Prior TOC)
            prompt_prior = f"""You are an expert Principal Engineer. We are architecting a system described as follows: 
{gist}

Based on this specific domain, predict the perfect, highly logical Table of Contents (TOC) for the system design document. Define the top-level Parts and Chapters.
Output ONLY a JSON object with this exact structure:
{{
    "parts": [
        {{
            "name": "Part 1: Name",
            "chapters": [
                {{ "title": "Chapter 1: Name", "synopsis": "This chapter covers..." }}
            ]
        }}
    ]
}}"""
            
            prior_json_str = await _call_llm(prompt_prior, expect_json=True, agent_name="MacroSynthesizer (Top-Down Prior)")
            cleaned_prior = prior_json_str.strip()
            if cleaned_prior.startswith("```json"): cleaned_prior = cleaned_prior[7:]
            if cleaned_prior.endswith("```"): cleaned_prior = cleaned_prior[:-3]
            prior_toc = json.loads(cleaned_prior.strip())
            
            # STEP 3: Hierarchical Predictive Processing (2-Pass RLM)
            batch_size = 50
            predicted_toc_state = prior_toc
            entity_parts = {}
            entity_chapters = {}
            
            # Pass 1: Gist Router (Bucket entities into Parts)
            part_names = [p.get("name") for p in predicted_toc_state.get("parts", [])]
            for i in range(0, len(entities), batch_size):
                batch = entities[i:i+batch_size]
                prompt_router = f"Here are the Top-Level Parts of our architecture:\n{json.dumps(part_names, indent=2)}\n\nRoute each of the following Traces into the most appropriate Part Bucket. Output ONLY a JSON array of objects with 'entity' and 'part' keys:\n"
                for e in batch:
                    prompt_router += f"- {e.canonical_name}\n"
                
                router_resp = await _call_llm(prompt_router, expect_json=True, agent_name=f"MacroSynthesizer (Gist Router Batch {i//batch_size + 1})")
                try:
                    cleaned_router = router_resp.strip()
                    if cleaned_router.startswith("```json"): cleaned_router = cleaned_router[7:]
                    if cleaned_router.endswith("```"): cleaned_router = cleaned_router[:-3]
                    
                    routed_data = json.loads(cleaned_router.strip())
                    if isinstance(routed_data, dict) and "mappings" in routed_data:
                        routed_data = routed_data["mappings"]
                        
                    for mapping in routed_data:
                        if isinstance(mapping, dict):
                            e_name = mapping.get("entity")
                            part_name = mapping.get("part")
                            if e_name and part_name:
                                entity_parts[e_name] = part_name
                except Exception as e:
                    print(f"Error parsing Gist Router batch: {e}")

            # Pass 2: Local Active Inference
            part_to_entities = {}
            for e in entities:
                part_name = entity_parts.get(e.canonical_name, "Uncategorized")
                if part_name not in part_to_entities:
                    part_to_entities[part_name] = []
                part_to_entities[part_name].append(e)
                
            for part_index, part in enumerate(predicted_toc_state.get("parts", [])):
                part_name = part.get("name")
                part_entities = part_to_entities.get(part_name, [])
                if not part_entities: continue
                
                for i in range(0, len(part_entities), batch_size):
                    batch = part_entities[i:i+batch_size]
                    prompt_rlm = f"Here is the Local Prior (TOC for {part_name}):\n{json.dumps(part, indent=2)}\n\n"
                    prompt_rlm += "Map each Trace to the appropriate Chapter. If it represents a major component but doesn't fit, create a new chapter in this Part.\n"
                    prompt_rlm += "Output ONLY a JSON object:\n"
                    prompt_rlm += '{"mappings": [{"entity": "Entity Name", "chapter": "Chapter Name"}], "new_chapters_created": [{"title": "Chapter Name", "synopsis": "Synopsis"}]}\n\n'
                    prompt_rlm += "Traces:\n"
                    for e in batch:
                        prompt_rlm += f"- {e.canonical_name}\n"
                        
                    rlm_resp = await _call_llm(prompt_rlm, expect_json=True, agent_name=f"MacroSynthesizer (Local Active Inference {part_name})")
                    try:
                        cleaned_rlm = rlm_resp.strip()
                        if cleaned_rlm.startswith("```json"): cleaned_rlm = cleaned_rlm[7:]
                        if cleaned_rlm.endswith("```"): cleaned_rlm = cleaned_rlm[:-3]
                        
                        rlm_data = json.loads(cleaned_rlm.strip())
                        for mapping in rlm_data.get("mappings", []):
                            e_name = mapping.get("entity")
                            chap_name = mapping.get("chapter")
                            if e_name:
                                entity_chapters[e_name] = chap_name
                                
                        new_chaps = rlm_data.get("new_chapters_created", [])
                        if new_chaps:
                            if "chapters" not in predicted_toc_state["parts"][part_index]:
                                predicted_toc_state["parts"][part_index]["chapters"] = []
                            predicted_toc_state["parts"][part_index]["chapters"].extend(new_chaps)
                    except Exception as e:
                        print(f"Error parsing Local Active Inference batch: {e}")
                    
            # STEP 4: Actor-Critic Polish
            prompt_critic = f"""You are the Chief Architect reviewing a Draft TOC.
Draft TOC:
{json.dumps(predicted_toc_state, indent=2)}

High Salience Traces (Top 20 most central concepts):
{[e.canonical_name for e in top_20_entities]}

Are there any Chapters that overlap and should be merged? Did we forget to include any High Salience Traces?
Output ONLY a JSON object of the Final polished TOC using the same structure:
{{
    "parts": [
        {{
            "name": "Part Name",
            "chapters": [
                {{ "title": "Chapter Name", "synopsis": "Synopsis" }}
            ]
        }}
    ]
}}"""
            
            critic_resp = await _call_llm(prompt_critic, expect_json=True, agent_name="MacroSynthesizer (Actor-Critic)")
            cleaned_critic = critic_resp.strip()
            if cleaned_critic.startswith("```json"): cleaned_critic = cleaned_critic[7:]
            if cleaned_critic.endswith("```"): cleaned_critic = cleaned_critic[:-3]
            
            final_toc = json.loads(cleaned_critic.strip())
            
            # Assemble global_toc string and part_guidance
            global_toc_lines = ["# Project Architecture TOC\n"]
            part_guidance = {}
            
            for part in final_toc.get("parts", []):
                part_name = part.get("name", "Unknown Part")
                global_toc_lines.append(f"## {part_name}")
                
                guidance = f"Guidelines for {part_name}:\n"
                
                for chap in part.get("chapters", []):
                    chap_name = chap.get("title", "Unknown Chapter")
                    synopsis = chap.get("synopsis", "")
                    
                    global_toc_lines.append(f"### {chap_name}")
                    global_toc_lines.append(f"_{synopsis}_\n")
                    guidance += f"- {chap_name}: {synopsis}\n"
                    
                    mapped_entities = []
                    for e_name, c_name in entity_chapters.items():
                        if c_name == chap_name:
                            mapped_entities.append(e_name)
                            
                    for t in mapped_entities:
                        global_toc_lines.append(f"* [[{t}]]")
                    global_toc_lines.append("")
                    
                part_guidance[part_name] = guidance
                
            mapped_set = set(entity_chapters.keys())
            unmapped = [e.canonical_name for e in entities if e.canonical_name not in mapped_set]
            if unmapped:
                global_toc_lines.append("## Uncategorized\n")
                for t in unmapped:
                    global_toc_lines.append(f"* [[{t}]]")
                    
            global_toc = "\n".join(global_toc_lines)
            
            from trace.core.db import db
            db.save_toc(payload.project_id, global_toc)
            
            toc_payload = TocGeneratedPayload(
                project_id=payload.project_id,
                global_toc=global_toc,
                entities=payload.entities,
                edges=payload.edges,
                part_guidance=part_guidance,
                entity_parts=entity_parts
            )
            await event_bus.publish(Event(name="TocGenerated", payload=toc_payload))
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error in MacroSynthesizer: {e}")
            await event_bus.publish(Event(name="PipelineError", payload=f"MacroSynthesizer failed to generate TOC: {e}"))

    async def generate_insight_report(self, project_id: str, goal: str, high_scoring_trace_ids: List[str]) -> str:
        from trace.core.db import db
        import os
        
        # Fetch the relevant traces
        traces = []
        for trace_id in high_scoring_trace_ids:
            # We don't have get_trace by id, we can just filter all traces
            pass
            
        all_traces = db.get_traces_by_project(project_id)
        for t in all_traces:
            if t['trace_id'] in high_scoring_trace_ids:
                traces.append(t)
                
        if not traces:
            return "No traces found to generate insights."
            
        context_block = ""
        for t in traces:
            context_block += f"- Concept: {t.get('anchor_concept', 'Unknown')}\n"
            context_block += f"  Source: {t.get('raw_source_text', '')[:500]}...\n"
            context_block += f"  Summary: {t.get('summary_trace', '')}\n\n"
            
        prompt = f"""You are an autonomous research agent. Based on the user's generalized goal:
GOAL: {goal}

And the following highly salient memory traces retrieved from the knowledge graph:
{context_block}

Synthesize a comprehensive 'Insight Report' that answers the goal. Point out connections and architectural implications.
Use markdown formatting."""

        model_to_use = self.model_name
        if "gemini" in model_to_use.lower() and "/" not in model_to_use:
            model_to_use = f"gemini/{model_to_use}"
        elif "deepseek" in model_to_use.lower() and "/" not in model_to_use:
            model_to_use = f"deepseek/{model_to_use}"
            
        from tenacity import retry, stop_after_attempt, wait_exponential
        
        @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
        async def _call_llm():
            return await safe_acompletion(
                model=model_to_use,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            
        try:
            resp = await _call_llm()
            out = resp.choices[0].message.content
            
            # Save the report
            output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "repo_out", project_id)
            os.makedirs(output_dir, exist_ok=True)
            
            # Create a safe filename from the goal
            safe_goal = "".join([c if c.isalnum() else "_" for c in goal[:30]])
            filepath = os.path.join(output_dir, f"Insights_on_{safe_goal}.md")
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(out)
                
            await event_bus.publish(Event(
                name="LLMCall",
                payload=LLMCallPayload(
                    project_id=project_id,
                    agent_name="MacroSynthesizer (Insight Report)",
                    model_name=model_to_use,
                    prompt=prompt,
                    response=out
                )
            ))
            return out
        except Exception as e:
            print(f"Error generating insight report: {e}")
            return ""

    async def revise_toc(self, chat_history: list, entities: list, edges: list) -> str:
        # Build system prompt with the graph context
        system_prompt = "System: You are the Chief Architect refining a Markdown Table of Contents (TOC) for the repository based on user feedback.\n"
        system_prompt += "\nOutput ONLY the revised markdown structure for the TOC. Do not add conversational fluff. Retain the detailed chapter synopses if possible."
        
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
                return await safe_acompletion(
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
                    project_id="revise", # Dummy or find from context if possible
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
