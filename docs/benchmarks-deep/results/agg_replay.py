#!/usr/bin/env python3
"""Aggregate replay.js (read-only) into results JSON for figures. Stdlib."""
import json, os, statistics, sys
# Repo root resolved from this script's own location (docs/benchmarks-deep/results/).
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
P = os.path.join(ROOT, "docs", "explorer", "data", "replay.js")
with open(P) as f:
    s = f.read()
d = json.loads(s[s.index("{"):s.rindex("}")+1])
qs = d["questions"]
rows = []
for q in qs:
    g = [x[0] for x in q["g"]]
    f = [x[0] for x in q["f"]]
    rows.append({"id": q["id"], "cat": q.get("cat"),
                 "overlap10": len(set(g) & set(f))/10,
                 "same_order": g == f, "tg_ms": q["tg"], "tf_ms": q["tf"],
                 "top1_score": q["g"][0][1],
                 "margin": q["g"][0][1]-q["g"][1][1]})
ovs = [r["overlap10"] for r in rows]
tgs = [r["tg_ms"] for r in rows]
tfs = [r["tf_ms"] for r in rows]
json.dump({"meta": d["meta"],
           "n": len(rows),
           "identical_sets": sum(1 for r in rows if r["overlap10"] == 1.0),
           "same_order": sum(1 for r in rows if r["same_order"]),
           "mean_overlap10": statistics.mean(ovs),
           "tg_ms": {"p50": statistics.median(tgs), "mean": statistics.mean(tgs),
                     "min": min(tgs), "max": max(tgs)},
           "tf_ms": {"p50": statistics.median(tfs), "mean": statistics.mean(tfs),
                     "min": min(tfs), "max": max(tfs)},
           "rows": rows}, sys.stdout, indent=1)
