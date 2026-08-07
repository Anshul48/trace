"""Command line interface for the offline Trace Phase 1 alpha."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .local import CapacityError, LocalTrace, RecordValidationError, TraceLocalError
from .pilot import PilotEvidenceError, evaluate_pilot, run_public_fixture


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _json_object(value: str, *, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(f"{label} must be JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError(f"{label} must be a JSON object")
    return parsed


def _add_data_dir(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--data-dir",
        required=True,
        type=Path,
        help="local Trace directory; no default directory is selected implicitly",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trace",
        description="Trace Phase 1 local-first evidence store. All commands are offline by default.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create or inspect a local data directory")
    _add_data_dir(init)

    ingest = commands.add_parser("ingest", help="ingest caller-normalized JSONL source records")
    _add_data_dir(ingest)
    ingest.add_argument("input", help="JSONL file, or - to read JSONL from standard input")
    ingest.add_argument("--format", choices=("auto", "json", "jsonl"), default="auto")
    ingest.add_argument("--actor", default="local-user")

    query = commands.add_parser("query", help="retrieve raw supporting evidence")
    _add_data_dir(query)
    query.add_argument("text")
    query.add_argument("--limit", type=int, default=10)
    query.add_argument("--collection")
    query.add_argument("--mode", choices=("lexical", "hybrid", "rerank"), default="lexical")
    query.add_argument("--embedding-plugin", help="explicit local plugin in package.module:object form")
    query.add_argument("--reranker-plugin", help="explicit local plugin in package.module:object form")

    status = commands.add_parser("status", help="report local resources and observed performance")
    _add_data_dir(status)

    verify = commands.add_parser("verify", help="verify provenance and projection parity")
    _add_data_dir(verify)

    rebuild = commands.add_parser("rebuild", help="rebuild lexical projection from immutable atoms")
    _add_data_dir(rebuild)
    rebuild.add_argument("--actor", default="local-user")

    export = commands.add_parser("export", help="write a portable event and evidence archive")
    _add_data_dir(export)
    export.add_argument("output", type=Path)
    export.add_argument("--overwrite", action="store_true", help="replace an existing output archive")

    import_command = commands.add_parser("import", help="import a portable event and evidence archive")
    _add_data_dir(import_command)
    import_command.add_argument("input", type=Path)
    import_command.add_argument("--actor", default="local-user")

    atom = commands.add_parser("atom", help="show one raw source atom and provenance")
    _add_data_dir(atom)
    atom.add_argument("atom_id")

    events = commands.add_parser("events", help="show immutable event lineage")
    _add_data_dir(events)
    events.add_argument("--after", type=int, default=0)
    events.add_argument("--limit", type=int, default=100)

    propose = commands.add_parser("propose", help="create a review-required derived proposal")
    _add_data_dir(propose)
    propose.add_argument("proposal_type")
    propose.add_argument("--candidate", required=True, type=lambda value: _json_object(value, label="candidate"))
    propose.add_argument("--evidence", required=True, nargs="+", metavar="ATOM_ID")
    propose.add_argument("--actor", default="local-user")

    review = commands.add_parser("review", help="approve or reject a derived proposal")
    _add_data_dir(review)
    review.add_argument("proposal_id")
    review.add_argument("decision", choices=("approved", "rejected"))
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reason")

    summary = commands.add_parser("summarize", help="create an extractive source-navigation summary")
    _add_data_dir(summary)
    summary.add_argument("--atom", required=True, action="append", dest="atom_ids", metavar="ATOM_ID")
    summary.add_argument("--title")
    summary.add_argument("--max-excerpt-characters", type=int, default=280)
    summary.add_argument("--actor", default="system")

    queue = commands.add_parser("run-queue", help="run resource-safe queued local work")
    _add_data_dir(queue)
    queue.add_argument("--limit", type=int, default=1)
    queue.add_argument("--actor", default="local-user")

    pilot = commands.add_parser("evaluate-pilot", help="evaluate measured Phase 1 pilot evidence")
    pilot.add_argument("report", type=Path, help="measured pilot JSON report")

    fixture = commands.add_parser("run-fixture", help="run a public judged JSONL fixture locally")
    _add_data_dir(fixture)
    fixture.add_argument("--corpus", type=Path, default=Path("fixtures/phase1/public-corpus.jsonl"))
    fixture.add_argument("--judgments", type=Path, default=Path("fixtures/phase1/public-judged-queries.json"))
    fixture.add_argument("--limit", type=int, default=10)
    fixture.add_argument("--actor", default="fixture-runner")
    return parser


def _execute(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.command == "evaluate-pilot":
        try:
            report = json.loads(arguments.report.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise TraceLocalError(f"cannot read pilot report: {error}") from error
        return evaluate_pilot(report)
    with LocalTrace.open(arguments.data_dir) as trace:
        if arguments.command == "init":
            return {"status": "initialized", **trace.status()}
        if arguments.command == "ingest":
            selected_format = arguments.format
            if selected_format == "auto":
                selected_format = "json" if arguments.input.lower().endswith(".json") else "jsonl"
            if selected_format == "json":
                source: Any = sys.stdin.read() if arguments.input == "-" else Path(arguments.input)
                results = trace.ingest_json(source, actor=arguments.actor)
            else:
                lines = sys.stdin if arguments.input == "-" else Path(arguments.input)
                results = trace.ingest_jsonl(lines, actor=arguments.actor)
            return {
                "status": "completed",
                "ingested": len(results),
                "duplicates": sum(1 for result in results if result["duplicate"]),
                "records": results,
                "resources": trace.status(),
            }
        if arguments.command == "query":
            return trace.query(
                arguments.text,
                limit=arguments.limit,
                collection=arguments.collection,
                mode=arguments.mode,
                embedding_plugin=arguments.embedding_plugin,
                reranker_plugin=arguments.reranker_plugin,
            )
        if arguments.command == "status":
            return trace.status()
        if arguments.command == "verify":
            return trace.verify_integrity()
        if arguments.command == "rebuild":
            return trace.rebuild_projections(actor=arguments.actor)
        if arguments.command == "export":
            return trace.export(arguments.output, overwrite=arguments.overwrite)
        if arguments.command == "import":
            return trace.import_bundle(arguments.input, actor=arguments.actor)
        if arguments.command == "atom":
            return trace.get_atom(arguments.atom_id)
        if arguments.command == "events":
            return {"events": trace.events(after_sequence=arguments.after, limit=arguments.limit)}
        if arguments.command == "propose":
            return trace.propose(
                arguments.proposal_type,
                arguments.candidate,
                arguments.evidence,
                actor=arguments.actor,
            )
        if arguments.command == "review":
            return trace.review_proposal(
                arguments.proposal_id,
                decision=arguments.decision,
                reviewer=arguments.reviewer,
                reason=arguments.reason,
            )
        if arguments.command == "summarize":
            return trace.generate_navigation_summary(
                arguments.atom_ids,
                title=arguments.title,
                max_excerpt_characters=arguments.max_excerpt_characters,
                actor=arguments.actor,
            )
        if arguments.command == "run-queue":
            return trace.run_queued_work(limit=arguments.limit, actor=arguments.actor)
        if arguments.command == "run-fixture":
            return run_public_fixture(
                trace,
                corpus_path=arguments.corpus,
                judgments_path=arguments.judgments,
                limit=arguments.limit,
                actor=arguments.actor,
            )
    raise AssertionError(f"unhandled command {arguments.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        result = _execute(arguments)
    except CapacityError as error:
        _print(error.public_dict())
        return 75
    except (OSError, ValueError, KeyError, TraceLocalError, RecordValidationError, PilotEvidenceError) as error:
        _print({"error": "trace_local_error", "detail": str(error)})
        return 2
    _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
