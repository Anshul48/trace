"""Maintained test: defer_manifest_save flag (ingest + organize).

Flag-gated, default OFF. Flag ON skips intermediate full-manifest
dumps and writes the manifest exactly once at call end; committed
ops and final manifest bytes must be identical to flag OFF.
Flag OFF path is untouched. Defer + keyed_state fails closed.

Deterministic (mocked clock/random); scratch stores under /tmp.
Run: python tl-sys/tests/test_defer_manifest.py
"""
import os
import random
import sys
import tempfile
import time

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

import tlsys.ingest as ingest_mod  # noqa: E402
import tlsys.maint as maint_mod  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.maint import organize_segments  # noqa: E402
from tlsys.store_if import TLStore  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def reset_determinism():
    time.time = lambda: 1791720000.0
    random.seed(987654)


DIM = 8


def emb(texts):
    out = []
    for t in texts:
        v = [0.0] * DIM
        v[sum(t.encode()) % DIM] = 1.0
        out.append(v)
    return out


DOCS = [(f"dm-doc-{i}", " ".join(f"term{i}_{j}" for j in range(60)))
        for i in range(12)]


def run_once(defer):
    reset_determinism()
    counts = {"ingest": 0, "maint": 0}
    real_ingest = ingest_mod._save_manifest
    real_maint = maint_mod._save_manifest

    def wrap_ingest(path, manifest):
        counts["ingest"] += 1
        return real_ingest(path, manifest)

    def wrap_maint(path, manifest):
        counts["maint"] += 1
        return real_maint(path, manifest)

    ingest_mod._save_manifest = wrap_ingest
    maint_mod._save_manifest = wrap_maint
    try:
        root = tempfile.mkdtemp(prefix="defer-manifest-")
        tl = TLStore(root, create=True, local_repair=False)
        kw = {"defer_manifest_save": True} if defer else {}
        rep = ingest_docs(tl, DOCS, emb, place_xdoc=False, **kw)
        org = organize_segments(tl, **kw)
        with open(os.path.join(root, "ingest_manifest.json"), "rb") as f:
            manifest_bytes = f.read()
        tl.close()
    finally:
        ingest_mod._save_manifest = real_ingest
        maint_mod._save_manifest = real_maint
    return {"rep": rep, "org": org, "manifest": manifest_bytes,
            "counts": counts}


off = run_once(False)
on = run_once(True)

check("off-saves-multiple",
      off["counts"]["ingest"] > 1 and off["counts"]["maint"] > 1,
      f"{off['counts']}")
check("on-ingest-single-save", on["counts"]["ingest"] == 1,
      f"{on['counts']}")
check("on-organize-single-save", on["counts"]["maint"] == 1,
      f"{on['counts']}")
check("manifest-bytes-identical", off["manifest"] == on["manifest"],
      f"{len(off['manifest'])} vs {len(on['manifest'])}")
check("ingest-counts-identical",
      (off["rep"]["n_atoms"], off["rep"]["n_holons"])
      == (on["rep"]["n_atoms"], on["rep"]["n_holons"]),
      f"{off['rep']} vs {on['rep']}")
check("organized-identical",
      off["org"]["organized"] == on["org"]["organized"]
      and off["org"]["failed"] == on["org"]["failed"] == {},
      "organized lists differ")

# Fail-closed combinations (raise before any store IO).
for fn, label in ((ingest_docs, "ingest"), (organize_segments, "organize")):
    try:
        fn(None, [], emb, defer_manifest_save=True, keyed_state=True)
        check(f"{label}-keyed-fails-closed", False, "no raise")
    except ValueError:
        check(f"{label}-keyed-fails-closed", True)
    except Exception as e:  # noqa: BLE001
        check(f"{label}-keyed-fails-closed", False, f"wrong error: {e!r}")

print(f"{len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
