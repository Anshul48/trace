# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the paper bundle: the public check passes and the
shipped files are all present. Stdlib only; run with pytest or unittest."""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
PAPER = os.path.join(ROOT, "paper")

WITHHELD = "evidence/scratch/wave6/paper/evidence-facts/FACTS-AND-RULES.md"

EXPECTED_FILES = [
    "checkable-memory-for-agents.pdf",
    "writeup.txt",
    "writeup-arxiv.html",
    "paper.css",
    "check_receipts.py",
    "receipts.json",
    "banned.txt",
    "figures/img-1-problem.png",
    "figures/img-2-trace.png",
    "figures/img-3-audit.png",
    "figures/img-4-results.png",
    "figures/img-5-planted-errors.png",
    "figures/img-6-next.png",
    "video/checkable-memory-for-agents.mp4",
    "video/narration.txt",
]


class PaperBundleTest(unittest.TestCase):
    def test_public_check_ok(self):
        p = subprocess.run(
            [sys.executable, os.path.join("tools", "verify_paper_public.py")],
            cwd=ROOT, capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("0 other problems", p.stdout)

    def test_files_present(self):
        for f in EXPECTED_FILES:
            self.assertTrue(os.path.isfile(os.path.join(PAPER, f)), f)

    def test_receipts_resolve(self):
        rec = json.loads(open(os.path.join(PAPER, "receipts.json"),
                              encoding="utf-8").read())
        self.assertTrue(len(rec) > 0)
        for rid, e in rec.items():
            p = os.path.join(PAPER, e["file"])
            if e["file"] == WITHHELD:
                self.assertFalse(os.path.isfile(p), rid)
            else:
                self.assertTrue(os.path.isfile(p), rid)


if __name__ == "__main__":
    unittest.main()
