import os
import chromadb
from typing import List, Dict, Any, Optional

class VectorDB:
    def __init__(self, db_dir: str = "chroma_db"):
        self.db_dir = db_dir
        # Initialize a persistent ChromaDB client
        self.client = chromadb.PersistentClient(path=self.db_dir)
        # Create or get the collection for our chunks
        # We will use the default embedding function (all-MiniLM-L6-v2) built into ChromaDB 
        # unless a custom one is needed.
        self.collection = self.client.get_or_create_collection(
            name="chunks",
            metadata={"hnsw:space": "cosine"} # Use cosine similarity for distance
        )
        
    def upsert_chunks(self, project_id: str, chunk_ids: List[str], chunk_texts: List[str], metadatas: List[Dict[str, Any]] = None):
        """
        Compute and store dense embeddings for the given text chunks.
        """
        if not chunk_ids or not chunk_texts:
            return
            
        if len(chunk_ids) != len(chunk_texts):
            raise ValueError("chunk_ids and chunk_texts must have the same length")
            
        if metadatas is None:
            metadatas = [{} for _ in range(len(chunk_ids))]
            
        # Add project_id to metadata to filter easily later
        for meta in metadatas:
            meta['project_id'] = project_id
            
        self.collection.upsert(
            ids=chunk_ids,
            documents=chunk_texts,
            metadatas=metadatas
        )
        
    def query_similar_chunks(self, project_id: str, query_texts: List[str], n_results: int = 5) -> Dict:
        """
        Query the vector DB for the most similar chunks within a specific project.
        """
        results = self.collection.query(
            query_texts=query_texts,
            n_results=n_results,
            where={"project_id": project_id}
        )
        return results

    def delete_project_chunks(self, project_id: str):
        """
        Delete all chunks associated with a specific project.
        """
        self.collection.delete(
            where={"project_id": project_id}
        )

# Instantiate a global VectorDB client
vector_db = VectorDB()
