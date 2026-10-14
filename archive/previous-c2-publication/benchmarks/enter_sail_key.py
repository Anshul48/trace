#!/usr/bin/env python3
"""Secure interactive helper to record and validate Sail Research API key in .env without echoing."""

from __future__ import annotations

import getpass
from pathlib import Path
import sys

# Add repo root to import path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.run_deepseek_flash_bakeoff import SailResearchClient


def main() -> int:
    print("=" * 65)
    print("Sail Research API Key Setup (Interactive Console)")
    print("=" * 65)
    print("Please paste your Sail Research API key below (input will be hidden):")
    try:
        key = getpass.getpass("Sail Research API Key: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[ABORT] Key entry cancelled.")
        return 1

    if not key:
        print("[ABORT] No key entered.")
        return 1

    print("\nValidating key against https://api.sailresearch.com/v1/models ...")
    client = SailResearchClient(api_key=key)
    ok, msg = client.verify_credentials()
    if not ok:
        print(f"\n[WARNING] Key verification failed: {msg}")
        try:
            ans = input("Save key anyway? (y/N): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n[ABORT] Discarded.")
            return 1
        if ans != "y":
            print("[ABORT] Discarded key. Please check your Sail Research account credentials.")
            return 2
    else:
        print(f"[SUCCESS] {msg}")

    env_path = Path(".env")
    lines = []
    found = False
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("SAIL_API_KEY="):
                    lines.append(f"SAIL_API_KEY={key}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"\nSAIL_API_KEY={key}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print("\n[SUCCESS] SAIL_API_KEY saved to .env securely.")
    print("You can now launch the bake-off via:")
    print("  python benchmarks/run_deepseek_flash_bakeoff.py")
    print("or run:")
    print("  run_deepseek_flash_bakeoff.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
