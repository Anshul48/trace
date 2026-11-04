"""API + backend-vs-frozen-function tests. Run: .venv/bin/python -m pytest tests/ -q
(falls back to unittest discovery: .venv/bin/python -m unittest discover tests)"""
import json
import sys
import unittest
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import backend  # noqa: E402


class TestBackendVsFrozen(unittest.TestCase):
    def test_guided_matches_direct_frozen_call(self):
        import numpy as np
        from tlsys.query import HierQuery
        out = backend.run_query(0, top_k=10, mode="guided")
        idx = backend.build_index()
        hq = HierQuery(backend.DemoArtifacts(), idx, lambda x: x)
        rows, report = hq.guided(backend.VECS[0], top_parents=4,
                                 top_children=8, top_atoms=10)
        self.assertEqual([r["aid"] for r in rows],
                         [r["aid"] for r in out["guided"]["rows"]])
        self.assertEqual(report["work"], out["guided"]["report"]["work"])

    def test_tie_recall_is_frozen(self):
        import product_pilot
        self.assertIs(backend.product_pilot.tie_recall, product_pilot.tie_recall)
        self.assertTrue(str(backend.SRC).endswith("cand") or
                        (backend.SRC / "SOURCEFREEZE.json").exists())

    def test_freeze_sha(self):
        self.assertEqual(backend.FREEZE_SHA,
                         "38c66bef71fbc8768a2887024fecf1bf58ff90f3"
                         "feaf3a922d4c8b51a43a0d54")

    def test_oracle_first_is_self_for_chunk_probe(self):
        out = backend.run_query(0, top_k=5, mode="both")
        self.assertEqual(out["oracle_top"][0], "a0")
        self.assertEqual(out["guided"]["rows"][0]["aid"], "a0")

    def test_lso_excludes_source(self):
        out = backend.run_query(0, top_k=5, mode="guided", lso=True)
        src = set(backend.PROBES[0]["sources"])
        for r in out["guided"]["rows"]:
            self.assertNotIn(r["doc_id"], src)

    def test_error_cases(self):
        for bad in (-1, 120, "x", None):
            with self.assertRaises((ValueError, TypeError)):
                backend.run_query(bad)
        with self.assertRaises(ValueError):
            backend.run_query(0, mode="neural-qa")

    def test_evidence_receipt_values(self):
        ev = backend.evidence()
        self.assertEqual(ev["oracle_status"],
                         "VERIFIED_PASS_READONLY_ORACLE_REPLAY")
        self.assertEqual(ev["input"]["actual_tokens"], 10003381)
        self.assertAlmostEqual(
            ev["summary"]["all_sources"]["guided_recall10"], 0.73)


class TestFreezeVerification(unittest.TestCase):
    def test_all_207_actual_files_match_manifest(self):
        sha, count = backend.verify_freeze_files(backend.SRC)
        self.assertEqual(sha, backend.EXPECTED_FREEZE_SHA)
        self.assertEqual(count, 207)

    def test_modified_source_byte_refuses_startup(self):
        import os
        import shutil
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cand = Path(td) / "cand"
            shutil.copytree(backend.SRC, cand,
                            ignore=shutil.ignore_patterns("__pycache__"))
            target = cand / "tools" / "product_pilot.py"
            data = bytearray(target.read_bytes())
            data[0] ^= 0xFF  # flip one actual source byte; manifest untouched
            target.write_bytes(bytes(data))
            with self.assertRaises(RuntimeError):
                backend.verify_freeze_files(cand)
            env = dict(os.environ, TRACE_FREEZE_SRC=str(cand),
                       PYTHONDONTWRITEBYTECODE="1")
            proc = subprocess.run(
                [sys.executable, "-B", "-c", "import backend"],
                cwd=str(HERE), env=env, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("refusing to start", proc.stderr)


class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import ThreadingHTTPServer
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), backend.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def get(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}") as r:
            return r.status, r.read()

    def test_pages_and_api(self):
        self.assertEqual(self.get("/")[0], 200)
        self.assertEqual(self.get("/api/health")[0], 200)
        probes = json.loads(self.get("/api/probes")[1])
        self.assertEqual(len(probes["probes"]), 120)
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/query", method="POST",
            data=json.dumps({"probe_id": 1, "top_k": 3}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            out = json.loads(r.read())
        self.assertEqual(len(out["guided"]["rows"]), 3)

    def test_http_error_cases(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/query", method="POST",
            data=json.dumps({"probe_id": 999}).encode(),
            headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/nope")
        self.assertEqual(cm.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
