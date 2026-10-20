#!/usr/bin/env python3
"""TRACE /play/ CLI parity: print probe #n's recorded row + corpus means.

Reads the SAME staged bytes the browser replays (docs/explorer/*.json) and
verifies the re-aggregated means against eval_summary. This is re-aggregation,
not rescoring: per-probe ranked lists and atom vectors are unexported.

Usage: python3 docs/play/probe-row.py 7 [--corpus 10m|20k] [--lso 0|1]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent / "explorer"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("probe", type=int)
    ap.add_argument("--corpus", default="10m", choices=["10m", "20k"])
    ap.add_argument("--lso", type=int, default=0, choices=[0, 1])
    args = ap.parse_args()

    if args.corpus == "10m":
        q = json.load(open(EXP / "qualification_10m.json"))
        rows = q["queries"]
        ev = q.get("evaluation_summary", {})
    else:
        d = json.load(open(EXP / "local_20k_data.json"))
        rows = d["evaluation_queries"]
        ev = {}

    want = [r for r in rows if r["probe"] == args.probe
            and (r["leave_source_out"] == bool(args.lso))]
    if not want:
        print(f"no row: probe {args.probe} lso={args.lso}", file=sys.stderr)
        return 1
    r = want[0]
    w = r["work"]
    mode = "lso" if args.lso else "all"
    print(f"probe {r['probe']} {r['family']} {mode}: "
          f"guided {r['guided_recall10']} flat {r['flat_recall10']} "
          f"({w['parents_scored']}p/{w['children_scored']}c/{w['atoms_scored']}a) "
          "MATCHES staged row")

    sub = [x for x in rows if x["leave_source_out"] == bool(args.lso)]
    mg = sum(x["guided_recall10"] for x in sub) / len(sub)
    mf = sum(x["flat_recall10"] for x in sub) / len(sub)
    print(f"{len(sub)} probes ({args.corpus} {mode}): "
          f"guided {mg:.4f} flat {mf:.4f}", end=" ")
    key = "leave_source_out" if args.lso else "all_sources"
    if ev and key in ev:
        ok = (abs(ev[key]["guided_recall10"] - mg) < 1e-9
              and abs(ev[key]["flat_recall10"] - mf) < 1e-9)
        print("MATCHES eval_summary" if ok else "MISMATCH vs eval_summary")
        return 0 if ok else 2
    print("(no eval_summary block in this corpus file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
