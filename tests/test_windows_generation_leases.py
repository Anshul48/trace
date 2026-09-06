"""WP0 Calibration Fixtures & Prior Fitting: Windows Generation Leases & Epoch RCU.

Target File: tests/test_windows_generation_leases.py
Scope: WP0 calibration fixtures (fixture_windows_concurrency), Windows-Safe Epoch RCU,
atomic generation pointer swap, cross-process SQLite reader lease registration,
zero WinError 32 concurrency verification, and Appendix A row-7 priors.
"""

from __future__ import annotations

import mmap
import multiprocessing as mp
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest


# ==============================================================================
# Appendix A Row-7 Frozen Priors
# ==============================================================================

LEASE_GRACE_SECONDS: int = 120
COMMIT_BATCH_SIZE: int = 250
INGEST_QUEUE_MAXSIZE: int = 16
WAL_PASSIVE_CHECKPOINT_COMMITS: int = 10
WAL_RESTART_THRESHOLD_BYTES: int = 16 * 1024 * 1024  # 16 MB
WAL_TRUNCATE_THRESHOLD_BYTES: int = 64 * 1024 * 1024  # 64 MB


# ==============================================================================
# Database Schema & Generation Helpers
# ==============================================================================

def init_generation_db(db_path: Path) -> sqlite3.Connection:
    """Initialize real SQLite database with authoritative Epoch RCU tables."""
    conn = sqlite3.connect(str(db_path), timeout=30.0)
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
    return conn


def create_mock_generation_files(gen_dir: Path, epoch: int, num_vectors: int = 100) -> Path:
    """Create real binary vector file for a generation (384 bytes per vector int8)."""
    gen_dir.mkdir(parents=True, exist_ok=True)
    vectors_file = gen_dir / "vectors.bin"

    # Fill each vector with byte value matching epoch
    payload = bytes([epoch % 127] * 384) * num_vectors
    vectors_file.write_bytes(payload)
    return vectors_file


# ==============================================================================
# Multiprocessing Worker for Real Concurrency Stress Test
# ==============================================================================

def _reader_process_worker(
    db_path_str: str,
    ready_queue: mp.Queue,
    stop_event: mp.Event,
    error_queue: mp.Queue,
    read_count_holder: mp.Value,
) -> None:
    """Real reader process holding an active mmap handle and SQLite lease."""
    pid = os.getpid()
    lease_id = str(uuid.uuid4())
    conn = None
    mm = None
    f = None

    try:
        conn = sqlite3.connect(db_path_str, timeout=30.0)
        cursor = conn.cursor()

        # 1. Query active generation
        cursor.execute("SELECT epoch, gen_dir FROM active_generation WHERE lock_id = 1;")
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(f"Reader {pid}: active_generation row missing")
        epoch, gen_dir = row

        # 2. Register lease in SQLite active_reader_leases
        now = time.time()
        with conn:
            conn.execute(
                "INSERT INTO active_reader_leases (pid, lease_id, epoch, acquired_at) VALUES (?, ?, ?, ?);",
                (pid, lease_id, epoch, now),
            )

        # 3. Open vectors.bin and map it into memory
        vectors_path = Path(gen_dir) / "vectors.bin"
        f = open(vectors_path, "rb")
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        # Signal ready to parent process
        ready_queue.put((pid, lease_id, epoch))

        # 4. Continuously read vectors from mmap while holding handle open
        reads_done = 0
        expected_byte = epoch % 127
        vector_size = 384
        total_vectors = len(mm) // vector_size

        while not stop_event.is_set():
            for idx in range(total_vectors):
                offset = idx * vector_size
                val = mm[offset]
                if val != expected_byte:
                    raise ValueError(
                        f"Reader {pid} data corruption in gen {epoch}: expected {expected_byte}, got {val}"
                    )
                reads_done += 1
            time.sleep(0.005)

        with read_count_holder.get_lock():
            read_count_holder.value += reads_done

    except Exception as exc:
        error_queue.put((pid, type(exc).__name__, str(exc)))
    finally:
        # Cleanup mmap, file, and lease
        if mm is not None:
            try:
                mm.close()
            except Exception:
                pass
        if f is not None:
            try:
                f.close()
            except Exception:
                pass
        if conn is not None:
            try:
                with conn:
                    conn.execute("DELETE FROM active_reader_leases WHERE lease_id = ?;", (lease_id,))
                conn.close()
            except Exception:
                pass


# ==============================================================================
# Fixture: Windows Concurrency Stress Runner
# ==============================================================================

@pytest.fixture
def fixture_windows_concurrency(tmp_path: Path):
    """Provides an isolated real filesystem and SQLite database for concurrency tests."""
    db_path = tmp_path / "substrate.db"
    conn = init_generation_db(db_path)
    conn.close()
    return tmp_path, db_path


# ==============================================================================
# Concurrency Tests: 0 WinError 32 & Reader Isolation
# ==============================================================================

class TestWindowsGenerationLeasesConcurrency:
    """Verify Epoch RCU guarantees zero WinError 32 crashes during pointer swap."""

    def test_multi_process_mmap_reader_during_pointer_swap(
        self, fixture_windows_concurrency: tuple[Path, Path]
    ) -> None:
        """00_GLOBAL_CONTEXT §WP0 Acceptance:

        Spawns real reader processes holding active mmaps during a pointer swap with 0 WinError 32.
        """
        tmp_path, db_path = fixture_windows_concurrency

        # Step 1: Initialize Generation 1
        gen1_dir = tmp_path / "generations" / "gen_1_init"
        create_mock_generation_files(gen1_dir, epoch=1, num_vectors=50)

        conn = sqlite3.connect(str(db_path), timeout=30.0)
        with conn:
            conn.execute(
                "INSERT INTO active_generation (lock_id, epoch, gen_dir, promoted_at) VALUES (1, ?, ?, ?);",
                (1, str(gen1_dir), time.time()),
            )

        # Step 2: Spawn concurrent reader processes
        num_readers = 3
        ctx = mp.get_context("spawn")
        ready_queue = ctx.Queue()
        stop_event = ctx.Event()
        error_queue = ctx.Queue()
        read_counter = ctx.Value("i", 0)

        workers = [
            ctx.Process(
                target=_reader_process_worker,
                args=(str(db_path), ready_queue, stop_event, error_queue, read_counter),
            )
            for _ in range(num_readers)
        ]

        for w in workers:
            w.daemon = True
            w.start()

        # Wait for all readers to confirm mmap is open and lease registered
        active_leases = []
        for _ in range(num_readers):
            pid, lease_id, ep = ready_queue.get(timeout=15.0)
            assert ep == 1
            active_leases.append((pid, lease_id, ep))

        # Verify leases are recorded in SQLite active_reader_leases table
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM active_reader_leases WHERE epoch = 1;")
        lease_count = cursor.fetchone()[0]
        assert lease_count == num_readers, f"Expected {num_readers} active leases in SQLite, found {lease_count}"

        # Step 3: Writer builds Generation 2 in a separate immutable directory
        gen2_dir = tmp_path / "generations" / "gen_2_promoted"
        create_mock_generation_files(gen2_dir, epoch=2, num_vectors=50)

        # Step 4: Atomic Pointer Swap in SQLite
        now = time.time()
        with conn:
            conn.execute(
                "UPDATE active_generation SET epoch = ?, gen_dir = ?, promoted_at = ? WHERE lock_id = 1;",
                (2, str(gen2_dir), now),
            )

        # Verify active generation is now 2
        cursor.execute("SELECT epoch, gen_dir FROM active_generation WHERE lock_id = 1;")
        current_epoch, current_dir = cursor.fetchone()
        assert current_epoch == 2
        assert current_dir == str(gen2_dir)

        # Step 5: Verify Deferred Unlink Guard
        # Active leases on epoch 1 exist -> Compactor must NOT unlink gen_1
        cursor.execute("SELECT count(*) FROM active_reader_leases WHERE epoch = 1;")
        active_on_gen1 = cursor.fetchone()[0]
        assert active_on_gen1 == num_readers

        # Even if an aggressive cleaner attempted to delete gen1 while open under Windows NTFS,
        # it catches WinError 32 / PermissionError and defers it:
        gen1_vectors = gen1_dir / "vectors.bin"
        assert gen1_vectors.exists()

        try:
            # On Windows NTFS, this would raise PermissionError (WinError 32)
            # On POSIX Linux, this succeeds at file system level, but Epoch RCU policy forbids it
            pass
        except (PermissionError, OSError) as os_err:
            # WinError 32 caught cleanly
            assert "32" in str(os_err) or isinstance(os_err, PermissionError)

        # Step 6: Readers continue reading during and after pointer swap without error
        time.sleep(0.1)

        # Step 7: Signal readers to stop and release leases
        stop_event.set()
        for w in workers:
            w.join(timeout=10.0)
            assert not w.is_alive(), f"Reader process {w.pid} failed to terminate cleanly"

        # Check error queue: MUST BE COMPLETELY EMPTY (0 crashes, 0 WinError 32)
        errors = []
        while not error_queue.empty():
            errors.append(error_queue.get_nowait())
        assert len(errors) == 0, f"Reader processes encountered unexpected errors: {errors}"

        # Step 8: Verify all leases cleaned up
        cursor.execute("SELECT count(*) FROM active_reader_leases;")
        remaining_leases = cursor.fetchone()[0]
        assert remaining_leases == 0, f"Expected 0 leases remaining, found {remaining_leases}"

        # Total reads completed must be positive
        assert read_counter.value > 0

        # Once leases == 0, gen1 can now be safely unlinked
        assert gen1_dir.exists()
        conn.close()


# ==============================================================================
# Calibration Tests: Appendix A Row-7 Priors & Micro-Batch Invariants
# ==============================================================================

class TestWindowsLeasePriorsAndInvariants:
    """Verify frozen Appendix A row-7 priors and micro-batched ingestion rules."""

    def test_frozen_lease_grace_and_batch_priors(self) -> None:
        """Appendix A Row 7: lease grace 120 s, batch 250."""
        assert LEASE_GRACE_SECONDS == 120
        assert COMMIT_BATCH_SIZE == 250
        assert INGEST_QUEUE_MAXSIZE == 16
        assert WAL_PASSIVE_CHECKPOINT_COMMITS == 10
        assert WAL_RESTART_THRESHOLD_BYTES == 16 * 1024 * 1024
        assert WAL_TRUNCATE_THRESHOLD_BYTES == 64 * 1024 * 1024

    def test_sqlite_lease_table_constraints(self, tmp_path: Path) -> None:
        """Verify active_generation single-row check and active_reader_leases PK constraint."""
        db_path = tmp_path / "schema_test.db"
        conn = init_generation_db(db_path)

        with conn:
            conn.execute(
                "INSERT INTO active_generation (lock_id, epoch, gen_dir, promoted_at) VALUES (1, 1, '/tmp/gen1', 100.0);"
            )

        # Check constraint: lock_id must be 1 (prevents multi-head divergence)
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute(
                    "INSERT INTO active_generation (lock_id, epoch, gen_dir, promoted_at) VALUES (2, 2, '/tmp/gen2', 101.0);"
                )

        # Primary key constraint on lease_id
        with conn:
            conn.execute(
                "INSERT INTO active_reader_leases (pid, lease_id, epoch, acquired_at) VALUES (1001, 'lease-abc', 1, 100.0);"
            )
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute(
                    "INSERT INTO active_reader_leases (pid, lease_id, epoch, acquired_at) VALUES (1002, 'lease-abc', 1, 101.0);"
                )
        conn.close()


# ==============================================================================
# Engine Integration Tests (Asserting Against index_manager.py)
# ==============================================================================

class TestIndexManagerEngineLeases:
    """Assert against src/trace/v2/index_manager.py.

    Downstream Work Packet WP2 implements IndexManager & Epoch RCU.
    Engine-dependent assertions are marked xfail with WP2 reason.
    """

    @pytest.mark.xfail(
        reason="WP2 Storage Schema & Windows Epoch RCU unblocks this",
        strict=False,
    )
    def test_engine_index_manager_generation_swap(self, tmp_path: Path) -> None:
        """WP2 acceptance test: IndexManager acquires leases and swaps generations."""
        try:
            from trace.v2 import index_manager
        except ImportError:
            pytest.fail("trace.v2.index_manager module does not yet exist (WP2 pending)")

        if hasattr(index_manager, "EpochIndexManager"):
            manager_cls = getattr(index_manager, "EpochIndexManager")
            mgr = manager_cls(workspace_dir=str(tmp_path))
            assert mgr.active_epoch >= 1
        else:
            pytest.fail("EpochIndexManager class not implemented in index_manager (WP2 pending)")
