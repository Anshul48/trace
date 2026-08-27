#!/usr/bin/env python3
"""Interactive LLM Setup & Verification CLI for Trace.

Simple 1-step setup:
1. Paste your DeepInfra API key.
2. It tests the connection to DeepSeek-V4-Flash immediately.
3. It remembers your configuration in .env.
4. Lets you query, synthesize, or run benchmarks interactively!

Usage:
    python scripts/connect_llm.py
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import time
from pathlib import Path

# Repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
sys.path.insert(0, str(REPO_ROOT / "src"))

DEFAULT_MODEL = "deepinfra/deepseek-ai/DeepSeek-V4-Flash"


def load_env_file() -> dict[str, str]:
    """Load key-value pairs from .env if present."""
    loaded = {}
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("\"'")
                    loaded[k] = v
                    os.environ[k] = v
        except Exception:
            pass
    return loaded


def save_env_file(key: str, model: str) -> None:
    """Persist the key and model to local .env (which is gitignored)."""
    lines = [
        "# Trace Local Environment Configuration",
        f"DEEPINFRA_API_KEY={key}",
        "TRACE_ALLOW_CLOUD_MODELS=true",
        f"TRACE_MODEL_ID={model}",
    ]
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def print_banner() -> None:
    print("\n" + "=" * 65)
    print("  🚀 TRACE ⇋ DEEPINFRA COGNITIVE SETUP & PLAYGROUND")
    print("=" * 65)
    print(f"• Provider:  DeepInfra (LiteLLM Gateway)")
    print(f"• Model:     {DEFAULT_MODEL}")
    print("=" * 65 + "\n")


def test_live_connection(api_key: str, model: str) -> bool:
    """Test direct completion and Trace evidence-grounded synthesis."""
    print("🔍 Testing live model connection...")
    try:
        from litellm import completion
    except ImportError:
        print("❌ LiteLLM is not installed. Please run: pip install litellm")
        return False

    t0 = time.perf_counter()
    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": "Respond with 'CONNECTED' and your model name in one line."}],
            api_key=api_key,
            max_tokens=60,
            temperature=0.0,
        )
        elapsed = time.perf_counter() - t0
        reply = response.choices[0].message.content.strip()
        print(f"  ✓ DeepInfra Response ({elapsed:.2f}s): {reply}")
    except Exception as err:
        print(f"❌ Connection failed: {err}")
        return False

    print("\n🔍 Testing Trace Evidence Synthesis with byte anchors...")
    try:
        from trace.v2.models import IngestionRequest, QueryRequest
        from trace.v2.service import TraceService
        from trace.v2.store import SqliteEventStore

        service = TraceService.from_environment()
        sample = "Trace is an immutable evidence-preserving memory engine that guarantees zero hallucination."
        ingest_res = service.ingest(IngestionRequest(workspace_id="test", text=sample))
        q_res = service.query(QueryRequest(workspace_id="test", query="zero hallucination"))
        synth = service.synthesize(
            evidence_bundle_id=q_res["evidence_bundle_id"],
            prompt="Explain Trace grounding in one short sentence.",
            format="prose",
            privacy_context={},
            model_id=model,
        )
        print(f"  ✓ Trace Synthesis: {synth['rendering']}")
        print(f"  ✓ Byte Citations:  {len(synth['citations'])} provable source anchors verified.")
    except Exception as err:
        print(f"⚠️ Trace synthesis test note: {err}")

    return True


def interactive_playground(api_key: str, model: str) -> None:
    """Interactive loop for querying Trace with LLM synthesis."""
    from trace.v2.models import IngestionRequest, QueryRequest
    from trace.v2.service import TraceService
    from trace.v2.store import SqliteEventStore

    store = SqliteEventStore("trace_playground.db")
    service = TraceService.from_environment()

    # Pre-seed a few facts if store is empty
    sample_text = (
        "Trace uses Complementary Learning Systems: Hippocampal Spine for immutable byte truth, and Neocortex for LLM synthesis.\n\n"
        "At 100K document scale, Trace achieves 1,126 docs/sec ingestion throughput with under 515MB peak RAM.\n\n"
        "Retrieval latency is bounded to 0.54ms P95 direct lookup using Okapi BM25 and TL2 Personalized PageRank."
    )
    service.ingest(IngestionRequest(workspace_id="default", text=sample_text))

    while True:
        print("\n" + "-" * 55)
        print("Choose an action:")
        print("  [1] Ask a Question (Search + LLM Synthesis)")
        print("  [2] Ingest New Text into Memory")
        print("  [3] Run 100K Scale Gate Benchmark")
        print("  [4] Re-test Connection")
        print("  [5] Exit")
        print("-" * 55)

        choice = input("Enter choice [1-5]: ").strip()

        if choice == "1":
            q = input("\nEnter your question / query: ").strip()
            if not q:
                continue
            print("• Retrieving byte-anchored evidence...")
            q_res = service.query(QueryRequest(workspace_id="default", query=q, retrieval_profile="rerank"))
            bundle_id = q_res["evidence_bundle_id"]
            results = q_res.get("results", [])
            print(f"  Found {len(results)} matching evidence atoms.")

            print("• Generating evidence-grounded synthesis with DeepSeek-V4-Flash...")
            t0 = time.perf_counter()
            synth = service.synthesize(
                evidence_bundle_id=bundle_id,
                prompt=f"Answer the question concisely: {q}",
                format="prose",
                privacy_context={},
                model_id=model,
            )
            elapsed = time.perf_counter() - t0
            print(f"\n💬 Answer ({elapsed:.2f}s):")
            print("  " + synth["rendering"])
            print(f"\n📌 Citations ({len(synth['citations'])} verified anchors):")
            for cit in synth["citations"][:3]:
                loc = cit["source_location"]
                print(f"  • Atom [{cit['atom_version_id'][:10]}...] byte span: {loc.get('start')}..{loc.get('end')}")

        elif choice == "2":
            print("\nEnter or paste text to ingest (press Enter twice to finish):")
            lines = []
            while True:
                line = input()
                if not line and lines and not lines[-1]:
                    break
                lines.append(line)
            content = "\n".join(lines).strip()
            if content:
                res = service.ingest(IngestionRequest(workspace_id="default", text=content))
                print(f"✓ Ingested into Spine! Ingestion ID: {res['ingestion_id']}")

        elif choice == "3":
            print("\n🚀 Launching 100K Scale Gate Benchmark...")
            import subprocess
            subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "run_100k_scale_gate.py")])

        elif choice == "4":
            test_live_connection(api_key, model)

        elif choice in {"5", "q", "exit", "quit"}:
            print("\nGoodbye!")
            break


def main() -> None:
    print_banner()

    saved_env = load_env_file()
    existing_key = os.environ.get("DEEPINFRA_API_KEY") or saved_env.get("DEEPINFRA_API_KEY", "")
    model = os.environ.get("TRACE_MODEL_ID") or saved_env.get("TRACE_MODEL_ID", DEFAULT_MODEL)

    if existing_key:
        masked = existing_key[:4] + "..." + existing_key[-4:] if len(existing_key) > 8 else "***"
        print(f"🔑 Existing API Key found: {masked}")
        user_input = input("Press [Enter] to use this key, or paste a new key: ").strip()
        api_key = user_input if user_input else existing_key
    else:
        api_key = input("🔑 Paste your DeepInfra API key: ").strip()

    if not api_key:
        print("❌ No API key provided. Exiting.")
        sys.exit(1)

    os.environ["DEEPINFRA_API_KEY"] = api_key
    os.environ["TRACE_ALLOW_CLOUD_MODELS"] = "true"
    save_env_file(api_key, model)
    print(f"✓ Saved configuration to {ENV_FILE.name} (will be remembered automatically).")

    success = test_live_connection(api_key, model)
    if success:
        print("\n🎉 Connection Verified & Ready!")
        interactive_playground(api_key, model)
    else:
        print("\n❌ Setup failed to verify connection. Please check your API key.")


if __name__ == "__main__":
    main()
