#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""TRACE Local Demonstration & Explorer Server.

Serves the interactive research explorer and authentic 20k local run results
using Python standard library HTTP server.
"""
import argparse
import http.server
import json
import os
import socketserver
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLORER_DIR = ROOT / "docs" / "explorer"


class TraceRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, run_dir=None, **kwargs):
        self.run_dir = run_dir
        super().__init__(*args, directory=str(EXPLORER_DIR), **kwargs)

    def do_GET(self):
        # API Health / Status endpoint
        if self.path == "/api/status" or self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            status_data = {
                "engine": "TRACE",
                "source_freeze": "38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54",
                "run_dir": str(self.run_dir) if self.run_dir else None,
                "local_20k_available": False,
                "qualification_receipts_available": (ROOT / "receipts" / "result.json").exists()
            }
            if self.run_dir and (self.run_dir / "result.json").exists():
                try:
                    res = json.loads((self.run_dir / "result.json").read_text())
                    status_data["local_20k_available"] = True
                    status_data["local_run"] = {
                        "status": res.get("status"),
                        "actual_tokens": res.get("input", {}).get("actual_tokens"),
                        "complete_documents": res.get("input", {}).get("complete_documents"),
                        "atoms": res.get("final", {}).get("atoms"),
                        "leaves": res.get("final", {}).get("leaves"),
                        "parents": res.get("final", {}).get("parents")
                    }
                except Exception:
                    pass
            self.wfile.write(json.dumps(status_data, indent=2).encode())
            return

        # Serve files from explorer directory
        return super().do_GET()

    def log_message(self, format, *args):
        # Concise logging
        sys.stderr.write(f"[{self.log_date_time_string()}] {args[0]} - {args[1]}\n")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def resolve_run_dir(given_path=None):
    if given_path:
        p = Path(given_path).resolve()
        if (p / "result.json").exists():
            return p
    current_pointer = ROOT / "local-runs" / "current_run.json"
    if current_pointer.exists():
        try:
            data = json.loads(current_pointer.read_text())
            active = data.get("active_run")
            if active and (Path(active) / "result.json").exists():
                return Path(active).resolve()
        except Exception:
            pass
    fallback = ROOT / "local-run-20k"
    if (fallback / "result.json").exists():
        return fallback.resolve()
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
    print(f"Serving directory: {EXPLORER_DIR}")
    if active_run:
        print(f"Active run:        {active_run}")
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    main()
