#!/usr/bin/env python3
"""Fetch, parse, and stage Linux Kernel Git archives and LKML patch threads.

The Linux Kernel Git repository & LKML archive contains millions of commits
and patch discussions (10M - 100M+ tokens).

This script extracts:
- Commit SHA, parent SHA(s) -> NEXT/PREV directed acyclic commit graph
- Author & Committer metadata (name, email, timestamp in ISO 8601)
- Full commit log, subject, and trailer tags (Signed-off-by, Acked-by, Reviewed-by)
- Unified patch diffs, file modifications, insertions/deletions stats
- LKML patch series metadata ([PATCH vN M/T] numbering, thread relation)

Supports:
- Git repo ingestion via subprocess / git commands or local repo parsing
- --dry-run for fast offline graph validation
- --limit <N> for bounded ingestion
- Standard Phase 1 JSONL output
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Support execution both as script and module
try:
    from .common import (
        DEFAULT_SCALE_DATA_ROOT,
        clean_text_whitespace,
        create_trace_record,
        get_default_staging_dir,
        write_jsonl_records,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.scale_datasets.common import (
        DEFAULT_SCALE_DATA_ROOT,
        clean_text_whitespace,
        create_trace_record,
        get_default_staging_dir,
        write_jsonl_records,
    )


def parse_trailers(message: str) -> dict[str, list[str]]:
    """Extract standard git trailers (Signed-off-by, Acked-by, Reviewed-by, Cc, Fixes)."""
    trailers: dict[str, list[str]] = {
        "signed_off_by": [],
        "acked_by": [],
        "reviewed_by": [],
        "tested_by": [],
        "reported_by": [],
        "suggested_by": [],
        "fixes": [],
    }
    for line in message.splitlines():
        line_s = line.strip()
        if re.match(r"^Signed-off-by:\s*", line_s, re.I):
            trailers["signed_off_by"].append(re.sub(r"^Signed-off-by:\s*", "", line_s, flags=re.I))
        elif re.match(r"^Acked-by:\s*", line_s, re.I):
            trailers["acked_by"].append(re.sub(r"^Acked-by:\s*", "", line_s, flags=re.I))
        elif re.match(r"^Reviewed-by:\s*", line_s, re.I):
            trailers["reviewed_by"].append(re.sub(r"^Reviewed-by:\s*", "", line_s, flags=re.I))
        elif re.match(r"^Tested-by:\s*", line_s, re.I):
            trailers["tested_by"].append(re.sub(r"^Tested-by:\s*", "", line_s, flags=re.I))
        elif re.match(r"^Reported-by:\s*", line_s, re.I):
            trailers["reported_by"].append(re.sub(r"^Reported-by:\s*", "", line_s, flags=re.I))
        elif re.match(r"^Suggested-by:\s*", line_s, re.I):
            trailers["suggested_by"].append(re.sub(r"^Suggested-by:\s*", "", line_s, flags=re.I))
        elif re.match(r"^Fixes:\s*", line_s, re.I):
            trailers["fixes"].append(re.sub(r"^Fixes:\s*", "", line_s, flags=re.I))
    return trailers


def parse_patch_subject(subject: str) -> dict[str, Any]:
    """Parse patch series markers like [PATCH v3 2/5] subsystem: description."""
    res = {
        "is_patch": False,
        "patch_version": 1,
        "patch_index": 1,
        "patch_total": 1,
        "subsystem": "",
        "clean_subject": subject,
    }
    match = re.search(r"\[(?:PATCH|RFC PATCH)(?:\s+v(\d+))?(?:\s+(\d+)/(\d+))?\]\s*(.*)", subject, re.IGNORECASE)
    if match:
        res["is_patch"] = True
        if match.group(1):
            res["patch_version"] = int(match.group(1))
        if match.group(2) and match.group(3):
            res["patch_index"] = int(match.group(2))
            res["patch_total"] = int(match.group(3))
        res["clean_subject"] = match.group(4) or subject

    # Extract subsystem tag e.g. "mm/damon: fix memory leak" -> "mm/damon"
    sub_match = re.match(r"^([a-zA-Z0-9_\-/\.]+):\s*(.*)", res["clean_subject"])
    if sub_match:
        res["subsystem"] = sub_match.group(1)
    return res


def generate_synthetic_lkml_records(count: int = 15) -> Generator[dict[str, Any], None, None]:
    """Generate realistic synthetic Linux kernel commits and patch series DAG."""
    commits_data = [
        {
            "commit_sha": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
            "parents": ["9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"],
            "next_commits": ["b2c3d4e5f60718293a4b5c6d7e8f90123456789a"],
            "author_name": "Linus Torvalds",
            "author_email": "torvalds@linux-foundation.org",
            "author_date": "2024-03-10T18:22:01Z",
            "subject": "mm/page_alloc: optimize buddy allocator order-0 fast path",
            "message": (
                "mm/page_alloc: optimize buddy allocator order-0 fast path\n\n"
                "In high-throughput networked workloads, zone watermarks for order-0 allocations "
                "are checked redundantly inside rmqueue() even when the per-cpu page lists (PCP) "
                "have sufficient capacity. Bypass the lock acquisition when PCP is non-empty.\n\n"
                "Benchmark results on 128-core AMD EPYC menunjukkan a 4.2% increase in packet/sec "
                "under synthetic UDP flood testing.\n\n"
                "Signed-off-by: Linus Torvalds <torvalds@linux-foundation.org>\n"
                "Reviewed-by: Mel Gorman <mgorman@techsingularity.net>\n"
                "Acked-by: Vlastimil Babka <vbabka@suse.cz>"
            ),
            "files": ["mm/page_alloc.c", "include/linux/mmzone.h"],
            "diff": (
                "diff --git a/mm/page_alloc.c b/mm/page_alloc.c\n"
                "--- a/mm/page_alloc.c\n"
                "+++ b/mm/page_alloc.c\n"
                "@@ -3210,8 +3210,12 @@ struct page *rmqueue(struct zone *preferred_zone,\n"
                " \tif (likely(order == 0)) {\n"
                "+\t\t/* Fast-path PCP lookup without spinlock contention */\n"
                "+\t\tpage = rmqueue_pcplist(preferred_zone, zone, order,\n"
                "+\t\t\t\t       gfp_flags, alloc_flags, migratetype);\n"
                "+\t\tif (likely(page))\n"
                "+\t\t\tgoto out;\n"
                " \t}\n"
                " \tpage = __rmqueue(zone, order, migratetype, alloc_flags);\n"
            ),
        },
        {
            "commit_sha": "b2c3d4e5f60718293a4b5c6d7e8f90123456789a",
            "parents": ["a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"],
            "next_commits": ["c3d4e5f60718293a4b5c6d7e8f90123456789ab1"],
            "author_name": "Alexei Starovoitov",
            "author_email": "ast@kernel.org",
            "author_date": "2024-03-11T09:14:30Z",
            "subject": "bpf: introduce bpf_arena memory allocator for zero-copy structures",
            "message": (
                "bpf: introduce bpf_arena memory allocator for zero-copy structures\n\n"
                "Add BPF arena which is a sparse memory region accessible from both kernel BPF "
                "programs and user space via mmap(). This allows lockless shared memory algorithms "
                "and complex graph structures without per-element serialization overhead.\n\n"
                "Signed-off-by: Alexei Starovoitov <ast@kernel.org>\n"
                "Signed-off-by: Daniel Borkmann <daniel@iogearbox.net>\n"
                "Reviewed-by: Andrii Nakryiko <andrii@kernel.org>"
            ),
            "files": ["kernel/bpf/arena.c", "kernel/bpf/verifier.c", "include/uapi/linux/bpf.h"],
            "diff": (
                "diff --git a/kernel/bpf/arena.c b/kernel/bpf/arena.c\n"
                "--- a/kernel/bpf/arena.c\n"
                "+++ b/kernel/bpf/arena.c\n"
                "@@ -100,6 +100,18 @@ static struct bpf_map *arena_map_alloc(union bpf_attr *attr)\n"
                "+\tstruct bpf_arena *arena;\n"
                "+\tarena = kzalloc(sizeof(*arena), GFP_USER | __GFP_ACCOUNT);\n"
                "+\tif (!arena)\n"
                "+\t\treturn ERR_PTR(-ENOMEM);\n"
                "+\tarena->map.max_entries = attr->max_entries;\n"
                "+\treturn &arena->map;\n"
            ),
        },
        {
            "commit_sha": "c3d4e5f60718293a4b5c6d7e8f90123456789ab1",
            "parents": ["b2c3d4e5f60718293a4b5c6d7e8f90123456789a"],
            "next_commits": ["d4e5f60718293a4b5c6d7e8f90123456789ab1c2"],
            "author_name": "Jens Axboe",
            "author_email": "axboe@kernel.dk",
            "author_date": "2024-03-12T14:45:10Z",
            "subject": "io_uring: add support for IORING_OP_FUTEX_WAITV",
            "message": (
                "io_uring: add support for IORING_OP_FUTEX_WAITV\n\n"
                "Wire up futex_waitv support to io_uring. This enables asynchronous waiting on "
                "multiple futexes directly within an io_uring SQE submission ring, avoiding "
                "dedicated thread context switches in gaming runtime dispatchers.\n\n"
                "Signed-off-by: Jens Axboe <axboe@kernel.dk>\n"
                "Reviewed-by: Peter Zijlstra <peterz@infradead.org>\n"
                "Tested-by: André Almeida <andrealmeid@igalia.com>"
            ),
            "files": ["io_uring/futex.c", "include/uapi/linux/io_uring.h"],
            "diff": (
                "diff --git a/io_uring/futex.c b/io_uring/futex.c\n"
                "--- a/io_uring/futex.c\n"
                "+++ b/io_uring/futex.c\n"
                "@@ -150,6 +150,15 @@ int io_futex_waitv(struct io_kiocb *req, unsigned int issue_flags)\n"
                "+\tstruct io_futex_waitv *fw = io_kiocb_to_cmd(req, struct io_futex_waitv);\n"
                "+\treturn futex_wait_multiple(fw->futexes, fw->nr_futexes, fw->flags);\n"
            ),
        },
        {
            "commit_sha": "d4e5f60718293a4b5c6d7e8f90123456789ab1c2",
            "parents": ["c3d4e5f60718293a4b5c6d7e8f90123456789ab1"],
            "next_commits": [],
            "author_name": "Greg Kroah-Hartman",
            "author_email": "gregkh@linuxfoundation.org",
            "author_date": "2024-03-13T11:05:44Z",
            "subject": "driver core: fix sysfs device reference leak in device_add() error path",
            "message": (
                "driver core: fix sysfs device reference leak in device_add() error path\n\n"
                "When kobject_add() fails during device_add(), the device kobject reference count "
                "must be decremented using put_device() to prevent dangling bus links.\n\n"
                "Fixes: 8a7c29e102f4 (\"driver core: refactor device hierarchy lifecycle\")\n"
                "Signed-off-by: Greg Kroah-Hartman <gregkh@linuxfoundation.org>\n"
                "Reported-by: syzbot+e8a93bf@syzkaller.appspotmail.com\n"
                "Cc: stable@vger.kernel.org"
            ),
            "files": ["drivers/base/core.c"],
            "diff": (
                "diff --git a/drivers/base/core.c b/drivers/base/core.c\n"
                "--- a/drivers/base/core.c\n"
                "+++ b/drivers/base/core.c\n"
                "@@ -3550,7 +3550,7 @@ int device_add(struct device *dev)\n"
                " \terror = kobject_add(&dev->kobj, dev->kobj.parent, \"%s\", dev_name(dev));\n"
                " \tif (error)\n"
                "-\t\tgoto Error;\n"
                "+\t\tgoto out_put_device;\n"
            ),
        },
    ]

    generated = 0
    for idx, c in enumerate(commits_data):
        if generated >= count:
            return

        patch_meta = parse_patch_subject(c["subject"])
        trailers = parse_trailers(c["message"])

        header_lines = [
            f"Commit: {c['commit_sha']}",
            f"Author: {c['author_name']} <{c['author_email']}>",
            f"Date: {c['author_date']}",
            f"Parent(s): {', '.join(c['parents'])}",
            f"Next: {', '.join(c['next_commits']) if c['next_commits'] else 'HEAD'}",
            f"Files Changed: {', '.join(c['files'])}",
            "",
            c["message"],
            "",
            "--- Diffs ---",
            c["diff"],
        ]
        full_content = "\n".join(header_lines)

        metadata = {
            "dataset": "lkml",
            "commit_sha": c["commit_sha"],
            "parents": c["parents"],
            "prev_commit": c["parents"][0] if c["parents"] else None,
            "next_commits": c["next_commits"],
            "author_name": c["author_name"],
            "author_email": c["author_email"],
            "author_date": c["author_date"],
            "subject": c["subject"],
            "files_changed": c["files"],
            "trailers": trailers,
            "patch_info": patch_meta,
            "graph_node": {
                "id": c["commit_sha"],
                "in_edges": c["parents"],
                "out_edges": c["next_commits"],
            },
        }

        doc_name = f"lkml/commit/{c['commit_sha'][:12]}"
        yield create_trace_record(
            document_name=doc_name,
            content=full_content,
            source_uri=f"git://kernel.org/linux/commit/{c['commit_sha']}",
            metadata=metadata,
            collection="lkml",
        )
        generated += 1


def iterate_git_log(
    repo_path: Path | str,
    revision_range: str = "HEAD",
    limit: int | None = None,
    include_diff: bool = True,
) -> Generator[dict[str, Any], None, None]:
    """Extract commits and diffs sequentially from a local git repository."""
    repo = Path(repo_path)
    if not (repo / ".git").exists() and not repo.name.endswith(".git"):
        raise ValueError(f"Not a valid git repository: {repo}")

    # Format: SHA%x1fPARENT%x1fAN%x1fAE%x1faI%x1fs%x1fB%x1e
    # Using Unit Separator (0x1f) and Record Separator (0x1e)
    format_str = "%H%x1f%P%x1f%an%x1f%ae%x1faI%x1f%s%x1f%B%x1e"
    cmd = ["git", "-C", str(repo), "log", f"--format={format_str}", revision_range]
    if limit is not None:
        cmd.extend(["-n", str(limit)])
    if include_diff:
        cmd.append("-p")

    print(f"[LKML] Streaming git log from: {repo}")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1024 * 1024,
    )

    if process.stdout is None:
        return

    buffer = ""
    count = 0
    while True:
        chunk = process.stdout.read(65536)
        if not chunk and process.poll() is not None:
            break
        buffer += chunk
        while "\x1e" in buffer:
            record_str, buffer = buffer.split("\x1e", 1)
            record_str = record_str.strip()
            if not record_str:
                continue

            parts = record_str.split("\x1f")
            if len(parts) < 7:
                continue

            sha = parts[0].strip()
            parents = parts[1].strip().split() if parts[1].strip() else []
            author_name = parts[2].strip()
            author_email = parts[3].strip()
            author_date = parts[4].strip()
            subject = parts[5].strip()
            body_and_diff = parts[6].strip()

            trailers = parse_trailers(body_and_diff)
            patch_meta = parse_patch_subject(subject)

            doc_name = f"lkml/commit/{sha[:12]}"
            metadata = {
                "dataset": "lkml",
                "commit_sha": sha,
                "parents": parents,
                "prev_commit": parents[0] if parents else None,
                "author_name": author_name,
                "author_email": author_email,
                "author_date": author_date,
                "subject": subject,
                "trailers": trailers,
                "patch_info": patch_meta,
            }

            full_content = (
                f"Commit: {sha}\n"
                f"Author: {author_name} <{author_email}>\n"
                f"Date: {author_date}\n"
                f"Parent(s): {', '.join(parents)}\n\n"
                f"{body_and_diff}"
            )

            yield create_trace_record(
                document_name=doc_name,
                content=full_content,
                source_uri=f"git://kernel.org/linux/commit/{sha}",
                metadata=metadata,
                collection="lkml",
            )
            count += 1
            if limit is not None and count >= limit:
                process.terminate()
                return


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract and stage Linux Kernel Git commits, DAG history, and LKML patches."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_SCALE_DATA_ROOT / "lkml" / "lkml_commits.jsonl",
        help=f"Destination JSONL filepath (default: {DEFAULT_SCALE_DATA_ROOT / 'lkml' / 'lkml_commits.jsonl'})",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=None,
        help="Max number of commits/patches to extract.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run fast synthetic dry-run verification with realistic commit DAG & diffs.",
    )
    parser.add_argument(
        "--git-dir",
        type=Path,
        default=None,
        help="Path to a local git repository (e.g. linux kernel clone).",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default="HEAD",
        help="Git branch or revision range (default: HEAD).",
    )
    parser.add_argument(
        "--no-diff",
        action="store_true",
        help="Exclude unified patch diffs to reduce token size.",
    )

    args = parser.parse_args()

    print("=== LKML / Linux Kernel Git Staging Suite ===")
    get_default_staging_dir("lkml")

    if args.dry_run:
        print("[Mode] DRY-RUN verification")
        limit = args.limit or 10
        records = list(generate_synthetic_lkml_records(count=limit))
        count = write_jsonl_records(records, args.output, limit=limit)
        print(f"[Success] Dry-run staged {count} LKML commit records to {args.output}")
        return 0

    if args.git_dir:
        generator = iterate_git_log(
            repo_path=args.git_dir,
            revision_range=args.branch,
            limit=args.limit,
            include_diff=not args.no_diff,
        )
    else:
        print("[Info] No --git-dir specified. Defaulting to dry-run verification.")
        generator = generate_synthetic_lkml_records(count=args.limit or 10)

    count = write_jsonl_records(generator, args.output, limit=args.limit)
    print(f"[Done] Staged {count:,} LKML commit records to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
