#!/usr/bin/env python3
"""Phase 1 local-API demo (additional, clearly scoped).

Exercises the INSTALLED ``trace_local`` SDK end to end on a tiny bundled
fixture: open store -> ingest JSONL -> answerable query -> fail-closed
query -> integrity verify. Fully offline; no server, no model, no network.

This demo covers the Phase 1 local surface only. The 10M shipping-candidate
demo lives beside it (see demos/README.md) and runs the pinned historical
candidate harness.

Usage:
    python demos/demo_phase1_api.py [--data-dir DIR] [--keep] [--quiet]

Exit status: 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "demo_docs.jsonl"

ANSWERABLE_QUERY = "reader leases mmap"
UNANSWERABLE_QUERY = "quantum teleportation warranty terms"


def step(number: int, title: str, quiet: bool) -> None:
    if not quiet:
        print(f"\n[demo {number}] {title}")


def fail(message: str) -> int:
    print(f"DEMO FAIL: {message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=None, help="Store directory (default: temp dir).")
    parser.add_argument("--keep", action="store_true", help="Keep --data-dir after the run.")
    parser.add_argument("--quiet", action="store_true", help="Print only the final verdict.")
    args = parser.parse_args(argv)

    try:
        from trace_local import Trace
    except ImportError:
        return fail("trace_local is not installed; run: pip install -e .")

    if not FIXTURE.exists():
        return fail(f"fixture missing: {FIXTURE}")

    data_dir = (
        Path(args.data_dir) if args.data_dir else Path(tempfile.mkdtemp(prefix="trace-demo-"))
    )
    if args.data_dir:
        data_dir.mkdir(parents=True, exist_ok=True)

    try:
        step(1, f"open local store at {data_dir}", args.quiet)
        with Trace.open(data_dir) as trace:
            step(2, f"ingest {FIXTURE.name}", args.quiet)
            ingested = trace.ingest_jsonl(FIXTURE)
            if len(ingested) != 3:
                return fail(f"expected 3 ingested records, got {len(ingested)}")
            if not args.quiet:
                for record in ingested:
                    print(
                        f"  ingested {record['document_name']} hash={record['content_hash'][:16]}..."
                    )

            step(3, f"answerable query: {ANSWERABLE_QUERY!r}", args.quiet)
            answer = trace.query(ANSWERABLE_QUERY)
            if answer["sufficiency_state"] != "answerable" or not answer["results"]:
                return fail(f"expected answerable results, got: {json.dumps(answer)[:300]}")
            top = answer["results"][0]
            if top["source"]["document_name"] != "Epoch_RCU.md":
                return fail(f"wrong top hit: {top['source']['document_name']}")
            if not args.quiet:
                print(f"  top hit: {top['source']['document_name']}")
                print(f"  span: {top['content'][:80]}")
                print(f"  sha256: {top['content_hash']}")
                print(f"  elapsed: {answer['elapsed_ms']:.1f} ms")

            step(4, f"fail-closed query: {UNANSWERABLE_QUERY!r}", args.quiet)
            refused = trace.query(UNANSWERABLE_QUERY)
            if refused["sufficiency_state"] != "insufficient_evidence":
                return fail(f"expected insufficient_evidence, got: {refused['sufficiency_state']}")
            if not args.quiet:
                print("  correctly returned insufficient_evidence (no hallucinated answer)")

            step(5, "verify store integrity + projection parity", args.quiet)
            report = trace.verify_integrity()
            if not report.get("valid"):
                return fail(f"integrity invalid: {json.dumps(report)[:300]}")
            if not args.quiet:
                print(
                    f"  valid={report['valid']} atoms={report['canonical_atom_count']} "
                    f"events={report['event_count']} parity={report['projection_parity']}"
                )

            status = trace.status()
            if not args.quiet:
                print(
                    f"  offline_by_default={status['offline_by_default']} "
                    f"queries_observed={status['queries']['observed_count']}"
                )
    finally:
        if not args.keep and not args.data_dir:
            shutil.rmtree(data_dir, ignore_errors=True)

    print("DEMO PASS: init/ingest/query/refuse/verify round-trip succeeded (offline).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
