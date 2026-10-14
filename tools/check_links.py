# SPDX-License-Identifier: Apache-2.0
"""Check relative Markdown links in the maintained docs resolve to files.

Skips the frozen snapshot, the byte-exact archive (historical links are
preserved as-is), and demo-app (integrated separately; links to its README
are allowed to be pending — reported as warnings, not failures).

Run from the repo root:  python3 tools/check_links.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = ["README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md"]
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

for msg in warnings:
    print("PENDING (demo integration):", msg)
if failures:
    print("BROKEN LINKS")
    for msg in failures:
        print(" -", msg)
    sys.exit(1)
print(f"links ok ({len(warnings)} pending demo-app link(s))")
