"""Lane BUILD100M-C2: freeze the COMPLETE transitive producer set (§5.5/§5.7).

The freeze is the full synced-tree manifest (every file hash — a
superset by construction, never a hand-picked subset) plus config
hashes (INCLUDING the bound C2 profile identity: id + sha256 +
R_cat), corpus hashes, and cache bindings, plus the dynamic loaded-
module closure recorded by the 10M build receipt (merged when given).

Usage on the VM:
  python3 b100m_freeze.py --root /srv/tl/lane-relaunch/work \\
      --docs-10m <path> --docs-100m <path> --anchors-v1 <path> \\
      --relations-10m <path> --cache-dir <emb_cache> \\
      --profile <work>/inputs/c2-profile-100m.json \\
      --build-receipt <build-10m-c2/BUILD-RECEIPT.json> --out FREEZE.json

Refuses (exit 2) when any named corpus/input file is missing OR the
profile is missing/unparseable (§5.7: no profile-free freeze). Hash
mismatches against expected pins are RECORDED, not refused here —
the preflight gate disposes them.
"""
import argparse
import hashlib
import json
import os
import sys


EXPECTED = {
    "docs_10m": "04bbbb3ea3425a49491559173b20280fb286edeeef49c8293aebc0b92bcce3fd",
    "docs_100m": "c098fdace3a73efc83f3c71a9e024b3cd77114fd0d7f2348c7c813995e6b0e09",
    "anchors_v1": "9728129bd96b8a948bd60ace37d7c270af2779cc33154624a0653e4e5cf33754",
}

SKIP_DIRS = {"__pycache__", ".venv", "node_modules"}
SKIP_SUFFIX = {".pyc", ".pyo"}


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def tree_manifest(root):
    files = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        dirnames.sort()
        for fn in sorted(filenames):
            if os.path.splitext(fn)[1] in SKIP_SUFFIX:
                continue
            full = os.path.join(dirpath, fn)
            if not os.path.isfile(full) or os.path.islink(full):
                continue
            rel = os.path.relpath(full, root)
            files[rel] = {
                "sha256": sha256_file(full),
                "bytes": os.path.getsize(full),
            }
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--docs-10m", required=True)
    ap.add_argument("--docs-100m", required=True)
    ap.add_argument("--anchors-v1", required=True)
    ap.add_argument("--relations-10m", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--profile", required=True,
                    help="bound C2 profile JSON (must live under --root)")
    ap.add_argument("--build-receipt", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="c2-b100m-producer-freeze-001")
    ns = ap.parse_args()

    missing = [p for p in (ns.docs_10m, ns.docs_100m, ns.anchors_v1,
                           ns.relations_10m, ns.profile)
               if not os.path.isfile(p)]
    if missing:
        print(f"freeze refused: missing inputs: {missing}", flush=True)
        return 2
    prof_abs = os.path.abspath(ns.profile)
    root_abs = os.path.abspath(ns.root)
    if not prof_abs.startswith(root_abs + os.sep):
        print("freeze refused: --profile is not under --root", flush=True)
        return 2
    try:
        with open(ns.profile) as f:
            prof = json.load(f)
        prof_id = prof["profile_id"]
        prof_rcat = prof["derived_limits"]["R_cat"]
        prof_cal = prof["calibration_manifest_id"]
        routing = prof["flags"]["organization_catalog_routing"]
    except (ValueError, KeyError, TypeError) as e:
        print(f"freeze refused: profile unparseable: {e}", flush=True)
        return 2
    if routing is not True:
        print("freeze refused: profile does not enable catalog routing",
              flush=True)
        return 2
    prof_rel = os.path.relpath(prof_abs, root_abs)
    prof_sha = sha256_file(prof_abs)
    if not os.path.isdir(ns.cache_dir):
        print(f"freeze refused: cache dir missing: {ns.cache_dir}",
              flush=True)
        return 2

    sys.path.insert(0, os.path.join(ns.root, "tl-eval"))
    from gpu_encode import config as cfg
    from gpu_encode import cache as cache_mod
    reader = cache_mod.CacheReader(ns.cache_dir)
    try:
        cache_meta = dict(reader.meta or {})
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            close()

    files = tree_manifest(ns.root)
    corpus = {}
    for key, path in (("docs_10m", ns.docs_10m),
                      ("docs_100m", ns.docs_100m),
                      ("anchors_v1", ns.anchors_v1),
                      ("relations_10m", ns.relations_10m)):
        digest = sha256_file(path)
        corpus[key] = {
            "path": path,
            "sha256": digest,
            "bytes": os.path.getsize(path),
            "pin_match": (EXPECTED.get(key) == digest
                          if key in EXPECTED else None),
        }
    configs = {
        "profile": {"profile_id": prof_id,
                    "sha256": prof_sha,
                    "R_cat": prof_rcat,
                    "calibration_manifest_id": prof_cal,
                    "path": prof_rel},
        "profile_note": "C2 catalog organization (§5.7); "
                        "reference (None) is refused",
        "place_xdoc": True,
        "place_budget": None,
        "drain_budget": 2,
        "keyed_state": True,
        "session": "tlsys.prodstate.ProducerSession(profile), "
                   "one shared instance per build; profile threaded "
                   "through every ingest/drain/organize call; "
                   "bind_candidate_store once after first commit "
                   "(c2-keyed-1); ONE explicit export_manifest_archive "
                   "per completed bulk prefix (+ final boundary "
                   "archive in 10m mode), each cost separately "
                   "checkpointed",
        "store_id": "gate-full",
        "extractor_cfg": {"extractor": "gate-runner-v1", "window": 1,
                          "model": "none", "rules": ["gate-confirmation"]},
        "chunk_geometry": {"tokens": 200, "overlap": 50},
        "encoder": {
            "model": cfg.MODEL_ID,
            "revision": cfg.MODEL_REVISION,
            "precision_first": cfg.PRECISION_FIRST,
            "config_id": cfg.config_id(cfg.PRECISION_FIRST),
        },
        "cache_served": {
            "config_id": cache_meta.get("config_id"),
            "meta_keys": sorted(cache_meta.keys()),
        },
        "env": {
            "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED"),
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
        },
    }
    dynamic = None
    if ns.build_receipt:
        with open(ns.build_receipt) as f:
            rec = json.load(f)
        dynamic = rec.get("loaded_modules")

    freeze = {
        "label": ns.label,
        "root": ns.root,
        "n_files": len(files),
        "files": files,
        "configs": configs,
        "corpus": corpus,
        "cache_dir": ns.cache_dir,
        "dynamic_closure": dynamic,
    }
    with open(ns.out, "w") as f:
        json.dump(freeze, f, indent=1, sort_keys=True)
    print(f"freeze wrote {ns.out}: {len(files)} files", flush=True)
    print(f"  profile: {prof_id} {prof_sha[:16]}… "
          f"R_cat={prof_rcat} cal={prof_cal}", flush=True)
    for key, entry in corpus.items():
        print(f"  {key}: {entry['sha256'][:16]}… "
              f"pin_match={entry['pin_match']}", flush=True)
    print(f"  cache served config_id={cache_meta.get('config_id')} "
          f"want={configs['encoder']['config_id']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
