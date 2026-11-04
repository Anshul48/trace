# SPDX-License-Identifier: Apache-2.0
"""Check relative Markdown links in the maintained docs resolve to files.

Skips the frozen snapshot, the byte-exact archive (historical links are
preserved as-is), and tools/demo-app (integrated separately; links to its README
are allowed to be pending — reported as warnings, not failures).

It also checks docs/status.json (every capability marked "built" must name an
evidence path that exists in this repository) and docs/demos/films.json (every
named film, poster and caption file must exist).

Run from the repo root:  python3 tools/check_links.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = ["README.md", ".github/CONTRIBUTING.md", ".github/SECURITY.md"]
DOCS += [
    os.path.join("docs", f)
    for f in sorted(os.listdir(os.path.join(ROOT, "docs")))
    if f.endswith(".md")
]

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
failures, warnings = [], []
for rel in DOCS:
    path = os.path.join(ROOT, rel)
    if not os.path.isfile(path):
        continue
    base = os.path.dirname(path)
    for i, line in enumerate(open(path), 1):
        for target in LINK.findall(line):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            target_path = target.split("#", 1)[0]
            if not target_path:
                continue
            resolved = os.path.normpath(os.path.join(base, target_path))
            if os.path.exists(resolved):
                continue
            msg = f"{rel}:{i}: {target}"
            if "demo-app" in target_path:
                warnings.append(msg)
            else:
                failures.append(msg)

# ---- status.json: "built" needs evidence that exists ----
try:
    with open(os.path.join(ROOT, "docs", "status.json"), encoding="utf-8") as fh:
        status = json.load(fh)
    seen = set()
    n_built = 0
    for cap in status["capabilities"]:
        cid = cap["id"]
        if cid in seen:
            failures.append("docs/status.json: duplicate id " + cid)
        seen.add(cid)
        if cap["status"] not in status["labels"]:
            failures.append("docs/status.json: %s has unknown status %r" % (cid, cap["status"]))
        if cap["status"] == "built":
            n_built += 1
            ev = cap.get("evidence")
            if not ev or not os.path.exists(os.path.join(ROOT, ev)):
                failures.append("docs/status.json: %s is marked built but its evidence path is missing: %r" % (cid, ev))
except (OSError, ValueError, KeyError) as exc:
    failures.append("docs/status.json unreadable: %s" % exc)
    status, n_built = {"capabilities": []}, 0

# ---- films.json: named files exist ----
try:
    with open(os.path.join(ROOT, "docs", "demos", "films.json"), encoding="utf-8") as fh:
        films = json.load(fh)["films"]
    for f in films:
        for key in ("file", "poster", "captions"):
            if f.get(key) and not os.path.isfile(os.path.join(ROOT, "docs", "demos", f[key])):
                failures.append("docs/demos/films.json: %s %s missing: %s" % (f["id"], key, f[key]))
except (OSError, ValueError, KeyError) as exc:
    failures.append("docs/demos/films.json unreadable: %s" % exc)

for msg in warnings:
    print("PENDING (demo integration):", msg)
if failures:
    print("BROKEN LINKS")
    for msg in failures:
        print(" -", msg)
    sys.exit(1)
print(f"links ok ({len(warnings)} pending demo-app link(s)); "
      f"status ok ({len(status['capabilities'])} capabilities, {n_built} built with evidence present); films ok")
