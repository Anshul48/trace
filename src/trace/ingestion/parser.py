import os
from pathlib import Path
from unstructured.partition.auto import partition
from unstructured.chunking.title import chunk_by_title
from trace.core.schemas import Event, SourceMeta, DocumentChunkedPayload
from trace.events.bus import event_bus

import uuid
from trace.core.db import db

async def ingest_documents(directory_path: str, project_id: str = "default", fast_mode: bool = False):
    """
    Scans a directory for documents, partitions and chunks them using unstructured,
    and publishes a DocumentChunked event for each chunk.
    """
    path = Path(directory_path)
    if not path.exists() or not path.is_dir():
        raise ValueError(f"Directory {directory_path} does not exist.")

    for root, _, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            # Skip hidden files
            if file.startswith('.') or file_path.endswith('.py') or file_path.endswith('.toml') or file_path.endswith('.lock') or file_path.endswith('.db'):
                continue
            
            try:
                # Use unstructured to partition and chunk
                if fast_mode:
                    elements = partition(filename=file_path, strategy="fast")
                else:
                    elements = partition(filename=file_path)
                chunks = chunk_by_title(
                    elements, 
                    max_characters=1000, 
                    new_after_n_chars=800, 
                    overlap=100
                )
                
                for idx, chunk in enumerate(chunks):
                    chunk_text = str(chunk)
                    block_id = str(uuid.uuid4())
                    db.upsert_block(block_id, project_id, chunk_text)
                    
                    meta = SourceMeta(
                        filename=file,
                        absolute_path=os.path.abspath(file_path),
                        chunk_index=idx,
                        block_id=block_id
                    )
                    payload = DocumentChunkedPayload(
                        project_id=project_id,
                        chunk_text=chunk_text,
                        meta=meta
                    )
                    event = Event(name="DocumentChunked", payload=payload)
                    await event_bus.publish(event)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")

    await event_bus.publish(Event(name="AllDocumentsProcessed", payload=None))
