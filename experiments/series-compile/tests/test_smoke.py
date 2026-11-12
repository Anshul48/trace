# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the synthetic series-compile demo (stdlib only).

Hermetic: every test works in a scratch directory created inside this
package directory and removed afterwards; the demo subprocesses get that
scratch directory as TMPDIR so they leave nothing behind elsewhere.
"""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

PKGDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(PKGDIR, "series_compile.py")
EXPECTED = os.path.join(PKGDIR, "EXPECTED_OUTPUT.txt")
README = os.path.join(PKGDIR, "README.md")

sys.path.insert(0, PKGDIR)
import series_compile as sc


def fresh_data(root: str) -> dict:
    data_dir = tempfile.mkdtemp(prefix="data-", dir=root)
    return sc.gen_all(data_dir)


def run_cli(args, scratch: str) -> str:
    env = dict(os.environ)
    env["TMPDIR"] = scratch
    env["TEMP"] = scratch
    env["TMP"] = scratch
    done = subprocess.run([sys.executable, "-I", SCRIPT] + args,
                          capture_output=True, text=True, env=env,
                          timeout=120)
    if done.returncode != 0:
        raise AssertionError("CLI %r failed: %s" % (args, done.stderr))
    return done.stdout


class Smoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.mkdtemp(prefix="smoke-", dir=PKGDIR)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def test_gen_counts(self):
        paths = fresh_data(self.scratch)
        self.assertEqual(len(sc.read_runs(paths["a"])), 40)
        self.assertEqual(len(sc.read_runs(paths["b"])), 40)
        self.assertEqual(len(sc.read_runs(paths["c"])), 40)
        self.assertEqual(len(sc.read_runs(paths["d"])), 40)
        self.assertEqual(len(sc.read_runs(paths["e"])), 30)

    def test_gen_is_deterministic(self):
        first = fresh_data(self.scratch)
        second = fresh_data(self.scratch)
        for name in ("a", "b", "c", "d", "e"):
            old = sc.read_runs(first[name])
            new = sc.read_runs(second[name])
            self.assertEqual([sc.canon(run) for run in old],
                             [sc.canon(run) for run in new])

    def test_detect_finds_series_a_b_d(self):
        paths = fresh_data(self.scratch)
        for name in ("a", "b", "d"):
            series, count, _max = sc.detect_series(sc.read_runs(paths[name]))
            self.assertEqual(count, 40)
            self.assertEqual(len(series), 1)
            self.assertEqual(series[0][1], 40)

    def test_detect_finds_series_e(self):
        paths = fresh_data(self.scratch)
        series, count, _max = sc.detect_series(sc.read_runs(paths["e"]))
        self.assertEqual(count, 30)
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0][1], 30)

    def test_detect_finds_nothing_for_one_offs(self):
        paths = fresh_data(self.scratch)
        series, count, top = sc.detect_series(sc.read_runs(paths["c"]))
        self.assertEqual(count, 40)
        self.assertEqual(series, [])
        self.assertEqual(top, 1)

    def test_shadow_a_all_matched_copy_lower(self):
        paths = fresh_data(self.scratch)
        comp = sc.shadow_compare(sc.read_runs(paths["a"]))
        self.assertEqual(len(comp["matched"]), 40)
        self.assertEqual(comp["mismatched"], [])
        self.assertEqual(comp["corrupted"], [])
        self.assertLessEqual(comp["copy_prev_matched"], 4)

    def test_shadow_b_mismatch_block(self):
        paths = fresh_data(self.scratch)
        comp = sc.shadow_compare(sc.read_runs(paths["b"]))
        self.assertEqual(len(comp["matched"]), 20)
        self.assertEqual(len(comp["mismatched"]), 20)
        self.assertEqual(min(comp["mismatched"]), 21)
        self.assertEqual(max(comp["mismatched"]), 40)
        self.assertEqual(comp["first_bad_field"][21], "total_weight")

    def test_shadow_d_corrupted_run(self):
        paths = fresh_data(self.scratch)
        comp = sc.shadow_compare(sc.read_runs(paths["d"]))
        self.assertEqual(len(comp["matched"]), 39)
        self.assertEqual(comp["corrupted"], [17])
        runs = sc.read_runs(paths["d"])
        profile = sc.build_profile(sc.read_runs(paths["a"]))
        bad = [run for run in runs if run["id"] == 17][0]
        allowed, reason, _out = sc.guard_check(profile, bad["brief"],
                                               bad["input"])
        self.assertFalse(allowed)
        self.assertIn("corrupted-input", reason)
        self.assertIn("handoff-to-person", reason)

    def test_shadow_e_matches_one_worker_only(self):
        paths = fresh_data(self.scratch)
        runs = sc.read_runs(paths["e"])
        workers = sc.shadow_workers(runs)
        self.assertEqual(workers["n"], 30)
        self.assertEqual(workers["script_vs_worker_alpha"], 30)
        self.assertEqual(workers["script_vs_worker_beta"], 0)
        self.assertEqual(workers["script_vs_worker_gamma"], 0)
        self.assertEqual(workers["agree_worker_alpha_worker_beta"], 0)
        self.assertEqual(workers["agree_worker_alpha_worker_gamma"], 0)
        self.assertEqual(workers["agree_worker_beta_worker_gamma"], 0)

    def test_guard_allows_seen_input(self):
        paths = fresh_data(self.scratch)
        runs = sc.read_runs(paths["a"])
        profile = sc.build_profile(runs)
        allowed, reason, out = sc.guard_check(profile, runs[0]["brief"],
                                              runs[0]["input"])
        self.assertTrue(allowed)
        self.assertTrue(reason.startswith("ALLOWED "))
        self.assertEqual(out, runs[0]["output"])

    def test_guard_refuses_novel_schema_value_and_damage(self):
        paths = fresh_data(self.scratch)
        runs = sc.read_runs(paths["a"])
        profile = sc.build_profile(runs)
        brief = runs[0]["brief"]
        base = json.loads(sc.canon(runs[0]["input"]))

        novel_schema = json.loads(sc.canon(base))
        novel_schema["priority"] = "high"
        allowed, reason, _out = sc.guard_check(profile, brief, novel_schema)
        self.assertFalse(allowed)
        self.assertIn("new-schema", reason)

        novel_value = json.loads(sc.canon(base))
        novel_value["store"] = "WH-99"
        allowed, reason, _out = sc.guard_check(profile, brief, novel_value)
        self.assertFalse(allowed)
        self.assertIn("new-slot-value", reason)

        damaged = json.loads(sc.canon(base))
        damaged["items"][0]["weight"] = "N/A"
        allowed, reason, _out = sc.guard_check(profile, brief, damaged)
        self.assertFalse(allowed)
        self.assertIn("corrupted-input", reason)

        far = json.loads(sc.canon(base))
        far["items"][0]["weight"] = profile["max_weight"] + 100.0
        allowed, reason, _out = sc.guard_check(profile, brief, far)
        self.assertFalse(allowed)
        self.assertIn("out-of-range", reason)

        allowed, reason, _out = sc.guard_check(
            profile, "Something else entirely.", base)
        self.assertFalse(allowed)
        self.assertIn("unknown-brief", reason)

    def test_cli_detect_shadow_guard(self):
        paths = fresh_data(self.scratch)
        out = run_cli(["detect", paths["a"]], self.scratch)
        self.assertIn("SERIES count=40", out)
        out = run_cli(["detect", paths["c"]], self.scratch)
        self.assertIn("NO-SERIES", out)
        out = run_cli(["shadow", paths["b"]], self.scratch)
        self.assertIn("matched=20 mismatched=20", out)
        self.assertIn("first-mismatch-run=021", out)
        runs = sc.read_runs(paths["a"])
        payload_path = os.path.join(self.scratch, "guard-input.json")
        with open(payload_path, "w", encoding="utf-8") as handle:
            json.dump({"brief": runs[0]["brief"], "input": runs[0]["input"]},
                      handle)
        out = run_cli(["guard", "--series", paths["a"],
                       "--input", payload_path], self.scratch)
        self.assertTrue(out.startswith("ALLOWED "))

    def test_demo_twice_identical_and_matches_expected(self):
        first = run_cli(["demo"], self.scratch)
        second = run_cli(["demo"], self.scratch)
        self.assertEqual(first, second)
        with open(EXPECTED, encoding="utf-8") as handle:
            self.assertEqual(first, handle.read())

    def test_readme_shows_expected_output(self):
        with open(EXPECTED, encoding="utf-8") as handle:
            expected = handle.read()
        with open(README, encoding="utf-8") as handle:
            readme = handle.read()
        self.assertIn(expected, readme)

    def test_no_file_over_500kb(self):
        for root, _dirs, names in os.walk(PKGDIR):
            for name in names:
                if name == "__pycache__":
                    continue
                path = os.path.join(root, name)
                if os.path.isfile(path) and "__pycache__" not in path:
                    self.assertLess(os.path.getsize(path), 500 * 1024, path)

    def test_stdlib_imports_only(self):
        local = set()
        for name in os.listdir(PKGDIR):
            if name.endswith(".py"):
                local.add(name[:-3])
        local.add("tests")
        allowed = set(sys.stdlib_module_names) | local
        for root, _dirs, names in os.walk(PKGDIR):
            for name in names:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as handle:
                    tree = ast.parse(handle.read())
                roots = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        roots.update(part.name.split(".")[0]
                                     for part in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        roots.add(node.module.split(".")[0])
                self.assertLessEqual(roots, allowed, path)


if __name__ == "__main__":
    unittest.main()
