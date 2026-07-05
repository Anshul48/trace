import re
import os
from typing import List
import torch
import transformers
from sentence_transformers import SentenceTransformer, util
from trace.core.db import db
import sqlite3

class Decompiler:
    def __init__(self):
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        # Local fast embedding model for Triage Routing
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2', device=device)
        # Regex to match the hidden trace anchors
        self.pattern = re.compile(r'<!--\s*trace_id:\s*(.*?)\s*-->(.*?)<!--\s*end_trace_id\s*-->', re.DOTALL)
        
    def sync_file(self, file_path: str):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        matches = self.pattern.findall(content)
        for trace_id, modified_text in matches:
            modified_text = modified_text.strip()
            self._evaluate_impact(trace_id, modified_text)
            
    def _evaluate_impact(self, trace_id: str, new_text: str):
        # Look up the trace to find the original block_id
        with sqlite3.connect(db.db_path) as conn:
            conn.row_factory = sqlite3.Row
            trace_row = conn.execute('SELECT * FROM traces WHERE trace_id = ?', (trace_id,)).fetchone()
            
        if not trace_row:
            print(f"[Tier 3] Unknown trace {trace_id}. This represents a topology mutation.")
            # TODO: Route to full ingestion
            return
            
        block_id = trace_row['block_id']
        block = db.get_block(block_id)
        if not block:
            return
            
        old_text = block['content']
        old_hash = block['hash']
        new_hash = db.compute_hash(new_text)
        
        if old_hash == new_hash:
            # No change
            return 
            
        # Hashes differ. Triage evaluation via Cosine Similarity
        emb1 = self.embedder.encode(old_text, convert_to_tensor=True)
        emb2 = self.embedder.encode(new_text, convert_to_tensor=True)
        cosine_score = util.cos_sim(emb1, emb2).item()
        
        if cosine_score > 0.95:
            print(f"[Tier 1] Surface mutation on trace {trace_id} (sim {cosine_score:.3f}). Silent DB update.")
            db.upsert_block(block_id, new_text)
        else:
            print(f"[Tier 2] Semantic mutation on trace {trace_id} (sim {cosine_score:.3f}). Propagating state change.")
            db.upsert_block(block_id, new_text)
            # In a full run, we would re-run the MicroExtractor locally here and trigger WriterAgent to re-render.

decompiler = Decompiler()
