"""Installed operational entry point for the Trace V2 package."""

from __future__ import annotations

import argparse
import os

from .service import TraceService
from .worker import JobWorker


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace V2 operations")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the V2 HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    migrate = commands.add_parser("migrate", help="apply the selected repository migrations")
    worker = commands.add_parser("worker-once", help="run one workspace-scoped durable job batch")
    worker.add_argument("--workspace-id", default=os.environ.get("TRACE_WORKER_WORKSPACE_ID"))
    worker.add_argument("--kind")
    worker.add_argument("--limit", type=int, default=10)
    arguments = parser.parse_args()

    if arguments.command == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(), host=arguments.host, port=arguments.port)
        return
    if arguments.command == "migrate":
        if os.environ.get("TRACE_REPOSITORY", "sqlite").lower() in {"postgres", "postgresql"}:
            from .production import PostgresEventStore

            PostgresEventStore(os.environ.get("TRACE_POSTGRES_MIGRATION_DSN") or os.environ.get("TRACE_POSTGRES_DSN")).initialize()
        else:
            service = TraceService.from_environment()
            if hasattr(service.store, "initialize"):
                service.store.initialize()
        return
    service = TraceService.from_environment()
    print(JobWorker(service).run_once(limit=arguments.limit, kind=arguments.kind, workspace_id=arguments.workspace_id))


if __name__ == "__main__":  # pragma: no cover - exercised by packaging smoke tests
    main()
