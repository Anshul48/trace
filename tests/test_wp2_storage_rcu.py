"""WP2 Acceptance Test Suite: Storage Schema Migration & Windows Epoch RCU.

Target File: tests/test_wp2_storage_rcu.py
Scope: WP2 Storage Schema & Windows Epoch RCU.
- Tables: atom (canonical L0 text), fts_atoms external-content FTS5 (content='atom', content_rowid='id'),
  holons (int8 blob + lex_sig JSON top-32 strings + spans/energy/tier/status), toc, edges,
  active_reader_leases(pid, lease_id, epoch), active_generation(single-row pointer).
- RCU: compactions write generations/gen_{epoch}_{timestamp}/, pointer swap is one atomic row update,
  readers hold SQLite leases, retired generations unlink after 120 s grace + zero leases.
- Acceptance: total-hot <= 3.0x MEASURED on disk; test_windows_generation_leases.py passes under
  multiprocess load; full tests/ regression clean.
"""

from __future__ import annotations

import hashlib
import mmap
import multiprocessing as mp
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trace.v2.store import SqliteEventStore
from trace.v2.index_manager import (
    COMMIT_BATCH_SIZE,
    CSRGraph,
    EpochIndexManager,
    INGEST_QUEUE_MAXSIZE,
    LEASE_GRACE_SECONDS,
    MAX_DURABLE_MULTIPLIER,
    MAX_STORAGE_MULTIPLIER,
    VECTOR_BYTES_PER_ITEM,
    VECTOR_DIM,
    WAL_PASSIVE_CHECKPOINT_COMMITS,
    WAL_RESTART_THRESHOLD_BYTES,
    WAL_TRUNCATE_THRESHOLD_BYTES,
    init_generation_db,
)


# ==============================================================================
# 1. Database Schema & Invariants Tests
# ==============================================================================

class TestWP2StorageSchema:
    """Verify SQLite database schema additions in store.py."""

    def test_schema_tables_and_views_created(self, tmp_path: Path) -> None:
        """Verify all WP2 tables, views, and indexes are created in real SQLite."""
        db_path = tmp_path / "test_store.db"
        store = SqliteEventStore(str(db_path))

        with store.transaction() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view');"
                ).fetchall()
            }

            # Required tables per WP2 spec
            assert "atom" in tables
            assert "fts_atoms" in tables
            assert "holons" in tables
            assert "holon" in tables  # view
            assert "toc" in tables
            assert "edges" in tables
            assert "edge" in tables   # view
            assert "active_generation" in tables
            assert "active_reader_leases" in tables

        store.close()

    def test_atom_byte_exact_provenance_and_fts_sync(self, tmp_path: Path) -> None:
        """Verify L0 atom byte-exact provenance and automatic external-content FTS5 sync."""
        db_path = tmp_path / "test_provenance.db"
        store = SqliteEventStore(str(db_path))

        full_doc = "The cortical substrate provides an episodic ground with immutable atom representations."
        # normalized span
        start = 4
        end = 22
        expected_span = full_doc[start:end]  # 'cortical substrate'
        assert expected_span == "cortical substrate"

        content_hash = hashlib.sha256(expected_span.encode("utf-8")).digest()

        atom_id = store.insert_atom(
            doc_id="doc_001",
            file_id="file_001",
            start_byte=start,
            end_byte=end,
            content_hash=content_hash,
            text=expected_span,
        )

        atom = store.get_atom(atom_id)
        assert atom is not None
        assert atom["text"] == expected_span
        assert atom["start_byte"] == start
        assert atom["end_byte"] == end
        assert atom["content_hash"] == content_hash
        # Byte exactness invariant: text == full_doc[start:end]
        assert atom["text"] == full_doc[atom["start_byte"]:atom["end_byte"]]

        # External-content FTS5 search (zero duplicate text, automatically indexed)
        hits = store.search_fts_atoms("substrate")
        assert len(hits) >= 1
        assert hits[0]["id"] == atom_id
        assert hits[0]["text"] == expected_span

        store.close()

    def test_holons_storage_contract(self, tmp_path: Path) -> None:
        """Verify holon schema: 384-byte int8 blob, top-32 strings JSON, spans JSON."""
        db_path = tmp_path / "test_holons.db"
        store = SqliteEventStore(str(db_path))

        centroid_384 = bytes([42] * 384)
        top_tokens = [f"token_{i}" for i in range(32)]
        spans = [[0, 50], [100, 150]]

        store.insert_holons(
            [
                {
                    "id": "holon_0001",
                    "parent_toc": "toc_001",
                    "centroid_int8": centroid_384,
                    "lex_sig": top_tokens,
                    "spans": spans,
                    "energy": 2.5,
                    "tier": "nav",
                    "status": "ACTIVE",
                    "version": 1,
                    "anchor_model": "intfloat/e5-small-v2",
                    "anchor_prompt_hash": "a" * 64,
                }
            ]
        )

        h = store.get_holon("holon_0001")
        assert h is not None
        assert h["id"] == "holon_0001"
        assert h["parent_toc"] == "toc_001"
        assert len(h["centroid_int8"]) == 384
        assert h["centroid_int8"] == centroid_384
        assert len(h["lex_sig"]) == 32
        assert h["lex_sig"] == top_tokens
        assert h["spans"] == spans
        assert h["energy"] == 2.5
        assert h["tier"] == "nav"
        assert h["status"] == "ACTIVE"

        store.close()

    def test_toc_and_edges_storage(self, tmp_path: Path) -> None:
        """Verify TOC routing nodes and explicit graph edges."""
        db_path = tmp_path / "test_toc_edges.db"
        store = SqliteEventStore(str(db_path))

        c0_bytes = bytes([0] * (384 * 4))  # float32 array
        members = ["holon_0001", "holon_0002"]
        boundary = {"cohesion_floor": 0.08, "radius": 0.25}

        store.insert_toc_nodes(
            [
                {
                    "id": "toc_0001",
                    "parent": None,
                    "c0": c0_bytes,
                    "r0": 0.25,
                    "members": members,
                    "boundary": boundary,
                    "status": "ACTIVE",
                }
            ]
        )

        toc_node = store.get_toc_node("toc_0001")
        assert toc_node is not None
        assert toc_node["id"] == "toc_0001"
        assert toc_node["r0"] == 0.25
        assert toc_node["members"] == members
        assert toc_node["boundary"] == boundary

        store.insert_edges(
            [
                {
                    "src": "holon_0001",
                    "dst": "holon_0002",
                    "type": "SEE_ALSO",
                    "weight": 0.85,
                }
            ]
        )

        edges = store.get_edges(src="holon_0001")
        assert len(edges) == 1
        assert edges[0]["dst"] == "holon_0002"
        assert edges[0]["type"] == "SEE_ALSO"
        assert edges[0]["weight"] == 0.85

        store.close()


# ==============================================================================
# 2. Windows Epoch RCU & Index Manager Lifecycle Tests
# ==============================================================================

class TestEpochIndexManagerLifecycle:
    """Verify EpochIndexManager compaction, pointer swap, leases, and deferred unlinking."""

    def test_manager_initialization_and_active_generation(self, tmp_path: Path) -> None:
        """Verify baseline generation 1 is created upon manager initialization."""
        mgr = EpochIndexManager(workspace_dir=tmp_path)
        assert mgr.active_epoch == 1
        assert mgr.active_gen_dir.exists()
        assert (mgr.active_gen_dir / "vectors.bin").exists()
        assert (mgr.active_gen_dir / "fts_atoms.db").exists()
        assert (mgr.active_gen_dir / "graph.csr").exists()

    def test_compaction_and_atomic_pointer_swap(self, tmp_path: Path) -> None:
        """Verify compaction writes immutable generation and performs atomic SQLite swap."""
        mgr = EpochIndexManager(workspace_dir=tmp_path)
        assert mgr.active_epoch == 1
        old_dir = mgr.active_gen_dir

        # Compact and promote to generation 2
        custom_vectors = bytes([2] * 384) * 20
        gen2 = mgr.compact_and_promote(vectors_data=custom_vectors, target_epoch=2)

        assert mgr.active_epoch == 2
        assert gen2.epoch == 2
        assert gen2.gen_dir != old_dir
        assert gen2.gen_dir.exists()
        assert (gen2.gen_dir / "vectors.bin").read_bytes() == custom_vectors
        # Old generation directory remains intact (deferred unlinking)
        assert old_dir.exists()

    def test_reader_lease_registration_and_active_tracking(self, tmp_path: Path) -> None:
        """Verify cross-process reader leases in SQLite active_reader_leases."""
        mgr = EpochIndexManager(workspace_dir=tmp_path)
        assert mgr.count_active_leases() == 0

        with mgr.acquire_lease() as lease:
            assert lease.epoch == 1
            assert lease.gen_dir == mgr.active_gen_dir
            assert mgr.count_active_leases(epoch=1) == 1

            # Open mmap under lease
            mm = lease.open_vectors_mmap()
            assert mm is not None
            assert len(mm) > 0

        # After exiting context manager, lease is automatically released
        assert mgr.count_active_leases() == 0

    def test_deferred_unlinking_grace_period_and_lease_guard(self, tmp_path: Path) -> None:
        """Verify retired generations unlink only after grace period AND zero leases."""
        mgr = EpochIndexManager(workspace_dir=tmp_path, lease_grace_seconds=0.5)
        gen1_dir = mgr.active_gen_dir

        # Reader acquires lease on generation 1
        lease = mgr.register_lease(epoch=1)
        assert mgr.count_active_leases(epoch=1) == 1

        # Writer promotes to generation 2
        mgr.compact_and_promote(target_epoch=2)
        assert mgr.active_epoch == 2

        # 1. Sweep while lease is active: MUST NOT unlink gen1
        unlinked = mgr.sweep_retired_generations(force=False)
        assert len(unlinked) == 0
        assert gen1_dir.exists()

        # 2. Release lease, but grace period has not expired: MUST NOT unlink gen1
        lease.release()
        assert mgr.count_active_leases(epoch=1) == 0

        # Sweep immediately with long grace: does not unlink
        unlinked = mgr.sweep_retired_generations(force=False, grace_seconds=100.0)
        assert len(unlinked) == 0
        assert gen1_dir.exists()

        # 3. Grace period expired AND leases == 0: MUST unlink safely
        time.sleep(0.8)
        unlinked = mgr.sweep_retired_generations(force=False, grace_seconds=0.5)
        assert len(unlinked) == 1
        assert not gen1_dir.exists()

    def test_winerror_32_mitigation(self, tmp_path: Path) -> None:
        """Verify PermissionError / file-locking during unlinking is caught and deferred."""
        mgr = EpochIndexManager(workspace_dir=tmp_path, lease_grace_seconds=120.0)
        gen1_dir = mgr.active_gen_dir
        mgr.compact_and_promote(target_epoch=2)
        assert gen1_dir.exists()

        # Real filesystem permission restriction (zero mocks): revoke write permission on generations dir
        orig_mode = mgr.generations_dir.stat().st_mode
        try:
            os.chmod(mgr.generations_dir, 0o555)
            # Sweep must catch the PermissionError cleanly without crashing
            unlinked = mgr.sweep_retired_generations(force=True)
            assert len(unlinked) == 0
            assert gen1_dir.exists()
        finally:
            os.chmod(mgr.generations_dir, orig_mode)


# ==============================================================================
# 3. Micro-Batched Ingestion & WAL Throttling Tests
# ==============================================================================

class TestWALThrottlingAndPriors:
    """Verify Appendix A row-7 priors and active WAL checkpoint throttling."""

    def test_priors_frozen_values(self) -> None:
        """Verify Appendix A row 7 frozen constants."""
        assert LEASE_GRACE_SECONDS == 120
        assert COMMIT_BATCH_SIZE == 250
        assert INGEST_QUEUE_MAXSIZE == 16
        assert WAL_PASSIVE_CHECKPOINT_COMMITS == 10
        assert WAL_RESTART_THRESHOLD_BYTES == 16 * 1024 * 1024
        assert WAL_TRUNCATE_THRESHOLD_BYTES == 64 * 1024 * 1024
        assert VECTOR_DIM == 384
        assert VECTOR_BYTES_PER_ITEM == 384
        assert MAX_STORAGE_MULTIPLIER == 3.0

    def test_wal_checkpoint_throttling_triggers(self, tmp_path: Path) -> None:
        """Verify passive, restart, and truncate checkpoint throttling."""
        mgr = EpochIndexManager(workspace_dir=tmp_path)

        # Commit count not multiple of 10: returns None
        assert mgr.checkpoint_wal_if_needed(commit_count=1) is None
        assert mgr.checkpoint_wal_if_needed(commit_count=9) is None

        # Commit count multiple of 10: triggers checkpoint
        action = mgr.checkpoint_wal_if_needed(commit_count=10)
        assert action in {"PASSIVE", "RESTART", "TRUNCATE"}


# ==============================================================================
# 4. Storage Gate Acceptance: Total-Hot <= 3.0x MEASURED On Disk
# ==============================================================================

class TestStorageGateFootprint:
    """Verify total-hot <= 3.0x measured on real disk against admitted raw text."""

    def test_storage_gate_measurement_on_disk(self, tmp_path: Path) -> None:
        """Empirically measure physical on-disk byte footprint and assert total-hot <= 3.0x."""
        mgr = EpochIndexManager(workspace_dir=tmp_path)

        # Populate a realistic batch of atoms and vectors
        # Let raw admitted text be 1,000 documents of 2,000 bytes each = 2,000,000 bytes
        num_docs = 1000
        doc_len = 2000
        raw_admitted_bytes = num_docs * doc_len

        # Write atoms to SQLite DB
        store = SqliteEventStore(str(mgr.db_path))
        atoms = []
        for i in range(num_docs):
            sample_text = f"Document {i:04d}: " + ("cortical episodic evidence substrate " * 45)[:doc_len - 15]
            h = hashlib.sha256(sample_text.encode("utf-8")).digest()
            atoms.append({
                "id": i + 1,
                "doc_id": f"doc_{i}",
                "file_id": f"file_{i}",
                "start_byte": 0,
                "end_byte": len(sample_text),
                "content_hash": h,
                "text": sample_text,
            })
        store.insert_atoms(atoms)
        store.close()

        # Checkpoint WAL before compaction to sync committed pages
        conn = sqlite3.connect(str(mgr.db_path))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.close()

        # Write corresponding generation vectors (384-d int8 per holon = 384 bytes * 1000 = 384,000 bytes)
        vectors_data = bytes([1] * 384) * num_docs
        # Write compact CSR graph
        csr = CSRGraph(
            num_nodes=num_docs,
            indptr=list(range(num_docs + 1)),
            indices=list(range(num_docs)),
            types=[1] * num_docs,
            weights=[1.0] * num_docs,
        )

        mgr.compact_and_promote(
            vectors_data=vectors_data,
            graph_csr_data=csr.to_bytes(),
            target_epoch=2,
        )

        # Measure real physical on-disk footprint
        report = mgr.measure_storage_footprint(admitted_raw_bytes=raw_admitted_bytes)

        # Assert 4 required numbers are present
        assert "durable_bytes" in report
        assert "retrieval_hot_bytes" in report
        assert "cortex_hot_bytes" in report
        assert "total_hot_bytes" in report

        # Acceptance Gate: total-hot <= 3.0x MEASURED on disk
        total_mult = report["total_hot_multiplier"]
        durable_mult = report["durable_multiplier"]

        assert report["gate_passed"] is True, f"Total hot multiplier {total_mult}x exceeds 3.0x limit"
        assert total_mult <= 3.0, f"Measured total-hot multiplier {total_mult}x > 3.0x"
        assert durable_mult <= 1.6, f"Measured durable multiplier {durable_mult}x > 1.6x"


# ==============================================================================
# 5. Multiprocess Concurrency Stress Test
# ==============================================================================

def _multiprocess_reader_worker(
    workspace_dir_str: str,
    ready_q: mp.Queue,
    stop_evt: mp.Event,
    err_q: mp.Queue,
    read_counter: mp.Value,
) -> None:
    """Real child process holding an EpochIndexManager lease and reading mmaps."""
    pid = os.getpid()
    mgr = EpochIndexManager(workspace_dir=workspace_dir_str, auto_init=False)

    try:
        with mgr.acquire_lease(pid=pid) as lease:
            ready_q.put((pid, lease.lease_id, lease.epoch))

            mm = lease.open_vectors_mmap()
            reads = 0
            while not stop_evt.is_set():
                if mm is not None and len(mm) >= 384:
                    # Verify read
                    byte_val = mm[0]
                    reads += 1
                time.sleep(0.005)

            with read_counter.get_lock():
                read_counter.value += reads

    except Exception as exc:
        err_q.put((pid, type(exc).__name__, str(exc)))
        ready_q.put((pid, "ERROR", -1))


class TestMultiprocessEpochRCU:
    """Real multiprocess stress tests with zero WinError 32."""

    def test_multiprocess_readers_during_generation_swap(self, tmp_path: Path) -> None:
        """Verify concurrent reader subprocesses during compaction and pointer swap."""
        mgr = EpochIndexManager(workspace_dir=tmp_path)
        assert mgr.active_epoch == 1

        ctx = mp.get_context("spawn")
        ready_q = ctx.Queue()
        stop_evt = ctx.Event()
        err_q = ctx.Queue()
        read_counter = ctx.Value("i", 0)

        num_workers = 3
        workers = [
            ctx.Process(
                target=_multiprocess_reader_worker,
                args=(str(tmp_path), ready_q, stop_evt, err_q, read_counter),
            )
            for _ in range(num_workers)
        ]

        for w in workers:
            w.daemon = True
            w.start()

        # Wait for all readers to acquire lease and signal ready
        leases = []
        for _ in range(num_workers):
            item = ready_q.get(timeout=30.0)
            if item[1] == "ERROR":
                err = err_q.get(timeout=5.0) if not err_q.empty() else "Unknown worker error"
                pytest.fail(f"Worker {item[0]} failed on startup: {err}")
            leases.append(item)

        assert len(leases) == num_workers
        assert mgr.count_active_leases(epoch=1) == num_workers

        # Writer promotes to generation 2 while readers are actively reading
        gen2_vectors = bytes([2] * 384) * 20
        mgr.compact_and_promote(vectors_data=gen2_vectors, target_epoch=2)
        assert mgr.active_epoch == 2

        time.sleep(0.2)

        # Stop readers
        stop_evt.set()
        for w in workers:
            w.join(timeout=10.0)
            assert not w.is_alive()

        # Verify no errors occurred in child processes
        errors = []
        while not err_q.empty():
            errors.append(err_q.get_nowait())
        assert len(errors) == 0, f"Child processes encountered errors: {errors}"

        # Verify all leases released
        assert mgr.count_active_leases() == 0
        assert read_counter.value > 0


# ==============================================================================
# 6. Edge Cases & Attack Vector Tests
# ==============================================================================

class TestEdgeCasesAndRCURobustness:
    """Verify edge cases, dead process cleanup, CSR round-trip, and input validation."""

    def test_csr_graph_binary_roundtrip(self) -> None:
        """Verify CSRGraph to_bytes and from_bytes round-trip serialization."""
        # Case 1: Empty graph
        empty_csr = CSRGraph(num_nodes=0, indptr=[0], indices=[], types=[], weights=[])
        raw_empty = empty_csr.to_bytes()
        restored_empty = CSRGraph.from_bytes(raw_empty)
        assert restored_empty.num_nodes == 0
        assert restored_empty.indptr == [0]
        assert restored_empty.indices == []
        assert restored_empty.types == []
        assert restored_empty.weights == []

        # Case 2: Multi-node multi-edge graph
        csr = CSRGraph(
            num_nodes=4,
            indptr=[0, 2, 3, 5, 6],
            indices=[1, 2, 0, 1, 3, 2],
            types=[1, 2, 1, 3, 2, 1],
            weights=[0.1, 0.5, 0.9, 0.25, 0.75, 1.0],
        )
        data = csr.to_bytes()
        restored = CSRGraph.from_bytes(data)
        assert restored.num_nodes == csr.num_nodes
        assert restored.indptr == csr.indptr
        assert restored.indices == csr.indices
        assert restored.types == csr.types
        assert len(restored.weights) == len(csr.weights)
        for w1, w2 in zip(csr.weights, restored.weights):
            assert abs(w1 - w2) < 1e-6

    def test_stale_pid_lease_cleanup_on_process_crash(self, tmp_path: Path) -> None:
        """Reviewer attack target: dead process PID lease is safely cleaned up and allows retired generation sweep."""
        mgr = EpochIndexManager(workspace_dir=tmp_path, lease_grace_seconds=0.1)
        gen1_dir = mgr.active_gen_dir

        # Simulate a reader process that crashed / terminated abruptly (PID 9999999 is not running)
        fake_dead_pid = 9999999
        lease = mgr.register_lease(pid=fake_dead_pid, epoch=1)
        assert mgr.count_active_leases(epoch=1) == 1

        # Writer promotes to generation 2
        mgr.compact_and_promote(target_epoch=2)
        assert mgr.active_epoch == 2

        # Generation 1 has 1 lease belonging to a dead PID
        # Clean stale leases and sweep
        time.sleep(0.15)  # Grace expired
        unlinked = mgr.sweep_retired_generations(force=False, grace_seconds=0.1)

        # Stale lease should be pruned and retired generation successfully unlinked
        assert len(unlinked) == 1
        assert not gen1_dir.exists()
        assert mgr.count_active_leases() == 0

    def test_retirement_grace_period_calculation(self, tmp_path: Path) -> None:
        """Verify grace period is measured from RETIREMENT time, not directory creation time."""
        # Set grace to 0.4 seconds
        mgr = EpochIndexManager(workspace_dir=tmp_path, lease_grace_seconds=0.4)
        gen1_dir = mgr.active_gen_dir

        # Let 0.2s pass while Gen 1 is actively running
        time.sleep(0.2)

        # Promote to Gen 2: Gen 1 is retired AT THIS MOMENT
        mgr.compact_and_promote(target_epoch=2)
        assert mgr.active_epoch == 2

        # Immediately sweep: Gen 1 was retired 0.0s ago (< 0.4s grace) -> MUST NOT BE UNLINKED
        unlinked = mgr.sweep_retired_generations(force=False, grace_seconds=0.4)
        assert len(unlinked) == 0
        assert gen1_dir.exists()

        # Wait until grace elapsed since retirement
        time.sleep(0.45)
        unlinked = mgr.sweep_retired_generations(force=False, grace_seconds=0.4)
        assert len(unlinked) == 1
        assert not gen1_dir.exists()

    def test_fts_atoms_query_robustness(self, tmp_path: Path) -> None:
        """Verify search_fts_atoms handles special characters and syntax gracefully."""
        db_path = tmp_path / "fts_robust.db"
        store = SqliteEventStore(str(db_path))

        store.insert_atom(
            doc_id="d1",
            file_id="f1",
            start_byte=0,
            end_byte=22,
            content_hash="aabbccdd" * 8,
            text="hello (world) testing*",
        )

        # Queries with special FTS syntax characters should not crash
        hits = store.search_fts_atoms("hello (world")
        assert len(hits) >= 1
        assert hits[0]["text"] == "hello (world) testing*"

        hits_empty = store.search_fts_atoms("")
        assert hits_empty == []

        hits_star = store.search_fts_atoms("testing*")
        assert len(hits_star) >= 1

        store.close()

    def test_atom_validation_and_nonhex_hash(self, tmp_path: Path) -> None:
        """Verify input validation for start/end bytes and non-hex content_hash."""
        db_path = tmp_path / "atom_val.db"
        store = SqliteEventStore(str(db_path))

        # Invalid bounds: end_byte < start_byte must raise ValueError
        with pytest.raises(ValueError):
            store.insert_atom(
                doc_id="d1",
                file_id="f1",
                start_byte=50,
                end_byte=10,
                content_hash=b"hash",
                text="invalid",
            )

        # Arbitrary non-hex string with even length: should not crash with ValueError
        atom_id = store.insert_atom(
            doc_id="d2",
            file_id="f2",
            start_byte=0,
            end_byte=6,
            content_hash="nothex",  # len 6, even, not hex!
            text="hello!",
        )
        atom = store.get_atom(atom_id)
        assert atom is not None
        assert atom["text"] == "hello!"

        store.close()

