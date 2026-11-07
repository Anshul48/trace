#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Focused test helper and standalone verification suite for TRACE review controls.

Rewritten for the CURRENT static-replay UI (docs/explorer/index.html and
docs/explorer/inside.html). The old topology/20k/recordings UI is gone, so every
selector below targets shipped elements, and every expected number is computed
from the shipped data files (data/replay.js, data/corpus.js) at run time.

Verifies:
1. Corpus-view 20k labels (stats cells, sealed strip, parent filter options).
2. Library-canvas zoom/pan/reset via the read-only camera hook + pixel change.
3. Scrolled screenshots: passage detail and library canvas.
4. Query-trace stepper: prev/next/play-pause and stage highlight.

DROPPED (no shipped equivalent): verify_recording_player — docs/recording/ is
absent from the repo, and no terminal player is shipped anywhere.
"""

import http.server
import json
import os
import socketserver
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLORER_DIR = ROOT / "docs" / "explorer"


def _default_shots_dir():
    env = os.environ.get("TRACE_SHOTS_DIR")
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p
    for base in ("/dev/shm", str(ROOT)):
        try:
            return Path(tempfile.mkdtemp(prefix="trace-suite-shots-", dir=base))
        except Exception:
            continue
    p = ROOT / "trace-suite-shots"
    p.mkdir(parents=True, exist_ok=True)
    return p


SHOTS_DIR = _default_shots_dir()

from playwright.sync_api import sync_playwright


class MultiDirHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "docs"), **kwargs)

    def log_message(self, format, *args):
        pass


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def start_server():
    server = ReusableTCPServer(("127.0.0.1", 0), MultiDirHTTPHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server, server.server_address[1]


def save_screenshot(page, name, full_page=False):
    p = str(SHOTS_DIR / name)
    page.screenshot(path=p, full_page=full_page)
    return p


def _load_js_object(path):
    text = Path(path).read_text(encoding="utf-8")
    obj, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    return obj


def load_shipped_data():
    """Parse the shipped replay/corpus data the pages themselves read."""
    replay = _load_js_object(EXPLORER_DIR / "data" / "replay.js")
    corpus = _load_js_object(EXPLORER_DIR / "data" / "corpus.js")
    return replay, corpus


def expected_trace_probes(corpus):
    """Replicate inside.js pickProbes: first eval row of each family/lso combo."""
    rows = corpus["evaluation_queries"]
    seen = set()
    out = []
    for i, e in enumerate(rows):
        k = (e["family"], e["leave_source_out"])
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out[:6]


def verify_corpus_labels(page, corpus, replay):
    """Stats cells, sealed strip and parent filter vs shipped corpus/replay data."""
    stats_text = page.locator("#corpus-stats").inner_text()
    fmt = lambda n: f"{n:,}"
    multi = sum(1 for leaf in corpus["leaves"] if len(leaf["parent_ids"]) > 1)
    checks = [
        (corpus["manifest"]["actual_tokens"], "tokens"),
        (len(corpus["atoms"]), "atoms = passages"),
        (len(corpus["leaves"]), "leaves = units"),
        (len(corpus["parents"]), "parents = groups"),
        (corpus["manifest"]["complete_documents"], "documents"),
        (corpus["manifest"]["parent_child_edges"], "parent\u2192leaf edges"),
        (multi, "multi-parent leaves"),
    ]
    for val, label in checks:
        assert fmt(val) in stats_text, f"{fmt(val)} missing from corpus stats"
        assert label in stats_text, f"{label!r} missing from corpus stats"

    assert page.locator("#cov-pass").inner_text() == fmt(len(replay["passages"])), \
        "sealed strip passage count mismatch"
    groups = {(p["sh"], p["pa"]) for p in replay["passages"].values()}
    assert page.locator("#cov-grp").inner_text() == fmt(len(groups)), \
        "sealed strip group count mismatch"

    assert page.locator("#cpar option").count() == len(corpus["parents"]) + 1, \
        "parent filter option count mismatch"


def verify_library_zoom(page):
    """Zoom-in shrinks the camera, pixels change, drag pans, reset restores."""
    cam0 = page.evaluate("window.__LIBRARY__.camera()")
    assert cam0["w"] > 0, "library camera not initialised"

    before = page.evaluate("document.getElementById('lmap').toDataURL()")
    page.locator("#lzin").click()
    cam1 = page.evaluate("window.__LIBRARY__.camera()")
    assert cam1["w"] < cam0["w"], f"zoom-in did not shrink camera ({cam0['w']} -> {cam1['w']})"
    assert abs(cam1["w"] / cam0["w"] - 0.7) < 0.05, \
        f"expected zoom factor 0.7, got {cam1['w'] / cam0['w']}"

    after = page.evaluate("document.getElementById('lmap').toDataURL()")
    assert before != after, "canvas pixels did not change after zoom-in"

    canvas = page.locator("#lmap")
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    assert box is not None, "lmap bounding box unavailable"
    sx, sy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(sx + 60, sy + 40, steps=5)
    page.mouse.up()
    cam2 = page.evaluate("window.__LIBRARY__.camera()")
    assert cam2["x"] != cam1["x"] or cam2["y"] != cam1["y"], \
        f"drag did not pan the camera: {cam2}"

    page.locator("#lzreset").click()
    cam3 = page.evaluate("window.__LIBRARY__.camera()")
    assert cam3["w"] == cam0["w"] and cam3["x"] == cam0["x"] and cam3["y"] == cam0["y"], \
        f"reset did not restore overview camera: {cam3} vs {cam0}"


def verify_trace_stepper(page):
    """Prev/next move the stage highlight; play toggles to pause and back."""
    page.wait_for_selector("#stages li")
    assert page.locator("#stages li").count() == 6, "expected 6 trace stages"
    first = page.locator("#stages li").nth(0)
    assert first.get_attribute("aria-current") == "true", "stage 1 not current initially"
    page.locator("#tnext").click()
    assert page.locator("#stages li").nth(1).get_attribute("aria-current") == "true", \
        "next did not advance the stage highlight"
    page.locator("#tprev").click()
    assert page.locator("#stages li").nth(0).get_attribute("aria-current") == "true", \
        "prev did not return the stage highlight"
    page.locator("#tplay").click()
    assert "Pause" in page.locator("#tplay").inner_text(), "play did not toggle to pause"
    page.locator("#tplay").click()
    assert "Play" in page.locator("#tplay").inner_text(), "second click did not stop play"


def capture_scrolled_detail_screenshot(page, save_screenshot_fn=save_screenshot):
    """Scrolls the corpus passage detail into view before capturing it."""
    detail = page.locator("#cdetail")
    detail.scroll_into_view_if_needed()
    time.sleep(0.2)
    save_screenshot_fn(page, "review-corpus-detail.png")


def capture_scrolled_library_screenshot(page, save_screenshot_fn=save_screenshot):
    """Scrolls the library canvas into view before capturing it."""
    canvas = page.locator("#lmap")
    canvas.scroll_into_view_if_needed()
    time.sleep(0.2)
    save_screenshot_fn(page, "review-library-canvas.png")


def run_focused_review_tests():
    server, port = start_server()
    inside_url = f"http://127.0.0.1:{port}/explorer/inside.html"
    print(f"Running focused TRACE review tests against {inside_url}...")
    print(f"Screenshots go to {SHOTS_DIR}")

    replay, corpus = load_shipped_data()
    passed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # 1. Corpus: 20k labels (stats, sealed strip, parent filter)
        print("\n--- Test: Corpus-View 20k Labels ---")
        page.goto(inside_url)
        page.wait_for_selector("#corpus-stats div")
        verify_corpus_labels(page, corpus, replay)
        print("  PASS: corpus stats, sealed strip and parent filter match shipped data")
        passed += 1

        # 2. Library: canvas zoom, pan, reset
        print("\n--- Test: Library Canvas Zoom & Pan ---")
        page.goto(inside_url + "#/library")
        page.wait_for_function(
            "window.__LIBRARY__ && window.__LIBRARY__.ready() "
            "&& window.__LIBRARY__.camera().w > 0"
        )
        verify_library_zoom(page)
        print("  PASS: library camera zoom, drag pan and reset verified")
        passed += 1

        # 3. Fresh scrolled screenshots (passage detail + library canvas)
        print("\n--- Test: Fresh Scrolled Screenshots (Detail & Library) ---")
        page.goto(inside_url)
        page.wait_for_selector("#plist li")
        atom_id = corpus["atoms"][0]["id"]
        page.locator("#cq").fill(atom_id)
        page.locator("#plist li").first.click()
        assert atom_id in page.locator("#cdetail").inner_text()
        capture_scrolled_detail_screenshot(page, save_screenshot)
        print("  PASS: review-corpus-detail.png captured with detail scrolled into view")
        passed += 1

        page.goto(inside_url + "#/library")
        page.wait_for_function(
            "window.__LIBRARY__ && window.__LIBRARY__.ready() "
            "&& window.__LIBRARY__.camera().w > 0"
        )
        capture_scrolled_library_screenshot(page, save_screenshot)
        print("  PASS: review-library-canvas.png captured with canvas scrolled into view")
        passed += 1

        # 4. Trace: stepper controls
        print("\n--- Test: Query-Trace Stepper Controls ---")
        page.goto(inside_url + "#/trace")
        page.wait_for_selector("#stages li")
        verify_trace_stepper(page)
        print("  PASS: trace prev/next/play-pause and stage highlight verified")
        passed += 1

        browser.close()

    server.shutdown()
    print(f"\n========================================================")
    print(f"FOCUSED REVIEW TESTS PASSED: {passed} test blocks verified.")
    print(f"Screenshots saved to {SHOTS_DIR}:")
    for f in sorted(SHOTS_DIR.glob("*.png")):
        print(f"  - {f.name} ({f.stat().st_size} bytes)")
    print(f"========================================================")


if __name__ == "__main__":
    run_focused_review_tests()
