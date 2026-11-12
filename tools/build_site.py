#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the static site in docs/ from the page sources in docs/source/.

Why a build step at all: every page shares one header, footer and scale ladder,
and every status badge must say exactly what docs/status.json says. Writing
those by hand nine times invites drift. The output is plain HTML that is
committed, so GitHub Pages needs no build and visitors need no JavaScript to
read it.

  python3 tools/build_site.py           write docs/**/index.html and docs/badges/*.svg
  python3 tools/build_site.py --check   exit 1 if docs/ differs from what the sources produce

Standard library only. Sources:
  docs/source/pages/<route>.html     first line: <!--page {"title": "...", "desc": "...", "nav": "try"} -->
  docs/source/partials/<name>.html   included with {{include:name}}
  docs/status.json                badges: {{badge:id}} and {{label:id}}
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs/source")
OUT = os.path.join(ROOT, "docs")
SITE = "https://anshul48.github.io/trace/"

NAV = [
    ("try", "try/", "Try it"),
    ("how", "how-it-works/", "How it works"),
    ("evidence", "evidence/", "Evidence & limits"),
    ("demos", "demos/", "Demos"),
    ("verify", "verify/", "Verify"),
    ("about", "about/", "About"),
]


def load_status():
    with open(os.path.join(OUT, "status.json"), encoding="utf-8") as fh:
        return json.load(fh)


def route_out(route):
    return os.path.join(OUT, "index.html") if route == "index" else os.path.join(OUT, route, "index.html")


def root_prefix(route):
    return "" if route == "index" else "../" * (route.count("/") + 1)


def badge_html(status, cap_id):
    cap = next((c for c in status["capabilities"] if c["id"] == cap_id), None)
    if cap is None:
        raise SystemExit("unknown badge id: " + cap_id)
    st = cap["status"]
    cls = {"built": "badge-built", "prototype": "badge-proto", "next": "badge-next"}[st]
    text = cap.get("badge_text") or status["labels"][st]
    return '<span class="badge %s" data-status-id="%s">%s</span>' % (cls, cap_id, html.escape(text))


STATUSLINE = [("explorer-replay", "Recorded replay"), ("browser-mode", "Browser mode"),
              ("public-service", "Public backend"), ("local-kit", "Local kit")]


def statusline_html(status):
    parts = ['<span class="sl-item"><b>%s</b> %s</span>' % (name, badge_html(status, cid)) for cid, name in STATUSLINE]
    return '<p class="statusline" aria-label="What you can try today">%s</p>' % " ".join(parts)


def statusline_md(status):
    out = []
    for cid, name in STATUSLINE:
        cap = next(c for c in status["capabilities"] if c["id"] == cid)
        out.append("**%s:** %s" % (name, (cap.get("badge_text") or status["labels"][cap["status"]]).lower()))
    return ". ".join(out) + "."


def status_table(status, root):
    rows = []
    order = {"built": 0, "prototype": 1, "next": 2}
    caps = sorted(status["capabilities"], key=lambda c: order[c["status"]])
    for cap in caps:
        note = html.escape(cap.get("evidence_note", ""))
        ev = cap.get("evidence")
        if ev:
            link = "https://github.com/Anshul48/trace/blob/main/" + ev
            note = (note + " " if note else "") + '<a href="%s"><code>%s</code></a>' % (link, html.escape(ev))
        rows.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (html.escape(cap["title"]), badge_html(status, cap["id"]), note))
    return ('<div class="table-wrap"><table>\n<thead><tr><th scope="col">Capability</th><th scope="col">Status</th>'
            '<th scope="col">Where to look</th></tr></thead>\n<tbody>\n' + "\n".join(rows) + '\n</tbody></table></div>')


def render(text, route, status, meta, depth=0):
    root = root_prefix(route)

    def inc(m):
        name = m.group(1)
        path = os.path.join(SRC, "partials", name + ".html")
        if not os.path.isfile(path):
            raise SystemExit("missing partial: " + name)
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        if depth > 5:
            raise SystemExit("partial nesting too deep")
        return render(body, route, status, meta, depth + 1)

    text = re.sub(r"\{\{include:([a-z0-9-]+)\}\}", inc, text)
    text = re.sub(r"\{\{badge:([a-z0-9-]+)\}\}", lambda m: badge_html(status, m.group(1)), text)
    text = re.sub(r"\{\{label:([a-z0-9-]+)\}\}", lambda m: status["labels"][
        next(c for c in status["capabilities"] if c["id"] == m.group(1))["status"]], text)
    text = text.replace("{{statustable}}", status_table(status, root)) if "{{statustable}}" in text else text
    text = text.replace("{{statusline}}", statusline_html(status))
    text = text.replace("{{root}}", root)
    text = text.replace("{{updated}}", status["updated"])
    if "{{nav}}" in text:
        links = []
        for key, href, label in NAV:
            cur = ' aria-current="page"' if meta.get("nav") == key else ""
            links.append('<a href="%s%s"%s>%s</a>' % (root, href, cur, html.escape(label)))
        text = text.replace("{{nav}}", "\n        ".join(links))
    return text


def build_page(route, status):
    path = os.path.join(SRC, "pages", route + ".html")
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    m = re.match(r"<!--page (\{.*?\}) -->\n", raw, re.S)
    if not m:
        raise SystemExit(path + ": first line must be <!--page {...} -->")
    meta = json.loads(m.group(1))
    body = raw[m.end():]
    root = root_prefix(route)
    url = SITE + ("" if route == "index" else route + "/")
    title = meta["title"]
    full_title = title if route == "index" else title + " | TRACE"
    desc = html.escape(meta["desc"], quote=True)
    css = "".join('<link rel="stylesheet" href="%s">\n' % c for c in meta.get("css", []))
    page_scripts = "".join('<script src="%s" defer></script>\n' % s for s in meta.get("scripts", []))
    og_img = SITE + "img/social-preview.png"
    head = f"""<!doctype html>
<html lang="en" data-project="trace">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:title" content="{html.escape(full_title, quote=True)}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{og_img}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#f4f6fb">
<link rel="icon" type="image/svg+xml" href="{root}assets/favicon.svg">
<script>(function(){{try{{var t=localStorage.getItem("trace-theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}}catch(e){{}}document.documentElement.classList.add("js")}})();</script>
<link rel="stylesheet" href="{root}assets/tokens.css">
<link rel="stylesheet" href="{root}assets/base.css">
{css}</head>
<body>
<a class="skip" href="#main">Skip to the content</a>
{{{{include:header}}}}
<main id="main">
"""
    foot = f"""
</main>
{{{{include:footer}}}}
<script src="{root}assets/site.js" defer></script>
{page_scripts}</body>
</html>
"""
    page = head + body.rstrip("\n") + "\n" + foot
    return render(page, route, status, meta)


def badges_svg(status):
    colors = {"built": ("#17713f", "#dff3e7"), "prototype": ("#8a5a00", "#fdf0cf"), "next": ("#5546c9", "#e9e6ff")}
    out = {}
    for cap in status["capabilities"]:
        st = cap["status"]
        fg, bg = colors[st]
        label = cap.get("badge_text") or status["labels"][st]
        w = 18 + 7 * len(label)
        title = html.escape(cap["title"] + ": " + label)
        out[cap["id"]] = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="24" viewBox="0 0 %d 24" role="img" aria-label="%s">'
            '<title>%s</title><rect width="%d" height="24" rx="12" fill="%s"/>'
            '<circle cx="12" cy="12" r="4" fill="%s"/>'
            '<text x="22" y="16" font-family="system-ui,Segoe UI,Arial,sans-serif" font-size="11" font-weight="700" fill="%s">%s</text></svg>\n'
            % (w, w, title, title, w, bg, fg, fg, html.escape(label))
        )
    return out


def badge_md(status, cap_id):
    cap = next((c for c in status["capabilities"] if c["id"] == cap_id), None)
    if cap is None:
        raise SystemExit("unknown badge id: " + cap_id)
    text = cap.get("badge_text") or status["labels"][cap["status"]]
    return "![%s](docs/badges/%s.svg)" % (text, cap_id)


def film_md():
    path = os.path.join(OUT, "demos", "films.json")
    with open(path, encoding="utf-8") as fh:
        films = json.load(fh)["films"]
    main = next((f for f in films if f.get("role") == "main"), None)
    if main and main.get("youtube"):
        return "[Demo videos](https://www.youtube.com/watch?v=%s)" % main["youtube"]
    return "[Demo videos](https://anshul48.github.io/trace/demos/)"


def render_md(text, status):
    text = re.sub(r"\{\{badge:([a-z0-9-]+)\}\}", lambda m: badge_md(status, m.group(1)), text)
    text = text.replace("{{film}}", film_md())
    text = text.replace("{{statusline}}", statusline_md(status))
    text = text.replace("{{updated}}", status["updated"])
    if "{{statusmd}}" in text:
        order = {"built": 0, "prototype": 1, "next": 2}
        rows = ["| Capability | Status |", "|---|---|"]
        for cap in sorted(status["capabilities"], key=lambda c: order[c["status"]]):
            rows.append("| %s | %s |" % (cap["title"], badge_md(status, cap["id"])))
        text = text.replace("{{statusmd}}", "\n".join(rows))
    return text


def desired_files():
    status = load_status()
    files = {}
    routes = []
    for base, _dirs, names in os.walk(os.path.join(SRC, "pages")):
        for n in names:
            if n.endswith(".html"):
                rel = os.path.relpath(os.path.join(base, n), os.path.join(SRC, "pages"))[:-5]
                routes.append(rel.replace(os.sep, "/"))
    for route in sorted(routes):
        files[route_out(route)] = build_page(route, status)
    with open(os.path.join(SRC, "README.src.md"), encoding="utf-8") as fh:
        files[os.path.join(ROOT, "README.md")] = render_md(fh.read(), status)
    for cid, svg in badges_svg(status).items():
        files[os.path.join(OUT, "badges", cid + ".svg")] = svg
    return files


def main():
    check = "--check" in sys.argv
    files = desired_files()
    bad = []
    for path, text in files.items():
        cur = None
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                cur = fh.read()
        if cur != text:
            bad.append(os.path.relpath(path, ROOT))
            if not check:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
    if check:
        if bad:
            print("SITE OUT OF DATE (run: python3 tools/build_site.py):")
            for b in bad:
                print(" -", b)
            return 1
        print("site ok: %d generated files match docs/source and docs/status.json" % len(files))
        return 0
    print("wrote %d file(s); %d unchanged" % (len(bad), len(files) - len(bad)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
