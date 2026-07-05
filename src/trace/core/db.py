import sqlite3
import os
import hashlib
from typing import Optional, Dict

class Database:
    def __init__(self, db_path: str = "trace.db"):
        self.db_path = db_path
        self.init_db()
        
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    toc TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS blocks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    hash TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    block_id TEXT,
                    entity_id TEXT,
                    metadata TEXT,
                    user_concept TEXT,
                    user_type TEXT,
                    user_relations TEXT
                )
            ''')
            conn.commit()
            
            # Add toc column if it doesn't exist (for existing databases)
            try:
                conn.execute('ALTER TABLE projects ADD COLUMN toc TEXT')
            except sqlite3.OperationalError:
                pass # Column already exists
                
    def save_toc(self, project_id: str, toc: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE projects SET toc = ? WHERE id = ?', (toc, project_id))
            conn.commit()
            
    def get_toc(self, project_id: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT toc FROM projects WHERE id = ?', (project_id,)).fetchone()
            if row and row['toc']:
                return row['toc']
        return None
            
    def compute_hash(self, content: str) -> str:
        # Normalize trailing spaces and newlines to avoid trivial diffs
        normalized = "\n".join([line.rstrip() for line in content.splitlines()]).strip()
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def create_project(self, project_id: str, name: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO projects (id, name, status)
                VALUES (?, ?, 'created')
            ''', (project_id, name))
            conn.commit()

    def update_project_status(self, project_id: str, status: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE projects SET status = ? WHERE id = ?', (status, project_id))
            conn.commit()

    def get_all_projects(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM projects ORDER BY created_at DESC').fetchall()
            return [dict(row) for row in rows]

    def delete_project(self, project_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM traces WHERE project_id = ?', (project_id,))
            conn.execute('DELETE FROM blocks WHERE project_id = ?', (project_id,))
            conn.execute('DELETE FROM projects WHERE id = ?', (project_id,))
            conn.commit()

    def upsert_block(self, block_id: str, project_id: str, content: str) -> str:
        content_hash = self.compute_hash(content)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO blocks (id, project_id, hash, content)
                VALUES (?, ?, ?, ?)
            ''', (block_id, project_id, content_hash, content))
            conn.commit()
        return content_hash
        
    def upsert_trace(self, trace_id: str, project_id: str, block_id: str, entity_id: str, metadata: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO traces (trace_id, project_id, block_id, entity_id, metadata, user_concept, user_type, user_relations)
                VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)
            ''', (trace_id, project_id, block_id, entity_id, metadata))
            conn.commit()

    def get_block(self, block_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT * FROM blocks WHERE id = ?', (block_id,)).fetchone()
            if row:
                return dict(row)
        return None

    def get_traces_by_project(self, project_id: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM traces WHERE project_id = ?', (project_id,)).fetchall()
            return [dict(row) for row in rows]

db = Database()
