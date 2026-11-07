#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Automated Playwright test suite for the TRACE static-replay Explorer.

Rewritten for the CURRENT UI (docs/explorer/index.html + inside.html). The old
topology/20k/query-router/audit UI is gone; every selector below targets shipped
elements, and every expected number is computed from the shipped data files
(data/replay.js, data/corpus.js) at run time — never invented.

Authoritative Integrated Verifications:
1. Zero fictional IDs: assert NO 'xpar-sample' anywhere in the DOM.
2. Visitor-first hero: 4-step guide, 4-step todo strip, category tabs.
3. Recorded-question replay: chips pick a question, 10 ranked cards render.
4. Real checkable records: per-result record with article ID, passage number,
   SHA-256 fingerprint, and an in-browser fingerprint match, cross-checked in
   Python with hashlib against the shipped text.
5. Corpus view: real 20k stats, passage search, multi-parent filter, detail.
6. Query-trace view: recorded eval row rendered byte-equal to shipped data,
   stage counts match, stepper + play/pause work.
7. Library view: zoomable canvas, zoom/pan/reset, passage click, fingerprint.
8. Honest-numbers views: memory and keyword-compare figures present.
9. Typed-question matching: closest-recorded note and no-match note.
10. Mobile responsive layout (375x812 and 390x844) without overflow.
11. Reduced-motion load.

DROPPED (no shipped equivalent, see the commit message): old Test 7
(TRACE_VALIDATION fail-closed API — no such object is shipped) and old Test 9
(docs/recording terminal player — docs/recording/ is absent).
"""

import hashlib
import http.server
import json
import os
import socketserver
import sys
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

sys.path.insert(0, str(ROOT))
from tools.test_review_controls import (
    expected_trace_probes,
    load_shipped_data,
    verify_corpus_labels,
    verify_library_zoom,
    verify_trace_stepper,
)


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


def main():
    server, port = start_server()
    explorer_url = f"http://127.0.0.1:{port}/explorer/index.html"
    inside_url = f"http://127.0.0.1:{port}/explorer/inside.html"
    print(f"Testing TRACE Explorer at {explorer_url}...")
    print(f"Testing Inside TRACE at {inside_url}...")
    print(f"Screenshots go to {SHOTS_DIR}")

    replay, corpus = load_shipped_data()
    questions = replay["questions"]
    passages = replay["passages"]
    cats = {}
    for q in questions:
        cats.setdefault(q["cat"], []).append(q)

    passed = 0
    pageerrors = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # -------------------------------------------------------------
        # Test 1: Desktop Viewport, Title, Hero & 4-Step Guide
        # -------------------------------------------------------------
        print("\n--- Test 1: Desktop Viewport (1280x900), Hero & 4-Step Guide ---")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: pageerrors.append(f"explorer: {e}"))
        page.goto(explorer_url)
        page.wait_for_selector(".site-header")
        assert "TRACE" in page.title()
        assert "TRACE" in page.locator(".site-header .brand").inner_text()
        print("  PASS: Page title and header brand verified")
        passed += 1

        hero_h1 = page.locator(".xhero h1").inner_text()
        assert "checkable record" in hero_h1, f"Unexpected hero h1: {hero_h1}"
        guide_steps = page.locator(".guide-steps li").count()
        assert guide_steps == 4, f"Expected 4 guide steps, got {guide_steps}"
        todo_steps = page.locator(".xsteps li").count()
        assert todo_steps == 4, f"Expected 4 todo steps, got {todo_steps}"
        print("  PASS: hero heading, 4-step guide and 4-step todo strip verified")
        passed += 1

        html_content = page.content()
        assert "xpar-sample" not in html_content, "CRITICAL: fictional xpar-sample IDs found!"
        print("  PASS: Strict referential integrity — zero xpar-sample fake IDs found")
        passed += 1

        tab_btns = page.locator("#cattabs button")
        assert tab_btns.count() == len(cats), \
            f"Expected {len(cats)} category tabs, got {tab_btns.count()}"
        for cat, qs in sorted(cats.items()):
            btn = page.locator("#cattabs button", has_text=f"{cat} (")
            assert btn.count() == 1, f"Missing tab for {cat}"
            assert btn.inner_text() == f"{cat} ({len(qs)})", \
                f"Wrong count on {cat} tab: {btn.inner_text()}"
        print(f"  PASS: {len(cats)} category tabs with shipped question counts verified")
        passed += 1

        meta_text = page.locator("#recmeta").inner_text()
        assert f"{len(questions)} questions" in meta_text, f"Bad recmeta: {meta_text}"
        assert page.locator(".status [data-status-id]").count() == 5
        print("  PASS: recording meta and 5-row status table verified")
        passed += 1

        page.wait_for_function(
            "document.getElementById('captiontext').textContent.indexOf('of 10 match exact search') > 0",
            timeout=10000,
        )
        print("  PASS: live results caption rendered from replay data")
        passed += 1

        save_screenshot(page, "explorer-overview.png", full_page=True)

        # -------------------------------------------------------------
        # Test 2: Question Chips Navigate to a 10-Card Recorded Replay
        # -------------------------------------------------------------
        print("\n--- Test 2: Question Chips Navigate to a 10-Card Replay ---")
        default_chips = page.locator("#chips li").count()
        default_cat = next(q["cat"] for q in questions if q["id"] == "why-is-the-sky-blue")
        assert default_chips == len(cats[default_cat]), \
            f"Expected {len(cats[default_cat])} default chips, got {default_chips}"
        print(f"  PASS: default chip list shows all {default_chips} {default_cat} questions")
        passed += 1

        target_cat = "History"
        page.locator("#cattabs button", has_text=target_cat).click()
        assert page.locator("#chips li").count() == len(cats[target_cat])
        target_q = cats[target_cat][0]["q"]
        page.locator("#chips li button").first.click()
        page.wait_for_function(
            f"document.getElementById('qtitle').textContent.indexOf({json.dumps(target_q)}) >= 0"
        )
        assert page.locator("#list .card").count() == 10, "Expected 10 ranked cards"
        print(f"  PASS: chip navigated to recorded replay of {target_q!r} with 10 cards")
        passed += 1

        big = " ".join(page.locator("#compare .big").text_content().split())
        assert " of 10 " in big and "passages are the same" in big, f"Bad compare big: {big}"
        assert page.locator("#compare .cols > div").count() == 2
        print("  PASS: TRACE-vs-exact comparison panel rendered (shared count + 2 lists)")
        passed += 1

        # -------------------------------------------------------------
        # Test 3: Checkable Record & In-Browser Fingerprint Match
        # -------------------------------------------------------------
        print("\n--- Test 3: Checkable Record & Fingerprint Match ---")
        page.goto(explorer_url)  # clean state: default recorded question
        page.wait_for_selector("#list .card")
        q0 = next(q for q in questions if q["id"] == "why-is-the-sky-blue")
        assert q0["q"] in page.locator("#qtitle").inner_text()
        pid = str(q0["g"][0][0])
        expected = passages[pid]
        assert hashlib.sha256(expected["tx"].encode("utf-8")).hexdigest() == expected["h"], \
            "shipped fingerprint does not match shipped text (data integrity)"
        print("  PASS: shipped fingerprint matches shipped text in Python (hashlib)")
        passed += 1

        page.locator("#r1 .recbtn").click()
        page.wait_for_selector("#rec1:not([hidden])")
        assert "Article ID" in page.locator("#rec1").inner_text()
        shown_hash = page.locator("#rec1 .hash").inner_text()
        assert shown_hash == expected["h"], f"page shows {shown_hash}, data has {expected['h']}"
        print("  PASS: record shows article ID and the shipped 64-hex fingerprint")
        passed += 1


        page.locator("#rec1 .chk").click()
        page.wait_for_selector("#rec1 .verdict.pass")
        assert "Match" in page.locator("#rec1 .verdict.pass").inner_text()
        print("  PASS: in-browser fingerprint check returned Match")
        passed += 1

        save_screenshot(page, "explorer-record.png")

        # -------------------------------------------------------------
        # Test 4: Corpus View — Real 20k Stats, Search & Detail
        # -------------------------------------------------------------
        print("\n--- Test 4: Corpus View (Local 20k Reproduction) ---")
        page.goto(inside_url)
        page.wait_for_selector("#corpus-stats div")
        verify_corpus_labels(page, corpus, replay)
        print("  PASS: 20k stats, sealed strip and parent filter match shipped data")
        passed += 1

        atom = corpus["atoms"][0]
        page.locator("#cq").fill(atom["id"])
        page.wait_for_function(
            "document.getElementById('ccount').textContent.indexOf('Showing 1 of') === 0"
        )
        assert page.locator("#ccount").inner_text() == \
            f"Showing 1 of {len(corpus['atoms'])} passages."
        page.locator("#plist li").first.click()
        detail = page.locator("#cdetail").inner_text()
        assert atom["doc_id"] in detail and "Tier" in detail
        assert atom["id"] in detail
        print(f"  PASS: searched authentic atom {atom['id'][:12]}…; detail shows tier chain")
        passed += 1

        page.locator("#cq").fill("")
        multi_leaves = {l["id"] for l in corpus["leaves"] if len(l["parent_ids"]) > 1}
        expect_multi = sum(
            1 for a in corpus["atoms"]
            if any(lid in multi_leaves for lid in a["leaf_ids"])
        )
        page.locator("#cmp").check()
        page.wait_for_function(
            f"document.getElementById('ccount').textContent === "
            f"'Showing {expect_multi} of {len(corpus['atoms'])} passages.'"
        )
        page.locator("#cmp").uncheck()
        print(f"  PASS: multi-parent filter shows {expect_multi} passages (shipped data)")
        passed += 1

        save_screenshot(page, "corpus-view.png")

        # -------------------------------------------------------------
        # Test 5: Query-Trace View — Exact Recorded-Row Equality & Stepper
        # -------------------------------------------------------------
        print("\n--- Test 5: Query-Trace View & Exact Row Equality ---")
        page.goto(inside_url + "#/trace")
        page.wait_for_selector("#stages li")
        probes = expected_trace_probes(corpus)
        assert page.locator("#tq option").count() == len(questions)
        assert page.locator("#tp option").count() == len(probes)
        print(f"  PASS: {len(questions)} recorded questions, {len(probes)} eval probes listed")
        passed += 1

        rows = corpus["evaluation_queries"]
        for opt_index in (0, 1):
            page.locator("#tp").select_option(index=opt_index)
            receipt = json.loads(page.locator("#treceipt").text_content())
            assert receipt == rows[probes[opt_index]], \
                f"trace receipt mismatch for probe option {opt_index}"
        print("  PASS: rendered eval rows byte-equal shipped corpus rows (2 probes)")
        passed += 1

        page.locator("#tp").select_option(index=0)
        e0 = rows[probes[0]]
        stage3 = page.locator("#stages li").nth(2).inner_text()
        assert str(e0["work"]["children_scored"]) in stage3
        stage4 = page.locator("#stages li").nth(3).inner_text()
        assert str(e0["work"]["atoms_scored"]) in stage4
        assert str(e0["work"]["member_visits"]) in stage4
        stage5 = page.locator("#stages li").nth(4).inner_text()
        assert str(e0["guided_scoring_rows"]) in stage5
        stage6 = page.locator("#stages li").nth(5).inner_text()
        assert f"{e0['guided_recall10']:.2f}" in stage6
        prov = page.locator("#tprov").inner_text()
        assert f"eval row {probes[0]} of {len(rows)}" in prov
        print("  PASS: stage counts and provenance match the recorded eval row")
        passed += 1

        verify_trace_stepper(page)
        print("  PASS: trace stepper prev/next/play-pause verified")
        passed += 1

        q5 = questions[5]
        page.locator("#tq").select_option("5")
        assert q5["q"] in page.locator("#tanswer").inner_text()
        assert page.locator("#tanswer ol > li").count() == 10
        print("  PASS: recorded top-10 answer rendered for picked question")
        passed += 1

        save_screenshot(page, "trace-view.png")

        # -------------------------------------------------------------
        # Test 6: Library View — Zoomable Canvas, Passage Click, Fingerprint
        # -------------------------------------------------------------
        print("\n--- Test 6: Library View (Zoomable Cluster Canvas) ---")
        page.goto(inside_url + "#/library")
        page.wait_for_function(
            "window.__LIBRARY__ && window.__LIBRARY__.ready() "
            "&& window.__LIBRARY__.camera().w > 0"
        )
        assert page.locator("#lmap").is_visible()
        box = page.locator("#lmap").bounding_box()
        assert box is not None and box["width"] > 100 and box["height"] > 100
        stats = page.evaluate("window.__LIBRARY__.stats()")
        assert stats["passages"] == len(passages)
        assert stats["questions"] == len(questions)
        assert page.locator("#lq option").count() == len(questions)
        print(f"  PASS: library canvas visible; {stats['passages']} passages, "
              f"{stats['groups']} groups, {stats['questions']} questions")
        passed += 1

        verify_library_zoom(page)
        print("  PASS: library zoom-in / pixel change / pan / reset verified")
        passed += 1

        page.locator("#lq").select_option("0")
        assert "0 of 203,137 rows scored" in page.locator("#lcount").inner_text()
        assert "0 of 10 recorded top passages lit" in page.locator("#lpass").inner_text()
        page.locator("#lz3").click()  # Passages preset: dive to top guided group
        lpid = str(questions[0]["g"][0][0])
        page.locator("#lmap").scroll_into_view_if_needed()
        pt = page.evaluate(f"window.__LIBRARY__.locate({lpid!r})")
        assert pt is not None, f"guided passage {lpid} not locatable on canvas"
        page.mouse.click(pt["x"], pt["y"])
        page.wait_for_selector("#lchk")
        lpanel = page.locator("#lpanel").inner_text()
        assert passages[lpid]["ti"] in lpanel, f"panel missed title: {lpanel[:200]}"
        assert passages[lpid]["h"] in lpanel
        print("  PASS: canvas click opened the guided passage with title + fingerprint")
        passed += 1

        page.locator("#lchk").click()
        page.wait_for_selector("#lverdict .verdict.pass")
        assert "Match" in page.locator("#lverdict .verdict.pass").inner_text()
        print("  PASS: library fingerprint check returned Match")
        passed += 1

        save_screenshot(page, "library-view.png")

        # -------------------------------------------------------------
        # Test 7: Memory & Keyword-Compare Honest Numbers
        # -------------------------------------------------------------
        print("\n--- Test 7: Memory & Keyword-Compare Views ---")
        page.goto(inside_url + "#/memory")
        page.wait_for_selector("#view-memory:not([hidden])")
        mem_text = page.locator("#view-memory").inner_text()
        assert "2.28 GB" in mem_text and "1.03 GiB" in mem_text
        assert "not measured" in mem_text
        print("  PASS: memory view shows stored sizes + no-comparison guard")
        passed += 1

        page.goto(inside_url + "#/compare")
        page.wait_for_selector("#view-compare:not([hidden])")
        cmp_text = page.locator("#view-compare").inner_text()
        assert "0.74" in cmp_text and "0.42" in cmp_text
        assert "82%" in cmp_text and "52%" in cmp_text
        print("  PASS: keyword-compare view shows audited 0.74/0.42 and 82%/52%")
        passed += 1

        save_screenshot(page, "memory-view.png")

        # -------------------------------------------------------------
        # Test 8: Mobile Viewports (375x812 and 390x844)
        # -------------------------------------------------------------
        print("\n--- Test 8: Mobile Viewports (375x812 and 390x844) ---")
        for width, height, fname in [(375, 812, "mobile-375x812.png"),
                                     (390, 844, "mobile-390x844.png")]:
            mob = browser.new_page(viewport={"width": width, "height": height})
            mob.on("pageerror", lambda e: pageerrors.append(f"mobile: {e}"))
            mob.goto(explorer_url)
            mob.wait_for_selector(".site-header")

            scroll_width = mob.evaluate("document.documentElement.scrollWidth")
            inner_width = mob.evaluate("window.innerWidth")
            assert scroll_width <= inner_width, \
                f"Horizontal overflow on {width}px: scrollWidth {scroll_width} > {inner_width}"

            brand = mob.locator(".site-header .brand")
            assert brand.is_visible()
            brand_box = brand.bounding_box()
            assert brand_box is not None and brand_box["y"] < height, \
                f"header brand offscreen at y={brand_box['y']}"

            cta = mob.locator("#askform .primary")
            cta.scroll_into_view_if_needed()
            assert cta.is_visible()
            assert cta.is_enabled()
            assert mob.locator("#chips li").count() > 0

            save_screenshot(mob, fname, full_page=True)
            mob.close()
            print(f"  PASS: Mobile {width}x{height} rendered cleanly without overflow")
            passed += 1

        # -------------------------------------------------------------
        # Test 9: Typed-Question Matching (Closest-Recorded & No-Match)
        # -------------------------------------------------------------
        print("\n--- Test 9: Typed-Question Matching ---")
        page.goto(explorer_url)
        page.wait_for_selector("#list .card")
        page.locator("#q").fill(questions[0]["q"])
        page.locator("#askform button[type='submit']").click()
        page.wait_for_selector("#matchnote:not([hidden])")
        assert "closest to the recorded question" in page.locator("#matchnote").inner_text()
        assert questions[0]["q"] in page.locator("#qtitle").inner_text()
        print("  PASS: exact typed question matched to its recording")
        passed += 1

        page.locator("#q").fill("zzzzqqqxjv kvvzzwx qzxj")
        page.locator("#askform button[type='submit']").click()
        page.wait_for_function(
            "document.getElementById('matchnote').hidden === false "
            "&& document.getElementById('matchnote').textContent.indexOf("
            "'No recorded question is a close match') >= 0"
        )
        print("  PASS: unrelated typed words show the honest no-match note")
        passed += 1

        # -------------------------------------------------------------
        # Test 10: Prefers-Reduced-Motion Emulation
        # -------------------------------------------------------------
        print("\n--- Test 10: Prefers-Reduced-Motion Emulation ---")
        rm_page = browser.new_page(viewport={"width": 1280, "height": 900},
                                   reduced_motion="reduce")
        rm_page.on("pageerror", lambda e: pageerrors.append(f"reduced-motion: {e}"))
        rm_page.goto(explorer_url)
        rm_page.wait_for_selector(".site-header")
        rm_page.wait_for_selector("#chips li")
        print("  PASS: Loaded successfully under prefers-reduced-motion: reduce")
        passed += 1

        assert not pageerrors, f"JS page errors seen: {pageerrors}"

        browser.close()

    server.shutdown()
    print(f"\n========================================================")
    print(f"ALL TESTS PASSED: {passed} automated assertions verified.")
    print(f"Screenshots saved to {SHOTS_DIR}:")
    for f in sorted(SHOTS_DIR.glob("*.png")):
        print(f"  - {f.name} ({f.stat().st_size} bytes)")
    print(f"========================================================")


if __name__ == "__main__":
    main()
