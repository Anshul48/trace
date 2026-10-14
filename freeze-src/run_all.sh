#!/usr/bin/env bash
# Stack-fork local test runner: synthetic/unit tests ONLY (no corpus).
# Usage: bash run_all.sh [stack|fix1|existing|all]  (default: all)
set -u
CAND="$(cd "$(dirname "$0")/cand" && pwd)"
PY="${PY:-/tmp/baseline-venv/bin/python}"
export PYTHONPATH="$CAND/tools:$CAND/fork/tl-sys:$CAND/fork/tl-candidate-batch/candidate:$CAND/fork/tl-sys/tlsys/serving/tests:$CAND/tests"
export PYTHONDONTWRITEBYTECODE=1
MODE="${1:-all}"
fail=0
run() { echo "--- $1"; shift; nice -n 19 "$PY" -B "$@" || fail=1; }

if [ "$MODE" = stack ] || [ "$MODE" = all ]; then
  for t in test_changed_set test_default_path_identity test_fix3_knob \
           test_fix6_parity test_fix2_suffix test_fix5_gc; do
    run "stack/$t" "$CAND/stack/tests/$t.py"
  done
fi
if [ "$MODE" = fix1 ] || [ "$MODE" = all ]; then
  for t in test_identity_off test_schema test_selfvalidation test_falsifier; do
    run "fix1/$t" "$CAND/fix1/tests/$t.py"
  done
fi
if [ "$MODE" = existing ] || [ "$MODE" = all ]; then
  run "existing/test_pending_topk" -m pytest "$CAND/tests/test_pending_topk.py" -q
  # Via the out-of-freeze wrapper: it excludes only the one test that
  # compares against the build host's upstream tree (absent on CI and
  # not part of the 207-file freeze) when that tree is not present.
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  run "existing/test_publication" "$ROOT/tools/run_publication_suite.py" "$CAND/tests/test_publication.py"
  run "existing/test_pool_reuse" "$CAND/tests/test_pool_reuse.py"
  run "existing/test_serving_pool" "$CAND/fork/tl-sys/tlsys/serving/tests/test_serving_pool.py"
fi
if [ "$fail" = 0 ]; then echo "RUN_ALL: PASS"; else echo "RUN_ALL: FAIL"; fi
exit "$fail"
