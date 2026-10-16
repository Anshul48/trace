#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# TRACE: Isolated Local Engine Installer & Runner (20k Prefix)
# License: Apache-2.0
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

RERUN=0
NO_SERVER=0
PORT=8765

for arg in "$@"; do
    case "$arg" in
        --rerun)
            RERUN=1
            ;;
        --no-server)
            NO_SERVER=1
            ;;
        --port=*)
            PORT_VAL="${arg#*=}"
            if ! [[ "${PORT_VAL}" =~ ^[0-9]+$ ]] || [ "${PORT_VAL}" -lt 1 ] || [ "${PORT_VAL}" -gt 65535 ]; then
                echo "ERROR: Invalid port: ${PORT_VAL}. Must be an integer between 1 and 65535." >&2
                exit 1
            fi
            PORT="${PORT_VAL}"
            ;;
        --help|-h)
            echo "Usage: ./install_and_run.sh [--rerun] [--no-server] [--port=PORT]"
            echo ""
            echo "Options:"
            echo "  --rerun      Execute a new frozen 20k pilot run into a new unique directory"
            echo "  --no-server  Complete installation and pilot verification without launching server"
            echo "  --port=PORT  Set local viewer port (default: 8765, valid: 1..65535)"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $arg" >&2
            echo "Run ./install_and_run.sh --help for usage." >&2
            exit 1
            ;;
    esac
done

echo "=================================================================="
echo "TRACE Research Engine: Local Installer & Runner (20k Token Prefix)"
echo "Candidate Sourcefreeze: 38c66bef (207 files immutable)"
echo "Supported OS: Linux (verified Python 3.12 baseline)"
echo "=================================================================="

# 1. Environment Verification (Python >= 3.11 per pyproject.toml)
echo ""
echo "[1/7] Checking Python runtime (floor: 3.11, verified: 3.12)..."
PY=""
for candidate in python3.12 python3.11 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        version_check=$("${candidate}" -c 'import sys; v=sys.version_info; print("OK" if (v.major==3 and v.minor>=11) else "NO")')
        if [ "${version_check}" = "OK" ]; then
            PY="$(command -v "${candidate}")"
            echo "  Found suitable Python: ${PY} ($("${PY}" --version))"
            break
        fi
    fi
done

if [ -z "${PY}" ]; then
    echo "ERROR: Python >= 3.11 required (Python 3.12 verified baseline). Please install Python 3.11 or 3.12." >&2
    exit 1
fi

# Locate uv tool: PATH discovery first, then known local fallbacks
UV_BIN=""
if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
elif [ -x "${HOME}/.local/bin/uv" ]; then
    UV_BIN="${HOME}/.local/bin/uv"
elif [ -x "${HOME}/.cargo/bin/uv" ]; then
    UV_BIN="${HOME}/.cargo/bin/uv"
fi

if [ -n "${UV_BIN}" ]; then
    echo "  Found uv binary: ${UV_BIN} ($("${UV_BIN}" --version))"
else
    echo "  Notice: uv not found in PATH or standard user paths; standard venv will be used if ensurepip is available."
fi

# 2. Isolated Virtual Environment (.trace-demo-env; preserve existing .venv)
ENV_DIR="${SCRIPT_DIR}/.trace-demo-env"
PYTHON_BIN="${ENV_DIR}/bin/python"

echo ""
echo "[2/7] Preparing isolated virtual environment in .trace-demo-env..."
if [ ! -d "${ENV_DIR}" ]; then
    if [ -n "${UV_BIN}" ]; then
        echo "  Creating isolated venv with uv for Python ${PY}..."
        "${UV_BIN}" venv --python "${PY}" "${ENV_DIR}"
    else
        echo "  Creating isolated venv with ${PY}..."
        "${PY}" -m venv "${ENV_DIR}"
    fi
fi

if [ ! -x "${PYTHON_BIN}" ]; then
    echo "ERROR: Virtual environment Python not found at ${PYTHON_BIN}" >&2
    exit 1
fi

# 3. Installing Minimal Dependencies (numpy, blake3)
echo ""
echo "[3/7] Checking minimal baseline dependencies (numpy, blake3)..."
DEPS_OK=$("${PYTHON_BIN}" -c '
try:
    import numpy
    import blake3
    print("OK")
except ImportError:
    print("NO")
')

if [ "${DEPS_OK}" = "OK" ]; then
    echo "  Dependencies already installed in isolated virtual environment."
else
    echo "  Installing numpy and blake3 into isolated environment..."
    if [ -n "${UV_BIN}" ]; then
        "${UV_BIN}" pip install --python "${PYTHON_BIN}" numpy blake3
    else
        "${PYTHON_BIN}" -m pip install numpy blake3
    fi
fi

# 4. Source Integrity Check (207 pinned files against manifest digest)
echo ""
echo "[4/7] Verifying 207 immutable source files against SOURCEFREEZE..."
"${PYTHON_BIN}" tools/verify_freeze.py

# 5. Small-Scale Real Prefix Verification
echo ""
echo "[5/7] Verifying 20k token prefix data..."
DATA_DIR="${SCRIPT_DIR}/repro-20k/data-20k"
TAR_FILE="${SCRIPT_DIR}/repro-20k/small-prefix-20k.tar.gz"

if [ ! -d "${DATA_DIR}" ]; then
    if [ ! -f "${TAR_FILE}" ]; then
        echo "ERROR: Missing prefix data directory and archive at ${TAR_FILE}" >&2
        exit 1
    fi
    echo "  Unpacking repro-20k/small-prefix-20k.tar.gz..."
    "${PYTHON_BIN}" repro-20k/prep_small_prefix.py unpack --tar "${TAR_FILE}" --data-dir "${DATA_DIR}"
fi
"${PYTHON_BIN}" repro-20k/prep_small_prefix.py verify --tokens 20000 --cand freeze-src/cand --data-dir "${DATA_DIR}"

# 6. Execute Frozen Product Pilot on 20k Prefix (Preserve all runs, NO deletions)
RUNS_DIR="${SCRIPT_DIR}/local-runs"
mkdir -p "${RUNS_DIR}"
ACTIVE_POINTER="${RUNS_DIR}/current_run.json"

echo ""
echo "[6/7] Resolving 20k pilot run (all prior runs preserved)..."

ACTIVE_RUN_DIR=""
if [ "${RERUN}" -eq 0 ] && [ -f "${ACTIVE_POINTER}" ]; then
    CANDIDATE_DIR=$("${PYTHON_BIN}" -c 'import json, sys, os
try:
    data = json.load(open(sys.argv[1]))
    path = data.get("active_run")
    if path and os.path.isdir(path):
        res = json.load(open(os.path.join(path, "result.json")))
        if res.get("status") == "PASS":
            print(path)
except Exception:
    pass' "${ACTIVE_POINTER}")

    if [ -n "${CANDIDATE_DIR}" ]; then
        # Comprehensive verification of existing PASS run:
        # Must be strictly under owned local-runs, correct status, prefix, tokens, atoms, and sourcefreeze
        VERIFIED=$("${PYTHON_BIN}" -c 'import json, sys, os
cand_real = os.path.realpath(sys.argv[1])
runs_real = os.path.realpath(sys.argv[2])
try:
    if os.path.commonpath([cand_real, runs_real]) != runs_real or cand_real == runs_real:
        print("NO_PATH")
        sys.exit(0)
except Exception:
    print("NO_PATH")
    sys.exit(0)
try:
    res = json.load(open(os.path.join(cand, "result.json")))
    status_ok = (res.get("status") == "PASS")
    prefix_ok = (res.get("input", {}).get("prefix_raw_sha256") == "530e51c72c117e0a8a312de19a6263fd8a40326990c6aa98f7f8303a7f4ed119")
    tokens_ok = (res.get("input", {}).get("actual_tokens") == 20030)
    atoms_ok = (res.get("final", {}).get("atoms") == 144)
    freeze_ok = (res.get("manifest_harness_sha256") == "9f516288a098eff7b2a52373ad0eaf6b9ad1664377a9f7be4f974701b8d9b1a0")
    print("OK" if (status_ok and prefix_ok and tokens_ok and atoms_ok and freeze_ok) else "NO")
except Exception:
    print("NO")' "${CANDIDATE_DIR}" "${RUNS_DIR}")

        if [ "${VERIFIED}" = "OK" ]; then
            ACTIVE_RUN_DIR="${CANDIDATE_DIR}"
            echo "  Reusing verified existing 20k run in: ${ACTIVE_RUN_DIR}"
            echo "  (All runs preserved; use --rerun to execute a fresh run into a new directory)"
        fi
    fi
fi

if [ -z "${ACTIVE_RUN_DIR}" ] || [ "${RERUN}" -eq 1 ]; then
    RUN_UUID=$("${PYTHON_BIN}" -c 'import uuid; print(uuid.uuid4())')
    TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    NEW_RUN_DIR="${RUNS_DIR}/run-${TIMESTAMP}-${RUN_UUID}"
    echo "  Creating new unique run directory: ${NEW_RUN_DIR}"

    echo "  Executing frozen harness product_pilot.py against data-20k..."
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="${SCRIPT_DIR}/freeze-src/cand/fork/tl-sys:${SCRIPT_DIR}/freeze-src/cand/fork/tl-candidate-batch/candidate:${SCRIPT_DIR}/freeze-src/cand/tools" \
    "${PYTHON_BIN}" -B "${SCRIPT_DIR}/freeze-src/cand/tools/product_pilot.py" \
        --tokens 20000 --profile local \
        --out "${NEW_RUN_DIR}" \
        --source-root "${SCRIPT_DIR}/freeze-src/cand" \
        --data-dir "${DATA_DIR}"

    # Confirm verdict via safe argument passing
    VERDICT=$("${PYTHON_BIN}" -c 'import json, sys; print(json.load(open(sys.argv[1]))["status"])' "${NEW_RUN_DIR}/result.json")
    if [ "${VERDICT}" != "PASS" ]; then
        echo "ERROR: Pilot run finished with status: ${VERDICT}" >&2
        exit 1
    fi
    echo "  Pilot execution completed with verdict: PASS"
    ACTIVE_RUN_DIR="${NEW_RUN_DIR}"

    # Record active run pointer and append to runs ledger
    "${PYTHON_BIN}" -c 'import json, sys, os, time
run_dir, pointer, ledger = sys.argv[1], sys.argv[2], sys.argv[3]
rec = {
    "active_run": run_dir,
    "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "status": "PASS"
}
with open(pointer, "w") as f:
    json.dump(rec, f, indent=2)
with open(ledger, "a") as f:
    f.write(json.dumps(rec) + "\n")' "${ACTIVE_RUN_DIR}" "${ACTIVE_POINTER}" "${RUNS_DIR}/runs.jsonl"
fi

# Export selected run data for explorer
echo "  Exporting run topology and queries for explorer from ${ACTIVE_RUN_DIR}..."
"${PYTHON_BIN}" tools/export_20k_viewer.py --run-dir "${ACTIVE_RUN_DIR}" --data-dir "${DATA_DIR}"

# 7. Launch Local Demonstration Server
echo ""
echo "[7/7] Launching local explorer server..."
if [ "${NO_SERVER}" -eq 1 ]; then
    echo "  Skipping server start (--no-server)."
    echo "  Installation and 20k pilot run verified successfully!"
    exit 0
fi

echo "=================================================================="
echo "TRACE Engine Ready! Open in your browser:"
echo "http://127.0.0.1:${PORT}/"
echo "=================================================================="
exec "${PYTHON_BIN}" tools/serve_local.py --run-dir "${ACTIVE_RUN_DIR}" --port "${PORT}"
