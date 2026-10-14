#!/usr/bin/env bash
set -eu
SUP_CANDIDATE=$(cd "$(dirname "$0")" && pwd)
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export TMPDIR="$SUP_CANDIDATE/tmp"
export PYTHONPATH="$SUP_CANDIDATE/fork/tl-sys:$SUP_CANDIDATE/tools:$SUP_CANDIDATE/tests"
SUP_PYTHON="${SUP_PYTHON:-$HOME/venv/bin/python}"
exec nice -n 19 "$SUP_PYTHON" -B "$@"
