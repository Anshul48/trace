# SPDX-License-Identifier: Apache-2.0
"""Repeated-task-series to checked-script demo on SYNTHETIC data only.

Every brief, input and output handled here is invented by the generator in
this file from a fixed synthetic vocabulary (imaginary stores, shipments,
shelves, weights). Nothing here describes any real workload, and no part
of the output makes any claim about one.

Pipeline stages (each is also a CLI subcommand):

* ``gen``    -- write five synthetic datasets (a/b/c/d/e) to a directory.
* ``detect`` -- group briefs that differ only in slots (numbers, dates,
  ids, paths); a group of >= 5 is reported as a series.
* ``shadow`` -- run the candidate script over every past input and compare
  with the recorded output field by field, beside control rows
  (copy-previous-output; worker-against-worker agreement where several
  workers ran the same input).
* ``guard``  -- refuse inputs outside what the series showed (new slot
  values, new schema, corrupted input) and hand them to a person.
* ``demo``   -- run gen/detect/shadow/guard end to end and print one table.

Stdlib only. Deterministic: fixed seeds, sorted traversal, no timestamps,
no paths in printed output.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import sys
import tempfile

MIN_SERIES = 5
SEED_A = 20310117
SEED_B = 20310217
SEED_E = 20310317
N_A = 40
N_B = 40
N_C = 40
N_D = 40
N_E = 30
B_V1_RUNS = 20  # runs 1..20 use method v1, runs 21..40 use method v2
D_CORRUPT_RUN = 17  # 1-based id of the corrupted run in dataset (d)
CRATE_FEE = 10.0
GAMMA_ALLOWANCE = 1.10

STORES = ["WH-01", "WH-02", "WH-03", "WH-04", "WH-05"]
SHELVES = ["/demo/shelf/A", "/demo/shelf/B", "/demo/shelf/C", "/demo/shelf/D"]
BRIEF_PACK = ("Packing summary for DEMO store {store} on {date}: shipment "
              "{ship} staged at {shelf}. Count items and total weight.")
BRIEF_SHIP = ("Shipping estimate for DEMO store {store} on {date}: shipment "
              "{ship} staged at {shelf}. Total weight by worker convention.")
VERBS_C = ["Calibrate", "Photograph", "Inventory", "Survey",
           "Catalog", "Inspect", "Map", "Audit"]
OBJECTS_C = ["harbor beacon array", "orchard irrigation grid",
             "museum tapestry wing", "stadium lighting rig",
             "library archive vault"]

WORKERS_E = ("worker_alpha", "worker_beta", "worker_gamma")

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
PATH_RE = re.compile(r"/demo/[A-Za-z0-9/_-]+")
ID_RE = re.compile(r"\b(?:DEMO|WH|WIDGET)-[A-Za-z0-9]+\b")
NUM_RE = re.compile(r"\d+")
WS_RE = re.compile(r"\s+")

TOP_KEYS = ("date", "items", "shelf", "shipment", "store")
ITEM_KEYS = ("qty", "sku", "weight")
DATE_FMT = re.compile(r"2031-01-\d{2}\Z")
SHIP_FMT = re.compile(r"DEMO-\d{4}\Z")
SKU_FMT = re.compile(r"WIDGET-\d{4}\Z")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def canon(obj) -> str:
    """Canonical string form used for every field-by-field comparison."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"))


def write_run(path: str, run: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(run, handle, sort_keys=True, indent=2)
        handle.write("\n")


def read_runs(data_dir: str) -> list:
    runs = []
    for name in sorted(os.listdir(data_dir)):
        if not (name.startswith("run-") and name.endswith(".json")):
            continue
        with open(os.path.join(data_dir, name), encoding="utf-8") as handle:
            runs.append(json.load(handle))
    runs.sort(key=lambda r: r["id"])
    return runs


def _is_num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# gen: synthetic data only
# ---------------------------------------------------------------------------

def synth_input(rng: random.Random) -> dict:
    items = []
    for _ in range(1 + rng.randrange(4)):
        items.append({
            "sku": "WIDGET-%04d" % (1 + rng.randrange(50)),
            "weight": round(0.5 + rng.random() * 9.0, 2),
            "qty": 1 + rng.randrange(9),
        })
    return {
        "store": STORES[rng.randrange(len(STORES))],
        "date": "2031-01-%02d" % (1 + rng.randrange(28)),
        "shipment": "DEMO-%04d" % (1000 + rng.randrange(9000)),
        "shelf": SHELVES[rng.randrange(len(SHELVES))],
        "items": items,
    }


def compute_v1(inp: dict) -> dict:
    """Candidate method: count items, total weight to 2 decimals."""
    items = inp.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("corrupted input: items is not a non-empty list")
    count = 0
    total = 0.0
    for pos, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("corrupted input: item %d is not an object" % pos)
        weight = item.get("weight")
        qty = item.get("qty")
        if not _is_num(weight):
            raise ValueError("corrupted input: weight is not a number")
        if not isinstance(qty, int) or isinstance(qty, bool):
            raise ValueError("corrupted input: qty is not an integer")
        if weight <= 0:
            raise ValueError("corrupted input: weight is not positive")
        if qty < 1:
            raise ValueError("corrupted input: qty is below one")
        count += qty
        total += weight * qty
    return {"item_count": count, "total_weight": round(total, 2)}


def compute_v2(inp: dict) -> dict:
    """Changed method used from run 21 on in dataset (b): adds crate fee."""
    base = compute_v1(inp)
    return {"item_count": base["item_count"],
            "total_weight": round(base["total_weight"] + CRATE_FEE, 2)}


def pack_brief(inp: dict) -> str:
    return BRIEF_PACK.format(store=inp["store"], date=inp["date"],
                             ship=inp["shipment"], shelf=inp["shelf"])


def ship_brief(inp: dict) -> str:
    return BRIEF_SHIP.format(store=inp["store"], date=inp["date"],
                             ship=inp["shipment"], shelf=inp["shelf"])


def worker_outputs(inp: dict) -> dict:
    """Three simulated workers reading one brief three ways (dataset e)."""
    base = compute_v1(inp)
    total = base["total_weight"]
    return {
        "worker_alpha": {"item_count": base["item_count"],
                         "total_weight": total},
        "worker_beta": {"item_count": base["item_count"],
                        "total_weight": round(total)},
        "worker_gamma": {"item_count": base["item_count"],
                         "total_weight": round(total * GAMMA_ALLOWANCE, 2)},
    }


def gen_dataset_a(out_dir: str) -> str:
    rng = random.Random(SEED_A)
    for run_id in range(1, N_A + 1):
        inp = synth_input(rng)
        write_run(os.path.join(out_dir, "run-%03d.json" % run_id),
                  {"id": run_id, "brief": pack_brief(inp),
                   "input": inp, "output": compute_v1(inp)})
    return out_dir


def gen_dataset_b(out_dir: str) -> str:
    rng = random.Random(SEED_B)
    for run_id in range(1, N_B + 1):
        inp = synth_input(rng)
        if run_id <= B_V1_RUNS:
            out = compute_v1(inp)
        else:
            out = compute_v2(inp)
        write_run(os.path.join(out_dir, "run-%03d.json" % run_id),
                  {"id": run_id, "brief": pack_brief(inp),
                   "input": inp, "output": out})
    return out_dir


def gen_dataset_c(out_dir: str) -> str:
    run_id = 0
    for verb in VERBS_C:
        for obj in OBJECTS_C:
            run_id += 1
            brief = "%s the %s (job DEMO-C%02d)." % (verb, obj, run_id)
            write_run(os.path.join(out_dir, "run-%03d.json" % run_id),
                      {"id": run_id, "brief": brief,
                       "input": {"job": "DEMO-C-%04d" % run_id,
                                 "detail": "%s %s" % (verb, obj)},
                       "output": {"status": "filed"}})
    return out_dir


def gen_dataset_d(out_dir: str) -> str:
    gen_dataset_a(out_dir)
    path = os.path.join(out_dir, "run-%03d.json" % D_CORRUPT_RUN)
    with open(path, encoding="utf-8") as handle:
        run = json.load(handle)
    run["input"]["items"][0]["weight"] = "N/A"
    run["output"] = {"status": "no-output-corrupted-input"}
    write_run(path, run)
    return out_dir


def gen_dataset_e(out_dir: str) -> str:
    rng = random.Random(SEED_E)
    for run_id in range(1, N_E + 1):
        inp = synth_input(rng)
        outputs = worker_outputs(inp)
        write_run(os.path.join(out_dir, "run-%03d.json" % run_id),
                  {"id": run_id, "brief": ship_brief(inp), "input": inp,
                   "output": outputs["worker_alpha"], "outputs": outputs})
    return out_dir


def gen_all(root: str) -> dict:
    paths = {}
    for name, func in (("a", gen_dataset_a), ("b", gen_dataset_b),
                       ("c", gen_dataset_c), ("d", gen_dataset_d),
                       ("e", gen_dataset_e)):
        data_dir = os.path.join(root, name)
        os.makedirs(data_dir, exist_ok=True)
        paths[name] = func(data_dir)
    return paths


# ---------------------------------------------------------------------------
# detect: group briefs that differ only in slots
# ---------------------------------------------------------------------------

def normalize_brief(brief: str) -> str:
    text = DATE_RE.sub("<DATE>", brief)
    text = PATH_RE.sub("<PATH>", text)
    text = ID_RE.sub("<ID>", text)
    text = NUM_RE.sub("<NUM>", text)
    return WS_RE.sub(" ", text).strip()


def detect_series(runs: list) -> tuple:
    """Return (series, brief_count, max_group).

    series is a list of (template, count, [run ids]) with count >= MIN_SERIES,
    sorted by descending count then template.
    """
    groups: dict = {}
    for run in runs:
        template = normalize_brief(run["brief"])
        groups.setdefault(template, []).append(run["id"])
    series = [(template, len(ids), sorted(ids))
              for template, ids in groups.items() if len(ids) >= MIN_SERIES]
    series.sort(key=lambda item: (-item[1], item[0]))
    max_group = max((len(ids) for ids in groups.values()), default=0)
    return series, len(runs), max_group


def format_detect(data_dir: str) -> list:
    runs = read_runs(data_dir)
    series, brief_count, max_group = detect_series(runs)
    if not series:
        return ["NO-SERIES briefs=%d max-group=%d (need >=%d)"
                % (brief_count, max_group, MIN_SERIES)]
    return ['SERIES count=%d template="%s"' % (count, template)
            for template, count, _ids in series]


# ---------------------------------------------------------------------------
# shadow: candidate script vs recorded outputs, plus controls
# ---------------------------------------------------------------------------

def candidate_script(brief: str, inp: dict) -> dict:
    if "Count items and total weight." in brief:
        return compute_v1(inp)
    if "Total weight by worker convention." in brief:
        return compute_v1(inp)
    raise ValueError("no compiled script for this brief")


def shadow_compare(runs: list) -> dict:
    matched, mismatched, corrupted, unsupported = [], [], [], []
    first_bad_field: dict = {}
    for run in runs:
        try:
            produced = candidate_script(run["brief"], run["input"])
        except ValueError as exc:
            if "no compiled script" in str(exc):
                unsupported.append(run["id"])
            else:
                corrupted.append(run["id"])
            continue
        recorded = run["output"]
        if canon(produced) == canon(recorded):
            matched.append(run["id"])
        else:
            mismatched.append(run["id"])
            for key in sorted(set(produced) | set(recorded)):
                if canon(produced.get(key)) != canon(recorded.get(key)):
                    first_bad_field[run["id"]] = key
                    break
    copy_prev = 0
    for pos, run in enumerate(runs):
        if pos == 0:
            continue  # no previous output to copy for the first run
        if canon(runs[pos - 1]["output"]) == canon(run["output"]):
            copy_prev += 1
    return {"n": len(runs), "matched": matched, "mismatched": mismatched,
            "corrupted": corrupted, "unsupported": unsupported,
            "copy_prev_matched": copy_prev,
            "copy_prev_total": max(len(runs) - 1, 0),
            "first_bad_field": first_bad_field}


def shadow_workers(runs: list) -> dict:
    """Script-vs-each-worker and worker-against-worker agreement (dataset e)."""
    script_vs = {name: 0 for name in WORKERS_E}
    agree = {pair: 0 for pair in (("worker_alpha", "worker_beta"),
                                  ("worker_alpha", "worker_gamma"),
                                  ("worker_beta", "worker_gamma"))}
    usable = 0
    for run in runs:
        outputs = run.get("outputs")
        if not outputs:
            continue
        usable += 1
        try:
            produced = canon(candidate_script(run["brief"], run["input"]))
        except ValueError:
            continue
        for name in WORKERS_E:
            if produced == canon(outputs[name]):
                script_vs[name] += 1
        for left, right in agree:
            if canon(outputs[left]) == canon(outputs[right]):
                agree[(left, right)] += 1
    out = {"n": usable}
    for name in WORKERS_E:
        out["script_vs_" + name] = script_vs[name]
    for (left, right), count in agree.items():
        out["agree_%s_%s" % (left, right)] = count
    return out


def format_shadow(data_dir: str) -> list:
    runs = read_runs(data_dir)
    comp = shadow_compare(runs)
    lines = ["script matched=%d mismatched=%d corrupted=%d unsupported=%d"
             % (len(comp["matched"]), len(comp["mismatched"]),
                len(comp["corrupted"]), len(comp["unsupported"]))]
    if comp["mismatched"]:
        lines.append("script first-mismatch-run=%03d last-mismatch-run=%03d"
                     % (min(comp["mismatched"]), max(comp["mismatched"])))
    lines.append("copy-previous matched=%d/%d"
                 % (comp["copy_prev_matched"], comp["copy_prev_total"]))
    if any(run.get("outputs") for run in runs):
        workers = shadow_workers(runs)
        lines.append("script-vs-worker alpha=%d/%d beta=%d/%d gamma=%d/%d"
                     % (workers["script_vs_worker_alpha"], workers["n"],
                        workers["script_vs_worker_beta"], workers["n"],
                        workers["script_vs_worker_gamma"], workers["n"]))
        lines.append("worker-agreement alpha-beta=%d/%d alpha-gamma=%d/%d "
                     "beta-gamma=%d/%d"
                     % (workers["agree_worker_alpha_worker_beta"], workers["n"],
                        workers["agree_worker_alpha_worker_gamma"], workers["n"],
                        workers["agree_worker_beta_worker_gamma"], workers["n"]))
    return lines


# ---------------------------------------------------------------------------
# guard: refuse inputs outside what the series showed
# ---------------------------------------------------------------------------

def build_profile(runs: list) -> dict:
    stores, shelves, templates = set(), set(), set()
    max_weight, max_qty = 0.0, 0
    for run in runs:
        templates.add(normalize_brief(run["brief"]))
        inp = run.get("input", {})
        if isinstance(inp, dict):
            if inp.get("store") in STORES:
                stores.add(inp["store"])
            if inp.get("shelf") in SHELVES:
                shelves.add(inp["shelf"])
            items = inp.get("items")
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    weight = item.get("weight")
                    qty = item.get("qty")
                    if _is_num(weight) and weight > max_weight:
                        max_weight = float(weight)
                    if (isinstance(qty, int) and not isinstance(qty, bool)
                            and qty > max_qty):
                        max_qty = qty
    return {"stores": sorted(stores), "shelves": sorted(shelves),
            "templates": sorted(templates),
            "max_weight": max_weight, "max_qty": max_qty}


def guard_check(profile: dict, brief: str, inp) -> tuple:
    """Return (allowed, reason, output_or_None)."""
    if normalize_brief(brief) not in profile["templates"]:
        return False, "REFUSED unknown-brief -> handoff-to-person", None
    if not isinstance(inp, dict) or tuple(sorted(inp)) != TOP_KEYS:
        return False, "REFUSED new-schema -> handoff-to-person", None
    if inp["store"] not in profile["stores"]:
        return (False, 'REFUSED new-slot-value store="%s" not-in-series '
                "-> handoff-to-person" % inp["store"], None)
    if inp["shelf"] not in profile["shelves"]:
        return (False, 'REFUSED new-slot-value shelf="%s" not-in-series '
                "-> handoff-to-person" % inp["shelf"], None)
    if not isinstance(inp["date"], str) or not DATE_FMT.match(inp["date"]):
        return False, "REFUSED bad-slot date -> handoff-to-person", None
    if not isinstance(inp["shipment"], str) or not SHIP_FMT.match(inp["shipment"]):
        return False, "REFUSED bad-slot shipment -> handoff-to-person", None
    items = inp["items"]
    if not isinstance(items, list) or not items:
        return False, "REFUSED corrupted-input items -> handoff-to-person", None
    for item in items:
        if not isinstance(item, dict) or tuple(sorted(item)) != ITEM_KEYS:
            return False, "REFUSED new-schema item-keys -> handoff-to-person", None
        if not isinstance(item["sku"], str) or not SKU_FMT.match(item["sku"]):
            return False, "REFUSED bad-slot sku -> handoff-to-person", None
        weight = item["weight"]
        qty = item["qty"]
        if not _is_num(weight):
            return (False, "REFUSED corrupted-input weight=%r "
                    "-> handoff-to-person" % (weight,), None)
        if not isinstance(qty, int) or isinstance(qty, bool):
            return (False, "REFUSED corrupted-input qty=%r "
                    "-> handoff-to-person" % (qty,), None)
        if weight <= 0 or qty < 1:
            return (False, "REFUSED corrupted-input non-positive "
                    "-> handoff-to-person", None)
        if float(weight) > profile["max_weight"]:
            return (False, "REFUSED out-of-range weight=%s -> handoff-to-person"
                    % weight, None)
        if qty > profile["max_qty"]:
            return (False, "REFUSED out-of-range qty=%s -> handoff-to-person"
                    % qty, None)
    try:
        produced = candidate_script(brief, inp)
    except ValueError as exc:
        return False, "REFUSED %s -> handoff-to-person" % exc, None
    return True, "ALLOWED %s" % canon(produced), produced


# ---------------------------------------------------------------------------
# demo: one command, one table
# ---------------------------------------------------------------------------

TITLE = ("SYNTHETIC repeated-task-series to checked-script demo "
         "(SYNTHETIC DATA ONLY)")
FOOTER = ("SYNTHETIC DATA ONLY: invented stores, shipments and weights; "
          "no claim about any real workload.")


def demo_rows(root: str) -> list:
    paths = gen_all(root)
    rows = []
    runs_a = read_runs(paths["a"])
    series_a, _, _ = detect_series(runs_a)
    rows.append(("a", "detect",
                 'SERIES count=%d template="%s"'
                 % (series_a[0][1], series_a[0][0])))
    comp_a = shadow_compare(runs_a)
    rows.append(("a", "shadow-script",
                 "matched=%d mismatched=%d"
                 % (len(comp_a["matched"]), len(comp_a["mismatched"]))))
    rows.append(("a", "copy-previous",
                 "matched=%d/%d control: repeat last output"
                 % (comp_a["copy_prev_matched"], comp_a["copy_prev_total"])))
    runs_b = read_runs(paths["b"])
    series_b, _, _ = detect_series(runs_b)
    rows.append(("b", "detect",
                 'SERIES count=%d template="%s"'
                 % (series_b[0][1], series_b[0][0])))
    comp_b = shadow_compare(runs_b)
    rows.append(("b", "shadow-script",
                 "matched=%d mismatched=%d mismatch-block=runs-%03d-to-%03d "
                 "method-changed-after-run-20"
                 % (len(comp_b["matched"]), len(comp_b["mismatched"]),
                    min(comp_b["mismatched"]), max(comp_b["mismatched"]))))
    rows.append(("b", "copy-previous",
                 "matched=%d/%d control: repeat last output"
                 % (comp_b["copy_prev_matched"], comp_b["copy_prev_total"])))
    runs_c = read_runs(paths["c"])
    _series_c, briefs_c, max_c = detect_series(runs_c)
    rows.append(("c", "detect",
                 "NO-SERIES briefs=%d max-group=%d need>=%d"
                 % (briefs_c, max_c, MIN_SERIES)))
    rows.append(("c", "shadow-script", "SKIPPED no-series"))
    runs_d = read_runs(paths["d"])
    series_d, _, _ = detect_series(runs_d)
    rows.append(("d", "detect",
                 'SERIES count=%d template="%s"'
                 % (series_d[0][1], series_d[0][0])))
    comp_d = shadow_compare(runs_d)
    rows.append(("d", "shadow-script",
                 "matched=%d corrupted=%d corrupted-run=%03d"
                 % (len(comp_d["matched"]), len(comp_d["corrupted"]),
                    comp_d["corrupted"][0])))
    profile = build_profile(runs_a)
    bad_run = [run for run in runs_d if run["id"] == D_CORRUPT_RUN][0]
    _ok, reason, _out = guard_check(profile, bad_run["brief"],
                                    bad_run["input"])
    rows.append(("d", "guard-corrupted", reason))
    runs_e = read_runs(paths["e"])
    series_e, _, _ = detect_series(runs_e)
    rows.append(("e", "detect",
                 'SERIES count=%d template="%s"'
                 % (series_e[0][1], series_e[0][0])))
    workers = shadow_workers(runs_e)
    rows.append(("e", "shadow-script",
                 "vs-alpha=%d/%d vs-beta=%d/%d vs-gamma=%d/%d "
                 "matches-one-worker-only"
                 % (workers["script_vs_worker_alpha"], workers["n"],
                    workers["script_vs_worker_beta"], workers["n"],
                    workers["script_vs_worker_gamma"], workers["n"])))
    rows.append(("e", "worker-agree",
                 "alpha-beta=%d/%d alpha-gamma=%d/%d beta-gamma=%d/%d"
                 % (workers["agree_worker_alpha_worker_beta"], workers["n"],
                    workers["agree_worker_alpha_worker_gamma"], workers["n"],
                    workers["agree_worker_beta_worker_gamma"], workers["n"])))
    good = json.loads(canon(runs_a[0]["input"]))
    _ok, reason, _out = guard_check(profile, runs_a[0]["brief"], good)
    rows.append(("guard", "valid-input", reason))
    novel_schema = json.loads(canon(good))
    novel_schema["priority"] = "high"
    _ok, reason, _out = guard_check(profile, runs_a[0]["brief"], novel_schema)
    rows.append(("guard", "new-schema", reason))
    novel_value = json.loads(canon(good))
    novel_value["store"] = "WH-99"
    _ok, reason, _out = guard_check(profile, runs_a[0]["brief"], novel_value)
    rows.append(("guard", "new-slot-value", reason))
    return rows


def render_table(rows: list) -> str:
    lines = [TITLE,
             "dataset | check           | outcome",
             "--------+-----------------+--------"]
    for dataset, check, outcome in rows:
        lines.append("%-7s | %-15s | %s" % (dataset, check, outcome))
    lines.append(FOOTER)
    return "\n".join(lines) + "\n"


def run_demo() -> str:
    tmp_dir = tempfile.mkdtemp(prefix="series-compile-demo-")
    try:
        return render_table(demo_rows(tmp_dir))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synthetic repeated-task-series to checked-script demo.")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("gen", help="write synthetic datasets a/b/c/d/e")
    gen.add_argument("--out", default=None,
                     help="output directory (default: fresh temp dir)")
    det = sub.add_parser("detect", help="group briefs into series")
    det.add_argument("data_dir", help="directory holding run-*.json files")
    sha = sub.add_parser("shadow", help="candidate script vs recorded outputs")
    sha.add_argument("data_dir", help="directory holding run-*.json files")
    gua = sub.add_parser("guard", help="check one input against a series")
    gua.add_argument("--series", required=True,
                     help="directory holding run-*.json files")
    gua.add_argument("--input", required=True,
                     help='JSON file {"brief": ..., "input": {...}}')
    sub.add_parser("demo", help="run gen/detect/shadow/guard, print one table")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "gen":
        out = args.out or tempfile.mkdtemp(prefix="series-compile-gen-")
        os.makedirs(out, exist_ok=True)
        paths = gen_all(out)
        counts = sorted((name, len(read_runs(path)))
                        for name, path in paths.items())
        sys.stdout.write("wrote %s to %s\n"
                         % (" ".join("%s=%d" % item for item in counts), out))
        return 0
    if args.command == "detect":
        for line in format_detect(args.data_dir):
            sys.stdout.write(line + "\n")
        return 0
    if args.command == "shadow":
        for line in format_shadow(args.data_dir):
            sys.stdout.write(line + "\n")
        return 0
    if args.command == "guard":
        with open(args.input, encoding="utf-8") as handle:
            payload = json.load(handle)
        profile = build_profile(read_runs(args.series))
        _ok, reason, _out = guard_check(profile, payload["brief"],
                                        payload["input"])
        sys.stdout.write(reason + "\n")
        return 0
    if args.command == "demo":
        sys.stdout.write(run_demo())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
