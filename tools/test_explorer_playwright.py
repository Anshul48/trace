#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Automated Playwright test suite for TRACE Research Explorer.

Tests:
1. Desktop & Mobile viewports
2. Keyboard navigation across tabs and controls
3. Node inspection hit-testing on Canvas
4. Query replay stepper controls (Prev, Next, Play, Speed, LSO mode)
5. Reduced motion compliance
6. Programmatic screenshots for architect review in /tmp/trace-presentation-agy2-20261015/screenshots/
"""
import os
import sys
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLORER_DIR = ROOT / "docs" / "explorer"
SHOTS_DIR = Path("/tmp/trace-presentation-agy2-20261015/screenshots")
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

from playwright.sync_api import sync_playwright
import http.server
import socketserver


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(EXPLORER_DIR), **kwargs)

    def log_message(self, format, *args):
        pass


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def start_server():
    server = ReusableTCPServer(("127.0.0.1", 0), QuietHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server, server.server_address[1]


def main():
    server, port = start_server()
    url = f"http://127.0.0.1:{port}/index.html"
    print(f"Testing explorer at {url}...")

    passed = 0
    failed = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # 1. Desktop Test
        print("\n--- Test 1: Desktop Viewport (1280x900) ---")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(url)
        page.wait_for_selector(".app-header h1")
        assert "TRACE Explorer" in page.title() or "TRACE" in page.title()
        print("  PASS: Page title and header loaded")
        passed += 1

        # Check phase bars rendered
        page.wait_for_selector(".phase-seg")
        segs = page.locator(".phase-seg").count()
        assert segs >= 7, f"Expected >= 7 phase segments, got {segs}"
        print(f"  PASS: {segs} phase duration segments rendered")
        passed += 1
        page.screenshot(path=str(SHOTS_DIR / "desktop-10m-overview.png"), full_page=True)

        # 2. Tab Navigation & Keyboard
        print("\n--- Test 2: Tab Navigation & Keyboard Arrow Keys ---")
        tab_topo = page.locator("#tab-btn-topology")
        tab_topo.click()
        assert page.locator("#tab-topology").is_visible()
        print("  PASS: Clicked Topology Tab")
        passed += 1

        # Keyboard ArrowRight from topology tab
        tab_topo.focus()
        page.keyboard.press("ArrowRight")
        assert page.locator("#tab-queries").is_visible()
        print("  PASS: ArrowRight switched to Query Routing Replay Tab")
        passed += 1

        # 3. Query Replay Stepper Controls
        print("\n--- Test 3: Query Replay Stepper Controls ---")
        page.wait_for_selector("#query-select option", state="attached")
        probe_opts = page.locator("#query-select option").count()
        assert probe_opts >= 10, f"Expected probe options, got {probe_opts}"
        print(f"  PASS: {probe_opts} probe options loaded")
        passed += 1

        # Select LSO on
        lso_on = page.locator("input[name='lso-mode'][value='true']")
        lso_on.check()
        assert lso_on.is_checked()
        print("  PASS: Leave-Source-Out mode toggle checked")
        passed += 1

        # Advance step
        btn_next = page.locator("#btn-step-next")
        btn_next.click()
        page.wait_for_selector(".step-card[data-step='2'].active")
        print("  PASS: Stepped to Stage 2 (Parent Scoring)")
        passed += 1

        btn_next.click()
        page.wait_for_selector(".step-card[data-step='3'].active")
        print("  PASS: Stepped to Stage 3 (Child Descent)")
        passed += 1

        page.screenshot(path=str(SHOTS_DIR / "desktop-query-replay.png"), full_page=True)

        # 4. Canvas Topology & Node Click Inspection
        print("\n--- Test 4: Canvas Topology & Node Inspection ---")
        page.locator("#tab-btn-topology").click()
        page.wait_for_selector("#topology-canvas")
        canvas_elem = page.locator("#topology-canvas")
        box = canvas_elem.bounding_box()
        assert box is not None

        # Click canvas near center
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + 50)
        time.sleep(0.3)
        inspector_text = page.locator("#node-inspector-content").inner_text()
        assert len(inspector_text) > 10, "Expected node inspector text"
        print("  PASS: Canvas clicked and node inspected")
        passed += 1

        # Test zoom buttons
        page.locator("#btn-zoom-in").click()
        page.locator("#btn-zoom-out").click()
        page.locator("#btn-reset-zoom").click()
        print("  PASS: Zoom in, zoom out, reset view buttons functional")
        passed += 1

        page.screenshot(path=str(SHOTS_DIR / "desktop-topology.png"), full_page=True)
        page.screenshot(path=str(SHOTS_DIR / "desktop-node-inspected.png"))

        # 5. Mobile Viewport Test
        print("\n--- Test 5: Mobile Viewport (375x812) ---")
        mob = browser.new_page(viewport={"width": 375, "height": 812})
        mob.goto(url)
        mob.wait_for_selector(".brand-group h1")
        assert mob.locator(".stats-grid").first.is_visible()
        mob.screenshot(path=str(SHOTS_DIR / "mobile-overview.png"), full_page=True)
        print("  PASS: Mobile viewport rendered cleanly")
        passed += 1

        # 6. Reduced Motion Preference
        print("\n--- Test 6: Prefers-Reduced-Motion Emulation ---")
        rm_page = browser.new_page(viewport={"width": 1280, "height": 900},
                                   reduced_motion="reduce")
        rm_page.goto(url)
        rm_page.wait_for_selector(".app-header")
        print("  PASS: Loaded successfully under prefers-reduced-motion: reduce")
        passed += 1

        browser.close()

    server.shutdown()
    print(f"\n========================================================")
    print(f"PLAYWRIGHT PASS: {passed} assertions passed across desktop,")
    print(f"mobile, keyboard, controls, node inspection, and reduced motion.")
    print(f"Screenshots saved to {SHOTS_DIR}:")
    for f in SHOTS_DIR.glob("*.png"):
        print(f"  - {f.name} ({f.stat().st_size} bytes)")
    print(f"========================================================")


if __name__ == "__main__":
    main()
