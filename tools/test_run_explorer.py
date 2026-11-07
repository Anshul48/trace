#!/usr/bin/env python3
"""Hermetic unittest for run_explorer.py (trace-oneliner-v1b, repo-carried).

Runs the tree's run_explorer.py only against localhost scratch state:
no network, no browser, no numpy. All paths derive from the tree root
(no hardcoded absolute paths). Run in the foreground from the tree root:

    python3 -W error::ResourceWarning -m unittest -v tools.test_run_explorer
    python3 -W error::ResourceWarning tools/test_run_explorer.py

Serve-log scratch defaults to a fresh tempdir; set TRACE_TEST_TMP to
redirect it (e.g. to a scratch dir) without editing the file.
"""

import ast
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "run_explorer.py")
WORKSPACE = os.environ.get("TRACE_TEST_TMP") or tempfile.mkdtemp(prefix="trace-oneliner-")

STDLIB_ALLOW = {
    "argparse", "errno", "http", "http.server", "os", "pathlib",
    "socketserver", "sys", "threading", "webbrowser",
}

EXPECTED_README_SECTION = [
    "## Run it in two commands",
    "",
    "```bash",
    "git clone --depth 1 https://github.com/Anshul48/trace && cd trace",
    "python3 run_explorer.py --dataset 20k",
    "```",
]


def load_module():
    spec = importlib.util.spec_from_file_location("run_explorer", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def fetch(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read()


class ServedServer:
    """A headless run_explorer.py subprocess on localhost; always cleaned up."""

    def __init__(self, test, port, python_args=()):
        self.test = test
        self.port = port
        self.python_args = tuple(python_args)
        self.proc = None
        self.log_file = None
        self.log_path = None

    def start(self):
        os.makedirs(WORKSPACE, exist_ok=True)
        handle, self.log_path = tempfile.mkstemp(
            prefix="oneliner-serve-", suffix=".log", dir=WORKSPACE
        )
        os.close(handle)
        self.log_file = open(self.log_path, "w", encoding="utf-8")
        cmd = (
            [sys.executable]
            + list(self.python_args)
            + [SCRIPT, "--dataset", "20k", "--no-browser", "--port", str(self.port)]
        )
        self.proc = subprocess.Popen(
            cmd, cwd=REPO_ROOT, stdout=self.log_file, stderr=subprocess.STDOUT
        )
        self.test.addCleanup(self.stop)
        base = "http://127.0.0.1:%d/explorer/" % self.port
        deadline = time.time() + 20
        last_error = None
        while time.time() < deadline:
            try:
                status, _ = fetch(base, timeout=3)
                if status == 200:
                    return base
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
            if self.proc.poll() is not None:
                break
            time.sleep(0.2)
        self.stop()
        raise AssertionError(
            "server on port %d never served 200 (last: %r)" % (self.port, last_error)
        )

    def stop(self):
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=10)
            else:
                self.proc.wait(timeout=10)
            self.proc = None
        if self.log_file is not None:
            self.log_file.close()
            self.log_file = None

    def log_text(self):
        with open(self.log_path, encoding="utf-8") as handle:
            return handle.read()


class TestRunExplorer(unittest.TestCase):
    def test_01_stdlib_imports_only(self):
        with open(SCRIPT, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
                imported.add(node.module)
        third_party = {name for name in imported if name not in STDLIB_ALLOW}
        self.assertEqual(third_party, set(), "non-stdlib imports: %r" % third_party)
        self.assertNotIn("numpy", imported)
        self.assertNotIn("blake3", imported)

    def test_02_python_floor_logic(self):
        module = load_module()
        self.assertTrue(module.python_ok((3, 8, 0)))
        self.assertTrue(module.python_ok((3, 12, 3)))
        self.assertFalse(module.python_ok((3, 7, 9)))
        self.assertFalse(module.python_ok((2, 7, 18)))

    def run_script(self, *args):
        proc = subprocess.run(
            [sys.executable, SCRIPT] + list(args),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc

    def test_03_download_10m_exit2(self):
        proc = self.run_script("--download", "10m")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no downloadable 10m-token local kit exists", proc.stderr)
        self.assertIn("planned", proc.stderr)

    def test_04_download_100m_exit2(self):
        proc = self.run_script("--download", "100m")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no downloadable 100m-token local kit exists", proc.stderr)
        self.assertIn("planned", proc.stderr)

    def test_05_download_bad_value_exit2(self):
        proc = self.run_script("--download", "1b")
        self.assertEqual(proc.returncode, 2)

    def test_06_bad_dataset_exit2(self):
        proc = self.run_script("--dataset", "10m")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("only --dataset 20k", proc.stderr)

    def test_07_bad_port_exit2(self):
        proc = self.run_script("--port", "99999")
        self.assertEqual(proc.returncode, 2)

    def test_08_port_busy_clear_error(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            holder.bind(("127.0.0.1", 0))
            holder.listen(1)
            busy = holder.getsockname()[1]
            proc = self.run_script(
                "--dataset", "20k", "--no-browser", "--port", str(busy)
            )
        finally:
            holder.close()
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("busy", combined)
        self.assertIn("--port", combined)

    def test_09_serve_headless_fetch(self):
        server = ServedServer(self, free_port())
        base = server.start()
        status, page = fetch(base)
        self.assertEqual(status, 200)
        self.assertIn(b"<title>Explorer | TRACE</title>", page)
        status, inside = fetch(base + "inside.html")
        self.assertEqual(status, 200)
        self.assertIn(b"Inside TRACE", inside)
        status, replay = fetch(base + "data/replay.js")
        self.assertEqual(status, 200)
        self.assertIn(b"TRACE_REPLAY", replay)
        status, corpus = fetch(base + "data/corpus.js")
        self.assertEqual(status, 200)
        self.assertIn(b"TRACE_CORPUS", corpus)
        status, raw = fetch(base + "local_20k_data.json")
        self.assertEqual(status, 200)
        data = json.loads(raw.decode("utf-8"))
        self.assertEqual(data["manifest"]["status"], "PASS")
        self.assertEqual(data["manifest"]["atoms_count"], 144)
        log = server.log_text()
        self.assertIn("Explorer (replay):", log)
        self.assertIn("inside.html", log)

    def test_10_serve_without_site_packages(self):
        # python3 -S disables site-packages: proves no numpy/pip dep needed.
        server = ServedServer(self, free_port(), python_args=("-S",))
        base = server.start()
        status, page = fetch(base)
        self.assertEqual(status, 200)
        self.assertIn(b"<title>Explorer | TRACE</title>", page)

    def test_11_readme_section_exact(self):
        for path in (
            os.path.join(REPO_ROOT, "README.md"),
            os.path.join(REPO_ROOT, "docs", "source", "README.src.md"),
        ):
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().split("\n")
            idx = lines.index("## Run it in two commands")
            section = lines[idx : idx + 6]
            self.assertEqual(section, EXPECTED_README_SECTION, path)

    def test_12_build_site_check_clean(self):
        proc = subprocess.run(
            [sys.executable, "tools/build_site.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
