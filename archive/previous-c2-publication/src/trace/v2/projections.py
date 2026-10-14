"""Revision lifecycle controls for rebuildable retrieval projections.

The controller intentionally knows nothing about a vendor SDK.  It makes the
release protocol explicit: create an immutable target revision, backfill it,
verify bounded parity metadata, then atomically activate it.  Query paths only
read the adapter's active alias/collection; they never invoke these methods.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class ProjectionRevisionError(RuntimeError):
    """Raised when a revision cannot safely become a read target."""


@dataclass(frozen=True)
class RevisionParity:
    projection: str
    workspace_id: str
    revision: str
    expected_count: int
    actual_count: int | None
    checked: bool
    passed: bool
    missing_count: int | None
    stale_count: int | None

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class RevisionedProjectionController:
    """Small vendor-neutral lifecycle adapter used by explicit reindex jobs."""

    def __init__(self, *, strict: bool = False) -> None:
        self.strict = strict

    @staticmethod
    def _call(adapter: Any, name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(adapter, name, None)
        if not callable(method):
            raise ProjectionRevisionError(f"adapter does not implement {name}()")
        try:
            return method(*args, **kwargs)
        except TypeError:
            # Injected development adapters often expose the pre-revision
            # signature. They are valid only for non-strict local exercises.
            if kwargs:
                return method(*args)
            raise

    def prepare(self, adapter: Any | None, *, revision: str, vector_size: int | None = None) -> dict[str, Any]:
        if adapter is None:
            return {"supported": False, "prepared": False}
        create = getattr(adapter, "create_revision", None)
        if not callable(create):
            if self.strict:
                raise ProjectionRevisionError("production adapter lacks immutable create_revision()")
            return {"supported": False, "prepared": False}
        kwargs = {"vector_size": vector_size} if vector_size else {}
        try:
            target = create(revision, **kwargs)
        except TypeError:
            target = create(revision)
        return {"supported": True, "prepared": True, "target": target}

    def verify(
        self,
        adapter: Any | None,
        *,
        projection: str,
        workspace_id: str,
        revision: str,
        expected_count: int,
    ) -> RevisionParity:
        if adapter is None or not callable(getattr(adapter, "revision_count", None)):
            if self.strict:
                raise ProjectionRevisionError(f"{projection} adapter lacks revision_count() parity verification")
            return RevisionParity(
                projection=projection, workspace_id=workspace_id, revision=revision,
                expected_count=expected_count, actual_count=None, checked=False,
                passed=True, missing_count=None, stale_count=None,
            )
        actual = int(self._call(adapter, "revision_count", workspace_id=workspace_id, revision=revision))
        return RevisionParity(
            projection=projection,
            workspace_id=workspace_id,
            revision=revision,
            expected_count=expected_count,
            actual_count=actual,
            checked=True,
            passed=actual == expected_count,
            missing_count=max(0, expected_count - actual),
            stale_count=max(0, actual - expected_count),
        )

    def activate(self, adapter: Any | None, *, revision: str) -> dict[str, Any]:
        if adapter is None:
            return {"supported": False, "activated": False}
        activate = getattr(adapter, "activate_revision", None)
        if not callable(activate):
            if self.strict:
                raise ProjectionRevisionError("production adapter lacks activate_revision()")
            return {"supported": False, "activated": False}
        self._call(adapter, "activate_revision", revision)
        return {"supported": True, "activated": True, "revision": revision}

    def rollback(self, adapter: Any | None, *, revision: str) -> dict[str, Any]:
        if adapter is None:
            return {"supported": False, "rolled_back": False}
        rollback = getattr(adapter, "rollback_revision", None)
        if callable(rollback):
            self._call(adapter, "rollback_revision", revision)
            return {"supported": True, "rolled_back": True, "revision": revision}
        # Activation is intentionally atomic, so moving an alias back is a
        # valid rollback implementation for a simple adapter.
        return {**self.activate(adapter, revision=revision), "rolled_back": True}
