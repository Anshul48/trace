"""Small operational entry point for the headless Trace V2 runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
    studio = commands.add_parser("studio", help="launch the interactive Trace Benchmark & Live Demo Studio")
    studio.add_argument("--host", default="127.0.0.1")
    studio.add_argument("--port", type=int, default=8501)
    studio.add_argument("--open-browser", action="store_true", help="open web browser automatically")
    benchmark_cmd = commands.add_parser("benchmark-suite", help="run one-click headless benchmark evaluation across datasets")
    benchmark_cmd.add_argument("--dataset", default="fixture-technical-docs-v1", help="dataset ID or 'all'")
    benchmark_cmd.add_argument("--engines", default="trace_hybrid,pure_vector,pure_lexical,naive_rag", help="comma-separated engine IDs")
    benchmark_cmd.add_argument("--max-cases", type=int, default=50, help="max cases to evaluate")
    benchmark_cmd.add_argument("--output-json", type=Path, help="optional path to save report JSON")

    arguments = parser.parse_args()
    if arguments.command == "studio":
        import threading
        import webbrowser
        import uvicorn
        from trace.v2.api import create_app

        app = create_app()
        url = f"http://{arguments.host}:{arguments.port}/studio"
        print("=" * 72)
        print("  🧠 TRACE ONE-CLICK BENCHMARK & LIVE DEMO STUDIO")
        print(f"  • Studio UI:  {url}")
        print(f"  • API Docs:   http://{arguments.host}:{arguments.port}/docs")
        print("=" * 72)

        if arguments.open_browser:
            def _open():
                import time
                time.sleep(1.0)
                webbrowser.open(url)
            threading.Thread(target=_open, daemon=True).start()

        uvicorn.run(app, host=arguments.host, port=arguments.port, reload=False)
        return

    if arguments.command == "benchmark-suite":
        from trace.v2.studio.engine import BenchmarkCoordinator, DatasetCatalog

        service = TraceService.from_environment()
        catalog = DatasetCatalog()
        coordinator = BenchmarkCoordinator(service=service, catalog=catalog)

        dataset_id = arguments.dataset
        engine_ids = [e.strip() for e in arguments.engines.split(",") if e.strip()]
        print(f"Running benchmark on dataset: {dataset_id} with engines: {engine_ids}")

        report = asyncio.run(coordinator.run_benchmark(
            dataset_id=dataset_id,
            engine_ids=engine_ids,
            max_cases=arguments.max_cases,
        ))

        print("\n" + "=" * 76)
        print(f"  📊 BENCHMARK EVALUATION RESULTS ({report.get('dataset_id')})")
        print("=" * 76)
        metrics = report.get("metrics", {})
        for eng, m in metrics.items():
            print(f"  • [{eng.upper()}]:")
            print(f"      Recall@5: {m.get('recall_at_5', 0.0):.2f} | Recall@20: {m.get('recall_at_20', 0.0):.2f} | NDCG@10: {m.get('ndcg_at_10', 0.0):.2f}")
            print(f"      Evidence Coverage: {m.get('complete_gold_evidence_coverage', 0.0)*100:.1f}% | Citation Precision: {m.get('citation_precision', 0.0)*100:.1f}%")
            print(f"      Abstention Accuracy: {m.get('abstention_correctness', 0.0)*100:.1f}% | Hallucination: {m.get('hallucination_rate', 0.0)*100:.1f}%")
            print(f"      P95 Latency: {m.get('p95_latency_ms', 0.0):.1f}ms | Token Cost: ${m.get('total_token_cost_usd', 0.0):.4f}")
            print("  " + "-" * 74)

        if arguments.output_json:
            arguments.output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Report saved to {arguments.output_json}")
        return


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
