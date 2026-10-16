#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""TRACE Local Demonstration & Explorer Server.

Serves the interactive research explorer and authentic 20k local run results
using Python standard library HTTP server. Read-only, localhost default.
"""
import argparse
import http.server
import json
import os
import re
import socketserver
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLORER_DIR = ROOT / "docs" / "explorer"


def extract_run_uuid(run_dir: Path) -> str:
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", run_dir.name, re.I)
    if m:
        return m.group(1).lower()
    return run_dir.name


class TraceRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, run_dir=None, **kwargs):
        self.run_dir = Path(run_dir).resolve() if run_dir else None
        # Use existing docs/explorer if available, else current directory
        base_dir = str(EXPLORER_DIR) if EXPLORER_DIR.is_dir() else str(ROOT)
        super().__init__(*args, directory=base_dir, **kwargs)

    def do_GET(self):
        # Route /local_20k_data.json directly to selected run's actual exported graph
        if self.path == "/local_20k_data.json" or self.path == "/docs/explorer/local_20k_data.json":
            if self.run_dir:
                run_data = self.run_dir / "local_20k_data.json"
                if run_data.is_file():
                    data_bytes = run_data.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data_bytes)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data_bytes)
                    return

        # API Status / Health endpoint
        if self.path == "/api/status" or self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            status_data = {
                "engine": "TRACE",
                "source_freeze": "38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54",
                "selected_run_dir": str(self.run_dir) if self.run_dir else None,
                "selected_run_uuid": extract_run_uuid(self.run_dir) if self.run_dir else None,
                "local_20k_available": False,
            }
            if self.run_dir and (self.run_dir / "result.json").exists():
                try:
                    res = json.loads((self.run_dir / "result.json").read_text(encoding="utf-8"))
                    status_data["local_20k_available"] = True
                    status_data["local_run"] = {
                        "status": res.get("status"),
                        "actual_tokens": res.get("input", {}).get("actual_tokens"),
                        "complete_documents": res.get("input", {}).get("complete_documents"),
                        "atoms": res.get("final", {}).get("atoms"),
                        "leaves": res.get("final", {}).get("leaves"),
                        "parents": res.get("final", {}).get("parents"),
                        "store_head_pin": res.get("final", {}).get("source_head"),
                        "wall_s": res.get("wall_s"),
                    }
                except Exception:
                    pass
            self.wfile.write(json.dumps(status_data, indent=2).encode())
            return

        # Serve static assets
        return super().do_GET()

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def resolve_run_dir(given_path=None):
    if given_path:
        p = Path(given_path).resolve()
        if (p / "result.json").exists():
            return p
        raise FileNotFoundError(f"result.json not found in specified --run-dir: {given_path}")

    current_pointer = ROOT / "local-runs" / "current_run.json"
    if current_pointer.exists():
        try:
            data = json.loads(current_pointer.read_text(encoding="utf-8"))
            active = data.get("active_run")
            if active and (Path(active) / "result.json").exists():
                return Path(active).resolve()
        except Exception:
            pass

    return None


def main():
    parser = argparse.ArgumentParser(description="TRACE Local Demonstration Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    parser.add_argument("--run-dir", default=None, help="Path to pilot run directory")
    args = parser.parse_args()

    active_run = resolve_run_dir(args.run_dir)

    def handler(*h_args, **h_kwargs):
        return TraceRequestHandler(*h_args, run_dir=active_run, **h_kwargs)

    server = ThreadedHTTPServer((args.host, args.port), handler)
    print("=" * 60)
    print("TRACE Research Engine Explorer Server")
    print("=" * 60)
    print(f"Server running at: http://{args.host}:{args.port}/")
    if active_run:
        print(f"Selected run:      {active_run}")
        print(f"Run UUID:          {extract_run_uuid(active_run)}")
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    main()
