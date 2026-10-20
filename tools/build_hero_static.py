#!/usr/bin/env python3
"""Render docs/assets/hero-static.svg: a static SVG snapshot of the real 20K graph.

Membership is real: atom -> primary (+secondary) parent indices come straight
from docs/assets/hero20k.json (built by tools/build_hero20k.py from the recorded
20K run: 51 parents, 144 atoms, 14 atoms in 8 multi-parent leaves).

Layout is illustrative and matches the canvas hero (docs/hero.js) exactly:
51 anchors on a deterministic circle, per-atom id-hash jitter (FNV-1a), then the
same settle loop the canvas runs for prefers-reduced-motion (1500 steps at full
pull). Colors: amber atoms warming toward teal, teal spokes/anchors, pink dashed
second edges -- same palette as the live canvas.

No text is drawn (the canvas never draws text either); numbers stay in HTML.

Usage:  python3 tools/build_hero_static.py
"""

import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "assets", "hero20k.json")
DST = os.path.join(ROOT, "docs", "assets", "hero-static.svg")

IW, IH = 880, 360


def hash32(s):
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def main():
    with open(SRC, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    parents = payload["parents"]
    atom_rows = payload["atoms"]
    assert len(parents) == 51, len(parents)
    assert len(atom_rows) == 144, len(atom_rows)

    anchors = []
    for i in range(len(parents)):
        angle = (i / len(parents)) * math.pi * 2
        anchors.append((IW / 2 + math.cos(angle) * 125,
                        IH / 2 + math.sin(angle) * 125))

    parts = []
    for row in atom_rows:
        cells = str(row).split(":")
        a = int(cells[1])
        b = int(cells[2]) if len(cells) > 2 else -1
        assert 0 <= a < len(anchors), row
        assert b == -1 or 0 <= b < len(anchors), row
        h1 = hash32(cells[0] + "p")
        h2 = hash32(cells[0] + "q")
        ja = (h1 % 360) / 360 * math.pi * 2
        jr = 10 + (h1 % 40)
        parts.append({
            "x": anchors[a][0] + math.cos(ja) * jr,
            "y": anchors[a][1] + math.sin(ja) * jr * 0.6,
            "vx": ((h2 % 200) - 100) / 100 * 11,
            "vy": (((h2 >> 8) % 200) - 100) / 100 * 11,
            "r": 1.5 + (h1 % 12) / 10,
            "a": a, "b": b,
            "ph": (h2 % 628) / 100,
        })

    # Same settle loop as hero.js reduced-motion path: pull = 1, dt = 1/60.
    dt, pull = 1 / 60, 1.0
    spring = pull * 0.55
    damp = max(0, 1 - 1.6 * dt)
    for s in range(1500):
        now_ms = s * 16.7
        for p in parts:
            c = anchors[p["a"]]
            p["vx"] += ((c[0] - p["x"]) * spring
                         + math.cos(now_ms / 1700 + p["ph"]) * 5) * dt
            p["vy"] += ((c[1] - p["y"]) * spring
                         + math.sin(now_ms / 2100 + p["ph"]) * 5) * dt
            if p["b"] >= 0:
                d = anchors[p["b"]]
                weak = pull * 0.14
                p["vx"] += (d[0] - p["x"]) * weak * dt
                p["vy"] += (d[1] - p["y"]) * weak * dt
            p["vx"] *= damp
            p["vy"] *= damp
            p["x"] = (p["x"] + p["vx"] * dt) % IW
            p["y"] = (p["y"] + p["vy"] * dt) % IH

    def fmt(v):
        return ("%.2f" % v).rstrip("0").rstrip(".")

    out = []
    A = out.append
    A('<?xml version="1.0" encoding="UTF-8"?>')
    A('<svg xmlns="http://www.w3.org/2000/svg" width="880" height="360" viewBox="0 0 880 360" role="img">')
    A('<title>Static snapshot of the recorded 20K run: 144 atoms gathered into their 51 real schema anchors</title>')
    A('<desc>Deterministic fallback for the canvas hero. Membership real (docs/assets/hero20k.json); layout illustrative '
      '(deterministic circle + id-hash jitter). Amber atoms, teal schema anchors, pink dashed second edges for multi-parent atoms.</desc>')
    A('<rect width="880" height="360" fill="#0b1220"/>')
    # Solid teal spokes: every atom to its REAL primary parent anchor.
    A('<g stroke="rgba(45,212,191,0.25)" stroke-width="1">')
    for p in parts:
        c = anchors[p["a"]]
        A('<line x1="%s" y1="%s" x2="%s" y2="%s"/>' % (
            fmt(p["x"]), fmt(p["y"]), fmt(c[0]), fmt(c[1])))
    A('</g>')
    # Dashed pink spokes: second edge for multi-parent atoms only.
    A('<g stroke="rgba(236,72,153,0.50)" stroke-width="1" stroke-dasharray="4 3">')
    n2 = 0
    for p in parts:
        if p["b"] < 0:
            continue
        c = anchors[p["b"]]
        A('<line x1="%s" y1="%s" x2="%s" y2="%s"/>' % (
            fmt(p["x"]), fmt(p["y"]), fmt(c[0]), fmt(c[1])))
        n2 += 1
    A('</g>')
    assert n2 == 14, n2
    # Teal schema anchors + halo rings.
    A('<g fill="#2dd4bf">')
    for c in anchors:
        A('<circle cx="%s" cy="%s" r="4"/>' % (fmt(c[0]), fmt(c[1])))
    A('</g>')
    A('<g fill="none" stroke="rgba(45,212,191,0.65)">')
    for i, c in enumerate(anchors):
        pulse = 4.5 + math.sin(i * 1.3) * 0.8
        A('<circle cx="%s" cy="%s" r="%s"/>' % (
            fmt(c[0]), fmt(c[1]), fmt(4 + pulse * 1.5)))
    A('</g>')
    # Amber particles, warming toward teal as they settle on anchors.
    A('<g>')
    for p in parts:
        c = anchors[p["a"]]
        dist = math.hypot(c[0] - p["x"], c[1] - p["y"])
        near = max(0, 1 - dist / 320)
        fill = "rgb(%d,%d,%d)" % (round(245 - 35 * near),
                                  round(165 + 20 * near),
                                  round(36 + 140 * near))
        A('<circle cx="%s" cy="%s" r="%s" fill="%s"/>' % (
            fmt(p["x"]), fmt(p["y"]), fmt(p["r"]), fill))
    A('</g>')
    A('</svg>')
    with open(DST, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("wrote %s (%d atoms, %d anchors, %d second edges)"
          % (DST, len(parts), len(anchors), n2))


if __name__ == "__main__":
    main()
