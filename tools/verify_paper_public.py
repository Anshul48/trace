#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Public receipt check for judges: wraps paper/check_receipts.py.

Runs the paper's receipt checker over the published write-up and classifies
the result. Prints one PUBLIC CHECK OK line and exits 0 ONLY when every
checker problem is the known withheld evidence file (listed in
WITHHELD_FILES below) and the set of missing files matches that list
exactly. Anything else — including a genuine full pass, which prints the
checker's own OK line — behaves honestly: any other problem prints the
checker's own output and exits 1.

Run from the repo root (stdlib only, no downloads):

    python3 tools/verify_paper_public.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(ROOT, "paper")

# Evidence files deliberately not published, with reason. Paths as they
# appear in paper/receipts.json (relative to paper/). This list is fixed:
# the OK line below prints only when the checker's missing files equal it.
WITHHELD_FILES = {
    "evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md",
}
WITHHELD_REASON = "contains a server address"

RE_MISSING = re.compile(r"^RECEIPT (\S+): file does not exist: (\S+)\s*$")


def main():
    os.chdir(PAPER)
    sys.path.insert(0, PAPER)
    import check_receipts

    failures, report = check_receipts.run_checks(
        "writeup-arxiv.html", "receipts.json", "banned.txt")
    if not failures:
        sys.stdout.write(report)
        return 0
    missing = set()
    for f in failures:
        m = RE_MISSING.match(f)
        if not m or m.group(2) not in WITHHELD_FILES:
            sys.stdout.write(report)
            return 1
        missing.add(m.group(2))
    if missing != WITHHELD_FILES:
        sys.stdout.write(report)
        return 1
    receipts = json.loads(open("receipts.json", encoding="utf-8").read())
    wset = {rid for rid, rec in receipts.items()
            if rec.get("file") in WITHHELD_FILES}
    parser = check_receipts.BodyScan()
    parser.feed(open("writeup-arxiv.html", encoding="utf-8").read())
    spans = parser.spans
    w = sum(1 for sp in spans if sp.get("receipt") in wset)
    sys.stdout.write(
        "PUBLIC CHECK OK: %d of %d receipted spans verified against "
        "published files; %d spans cite %d withheld file (%s); "
        "0 other problems\n"
        % (len(spans) - w, len(spans), w, len(WITHHELD_FILES),
           WITHHELD_REASON))
    return 0


if __name__ == "__main__":
    sys.exit(main())
