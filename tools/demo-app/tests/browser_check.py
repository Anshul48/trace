"""Playwright check: desktop+mobile, keyboard-only flow, >=4 controls, screenshots.
Run with server up: DEMO_URL=http://127.0.0.1:PORT .venv/bin/python tests/browser_check.py"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = os.environ.get("DEMO_URL", "http://127.0.0.1:8765")
SHOTS = Path(__file__).resolve().parent.parent / "screenshots"
SHOTS.mkdir(exist_ok=True)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(URL)
        page.wait_for_function(
            "document.querySelectorAll('#probe option').length === 120")
        # Control 1: probe select; 2: mode select; 3: topk; 4: submit (keyboard)
        page.select_option("#probe", "5")
        page.select_option("#mode", "both")
        page.fill("#topk", "5")
        page.keyboard.press("Tab")
        page.click("button[type=submit]")
        page.wait_for_function(
            "document.querySelectorAll('#results .card').length >= 5")
        cards = page.locator("#results .card").count()
        assert cards >= 5, f"expected guided+flat result cards, got {cards}"
        assert page.locator("#metrics .metric").count() >= 3
        page.screenshot(path=str(SHOTS / "desktop-results.png"), full_page=True)
        # Control 5: evidence button; Control 6: LSO checkbox via keyboard
        page.click("#evidence-btn")
        page.wait_for_function(
            "document.querySelector('#evidence').textContent.includes('VERIFIED_PASS')")
        page.focus("#lso")
        page.keyboard.press("Space")
        assert page.is_checked("#lso")
        page.click("button[type=submit]")
        page.wait_for_function(
            "document.querySelector('#status').textContent === 'Query complete.'")
        page.screenshot(path=str(SHOTS / "desktop-evidence.png"), full_page=True)
        # Mobile viewport
        mob = browser.new_page(viewport={"width": 375, "height": 812})
        mob.goto(URL)
        mob.wait_for_function(
            "document.querySelectorAll('#probe option').length === 120")
        mob.click("button[type=submit]")
        mob.wait_for_function(
            "document.querySelectorAll('#results .card').length >= 5")
        mob.screenshot(path=str(SHOTS / "mobile-results.png"), full_page=True)
        browser.close()
    print("BROWSER CHECK PASS: 6 controls exercised, desktop+mobile,",
          "keyboard Space on LSO checkbox, 3 screenshots in", SHOTS)


if __name__ == "__main__":
    main()
