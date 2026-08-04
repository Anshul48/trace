import os
from pathlib import Path
from unstructured.partition.auto import partition
from trace.ingestion.chunker import semantic_chunker
from trace.core.schemas import Event, SourceMeta, DocumentChunkedPayload
from trace.events.bus import event_bus
from trace.core.vector_db import vector_db

import uuid
from trace.core.db import db

async def ingest_documents(directory_path: str, project_id: str, fast_mode: bool = False, is_chronological: bool = False, thread_id: str = "default"):
    """
    Scans a directory for documents, partitions and chunks them using unstructured,
    and publishes a DocumentChunked event for each chunk.
    """
    path = Path(directory_path)
    if not path.exists() or not path.is_dir():
        raise ValueError(f"Directory {directory_path} does not exist.")

    import asyncio
    
    for root, _, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            # Skip hidden files
            if file.startswith('.') or file_path.endswith('.py') or file_path.endswith('.toml') or file_path.endswith('.lock') or file_path.endswith('.db'):
                continue
            
            try:
                # Use unstructured to partition
                if fast_mode:
                    elements = partition(filename=file_path, strategy="fast")
                else:
                    elements = partition(filename=file_path)
                    
                full_text = "\n\n".join([str(e) for e in elements if str(e).strip()])
                
                # Semantic Chunking
                chunk_tuples = semantic_chunker.chunk_text(full_text)
                
                tasks = []
                chunk_ids = []
                chunk_texts = []
                chunk_metas = []
                
                for idx, (chunk_text, sparse_vector, structural_tag) in enumerate(chunk_tuples):
                    block_id = str(uuid.uuid4())
                    db.upsert_block(block_id, project_id, chunk_text, sparse_vector=sparse_vector, structural_tag=structural_tag)
                    
                    if structural_tag == 'ephemeral':
                        continue
                    
                    meta = SourceMeta(
                        filename=file,
                        absolute_path=os.path.abspath(file_path),
                        chunk_index=idx,
                        block_id=block_id
                    )
                    
                    chunk_ids.append(block_id)
                    chunk_texts.append(chunk_text)
                    chunk_metas.append(meta.model_dump())
                    
                    payload = DocumentChunkedPayload(
                        project_id=project_id,
                        chunk_text=chunk_text,
                        meta=meta,
                        is_chronological=is_chronological,
                        thread_id=thread_id
                    )
                    event = Event(name="DocumentChunked", payload=payload)
                    
                    if is_chronological:
                        await event_bus.publish(event)
                    else:
                        tasks.append(event_bus.publish(event))
                        
                # Insert into Vector DB for dense embeddings
                if chunk_ids:
                    vector_db.upsert_chunks(project_id, chunk_ids, chunk_texts, chunk_metas)
                        
                if tasks:
                    await asyncio.gather(*tasks)
                    
            except Exception as e:
                print(f"Error processing {file_path}: {e}")

    await event_bus.publish(Event(name="AllDocumentsProcessed", payload=None))
