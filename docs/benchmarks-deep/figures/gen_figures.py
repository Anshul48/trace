#!/usr/bin/env python3
"""bench-polish-v1: re-render bench-deep-v0 figures with layout defects fixed.
Stdlib only. Reads results/*.json + repo tree JSON (read-only). No external fetch.
Changes vs bench-deep: ram-cpu split into ram-build + per-query-time; legend/
xlabel spacing in abstention-curve; y-axis + clear-space label in scored-fraction;
tree-route kept (spacing only)."""
import json, math, os

# Repo root resolved from this script's own location (docs/benchmarks-deep/figures/).
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
with open(os.path.join(ROOT, "docs", "benchmarks-deep", "results", "run_20k.json")) as f:
    run = json.load(f)
with open(os.path.join(ROOT, "docs", "benchmarks-deep", "results", "replay_agg.json")) as f:
    rep = json.load(f)
with open(os.path.join(ROOT, "docs", "explorer", "local_20k_data.json")) as f:
    tree = json.load(f)

BG, INK, MUT, LIT, SELF, GRID = ("#ffffff", "#1a1a1a", "#8a8f98",
                                 "#0b6e4f", "#b42318", "#d7dce3")

def head(w, h, title):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d" role="img"><title>%s</title>'
            '<rect width="%d" height="%d" fill="%s"/>' % (w, h, w, h, title, w, h, BG))

def badge(x, y, kind):
    c = "#0b6e4f" if kind == "REAL" else "#4a3aff"
    return ('<rect x="%d" y="%d" width="118" height="22" rx="4" fill="%s"/>'
            '<text x="%d" y="%d" font-size="12" fill="#fff" font-family="sans-serif">%s</text>'
            % (x, y, c, x+8, y+15, kind + (" RUN" if kind == "REAL" else "-DATA")))

def cap(lines, w, y):
    o = []
    for i, t in enumerate(lines):
        o.append('<text x="16" y="%d" font-size="11" fill="%s" font-family="sans-serif">%s</text>'
                 % (y + 14*i, MUT, t))
    return "".join(o)

def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ---- 1. tree route: 81-leaf grid, query route lit (kept; spacing only) ----
q = 0
l8 = run["routing"]["leaf_L8"]["per_query"][q]
opened = set(l8["opened"])
leaf_ids = sorted({x for a in tree["atoms"] for x in a["leaf_ids"]})
assert len(leaf_ids) == 81
selfleaf = tree["atoms"][0]["leaf_ids"]
W, H = 760, 560
o = [head(W, H, "Group tree with query route lit")]
o.append('<text x="16" y="30" font-size="16" font-family="sans-serif" fill="%s">'
         'Inside view: 81 leaves, one query route lit (leaf budget 8)</text>' % INK)
o.append(badge(16, 42, "REAL"))
# leaf grid 9x9
gx, gy, cell = 16, 84, 40
for i, lid in enumerate(leaf_ids):
    cx, cy = gx + (i % 9)*(cell+6), gy + (i//9)*(cell+6)
    fill = LIT if lid in opened else ("#eef1f4" if lid not in selfleaf else "#f6d9d5")
    o.append('<rect x="%d" y="%d" width="%d" height="%d" rx="5" fill="%s" stroke="%s"/>'
             % (cx, cy, cell, cell, fill, SELF if lid in selfleaf else GRID))
    if lid in opened or lid in selfleaf:
        o.append('<text x="%d" y="%d" font-size="8" fill="%s" font-family="sans-serif">%s</text>'
                 % (cx+3, cy+24, "#fff" if lid in opened else INK, lid.split("-")[1][:6]))
# side panel
px = gx + 9*(cell+6) + 24
panel = ["Query: atom #0 (doc %s)" % tree["atoms"][0]["doc_id"],
         "Opened leaves: %d of 81" % len(opened),
         "Atoms scored: %d of 144" % l8["scored"],
         "recall@10 vs exact: %.2f" % l8["rec10"],
         "Self leaf (red ring): %s" % ", ".join(selfleaf),
         "Green = opened; grey = untouched."]
for i, t in enumerate(panel):
    o.append('<text x="%d" y="%d" font-size="12" fill="%s" font-family="sans-serif">%s</text>'
             % (px, gy+20+22*i, INK, esc(t)))
o.append('<text x="%d" y="%d" font-size="11" fill="%s" font-family="sans-serif">Opened leaf ids:</text>' % (px, gy+184, MUT))
for i, lid in enumerate(sorted(opened)):
    o.append('<text x="%d" y="%d" font-size="10" fill="%s" font-family="monospace">%s</text>'
             % (px, gy+200+14*i, MUT, lid))
o.append(cap(["REAL RUN. Tree: docs/explorer/local_20k_data.json (51 parents, 81 leaves, 144 atoms).",
              "Route: results/run_20k.json routing.leaf_L8.per_query[0]. Scope: 20k prefix, 144 atoms.",
              "Green = the 8 leaves whose centres scored nearest; red ring = leaf holding the query atom."], W, H-52))
o.append("</svg>")
with open(os.path.join(HERE, "tree-route.svg"), "w") as f:
    f.write("".join(o))

# ---- 2. per-query scored fraction (y-axis 0-15%, label in clear space) ----
W, H = 760, 450
o = [head(W, H, "Per-query scored fraction")]
o.append('<text x="16" y="30" font-size="16" font-family="sans-serif" fill="%s">'
         'Per-query scored fraction at leaf budget 8 (144 queries)</text>' % INK)
o.append(badge(16, 42, "REAL"))
pq = run["routing"]["leaf_L8"]["per_query"]
fr = [p["scored"]/144 for p in pq]
mean = sum(fr)/len(fr)
ymax = 0.15  # fixed 0-15% axis: highest bar is ~13.2%
assert max(fr) < ymax, "axis too small for data"
bx, by, bw, bh = 56, 76, W-72, 230
o.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="%s"/>' % (bx, by, bw, bh, GRID))
for g in (0.0, 0.05, 0.10, 0.15):
    y = by+bh-(g/ymax)*bh
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s"/>' % (bx, y, bx+bw, y, GRID))
    o.append('<text x="%d" y="%.1f" font-size="10" fill="%s" font-family="sans-serif">%d%%</text>'
             % (bx-34, y+4, MUT, int(g*100+0.5)))
# (axis unit omitted: every tick already carries a % sign)
for i, f in enumerate(fr):
    x = bx + i*(bw/144)
    h = (f/ymax)*bh
    o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
             % (x, by+bh-h, bw/144-0.6, h, LIT))
my = by+bh-(mean/ymax)*bh
o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="2"/>'
         % (bx, my, bx+bw, my, SELF))
# mean label in clear space: white box, top-right inside plot (bars there are short)
lab = "mean %.1f rows (%.2f%%)" % (mean*144, mean*100)
lx, ly, lw, lh = bx+bw-208, by+8, 200, 24
o.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#ffffff" stroke="%s"/>' % (lx, ly, lw, lh, SELF))
o.append('<text x="%d" y="%d" font-size="11" fill="%s" font-family="sans-serif">%s</text>'
         % (lx+8, ly+16, SELF, lab))
o.append('<line x1="%d" y1="%d" x2="%d" y2="%.1f" stroke="%s" stroke-dasharray="4,3"/>'
         % (lx+lw//2, ly+lh, bx+bw-30, my, SELF))
o.append('<text x="%d" y="%d" font-size="11" fill="%s" font-family="sans-serif">query 0 .. 143 (each bar = one atom-as-query)</text>' % (bx, by+bh+22, MUT))
o.append(cap(["REAL RUN. Data: results/run_20k.json routing.leaf_L8.per_query[].scored / 144.",
              "Scope: 20k prefix; leaf centres (routing rows) not counted in these bars.",
              "Highest bar: %.1f%%; lowest: %.1f%%." % (max(fr)*100, min(fr)*100)], W, H-52))
o.append("</svg>")
with open(os.path.join(HERE, "scored-fraction.svg"), "w") as f:
    f.write("".join(o))

# ---- 3. abstention risk-coverage (legend + xlabel spacing fixed) ----
W, H = 840, 510
o = [head(W, H, "Abstention risk-coverage curve")]
o.append('<text x="16" y="30" font-size="16" font-family="sans-serif" fill="%s">'
         'Abstention: false-answer rate vs coverage (336 synthetic queries)</text>' % INK)
o.append(badge(16, 42, "REAL"))
bx, by, bw, bh = 56, 76, W-56-200, 300
o.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="%s"/>' % (bx, by, bw, bh, GRID))
for g in (0.0, 0.25, 0.5, 0.75, 1.0):
    x = bx+g*bw
    o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s"/>' % (x, by, x, by+bh, GRID))
    o.append('<text x="%.1f" y="%d" font-size="10" fill="%s" font-family="sans-serif">%.2f</text>' % (x-10, by+bh+16, MUT, g))
    y = by+bh-g*bh
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s"/>' % (bx, y, bx+bw, y, GRID))
    o.append('<text x="%d" y="%.1f" font-size="10" fill="%s" font-family="sans-serif">%.2f</text>' % (bx-34, y+4, MUT, g))
o.append('<text x="%d" y="%d" font-size="11" fill="%s" font-family="sans-serif">coverage (answered / 336) -&gt;</text>' % (bx+bw//2-90, by+bh+36, MUT))
cols = {"top1": LIT, "margin": "#b26a00"}
for sname, col in cols.items():
    pts = []
    for r in run["abstention_curves"][sname]:
        p = r["pooled"]
        pts.append((bx+p["coverage"]*bw, by+bh-p["false_answer_rate"]*bh))
    o.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2"/>'
             % (" ".join("%.1f,%.1f" % t for t in pts), col))
for idx, (sname, col) in enumerate(cols.items()):
    lx, ly = bx+bw+14, by+20+26*idx
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="3"/>' % (lx, ly, lx+24, ly, col))
    o.append('<text x="%d" y="%d" font-size="11" fill="%s" font-family="sans-serif">%s</text>'
             % (lx+30, ly+4, INK, "top-1 score" if sname == "top1" else "top-1 minus top-2"))
# prereg points (labels offset into clear space)
for sname, thr, col, dx, dy in (("top1", 0.95, LIT, 8, -8), ("margin", 0.10, "#b26a00", 8, -8)):
    p = run["abstention_prereg"]["%s_%s" % (sname, thr)]
    x, y = bx+p["coverage"]*bw, by+bh-p["false_answer_rate"]*bh
    o.append('<circle cx="%.1f" cy="%.1f" r="5" fill="%s" stroke="#fff"/>' % (x, y, col))
    o.append('<rect x="%.1f" y="%.1f" width="86" height="16" fill="#ffffff" opacity="0.85"/>' % (x+dx-2, y+dy-11))
    o.append('<text x="%.1f" y="%.1f" font-size="10" fill="%s" font-family="sans-serif">%s=%.2f</text>' % (x+dx, y+dy, INK, sname, thr))
o.append(cap(["REAL RUN. Data: results/run_20k.json abstention_curves (120 swept thresholds/signal, pooled).",
              "Scope: 144 answerable + 192 constructed unanswerable (held-out + seed-7 noise); strict self-match;",
              "any answer to an unanswerable counts as a false answer. Lower curve = fewer false answers per coverage."], W, H-52))
o.append("</svg>")
with open(os.path.join(HERE, "abstention-curve.svg"), "w") as f:
    f.write("".join(o))

# ---- 4a. build memory only (was top half of ram-cpu) ----
def logbars(o, rows, unit, y0, bx, bw, rh=24, gap=18):
    lo = math.log10(min(v for _, v, _, _ in rows))
    hi = math.log10(max(v for _, v, _, _ in rows))
    for i, (name, v, kind, src) in enumerate(rows):
        y = y0+16+i*(rh+gap)
        w = max(4, (math.log10(v)-lo)/((hi-lo) or 1)*(bw-260))
        col = LIT if kind == "REAL" else "#4a3aff"
        o.append('<text x="16" y="%d" font-size="11" fill="%s" font-family="sans-serif">%s [%s]</text>' % (y+16, INK, esc(name), kind))
        o.append('<rect x="%d" y="%d" width="%.1f" height="%d" fill="%s"/>' % (bx, y, w, rh, col))
        tx = bx + max(w+8, 30)  # value label never inside/touching a short bar
        o.append('<text x="%.1f" y="%d" font-size="10" fill="%s" font-family="sans-serif">%g %s (%s)</text>' % (tx, y+16, MUT, v, unit, esc(src)))
    return y0+16+len(rows)*(rh+gap)+10

W = 880
ram = [("this job stdlib run", 23.9, "REAL", "run_20k.time.log"),
       ("20k frozen pilot", 136.6, "RECORDED", "pilot-20k-out2/result.json"),
       ("seam12a build", 8489.1, "RECORDED", "seam12a-result.json"),
       ("G5 build", 22565.5, "RECORDED", "receipts/result.json")]
H = 400
o = [head(W, H, "Peak build memory by run")]
o.append('<text x="16" y="30" font-size="16" font-family="sans-serif" fill="%s">'
         'Peak build memory by run (log scale, MiB)</text>' % INK)
o.append(badge(16, 42, "RECORDED"))
o.append('<text x="142" y="57" font-size="11" fill="%s" font-family="sans-serif">mixed: REAL + RECORDED-DATA, labeled per bar</text>' % MUT)
o.append('<text x="16" y="96" font-size="11" fill="%s" font-family="sans-serif">Scope: peak resident memory while BUILDING only (never serving); one bar per run.</text>' % INK)
logbars(o, ram, "MiB", 104, 250, W-266)
o.append(cap(["Scopes differ per bar — read the labels, not just the lengths.",
              "This job: 20k prefix, 144 atoms. Earlier runs: smaller-corpus builds (see page section 4).",
              "Do not compare these build peaks against per-query serving figures."], W, H-52))
o.append("</svg>")
with open(os.path.join(HERE, "ram-build.svg"), "w") as f:
    f.write("".join(o))

# ---- 4b. per-query time only (was bottom half of ram-cpu) ----
cpu = [("this job exact", 4.63, "REAL", "run_20k.json"),
       ("this job leaf-8", 2.67, "REAL", "run_20k.json"),
       ("BEIR FiQA exact", 9.883, "RECORDED", "beir summary.md"),
       ("BEIR FiQA grouped p16", 0.742, "RECORDED", "beir summary.md"),
       ("replay guided p50", 1198.8, "RECORDED", "replay.js"),
       ("replay exact p50", 1288.1, "RECORDED", "replay.js")]
H = 490
o = [head(W, H, "Per-query wall time by run")]
o.append('<text x="16" y="30" font-size="16" font-family="sans-serif" fill="%s">'
         'Per-query wall time by run (log scale, ms)</text>' % INK)
o.append(badge(16, 42, "RECORDED"))
o.append('<text x="142" y="57" font-size="11" fill="%s" font-family="sans-serif">mixed: REAL + RECORDED-DATA, labeled per bar</text>' % MUT)
o.append('<text x="16" y="96" font-size="11" fill="%s" font-family="sans-serif">Scope: per-query wall time; each bar its own machine and protocol — no cross-bar comparison.</text>' % INK)
logbars(o, cpu, "ms", 104, 250, W-266)
o.append(cap(["Scopes differ per bar — read the labels, not just the lengths.",
              "This job: 20k prefix on laptop stdlib script. BEIR: FiQA 57,638 passages on Ryzen. Replay: sealed",
              "812,545-passage library on VM service. Do not compare these against build-memory peaks."], W, H-52))
o.append("</svg>")
with open(os.path.join(HERE, "per-query-time.svg"), "w") as f:
    f.write("".join(o))
print("wrote 5 SVGs")
