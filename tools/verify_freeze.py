# SPDX-License-Identifier: Apache-2.0
"""Verify frozen stack-fork bytes against the SOURCEFREEZE manifest (read-only).

Run from the repo root:  python3 tools/verify_freeze.py
Expects:  entries=207 ok=207 missing=0 mismatch=0
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAND = os.path.join(ROOT, "freeze-src", "cand")

manifest = json.load(open(os.path.join(CAND, "SOURCEFREEZE.json")))
files = manifest["files"]
ok, missing, mismatch = 0, [], []
for rel, want in files.items():
    p = os.path.join(CAND, rel)
    if not os.path.isfile(p):
        missing.append(rel)
        continue
    got = hashlib.sha256(open(p, "rb").read()).hexdigest()
    if got != want:
        mismatch.append((rel, want[:12], got[:12]))
    else:
        ok += 1
print(f"entries={len(files)} ok={ok} missing={len(missing)} mismatch={len(mismatch)}")
for r in missing[:10]:
    print("MISSING", r)
for r, w, g in mismatch[:10]:
    print("MISMATCH", r, w, g)
sys.exit(1 if (missing or mismatch) else 0)
