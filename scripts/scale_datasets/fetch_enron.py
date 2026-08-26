#!/usr/bin/env python3
"""Fetch, parse, and stage the Enron Corporate Email Corpus.

The Enron Email Dataset contains ~500,000 emails from ~150 senior management
employees (~15M - 50M tokens).

This script extracts:
- Sender, recipients (To, Cc, Bcc), timestamps (normalized to ISO 8601)
- Subject, folder origin, custodian
- Clean email body text
- Conversation threading metadata (Message-ID, In-Reply-To, References, normalized thread key)

Supports:
- Direct streaming from .tar.gz archive without full disk extraction
- Ingestion from pre-extracted maildir directory
- --dry-run for fast offline testing and schema validation
- --limit <N> for bounded ingestion
- Standard Phase 1 JSONL output
"""

from __future__ import annotations

import argparse
import email
import email.policy
import email.utils
import os
import re
import sys
import tarfile
import urllib.request
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

ENRON_TAR_URL = "https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz"


def normalize_thread_subject(subject: str) -> str:
    """Normalize subject line by stripping Re:, Fwd:, etc. for conversation grouping."""
    if not subject:
        return "(no subject)"
    cleaned = re.sub(r"^(\s*(?:re|fwd?|fw|aw)\s*:\s*)+", "", subject, flags=re.IGNORECASE)
    return cleaned.strip() or "(no subject)"


def parse_date_to_iso(date_str: str | None) -> str | None:
    """Parse RFC 2822 email date string into ISO 8601 UTC timestamp."""
    if not date_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def parse_email_message(raw_content: str | bytes, file_path_hint: str = "") -> dict[str, Any] | None:
    """Parse raw email message string/bytes into structured fields and clean text."""
    try:
        if isinstance(raw_content, bytes):
            msg = email.message_from_bytes(raw_content, policy=email.policy.default)
        else:
            msg = email.message_from_string(raw_content, policy=email.policy.default)
    except Exception:
        return None

    # Extract headers
    msg_id = (msg.get("Message-ID") or "").strip()
    date_raw = msg.get("Date")
    date_iso = parse_date_to_iso(date_raw)
    subject = (msg.get("Subject") or "").strip()
    thread_key = normalize_thread_subject(subject)

    from_raw = msg.get("From") or ""
    to_raw = msg.get("To") or ""
    cc_raw = msg.get("Cc") or ""
    bcc_raw = msg.get("Bcc") or ""

    sender = email.utils.parseaddr(from_raw)[1] or from_raw.strip()
    to_list = [addr[1] for addr in email.utils.getaddresses([to_raw]) if addr[1]]
    cc_list = [addr[1] for addr in email.utils.getaddresses([cc_raw]) if addr[1]]
    bcc_list = [addr[1] for addr in email.utils.getaddresses([bcc_raw]) if addr[1]]
    all_recipients = list(dict.fromkeys(to_list + cc_list + bcc_list))

    in_reply_to = (msg.get("In-Reply-To") or "").strip()
    references = (msg.get("References") or "").strip()

    # Enron-specific headers
    x_from = (msg.get("X-From") or "").strip()
    x_to = (msg.get("X-To") or "").strip()
    x_folder = (msg.get("X-Folder") or "").strip()
    x_origin = (msg.get("X-Origin") or "").strip()
    x_filename = (msg.get("X-FileName") or "").strip()

    # Extract body text
    body = ""
    try:
        if msg.is_multipart():
            parts = []
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode("utf-8", errors="replace"))
            body = "\n\n".join(parts)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")
            else:
                body = str(msg.get_payload() or "")
    except Exception:
        body = str(msg.get_payload() or "")

    clean_body = clean_text_whitespace(body)
    if not clean_body and not subject:
        return None

    # Derive document name from path hint or msg_id
    doc_name = file_path_hint or f"enron/{x_origin or 'unknown'}/{msg_id or 'msg'}"

    # Build readable document text block
    header_block = [
        f"From: {x_from or sender}",
        f"To: {x_to or ', '.join(to_list)}",
    ]
    if cc_list:
        header_block.append(f"Cc: {', '.join(cc_list)}")
    if date_iso:
        header_block.append(f"Date: {date_iso}")
    header_block.append(f"Subject: {subject or '(no subject)'}")
    if x_folder:
        header_block.append(f"Folder: {x_folder}")

    full_text = "\n".join(header_block) + "\n\n" + clean_body

    metadata = {
        "dataset": "enron",
        "sender": sender,
        "sender_name": x_from,
        "recipients": all_recipients,
        "to": to_list,
        "cc": cc_list,
        "bcc": bcc_list,
        "subject": subject,
        "thread_key": thread_key,
        "message_id": msg_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "date_raw": date_raw,
        "date_iso": date_iso,
        "folder": x_folder,
        "custodian": x_origin,
        "original_file": x_filename,
        "source_path": file_path_hint,
    }

    return create_trace_record(
        document_name=doc_name,
        content=full_text,
        source_uri=f"enron://{doc_name.replace('\\', '/')}",
        metadata=metadata,
        collection="enron",
    )


def generate_synthetic_enron_records(count: int = 15) -> Generator[dict[str, Any], None, None]:
    """Generate realistic synthetic Enron email threads for dry-run verification."""
    threads = [
        {
            "thread_key": "California Power Market & Risk Assessment",
            "subject_base": "California Power Market & Risk Assessment",
            "messages": [
                {
                    "from_name": "Jeff Skilling",
                    "from_addr": "jeff.skilling@enron.com",
                    "to": ["kenneth.lay@enron.com", "vince.kaminski@enron.com"],
                    "date": "2001-04-12T14:30:00Z",
                    "msg_id": "<skilling-1001@enron.com>",
                    "body": (
                        "Ken, Vince -\n\n"
                        "Following our conversation yesterday regarding Western electricity price volatility, "
                        "we need a comprehensive stress test of our forward curve models in the California ISO market. "
                        "The risk committee will review our value-at-risk (VaR) thresholds next Tuesday.\n\n"
                        "Please provide the preliminary numbers by Monday morning.\n\n"
                        "Regards,\nJeff"
                    ),
                    "folder": "notes_inbox",
                    "custodian": "skilling-j",
                },
                {
                    "from_name": "Vince J Kaminski",
                    "from_addr": "vince.kaminski@enron.com",
                    "to": ["jeff.skilling@enron.com"],
                    "cc": ["kenneth.lay@enron.com", "stinson.gibner@enron.com"],
                    "date": "2001-04-12T16:45:00Z",
                    "msg_id": "<kaminski-2002@enron.com>",
                    "in_reply_to": "<skilling-1001@enron.com>",
                    "body": (
                        "Jeff,\n\n"
                        "The Research Group has started calibration of the Monte Carlo simulation engine. "
                        "Under extreme load scenarios, current liquidity assumptions may underestimate tail risk "
                        "by approximately 18-24%.\n\n"
                        "Stinson Gibner and I are refining the correlation matrices between Northwest hydro "
                        "availability and Southern California peak demand. We will deliver the full technical "
                        "memorandum on Monday at 9:00 AM.\n\n"
                        "Vince"
                    ),
                    "folder": "sent_items",
                    "custodian": "kaminski-v",
                },
                {
                    "from_name": "Kenneth Lay",
                    "from_addr": "kenneth.lay@enron.com",
                    "to": ["vince.kaminski@enron.com", "jeff.skilling@enron.com"],
                    "date": "2001-04-13T08:15:00Z",
                    "msg_id": "<lay-3003@enron.com>",
                    "in_reply_to": "<kaminski-2002@enron.com>",
                    "body": (
                        "Vince, Jeff,\n\n"
                        "Thank you for the update. Ensure that Greg Whalley and Mark Frevert are looped into "
                        "the findings so commercial desks can adjust hedge ratios accordingly.\n\n"
                        "Ken"
                    ),
                    "folder": "all_documents",
                    "custodian": "lay-k",
                },
            ],
        },
        {
            "thread_key": "LJM2 Special Purpose Vehicle Review",
            "subject_base": "LJM2 Special Purpose Vehicle Review",
            "messages": [
                {
                    "from_name": "Sherron Watkins",
                    "from_addr": "sherron.watkins@enron.com",
                    "to": ["kenneth.lay@enron.com"],
                    "date": "2001-08-15T11:00:00Z",
                    "msg_id": "<watkins-4001@enron.com>",
                    "body": (
                        "Dear Mr. Lay,\n\n"
                        "I am writing to express grave concerns regarding our accounting practices and "
                        "the off-balance sheet partnerships created through LJM and Chewco entities. "
                        "Has Enron become a risky place to work? For those of us who have stayed with "
                        "the company, it appears our financial statements may face significant restatement "
                        "if Raptor hedging mechanisms unwind.\n\n"
                        "I recommend an independent legal and accounting investigation.\n\n"
                        "Sincerely,\nSherron Watkins"
                    ),
                    "folder": "inbox",
                    "custodian": "lay-k",
                },
                {
                    "from_name": "Kenneth Lay",
                    "from_addr": "kenneth.lay@enron.com",
                    "to": ["james.derrick@enron.com"],
                    "date": "2001-08-15T15:20:00Z",
                    "msg_id": "<lay-5002@enron.com>",
                    "in_reply_to": "<watkins-4001@enron.com>",
                    "body": (
                        "Jim,\n\n"
                        "Please review the attached memorandum from Sherron Watkins with external counsel "
                        "at Vinson & Elkins. We need a discrete inquiry into the structure of these transactions.\n\n"
                        "Ken"
                    ),
                    "folder": "sent",
                    "custodian": "lay-k",
                },
            ],
        },
    ]

    generated = 0
    for thread in threads:
        base_subj = thread["subject_base"]
        for idx, m in enumerate(thread["messages"]):
            if generated >= count:
                return
            subj = f"Re: {base_subj}" if idx > 0 else base_subj
            to_field = ", ".join(m.get("to", []))
            cc_field = ", ".join(m.get("cc", []))
            raw_email = (
                f"Message-ID: {m['msg_id']}\n"
                f"Date: {m['date']}\n"
                f"From: {m['from_addr']}\n"
                f"To: {to_field}\n"
                + (f"Cc: {cc_field}\n" if cc_field else "")
                + f"Subject: {subj}\n"
                f"X-From: {m['from_name']}\n"
                f"X-To: {to_field}\n"
                f"X-Folder: \\{m['custodian']}\\{m['folder']}\n"
                f"X-Origin: {m['custodian']}\n"
                f"X-FileName: {m['custodian']}.nsf\n"
                + (f"In-Reply-To: {m['in_reply_to']}\n" if "in_reply_to" in m else "")
                + "\n"
                + m["body"]
            )
            rec = parse_email_message(
                raw_email,
                file_path_hint=f"maildir/{m['custodian']}/{m['folder']}/{generated + 1}_.",
            )
            if rec:
                yield rec
                generated += 1


def stream_enron_tar(tar_path: Path | str, limit: int | None = None) -> Generator[dict[str, Any], None, None]:
    """Stream and parse emails directly from a .tar.gz archive without extracting to disk."""
    path = Path(tar_path)
    if not path.is_file():
        raise FileNotFoundError(f"Tar file not found: {path}")

    count = 0
    print(f"[Enron] Opening tar archive stream: {path}")
    with tarfile.open(path, "r:*") as tar:
        for member in tar:
            if limit is not None and count >= limit:
                break
            if not member.isfile():
                continue
            # Skip hidden files or non-email files
            if member.name.endswith(".DS_Store") or "/." in member.name:
                continue

            try:
                f = tar.extractfile(member)
                if f is None:
                    continue
                raw_bytes = f.read()
                record = parse_email_message(raw_bytes, file_path_hint=member.name)
                if record:
                    yield record
                    count += 1
            except Exception as e:
                continue


def iterate_enron_maildir(maildir_path: Path | str, limit: int | None = None) -> Generator[dict[str, Any], None, None]:
    """Traverse an already extracted maildir directory."""
    root = Path(maildir_path)
    if not root.is_dir():
        raise NotADirectoryError(f"Directory not found: {root}")

    count = 0
    print(f"[Enron] Scanning maildir: {root}")
    for root_dir, _, files in os.walk(root):
        for fname in files:
            if limit is not None and count >= limit:
                return
            if fname.startswith("."):
                continue
            full_path = Path(root_dir) / fname
            try:
                raw_bytes = full_path.read_bytes()
                rel_path = str(full_path.relative_to(root))
                record = parse_email_message(raw_bytes, file_path_hint=rel_path)
                if record:
                    yield record
                    count += 1
            except Exception:
                continue


def download_enron_archive(dest_path: Path, url: str = ENRON_TAR_URL) -> Path:
    """Download Enron corpus tar archive with progress logging."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.is_file() and dest_path.stat().st_size > 100_000_000:
        print(f"[Enron] Using existing archive: {dest_path} ({dest_path.stat().st_size:,} bytes)")
        return dest_path

    print(f"[Enron] Downloading Enron archive from {url} to {dest_path} (~423 MB)...")
    urllib.request.urlretrieve(url, dest_path)
    print(f"[Enron] Download complete: {dest_path}")
    return dest_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch, parse, and stage the Enron Corporate Email Corpus into JSONL format."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_SCALE_DATA_ROOT / "enron" / "enron_emails.jsonl",
        help=f"Destination JSONL filepath (default: {DEFAULT_SCALE_DATA_ROOT / 'enron' / 'enron_emails.jsonl'})",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=None,
        help="Max number of email records to parse and output.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run fast synthetic dry-run verification without downloading.",
    )
    parser.add_argument(
        "--tar-path",
        type=Path,
        default=None,
        help="Path to an existing enron_mail_*.tar.gz file.",
    )
    parser.add_argument(
        "--maildir",
        type=Path,
        default=None,
        help="Path to an existing extracted maildir/ directory.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download official tar.gz archive if not present locally.",
    )

    args = parser.parse_args()

    print("=== Enron Email Corpus Ingestion & Staging ===")
    staging_dir = get_default_staging_dir("enron")

    if args.dry_run:
        print("[Mode] DRY-RUN verification")
        limit = args.limit or 10
        records = list(generate_synthetic_enron_records(count=limit))
        count = write_jsonl_records(records, args.output, limit=limit)
        print(f"[Success] Dry-run created {count} records in {args.output}")
        return 0

    if args.maildir:
        generator = iterate_enron_maildir(args.maildir, limit=args.limit)
    elif args.tar_path:
        generator = stream_enron_tar(args.tar_path, limit=args.limit)
    elif args.download:
        tar_dest = staging_dir / "enron_mail_20150507.tar.gz"
        download_enron_archive(tar_dest)
        generator = stream_enron_tar(tar_dest, limit=args.limit)
    else:
        print("[Info] Neither --maildir, --tar-path, --download, nor --dry-run specified.")
        print("[Info] Defaulting to dry-run mode for demonstration. Use --download or provide --tar-path for full scale.")
        generator = generate_synthetic_enron_records(count=args.limit or 10)

    count = write_jsonl_records(generator, args.output, limit=args.limit)
    print(f"[Done] Staged {count:,} Enron email records to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
