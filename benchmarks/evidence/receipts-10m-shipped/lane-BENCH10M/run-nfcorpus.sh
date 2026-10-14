#!/bin/bash
L=/srv/tl/lane-bench10m
export TRACE_BENCH_DATA=$L/tb-cache HF_HOME=/srv/tl/weights HF_HUB_OFFLINE=1 TRACE_ARCHITECTURE_DIR=$L/tree PYTHONPATH=$L/bench10m/adapters
exec $L/venv/bin/python -m trace_bench run --dataset nfcorpus --baselines bm25,dense,python:c2_bench10m:C2Bench10MShipped,python:c2_bench10m:C2Bench10MK100 --output-dir $L/runs/nfcorpus
