#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Focused Playwright test: corpus-map node clicks on Inside TRACE.

Regression test for the dead node-click bug on the public Explorer corpus map
(docs/explorer/inside.html, svg#cmap): pointerdown called setPointerCapture on
the svg, which retargeted pointerup to the svg itself, so the pointerup handler
always read a null data-n and ran select(null). A real node click must select
the node and fill #mapnote, while drag-to-pan must keep working and must not
select, zoom buttons must keep working, and the passage-list keyboard path
(Enter/Space) must keep working.

Usage: python3 tools/test_inside_map_click.py
Requires: playwright + headless chromium (see tools/test_explorer_playwright.py).
"""

import http.server
import re
import socketserver
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from playwright.sync_api import sync_playwright


class DocsHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "docs"), **kwargs)

    def log_message(self, format, *args):
        pass


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def start_server():
    server = ReusableTCPServer(("127.0.0.1", 0), DocsHTTPHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server, server.server_address[1]


def main():
    server, port = start_server()
    url = f"http://127.0.0.1:{port}/explorer/inside.html"
    print(f"Testing Inside TRACE corpus map at {url}...")

    passed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(url)
        page.wait_for_selector("#cmap circle.node")
        assert page.locator("#view-corpus").is_visible(), "corpus view not visible"
        print("  PASS: corpus view with map nodes rendered")
        passed += 1

        # --- Test 1: parent node click fills the map note ---
        page.locator('#cmap circle.node[data-n^="p:"]').first.click()
        note = page.locator("#mapnote").inner_text()
        assert re.match(r"^parent xpar-\S+: \d+ child units, \d+ atoms\.$", note), \
            f"parent click did not fill map note, got: {note!r}"
        print(f"  PASS: parent node click fills map note: {note}")
        passed += 1

        # --- Test 2: leaf node click fills the map note ---
        page.locator('#cmap circle.node[data-n^="l:"]').first.click()
        note = page.locator("#mapnote").inner_text()
        assert re.match(r"^unit xseg-\S+: \d+ atoms; parents .+\.$", note), \
            f"leaf click did not fill map note, got: {note!r}"
        print(f"  PASS: leaf node click fills map note: {note}")
        passed += 1

        # --- Test 3: drag pans the map and does NOT select ---
        before_vb = page.locator("#cmap").get_attribute("viewBox")
        note_before = page.locator("#mapnote").inner_text()
        box = page.locator("#cmap").bounding_box()
        assert box is not None
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 150, cy + 80, steps=10)
        page.mouse.up()
        after_vb = page.locator("#cmap").get_attribute("viewBox")
        assert after_vb != before_vb, "drag did not pan (viewBox unchanged)"
        assert page.locator("#mapnote").inner_text() == note_before, \
            "drag changed the selection"
        print(f"  PASS: drag pans ({before_vb} -> {after_vb}) without selecting")
        passed += 1

        # --- Test 4: background click clears the selection ---
        page.locator("#cmap").click(position={"x": 5, "y": 5})
        assert page.locator("#mapnote").inner_text() == "", \
            f"background click did not clear note, got: {page.locator('#mapnote').inner_text()!r}"
        print("  PASS: background click clears the map note")
        passed += 1

        # --- Test 5: zoom buttons still work ---
        vb0 = page.locator("#cmap").get_attribute("viewBox")
        w0 = float(vb0.split()[2])
        page.locator("#zin").click()
        w1 = float(page.locator("#cmap").get_attribute("viewBox").split()[2])
        assert w1 < w0, f"zoom-in did not shrink viewBox width ({w0} -> {w1})"
        page.locator("#zreset").click()
        w2 = float(page.locator("#cmap").get_attribute("viewBox").split()[2])
        assert w2 == 760, f"reset did not restore width 760, got {w2}"
        print(f"  PASS: zoom in ({w0} -> {w1}) and reset (-> {w2}) work")
        passed += 1

        # --- Test 6: passage-list keyboard path still works ---
        first = page.locator("#plist li").first
        first.scroll_into_view_if_needed()
        first.focus()
        page.keyboard.press("Enter")
        detail = page.locator("#cdetail").inner_text()
        assert "Tier" in detail and first.get_attribute("aria-current") == "true", \
            f"keyboard Enter did not open passage detail, got: {detail[:120]!r}"
        print("  PASS: passage list keyboard (Enter) opens detail")
        passed += 1

        browser.close()
    server.shutdown()
    print(f"ALL TESTS PASSED: {passed} automated assertions verified.")


if __name__ == "__main__":
    main()
