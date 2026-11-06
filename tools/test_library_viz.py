#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unittest suite for the Inside-the-library cluster view (docs/explorer/).

Covers: tab renders with real counts; group labels are words from the real
member titles; lit passages equal the recorded guided top-10; the counter runs
to the recorded aggregate; clicking a lit passage shows its text and its
fingerprint check passes in the browser; zoom presets narrow the camera; plus
the screenshot set and the 20 s capture (record_tour.py style).

Run from the repo root, foreground:
  python3 -W error::ResourceWarning -m unittest discover -s tools -p "test_library_viz.py"
Needs: playwright + a chromium it can launch, ffmpeg with libx264.
Writes only to $TRACE_VIZ_OUT or <repo>/viz-artifacts (screenshots + mp4).
"""
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("TRACE_VIZ_OUT", str(ROOT / "viz-artifacts")))

from playwright.sync_api import sync_playwright  # noqa: E402


class DocsHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "docs"), **kwargs)

    def log_message(self, *args):
        pass


def load_replay():
    """Parse docs/explorer/data/replay.js with stdlib (window.X = {...};)."""
    src = (ROOT / "docs" / "explorer" / "data" / "replay.js").read_text(encoding="utf-8")
    start = src.index("{")
    end = src.rindex("}")
    return json.loads(src[start:end + 1])


class LibraryViz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUT.mkdir(parents=True, exist_ok=True)
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), DocsHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d/explorer/inside.html" % cls.server.server_address[1]
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()
        cls.replay = load_replay()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=10)

    def setUp(self):
        self.errors = []
        self.page = self.browser.new_page(viewport={"width": 1920, "height": 1080})
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.addCleanup(self.page.close)

    def goto_lib(self, query):
        self.page.goto(self.base + query, wait_until="load")
        self.page.wait_for_function("window.__LIBRARY__ && window.__LIBRARY__.ready()")
        self.page.wait_for_timeout(600)

    def test_01_renders_real_counts(self):
        self.goto_lib("?view=library&static=1")
        stats = self.page.evaluate("window.__LIBRARY__.stats()")
        self.assertEqual(stats["passages"], 1430)
        self.assertEqual(stats["groups"], 884)
        self.assertEqual(stats["shards"], 4)
        self.assertEqual(stats["questions"], 144)
        # independent recount from the shipped data file
        rp = self.replay["passages"]
        groups = {(p["sh"], p["pa"]) for p in rp.values()}
        self.assertEqual(len(rp), 1430)
        self.assertEqual(len(groups), 884)
        self.assertEqual(self.errors, [])

    def test_02_group_labels_come_from_real_titles(self):
        self.goto_lib("?view=library&static=1")
        rp = self.replay["passages"]
        titles = {}
        for pid, p in rp.items():
            titles.setdefault((p["sh"], p["pa"]), []).append(p.get("ti") or "")
        checked, empty = 0, 0
        for (sh, pa), ts in titles.items():
            term = self.page.evaluate("window.__LIBRARY__.groupLabel(%d, %d)" % (sh, pa))
            if not term:
                empty += 1
                continue
            words = set()
            for t in ts:
                words.update(re.findall(r"[a-z0-9][a-z0-9']{2,}", t.lower()))
            self.assertIn(term, words, "label %r not a word of group %d:%d titles" % (term, sh, pa))
            checked += 1
        self.assertGreater(checked, 800, "too few labelled groups: %d" % checked)
        self.assertLess(empty, 20, "too many unlabelled groups: %d" % empty)

    def test_03_lit_matches_recorded_top10_and_counter(self):
        self.goto_lib("?view=library&q=0&lit=1&static=1")
        lit = self.page.evaluate("window.__LIBRARY__.litIds()")
        guided = [str(h[0]) for h in self.replay["questions"][0]["g"]]
        self.assertEqual(sorted(lit), sorted(guided))
        self.assertEqual(len(lit), 10)
        counter = self.page.evaluate("window.__LIBRARY__.counter()")
        self.assertEqual(counter, {"scored": 1600, "total": 203137, "frac": "0.79%", "lit": 10})
        self.assertIn("0.79%", self.page.locator("#lcount").inner_text())
        self.assertIn("10 of 10", self.page.locator("#lpass").inner_text())
        self.assertEqual(self.errors, [])

    def test_04_click_lit_passage_checks_fingerprint(self):
        self.goto_lib("?view=library&q=0&lit=1&zoom=3&static=1")
        guided = [str(h[0]) for h in self.replay["questions"][0]["g"]]
        self.page.locator("#lmap").scroll_into_view_if_needed()
        pos = self.page.evaluate("window.__LIBRARY__.locate('%s')" % guided[0])
        self.assertIsNotNone(pos)
        self.page.mouse.click(pos["x"], pos["y"])
        panel = self.page.locator("#lpanel")
        want_title = self.replay["passages"][guided[0]]["ti"]
        self.assertIn(want_title, panel.inner_text())
        self.assertIn(self.replay["passages"][guided[0]]["h"], panel.inner_text())
        panel.locator("#lchk").click()
        panel.locator("#lverdict .verdict.pass").wait_for(timeout=8000)
        self.assertIn("Match", panel.locator("#lverdict").inner_text())
        self.assertEqual(self.errors, [])

    def test_05_zoom_presets_narrow(self):
        self.goto_lib("?view=library&q=0&static=1")
        widths = []
        for z in (0, 1, 2, 3):
            self.page.evaluate("window.__LIBRARY__.setZoom(%d)" % z)
            widths.append(self.page.evaluate("window.__LIBRARY__.camera()")["w"])
        self.assertTrue(widths[0] > widths[1] > widths[2] > widths[3], widths)

    def test_06_screenshots(self):
        shots = [
            ("shot-overview.png", "?view=library&static=1"),
            ("shot-zoom2.png", "?view=library&q=0&zoom=2&static=1"),
            ("shot-zoom3.png", "?view=library&q=0&zoom=3&static=1"),
            ("shot-query-lit.png", "?view=library&q=0&lit=1&static=1"),
        ]
        for name, query in shots:
            self.goto_lib(query)
            self.page.locator("#lmap").scroll_into_view_if_needed()
            self.page.wait_for_timeout(400)
            path = OUT / name
            self.page.locator("#lmap").screenshot(path=str(path))
            self.assertTrue(path.stat().st_size > 20000, "%s too small" % name)
        full = OUT / "shot-query-lit-full.png"
        self.page.screenshot(path=str(full), full_page=True)
        self.assertTrue(full.stat().st_size > 50000)
        self.assertEqual(self.errors, [])

    def test_07_capture_20s_mp4(self):
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg not installed")
        tmp = Path(tempfile.mkdtemp(prefix="trace-libviz-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        ctx = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(tmp),
            record_video_size={"width": 1920, "height": 1080},
        )
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.goto(self.base + "?view=library&q=0", wait_until="load")
        page.wait_for_function("window.__LIBRARY__ && window.__LIBRARY__.ready()")
        page.evaluate("window.scrollTo(0, document.querySelector('#lmap').getBoundingClientRect().top + window.scrollY - 150)")
        page.wait_for_timeout(500)
        page.locator("#lplay").click()  # follow-the-routing auto-zoom is on
        # the click auto-scrolls to the button; put the canvas back in frame
        page.evaluate("window.scrollTo(0, document.querySelector('#lmap').getBoundingClientRect().top + window.scrollY - 220)")
        page.wait_for_timeout(21000)
        page.close()
        ctx.close()
        webm = next(tmp.glob("*.webm"))
        out = OUT / "library-tour-20s.mp4"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-t", "20", "-an",
             "-vf", "scale=1920:1080,fps=30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-preset", "medium", "-crf", "23", "-movflags", "+faststart", str(out)],
            capture_output=True, text=True, timeout=240)
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        self.assertTrue(out.stat().st_size > 100000, "mp4 too small")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(out)], capture_output=True, text=True, timeout=60)
        if probe.returncode == 0:
            self.assertAlmostEqual(float(probe.stdout.strip()), 20.0, delta=0.6)


if __name__ == "__main__":
    unittest.main()
