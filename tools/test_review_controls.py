#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Focused test helper and standalone verification suite for TRACE review controls.

Verifies:
1. Cluster selector subset labels (10M: 64 of 3,711 real parents; 20k: actual rendered count).
2. Canvas zoom/pan transform instrumentation (ctx.scale, ctx.translate, pixel change, reset baseline).
3. Scrolled screenshots: node inspector and canvas scrolled into view before capture.
4. Terminal recording player: 41-event cast loaded, controls effect, seek 100 PASS marker, and end screenshot.
"""

import http.server
import os
import socketserver
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLORER_DIR = ROOT / "docs" / "explorer"
RECORDING_DIR = ROOT / "docs" / "recording"
SHOTS_DIR = Path(os.environ.get("TRACE_SHOTS_DIR", "/tmp/trace-presentation-agy2-20261015/screenshots"))
try:
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    SHOTS_DIR = ROOT / "screenshots-final"
FINAL_SHOTS_DIR = ROOT / "screenshots-final"
FINAL_SHOTS_DIR.mkdir(parents=True, exist_ok=True)

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
    p2 = str(FINAL_SHOTS_DIR / name)
    page.screenshot(path=p2, full_page=full_page)
    try:
        p1 = str(SHOTS_DIR / name)
        if Path(p1).resolve() != Path(p2).resolve():
            page.screenshot(path=p1, full_page=full_page)
    except Exception:
        pass
    return p2


def verify_subset_labels(page):
    """Verifies cluster selector overview option labels for 10M and 20k datasets."""
    dataset_select = page.locator("#topology-dataset-select")

    # 1. Check 10M dataset
    dataset_select.select_option("10m")
    time.sleep(0.3)
    opt_10m = page.locator("#cluster-focus-select option[value='overview']").inner_text()
    assert "Overview: 64 of 3,711 Real Parents (Structural Preview)" in opt_10m, (
        f"Unexpected 10M label: {opt_10m}"
    )

    # 2. Check 20k dataset
    dataset_select.select_option("20k")
    time.sleep(0.3)
    opt_20k = page.locator("#cluster-focus-select option[value='overview']").inner_text()
    assert "51 of 51 Real Parents" in opt_20k, f"Unexpected 20k label: {opt_20k}"

    # Verify searchable by ID
    search_input = page.locator("#node-search-input")
    search_input.fill("xseg-102662-s0")
    time.sleep(0.2)
    inspector_text = page.locator("#node-inspector-content").inner_text()
    assert "xseg-102662-s0" in inspector_text, f"20k leaf not found: {inspector_text}"

    # Switch back to 10M
    dataset_select.select_option("10m")
    time.sleep(0.3)
    search_input.fill("xpar-01f45e945309ff5cd92e-repair-parent-10428")
    time.sleep(0.2)
    inspector_10m = page.locator("#node-inspector-content").inner_text()
    assert "xpar-01f45e945309ff5cd92e-repair-parent-10428" in inspector_10m


def verify_canvas_zoom(page):
    """Instruments actual canvas 2D context to assert applied zoom and pan transforms."""
    # Instrument canvas context on the page
    page.evaluate("""() => {
        const canvas = document.getElementById('topology-canvas');
        if (!canvas) throw new Error('topology-canvas not found');
        const ctx = canvas.getContext('2d');
        window.__canvasTransformLog = [];
        window.__lastScale = null;
        window.__lastTranslate = null;

        const origScale = ctx.scale;
        ctx.scale = function(sx, sy) {
            window.__lastScale = { sx, sy };
            window.__canvasTransformLog.push({ type: 'scale', sx, sy });
            return origScale.apply(this, arguments);
        };

        const origTranslate = ctx.translate;
        ctx.translate = function(dx, dy) {
            window.__lastTranslate = { dx, dy };
            window.__canvasTransformLog.push({ type: 'translate', dx, dy });
            return origTranslate.apply(this, arguments);
        };
    }""")

    # Baseline draw verification via reset view
    page.locator("#btn-reset-zoom").click()
    time.sleep(0.15)
    baseline_scale = page.evaluate("window.__lastScale")
    baseline_translate = page.evaluate("window.__lastTranslate")
    assert baseline_scale is not None, "ctx.scale was not called during canvas draw"
    assert baseline_scale["sx"] == 1.0 and baseline_scale["sy"] == 1.0, (
        f"Expected baseline scale 1.0, got {baseline_scale}"
    )
    assert baseline_translate is not None, "ctx.translate was not called during canvas draw"
    assert baseline_translate["dx"] == 0 and baseline_translate["dy"] == 0, (
        f"Expected baseline translate (0, 0), got {baseline_translate}"
    )

    # Capture visual pixel hash before zoom
    data_url_before = page.evaluate("""() => {
        const canvas = document.getElementById('topology-canvas');
        return canvas.toDataURL();
    }""")

    # Click Zoom In
    page.locator("#btn-zoom-in").click()
    time.sleep(0.15)

    zoomed_scale = page.evaluate("window.__lastScale")
    assert zoomed_scale is not None, "ctx.scale not called after zoom-in"
    assert zoomed_scale["sx"] > 1.0 and zoomed_scale["sy"] > 1.0, (
        f"Expected zoom-in scale > 1.0, got {zoomed_scale}"
    )
    assert abs(zoomed_scale["sx"] - 1.25) < 0.01, (
        f"Expected zoom scale 1.25, got {zoomed_scale['sx']}"
    )

    # Prove visual change via pixel dataURL
    data_url_after = page.evaluate("""() => {
        const canvas = document.getElementById('topology-canvas');
        return canvas.toDataURL();
    }""")
    assert data_url_before != data_url_after, "Canvas pixels did not visually change after zoom-in"

    # Test Pan (drag canvas)
    canvas_elem = page.locator("#topology-canvas")
    canvas_elem.scroll_into_view_if_needed()
    box = canvas_elem.bounding_box()
    assert box is not None, "topology-canvas bounding box unavailable"
    start_x = box["x"] + box["width"] * 0.5
    start_y = box["y"] + box["height"] * 0.5
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x + 50, start_y + 40, steps=5)
    time.sleep(0.1)
    page.mouse.up()
    time.sleep(0.15)

    panned_translate = page.evaluate("window.__lastTranslate")
    assert panned_translate is not None, "ctx.translate not called during pan drag"
    assert panned_translate["dx"] != 0 or panned_translate["dy"] != 0, (
        f"Expected non-zero pan translation, got {panned_translate}"
    )

    # Click Reset Zoom & restore baseline
    page.locator("#btn-reset-zoom").click()
    time.sleep(0.15)

    restored_scale = page.evaluate("window.__lastScale")
    restored_translate = page.evaluate("window.__lastTranslate")
    assert restored_scale["sx"] == 1.0 and restored_scale["sy"] == 1.0, (
        f"Reset did not restore baseline scale 1.0: {restored_scale}"
    )
    assert restored_translate["dx"] == 0 and restored_translate["dy"] == 0, (
        f"Reset did not restore baseline pan (0, 0): {restored_translate}"
    )


def capture_scrolled_node_inspector_screenshot(page, save_screenshot_fn=save_screenshot):
    """Scrolls node inspector into view before capturing desktop-node-inspected.png."""
    inspector = page.locator("#node-inspector-panel")
    inspector.scroll_into_view_if_needed()
    time.sleep(0.2)
    save_screenshot_fn(page, "desktop-node-inspected.png")


def capture_scrolled_dag_screenshot(page, save_screenshot_fn=save_screenshot):
    """Scrolls DAG canvas into view before capturing desktop-dag-topology.png."""
    canvas = page.locator("#topology-canvas")
    canvas.scroll_into_view_if_needed()
    time.sleep(0.2)
    save_screenshot_fn(page, "desktop-dag-topology.png")


def verify_recording_player(page, save_screenshot_fn=save_screenshot):
    """Verifies terminal player controls, 41-event cast timestamps, end PASS output, and scrubbing."""
    # 1. Wait until actual cast loaded (not "Loading")
    page.wait_for_selector("#terminal-output")
    page.wait_for_function("""() => {
        const el = document.getElementById('terminal-output');
        return el && !el.textContent.includes('Loading') && el.textContent.length > 50;
    }""", timeout=10000)

    # 2. Verify asciicast SHA-256 hash displayed in page
    hash_text = page.locator(".hash-row code").inner_text()
    expected_sha = "7ef2cca320a25690756528524095d9f350bb0187a16a3060d5ec58b1eb5b3d58"
    assert expected_sha in hash_text, f"Expected cast SHA {expected_sha}, got {hash_text}"

    # 3. Seek to 100 via slider input
    page.evaluate("""() => {
        const slider = document.getElementById('progress-slider');
        slider.value = '100';
        slider.dispatchEvent(new Event('input', { bubbles: true }));
    }""")
    time.sleep(0.2)

    # Verify slider and time reached ~27.8s
    slider_val = float(page.locator("#progress-slider").input_value())
    assert slider_val == 100.0, f"Expected slider value 100, got {slider_val}"
    time_display = page.locator("#time-display").inner_text()
    assert "27.8" in time_display, f"Expected time display to reach 27.8s, got {time_display}"

    # Verify actual end output and unique final PASS marker from source cast
    end_text = page.locator("#terminal-output").inner_text()
    unique_marker = "Installation and 20k pilot run verified successfully!"
    assert unique_marker in end_text, f"Unique final PASS marker not found in terminal output: {end_text[-300:]}"
    assert "Pilot execution completed with verdict: PASS" in end_text
    assert '"status": "PASS"' in end_text
    assert "xpar-sample" not in end_text

    # 4. Capture actual recording end PASS screenshot
    if save_screenshot_fn:
        save_screenshot_fn(page, "recording-player.png")

    # 5. Seek 0 / restart removes end marker
    restart_btn = page.locator("#btn-restart")
    restart_btn.click()
    time.sleep(0.2)
    play_btn = page.locator("#btn-play")
    if play_btn.inner_text().strip().lower() == "pause":
        play_btn.click()
        time.sleep(0.1)

    page.evaluate("""() => {
        const slider = document.getElementById('progress-slider');
        slider.value = '0';
        slider.dispatchEvent(new Event('input', { bubbles: true }));
    }""")
    time.sleep(0.1)

    start_text = page.locator("#terminal-output").inner_text()
    assert unique_marker not in start_text, "Final PASS marker unexpectedly present at time 0"
    start_time = page.locator("#time-display").inner_text()
    assert "00:00.0" in start_time, f"Expected time 00:00.0 at beginning, got {start_time}"

    # 6. Speed select 2.0
    speed_sel = page.locator("#speed-select")
    speed_sel.select_option("2.0")
    assert speed_sel.input_value() == "2.0", f"Expected speed 2.0, got {speed_sel.input_value()}"

    # 7. Play advances time
    play_btn.click()
    time.sleep(0.5)
    advanced_time = page.evaluate("document.getElementById('progress-slider').value")
    advanced_time_val = float(advanced_time)
    assert advanced_time_val > 0.0, f"Expected playback to advance progress slider, got {advanced_time_val}"

    # 8. Pause holds time
    play_btn.click()  # Pause
    time.sleep(0.1)
    paused_val = float(page.evaluate("document.getElementById('progress-slider').value"))
    time.sleep(0.3)
    held_val = float(page.evaluate("document.getElementById('progress-slider').value"))
    assert paused_val == held_val, f"Pause did not hold time: was {paused_val}, became {held_val}"


def run_focused_review_tests():
    server, port = start_server()
    explorer_url = f"http://127.0.0.1:{port}/explorer/index.html"
    recording_url = f"http://127.0.0.1:{port}/recording/index.html"
    print(f"Running focused TRACE review tests against {explorer_url} and {recording_url}...")

    passed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # 1. Explorer: Subset labels verification (10M and 20k)
        print("\n--- Test: Cluster Selector Subset Labels (10M / 20k) ---")
        page.goto(explorer_url)
        page.wait_for_selector("#tab-btn-topology")
        page.locator("#tab-btn-topology").click()
        page.wait_for_selector("#tab-topology.active")
        page.wait_for_selector("#topology-dataset-select")
        time.sleep(0.5)
        verify_subset_labels(page)
        print("  PASS: Cluster selector subset labels verified (10M 64/3711 structural preview & 20k rendered count)")
        passed += 1

        # 2. Explorer: Canvas Zoom, Pan, Reset & Transform Assertions
        print("\n--- Test: Canvas Zoom & Pan Transform Instrumentation ---")
        verify_canvas_zoom(page)
        print("  PASS: Canvas ctx.scale and ctx.translate transform assertions verified")
        passed += 1

        # 3. Explorer: Fresh Scrolled Screenshots (DAG & Inspected Node)
        print("\n--- Test: Fresh Scrolled Screenshots (DAG & Node Inspector) ---")
        search_input = page.locator("#node-search-input")
        search_input.fill("xseg-10039688-s0")
        time.sleep(0.3)
        capture_scrolled_node_inspector_screenshot(page, save_screenshot)
        print("  PASS: desktop-node-inspected.png captured with inspector scrolled into view")
        passed += 1

        capture_scrolled_dag_screenshot(page, save_screenshot)
        print("  PASS: desktop-dag-topology.png captured with canvas scrolled into view")
        passed += 1

        # 4. Recording: Terminal Recording Player & End PASS Screenshot
        print("\n--- Test: Terminal Recording Player & Controls ---")
        rec_page = browser.new_page(viewport={"width": 1280, "height": 900})
        rec_page.goto(recording_url)
        verify_recording_player(rec_page, save_screenshot)
        print("  PASS: Terminal player controls, timestamps, PASS end marker, and recording-player.png verified")
        passed += 1

        browser.close()

    server.shutdown()
    print(f"\n========================================================")
    print(f"FOCUSED REVIEW TESTS PASSED: {passed} test blocks verified.")
    print(f"Screenshots updated in {FINAL_SHOTS_DIR}:")
    for f in sorted(FINAL_SHOTS_DIR.glob("*.png")):
        print(f"  - {f.name} ({f.stat().st_size} bytes)")
    print(f"========================================================")


if __name__ == "__main__":
    run_focused_review_tests()
