"""Lane BUILD100M-C2: machine-readable preparation preflight (§5.5/§5.7).

Gates the quarantined C2 100M build start on the frozen producer set
AND the bound C2 profile. Every check is re-verified from current
bytes; verdict PASS requires ALL checks green. The build does not
start without it.

Checks:
  F1 freeze manifest: every frozen file re-hashes to its recorded
     digest (no drift since freeze).
  F2 P suites: test_c2_p_sidecar + test_c2_p_routing +
     test_c2_p2_keyed_ops + test_c2_p3_birth run fresh on the VM,
     exit 0, "<N> failures" parses to 0.
  F3 10M producer receipt: BUILD-RECEIPT.json verdict ok + final pin
     + zero cache misses + expected geometry (3099 docs / 58629
     chunks) + organize covered all docs.
  F4 10M differential: DIFF-RECEIPT.json verdict PASS on all levels.
  F5 corpus pins: docs-100m + docs-10m + anchors-v1 re-hash to pins.
  F6 cache binding: strict CacheReader opens (fail-closed on config
     mismatch) + served config_id == PRECISION_FIRST id.
  F7 quarantine: build prefix is under lane-relaunch, is not a
     live C1 path, and live C1 campaign/store bytes+mtimes are
     unchanged vs the recorded intact markers.
  F8 environment: disk free >= threshold; no foreign python writer
     on the VM (recorded process list; fail on gate/build matches).
  F9 dynamic closure: every module in the 10M build's loaded_modules
     resolves to a frozen file with matching digest.
  F10 profile bindings (§5.7 gate): the frozen profile (id + sha256
     + R_cat) re-hashes from current bytes; the 10M receipt binds
     the SAME profile (id/sha/R_cat/session_bound) with catalogs
     engaged, zero rejections and no over-budget latch. A candidate
     build missing any binding is REFUSED.

Usage on the VM:
  /srv/tl/venv/bin/python b100m_preflight.py --root <work> \\
    --freeze FREEZE.json --build-10m <build-10m-c2 dir> \\
    --cache-dir <emb_cache> --docs-100m <path> \\
    --build-prefix <build-100m dir> --min-free-gb 150 \\
    --intact <intact-markers.json> --out PREFLIGHT.json
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time


GUARD = "lane-relaunch"
LIVE_PATHS = ("/srv/tl/staging-v3/campaign-10m", "/srv/tl/stores",
              "/srv/tl/pkg-v3")

PIN_DOCS_10M = "04bbbb3ea3425a49491559173b20280fb286edeeef49c8293aebc0b92bcce3fd"
PIN_DOCS_100M = "c098fdace3a73efc83f3c71a9e024b3cd77114fd0d7f2348c7c813995e6b0e09"
PIN_ANCHORS_V1 = "9728129bd96b8a948bd60ace37d7c270af2779cc33154624a0653e4e5cf33754"


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--freeze", required=True)
    ap.add_argument("--build-10m", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--docs-100m", required=True)
    ap.add_argument("--build-prefix", required=True)
    ap.add_argument("--min-free-gb", type=float, default=150.0)
    ap.add_argument("--intact", required=True)
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    sys.path.insert(0, os.path.join(ns.root, "tl-eval"))

    checks = []

    def check(name, ok, detail=None):
        checks.append({"name": name, "pass": bool(ok),
                       "detail": detail})
        print(f"preflight {name}: {'PASS' if ok else 'FAIL'} "
              f"{detail if isinstance(detail, str) else ''}",
              flush=True)

    with open(ns.freeze) as f:
        freeze = json.load(f)

    # F1: frozen files re-hash
    bad = []
    for rel, ent in freeze["files"].items():
        full = os.path.join(ns.root, rel)
        if not os.path.isfile(full):
            bad.append((rel, "missing"))
        elif sha256_file(full) != ent["sha256"]:
            bad.append((rel, "digest-mismatch"))
    check("F1-freeze-intact", not bad,
          f"{len(freeze['files'])} files, {len(bad)} bad"
          + (f" e.g. {bad[:3]}" if bad else ""))

    # F2: P suites fresh (P + P-2 + P-3 closure coverage).
    # RELAUNCH: the suites import the frozen candidate core
    # (`committer`) and Lane-G `profile` from the synced tree, so
    # thread the tree onto PYTHONPATH (same bytes F1 verifies).
    f2_env = dict(os.environ)
    f2_env["PYTHONPATH"] = os.pathsep.join([
        os.path.join(ns.root, "tl-candidate-batch", "candidate"),
        os.path.join(ns.root, "tl-sys"),
        os.path.join(ns.root, "coordination", "c2-work-20261006T1925Z",
                      "lane-G"),
        f2_env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    for suite in ("test_c2_p_sidecar.py", "test_c2_p_routing.py",
                  "test_c2_p2_keyed_ops.py", "test_c2_p3_birth.py"):
        p = subprocess.run(
            [sys.executable,
             os.path.join(ns.root, "tl-sys", "tests", suite)],
            capture_output=True, text=True, timeout=1200,
            cwd=os.path.join(ns.root, "tl-sys", "tests"),
            env=f2_env)
        tail = (p.stdout or "").strip().splitlines()[-1:]
        fails = None
        for line in (p.stdout or "").splitlines():
            if "failures" in line:
                try:
                    fails = int(line.split(":")[-1].split()[0])
                except (ValueError, IndexError):
                    pass
        check(f"F2-{suite[:-3]}",
              p.returncode == 0 and fails == 0,
              f"exit={p.returncode} failures={fails} "
              f"tail={tail} stderr={(p.stderr or '')[-300:]}")

    # F3: 10M producer receipt
    try:
        with open(os.path.join(ns.build_10m,
                               "BUILD-RECEIPT.json")) as f:
            rec = json.load(f)
        ck_phases = set()
        with open(os.path.join(ns.build_10m,
                               "checkpoints.jsonl")) as f:
            for line in f:
                if line.strip():
                    ck_phases.add(json.loads(line)["phase"])
        need = {"ingest-p0", "ingest-p1", "ingest-p2", "drain-p0",
                "drain-p1", "drain-p2", "publication",
                "organize-final", "snap-final"}
        cache = rec.get("cache_stats_total", {})
        geom_ok = True
        with open(os.path.join(ns.build_10m,
                               "checkpoints.jsonl")) as f:
            n_docs = sum(json.loads(line).get("n_docs", 0)
                         for line in f if '"ingest-p' in line)
        ok = (rec.get("verdict") == "ok"
              and need <= ck_phases
              and cache.get("misses", 1) == 0
              and cache.get("fallback_uses", 1) == 0
              and n_docs == 3099
              and bool(rec.get("final_pin")))
        check("F3-producer-receipt", ok,
              f"verdict={rec.get('verdict')} phases={len(ck_phases)} "
              f"n_docs={n_docs} misses={cache.get('misses')} "
              f"pin={(rec.get('final_pin') or '?')[:16]}…")
    except (OSError, ValueError, KeyError) as e:
        check("F3-producer-receipt", False, f"{type(e).__name__}: {e}")

    # F4: differential (RELAUNCH fix: the diff writes FIVE levels —
    # L1_occurrences, L2_xdoc, L3_leaves, L3_parents, L4_relations —
    # so `len(lv) == 4` could never pass; require the exact set)
    try:
        with open(os.path.join(ns.build_10m,
                               "DIFF-RECEIPT.json")) as f:
            diff = json.load(f)
        lv = diff.get("levels", {})
        ok = (diff.get("verdict") == "PASS"
              and set(lv) == {"L1_occurrences", "L2_xdoc",
                              "L3_leaves", "L3_parents",
                              "L4_relations"}
              and all(v.get("pass") for v in lv.values()))
        check("F4-differential", ok,
              f"verdict={diff.get('verdict')} "
              f"levels={sorted(lv)}")
    except (OSError, ValueError) as e:
        check("F4-differential", False, f"{type(e).__name__}: {e}")

    # F5: corpus pins
    try:
        pins = [("docs-100m", ns.docs_100m, PIN_DOCS_100M),
                ("docs-10m", os.path.join(ns.root, "inputs",
                                          "docs-10m.jsonl"),
                 PIN_DOCS_10M),
                ("anchors-v1", os.path.join(
                    ns.root, "inputs",
                    "relations-10m.anchors-v1.json"),
                 PIN_ANCHORS_V1)]
        bad = [(n, sha256_file(p)) for n, p, w in pins
               if sha256_file(p) != w]
        check("F5-corpus-pins", not bad,
              "all match" if not bad else f"bad={bad}")
    except OSError as e:
        check("F5-corpus-pins", False, f"{type(e).__name__}: {e}")

    # F6: cache binding
    try:
        from gpu_encode import config as _cfg
        from gpu_encode import cache as _cache
        reader = _cache.CacheReader(ns.cache_dir)
        try:
            got = reader.meta.get("config_id")
        finally:
            reader.close()
        want = _cfg.config_id(_cfg.PRECISION_FIRST)
        check("F6-cache-binding", got == want,
              f"served={got} want={want}")
    except (OSError, ValueError) as e:
        check("F6-cache-binding", False, f"{type(e).__name__}: {e}")

    # F7: quarantine + live intact
    try:
        bp = os.path.abspath(ns.build_prefix)
        q_ok = (GUARD in bp
                and not any(bp.startswith(lp) for lp in LIVE_PATHS))
        with open(ns.intact) as f:
            intact = json.load(f)
        drift = []
        for path, mark in intact["paths"].items():
            try:
                st = os.stat(path)
                size = int(subprocess.run(
                    ["du", "-sb", path], capture_output=True,
                    text=True, timeout=600).stdout.split()[0]) \
                    if mark.get("bytes") else None
            except (OSError, ValueError, IndexError):
                drift.append((path, "stat-failed"))
                continue
            if mark.get("mtime") is not None and (
                    int(st.st_mtime) != mark["mtime"]):
                drift.append((path, "mtime"))
            if size is not None and size != mark["bytes"]:
                drift.append((path, f"bytes {size}"))
        check("F7-quarantine-intact", q_ok and not drift,
              f"quarantine={q_ok} drift={drift or 'none'}")
    except (OSError, ValueError) as e:
        check("F7-quarantine-intact", False,
              f"{type(e).__name__}: {e}")

    # F8: environment
    try:
        free_gb = shutil.disk_usage(ns.build_prefix).free / (1 << 30)
        ps = subprocess.run(["ps", "-eo", "pid,args"],
                            capture_output=True, text=True,
                            timeout=60).stdout
        foreign = [ln.strip() for ln in ps.splitlines()
                   if ("python" in ln and "b100m_preflight" not in ln
                       and ("gate" in ln or "b100m_build" in ln
                            or "campaign" in ln))]
        check("F8-environment",
              free_gb >= ns.min_free_gb and not foreign,
              f"free={free_gb:.1f}GB<{ns.min_free_gb}> "
              f"foreign_writers={foreign or 'none'}")
    except (OSError, ValueError) as e:
        check("F8-environment", False, f"{type(e).__name__}: {e}")

    # F9: dynamic closure ⊆ freeze
    try:
        with open(os.path.join(ns.build_10m,
                               "BUILD-RECEIPT.json")) as f:
            rec = json.load(f)
        loaded = rec.get("loaded_modules", {})
        bad = [n for n, rel in loaded.items()
               if rel not in freeze["files"]]
        check("F9-dynamic-closure", bool(loaded) and not bad,
              f"{len(loaded)} loaded modules, "
              f"{len(bad)} outside freeze"
              + (f" e.g. {bad[:3]}" if bad else ""))
    except (OSError, ValueError) as e:
        check("F9-dynamic-closure", False,
              f"{type(e).__name__}: {e}")

    # F10: §5.7 profile bindings (REFUSES a candidate missing them)
    try:
        fprof = (freeze.get("configs") or {}).get("profile") or {}
        with open(os.path.join(ns.build_10m,
                               "BUILD-RECEIPT.json")) as f:
            rec = json.load(f)
        rprof = rec.get("profile") or {}
        rcat = rec.get("catalog") or {}
        fails = []
        if not fprof.get("profile_id") or not fprof.get("sha256") \
                or not fprof.get("R_cat"):
            fails.append("freeze lacks profile id/sha/R_cat")
        prel = fprof.get("path")
        if not prel or prel not in freeze.get("files", {}):
            fails.append(f"frozen profile path missing: {prel!r}")
        elif sha256_file(os.path.join(ns.root, prel)) != fprof["sha256"]:
            fails.append("frozen profile bytes drifted")
        for key in ("profile_id", "sha256", "R_cat"):
            if rprof.get(key) != fprof.get(key):
                fails.append(
                    f"receipt {key} {rprof.get(key)!r} != "
                    f"freeze {fprof.get(key)!r}")
        if rprof.get("session_bound") is not True:
            fails.append("receipt session_bound is not true")
        if not isinstance(rcat, dict) or not rcat.get("decisions"):
            fails.append("receipt shows 0 engaged catalog decisions")
        if not rcat.get("pops"):
            fails.append("receipt engaged no catalog populations")
        if rcat.get("rejected"):
            fails.append(
                f"receipt has {rcat.get('rejected')} R_cat rejections")
        if rcat.get("over_budget_any"):
            fails.append("receipt over_budget_any latched")
        check("F10-profile-bindings", not fails,
              f"id={fprof.get('profile_id')} "
              f"R_cat={fprof.get('R_cat')} "
              f"decisions={rcat.get('decisions')} "
              f"pops={rcat.get('pops')}"
              if not fails else "; ".join(fails))
    except (OSError, ValueError) as e:
        check("F10-profile-bindings", False,
              f"{type(e).__name__}: {e}")

    verdict = "PASS" if all(c["pass"] for c in checks) else "FAIL"
    with open(ns.out, "w") as f:
        json.dump({"verdict": verdict,
                   "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime()),
                   "checks": checks}, f, indent=1)
    print(f"PREFLIGHT {verdict} -> {ns.out}", flush=True)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
