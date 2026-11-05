#!/usr/bin/env python3
"""bench-fix-figs-v1: red-team findings B,D,E,J,K repaired in the figures.
Stdlib only. Every plotted number is read mechanically from a shipped record
(time log / results JSON / replay JSON / tree + span-hash join); no literals.
Reads results/*.json + repo tree JSON + 20k corpus join inputs (read-only).
Badge words match the page's evidence-status definitions (RECEIPTED =
record shipped in this repo). No external fetch."""
import json, math, os

# Repo root resolved from this script's own location (docs/benchmarks-deep/figures/).
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RES = os.path.join(ROOT, "docs", "benchmarks-deep", "results")
with open(os.path.join(RES, "run_20k.json")) as f:
    run = json.load(f)
with open(os.path.join(RES, "replay_agg.json")) as f:
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
    c = "#0b6e4f" if kind == "RECEIPTED" else "#4a3aff"
    return ('<rect x="%d" y="%d" width="118" height="22" rx="4" fill="%s"/>'
            '<text x="%d" y="%d" font-size="12" fill="#fff" font-family="sans-serif">%s</text>'
            % (x, y, c, x+8, y+15, kind))

def cap(lines, w, y):
    o = []
    for i, t in enumerate(lines):
        o.append('<text x="16" y="%d" font-size="11" fill="%s" font-family="sans-serif">%s</text>'
                 % (y + 14*i, MUT, t))
    return "".join(o)

def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ---- 1. tree route: 81-leaf grid, query route lit ----
# B: query identity resolved through the SAME span-hash join as the
# measurement (run_20k.py:43-48), not the tree's array order. If the join
# cannot be verified, the self highlight is suppressed (kill criterion).
q = 0
l8 = run["routing"]["leaf_L8"]["per_query"][q]
opened = set(l8["opened"])
leaf_ids = sorted({x for a in tree["atoms"] for x in a["leaf_ids"]})
assert len(leaf_ids) == 81
def query_atom(row):
    import hashlib
    idx = {}
    with open(os.path.join(ROOT, "docs", "reproduction", "repro-20k",
                           "data-20k", "emb_cache", "index.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            idx[r["chunk_sha256"]] = r["row"]
    docs = {}
    with open(os.path.join(ROOT, "docs", "reproduction", "repro-20k",
                           "data-20k", "docs-100m.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            docs[r["doc_id"]] = r["text"].encode("utf-8")
    aid_row = {}
    for a in tree["atoms"]:
        s, e = a["byte_span"]
        h = hashlib.sha256(docs[a["doc_id"]][s:e]).hexdigest()
        assert h in idx, "span hash missing from vector index"
        aid_row[a["id"]] = idx[h]
    assert len(set(aid_row.values())) == len(tree["atoms"]), "join must cover all rows"
    hit = [a for a in tree["atoms"] if aid_row[a["id"]] == row]
    assert len(hit) == 1, "row must map to exactly one atom"
    return hit[0]
try:
    qatom = query_atom(q)
    selfleaf = list(qatom["leaf_ids"])
    qline = "Query: row #%d (doc %s)" % (q, qatom["doc_id"])
    selfline = "Self leaf (red ring): %s" % ", ".join(selfleaf)
    self_opened = "yes" if set(selfleaf) & opened else "no"
    joinline = ("Query identity verified by the span-sha256 join (run_20k.py:43): "
                "row %d = doc %s; self leaf opened: %s."
                % (q, qatom["doc_id"], self_opened))
except Exception:
    selfleaf = []
    qline = "Query: row #%d" % q
    selfline = "Self leaf: not verified"
    joinline = "Query identity NOT verified: self highlight suppressed."
W, H = 760, 560
o = [head(W, H, "Group tree with query route lit")]
o.append('<text x="16" y="30" font-size="16" font-family="sans-serif" fill="%s">'
         'Inside view: 81 leaves, one query route lit (leaf budget 8)</text>' % INK)
o.append(badge(16, 42, "RECEIPTED"))
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
panel = [qline,
         "Opened leaves: %d of 81" % len(opened),
         "Atoms scored: %d of 144" % l8["scored"],
         "recall@10 vs exact: %.2f" % l8["rec10"],
         selfline,
         "Green = opened; grey = untouched."]
for i, t in enumerate(panel):
    o.append('<text x="%d" y="%d" font-size="12" fill="%s" font-family="sans-serif">%s</text>'
             % (px, gy+20+22*i, INK, esc(t)))
o.append('<text x="%d" y="%d" font-size="11" fill="%s" font-family="sans-serif">Opened leaf ids:</text>' % (px, gy+184, MUT))
for i, lid in enumerate(sorted(opened)):
    o.append('<text x="%d" y="%d" font-size="10" fill="%s" font-family="monospace">%s</text>'
             % (px, gy+200+14*i, MUT, lid))
o.append(cap(["RECEIPTED. Tree: docs/explorer/local_20k_data.json (51 parents, 81 leaves, 144 atoms).",
              "Route: results/run_20k.json routing.leaf_L8.per_query[0]. Scope: 20k prefix, 144 atoms.",
              esc(joinline)], W, H-52))
o.append("</svg>")
with open(os.path.join(HERE, "tree-route.svg"), "w") as f:
    f.write("".join(o))

# ---- 2. per-query scored fraction (y-axis 0-15%, label in clear space) ----
W, H = 760, 450
o = [head(W, H, "Per-query scored fraction")]
o.append('<text x="16" y="30" font-size="16" font-family="sans-serif" fill="%s">'
         'Per-query scored fraction at leaf budget 8 (144 queries)</text>' % INK)
o.append(badge(16, 42, "RECEIPTED"))
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
# mean label in clear space: white box, top-right inside plot (bars there are short).
# K: the 10.30% counts passages only; label it so.
lab = "mean %.1f rows (%.2f%% passages only)" % (mean*144, mean*100)
lx, ly, lw, lh = bx+bw-288, by+8, 280, 24
o.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#ffffff" stroke="%s"/>' % (lx, ly, lw, lh, SELF))
o.append('<text x="%d" y="%d" font-size="11" fill="%s" font-family="sans-serif">%s</text>'
         % (lx+8, ly+16, SELF, lab))
o.append('<line x1="%d" y1="%d" x2="%d" y2="%.1f" stroke="%s" stroke-dasharray="4,3"/>'
         % (lx+lw//2, ly+lh, bx+bw-30, my, SELF))
o.append('<text x="%d" y="%d" font-size="11" fill="%s" font-family="sans-serif">query 0 .. 143 (each bar = one atom-as-query)</text>' % (bx, by+bh+22, MUT))
o.append(cap(["RECEIPTED. Data: results/run_20k.json routing.leaf_L8.per_query[].scored / 144.",
              "Scope: 20k prefix; passages only — leaf centres (routing rows) not counted in these bars.",
              "Highest bar: %.1f%%; lowest: %.1f%%." % (max(fr)*100, min(fr)*100)], W, H-52))
o.append("</svg>")
with open(os.path.join(HERE, "scored-fraction.svg"), "w") as f:
    f.write("".join(o))

# ---- 3. abstention risk-coverage (legend + xlabel spacing fixed) ----
W, H = 840, 510
o = [head(W, H, "Abstention risk-coverage curve")]
o.append('<text x="16" y="30" font-size="16" font-family="sans-serif" fill="%s">'
         'Abstention: false-answer rate vs coverage (336 synthetic queries)</text>' % INK)
o.append(badge(16, 42, "RECEIPTED"))
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
o.append('<text x="%d" y="%d" font-size="11" fill="%s" font-family="sans-serif">y: false-answer rate = wrong answers / all 336 queries</text>' % (150, by-12, MUT))
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
o.append(cap(["RECEIPTED. Data: results/run_20k.json abstention_curves (120 swept thresholds/signal, pooled).",
              "Scope: 144 answerable + 192 constructed unanswerable (held-out + seed-7 noise); strict self-match;",
              "any answer to an unanswerable counts as a false answer. Lower curve = fewer false answers per coverage."], W, H-52))
o.append("</svg>")
with open(os.path.join(HERE, "abstention-curve.svg"), "w") as f:
    f.write("".join(o))

# ---- helpers for the two record-driven bar figures ----
def logbars(o, rows, y0, bx, bw, rh=24, gap=18):
    # rows: (name, scale_value, label_text, src). Each call gets its own log
    # axis: never share one axis across unlike machines/protocols.
    lo = math.log10(min(v for _, v, _, _ in rows))
    hi = math.log10(max(v for _, v, _, _ in rows))
    single = (len(rows) == 1) or (hi == lo)
    for i, (name, v, lab, src) in enumerate(rows):
        y = y0+16+i*(rh+gap)
        if single:
            w = (bw-260)*0.35  # one bar: length carries no comparison
        else:
            w = max(4, (math.log10(v)-lo)/((hi-lo) or 1)*(bw-260))
        o.append('<text x="16" y="%d" font-size="11" fill="%s" font-family="sans-serif">%s [RECEIPTED]</text>' % (y+16, INK, esc(name)))
        o.append('<rect x="%d" y="%d" width="%.1f" height="%d" fill="%s"/>' % (bx, y, w, rh, LIT))
        tx = bx + max(w+8, 30)  # value label never inside/touching a short bar
        o.append('<text x="%.1f" y="%d" font-size="10" fill="%s" font-family="sans-serif">%s (%s)</text>' % (tx, y+16, MUT, lab, esc(src)))
    return y0+16+len(rows)*(rh+gap)+10

def panelhead(o, y, text):
    o.append('<text x="16" y="%d" font-size="12" font-family="sans-serif" fill="%s">%s</text>' % (y, INK, esc(text)))

def read_peak(path):
    with open(path) as f:
        return json.load(f)["peak_parent_rss_mib"]

# ---- 4a. memory: whole-script peak vs full-store build peaks (split panels) ----
# J: the script's number is a whole-process peak (tree loaded, centres
# computed), not a store build; it gets its own panel and label. K: the
# conversion is mechanical (23856 KiB / 1024 = 23.296875 MiB).
maxrss_kb = None
with open(os.path.join(RES, "run_20k.time.log")) as f:
    for line in f:
        if "Maximum resident set size" in line:
            maxrss_kb = int(line.split(":")[1].split()[0])
assert maxrss_kb is not None, "time log lacks Maximum RSS"
job_mib = maxrss_kb/1024
assert abs(job_mib - run["peak_rss_mib"]) < 1e-9, "log vs JSON peak disagree"
pilot_mib = read_peak(os.path.join(ROOT, "docs", "reproduction", "repro-20k",
                                   "pilot-20k-out2", "result.json"))
seam_mib = read_peak(os.path.join(ROOT, "receipts", "earlier-runs", "seam12a-result.json"))
g5_mib = read_peak(os.path.join(ROOT, "receipts", "result.json"))
W, H = 880, 400
o = [head(W, H, "Peak memory by run")]
o.append('<text x="16" y="30" font-size="16" font-family="sans-serif" fill="%s">'
         'Peak memory by run (log scale, MiB; separate panels)</text>' % INK)
o.append(badge(16, 42, "RECEIPTED"))
o.append('<text x="142" y="57" font-size="11" fill="%s" font-family="sans-serif">all bars RECEIPTED (record shipped in this repo), labeled per bar</text>' % MUT)
panelhead(o, 92, "A. This-job stdlib script: whole-process peak (tree loaded from JSON, centres computed; NOT a store build).")
logbars(o, [("this job stdlib run", job_mib, "%.2f MiB" % job_mib, "run_20k.time.log")],
        100, 250, W-266)
panelhead(o, 178, "B. Full-store builds: peak parent RSS while building (own log axis; not comparable to A).")
logbars(o, [("20k frozen pilot", pilot_mib, "%.1f MiB" % pilot_mib, "pilot-20k-out2/result.json"),
            ("seam12a build", seam_mib, "%.1f MiB" % seam_mib, "seam12a-result.json"),
            ("G5 build", g5_mib, "%.1f MiB" % g5_mib, "receipts/result.json")],
        186, 250, W-266)
o.append(cap(["Panel A: %d KiB / 1024 = %.6f MiB (run_20k.time.log; cross-checked vs run_20k.json peak_rss_mib)." % (maxrss_kb, job_mib),
              "Panel B: peak_parent_rss_mib per receipt (pilot/seam12a/G5 full-store builds; scopes in page section 4).",
              "Separate log axes per panel: read values, not lengths; never compare A against B."], W, H-52))
o.append("</svg>")
with open(os.path.join(HERE, "ram-build.svg"), "w") as f:
    f.write("".join(o))

# ---- 4b. per-query time: script means vs replay-service p50s (split panels) ----
# D: the FiQA stand-in bars are gone (source "beir summary.md" is not shipped;
# page section 9: AS STATED, not TRACE's method) — no shared axis across
# unlike machines/protocols. E: script values read from run_20k.json.
exact_ms = run["timings_s"]["exact_per_query_s"]["mean"]*1000
leaf8_ms = run["routing"]["leaf_L8"]["per_query_wall_mean_s"]*1000
guided_p50 = rep["tg_ms"]["p50"]
exact_p50 = rep["tf_ms"]["p50"]
W, H = 880, 400
o = [head(W, H, "Per-query wall time by run")]
o.append('<text x="16" y="30" font-size="16" font-family="sans-serif" fill="%s">'
         'Per-query wall time by run (log scale, ms; separate panels)</text>' % INK)
o.append(badge(16, 42, "RECEIPTED"))
o.append('<text x="142" y="57" font-size="11" fill="%s" font-family="sans-serif">all bars RECEIPTED (record shipped in this repo), labeled per bar</text>' % MUT)
panelhead(o, 92, "A. This-job stdlib script, laptop CPU: mean per-query wall over 144 atom-queries.")
logbars(o, [("this job exact (mean)", exact_ms, "%.3f ms" % exact_ms, "run_20k.json"),
            ("this job leaf-8 (mean)", leaf8_ms, "%.3f ms" % leaf8_ms, "run_20k.json")],
        100, 250, W-266)
panelhead(o, 212, "B. Sealed-library replay service, VM: p50 server time over 144 recorded questions (own axis).")
logbars(o, [("replay guided (p50)", guided_p50, "%.1f ms" % guided_p50, "replay_agg.json"),
            ("replay exact (p50)", exact_p50, "%.1f ms" % exact_p50, "replay_agg.json")],
        220, 250, W-266)
o.append(cap(["Panel A: exact %.6f ms, leaf-8 %.6f ms (run_20k.json timings/routing means x1000)." % (exact_ms, leaf8_ms),
              "Panel B: guided p50 %.1f ms, exact p50 %.1f ms (replay_agg.json tg_ms/tf_ms)." % (guided_p50, exact_p50),
              "Separate log axes per panel: read values, not lengths; never compare A against B."], W, H-52))
o.append("</svg>")
with open(os.path.join(HERE, "per-query-time.svg"), "w") as f:
    f.write("".join(o))
print("wrote 5 SVGs")
