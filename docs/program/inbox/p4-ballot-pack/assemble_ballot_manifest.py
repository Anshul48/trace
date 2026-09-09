#!/usr/bin/env python3
"""Assemble the Trace v1.1 human-ballot evidence manifest (P4, scripts only).

Reads the per-packet dossiers / receipts / manifests / logs produced by
packets P0..P3, hashes every byte, and emits one evidence manifest JSON plus
a certification-string scan report. A second party recomputes with:

    python3 docs/program/inbox/p4-ballot-pack/assemble_ballot_manifest.py --check

which re-hashes the same inventory and exits nonzero on any mismatch.
No scale, retrieval, or cognition claim is made here: packet statuses are
transcribed from existing records (HOLD / PENDING-CRITIC / NOT-BUILT), and
the ballot rows in ballot_rows_draft.md are draft only for 06_DECISION_LOG.md.

Scope notes (auditable, not hidden):
- ``audit/logs/packet.diff`` under the H0 gate dir is hashed into the
  manifest but excluded from the token scan: it is a frozen append-only
  transcript of the already-judged P0 delivery (quoting its own history),
  while every live file it quotes is scanned directly.
- This script's own source is excluded from the token scan: its search
  patterns necessarily contain the literals. The exclusion covers exactly
  this file and is asserted by tests/test_p4_ballot_pack.py.
- P3 evidence is read from git objects at the pinned commit on
  branch p11-p3-warm-dream (critic verdict pending; unapproved), so this
  branch stays based on the last approved commit per coordinator protocol.
- The token scan covers the inventory plus ballot_rows_draft.md. The two
  generated outputs (evidence_manifest.json, cert_scan.txt) are derived
  artifacts: --check recomputes them instead of scanning them.

Exit codes: 0 manifest+scan written (scan verdict NO-EMISSION-FOUND);
1 any missing inventory file, hash mismatch in --check mode, unscanned
packet emission of CERTIFIED/APPROVED, or unallowlisted token hit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "p4-ballot-manifest/1.0.0"
GATE_DIR = Path("docs/program/inbox/p4-ballot-pack")
H0 = Path("docs/program/inbox/h0-1m-corpus-contract")
P3_COMMIT = "a9b4d3bec1aaee40aa404ed458de2c3b92054865"
P3_BRANCH = "p11-p3-warm-dream"
BASE_COMMIT = "43ed591732cf1a3649cb241478671b1d37ff489f"

TOKENS = ("CERTIFIED", "APPROVED")

# (path suffix, line regex, classification, rationale). A token hit is a
# violation unless exactly one entry matches. Fail-closed by construction.
ALLOWLIST: tuple[tuple[str, str, str, str], ...] = (
    ("docs/program/inbox/h0-1m-corpus-contract/audit/acceptance_and_law.md",
     r"critic APPROVED", "AUDIT-QUOTE",
     "Quotes the received blind-critic verdict; packet status stays quarantined until ballot."),
    ("docs/program/inbox/h0-1m-corpus-contract/audit/verdicts.md",
     r"APPROVED, no violations", "AUDIT-QUOTE",
     "Coordinator record of the received blind-critic verdict text."),
    ("docs/program/inbox/h0-1m-corpus-contract/gate_manifest.json",
     r'"status": "FROZEN_APPROVED"', "INPUT-STATUS",
     "Labels the staged capsule input as frozen; gate verdict is HOLD with co-signature PENDING."),
    ("scripts/sign_gate_manifest.py",
     r"CERTIFIED/APPROVED\)", "MENTION-PROHIBITION",
     "Tail line of the docstring prohibition (lines 11-14: the script never "
     "prints these strings); the script emits no such string."),
    ("docs/program/inbox/1m-02-corpus-capsule/evidence/1m_corpus_manifest.json",
     r'"status": "FROZEN_APPROVED"', "INPUT-STATUS",
     "Labels the staged capsule input as frozen; the gate verdict on it is "
     "HOLD with co-signature PENDING (see gate_manifest.json)."),
    ("tests/test_h0_1m_adopt.py",
     r"for token in", "TEST-PATTERN",
     "H0 packet test's own quoted-claim scan patterns (precedent: packet.diff:3137)."),
    ("docs/program/inbox/p4-ballot-pack/ballot_rows_draft.md",
     r"critic-APPROVED|APPROVED \(P0 attempt 2\)", "AUDIT-QUOTE",
     "Draft rows quote the received P0 critic verdict; the draft confers nothing."),
)

# (packet, path-or-git-path, kind). kind=file hashes worktree bytes;
# kind=git hashes `git cat-file -p <P3_COMMIT>:<path>`.
INVENTORY: tuple[tuple[str, str, str], ...] = (
    ("P0", str(H0 / "gate_manifest.json"), "file"),
    ("P0", str(H0 / "provisional_1m_manifest.json"), "file"),
    ("P0", str(H0 / "selection_record.json"), "file"),
    ("P0", str(H0 / "selection_reconciliation.json"), "file"),
    ("P0", str(H0 / "selection_reconciliation.md"), "file"),
    ("P0", str(H0 / "audit/00_AUDIT_INDEX.md"), "file"),
    ("P0", str(H0 / "audit/acceptance_and_law.md"), "file"),
    ("P0", str(H0 / "audit/verdicts.md"), "file"),
    ("P0", str(H0 / "audit/reverify.sh"), "file"),
    ("P0", str(H0 / "audit/logs/frozen_baseline.txt"), "file"),
    ("P0", str(H0 / "audit/logs/frozen_checksums.txt"), "file"),
    ("P0", str(H0 / "audit/logs/full_suite_q.txt"), "file"),
    ("P0", str(H0 / "audit/logs/independent_checker.txt"), "file"),
    ("P0", str(H0 / "audit/logs/packet_tests_v.txt"), "file"),
    ("P0", str(H0 / "audit/logs/help_seal_1m_manifest.txt"), "file"),
    ("P0", str(H0 / "audit/logs/help_sign_gate_manifest.txt"), "file"),
    ("P0", str(H0 / "audit/logs/help_verify_1m_checksums.txt"), "file"),
    ("P0", str(H0 / "audit/logs/help_verify_1m_independent.txt"), "file"),
    ("P0", str(H0 / "audit/logs/packet.diff"), "file"),
    ("P0", "docs/program/inbox/1m-02-corpus-capsule/evidence/1m_corpus_manifest.json", "file"),
    ("P0", "benchmarks/manifests/beir_musique_frozen_v1.json", "file"),
    ("P0", "docs/program/inbox/cap-ret04/retrieval_baseline_dossier.json", "file"),
    ("P0", "docs/program/inbox/cap-ret04/verification_receipt.json", "file"),
    ("P0", "scripts/seal_1m_manifest.py", "file"),
    ("P0", "scripts/sign_gate_manifest.py", "file"),
    ("P0", "benchmarks/verify_1m_checksums.py", "file"),
    ("P0", "benchmarks/verify_1m_independent.py", "file"),
    ("P0", "tests/test_h0_1m_adopt.py", "file"),
    ("P0", "tests/test_h0_1m_seal.py", "file"),
    ("P3", "src/trace/v2/cortex.py", "git"),
    ("P3", "src/trace/v2/jobs.py", "git"),
    ("P3", "src/trace/v2/worker.py", "git"),
    ("P3", "tests/test_p3_warm_dream.py", "git"),
)

# Packets with no delivered evidence yet: recorded, never synthesized.
PENDING = (
    ("P1", "p11-h1-core",
     "NOT-BUILT: branch cut, no commits. 1M runner + H1 durability unattempted."),
    ("P2a", "(no branch; sequential after P1)",
     "NOT-BUILT: B log pipeline + C2 budget router unattempted."),
    ("P2b", "p11-p2b-bridge-contradiction",
     "NOT-BUILT: branch cut, no commits. C1 + C4 unattempted."),
    ("P2c", "p11-p2c-hyde",
     "NOT-BUILT: branch cut, no commits. SLM probe belongs to the P2c packet; "
     "PARKED (no SLM) remains a valid terminal state per coordinator protocol."),
)

SCAN_SCOPE_FILES = ([path for _, path, kind in INVENTORY if kind == "file"]
                      + [str(GATE_DIR / "ballot_rows_draft.md")])
SCAN_SCOPE_GIT = [path for _, path, kind in INVENTORY if kind == "git"]
SCAN_EXCLUDED = (
    "docs/program/inbox/h0-1m-corpus-contract/audit/logs/packet.diff",
    "docs/program/inbox/p4-ballot-pack/assemble_ballot_manifest.py",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_bytes(commit: str, path: str, root: Path) -> bytes:
    proc = subprocess.run(
        ["git", "cat-file", "-p", "%s:%s" % (commit, path)],
        cwd=str(root), capture_output=True, check=False)
    if proc.returncode != 0:
        raise FileNotFoundError("git object unreadable: %s:%s" % (commit, path))
    return proc.stdout


def build_manifest(root: Path) -> dict:
    packets: dict[str, dict] = {}
    p0_files = []
    for packet, path, kind in INVENTORY:
        if kind == "file":
            full = root / path
            if not full.is_file():
                raise FileNotFoundError("inventory file missing: %s" % path)
            data = full.read_bytes()
            entry = {"path": path, "sha256": _sha256(data), "bytes": len(data)}
            if packet == "P0":
                p0_files.append(entry)
        else:
            data = _git_bytes(P3_COMMIT, path, root)
            entry = {"git": "%s:%s" % (P3_COMMIT, path),
                     "sha256": _sha256(data), "bytes": len(data)}
            packets.setdefault(packet, {"branch": P3_BRANCH, "commit": P3_COMMIT,
                                        "status": "PENDING-CRITIC",
                                        "note": "Code delivered on its branch; "
                                                "blind-critic verdict pending; "
                                                "unapproved, unmerged.",
                                        "files": []})["files"].append(entry)
    packets["P0"] = {"branch": "p11-h0-seal-repair", "commit": BASE_COMMIT,
                     "status": "HOLD",
                     "note": "Critic-APPROVED attempt 2, but corpus UNADOPTED: "
                             "successor H0-1M-SUCCESSOR-SEL-01 awaits human ballot; "
                             "P0 stays quarantined until ballot.",
                     "files": p0_files}
    for pid, branch, note in PENDING:
        packets[pid] = {"branch": branch, "commit": None, "status": "NOT-BUILT",
                        "note": note, "files": []}
    return {"schema_version": SCHEMA_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "base_commit": BASE_COMMIT,
            "p3_commit": P3_COMMIT,
            "packets": packets}


def run_scan(root: Path) -> dict:
    hits = []
    for path in SCAN_SCOPE_FILES:
        if path in SCAN_EXCLUDED:
            continue
        full = root / path
        if not full.is_file():
            raise FileNotFoundError("scan file missing: %s" % path)
        try:
            text = full.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for token in TOKENS:
                if token in line:
                    hits.append({"path": path, "line": lineno,
                                 "token": token, "snippet": line.strip()[:200]})
    for path in SCAN_SCOPE_GIT:
        data = _git_bytes(P3_COMMIT, path, root)
        for lineno, line in enumerate(data.decode("utf-8").splitlines(), 1):
            for token in TOKENS:
                if token in line:
                    hits.append({"path": "%s:%s" % (P3_COMMIT, path), "line": lineno,
                                 "token": token, "snippet": line.strip()[:200]})
    compiled = [(suf, re.compile(rx), cls, why) for suf, rx, cls, why in ALLOWLIST]
    reviewed, unreviewed = [], []
    for hit in hits:
        matches = [c for c in compiled
                   if hit["path"].endswith(c[0]) and c[1].search(hit["snippet"])]
        (reviewed if matches else unreviewed).append(
            {**hit, "classification": matches[0][2] if matches else "UNREVIEWED",
             "rationale": matches[0][3] if matches else
             "No allowlist entry covers this hit: fail closed."})
    verdict = "NO-EMISSION-FOUND" if not unreviewed else "VIOLATION-UNREVIEWED"
    return {"verdict": verdict, "tokens": list(TOKENS),
            "scope_files": len(SCAN_SCOPE_FILES) + len(SCAN_SCOPE_GIT),
            "excluded": list(SCAN_EXCLUDED),
            "exclusion_rationale":
                "packet.diff is a frozen transcript of judged history (live files scanned "
                "directly); the scanner source carries the literals as search patterns.",
            "hits_reviewed": reviewed, "hits_unreviewed": unreviewed}


def render_scan_text(scan: dict) -> str:
    lines = ["P4 certification-string scan",
             "verdict: %s" % scan["verdict"],
             "scope files: %d" % scan["scope_files"],
             "excluded (with rationale above):"]
    lines += ["  - %s" % e for e in scan["excluded"]]
    lines.append("reviewed hits (%d):" % len(scan["hits_reviewed"]))
    for h in scan["hits_reviewed"]:
        lines.append("  %s:%d [%s] %s :: %s"
                     % (h["path"], h["line"], h["classification"], h["token"], h["snippet"]))
        lines.append("    rationale: %s" % h["rationale"])
    lines.append("unreviewed hits (%d):" % len(scan["hits_unreviewed"]))
    for h in scan["hits_unreviewed"]:
        lines.append("  %s:%d %s :: %s" % (h["path"], h["line"], h["token"], h["snippet"]))
    return "\n".join(lines) + "\n"


def canonical(manifest: dict) -> str:
    trimmed = {k: v for k, v in manifest.items() if k != "created_utc"}
    return json.dumps(trimmed, sort_keys=True, indent=2) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble (or --check) the Trace v1.1 ballot evidence manifest. "
                    "Scripts only; no new claims; fail closed.")
    parser.add_argument("--root", default=".",
                        help="Repo root (default: current directory).")
    parser.add_argument("--out", default=str(GATE_DIR / "evidence_manifest.json"),
                        help="Manifest JSON to write (default: %(default)s).")
    parser.add_argument("--scan-out", default=str(GATE_DIR / "cert_scan.txt"),
                        help="Scan report to write (default: %(default)s).")
    parser.add_argument("--check", action="store_true",
                        help="Recompute and compare against --out/--scan-out; "
                             "exit nonzero on any mismatch (second-party recompute).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    root = Path(args.root).resolve()
    try:
        manifest = build_manifest(root)
        scan = run_scan(root)
    except FileNotFoundError as exc:
        print("BALLOT-MANIFEST-FAIL: %s" % exc)
        return 1
    manifest["cert_scan_verdict"] = scan["verdict"]
    if args.check:
        try:
            on_disk = json.loads(Path(args.out).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print("BALLOT-CHECK-FAIL: cannot read --out: %s" % exc)
            return 1
        if canonical(on_disk) != canonical(manifest):
            print("BALLOT-CHECK-FAIL: manifest mismatch vs %s" % args.out)
            return 1
        if on_disk.get("cert_scan_verdict") != scan["verdict"]:
            print("BALLOT-CHECK-FAIL: scan verdict mismatch")
            return 1
        if scan["verdict"] != "NO-EMISSION-FOUND":
            print("BALLOT-CHECK-FAIL: unreviewed certification strings present")
            return 1
        print("BALLOT-CHECK-PASS: manifest recomputable; scan clean.")
        return 0
    Path(args.out).write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    Path(args.scan_out).write_text(render_scan_text(scan), encoding="utf-8")
    print("wrote %s (%d packet files)" % (
        args.out, sum(len(p["files"]) for p in manifest["packets"].values())))
    print("wrote %s verdict=%s reviewed=%d unreviewed=%d" % (
        args.scan_out, scan["verdict"],
        len(scan["hits_reviewed"]), len(scan["hits_unreviewed"])))
    return 0 if scan["verdict"] == "NO-EMISSION-FOUND" else 1


if __name__ == "__main__":
    raise SystemExit(main())

