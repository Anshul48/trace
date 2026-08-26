"""Deterministic Control Plane Snapshot & Verification Utility.

Contract:
- Scope: All regular files recursively under docs/program excluding CONTROL_PLANE_LOCK.json.
- Normalization: relative path with '/', line format '<rel_path>:<lowercase_sha256>',
  sorted ordinally ascending, joined by LF ('\\n'), UTF-8 without BOM.
- Tree hash: SHA-256 over joined lines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def compute_control_plane_ledger(prog_dir: Path) -> tuple[str, list[dict[str, str]], list[dict[str, str]], int]:
    lines: list[str] = []
    ledger: list[dict[str, str]] = []
    core_docs: list[dict[str, str]] = []

    for p in sorted(prog_dir.rglob("*")):
        if p.is_file() and p.name != "CONTROL_PLANE_LOCK.json":
            rel = p.relative_to(prog_dir).as_posix()
            file_hash = hashlib.sha256(p.read_bytes()).hexdigest()
            lines.append(f"{rel}:{file_hash}")
            ledger.append({"path": rel, "sha256": file_hash})
            if p.parent == prog_dir:
                core_docs.append({"path": rel, "sha256": file_hash})

    joined = "\n".join(lines)
    tree_sha256 = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return tree_sha256, ledger, core_docs, len(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic Control Plane Snapshot & Verification Utility")
    parser.add_argument("--verify", action="store_true", help="Verify current control plane against lock file")
    parser.add_argument("--update", action="store_true", help="Update CONTROL_PLANE_LOCK.json")
    parser.add_argument("--snapshot-id", default=None, help="Snapshot ID when updating")
    parser.add_argument("--dir", default="docs/program", help="Path to docs/program directory")
    args = parser.parse_args()

    prog_dir = Path(args.dir).resolve()
    lock_file = prog_dir / "CONTROL_PLANE_LOCK.json"

    tree_sha256, ledger, core_docs, file_count = compute_control_plane_ledger(prog_dir)

    print(f"Control plane file count: {file_count}")
    print(f"Calculated Tree SHA-256:  {tree_sha256}")

    if args.verify:
        if not lock_file.is_file():
            print(f"ERROR: Lock file missing at {lock_file}", file=sys.stderr)
            sys.exit(1)
        lock = json.loads(lock_file.read_text(encoding="utf-8"))
        expected_tree = lock.get("tree_sha256")
        expected_count = lock.get("file_count")

        if tree_sha256 != expected_tree or file_count != expected_count:
            print(f"\n[VERIFICATION MISMATCH]", file=sys.stderr)
            print(f"  Expected file count: {expected_count}, Actual: {file_count}", file=sys.stderr)
            print(f"  Expected Tree SHA:   {expected_tree}", file=sys.stderr)
            print(f"  Actual Tree SHA:     {tree_sha256}", file=sys.stderr)
            sys.exit(1)
        else:
            print("\n[VERIFICATION PASS] Control plane tree hash exactly matches lock file.")
            sys.exit(0)

    if args.update:
        if not lock_file.is_file():
            lock = {
                "contract_version": "1.0",
                "snapshot_id": args.snapshot_id or "control-plane-snapshot",
                "generated_at_utc": "",
                "scope": "All regular files recursively under docs/program excluding this lock file.",
                "normalization": {
                    "relative_path_separator": "/",
                    "line_format": "<relative-path>:<lowercase-sha256>",
                    "sort": "ordinal ascending relative path",
                    "join": "LF",
                    "encoding": "UTF-8 without BOM",
                },
            }
        else:
            lock = json.loads(lock_file.read_text(encoding="utf-8"))

        if args.snapshot_id:
            lock["snapshot_id"] = args.snapshot_id
        lock["file_count"] = file_count
        lock["tree_sha256"] = tree_sha256
        lock["core_documents"] = core_docs

        lock_file.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        print(f"Successfully updated lock file at {lock_file}")


if __name__ == "__main__":
    main()
