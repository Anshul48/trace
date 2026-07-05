import asyncio
import os
import sys
import tempfile
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from trace.events.bus import event_bus, Event
from trace.ingestion.parser import ingest_documents
from trace.core.db import db

# Load agents
import trace.agents.micro_extractor
import trace.core.graph.builder
import trace.agents.macro_synthesizer

load_dotenv()
db.init_db()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProjectCreate(BaseModel):
    name: str

@app.post("/api/projects")
async def create_project(req: ProjectCreate):
    import uuid
    project_id = str(uuid.uuid4())
    db.create_project(project_id, req.name)
    return {"id": project_id, "name": req.name, "status": "created"}

@app.get("/api/projects")
async def get_projects():
    return db.get_all_projects()

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    db.delete_project(project_id)
    return {"status": "deleted", "id": project_id}

@app.post("/api/projects/{project_id}/ingest")
async def ingest_project_docs(project_id: str, files: list[UploadFile] = File(...)):
    db.update_project_status(project_id, "extracting")
    
    # Run ingestion in a persistent temporary dir
    temp_in_dir = tempfile.mkdtemp()
    for file in files:
        content = await file.read()
        input_file = os.path.join(temp_in_dir, file.filename)
        with open(input_file, "wb") as f:
            f.write(content)
            
    async def run_ingestion_and_cleanup(directory: str):
        try:
            await ingest_documents(directory, project_id=project_id, fast_mode=True)
        finally:
            import shutil
            shutil.rmtree(directory, ignore_errors=True)

    asyncio.create_task(run_ingestion_and_cleanup(temp_in_dir))
    return {"status": "started", "project_id": project_id}

@app.get("/api/projects/{project_id}/traces")
async def get_project_traces(project_id: str):
    raw_traces = db.get_traces_by_project(project_id)
    # Parse back the JSON metadata to send cleanly to frontend
    import json
    for t in raw_traces:
        if t.get("metadata"):
            t["details"] = json.loads(t["metadata"])
    return raw_traces

@app.post("/api/projects/{project_id}/synthesize")
async def trigger_synthesis(project_id: str):
    db.update_project_status(project_id, "synthesizing")
    await event_bus.publish(Event(name="TriggerGraphBuild", payload={"project_id": project_id}))
    return {"status": "started"}

class TocUpdate(BaseModel):
    toc: str

@app.get("/api/projects/{project_id}/toc")
async def get_project_toc(project_id: str):
    toc = db.get_toc(project_id)
    return {"toc": toc or ""}

@app.put("/api/projects/{project_id}/toc")
async def update_project_toc(project_id: str, req: TocUpdate):
    db.save_toc(project_id, req.toc)
    return {"status": "updated"}

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    chat_history: list[ChatMessage]

@app.post("/api/projects/{project_id}/toc/chat")
async def chat_toc_revision(project_id: str, req: ChatRequest):
    # Retrieve current traces and cluster them (lightweight)
    from trace.core.graph.builder import graph_builder
    raw_traces = db.get_traces_by_project(project_id)
    from trace.core.schemas import HippocampalTrace
    traces = []
    for row in raw_traces:
        if row.get("metadata"):
            try:
                t = HippocampalTrace.model_validate_json(row["metadata"])
                if row.get("user_concept"): t.anchor_concept = row["user_concept"]
                if row.get("user_type"): t.artifact_type = row["user_type"]
                traces.append(t)
            except: pass
    
    entities = graph_builder.clusterer.cluster_traces(traces)
    history = [{"role": msg.role, "content": msg.content} for msg in req.chat_history]
    
    from trace.agents.macro_synthesizer import macro_synthesizer
    new_toc = await macro_synthesizer.revise_toc(history, entities, [])
    
    db.save_toc(project_id, new_toc)
    return {"toc": new_toc}

@app.post("/api/projects/{project_id}/write")
async def trigger_write(project_id: str):
    db.update_project_status(project_id, "writing")
    
    # Run WriterAgent in background
    async def run_writer():
        try:
            from trace.core.graph.builder import graph_builder
            raw_traces = db.get_traces_by_project(project_id)
            from trace.core.schemas import HippocampalTrace
            traces = []
            for row in raw_traces:
                if row.get("metadata"):
                    try:
                        t = HippocampalTrace.model_validate_json(row["metadata"])
                        if row.get("user_concept"): t.anchor_concept = row["user_concept"]
                        if row.get("user_type"): t.artifact_type = row["user_type"]
                        traces.append(t)
                    except: pass
                    
            entities = graph_builder.clusterer.cluster_traces(traces)
            toc = db.get_toc(project_id)
            
            output_dir = os.path.join(os.path.dirname(__file__), "output", project_id)
            os.makedirs(output_dir, exist_ok=True)
            
            
            # Write TOC
            if toc:
                with open(os.path.join(output_dir, "TOC.md"), "w", encoding="utf-8") as f:
                    f.write(toc)
            
            # Generate DAG (Mermaid)
            try:
                # We need edges. Let's rebuild edges using the same logic as GraphBuilder.
                edges = []
                concept_to_id = {}
                for entity in entities:
                    for trace in entity.traces:
                        concept_to_id[trace.anchor_concept] = entity.id
                for entity in entities:
                    for trace in entity.traces:
                        for rel in trace.relations:
                            target_id = concept_to_id.get(rel.target_concept)
                            if not target_id:
                                for c_name in concept_to_id.keys():
                                    if rel.target_concept.lower() in c_name.lower():
                                        target_id = concept_to_id[c_name]
                                        break
                            if target_id and target_id != entity.id:
                                edges.append((entity.id, target_id, rel.relation_type))
                
                # Make unique
                edges = list(set(edges))
                
                mermaid = "graph TD\n"
                for entity in entities:
                    mermaid += f'  {entity.id}["{entity.canonical_name}"]\n'
                for source_id, target_id, relation_type in edges:
                    mermaid += f'  {source_id} -->|{relation_type}| {target_id}\n'
                
                with open(os.path.join(output_dir, "Graph.mmd"), "w", encoding="utf-8") as f:
                    f.write(mermaid)
            except Exception as e:
                print("Failed to generate DAG:", e)
                    
            from trace.agents.writer_agent import writer_agent
            for entity in entities:
                content = await writer_agent.generate_document(entity, project_id=project_id)
                safe_name = "".join(c if c.isalnum() else "_" for c in entity.canonical_name)
                with open(os.path.join(output_dir, f"{safe_name}.md"), "w", encoding="utf-8") as f:
                    f.write(content)
                    
            db.update_project_status(project_id, "completed")
            await broadcast_event(project_id, "WriterCompleted", {"status": "done"})
        except Exception as e:
            print(f"Error in writer task: {e}")
            await broadcast_event(project_id, "PipelineError", {"error": str(e)})

    asyncio.create_task(run_writer())
    return {"status": "started"}

@app.get("/api/projects/{project_id}/output")
async def get_project_output(project_id: str):
    output_dir = os.path.join(os.path.dirname(__file__), "output", project_id)
    if not os.path.exists(output_dir):
        return {"files": []}
    
    files_data = []
    for filename in os.listdir(output_dir):
        if filename.endswith(".md"):
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            files_data.append({
                "name": filename,
                "content": content
            })
    return {"files": files_data}

class SettingsUpdate(BaseModel):
    deepseek_api_key: str | None = None
    gemini_api_key: str | None = None
    planner_model: str | None = None
    writer_model: str | None = None

@app.get("/api/settings")
async def get_settings():
    return {
        "deepseek_api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "planner_model": os.environ.get("PLANNER_MODEL", "gemini/gemini-3.1-flash-lite"),
        "writer_model": os.environ.get("WRITER_MODEL", "gemini/gemma-4-31b-it")
    }

@app.post("/api/settings")
async def update_settings(req: SettingsUpdate):
    import dotenv
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        open(env_path, 'w').close()
        
    if req.deepseek_api_key is not None:
        dotenv.set_key(env_path, "DEEPSEEK_API_KEY", req.deepseek_api_key)
        os.environ["DEEPSEEK_API_KEY"] = req.deepseek_api_key
    if req.gemini_api_key is not None:
        dotenv.set_key(env_path, "GEMINI_API_KEY", req.gemini_api_key)
        os.environ["GEMINI_API_KEY"] = req.gemini_api_key
    if req.planner_model is not None:
        dotenv.set_key(env_path, "PLANNER_MODEL", req.planner_model)
        os.environ["PLANNER_MODEL"] = req.planner_model
    if req.writer_model is not None:
        dotenv.set_key(env_path, "WRITER_MODEL", req.writer_model)
        os.environ["WRITER_MODEL"] = req.writer_model
        
    # Reload agents to pick up new models
    import trace.agents.micro_extractor
    trace.agents.micro_extractor.micro_extractor.model_name = os.environ.get("PLANNER_MODEL", "gemini/gemini-3.1-flash-lite")
    
    return {"status": "updated"}

# Global dictionary to track active websocket connections per project
ws_connections = {}

async def broadcast_event(project_id: str, event_type: str, payload: any):
    if project_id in ws_connections:
        for ws in ws_connections[project_id]:
            try:
                await ws.send_json({"type": event_type, "payload": payload})
            except:
                pass

@app.websocket("/api/ws/logs/{project_id}")
async def websocket_logs(websocket: WebSocket, project_id: str):
    await websocket.accept()
    if project_id not in ws_connections:
        ws_connections[project_id] = []
    ws_connections[project_id].append(websocket)
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_connections[project_id].remove(websocket)

# Subscribe to global events and broadcast them to WS clients
def make_broadcaster(event_type: str):
    async def handler(event: Event):
        # We assume event.payload has project_id, or we broadcast to all if not sure
        project_id = getattr(event.payload, "project_id", None)
        payload_data = jsonable_encoder(event.payload)
        if project_id:
            await broadcast_event(project_id, event_type, payload_data)
        else:
            # Broadcast to all if no project_id (temporary fallback)
            for pid, clients in ws_connections.items():
                for ws in clients:
                    try:
                        await ws.send_json({"type": event_type, "payload": payload_data})
                    except:
                        pass
    return handler

event_bus.subscribe("LLMCall", make_broadcaster("LLMCall"))
event_bus.subscribe("TraceExtracted", make_broadcaster("TraceExtracted"))
event_bus.subscribe("PipelineError", make_broadcaster("PipelineError"))
event_bus.subscribe("TocGenerated", make_broadcaster("TocGenerated"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
