#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Hermetic tests for tools/verify_20k.py.

Each test builds a scratch fixture tree (MANIFEST.json, result.json,
local_20k_data.json plus the real explorer data-file bytes copied in) and
runs the verifier CLI against it. Scratch goes to tempfile (honour TMPDIR).

Run from the repo root, foreground:
  TMPDIR=<scratch> python3 -W error::ResourceWarning -m unittest tools.test_verify_20k
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, "tools", "verify_20k.py")

REL_MANIFEST = "docs/reproduction/repro-20k/MANIFEST.json"
REL_RESULT = "docs/reproduction/repro-20k/pilot-20k-out2/result.json"
REL_LOCAL = "docs/explorer/local_20k_data.json"
REL_CORPUS = "docs/explorer/data/corpus.js"
REL_REPLAY = "docs/explorer/data/replay.js"


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)
        fh.write("\n")


def good_manifest():
    return {
        "prefix_20k": {"actual_tokens": 20030, "atoms": 144},
        "verify_local": {"result": "PASS (8/8 checks)"},
        "small_pilot": {"status": "PASS"},
    }


def good_result():
    return {
        "status": "PASS",
        "input": {"actual_tokens": 20030, "atoms": 144},
        "final": {"atoms": 144, "leaves": 81, "parents": 51},
    }


class Verify20kTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="g2verify-")
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        # Real data-file bytes copied in (read-only source); JSON fixtures generated.
        for rel in (REL_LOCAL, REL_CORPUS, REL_REPLAY):
            dst = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(ROOT, rel), dst)
        write_json(os.path.join(self.root, REL_MANIFEST), good_manifest())
        write_json(os.path.join(self.root, REL_RESULT), good_result())

    def run_verify(self):
        proc = subprocess.run(
            [sys.executable, VERIFY, "--root", self.root],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=120,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def corrupt_json(self, rel, *keys, value):
        path = os.path.join(self.root, rel)
        with open(path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        cur = obj
        for key in keys[:-1]:
            cur = cur[key]
        cur[keys[-1]] = value
        write_json(path, obj)

    def test_all_green_reports_identical(self):
        rc, out, err = self.run_verify()
        self.assertEqual(rc, 0, "stderr: %s" % err)
        self.assertEqual(out, "IDENTICAL\n")
        self.assertEqual(err, "")

    def test_corrupt_tokens_named(self):
        self.corrupt_json(REL_MANIFEST, "prefix_20k", "actual_tokens", value=999)
        rc, out, _err = self.run_verify()
        self.assertEqual(rc, 1)
        self.assertIn("tokens", out)
        self.assertTrue(out.startswith("MISMATCH "))

    def test_corrupt_atoms_named(self):
        self.corrupt_json(REL_RESULT, "final", "atoms", value=999)
        rc, out, _err = self.run_verify()
        self.assertEqual(rc, 1)
        self.assertIn("atoms", out)
        self.assertTrue(out.startswith("MISMATCH "))

    def test_corrupt_leaves_named(self):
        self.corrupt_json(REL_RESULT, "final", "leaves", value=0)
        rc, out, _err = self.run_verify()
        self.assertEqual(rc, 1)
        self.assertIn("leaves", out)
        self.assertTrue(out.startswith("MISMATCH "))

    def test_corrupt_parents_named(self):
        self.corrupt_json(REL_RESULT, "final", "parents", value=0)
        rc, out, _err = self.run_verify()
        self.assertEqual(rc, 1)
        self.assertIn("parents", out)
        self.assertTrue(out.startswith("MISMATCH "))

    def test_corrupt_manifest_named(self):
        self.corrupt_json(REL_RESULT, "status", value="FAIL")
        rc, out, _err = self.run_verify()
        self.assertEqual(rc, 1)
        self.assertIn("manifest", out)
        self.assertTrue(out.startswith("MISMATCH "))

    def test_corrupt_data_file_named(self):
        path = os.path.join(self.root, REL_CORPUS)
        with open(path, "r+b") as fh:
            fh.seek(0)
            first = fh.read(1)
            fh.seek(0)
            fh.write(b"\x00" if first != b"\x00" else b"\x01")
        rc, out, _err = self.run_verify()
        self.assertEqual(rc, 1)
        self.assertIn("bytes", out)
        self.assertIn(REL_CORPUS, out)
        self.assertTrue(out.startswith("MISMATCH "))

    def test_deterministic(self):
        first = self.run_verify()
        second = self.run_verify()
        self.assertEqual(first, second)
        self.assertEqual(first[0], 0)
        self.assertEqual(first[1], "IDENTICAL\n")


if __name__ == "__main__":
    unittest.main()
