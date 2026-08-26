"""Forward-only raw-SQL migration runner for the PostgreSQL production spine."""

from __future__ import annotations

import hashlib
import os
import re
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SqlMigration:
    revision: int
    name: str
    path: Path
    sql: str
    checksum: str


_MIGRATION_NAME = re.compile(r"^(?P<revision>\d{3,})_(?P<name>[a-z0-9_]+)\.sql$", re.IGNORECASE)


def default_migration_root() -> Path:
    # Editable/source installs use the repository-level migration directory.
    # Wheels install the same SQL assets through ``data-files``; do not make a
    # production migration command depend on a checkout being present.
    candidates = [
        Path(__file__).resolve().parents[3] / "migrations",
        Path(sysconfig.get_path("data")) / "trace" / "migrations",
        Path(sys.prefix) / "trace" / "migrations",
    ]
    configured = os.environ.get("TRACE_MIGRATIONS_DIR")
    if configured:
        candidates.insert(0, Path(configured))
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    # Keep the conventional source path in the error message emitted by
    # ``discover`` if no packaged asset can be found.
    return candidates[0]


class MigrationRunner:
    """Apply checksum-protected SQL revisions under one advisory lock.

    The runner does not support down migrations. A deployed correction is a
    new numbered file, which preserves the Atom/Event Spine and creates an
    audit trail operators can compare across environments.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_migration_root()

    def discover(self) -> list[SqlMigration]:
        if not self.root.is_dir():
            raise MigrationError(f"migration directory is missing: {self.root}")
        result: list[SqlMigration] = []
        seen: set[int] = set()
        for path in sorted(self.root.glob("*.sql")):
            match = _MIGRATION_NAME.match(path.name)
            if not match:
                continue
            revision = int(match.group("revision"))
            if revision in seen:
                raise MigrationError(f"duplicate migration revision {revision}")
            sql = path.read_text(encoding="utf-8")
            if not sql.strip():
                raise MigrationError(f"migration {path.name} is empty")
            seen.add(revision)
            result.append(SqlMigration(
                revision=revision,
                name=path.name,
                path=path,
                sql=sql,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            ))
        if not result:
            raise MigrationError("no SQL migrations were found")
        return result

    @staticmethod
    def _mapping(cursor: Any, row: Any) -> dict[str, Any]:
        names = [getattr(column, "name", column[0]) for column in cursor.description]
        return dict(zip(names, row, strict=True))

    def apply(self, connection: Any) -> list[SqlMigration]:
        migrations = self.discover()
        with connection.cursor() as cursor:
            # The ledger itself is intentionally outside a numbered migration:
            # it is the bootstrap needed to prove which numbered migrations
            # have run. It contains no canonical workspace data.
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS trace_schema_migrations (
                    revision BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    checksum CHAR(64) NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )"""
            )
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("trace:v2:schema-migrations",))
            cursor.execute("SELECT revision,name,checksum FROM trace_schema_migrations ORDER BY revision")
            applied = {int(row[0]): {"name": str(row[1]), "checksum": str(row[2])} for row in cursor.fetchall()}
            for migration in migrations:
                prior = applied.get(migration.revision)
                if prior is not None:
                    if prior["checksum"] != migration.checksum or prior["name"] != migration.name:
                        raise MigrationError(
                            f"applied migration {migration.revision} does not match {migration.name}; create a forward corrective migration"
                        )
                    continue
                # PostgreSQL's extended protocol accepts a script containing
                # sequential DDL statements. Migration files intentionally do
                # not use CREATE INDEX CONCURRENTLY because this transaction is
                # protected by the advisory lock.
                cursor.execute(migration.sql)
                cursor.execute(
                    "INSERT INTO trace_schema_migrations(revision,name,checksum) VALUES (%s,%s,%s)",
                    (migration.revision, migration.name, migration.checksum),
                )
        return migrations

    def verify(self, connection: Any) -> None:
        expected = {migration.revision: migration for migration in self.discover()}
        with connection.cursor() as cursor:
            cursor.execute("SELECT revision,name,checksum FROM trace_schema_migrations ORDER BY revision")
            for revision, name, checksum in cursor.fetchall():
                migration = expected.get(int(revision))
                if migration is None or migration.name != name or migration.checksum != checksum:
                    raise MigrationError("database migration ledger differs from checked-in forward-only migrations")


def assert_runtime_role(connection: Any, *, expected_role: str | None = None) -> None:
    """Reject a superuser/BYPASSRLS or unexpected migration-owner connection."""

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT current_user, r.rolsuper, r.rolbypassrls
                 FROM pg_roles r WHERE r.rolname=current_user"""
        )
        row = cursor.fetchone()
    if not row:
        raise MigrationError("cannot inspect PostgreSQL runtime role")
    user, is_superuser, bypass_rls = str(row[0]), bool(row[1]), bool(row[2])
    if expected_role and user != expected_role:
        raise MigrationError(f"runtime PostgreSQL role {user!r} does not match TRACE_POSTGRES_RUNTIME_ROLE")
    if is_superuser or bypass_rls:
        raise MigrationError("runtime PostgreSQL role must not be superuser or BYPASSRLS")


def ensure_monthly_event_partitions(connection: Any, *, months_ahead: int = 3) -> None:
    """Invoke the SQL maintenance function under the migration role.

    The function is deliberately opt-in from an operational scheduler; it
    never moves/deletes historical events on a query or API worker.
    """

    with connection.cursor() as cursor:
        cursor.execute("SELECT trace_ensure_event_partitions(%s)", (max(0, min(int(months_ahead), 24)),))
