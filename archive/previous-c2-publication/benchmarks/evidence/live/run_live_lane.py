#!/usr/bin/env python3
"""Run a live BENCH10M lane end to end (bundled wheel + shipped stack).

This driver binds every piece the wheel CLI actually requires (see
`../harness/README.md` and `trace_bench/runner.py --help`):

- assembles the disposable bench runtime (producer tree + 7-file
  serving overlay, hash-verified) and binds it BOTH as
  `TRACE_ARCHITECTURE_DIR` and as the keyed `--config`
  `architecture_dir` (keyed by the full `python:...` engine name);
- prepends `../harness/adapters/` to `PYTHONPATH` so
  `python:c2_bench10m:C2Bench10MShipped` imports;
- binds the staged corpus cache explicitly (`--data-dir`, falling back
  to `TRACE_BENCH_DATA`); `smoke`/`curated` are wheel-bundled and need
  no staging;
- preflights the pinned MiniLM snapshot before running A1/A2 arms
  (offline runs give no recovery when weights are absent).

Usage (from the repo root, after the §0 install + weights fetch):

    HF_HOME=/tmp/c2-weights HF_HUB_OFFLINE=1 \\
        python benchmarks/evidence/live/run_live_lane.py --dataset smoke
    # smoke: 6 docs / 6 queries, minutes on CPU

    python benchmarks/evidence/harness/adapters/stage_pinned.py \\
        --manifest benchmarks/evidence/harness/vendor/upstream-links.json \\
        --cache /tmp/c2-bench-cache
    HF_HOME=/tmp/c2-weights HF_HUB_OFFLINE=1 \\
        python benchmarks/evidence/live/run_live_lane.py --dataset scifact \\
        --data-dir /tmp/c2-bench-cache --output-dir /tmp/c2-bench-runs/scifact
    # bigger lanes: ~1000 s CPU ingest per 5k-doc fresh store (REPORT §7.3)

Original protocol of record: `--top-k 100 --concurrency 1`
(defaults here); official splits; `warmup 0`.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADAPTERS = HERE.parent / "harness" / "adapters"
MANIFEST = HERE.parent / "harness" / "vendor" / "upstream-links.json"

# Wheel-bundled fixtures (trace_bench/datasets/portable.py aliases):
# no dataset staging, no --data-dir needed.
BUNDLED = {"smoke", "curated"}

BEIR_SLUGS = {"scifact", "nfcorpus", "beir-scifact", "beir-nfcorpus"}
BRIGHT_SLUGS = {"pony", "bright-pony"}

DEFAULT_BASELINES = "bm25,python:c2_bench10m:C2Bench10MShipped"


def fail(msg):
    print(f"LIVE-LANE FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def staged_ok(dataset, cache):
    """Check the stage_pinned.py TB-cache layout for one bigger lane."""
    slug = dataset.removeprefix("beir-")
    if dataset in BEIR_SLUGS:
        ddir = cache / slug
        return (ddir / "corpus.jsonl").is_file() and \
            (ddir / "queries.jsonl").is_file() and \
            (ddir / "qrels" / "test.tsv").is_file()
    if dataset in BRIGHT_SLUGS:
        return (cache / "bright" / "raw" / "documents"
                / "pony-00000-of-00001.parquet").is_file() and \
            (cache / "bright" / "raw" / "examples"
             / "pony-00000-of-00001.parquet").is_file()
    return None  # unknown to the stager: TB resolves it (path/manifest)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default="smoke")
    ap.add_argument("--baselines", default=DEFAULT_BASELINES,
                    help="wheel --baselines selection "
                         "(NOT --backends; no such option)")
    ap.add_argument("--data-dir", default=None,
                    help="staged TB cache (stage --cache and run "
                         "--data-dir must be the SAME dir)")
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None,
                    help="diagnostic query subset (full corpus kept)")
    ap.add_argument("--output-dir", default=None,
                    help="run logs (default: fresh /tmp/c2-bench-runs-*)")
    ap.add_argument("--keep-runtime", action="store_true",
                    help="keep the disposable product runtime for "
                         "inspection (path is printed)")
    args = ap.parse_args(argv)

    try:
        import trace_bench  # noqa: F401
    except ImportError:
        fail("trace_bench is not installed; pip install "
             "../harness/vendor/trace_bench-0.3.0-py3-none-any.whl first "
             "(see ../pins/PINS.md)")
    if not ADAPTERS.is_dir():
        fail(f"adapters dir missing: {ADAPTERS}")

    customs = [b for b in args.baselines.split(",")
               if b.strip().startswith("python:")]
    c2_arms = [b for b in customs if ":c2_bench10m:" in b]

    out_dir = Path(args.output_dir) if args.output_dir else Path(
        tempfile.mkdtemp(prefix="c2-bench-runs-"))
    out_dir.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="c10m_live_lane_"))
    env = dict(os.environ)
    cmd = [sys.executable, "-m", "trace_bench", "run",
           "--dataset", args.dataset,
           "--baselines", args.baselines,
           "--top-k", str(args.top_k),
           "--concurrency", str(args.concurrency),
           "--output-dir", str(out_dir)]
    if args.limit is not None:
        cmd += ["--limit", str(args.limit)]

    runtime = None
    rc = 1
    try:
        # 1. Product runtime + keyed config for the shipped-stack arms.
        if c2_arms:
            sys.path.insert(0, str(HERE))
            import assemble_runtime
            import fetch_weights
            fetch_weights.validate()  # refuses when the pinned snapshot
            # is absent: HF_HUB_OFFLINE=1 would fail mid-run otherwise.
            keep_dir = Path(tempfile.mkdtemp(prefix="c10m_bench_runtime_")) \
                if args.keep_runtime else None
            runtime = assemble_runtime.assemble(keep_dir)
            print(f"runtime: {runtime} (producer + 7-file serving overlay)")
            config = {name.strip(): {"architecture_dir": str(runtime)}
                      for name in c2_arms}
            cfg_path = work / "engines.json"
            cfg_path.write_text(json.dumps(config, indent=1))
            cmd += ["--config", str(cfg_path)]
            env["TRACE_ARCHITECTURE_DIR"] = str(runtime)
            print(f"config: {cfg_path} keys={sorted(config)}")
        elif customs:
            print("note: no c2_bench10m arm selected; no product runtime "
                  "assembled (custom backends resolve via PYTHONPATH only)")

        # 2. Adapter import path (wheel does importlib.import_module).
        env["PYTHONPATH"] = str(ADAPTERS) + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

        # 3. Corpus cache binding.
        data_dir = args.data_dir or env.get("TRACE_BENCH_DATA")
        if args.dataset in BUNDLED or Path(args.dataset).exists():
            if data_dir:
                print(f"note: --data-dir {data_dir} ignored for "
                      f"wheel-bundled/direct dataset {args.dataset!r}")
            else:
                print(f"dataset {args.dataset!r}: wheel-bundled, no "
                      f"staging needed")
        else:
            if not data_dir:
                fail(f"dataset {args.dataset!r} needs a staged cache: "
                     f"pass --data-dir (or TRACE_BENCH_DATA) pointing at "
                     f"the SAME dir stage_pinned.py --cache wrote")
            cache = Path(data_dir)
            ok = staged_ok(args.dataset, cache)
            if ok is False:
                fail(f"staged layout for {args.dataset!r} not found under "
                     f"{cache}; stage first:\n"
                     f"  python {ADAPTERS / 'stage_pinned.py'} "
                     f"--manifest {MANIFEST} --cache {cache}")
            if ok is None:
                print(f"note: {args.dataset!r} is not a staged lane; "
                      f"leaving resolution to trace-bench")
            cmd += ["--data-dir", str(cache)]
            env["TRACE_BENCH_DATA"] = str(cache)
            print(f"data-dir: {cache}")

        print("exec:", " ".join(cmd))
        proc = subprocess.run(cmd, env=env)
        rc = proc.returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if runtime is not None and not args.keep_runtime:
            shutil.rmtree(runtime, ignore_errors=True)
        if runtime is not None and args.keep_runtime:
            print(f"kept runtime: {runtime}")
        print(f"output-dir: {out_dir}")
    if rc != 0:
        raise SystemExit(rc)
    print(f"LIVE-LANE PASS dataset={args.dataset} "
          f"baselines={args.baselines} rc=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
