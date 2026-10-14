#!/usr/bin/env python3
"""Trace One-Click Benchmark & Live Demo Studio Runner.

Usage:
  # Launch the interactive Web UI Studio
  python scripts/benchmark_studio.py --ui [--port 8501] [--open-browser]

  # Run headless one-click benchmark on scale datasets or fixtures
  python scripts/benchmark_studio.py --benchmark [--dataset auto] [--output report.json]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time
import webbrowser

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure Trace source is on sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))


# Load .env if present
ENV_FILE = ROOT_DIR / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip("\"'")

from trace.v2.api import create_app
from trace.v2.service import TraceService
from trace.v2.studio.engine import BenchmarkCoordinator, DatasetCatalog


BANNER = r"""
==============================================================================
  🧠 TRACE HYBRID ONE-CLICK BENCHMARK & LIVE DEMO STUDIO
==============================================================================
  Trace Evidence-Preserving Grounded Retrieval & Stage Ablation Engine
  • Datasets: C:\Users\anshu\AppData\Local\trace-scale-data
  • Multi-Stage: Lexical | Dense Vector | Graph Walk | Hierarchy | Grounding
==============================================================================
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trace One-Click Benchmark & Live Demo Studio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python scripts/benchmark_studio.py --ui --open-browser
  python scripts/benchmark_studio.py --benchmark --dataset fixture-technical-docs-v1
  python scripts/benchmark_studio.py --benchmark --dataset scale-enron --max-cases 100
""",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--ui", action="store_true", default=True, help="launch interactive Web UI (default)")
    mode_group.add_argument("--benchmark", action="store_true", help="run headless benchmark evaluation")

    # Web UI options
    parser.add_argument("--host", default="127.0.0.1", help="host to bind Web UI (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8501, help="port for Web UI (default: 8501)")
    parser.add_argument("--open-browser", action="store_true", help="open web browser on startup")

    # Benchmark CLI options
    parser.add_argument("--dataset", default="fixture-technical-docs-v1", help="dataset ID or 'auto' (default: fixture-technical-docs-v1)")
    parser.add_argument("--engines", default="trace_hybrid,pure_vector,pure_lexical,naive_rag", help="comma-separated engine IDs")
    parser.add_argument("--max-cases", type=int, default=50, help="max cases to evaluate")
    parser.add_argument("--output", type=Path, help="save JSON evaluation report to file")

    args = parser.parse_args()

    print(BANNER)

    catalog = DatasetCatalog()
    datasets = catalog.list_datasets()
    print(f"📦 Discovered {len(datasets)} Datasets / Fixtures:")
    for d in datasets:
        print(f"   • [{d.id}] {d.name} ({d.record_count:,} records) - {d.category}")
    print("-" * 78)

    if args.benchmark:
        print(f"\n🚀 Running Headless Benchmark Evaluation...")
        print(f"• Target Dataset: {args.dataset}")
        engine_ids = [e.strip() for e in args.engines.split(",") if e.strip()]
        print(f"• Engines:        {', '.join(engine_ids)}")
        print(f"• Max Cases:      {args.max_cases}\n")

        service = TraceService.from_environment()
        coordinator = BenchmarkCoordinator(service=service, catalog=catalog)

        import asyncio

        started = time.perf_counter()
        report = asyncio.run(coordinator.run_benchmark(
            dataset_id=args.dataset,
            engine_ids=engine_ids,
            max_cases=args.max_cases,
        ))
        elapsed = time.perf_counter() - started



        print("\n" + "=" * 78)
        print(f"  📊 BENCHMARK EVALUATION RESULTS ({report.get('dataset_id')})")
        print("=" * 78)
        metrics = report.get("metrics", {})
        for eng, m in metrics.items():
            print(f"  • [{eng.upper()}]:")
            print(f"      Recall@5: {m.get('recall_at_5', 0.0):.2f} | Recall@20: {m.get('recall_at_20', 0.0):.2f} | NDCG@10: {m.get('ndcg_at_10', 0.0):.2f}")
            print(f"      Evidence Coverage: {m.get('complete_gold_evidence_coverage', 0.0)*100:.1f}% | Citation Precision: {m.get('citation_precision', 0.0)*100:.1f}%")
            print(f"      Abstention Accuracy: {m.get('abstention_correctness', 0.0)*100:.1f}% | Hallucination: {m.get('hallucination_rate', 0.0)*100:.1f}%")
            print(f"      P95 Latency: {m.get('p95_latency_ms', 0.0):.1f}ms | Token Cost: ${m.get('total_token_cost_usd', 0.0):.4f}")
            print("  " + "-" * 76)
        print(f"\n⏱️ Completed in {elapsed:.2f}s")

        if args.output:
            args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"💾 Saved full report to: {args.output.resolve()}")
        return


    # Launch Web UI
    import uvicorn

    app = create_app()
    url = f"http://{args.host}:{args.port}/studio"
    print(f"\n🌐 Studio Web Dashboard ready at:")
    print(f"   👉 {url}")
    print(f"   👉 http://{args.host}:{args.port}/api/overview (API Overview)")
    print("-" * 78)
    print("Press Ctrl+C to stop the Studio server.\n")

    if args.open_browser:
        def _open():
            time.sleep(1.2)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
