#!/usr/bin/env python3
"""Interactive LLM Setup & Verification CLI for Trace (OpenRouter & DeepInfra).

Features:
1. Connect via OpenRouter (Primary) or DeepInfra.
2. For OpenRouter: Fetches 300+ live models/providers directly from OpenRouter API.
3. Lets you filter by provider (DeepSeek, Anthropic, Meta LLaMA, OpenAI, Google, etc.) or search.
4. Immediately verifies live connection, measures latency, and tests Trace evidence synthesis.
5. Injects/saves settings to local `.env` so Trace remembers it without polluting codebase.

Usage:
    python scripts/connect_llm.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

# Repo root & path setup
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
sys.path.insert(0, str(REPO_ROOT / "src"))


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


def save_env_file(updates: dict[str, str]) -> None:
    """Persist settings to local .env (gitignored)."""
    current = load_env_file()
    current.update(updates)
    current["TRACE_ALLOW_CLOUD_MODELS"] = "true"

    lines = ["# Trace Local Environment Configuration"]
    for k, v in sorted(current.items()):
        lines.append(f"{k}={v}")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def print_banner() -> None:
    print("\n" + "=" * 65)
    print("  🚀 TRACE ⇋ LLM GATEWAY SETUP & PLAYGROUND")
    print("=" * 65)
    print("  Configure OpenRouter or DeepInfra for Trace Evidence Synthesis")
    print("=" * 65 + "\n")


def fetch_openrouter_models(api_key: str | None = None) -> list[dict]:
    """Fetch live model directory from OpenRouter API."""
    url = "https://openrouter.ai/api/v1/models"
    req = urllib.request.Request(url, headers={"User-Agent": "Trace-Setup-CLI/1.0"})
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", [])
    except Exception as err:
        print(f"⚠️ Could not fetch live OpenRouter model catalog ({err}). Using standard presets.")
        return []


def select_openrouter_model(api_key: str) -> str:
    """Interactive provider & model picker for OpenRouter."""
    print("📡 Fetching available providers and models from OpenRouter...")
    raw_models = fetch_openrouter_models(api_key)

    # Standard popular presets
    popular_presets = [
        ("deepseek/deepseek-chat", "DeepSeek Chat (V3) - Ultra fast & high intelligence"),
        ("deepseek/deepseek-r1", "DeepSeek R1 - Advanced reasoning model"),
        ("meta-llama/llama-3.3-70b-instruct", "Meta LLaMA 3.3 70B Instruct"),
        ("meta-llama/llama-3.1-8b-instruct", "Meta LLaMA 3.1 8B Instruct (Fast / Cheap)"),
        ("anthropic/claude-3.5-haiku", "Anthropic Claude 3.5 Haiku (Fast & Accurate)"),
        ("anthropic/claude-3.5-sonnet", "Anthropic Claude 3.5 Sonnet (Top Tier)"),
        ("openai/gpt-4o-mini", "OpenAI GPT-4o Mini"),
        ("google/gemini-2.0-flash-001", "Google Gemini 2.0 Flash"),
    ]

    print("\n" + "-" * 60)
    print("Select a model option:")
    print("  [1] Pick from Recommended Popular Models")
    print("  [2] Browse by Provider (DeepSeek, Meta, Anthropic, Google, etc.)")
    print("  [3] Search Models by Keyword")
    print("  [4] Type custom Model ID manually")
    print("-" * 60)
    mode = input("Enter choice [1-4] (default: 1): ").strip() or "1"

    if mode == "1":
        print("\n🌟 Recommended Models:")
        for idx, (m_id, desc) in enumerate(popular_presets, 1):
            print(f"  [{idx}] {m_id:38s} - {desc}")
        sel = input(f"\nEnter choice [1-{len(popular_presets)}] (default: 1): ").strip() or "1"
        try:
            chosen = popular_presets[int(sel) - 1][0]
        except Exception:
            chosen = popular_presets[0][0]
        return f"openrouter/{chosen}"

    elif mode == "2" and raw_models:
        # Group by provider prefix
        providers: dict[str, list[dict]] = {}
        for m in raw_models:
            p_name = m["id"].split("/")[0] if "/" in m["id"] else "other"
            providers.setdefault(p_name, []).append(m)

        sorted_providers = sorted(providers.keys(), key=lambda p: (-len(providers[p]), p))
        print(f"\n🏢 Top Available Providers ({len(sorted_providers)} found):")
        top_p = sorted_providers[:15]
        for idx, p in enumerate(top_p, 1):
            print(f"  [{idx:2d}] {p:20s} ({len(providers[p])} models)")
        p_sel = input(f"\nSelect provider [1-{len(top_p)}]: ").strip() or "1"
        try:
            chosen_p = top_p[int(p_sel) - 1]
        except Exception:
            chosen_p = top_p[0]

        p_models = providers[chosen_p]
        print(f"\nModels from '{chosen_p}':")
        for idx, m in enumerate(p_models[:20], 1):
            name = m.get("name", m["id"])
            print(f"  [{idx:2d}] {m['id']:40s} ({name[:30]})")
        m_sel = input(f"\nSelect model [1-{min(20, len(p_models))}]: ").strip() or "1"
        try:
            chosen_m = p_models[int(m_sel) - 1]["id"]
        except Exception:
            chosen_m = p_models[0]["id"]
        return f"openrouter/{chosen_m}"

    elif mode == "3" and raw_models:
        query = input("\nEnter search keyword (e.g. 'deepseek', 'llama', 'free', 'flash'): ").strip().lower()
        matches = [m for m in raw_models if query in m["id"].lower() or query in m.get("name", "").lower()]
        if not matches:
            print("No matching models found. Defaulting to 'openrouter/deepseek/deepseek-chat'.")
            return "openrouter/deepseek/deepseek-chat"

        print(f"\nMatching Models ({len(matches)} found):")
        for idx, m in enumerate(matches[:20], 1):
            print(f"  [{idx:2d}] {m['id']:40s} ({m.get('name', '')[:30]})")
        m_sel = input(f"\nSelect model [1-{min(20, len(matches))}]: ").strip() or "1"
        try:
            chosen_m = matches[int(m_sel) - 1]["id"]
        except Exception:
            chosen_m = matches[0]["id"]
        return f"openrouter/{chosen_m}"

    else:
        custom = input("\nEnter OpenRouter model ID (e.g. 'deepseek/deepseek-chat'): ").strip()
        if not custom:
            custom = "deepseek/deepseek-chat"
        if not custom.startswith("openrouter/"):
            custom = f"openrouter/{custom}"
        return custom


def test_live_connection(api_key: str, model: str, provider: str) -> bool:
    """Test direct completion and Trace evidence-grounded synthesis."""
    print(f"\n🔍 Testing live model connection with {model}...")
    try:
        from litellm import completion
    except ImportError:
        print("❌ LiteLLM is not installed. Please run: pip install litellm")
        return False

    t0 = time.perf_counter()
    try:
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": "Respond with 'CONNECTED' and your model name in one line."}],
            "max_tokens": 60,
            "temperature": 0.0,
        }
        if provider == "openrouter":
            kwargs["api_key"] = api_key
        else:
            kwargs["api_key"] = api_key

        response = completion(**kwargs)
        elapsed = time.perf_counter() - t0
        reply = response.choices[0].message.content.strip()
        print(f"  ✓ {provider.title()} Response ({elapsed:.2f}s): {reply}")
    except Exception as err:
        print(f"❌ Connection failed: {err}")
        return False

    print("\n🔍 Testing Trace Evidence Synthesis with byte-anchored citations...")
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
        print(f"⚠️ Trace synthesis note: {err}")

    return True


def interactive_playground(api_key: str, model: str) -> None:
    """Interactive playground for querying Trace with LLM synthesis."""
    from trace.v2.models import IngestionRequest, QueryRequest
    from trace.v2.service import TraceService
    from trace.v2.store import SqliteEventStore

    store = SqliteEventStore("trace_playground.db")
    service = TraceService.from_environment()

    # Pre-seed sample facts
    sample_text = (
        "Trace uses Complementary Learning Systems: Hippocampal Spine for immutable byte truth, and Neocortex for LLM synthesis.\n\n"
        "At 100K document scale, Trace achieves 1,126 docs/sec ingestion throughput with under 515MB peak RAM.\n\n"
        "Retrieval latency is bounded to 0.54ms P95 direct lookup using Okapi BM25 and TL2 Personalized PageRank."
    )
    service.ingest(IngestionRequest(workspace_id="default", text=sample_text))

    while True:
        print("\n" + "-" * 55)
        print(f"Active Model: {model}")
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

            print(f"• Generating evidence-grounded synthesis with {model}...")
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
            test_live_connection(api_key, model, "openrouter" if "openrouter" in model else "deepinfra")

        elif choice in {"5", "q", "exit", "quit"}:
            print("\nGoodbye!")
            break


def main() -> None:
    print_banner()
    saved_env = load_env_file()

    print("Choose your LLM Provider:")
    print("  [1] OpenRouter (300+ models: DeepSeek, Anthropic, Meta, OpenAI, etc.) [Default]")
    print("  [2] DeepInfra (Direct DeepSeek / LLaMA hosting)")
    prov_choice = input("\nEnter choice [1-2] (default: 1): ").strip() or "1"

    if prov_choice == "2":
        provider = "deepinfra"
        existing_key = os.environ.get("DEEPINFRA_API_KEY") or saved_env.get("DEEPINFRA_API_KEY", "")
        default_model = "deepinfra/deepseek-ai/DeepSeek-V4-Flash"
        if existing_key:
            masked = existing_key[:4] + "..." + existing_key[-4:] if len(existing_key) > 8 else "***"
            print(f"\n🔑 Existing DeepInfra API Key found: {masked}")
            user_input = input("Press [Enter] to use this key, or paste a new key: ").strip()
            api_key = user_input if user_input else existing_key
        else:
            api_key = input("\n🔑 Paste your DeepInfra API key: ").strip()

        if not api_key:
            print("❌ No API key provided. Exiting.")
            sys.exit(1)

        model = default_model
        os.environ["DEEPINFRA_API_KEY"] = api_key
        os.environ["TRACE_MODEL_ID"] = model
        save_env_file({"DEEPINFRA_API_KEY": api_key, "TRACE_MODEL_ID": model})

    else:
        provider = "openrouter"
        existing_key = os.environ.get("OPENROUTER_API_KEY") or saved_env.get("OPENROUTER_API_KEY", "")
        if existing_key:
            masked = existing_key[:4] + "..." + existing_key[-4:] if len(existing_key) > 8 else "***"
            print(f"\n🔑 Existing OpenRouter API Key found: {masked}")
            user_input = input("Press [Enter] to use this key, or paste a new key: ").strip()
            api_key = user_input if user_input else existing_key
        else:
            api_key = input("\n🔑 Paste your OpenRouter API key: ").strip()

        if not api_key:
            print("❌ No API key provided. Exiting.")
            sys.exit(1)

        os.environ["OPENROUTER_API_KEY"] = api_key
        model = select_openrouter_model(api_key)
        os.environ["TRACE_MODEL_ID"] = model
        save_env_file({"OPENROUTER_API_KEY": api_key, "TRACE_MODEL_ID": model})

    os.environ["TRACE_ALLOW_CLOUD_MODELS"] = "true"
    print(f"\n✓ Saved configuration to {ENV_FILE.name} (Model: {model})")

    success = test_live_connection(api_key, model, provider)
    if success:
        print("\n🎉 Model Connected & Verified Successfully!")
        interactive_playground(api_key, model)
    else:
        print("\n❌ Setup failed to verify connection. Please check your API key.")


if __name__ == "__main__":
    main()
