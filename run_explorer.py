#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""TRACE one-liner: serve the shipped explorer and open it in a browser.

Standard library only. No install, no downloads, no numpy::

    git clone https://github.com/Anshul48/trace
    python3 run_explorer.py --dataset 20k

--dataset 20k serves the explorer plus the data files that ship in this
repository (docs/explorer/, a static replay of real recorded queries over
the sealed library plus a real 20k-prefix hierarchy export). Larger local
kits (--download 10m / --download 100m) do not exist yet: there is no such
artifact committed in this repo and no release asset provides one (the
full-library download is listed as "planned" in docs/source/pages/try.html),
so those flags exit 2 with an honest message instead of pretending.
"""

import argparse
import errno
import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVE_DIR = ROOT / "docs"
EXPLORER_PATH = "/explorer/"

MIN_PYTHON = (3, 8)
DEFAULT_PORT = 8000

# Files the explorer page needs, relative to SERVE_DIR. All ship in the repo.
REQUIRED_FILES = (
    "explorer/index.html",
    "explorer/inside.html",
    "explorer/data/replay.js",
    "explorer/data/corpus.js",
    "explorer/local_20k_data.json",
)


def python_ok(version_info=None):
    """True if the running (or given) Python meets the floor."""
    info = version_info if version_info is not None else sys.version_info
    return (info[0], info[1]) >= MIN_PYTHON


def missing_shipped_files():
    """Names of required explorer files absent from this checkout."""
    return [name for name in REQUIRED_FILES if not (SERVE_DIR / name).is_file()]


def download_unavailable_message(which):
    """Honest text for --download: name exactly what is missing."""
    return (
        "run_explorer.py: no downloadable %s-token local kit exists.\n"
        "Checked: this repository (no 10m/100m data kit is committed; the only\n"
        "shipped dataset is the 20k prefix under docs/reproduction/repro-20k/)\n"
        "and the release tags (only 'seam12a-10m-freeze', a source tag, not a\n"
        "data download). The full-library download is listed as \"planned, not\n"
        "built\" in docs/source/pages/try.html. Run without --download:\n"
        "  python3 run_explorer.py --dataset 20k\n"
        % which
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Serve the TRACE explorer from this checkout (stdlib only) "
        "and open it in the default browser."
    )
    parser.add_argument(
        "--dataset",
        default="20k",
        help="Dataset to explore. Only '20k' ships in the repo (default: 20k).",
    )
    parser.add_argument(
        "--download",
        metavar="SIZE",
        default=None,
        help="Request a larger local kit ('10m' or '100m'). No such artifact "
        "exists yet, so this exits 2 with an honest message.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Local port to serve on (default: %d). Use 0 for any free port."
        % DEFAULT_PORT,
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Serve without opening the default browser (headless).",
    )
    return parser.parse_args(argv)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(host, port):
    """Bind and serve docs/. Returns (server, url). Raises on port busy."""

    def handler(*args, **kwargs):
        return http.server.SimpleHTTPRequestHandler(
            *args, directory=str(SERVE_DIR), **kwargs
        )

    try:
        server = ThreadedHTTPServer((host, port), handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise SystemExit(
                "run_explorer.py: port %d on %s is busy. "
                "Pick a free one, e.g. --port %d." % (port, host, port + 1)
            )
        raise
    actual_port = server.server_address[1]
    url = "http://%s:%d%s" % (host, actual_port, EXPLORER_PATH)
    return server, url


def main(argv=None):
    args = parse_args(argv)

    if not python_ok():
        cur = "%d.%d.%d" % sys.version_info[:3]
        need = "%d.%d" % MIN_PYTHON
        return "run_explorer.py: Python %s or newer is required (found %s)." % (
            need,
            cur,
        ), 1

    if args.download is not None:
        choice = str(args.download).strip().lower()
        if choice not in ("10m", "100m"):
            return (
                "run_explorer.py: --download takes '10m' or '100m' "
                "(got %r)." % args.download,
                2,
            )
        return download_unavailable_message(choice), 2

    if str(args.dataset).strip().lower() != "20k":
        return (
            "run_explorer.py: only --dataset 20k ships in this repo "
            "(got %r). Larger kits do not exist yet; see --download." % args.dataset,
            2,
        )

    if not isinstance(args.port, int) or not 0 <= args.port <= 65535:
        return "run_explorer.py: --port must be 0..65535 (got %r)." % args.port, 2

    missing = missing_shipped_files()
    if missing:
        return (
            "run_explorer.py: this checkout is missing shipped explorer files: %s. "
            "Re-clone https://github.com/Anshul48/trace and retry."
            % ", ".join(missing),
            1,
        )

    server, url = serve(args.host, args.port)
    inside_url = url + "inside.html"
    print("TRACE explorer serving docs/ at %s" % url.rsplit("/explorer/", 1)[0] + "/",
          flush=True)
    print("Explorer (Ask tab):  %s" % url, flush=True)
    print("Inside TRACE:        %s" % inside_url, flush=True)
    print("Dataset: 20k prefix shipped in this repo. Press Ctrl+C to stop.",
          flush=True)
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception as exc:  # browser launch must never kill serving
            print("run_explorer.py: could not open a browser (%s); "
                  "open the URL above manually." % exc)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return None, 0


if __name__ == "__main__":
    message, status = main()
    if message:
        print(message, file=sys.stderr if status else sys.stdout)
    sys.exit(status)
