#!/usr/bin/env python3
"""Bounded pinned-weight acquisition + cache validation (MiniLM-L6-v2).

The A1/A2 bench arms load `sentence-transformers/all-MiniLM-L6-v2` at
the pinned revision and run with `HF_HUB_OFFLINE=1`, which gives NO
recovery when the revision is absent from the local cache. Run this
script BEFORE any offline run: it downloads exactly the pinned
snapshot (bounded: one repo, one revision, ~90 MB) and then validates
that the snapshot is complete and loadable offline.

Usage:
    # one-time acquisition (needs network to huggingface.co):
    HF_HOME=/tmp/c2-weights python benchmarks/evidence/live/fetch_weights.py
    # WEIGHTS OK <snapshot-dir>

    # offline validation only (no network):
    HF_HOME=/tmp/c2-weights HF_HUB_OFFLINE=1 \\
        python benchmarks/evidence/live/fetch_weights.py --check-only
"""

import argparse
import os
import sys
from pathlib import Path

REPO_ID = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

# Files SentenceTransformer must resolve offline for this repo.
REQUIRED_FILES = ("config.json", "modules.json")


def fail(msg):
    print(f"WEIGHTS FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def cache_root():
    home = os.environ.get("HF_HOME")
    if home:
        return Path(home).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "huggingface"


def snapshot_dir():
    slug = "models--" + REPO_ID.replace("/", "--")
    return cache_root() / "hub" / slug / "snapshots" / REVISION


def validate():
    snap = snapshot_dir()
    if not snap.is_dir():
        fail(f"pinned snapshot absent: {snap} "
             f"(repo {REPO_ID} rev {REVISION[:12]}...). "
             f"Run without --check-only (network) to acquire it, with "
             f"the same HF_HOME the bench run will use.")
    missing = [name for name in REQUIRED_FILES
               if not (snap / name).is_file()]
    if missing:
        fail(f"snapshot {snap} incomplete, missing {missing} "
             f"(re-run acquisition without --check-only)")
    blobs = list((snap.parent.parent / "blobs").glob("*")) \
        if (snap.parent.parent / "blobs").is_dir() else []
    if not blobs:
        fail(f"snapshot {snap} has no cached blobs (empty download?)")
    if not (snap / "model.safetensors").is_file():
        cands = sorted(p.name for p in snap.glob("*.bin")) + \
            sorted(p.name for p in snap.glob("*.safetensors"))
        if not cands:
            fail(f"snapshot {snap} has no weight file "
                 f"(*.safetensors/*.bin)")
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=REPO_ID)
    ap.add_argument("--rev", default=REVISION)
    ap.add_argument("--check-only", action="store_true",
                    help="validate the local cache only (no network)")
    args = ap.parse_args(argv)
    if args.repo != REPO_ID or args.rev != REVISION:
        fail("this wrapper pins repo+rev to the bench record; refusing "
             f"non-pinned {args.repo}@{args.rev[:12]}...")
    if not args.check_only:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            fail("huggingface_hub is not installed (it ships with "
                 "sentence-transformers; see ../pins/PINS.md)")
        snapshot_download(args.repo, revision=args.rev)
    snap = validate()
    print(f"WEIGHTS OK {snap}")
    print(f"repo={args.repo} rev={args.rev} "
          f"required={','.join(REQUIRED_FILES)} present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
