import streamlit as st
import os
import tempfile
import asyncio
from pathlib import Path
import sys
import io
import contextlib
import json
from dotenv import load_dotenv

load_dotenv() # Auto-load keys for development convenience

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from trace.events.bus import event_bus, Event
from trace.ingestion.parser import ingest_documents
from trace.agents.micro_extractor import micro_extractor
from trace.agents.macro_synthesizer import macro_synthesizer
from trace.core.graph.builder import graph_builder
from trace.core.serializer.markdown_weaver import MarkdownWeaver
from trace.agents.writer_agent import writer_agent
from trace.core.schemas import RollingStateBuffer, TocGeneratedPayload
from trace.core.db import db

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '.trace_config.json')

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "deepseek_key": "",
        "google_key": "",
        "planner_model": "deepseek/deepseek-chat",
        "writer_model": "gemini/gemma-4-31b-it",
        "processing_mode": "Cloud Hybrid Strategy (Fast Parsing + Cloud API)"
    }

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)

st.set_page_config(layout="wide", page_title="Trace Pipeline Tester")

# Initialize session state
if "pipeline_state" not in st.session_state:
    st.session_state.pipeline_state = "idle" # idle -> review_toc -> finished
if "toc_payload" not in st.session_state:
    st.session_state.toc_payload = None
if "temp_out_dir" not in st.session_state:
    st.session_state.temp_out_dir = None
if "logs" not in st.session_state:
    st.session_state.logs = ""

config = load_config()

st.title("Trace Pipeline Tester (HITL)")
st.markdown("Test the Bi-Directional Knowledge Graph OS with Human-In-The-Loop TOC review.")

with st.sidebar:
    st.header("Configuration")
    deepseek_key = st.text_input("DeepSeek API Key", type="password", value=config.get("deepseek_key") or os.getenv("DEEPSEEK_API_KEY", ""))
    google_key = st.text_input("Google / Gemini API Key", type="password", value=config.get("google_key") or os.getenv("GEMINI_API_KEY", ""))
    
    processing_mode = st.radio(
        "Processing Mode",
        options=[
            "Cloud Hybrid Strategy (Fast Parsing + Cloud API)",
            "Existing Strategy (Heavy Local Parsing + Local LLM)"
        ],
        index=0 if "Cloud" in config.get("processing_mode", "Cloud") else 1
    )
    
    if "Cloud" in processing_mode:
        st.markdown("*Uses `fast` strategy for parsing to save RAM, and assumes you are using a cloud API like Gemma to avoid VRAM overload.*")
    else:
        st.markdown("*Uses heavy CV models for layout parsing, and assumes you are running a local LLM on GPU.*")
    
    planner_model = st.text_input("Planner Model (Extraction/TOC)", value=config.get("planner_model", "deepseek/deepseek-chat"))
    writer_model = st.text_input("Writer Model (Markdown Generation)", value=config.get("writer_model", "gemini/gemma-4-31b-it"))
    
    if st.button("Save Preferences"):
        config.update({
            "deepseek_key": deepseek_key,
            "google_key": google_key,
            "processing_mode": processing_mode,
            "planner_model": planner_model,
            "writer_model": writer_model
        })
        save_config(config)
        st.success("Preferences saved!")

# Custom stdout redirector to update Streamlit UI in real-time
class StreamlitRedirect:
    def __init__(self, st_placeholder):
        self.st_placeholder = st_placeholder
        self.buffer = ""
        
    def write(self, string):
        self.buffer += string
        self.st_placeholder.code(self.buffer, language="text")
        
    def flush(self):
        pass

if st.session_state.pipeline_state == "idle":
    raw_text = st.text_area("Paste Raw Document Text", height=300)

    if st.button("Run Pipeline"):
        if not raw_text.strip():
            st.warning("Please enter some text to process.")
        elif not deepseek_key and not google_key:
            st.warning("Please provide an API key in the sidebar.")
        else:
            st.markdown("### Live Pipeline Execution")
            col_logs, col_llm, col_traces, col_toc = st.columns(4)
            with col_logs:
                st.markdown("**System Logs**")
                log_placeholder = st.empty()
            with col_llm:
                st.markdown("**LLM Inspector**")
                llm_placeholder = st.empty()
            with col_traces:
                st.markdown("**Extracted Traces**")
                trace_placeholder = st.empty()
            with col_toc:
                st.markdown("**Planner (TOC)**")
                toc_placeholder = st.empty()
            
            
            if deepseek_key:
                os.environ["DEEPSEEK_API_KEY"] = deepseek_key
            if google_key:
                os.environ["GEMINI_API_KEY"] = google_key
                os.environ["GOOGLE_API_KEY"] = google_key
            
            # Save config implicitly on run
            config.update({
                "deepseek_key": deepseek_key,
                "google_key": google_key,
                "processing_mode": processing_mode,
                "planner_model": planner_model,
                "writer_model": writer_model
            })
            save_config(config)
            
            micro_extractor.model_name = planner_model
            macro_synthesizer.model_name = planner_model
            writer_agent.model_name = writer_model
            micro_extractor.state = RollingStateBuffer()
            graph_builder.traces = []
            db.init_db() # Init SQLite for blocks
            
            temp_out_dir_obj = tempfile.TemporaryDirectory()
            st.session_state.temp_out_dir_obj = temp_out_dir_obj
            st.session_state.temp_out_dir = temp_out_dir_obj.name
            
            macro_synthesizer.weaver = MarkdownWeaver(output_dir=st.session_state.temp_out_dir)
            
            async def run_pipeline_to_toc():
                toc_ready = asyncio.Event()
                
                def on_toc(event: Event):
                    if event.name == "TocGenerated":
                        st.session_state.toc_payload = event.payload
                        toc_placeholder.markdown(event.payload.global_toc)
                        toc_ready.set()
                        
                trace_buffer = []
                def on_trace(event: Event):
                    if event.name == "TraceExtracted":
                        trace = event.payload.trace
                        trace_buffer.append(f"- **{trace.anchor_concept}** ({trace.status})")
                        trace_placeholder.markdown("\n".join(trace_buffer[-15:]))
                        
                llm_html = ""
                def on_llm_call(event: Event):
                    nonlocal llm_html
                    if event.name == "LLMCall":
                        call = event.payload
                        import html
                        
                        safe_prompt = html.escape(str(call.prompt))
                        safe_response = html.escape(str(call.response))
                        
                        block = f"""
                        <details style="border: 1px solid #444; padding: 10px; margin-bottom: 10px; border-radius: 5px; background: #1e1e1e; font-family: monospace;">
                          <summary style="font-weight: bold; cursor: pointer; font-size: 14px; color: #fff;">
                            🤖 <b>{call.agent_name}</b> invoked <span style="color: #4CAF50;">{call.model_name}</span>
                          </summary>
                          <div style="margin-top: 10px; border-top: 1px solid #444; padding-top: 10px;">
                            <p style="color: #2196F3; font-weight: bold; margin-bottom: 5px;">Prompt:</p>
                            <pre style="background: #2d2d2d; color: #d4d4d4; padding: 10px; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-size: 12px; max-height: 300px; overflow-y: auto;">{safe_prompt}</pre>
                            <p style="color: #FF9800; font-weight: bold; margin-bottom: 5px; margin-top: 15px;">Response:</p>
                            <pre style="background: #2d2d2d; color: #d4d4d4; padding: 10px; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-size: 12px; max-height: 300px; overflow-y: auto;">{safe_response}</pre>
                          </div>
                        </details>
                        """
                        llm_html = block + llm_html
                llm_placeholder.markdown(llm_html, unsafe_allow_html=True)
                
                def on_error(event: Event):
                    st.session_state.pipeline_state = "error"
                    st.session_state.error_msg = event.payload
                    
                # Safely remove previous UI callbacks to avoid duplicate appends without disconnecting the backend
                ui_cbs = ["on_toc", "on_trace", "on_llm_call", "on_error"]
                for ev in ["TocGenerated", "TraceExtracted", "LLMCall", "PipelineError"]:
                    event_bus._subscribers[ev] = [cb for cb in event_bus._subscribers.get(ev, []) if getattr(cb, "__name__", "") not in ui_cbs]
                    
                event_bus.subscribe("TocGenerated", on_toc)
                event_bus.subscribe("TraceExtracted", on_trace)
                event_bus.subscribe("LLMCall", on_llm_call)
                event_bus.subscribe("PipelineError", on_error)
                
                with tempfile.TemporaryDirectory() as temp_in_dir:
                    input_file = os.path.join(temp_in_dir, "input.txt")
                    with open(input_file, "w", encoding="utf-8") as f:
                        f.write(raw_text)
                        
                    fast_mode = ("Cloud" in processing_mode)
                    await ingest_documents(temp_in_dir, fast_mode=fast_mode)
                    
                    try:
                        await asyncio.wait_for(toc_ready.wait(), timeout=120.0)
                    except asyncio.TimeoutError:
                        print("Pipeline timed out while waiting for TOC.")

            st_redirect = StreamlitRedirect(log_placeholder)
            
            with contextlib.redirect_stdout(st_redirect), contextlib.redirect_stderr(st_redirect):
                print("Starting Pipeline...")
                print(f"Mode: {processing_mode}")
                print(f"Planner Model: {planner_model}")
            
                try:
                    # Run the ingestion (this fires DocumentChunked events)
                    import asyncio
                    asyncio.run(run_pipeline_to_toc())
                    
                    # Instead of blocking indefinitely, just wait for TOC to be generated
                    while st.session_state.pipeline_state == "idle" and st.session_state.toc_payload is None:
                        import time
                        time.sleep(0.5)
                except Exception as e:
                    st.session_state.pipeline_state = "error"
                    st.session_state.error_msg = str(e)
            
            if st.session_state.toc_payload:
                st.session_state.pipeline_state = "review_toc"
                st.rerun()

elif st.session_state.pipeline_state == "error":
    st.error("Pipeline Failed")
    st.error(st.session_state.get("error_msg", "Unknown error"))
    if st.button("Restart"):
        st.session_state.pipeline_state = "idle"
        st.session_state.toc_payload = None
        st.rerun()

elif st.session_state.pipeline_state == "review_toc":
    st.success("TOC Generated successfully! You can review and discuss it with the Planner before finalizing.")
    
    # Initialize chat history if not present
    if "toc_chat_history" not in st.session_state:
        st.session_state.toc_chat_history = [
            {"role": "assistant", "content": st.session_state.toc_payload.global_toc}
        ]
        
    chat_container = st.container(height=500)
    with chat_container:
        for i, msg in enumerate(st.session_state.toc_chat_history):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
    # Use a column layout for the chat input and the approve button
    col_input, col_action = st.columns([4, 1])
    
    with col_input:
        if prompt := st.chat_input("Suggest changes to the TOC (e.g., 'Combine these two sections')..."):
            st.session_state.toc_chat_history.append({"role": "user", "content": prompt})
            st.rerun()
            
    with col_action:
        if st.button("Approve & Generate Docs", type="primary", use_container_width=True):
            # Finalize TOC
            st.session_state.toc_payload.global_toc = st.session_state.toc_chat_history[-1]["content"]
            st.session_state.pipeline_state = "generating_docs"
            st.rerun()
            
        if st.button("Cancel & Start Over", use_container_width=True):
            st.session_state.pipeline_state = "idle"
            st.rerun()
            
    # Process the last message if it's from the user
    if st.session_state.toc_chat_history[-1]["role"] == "user":
        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner("Revising TOC..."):
                    payload = st.session_state.toc_payload
                    
                    async def async_revise():
                        return await macro_synthesizer.revise_toc(
                            st.session_state.toc_chat_history,
                            payload.entities,
                            payload.edges
                        )
                    
                    revised_toc = asyncio.run(async_revise())
                    st.markdown(revised_toc)
                    st.session_state.toc_chat_history.append({"role": "assistant", "content": revised_toc})
                    st.rerun()

elif st.session_state.pipeline_state == "generating_docs":
    st.markdown("### Live Writer Execution")
    col_writer_logs, col_writer_llm, col_writer_out = st.columns(3)
    with col_writer_logs:
        st.markdown("**System Logs**")
        log_placeholder = st.empty()
    with col_writer_llm:
        st.markdown("**LLM Inspector**")
        llm_placeholder = st.empty()
    with col_writer_out:
        st.markdown("**Writer Output**")
        writer_placeholder = st.empty()
        
    async def finish_pipeline():
        payload = st.session_state.toc_payload
        
        print(f"\n--- Final Elaborated TOC ---\n{payload.global_toc}\n----------------------------\n")
        
        finished = asyncio.Event()
        def on_finish(e):
            if e.name == "PipelineFinished":
                finished.set()
                
        writer_buffer = ""
        def on_document_written(e):
            nonlocal writer_buffer
            if e.name == "DocumentWritten":
                writer_buffer += f"**{e.payload['name']}**\n{e.payload['content'][:200]}...\n\n---\n\n"
                writer_placeholder.markdown(writer_buffer)
                
        llm_html = ""
        def on_llm_call(event: Event):
            nonlocal llm_html
            if event.name == "LLMCall":
                call = event.payload
                import html
                
                safe_prompt = html.escape(str(call.prompt))
                safe_response = html.escape(str(call.response))
                
                block = f"""
                <details style="border: 1px solid #444; padding: 10px; margin-bottom: 10px; border-radius: 5px; background: #1e1e1e; font-family: monospace;">
                  <summary style="font-weight: bold; cursor: pointer; font-size: 14px; color: #fff;">
                    🤖 <b>{call.agent_name}</b> invoked <span style="color: #4CAF50;">{call.model_name}</span>
                  </summary>
                  <div style="margin-top: 10px; border-top: 1px solid #444; padding-top: 10px;">
                    <p style="color: #2196F3; font-weight: bold; margin-bottom: 5px;">Prompt:</p>
                    <pre style="background: #2d2d2d; color: #d4d4d4; padding: 10px; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-size: 12px; max-height: 300px; overflow-y: auto;">{safe_prompt}</pre>
                    <p style="color: #FF9800; font-weight: bold; margin-bottom: 5px; margin-top: 15px;">Response:</p>
                    <pre style="background: #2d2d2d; color: #d4d4d4; padding: 10px; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-size: 12px; max-height: 300px; overflow-y: auto;">{safe_response}</pre>
                  </div>
                </details>
                """
                llm_html = block + llm_html
                llm_placeholder.markdown(llm_html, unsafe_allow_html=True)
                
        def on_error(event: Event):
            st.session_state.pipeline_state = "error"
            st.session_state.error_msg = event.payload
            
        # Safely remove previous UI callbacks
        ui_cbs = ["on_finish", "on_document_written", "on_llm_call", "on_error"]
        for ev in ["PipelineFinished", "DocumentWritten", "LLMCall", "PipelineError"]:
            event_bus._subscribers[ev] = [cb for cb in event_bus._subscribers.get(ev, []) if getattr(cb, "__name__", "") not in ui_cbs]
            
        event_bus.subscribe("PipelineFinished", on_finish)
        event_bus.subscribe("DocumentWritten", on_document_written)
        event_bus.subscribe("LLMCall", on_llm_call)
        event_bus.subscribe("PipelineError", on_error)
        
        await macro_synthesizer.weaver.write_repository(payload.entities, payload.edges, payload.global_toc)
        await event_bus.publish(Event(name="PipelineFinished", payload=None))
        
        await asyncio.wait_for(finished.wait(), timeout=120.0)
        
    st_redirect = StreamlitRedirect(log_placeholder)
    st_redirect.buffer = st.session_state.logs + "\n\nGenerating Markdown files (this may take a moment)...\n"
    
    with contextlib.redirect_stdout(st_redirect), contextlib.redirect_stderr(st_redirect):
        asyncio.run(finish_pipeline())
        
    st.session_state.logs = st_redirect.buffer
    st.session_state.pipeline_state = "finished"
    st.rerun()

elif st.session_state.pipeline_state == "finished":
    st.success("Repository generated successfully!")
    
    st.header("Terminal Output")
    st.code(st.session_state.logs, language="text")
    
    st.header("Generated Repository Files")
    temp_out_dir = st.session_state.temp_out_dir
    if temp_out_dir and os.path.exists(temp_out_dir):
        for root, dirs, files in os.walk(temp_out_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, temp_out_dir)
                
                with st.expander(f"📄 {rel_path}", expanded=(file=="README.md")):
                    with open(file_path, "r", encoding="utf-8") as f:
                        st.markdown(f.read())
                        
    if st.button("Start New Extraction"):
        st.session_state.pipeline_state = "idle"
        st.rerun()
