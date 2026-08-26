from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trace.v2.migrations import MigrationRunner


class _RecordingCursor:
    def __init__(self, migration_sql: set[str]) -> None:
        self.ledger: dict[int, tuple[str, str]] = {}
        self.migration_sql = migration_sql
        self.executed_migrations: list[str] = []
        self._rows: list[tuple[int, str, str]] = []

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: str, parameters: tuple[object, ...] | None = None) -> None:
        normalized = " ".join(statement.split())
        if normalized.startswith("SELECT revision,name,checksum FROM trace_schema_migrations"):
            self._rows = [
                (revision, name, checksum)
                for revision, (name, checksum) in sorted(self.ledger.items())
            ]
        elif normalized.startswith("INSERT INTO trace_schema_migrations"):
            assert parameters is not None
            revision, name, checksum = parameters
            self.ledger[int(revision)] = (str(name), str(checksum))
        elif statement in self.migration_sql:
            self.executed_migrations.append(statement)

    def fetchall(self) -> list[tuple[int, str, str]]:
        return self._rows


class _RecordingConnection:
    def __init__(self, migration_sql: set[str]) -> None:
        self.cursor_instance = _RecordingCursor(migration_sql)

    def cursor(self) -> _RecordingCursor:
        return self.cursor_instance


class EventPartitionBootstrapContractTests(unittest.TestCase):
    def test_hash_parent_has_complete_explicit_routing_without_a_default(self) -> None:
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "001_trace_production.sql"
        ).read_text(encoding="utf-8")

        self.assertNotRegex(
            migration,
            r"PARTITION\s+OF\s+trace_events\s+DEFAULT",
            "a hash-partitioned PostgreSQL parent cannot own a DEFAULT partition",
        )
        partitions = re.findall(
            r"CREATE TABLE IF NOT EXISTS trace_events_h(\d{2}) "
            r"PARTITION OF trace_events FOR VALUES WITH \(MODULUS 16, REMAINDER (\d+)\)",
            migration,
        )
        self.assertEqual(
            {(int(bucket), int(remainder)) for bucket, remainder in partitions},
            {(value, value) for value in range(16)},
        )
        defaults = re.findall(
            r"CREATE TABLE IF NOT EXISTS trace_events_h(\d{2})_default "
            r"PARTITION OF trace_events_h\1 DEFAULT",
            migration,
        )
        self.assertEqual({int(bucket) for bucket in defaults}, set(range(16)))

    def test_migration_runner_records_the_repaired_baseline_once(self) -> None:
        root = Path(__file__).resolve().parents[1] / "migrations"
        runner = MigrationRunner(root)
        connection = _RecordingConnection({migration.sql for migration in runner.discover()})

        first = runner.apply(connection)
        first_execution_count = len(connection.cursor_instance.executed_migrations)
        second = runner.apply(connection)
        self.assertEqual([migration.revision for migration in first], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual([migration.revision for migration in second], [1, 2, 3, 4, 5, 6, 7])

        self.assertEqual(first_execution_count, 7)
        self.assertEqual(len(connection.cursor_instance.executed_migrations), first_execution_count)
        self.assertEqual(set(connection.cursor_instance.ledger), {1, 2, 3, 4, 5, 6, 7})



if __name__ == "__main__":
    unittest.main()
