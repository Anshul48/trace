import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure the src directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from trace.events.bus import event_bus, Event
from trace.ingestion.parser import ingest_documents

# Import agents to ensure their instances are initialized and subscribed to the event bus
import trace.agents.micro_extractor
import trace.core.graph.builder
import trace.agents.macro_synthesizer
from trace.core.db import db
from trace.ingestion.watcher import start_watcher
from trace.core.schemas import TocGeneratedPayload

async def main():
    load_dotenv() # Load API keys for litellm (e.g. DEEPSEEK_API_KEY, OPENAI_API_KEY, etc.)
    
    print("Initializing Database...")
    db.init_db()
    
    # Start the Bi-Directional Watcher
    watcher_observer = start_watcher("repo_out")

    # We can use an asyncio.Event to wait for PipelineFinished
    finished = asyncio.Event()
    
    def on_finished(event: Event):
        if event.name == "PipelineFinished":
            finished.set()
            
    event_bus.subscribe("PipelineFinished", on_finished)
    
    async def on_toc_generated(event: Event):
        payload: TocGeneratedPayload = event.payload
        print("TOC Generated. Automatically proceeding to write repository (CLI mode)...")
        from trace.agents.macro_synthesizer import macro_synthesizer
        await macro_synthesizer.weaver.write_repository(payload.entities, payload.edges, payload.global_toc)
        await event_bus.publish(Event(name="PipelineFinished", payload=None))
        
    event_bus.subscribe("TocGenerated", on_toc_generated)
    
    data_dir = "data/raw"
    if not os.path.exists(data_dir):
        print(f"Creating directory {data_dir}. Please place your raw documents there.")
        os.makedirs(data_dir, exist_ok=True)
        return
        
    print(f"Starting pipeline. Ingesting documents from {data_dir}...")
    await ingest_documents(data_dir)
    
    print("Ingestion complete. Awaiting downstream pipeline processing...")
    # Wait for the pipeline to finish processing
    await finished.wait()
    print("Pipeline execution completed successfully.")
    print("Initial ETL complete. Watcher is running in the background for bi-directional sync. Press Ctrl+C to exit.")
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        watcher_observer.stop()
        watcher_observer.join()

if __name__ == "__main__":
    asyncio.run(main())
