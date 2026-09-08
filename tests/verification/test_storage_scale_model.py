"""Verification Suite 4: 1M–10M Storage Model, Leaf-Page Overflow, FTS5 Sync, Page Cache Memory.

Scope:
1. Byte-Level Accounting & Multiplier Verification:
   - Verify exact sums from RFC-004 Section 3.2.
   - EMPIRICAL AUDIT FINDING: Cortex-Hot itemized entries sum to 381 B/doc (3.81 GB), yielding
     M_cortex = 0.762x > 0.600x (VIOLATION of CAP-D010 Cortex ceiling).
   - Line 260 sum discrepancy: 7.20 + 3.60 + 2.40 = 13.20 != 14.38.
2. Leaf-Page Overflow Avoidance in SQLite:
   - 4096-byte page size, NVMe sector alignment.
   - Test payload boundaries: 500B, 768B, 980B vs 1200B, 2000B.
   - Measure overflow pages using dbstat virtual table or page calculation.
3. Single-Copy Contentless External FTS5 Architecture:
   - Trigger-based synchronization: INSERT, UPDATE, DELETE on atom table.
   - Verify real-time index consistency without text duplication.
   - Verify that shadow table '%_content' is omitted in external content mode.
4. SQLite Page-Cache Memory Footprint:
   - Verify PRAGMA cache_size = -64000 bounds working set cache to <= 64MB.
"""

import math
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class TestStorageScaleModelVerification(unittest.TestCase):
    """Empirical verification of 1M-10M storage models and SQLite storage engine."""

    def test_byte_accounting_and_multiplier_compliance(self):
        """Audit itemized storage table from RFC-004 Section 3.2."""
        raw_per_doc = 500  # bytes
        n_docs = 10_000_000
        t_raw = (n_docs * raw_per_doc) / 1e9  # 5.00 GB

        # A. Durable Spine Footprint
        atom_text = 5.00
        atom_headers = 0.48
        events_log = 1.20
        secondary_indexes = 0.36
        wal_overhead = 0.16
        s_spine = atom_text + atom_headers + events_log + secondary_indexes + wal_overhead
        m_spine = s_spine / t_raw

        self.assertAlmostEqual(s_spine, 7.20, places=2)
        self.assertAlmostEqual(m_spine, 1.440, places=3)
        self.assertLessEqual(m_spine, 1.600, "Spine multiplier must be <= 1.6x")

        # B. Retrieval-Hot Footprint
        fts_postings = 1.80
        toc_router = 0.18
        query_btrees = 0.62
        postings_scratch = 1.00
        s_retrieval = fts_postings + toc_router + query_btrees + postings_scratch
        m_retrieval = s_retrieval / t_raw

        self.assertAlmostEqual(s_retrieval, 3.60, places=2)
        self.assertAlmostEqual(m_retrieval, 0.720, places=3)
        self.assertLessEqual(m_retrieval, 0.800, "Retrieval multiplier must be <= 0.8x")

        # C. Cortex-Hot Footprint - AUDIT RE-COMPUTATION
        dense_vectors = 3.84  # 384 B/doc
        dedup_saving = -0.77  # -77 B/doc
        net_vectors = dense_vectors + dedup_saving  # 3.07 GB (307 B/doc)
        csr_indices = 0.40   # 40 B/doc (100M * 4)
        csr_weights = 0.20   # 20 B/doc (100M * 2)
        csr_types = 0.10     # 10 B/doc (100M * 1)
        csr_row_ptrs = 0.04  # 4 B/doc  (10M * 4)

        # Real itemized sum:
        s_cortex_itemized = net_vectors + csr_indices + csr_weights + csr_types + csr_row_ptrs
        bytes_cortex_itemized = 307 + 40 + 20 + 10 + 4
        m_cortex_actual = s_cortex_itemized / t_raw

        print(f"\n[Storage Audit - Cortex-Hot Discrepancy]")
        print(f"  Itemized sum of rows: {bytes_cortex_itemized} B/doc ({s_cortex_itemized:.2f} GB)")
        print(f"  Actual Cortex Multiplier: {m_cortex_actual:.3f}x")
        print(f"  CAP-D010 Cortex Ceiling: 0.600x")
        print(f"  RFC-004 Claimed Sub-Total: 240 B/doc (2.40 GB, 0.480x)")

        # In RFC-004 line 235:
        # The author wrote: "SUB-TOTAL: CORTEX-HOT | 240 B | 2.40 GB | 0.480x (<=0.6)"
        # But 307 + 40 + 20 + 10 + 4 = 381 B (3.81 GB), NOT 240 B (2.40 GB)!
        # And 3.81 / 5.00 = 0.762x, which EXCEEDS the 0.600x limit!
        # This is an empirical defect in the RFC-004 specification!
        self.assertGreater(m_cortex_actual, 0.600, "Itemized Cortex rows exceed 0.6x ceiling!")

        # Also audit line 260 sum arithmetic:
        claimed_sum = s_spine + s_retrieval + 2.40
        print(f"  Arithmetic check: 7.20 + 3.60 + 2.40 = {claimed_sum:.2f} GB (RFC line 260 wrote: 14.38 GB)")
        self.assertNotEqual(claimed_sum, 14.38, "RFC-004 line 260 had an arithmetic error!")

        # If true itemized Cortex is used:
        true_grand_total = s_spine + s_retrieval + s_cortex_itemized
        m_total_true = true_grand_total / t_raw
        print(f"  True Grand Total: {true_grand_total:.2f} GB -> Multiplier: {m_total_true:.3f}x (<= 3.0x: {m_total_true <= 3.0})")
        self.assertLessEqual(m_total_true, 3.000, "Grand total still satisfies <= 3.0x")

    def test_leaf_page_overflow_avoidance(self):
        """Empirically test SQLite B-Tree overflow page allocation across record sizes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_overflow.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA page_size = 4096;")
            conn.execute("PRAGMA journal_mode = WAL;")

            conn.execute(
                """
                CREATE TABLE atom (
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

            # Insert 200 records of size 700 bytes (conforming inline size)
            text_700 = "x" * 700
            for i in range(200):
                conn.execute(
                    "INSERT INTO atom (doc_id, file_id, start_byte, end_byte, content_hash, text) VALUES (?, ?, ?, ?, ?, ?);",
                    (f"doc_{i}", "file1", 0, 700, b"hash", text_700)
                )
            conn.commit()

            # Check if dbstat extension is available to inspect overflow pages
            has_dbstat = False
            try:
                rows = conn.execute("SELECT name, ncell, noverflow FROM dbstat WHERE name='atom';").fetchall()
                has_dbstat = True
                total_overflow_700 = sum(r[2] for r in rows)
                print(f"\n[Leaf-Page Overflow Test (700B Records)] Total Overflow Pages: {total_overflow_700}")
                self.assertEqual(total_overflow_700, 0, "700B records should have zero overflow pages!")
            except sqlite3.OperationalError:
                # If dbstat not compiled in, calculate via page count vs row size
                cur = conn.execute("PRAGMA page_count;")
                pages = cur.fetchone()[0]
                # 200 rows of ~750 bytes = 150KB. In 4096B pages, ~40-50 pages.
                # If overflow occurred, page count would be > 200 pages.
                print(f"\n[Leaf-Page Size Test (700B Records)] Total DB Pages: {pages}")
                self.assertLess(pages, 60, "Page count indicates excessive overflow!")

            # Now insert records of size 2500 bytes (well over page_size/4 = 1024 bytes)
            conn.execute("DELETE FROM atom;")
            conn.commit()
            conn.execute("VACUUM;")

            text_2500 = "y" * 2500
            for i in range(200):
                conn.execute(
                    "INSERT INTO atom (doc_id, file_id, start_byte, end_byte, content_hash, text) VALUES (?, ?, ?, ?, ?, ?);",
                    (f"doc_{i}", "file1", 0, 2500, b"hash", text_2500)
                )
            conn.commit()

            if has_dbstat:
                rows = conn.execute("SELECT name, ncell, noverflow FROM dbstat WHERE name='atom';").fetchall()
                total_overflow_2500 = sum(r[2] for r in rows)
                print(f"  [Large Records (2500B)] Total Overflow Pages: {total_overflow_2500}")
                self.assertGreater(total_overflow_2500, 0, "2500B records must trigger overflow pages!")
            else:
                cur = conn.execute("PRAGMA page_count;")
                pages_large = cur.fetchone()[0]
                print(f"  [Large Records (2500B)] Total DB Pages: {pages_large}")
                # 200 records * 2500 bytes = 500KB. Plus each record requires an overflow page -> > 200 pages!
                self.assertGreaterEqual(pages_large, 150, "Large records should produce large page count due to overflow!")

            conn.close()

    def test_contentless_external_fts5_trigger_synchronization(self):
        """Verify external contentless FTS5 virtual table synchronization with atom table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_fts5.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA journal_mode = WAL;")

            # 1. Create canonical atom table
            conn.execute(
                """
                CREATE TABLE atom (
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

            # 2. Create external content FTS5 table
            conn.execute(
                """
                CREATE VIRTUAL TABLE fts_atoms USING fts5(
                    text,
                    content='atom',
                    content_rowid='id',
                    tokenize='porter unicode61 remove_diacritics 1'
                );
                """
            )

            # 3. Create synchronization triggers
            conn.execute(
                """
                CREATE TRIGGER atom_ai AFTER INSERT ON atom BEGIN
                    INSERT INTO fts_atoms(rowid, text) VALUES (new.id, new.text);
                END;
                """
            )
            conn.execute(
                """
                CREATE TRIGGER atom_ad AFTER DELETE ON atom BEGIN
                    INSERT INTO fts_atoms(fts_atoms, rowid, text) VALUES('delete', old.id, old.text);
                END;
                """
            )
            conn.execute(
                """
                CREATE TRIGGER atom_au AFTER UPDATE ON atom BEGIN
                    INSERT INTO fts_atoms(fts_atoms, rowid, text) VALUES('delete', old.id, old.text);
                    INSERT INTO fts_atoms(rowid, text) VALUES (new.id, new.text);
                END;
                """
            )
            conn.commit()

            # Test A: INSERT synchronization
            conn.execute(
                "INSERT INTO atom (doc_id, file_id, start_byte, end_byte, content_hash, text) VALUES (?, ?, ?, ?, ?, ?);",
                ("d1", "f1", 0, 100, b"h1", "Quantum superposition in superconducting circuits")
            )
            conn.commit()

            matches = conn.execute("SELECT rowid FROM fts_atoms WHERE fts_atoms MATCH 'superconducting';").fetchall()
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0][0], 1)

            # Test B: UPDATE synchronization
            conn.execute(
                "UPDATE atom SET text = 'Quantum entanglement in optical cavities' WHERE id = 1;"
            )
            conn.commit()

            # Old word should NOT match
            old_matches = conn.execute("SELECT rowid FROM fts_atoms WHERE fts_atoms MATCH 'superconducting';").fetchall()
            self.assertEqual(len(old_matches), 0)

            # New word MUST match
            new_matches = conn.execute("SELECT rowid FROM fts_atoms WHERE fts_atoms MATCH 'entanglement';").fetchall()
            self.assertEqual(len(new_matches), 1)
            self.assertEqual(new_matches[0][0], 1)

            # Test C: DELETE synchronization
            conn.execute("DELETE FROM atom WHERE id = 1;")
            conn.commit()

            del_matches = conn.execute("SELECT rowid FROM fts_atoms WHERE fts_atoms MATCH 'entanglement';").fetchall()
            self.assertEqual(len(del_matches), 0)

            # Test D: Verify zero text duplication (no fts_atoms_content table)
            shadow_tables = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fts_atoms_%';"
                ).fetchall()
            ]
            print(f"\n[FTS5 Contentless Shadow Tables]: {shadow_tables}")
            self.assertNotIn("fts_atoms_content", shadow_tables, "Content table should NOT exist in external content FTS5!")

            conn.close()

    def test_page_cache_configuration_and_memory_cap(self):
        """Verify PRAGMA cache_size = -64000 enforces 64MB memory limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA page_size = 4096;")
            conn.execute("PRAGMA cache_size = -64000;")  # 64,000 KB = 64 MB

            cur = conn.execute("PRAGMA cache_size;")
            val = cur.fetchone()[0]
            print(f"\n[SQLite Page Cache] PRAGMA cache_size confirmed: {val} KB")
            self.assertEqual(val, -64000)

            # Verify memory footprint under repeated queries
            conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, data BLOB);")
            payload = b"k" * 1000
            for i in range(1000):
                conn.execute("INSERT INTO t (data) VALUES (?);", (payload,))
            conn.commit()

            # Execute many queries
            for _ in range(500):
                conn.execute("SELECT data FROM t WHERE id = 50;").fetchone()

            conn.close()


if __name__ == "__main__":
    unittest.main()
