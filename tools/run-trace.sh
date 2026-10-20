#!/usr/bin/env bash
# run-trace.sh — clone-and-run launcher for the TRACE interactive explorer.
# Zero install beyond python3: serves docs/ on localhost and opens the
# explorer in your browser. Port falls back 8000 -> 8100 if busy.
set -euo pipefail
cd "$(dirname "$0")/.."

pick_python() {
  if command -v python3 >/dev/null 2>&1; then echo python3; return 0; fi
  if command -v python >/dev/null 2>&1; then echo python; return 0; fi
  echo "run-trace: python3 not found — install Python 3.8+ and retry." >&2
  return 1
}
open_browser() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$url" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "$url" >/dev/null 2>&1 &
  elif command -v start >/dev/null 2>&1; then start "$url" >/dev/null 2>&1 &
  else echo "run-trace: open this URL manually: $url"; fi
}
PY="$(pick_python)"
PORT="${TRACE_PORT:-8000}"
if ! "$PY" -c "import http.server" 2>/dev/null; then
  echo "run-trace: $PY has no stdlib http.server — reinstall Python 3." >&2; exit 1
fi
# port fallback: first free port in 8000..8100
for p in $(seq 8000 8100); do
  if ! "$PY" -c "import socket; socket.create_connection(('127.0.0.1',$p),timeout=1)" 2>/dev/null; then
    PORT="$p"; break
  fi
done
URL="http://127.0.0.1:${PORT}/explorer/"
echo "run-trace: serving docs/ at http://127.0.0.1:${PORT}/ (Ctrl+C to stop)"
echo "run-trace: opening explorer: $URL"
"$PY" -m http.server "$PORT" --directory docs >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT INT TERM
sleep 1
open_browser "$URL"
wait $SRV
