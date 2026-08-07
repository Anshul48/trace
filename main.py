"""Small operational entry point for the headless Trace V2 runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from trace.v2.models import IngestionRequest
from trace.v2.service import TraceService
from trace.v2.worker import JobWorker, OutboxWorker
from trace.v2.webhooks import WebhookDeliveryWorker
from trace.v2.preflight import run_self_hosted_preflight
from trace.v2.release import evaluate_release_evidence


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
    outbox = commands.add_parser("outbox", help="publish transactional outbox events to JetStream")
    outbox.add_argument("--limit", type=int, default=100)
    outbox.add_argument("--once", action="store_true")
    deliveries = commands.add_parser("webhook-worker", help="deliver queued signed webhooks")
    deliveries.add_argument("--limit", type=int, default=25)
    deliveries.add_argument("--once", action="store_true")
    preflight = commands.add_parser("preflight", help="run self-hosted production admission checks")
    preflight.add_argument("--data-path", default=".")
    release_gate = commands.add_parser("release-gate", help="evaluate measured load, restore, security, quality, and rollout evidence")
    release_gate.add_argument("evidence", type=Path)
    migrate = commands.add_parser("migrate", help="initialize the selected production repository")

    arguments = parser.parse_args()
    if arguments.command == "serve":
        import uvicorn

        uvicorn.run("main_api:app", host=arguments.host, port=arguments.port, reload=False)
        return

    if arguments.command == "migrate":
        if os.environ.get("TRACE_REPOSITORY", "sqlite").lower() in {"postgres", "postgresql"}:
            from trace.v2.production import PostgresEventStore

            PostgresEventStore(os.environ.get("TRACE_POSTGRES_MIGRATION_DSN") or os.environ.get("TRACE_POSTGRES_DSN")).initialize()
        else:
            service = TraceService.from_environment()
            if hasattr(service.store, "initialize"):
                service.store.initialize()
        print("Trace V2 repository initialized")
        return

    if arguments.command == "preflight":
        result = run_self_hosted_preflight(data_path=arguments.data_path)
        print({"passed": result.passed, "checks": result.checks})
        if not result.passed:
            raise SystemExit(2)
        return

    if arguments.command == "release-gate":
        try:
            evidence = json.loads(arguments.evidence.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(f"cannot read release evidence: {error}") from error
        result = evaluate_release_evidence(evidence)
        print(json.dumps(result.public_dict(), indent=2, sort_keys=True))
        if not result.passed:
            raise SystemExit(2)
        return

    if arguments.command == "worker":
        service = TraceService.from_environment()
        worker_instance = JobWorker(service)
        workspace_id = os.environ.get("TRACE_WORKER_WORKSPACE_ID")
        if arguments.once:
            print(worker_instance.run_once(limit=arguments.limit, kind=arguments.kind, workspace_id=workspace_id))
            return
        import time

        while True:
            worker_instance.run_once(limit=arguments.limit, kind=arguments.kind, workspace_id=workspace_id)
            time.sleep(1)

    if arguments.command == "outbox":
        from trace.v2.production import NatsJetStreamPublisher

        service = TraceService.from_environment()
        outbox_worker = OutboxWorker(service.store, NatsJetStreamPublisher())
        workspace_id = os.environ.get("TRACE_WORKER_WORKSPACE_ID")
        if arguments.once:
            print(asyncio.run(outbox_worker.drain_once(limit=arguments.limit, workspace_id=workspace_id)))
            return
        import time

        while True:
            print(asyncio.run(outbox_worker.drain_once(limit=arguments.limit, workspace_id=workspace_id)))
            time.sleep(1)

    if arguments.command == "webhook-worker":
        service = TraceService.from_environment()
        delivery_worker = WebhookDeliveryWorker(service.store)
        if arguments.once:
            print(delivery_worker.run_once(limit=arguments.limit, workspace_id=os.environ.get("TRACE_WORKER_WORKSPACE_ID")))
            return
        import time

        while True:
            delivery_worker.run_once(limit=arguments.limit, workspace_id=os.environ.get("TRACE_WORKER_WORKSPACE_ID"))
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
