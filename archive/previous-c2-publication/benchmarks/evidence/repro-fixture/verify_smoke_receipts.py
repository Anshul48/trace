#!/usr/bin/env python3
"""Re-verify the bundled smoke-lane receipts against REPORT.md §1 (stdlib only).

Parses the shipped smoke RUN.json + TREC files and asserts the published
smoke numbers, zero failures, and the A1 implementation self-identity
(arm, budgets, adapter + serving shas). This checks receipt integrity —
it is NOT a 10M measurement and NOT a substitute for re-running the lane
(see README.md for the live re-run protocol).

Usage:  python benchmarks/evidence/repro-fixture/verify_smoke_receipts.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SMOKE = HERE.parent / "receipts-10m-shipped" / "lane-BENCH10M" / "smoke-a1"

RUN_SHA = "19d96e621e0adf6163bdddac550443a669856487f0951799ba0361c87cea1d59"

# REPORT.md §1 smoke table, rounded as published.
EXPECT = {
    "bm25": {"n": "overall_ndcg_at_10", "v": 0.903, "m": "overall_map_at_10",
             "mv": 0.833, "r": "overall_recall_at_20", "rv": 0.933,
             "mrr": "overall_mrr", "mrrv": 1.000},
    "python:c2_bench10m:C2Bench10MShipped": {
        "n": "overall_ndcg_at_10", "v": 0.851, "m": "overall_map_at_10",
        "mv": 0.740, "r": "overall_recall_at_20", "rv": 1.000,
        "mrr": "overall_mrr", "mrrv": 0.900},
}

SERVING = {
    "tl-sys/tlsys/dossier.py":
        "93871fb3e7f63e58d9c48c113efecd551a5271c73184968259f8cce3df4e7ac0",
    "tl-sys/tlsys/relquery.py":
        "0fe79c501cf3582face656ff3da7340534ae871780f4e16c7e0f876f6afb45a8",
    "tl-sys/tlsys/relserve.py":
        "61b69a84c648717955426e3bbb3ffde7526658483f05a7532f9d145582bc9b71",
    "tl-sys/tlsys/query.py":
        "d7756e72e2de65814103e216edfc7d53650cc0fada34cefe7cf41411f03414ce",
    "tl-sys/tlsys/index.py":
        "b8bc139008a9da185f3438823836e03b8a171a10d0677faf7448ed21afcebef0",
    "tl-sys/tlsys/serving/generation.py":
        "929709390af18e7511197164d399ba71f368c767c2fc2df3680f43254424b22f",
    "tl-sys/tlsys/prodstate.py":
        "e7a4370c3e6faf122927db34919b2d42838f0b800edc4c8f877b564f405a47b1",
}
ADAPTER_SHA = "0f6e7bc3181f9702a453fd5b7fc0c7a1121cf8543d73af1d0a92d2a1b103fc71"


def fail(msg: str) -> None:
    print(f"SMOKE-VERIFY FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    import hashlib
    runs = sorted(SMOKE.glob("run_*.json"))
    if len(runs) != 1:
        fail(f"expected 1 smoke RUN.json, found {len(runs)}")
    if hashlib.sha256(runs[0].read_bytes()).hexdigest() != RUN_SHA:
        fail("smoke RUN.json hash mismatch")
    d = json.loads(runs[0].read_text(encoding="utf-8"))
    if d["total_cases"] != 6:
        fail(f"total_cases {d['total_cases']} != 6")
    if d["error_receipts"]:
        fail(f"run-level error receipts: {d['error_receipts']}")
    if set(d["baselines"]) != set(EXPECT):
        fail(f"arms {sorted(d['baselines'])} != 2-arm smoke lane")
    for name, e in EXPECT.items():
        b = d["baselines"][name]
        if b["status"] != "success":
            fail(f"{name}: status {b['status']}")
        if b["failed_cases_count"] != 0:
            fail(f"{name}: failures {b['failed_cases_count']}")
        for mk, ek in (("n", "v"), ("m", "mv"), ("r", "rv"), ("mrr", "mrrv")):
            got = round(b[e[mk]], 3)
            if got != e[ek]:
                fail(f"{name} {e[mk]}: {got} != published {e[ek]}")
    a1 = d["baselines"]["python:c2_bench10m:C2Bench10MShipped"]
    ii = a1["implementation_identity"]
    if ii["arm"] != "shipped-M80-P100-A40":
        fail(f"arm {ii['arm']}")
    if ii["query_budgets"] != {"M_REGIONS": 80, "PRUNE_CAP": 100,
                               "MAX_ENTRIES": 40}:
        fail(f"budgets {ii['query_budgets']}")
    if ii["source_sha256"] != ADAPTER_SHA:
        fail("adapter source sha mismatch")
    for path, want in SERVING.items():
        if ii["serving_file_sha256"].get(path) != want:
            fail(f"serving identity mismatch: {path}")
    trecs = sorted(SMOKE.glob("run_*.trec"))
    if len(trecs) != 2 or any(t.stat().st_size == 0 for t in trecs):
        fail(f"expected 2 non-empty trecs, found {len(trecs)}")
    print("SMOKE-VERIFY PASS: 2 arms success, 0 failures, published "
          "smoke numbers + A1 arm/budgets/adapter/serving identity all match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
