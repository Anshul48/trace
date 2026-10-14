"""Durable workflow coordination built on the repository job state machine."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from typing import Any

from .store import TraceStoreError


JobHandler = Callable[[dict[str, Any]], dict[str, Any]]


class JobManager:
    """Submit, claim, execute, and inspect durable jobs.

    The manager contains no queue-specific assumptions.  A process-local
    worker can call :meth:`run_once`; a NATS/JetStream worker can invoke the
    same method after receiving the job event.  Completion is written before a
    webhook is attempted, so webhook failures never lose the canonical result.
    """

    def __init__(self, store: Any, *, handlers: dict[str, JobHandler] | None = None, webhook_dispatcher: Any | None = None) -> None:
        self.store = store
        self.handlers = handlers or {}
        self.webhook_dispatcher = webhook_dispatcher

    def register(self, kind: str, handler: JobHandler) -> None:
        self.handlers[kind] = handler

    def _workspace_scope(self, workspace_id: str | None):
        scope_factory = getattr(self.store, "authorization_scope", None)
        if workspace_id and callable(scope_factory):
            return scope_factory(workspace_id)
        return nullcontext()

    def submit(
        self,
        *,
        workspace_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        actor: str = "system",
        idempotency_key: str | None = None,
        request_id: str | None = None,
        webhook_id: str | None = None,
        run_immediately: bool = False,
    ) -> dict[str, Any]:
        job = self.store.create_job(
            workspace_id=workspace_id,
            kind=kind,
            payload=payload or {},
            actor=actor,
            idempotency_key=idempotency_key,
            request_id=request_id,
            webhook_id=webhook_id,
        )
        if run_immediately and job["status"] == "queued":
            with self._workspace_scope(workspace_id):
                job = self.execute(job["job_id"], actor=actor)
        return job

    def execute(self, job_id: str, *, actor: str = "job-worker") -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        if job["status"] == "queued":
            claimed = self.store.claim_jobs(job_id=job_id, limit=1)
            if not claimed:
                return self.store.get_job(job_id)
            job = claimed[0]
        handler = self.handlers.get(job["kind"])
        if handler is None:
            return self.store.fail_job(
                job_id,
                error={"type": "unsupported_job_kind", "kind": job["kind"]},
                actor=actor,
                retry=False,
            )
        try:
            result = handler(job["payload"]) or {}
        except Exception as error:
            failed = self.store.fail_job(
                job_id,
                error={"type": error.__class__.__name__, "detail": str(error)[:2_000]},
                actor=actor,
            )
            return failed
        completed = self.store.complete_job(job_id, result=result, actor=actor)
        if self.webhook_dispatcher is not None and completed.get("webhook_id"):
            try:
                self.webhook_dispatcher(completed)
            except Exception:
                # The durable job is already complete.  A delivery worker can
                # retry the signed callback independently.
                pass
        return completed

    def run_once(
        self,
        *,
        limit: int = 10,
        kind: str | None = None,
        actor: str = "job-worker",
        workspace_id: str | None = None,
    ) -> dict[str, int]:
        """Run one explicitly workspace-scoped batch.

        SQLite keeps backwards-compatible global test behavior. PostgreSQL
        runtime stores enforce the scope through RLS, so a production worker
        must be scheduled with one workspace rather than acquiring a global
        privileged queue lease.
        """

        with self._workspace_scope(workspace_id):
            try:
                claimed = self.store.claim_jobs(limit=limit, kind=kind, workspace_id=workspace_id)
            except TypeError:
                claimed = self.store.claim_jobs(limit=limit, kind=kind)
            completed = failed = 0
            for job in claimed:
                result = self.execute(job["job_id"], actor=actor)
                if result["status"] == "succeeded":
                    completed += 1
                elif result["status"] == "failed":
                    failed += 1
            return {"claimed": len(claimed), "completed": completed, "failed": failed}

    def cancel(self, job_id: str, *, actor: str = "system", reason: str | None = None) -> dict[str, Any]:
        return self.store.cancel_job(job_id, actor=actor, reason=reason)

    def retry(self, job_id: str, *, actor: str = "system", execute: bool = False) -> dict[str, Any]:
        job = self.store.retry_job(job_id, actor=actor)
        return self.execute(job["job_id"], actor=actor) if execute and job["status"] == "queued" else job
