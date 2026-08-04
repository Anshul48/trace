"""Small operational entry point for the headless Trace V2 runtime."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from trace.v2.models import IngestionRequest
from trace.v2.service import TraceService
from trace.v2.worker import JobWorker, OutboxWorker


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace V2")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the versioned headless API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    ingest = commands.add_parser("ingest-text", help="durably ingest a UTF-8 text file")
    ingest.add_argument("workspace_id")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--idempotency-key")
    worker = commands.add_parser("worker", help="run durable Trace workflow jobs")
    worker.add_argument("--kind")
    worker.add_argument("--limit", type=int, default=10)
    worker.add_argument("--once", action="store_true")
    migrate = commands.add_parser("migrate", help="initialize the selected production repository")

    arguments = parser.parse_args()
    if arguments.command == "serve":
        import uvicorn

        uvicorn.run("main_api:app", host=arguments.host, port=arguments.port, reload=False)
        return

    if arguments.command == "migrate":
        service = TraceService.from_environment()
        if hasattr(service.store, "initialize"):
            service.store.initialize()
        print("Trace V2 repository initialized")
        return

    if arguments.command == "worker":
        service = TraceService.from_environment()
        worker_instance = JobWorker(service)
        if arguments.once:
            print(worker_instance.run_once(limit=arguments.limit, kind=arguments.kind))
            return
        import time

        while True:
            worker_instance.run_once(limit=arguments.limit, kind=arguments.kind)
            time.sleep(1)

    text = arguments.path.read_text(encoding="utf-8")
    result = TraceService.from_environment().ingest(
        IngestionRequest(
            workspace_id=arguments.workspace_id,
            text=text,
            idempotency_key=arguments.idempotency_key,
            source={"title": arguments.path.name, "uri": arguments.path.resolve().as_uri(), "adapter": "cli-text"},
        )
    )
    print(result["ingestion_id"])


if __name__ == "__main__":
    main()
