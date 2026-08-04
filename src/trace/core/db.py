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
                    toc TEXT,
                    current_goal TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS blocks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    hash TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sparse_vector TEXT,
                    structural_tag TEXT DEFAULT 'core_concept'
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    block_id TEXT,
                    anchor_concept TEXT,
                    artifact_type TEXT,
                    status TEXT,
                    summary_trace TEXT,
                    chronological_marker TEXT,
                    raw_source_text TEXT,
                    metadata TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    canonical_name TEXT,
                    status TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS edges (
                    source_id TEXT,
                    target_id TEXT,
                    project_id TEXT,
                    relation_type TEXT,
                    PRIMARY KEY (source_id, target_id, relation_type)
                )
            ''')
            conn.commit()
            
            # Add toc column if it doesn't exist (for existing databases)
            try:
                conn.execute('ALTER TABLE projects ADD COLUMN toc TEXT')
            except sqlite3.OperationalError:
                pass # Column already exists
                
            # Add sparse_vector column to blocks
            try:
                conn.execute('ALTER TABLE blocks ADD COLUMN sparse_vector TEXT')
            except sqlite3.OperationalError:
                pass
                
            # Add is_chronological column
            try:
                conn.execute('ALTER TABLE projects ADD COLUMN is_chronological BOOLEAN DEFAULT 0')
            except sqlite3.OperationalError:
                pass
                
            # Add structural_tag to blocks
            try:
                conn.execute('ALTER TABLE blocks ADD COLUMN structural_tag TEXT DEFAULT "core_concept"')
            except sqlite3.OperationalError:
                pass

            # Add current_goal to projects
            try:
                conn.execute('ALTER TABLE projects ADD COLUMN current_goal TEXT')
            except sqlite3.OperationalError:
                pass

            # Update traces table with new columns if they don't exist
            new_trace_columns = [
                ('anchor_concept', 'TEXT'),
                ('artifact_type', 'TEXT'),
                ('status', 'TEXT'),
                ('summary_trace', 'TEXT'),
                ('chronological_marker', 'TEXT'),
                ('raw_source_text', 'TEXT'),
                ('metadata', 'TEXT')
            ]
            for col_name, col_type in new_trace_columns:
                try:
                    conn.execute(f'ALTER TABLE traces ADD COLUMN {col_name} {col_type}')
                except sqlite3.OperationalError:
                    pass
                
    def set_is_chronological(self, project_id: str, is_chronological: bool):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE projects SET is_chronological = ? WHERE id = ?', (is_chronological, project_id))
            conn.commit()
            
    def get_is_chronological(self, project_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT is_chronological FROM projects WHERE id = ?', (project_id,)).fetchone()
            if row and row['is_chronological']:
                return bool(row['is_chronological'])
        return False
                
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
        
    def set_project_goal(self, project_id: str, goal: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE projects SET current_goal = ? WHERE id = ?', (goal, project_id))
            conn.commit()
            
    def get_project_goal(self, project_id: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT current_goal FROM projects WHERE id = ?', (project_id,)).fetchone()
            if row and row['current_goal']:
                return row['current_goal']
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
            conn.execute('DELETE FROM edges WHERE project_id = ?', (project_id,))
            conn.execute('DELETE FROM entities WHERE project_id = ?', (project_id,))
            conn.execute('DELETE FROM traces WHERE project_id = ?', (project_id,))
            conn.execute('DELETE FROM blocks WHERE project_id = ?', (project_id,))
            conn.execute('DELETE FROM projects WHERE id = ?', (project_id,))
            conn.commit()

    def upsert_block(self, block_id: str, project_id: str, content: str, sparse_vector: Optional[str] = None, structural_tag: str = 'core_concept') -> str:
        content_hash = self.compute_hash(content)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO blocks (id, project_id, hash, content, sparse_vector, structural_tag)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (block_id, project_id, content_hash, content, sparse_vector, structural_tag))
            conn.commit()
        return content_hash
        
    def upsert_trace(self, trace_id: str, project_id: str, block_id: str, anchor_concept: str, artifact_type: str, status: str, summary_trace: str, chronological_marker: Optional[str], raw_source_text: str, metadata: str = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO traces (trace_id, project_id, block_id, anchor_concept, artifact_type, status, summary_trace, chronological_marker, raw_source_text, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (trace_id, project_id, block_id, anchor_concept, artifact_type, status, summary_trace, chronological_marker, raw_source_text, metadata))
            conn.commit()

    def upsert_entity(self, entity_id: str, project_id: str, canonical_name: str, status: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO entities (id, project_id, canonical_name, status)
                VALUES (?, ?, ?, ?)
            ''', (entity_id, project_id, canonical_name, status))
            conn.commit()

    def upsert_edge(self, source_id: str, target_id: str, project_id: str, relation_type: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO edges (source_id, target_id, project_id, relation_type)
                VALUES (?, ?, ?, ?)
            ''', (source_id, target_id, project_id, relation_type))
            conn.commit()

    def get_block(self, block_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT * FROM blocks WHERE id = ?', (block_id,)).fetchone()
            if row:
                return dict(row)
        return None

    def get_blocks_by_project(self, project_id: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM blocks WHERE project_id = ?', (project_id,)).fetchall()
            return [dict(row) for row in rows]

    def get_traces_by_block(self, block_id: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM traces WHERE block_id = ? ORDER BY trace_id', (block_id,)).fetchall()
            return [dict(row) for row in rows]

    def get_traces_by_project(self, project_id: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM traces WHERE project_id = ? ORDER BY trace_id', (project_id,)).fetchall()
            return [dict(row) for row in rows]

db = Database()
