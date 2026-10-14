#!/usr/bin/env python3
"""Assemble a disposable C2-10M bench runtime (producer + serving overlay).

The shipped query stack is NOT `c10m/producer` alone (its serving files
are pre-repair bytes) and NOT `c10m/serving` alone (7 files, no product
tree). The runnable stack is the producer tree with the 7-file serving
overlay applied on top — the same assembly `demos/demo_c10m_narrow.py`
uses. This script builds that assembly into a disposable directory and
verifies every overlaid byte against the pinned serving hashes, failing
closed on any mismatch.

Layout written (mirrors the historical lane `tree/` copy):

    <runtime>/tl-sys/              from c10m/producer/tl-sys
    <runtime>/tl-candidate-batch/  from c10m/producer/tl-candidate-batch
    <runtime>/tl-sys/tlsys/<7 serving files>  overlaid from c10m/serving

Point `TRACE_ARCHITECTURE_DIR` (or the keyed `--config`
`architecture_dir`) at the printed directory. Stdlib only.

Usage:
    python benchmarks/evidence/live/assemble_runtime.py [--out DIR]
    # RUNTIME <dir>   (persists until the caller deletes it)
"""

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
C10M = REPO / "c10m"

# Pinned shipped serving bytes (c10m/README.md table; same pins the demo
# and the BENCH10M RUN.json implementation_identity blocks authenticate).
SERVING_PINS = {
    "tl-sys/tlsys/dossier.py": "93871fb3e7f63e58d9c48c113efecd551a5271c73184968259f8cce3df4e7ac0",
    "tl-sys/tlsys/relquery.py": "0fe79c501cf3582face656ff3da7340534ae871780f4e16c7e0f876f6afb45a8",
    "tl-sys/tlsys/relserve.py": "61b69a84c648717955426e3bbb3ffde7526658483f05a7532f9d145582bc9b71",
    "tl-sys/tlsys/query.py": "d7756e72e2de65814103e216edfc7d53650cc0fada34cefe7cf41411f03414ce",
    "tl-sys/tlsys/index.py": "b8bc139008a9da185f3438823836e03b8a171a10d0677faf7448ed21afcebef0",
    "tl-sys/tlsys/serving/generation.py": "929709390af18e7511197164d399ba71f368c767c2fc2df3680f43254424b22f",
    "tl-sys/tlsys/prodstate.py": "e7a4370c3e6faf122927db34919b2d42838f0b800edc4c8f877b564f405a47b1",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(msg):
    print(f"ASSEMBLE FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def assemble(out=None):
    """Build the runtime; return its path. Fails closed on any bad byte."""
    for need in ("producer/tl-sys", "producer/tl-candidate-batch", "serving"):
        if not (C10M / need).is_dir():
            fail(f"c10m/{need} missing (run from the repo root)")
    rt = Path(out) if out else Path(tempfile.mkdtemp(prefix="c10m_bench_runtime_"))
    if out and rt.exists() and any(rt.iterdir()):
        fail(f"--out {rt} exists and is not empty (refusing to mix trees)")
    rt.mkdir(parents=True, exist_ok=True)
    shutil.copytree(C10M / "producer" / "tl-sys", rt / "tl-sys",
                    dirs_exist_ok=True)
    shutil.copytree(C10M / "producer" / "tl-candidate-batch",
                    rt / "tl-candidate-batch", dirs_exist_ok=True)
    overlaid = sorted((C10M / "serving").rglob("*.py"))
    if len(overlaid) != 7:
        fail(f"expected 7 serving overlay files, found {len(overlaid)}")
    for src in overlaid:
        dst = rt / src.relative_to(C10M / "serving")
        shutil.copy2(src, dst)
    # Verify the ASSEMBLED bytes (not just the sources): the overlay must
    # have landed, and every serving file must equal its pinned ship byte.
    bad = []
    for rel, want in SERVING_PINS.items():
        got = sha256_file(rt / rel)
        if got != want:
            bad.append(f"{rel}: got {got[:16]}... want {want[:16]}...")
    if bad:
        raise SystemExit(f"ASSEMBLE FAIL: serving bytes mismatch: {bad}")
    if not (rt / "tl-sys" / "tlsys").is_dir():
        fail("assembled runtime has no tl-sys/tlsys (adapter discovery "
             "would fail)")
    return rt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=None,
                    help="runtime directory (default: fresh mkdtemp)")
    args = ap.parse_args(argv)
    rt = assemble(args.out)
    print(f"RUNTIME {rt}")
    print("SERVING-OVERLAY 7/7 pinned bytes verified "
          "(dossier/relquery/relserve/query/index/generation/prodstate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
