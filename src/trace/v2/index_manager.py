"""Windows-Safe Epoch RCU & Generation Index Manager.

Target File: src/trace/v2/index_manager.py
Scope: WP2 Storage Schema & Windows Epoch RCU.
- Immutable Generation Directories: compacted generations written to
  generations/gen_{epoch}_{timestamp}/ containing vectors.bin, fts_atoms.db, graph.csr.
  Files are NEVER overwritten in-place.
- Authoritative SQLite Pointer Swap: active generation governed by single SQLite ACID
  table active_generation(lock_id=1, epoch, gen_dir, promoted_at).
- Cross-Process SQLite Reader Leases: readers register active lease in SQLite table
  active_reader_leases(pid INT, lease_id TEXT, epoch INT, acquired_at TIMESTAMP),
  preventing cross-process WinError 32 file locking on active mmaps.
- Deferred Unlinking & WinError 32 Mitigation: retired generations enter DORMANT_RETIRED
  state for grace period T_grace = 120s AND until active reader leases query count reaches
  zero. Unlink failures (WinError 32 / PermissionError) are caught and deferred to next sweep.
- Micro-Batched Ingestion Pipeline invariants and active WAL checkpoint throttling.
- Storage Gate Verification: empirical total-hot <= 3.0x admitted UTF-8 bytes.
"""

from __future__ import annotations

import errno
import logging
import mmap
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import sys
import time
from typing import Any, Iterator, Mapping, Sequence
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def is_process_alive(pid: int) -> bool:
    """Check if process with given PID is currently running across POSIX and Windows."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h_proc:
                err = kernel32.GetLastError()
                return err == 5  # ERROR_ACCESS_DENIED implies process exists
            exit_code = ctypes.c_ulong()
            success = kernel32.GetExitCodeProcess(h_proc, ctypes.byref(exit_code))
            kernel32.CloseHandle(h_proc)
            return bool(success and exit_code.value == STILL_ACTIVE)
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as err:
        return err.errno != errno.ESRCH


# ==============================================================================
# Appendix A Row-7 Frozen Priors & Storage Invariants
# ==============================================================================

LEASE_GRACE_SECONDS: int = 120
COMMIT_BATCH_SIZE: int = 250
INGEST_QUEUE_MAXSIZE: int = 16
WAL_PASSIVE_CHECKPOINT_COMMITS: int = 10
WAL_RESTART_THRESHOLD_BYTES: int = 16 * 1024 * 1024  # 16 MB
WAL_TRUNCATE_THRESHOLD_BYTES: int = 64 * 1024 * 1024  # 64 MB

VECTOR_DIM: int = 384
VECTOR_BYTES_PER_ITEM: int = 384  # 384-d int8 quantized
MAX_STORAGE_MULTIPLIER: float = 3.0
MAX_DURABLE_MULTIPLIER: float = 1.6


# ==============================================================================
# Database Schema Helpers
# ==============================================================================

def init_generation_db(db_path: Path | str) -> sqlite3.Connection:
    """Initialize authoritative Epoch RCU tables in a SQLite database."""
    path = Path(db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_generation (
                lock_id INTEGER PRIMARY KEY CHECK (lock_id = 1),
                epoch INTEGER NOT NULL,
                gen_dir TEXT NOT NULL,
                promoted_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_reader_leases (
                pid INTEGER NOT NULL,
                lease_id TEXT PRIMARY KEY,
                epoch INTEGER NOT NULL,
                acquired_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS active_reader_leases_epoch
                ON active_reader_leases(epoch);
            """
        )
        # Canonical L0 and external FTS5 tables
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS atom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                start_byte INTEGER NOT NULL,
                end_byte INTEGER NOT NULL,
                content_hash BLOB NOT NULL,
                text TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS atom_file_start ON atom(file_id, start_byte);")
        conn.execute("CREATE INDEX IF NOT EXISTS atom_content_hash ON atom(content_hash);")
        conn.execute("CREATE INDEX IF NOT EXISTS atom_doc_id ON atom(doc_id);")

        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_atoms USING fts5(
                    text,
                    content='atom',
                    content_rowid='id',
                    tokenize='porter unicode61 remove_diacritics 1'
                );
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS atom_ai AFTER INSERT ON atom BEGIN
                    INSERT INTO fts_atoms(rowid, text) VALUES (new.id, new.text);
                END;
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS atom_ad AFTER DELETE ON atom BEGIN
                    INSERT INTO fts_atoms(fts_atoms, rowid, text) VALUES('delete', old.id, old.text);
                END;
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS atom_au AFTER UPDATE ON atom BEGIN
                    INSERT INTO fts_atoms(fts_atoms, rowid, text) VALUES('delete', old.id, old.text);
                    INSERT INTO fts_atoms(rowid, text) VALUES (new.id, new.text);
                END;
                """
            )
        except sqlite3.OperationalError:
            pass

        # Holons, TOC, Edges
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holons (
                id TEXT PRIMARY KEY,
                parent_toc TEXT,
                centroid_int8 BLOB,
                lex_sig TEXT NOT NULL,
                spans TEXT NOT NULL,
                energy REAL NOT NULL DEFAULT 0.0,
                tier TEXT NOT NULL DEFAULT 'nav',
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                version INTEGER NOT NULL DEFAULT 1,
                anchor_model TEXT,
                anchor_prompt_hash TEXT,
                created_at TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS holons_parent_toc ON holons(parent_toc);")
        conn.execute("CREATE INDEX IF NOT EXISTS holons_status ON holons(status);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS toc (
                id TEXT PRIMARY KEY,
                parent TEXT,
                c0 BLOB,
                r0 REAL,
                members TEXT NOT NULL,
                boundary TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS toc_parent ON toc(parent);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS edges (
                src TEXT NOT NULL,
                dst TEXT NOT NULL,
                type TEXT NOT NULL,
                weight REAL NOT NULL,
                properties_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT,
                PRIMARY KEY (src, dst, type)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS edges_src ON edges(src);")
        conn.execute("CREATE INDEX IF NOT EXISTS edges_dst ON edges(dst);")
        conn.execute("CREATE INDEX IF NOT EXISTS edges_type ON edges(type);")

    return conn


# ==============================================================================
# CSR Graph Serialization Helpers
# ==============================================================================

@dataclass
class CSRGraph:
    """Compressed Sparse Row (CSR) structure for explicit graph edges."""

    num_nodes: int
    indptr: list[int]
    indices: list[int]
    types: list[int]
    weights: list[float]

    def to_bytes(self) -> bytes:
        """Serialize CSR into compact binary bytes."""
        # Format:
        # Magic: 4 bytes b"TCSR"
        # Version: 1 byte (1)
        # Reserved: 3 bytes b"\x00\x00\x00"
        # num_nodes: uint32
        # num_edges: uint32
        # (Total header: 16 bytes)
        # indptr: (num_nodes + 1) * uint32
        # indices: num_edges * uint32
        # types: num_edges * uint16
        # weights: num_edges * float32
        num_edges = len(self.indices)
        header = struct.pack("<4sB3sII", b"TCSR", 1, b"\x00\x00\x00", self.num_nodes, num_edges)
        indptr_bytes = struct.pack(f"<{len(self.indptr)}I", *self.indptr)
        indices_bytes = struct.pack(f"<{num_edges}I", *self.indices) if num_edges > 0 else b""
        types_bytes = struct.pack(f"<{num_edges}H", *self.types) if num_edges > 0 else b""
        weights_bytes = struct.pack(f"<{num_edges}f", *self.weights) if num_edges > 0 else b""
        return header + indptr_bytes + indices_bytes + types_bytes + weights_bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> CSRGraph:
        """Deserialize CSR from binary bytes."""
        if len(data) < 16:
            return cls(num_nodes=0, indptr=[0], indices=[], types=[], weights=[])
        magic, ver, _, num_nodes, num_edges = struct.unpack_from("<4sB3sII", data, 0)
        if magic != b"TCSR":
            return cls(num_nodes=0, indptr=[0], indices=[], types=[], weights=[])
        offset = 16
        indptr_len = num_nodes + 1
        if indptr_len > 0 and len(data) >= offset + indptr_len * 4:
            indptr = list(struct.unpack_from(f"<{indptr_len}I", data, offset))
            offset += indptr_len * 4
        else:
            indptr = [0]
        if num_edges > 0 and len(data) >= offset + num_edges * (4 + 2 + 4):
            indices = list(struct.unpack_from(f"<{num_edges}I", data, offset))
            offset += num_edges * 4
            types = list(struct.unpack_from(f"<{num_edges}H", data, offset))
            offset += num_edges * 2
            weights = list(struct.unpack_from(f"<{num_edges}f", data, offset))
        else:
            indices = []
            types = []
            weights = []
        return cls(
            num_nodes=num_nodes,
            indptr=indptr,
            indices=indices,
            types=types,
            weights=weights,
        )


# ==============================================================================
# Generation Info & Reader Lease
# ==============================================================================

@dataclass
class GenerationInfo:
    """Immutable Generation descriptor."""

    epoch: int
    gen_dir: Path
    promoted_at: float
    status: str = "ACTIVE"

    @property
    def vectors_path(self) -> Path:
        return self.gen_dir / "vectors.bin"

    @property
    def fts_db_path(self) -> Path:
        return self.gen_dir / "fts_atoms.db"

    @property
    def graph_csr_path(self) -> Path:
        return self.gen_dir / "graph.csr"

    def load_graph_csr(self) -> CSRGraph:
        """Load and deserialize graph.csr for this generation."""
        if not self.graph_csr_path.exists():
            return CSRGraph(num_nodes=0, indptr=[0], indices=[], types=[], weights=[])
        return CSRGraph.from_bytes(self.graph_csr_path.read_bytes())


@dataclass
class ReaderLease:
    """Active cross-process reader lease registered in SQLite active_reader_leases."""

    pid: int
    lease_id: str
    epoch: int
    gen_dir: Path
    acquired_at: float
    _db_path: Path | None = None
    _open_files: list[Any] = field(default_factory=list, repr=False)
    _open_mmaps: list[mmap.mmap] = field(default_factory=list, repr=False)

    def __enter__(self) -> ReaderLease:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    @property
    def vectors_path(self) -> Path:
        return self.gen_dir / "vectors.bin"

    @property
    def fts_db_path(self) -> Path:
        return self.gen_dir / "fts_atoms.db"

    @property
    def graph_csr_path(self) -> Path:
        return self.gen_dir / "graph.csr"

    def load_graph_csr(self) -> CSRGraph:
        """Load and deserialize graph.csr under this lease."""
        if not self.graph_csr_path.exists():
            return CSRGraph(num_nodes=0, indptr=[0], indices=[], types=[], weights=[])
        return CSRGraph.from_bytes(self.graph_csr_path.read_bytes())

    def open_vectors_mmap(self) -> mmap.mmap | None:
        """Open vectors.bin with an active mmap under this lease handle."""
        if not self.vectors_path.exists():
            raise FileNotFoundError(f"Generation vectors file not found: {self.vectors_path}")
        size = self.vectors_path.stat().st_size
        if size == 0:
            return None
        f = open(self.vectors_path, "rb")
        self._open_files.append(f)
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        self._open_mmaps.append(mm)
        return mm

    def close(self) -> None:
        """Close all mmaps and file handles opened under this lease."""
        for mm in self._open_mmaps:
            try:
                mm.close()
            except Exception:
                pass
        self._open_mmaps.clear()
        for f in self._open_files:
            try:
                f.close()
            except Exception:
                pass
        self._open_files.clear()

    def release(self) -> bool:
        """Release the lease from SQLite and close open handles."""
        self.close()
        if self._db_path is not None and self._db_path.exists():
            try:
                conn = sqlite3.connect(str(self._db_path), timeout=30.0)
                with conn:
                    cursor = conn.execute(
                        "DELETE FROM active_reader_leases WHERE lease_id = ?;",
                        (self.lease_id,),
                    )
                    deleted = cursor.rowcount > 0
                conn.close()
                return deleted
            except Exception as exc:
                logger.warning("Failed to delete lease %s: %s", self.lease_id, exc)
                return False
        return False


# ==============================================================================
# Epoch Index Manager
# ==============================================================================

class EpochIndexManager:
    """Windows-Safe Epoch RCU Index Manager governing generation lifecycle."""

    def __init__(
        self,
        workspace_dir: str | Path,
        db_path: str | Path | None = None,
        lease_grace_seconds: float = LEASE_GRACE_SECONDS,
        auto_init: bool = True,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.generations_dir = self.workspace_dir / "generations"
        self.generations_dir.mkdir(parents=True, exist_ok=True)

        if db_path is not None:
            self.db_path = Path(db_path).resolve()
        else:
            # Check for existing substrate.db or trace_v2.db
            sub_db = self.workspace_dir / "substrate.db"
            tr_db = self.workspace_dir / "trace_v2.db"
            if tr_db.exists() and not sub_db.exists():
                self.db_path = tr_db
            else:
                self.db_path = sub_db

        self.lease_grace_seconds = float(lease_grace_seconds)
        if auto_init:
            self.init_db()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager yielding SQLite connection with WAL and 30s timeout, guaranteed closed on exit."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        try:
            yield conn
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        """Connect to SQLite database with WAL and 30s timeout (caller must close)."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_db(self) -> None:
        """Initialize SQLite database tables and baseline Generation 1 if needed."""
        init_conn = init_generation_db(self.db_path)
        init_conn.close()
        with self._connection() as conn:
            row = conn.execute(
                "SELECT epoch, gen_dir, promoted_at FROM active_generation WHERE lock_id = 1;"
            ).fetchone()
            if not row:
                now = time.time()
                gen1_dir = self.generations_dir / f"gen_1_{int(now)}"
                self._create_generation_files(gen1_dir, epoch=1, num_vectors=10)
                with conn:
                    conn.execute(
                        """
                        INSERT INTO active_generation (lock_id, epoch, gen_dir, promoted_at)
                        VALUES (1, ?, ?, ?)
                        ON CONFLICT(lock_id) DO UPDATE SET
                            epoch = excluded.epoch,
                            gen_dir = excluded.gen_dir,
                            promoted_at = excluded.promoted_at;
                        """,
                        (1, str(gen1_dir), now),
                    )

    def _create_generation_files(
        self,
        gen_dir: Path,
        epoch: int,
        num_vectors: int = 10,
        vector_dim: int = VECTOR_DIM,
    ) -> tuple[Path, Path, Path]:
        """Create baseline generation files (vectors.bin, fts_atoms.db, graph.csr)."""
        gen_dir.mkdir(parents=True, exist_ok=True)
        vectors_path = gen_dir / "vectors.bin"
        fts_path = gen_dir / "fts_atoms.db"
        graph_path = gen_dir / "graph.csr"

        if not vectors_path.exists():
            payload = bytes([epoch % 127] * vector_dim) * num_vectors
            vectors_path.write_bytes(payload)

        if not fts_path.exists():
            fts_conn = sqlite3.connect(str(fts_path))
            with fts_conn:
                fts_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS atom (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        doc_id TEXT NOT NULL,
                        file_id TEXT NOT NULL,
                        start_byte INTEGER NOT NULL,
                        end_byte INTEGER NOT NULL,
                        content_hash BLOB NOT NULL,
                        text TEXT NOT NULL
                    );
                    """
                )
                try:
                    fts_conn.execute(
                        """
                        CREATE VIRTUAL TABLE IF NOT EXISTS fts_atoms USING fts5(
                            text,
                            content='atom',
                            content_rowid='id',
                            tokenize='porter unicode61 remove_diacritics 1'
                        );
                        """
                    )
                except sqlite3.OperationalError:
                    pass
            fts_conn.close()

        if not graph_path.exists():
            csr = CSRGraph(num_nodes=0, indptr=[0], indices=[], types=[], weights=[])
            graph_path.write_bytes(csr.to_bytes())

        return vectors_path, fts_path, graph_path

    @property
    def active_epoch(self) -> int:
        """Query authoritative active epoch from SQLite single-row active_generation table."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT epoch FROM active_generation WHERE lock_id = 1;"
            ).fetchone()
            if not row:
                raise RuntimeError("active_generation row missing from SQLite database")
            return int(row["epoch"])

    @property
    def active_gen_dir(self) -> Path:
        """Query authoritative active generation directory from SQLite."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT gen_dir FROM active_generation WHERE lock_id = 1;"
            ).fetchone()
            if not row:
                raise RuntimeError("active_generation row missing from SQLite database")
            return Path(row["gen_dir"])

    @property
    def active_generation_info(self) -> GenerationInfo:
        """Query authoritative GenerationInfo from SQLite."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT epoch, gen_dir, promoted_at FROM active_generation WHERE lock_id = 1;"
            ).fetchone()
            if not row:
                raise RuntimeError("active_generation row missing from SQLite database")
            return GenerationInfo(
                epoch=int(row["epoch"]),
                gen_dir=Path(row["gen_dir"]),
                promoted_at=float(row["promoted_at"]),
                status="ACTIVE",
            )

    def cleanup_stale_leases(self, max_age_seconds: float | None = None) -> int:
        """Clean up orphaned reader leases from dead processes or expired leases."""
        now = time.time()
        cleaned = 0
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT pid, lease_id, acquired_at FROM active_reader_leases;"
            ).fetchall()
            for r in rows:
                pid = int(r["pid"])
                lid = str(r["lease_id"])
                acq = float(r["acquired_at"])

                is_dead = not is_process_alive(pid)
                is_expired = (max_age_seconds is not None) and ((now - acq) > max_age_seconds)

                if is_dead or is_expired:
                    with conn:
                        conn.execute(
                            "DELETE FROM active_reader_leases WHERE lease_id = ?;",
                            (lid,),
                        )
                    cleaned += 1
                    logger.info(
                        "Cleaned stale reader lease %s (pid=%d, dead=%s, expired=%s)",
                        lid,
                        pid,
                        is_dead,
                        is_expired,
                    )
        return cleaned

    def register_lease(
        self,
        pid: int | None = None,
        epoch: int | None = None,
        lease_id: str | None = None,
    ) -> ReaderLease:
        """Register a reader lease in SQLite active_reader_leases table."""
        proc_pid = pid or os.getpid()
        lid = lease_id or str(uuid.uuid4())
        now = time.time()

        with self._connection() as conn:
            if epoch is None:
                row = conn.execute(
                    "SELECT epoch, gen_dir FROM active_generation WHERE lock_id = 1;"
                ).fetchone()
                if not row:
                    raise RuntimeError("active_generation missing during lease acquisition")
                target_epoch = int(row["epoch"])
                target_gen_dir = Path(row["gen_dir"])
            else:
                target_epoch = int(epoch)
                row = conn.execute(
                    "SELECT gen_dir FROM active_generation WHERE lock_id = 1 AND epoch = ?;",
                    (target_epoch,),
                ).fetchone()
                if row:
                    target_gen_dir = Path(row["gen_dir"])
                else:
                    matching = sorted(self.generations_dir.glob(f"gen_{target_epoch}_*"))
                    if matching:
                        target_gen_dir = matching[-1]
                    else:
                        target_gen_dir = self.generations_dir / f"gen_{target_epoch}"

            with conn:
                conn.execute(
                    """
                    INSERT INTO active_reader_leases (pid, lease_id, epoch, acquired_at)
                    VALUES (?, ?, ?, ?);
                    """,
                    (proc_pid, lid, target_epoch, now),
                )

        return ReaderLease(
            pid=proc_pid,
            lease_id=lid,
            epoch=target_epoch,
            gen_dir=target_gen_dir,
            acquired_at=now,
            _db_path=self.db_path,
        )

    def release_lease(self, lease_id: str) -> bool:
        """Delete reader lease from SQLite active_reader_leases table."""
        with self._connection() as conn:
            with conn:
                cursor = conn.execute(
                    "DELETE FROM active_reader_leases WHERE lease_id = ?;",
                    (lease_id,),
                )
                return cursor.rowcount > 0

    @contextmanager
    def acquire_lease(self, pid: int | None = None) -> Iterator[ReaderLease]:
        """Context manager acquiring and cleanly releasing a SQLite reader lease."""
        lease = self.register_lease(pid=pid)
        try:
            yield lease
        finally:
            lease.release()

    def count_active_leases(self, epoch: int | None = None) -> int:
        """Count active reader leases registered in SQLite."""
        with self._connection() as conn:
            if epoch is not None:
                row = conn.execute(
                    "SELECT COUNT(*) FROM active_reader_leases WHERE epoch = ?;",
                    (epoch,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM active_reader_leases;").fetchone()
            return int(row[0]) if row else 0

    def compact_and_promote(
        self,
        vectors_data: bytes | None = None,
        fts_atoms_db_source: Path | str | None = None,
        graph_csr_data: bytes | None = None,
        target_epoch: int | None = None,
        num_vectors: int = 50,
    ) -> GenerationInfo:
        """Write compacted generation files into an immutable directory and swap pointer atomically.

        RCU guarantees:
        1. Immutable Generation Directory: generations/gen_{epoch}_{timestamp}/
        2. Files are NEVER overwritten in-place.
        3. Authoritative SQLite pointer swap: one atomic row update.
        4. Deferred unlinking for retired generations with retirement-timestamp grace period.
        """
        current_info = self.active_generation_info
        new_epoch = target_epoch if target_epoch is not None else (current_info.epoch + 1)
        now = time.time()
        ts_millis = int(now * 1000)
        new_gen_dir = self.generations_dir / f"gen_{new_epoch}_{ts_millis}"
        new_gen_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write vectors.bin
        vectors_path = new_gen_dir / "vectors.bin"
        if vectors_data is not None:
            vectors_path.write_bytes(vectors_data)
        elif current_info.vectors_path.exists():
            shutil.copy2(current_info.vectors_path, vectors_path)
        else:
            payload = bytes([new_epoch % 127] * VECTOR_DIM) * num_vectors
            vectors_path.write_bytes(payload)

        # 2. Write fts_atoms.db
        fts_path = new_gen_dir / "fts_atoms.db"
        if fts_atoms_db_source is not None and Path(fts_atoms_db_source).exists():
            shutil.copy2(Path(fts_atoms_db_source), fts_path)
        elif current_info.fts_db_path.exists():
            shutil.copy2(current_info.fts_db_path, fts_path)
        else:
            self._create_generation_files(new_gen_dir, epoch=new_epoch, num_vectors=0)

        # 3. Write graph.csr
        graph_path = new_gen_dir / "graph.csr"
        if graph_csr_data is not None:
            graph_path.write_bytes(graph_csr_data)
        elif current_info.graph_csr_path.exists():
            shutil.copy2(current_info.graph_csr_path, graph_path)
        else:
            csr = CSRGraph(num_nodes=0, indptr=[0], indices=[], types=[], weights=[])
            graph_path.write_bytes(csr.to_bytes())

        # 4. Authoritative atomic SQLite pointer swap
        with self._connection() as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO active_generation (lock_id, epoch, gen_dir, promoted_at)
                    VALUES (1, ?, ?, ?)
                    ON CONFLICT(lock_id) DO UPDATE SET
                        epoch = excluded.epoch,
                        gen_dir = excluded.gen_dir,
                        promoted_at = excluded.promoted_at;
                    """,
                    (new_epoch, str(new_gen_dir), now),
                )

        # 5. Mark previous generation as retired with timestamp
        if current_info.gen_dir.exists():
            try:
                (current_info.gen_dir / ".retired").write_text(str(now))
            except OSError:
                pass

        # 6. Deferred sweep of retired generations
        self.sweep_retired_generations()

        return GenerationInfo(
            epoch=new_epoch,
            gen_dir=new_gen_dir,
            promoted_at=now,
            status="ACTIVE",
        )

    def sweep_retired_generations(
        self,
        force: bool = False,
        grace_seconds: float | None = None,
    ) -> list[Path]:
        """Deferred unlinking and WinError 32 mitigation.

        Retired generations unlink ONLY after:
        1. T_grace = 120s has elapsed since retirement (unless force=True).
        2. AND active reader leases query count on that epoch is ZERO.

        Unlink failures (WinError 32 / PermissionError) are caught cleanly and deferred.
        """
        grace = self.lease_grace_seconds if grace_seconds is None else float(grace_seconds)
        now = time.time()
        unlinked: list[Path] = []

        if not self.generations_dir.exists():
            return unlinked

        # Clean up stale/dead reader leases before evaluating unlink eligibility
        self.cleanup_stale_leases()

        with self._connection() as conn:
            active_info = self.active_generation_info
            active_ep = active_info.epoch
            active_promoted_at = active_info.promoted_at

            for entry in list(self.generations_dir.iterdir()):
                if not entry.is_dir():
                    continue
                name = entry.name
                if not name.startswith("gen_"):
                    continue
                parts = name.split("_")
                try:
                    gen_epoch = int(parts[1])
                except (IndexError, ValueError):
                    continue

                # Invariant: NEVER unlink active generation
                if gen_epoch == active_ep:
                    continue

                # Check active leases in SQLite
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM active_reader_leases WHERE epoch = ?;",
                    (gen_epoch,),
                )
                lease_count = cursor.fetchone()[0]
                if lease_count > 0 and not force:
                    logger.debug(
                        "Generation %s holds %d active leases; skipping deferred unlink",
                        entry.name,
                        lease_count,
                    )
                    continue

                # Check grace period relative to retirement time
                retired_marker = entry / ".retired"
                if retired_marker.exists():
                    try:
                        retired_at = float(retired_marker.read_text().strip())
                    except (ValueError, OSError):
                        retired_at = entry.stat().st_mtime
                elif gen_epoch < active_ep:
                    retired_at = active_promoted_at
                else:
                    retired_at = entry.stat().st_mtime

                elapsed = now - retired_at
                if elapsed < grace and not force:
                    logger.debug(
                        "Generation %s age since retirement %.1fs < grace %.1fs; skipping unlink",
                        entry.name,
                        elapsed,
                        grace,
                    )
                    continue

                # Zero leases + expired grace -> Attempt deferred unlink
                try:
                    shutil.rmtree(entry)
                    unlinked.append(entry)
                    logger.info("Safely unlinked retired generation: %s", entry.name)
                except (PermissionError, OSError) as os_err:
                    # Windows NTFS file lock (WinError 32) or PermissionError: catch & defer
                    logger.warning(
                        "Deferred unlinking of %s due to lock: %s",
                        entry.name,
                        os_err,
                    )

        return unlinked

    def checkpoint_wal_if_needed(
        self,
        conn: sqlite3.Connection | None = None,
        commit_count: int = 1,
    ) -> str | None:
        """Active WAL checkpoint throttling per Appendix A row-7 priors."""
        if commit_count % WAL_PASSIVE_CHECKPOINT_COMMITS != 0:
            return None

        wal_path = Path(str(self.db_path) + "-wal")
        wal_size = wal_path.stat().st_size if wal_path.exists() else 0

        close_conn = False
        if conn is None:
            conn = self._connect()
            close_conn = True

        action = None
        try:
            if wal_size >= WAL_TRUNCATE_THRESHOLD_BYTES:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                action = "TRUNCATE"
            elif wal_size >= WAL_RESTART_THRESHOLD_BYTES:
                time.sleep(0.05)  # 50ms pause per plan
                conn.execute("PRAGMA wal_checkpoint(RESTART);")
                action = "RESTART"
            else:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
                action = "PASSIVE"
        except sqlite3.OperationalError as exc:
            logger.warning("WAL checkpoint deferred due to operational lock/busy: %s", exc)
            action = None
        finally:
            if close_conn:
                conn.close()

        return action

    def measure_storage_footprint(
        self,
        admitted_raw_bytes: int,
    ) -> dict[str, Any]:
        """Empirically measure physical on-disk storage footprint and test storage gate.

        Per CORTICAL_SUBSTRATE_V1_PLAN §0.D1:
        Reports 4 numbers:
        1. durable_bytes: SQLite DB data file + WAL + SHM
        2. retrieval_hot_bytes: active fts_atoms.db + L0 atom storage
        3. cortex_hot_bytes: active vectors.bin + graph.csr
        4. total_hot_bytes: durable + retrieval-hot + cortex-hot

        Storage gate: total-hot <= 3.0x admitted raw text bytes.
        """
        raw_denom = max(1, int(admitted_raw_bytes))

        # 1. Durable Spine footprint
        durable_bytes = 0
        if self.db_path.exists():
            durable_bytes += self.db_path.stat().st_size
        wal_path = Path(str(self.db_path) + "-wal")
        if wal_path.exists():
            durable_bytes += wal_path.stat().st_size
        shm_path = Path(str(self.db_path) + "-shm")
        if shm_path.exists():
            durable_bytes += shm_path.stat().st_size

        # 2. Active generation components
        active_dir = self.active_gen_dir
        retrieval_hot_bytes = 0
        cortex_hot_bytes = 0

        fts_file = active_dir / "fts_atoms.db"
        if fts_file.exists():
            retrieval_hot_bytes += fts_file.stat().st_size

        vec_file = active_dir / "vectors.bin"
        if vec_file.exists():
            cortex_hot_bytes += vec_file.stat().st_size

        graph_file = active_dir / "graph.csr"
        if graph_file.exists():
            cortex_hot_bytes += graph_file.stat().st_size

        total_hot_bytes = durable_bytes + retrieval_hot_bytes + cortex_hot_bytes
        total_hot_mult = round(total_hot_bytes / raw_denom, 4)
        durable_mult = round(durable_bytes / raw_denom, 4)

        return {
            "admitted_raw_bytes": raw_denom,
            "durable_bytes": durable_bytes,
            "durable_multiplier": durable_mult,
            "retrieval_hot_bytes": retrieval_hot_bytes,
            "retrieval_hot_multiplier": round(retrieval_hot_bytes / raw_denom, 4),
            "cortex_hot_bytes": cortex_hot_bytes,
            "cortex_hot_multiplier": round(cortex_hot_bytes / raw_denom, 4),
            "total_hot_bytes": total_hot_bytes,
            "total_hot_multiplier": total_hot_mult,
            "gate_passed": total_hot_mult <= MAX_STORAGE_MULTIPLIER,
            "durable_passed": durable_mult <= MAX_DURABLE_MULTIPLIER,
        }
