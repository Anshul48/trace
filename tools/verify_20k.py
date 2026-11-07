#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One-line verifier for the shipped 20k prefix.

Reads ONLY the shipped bytes (no re-run, no downloads, stdlib only):

  docs/reproduction/repro-20k/MANIFEST.json
  docs/reproduction/repro-20k/pilot-20k-out2/result.json
  docs/explorer/local_20k_data.json
  docs/explorer/data/corpus.js
  docs/explorer/data/replay.js

Prints exactly one line on stdout and exits:

  IDENTICAL          every check matches (exit 0)
  MISMATCH ...       first failing check, named (exit 1)

Checks, in order: tokens, atoms, leaves, parents, manifest, bytes.

  tokens   actual_tokens == 20030 in MANIFEST.json, result.json, local manifest
  atoms    144 in MANIFEST prefix_20k, result.json input+final,
           local manifest.atoms_count and len(local atoms)
  leaves   81 in result.json final, local manifest.leaves_count, len(local leaves)
  parents  51 in result.json final, local manifest.parents_count, len(local parents)
  manifest PASS in MANIFEST verify_local + small_pilot, result.json status,
           local manifest.status
  bytes    sha256 of the three explorer data files equals the pins below

The pins were measured on 2026-11-06; any later edit to these three files
must update them.

Usage:
  python3 tools/verify_20k.py [--root DIR]
"""

import argparse
import hashlib
import json
import os
import sys

EXPECTED_TOKENS = 20030
EXPECTED_ATOMS = 144
EXPECTED_LEAVES = 81
EXPECTED_PARENTS = 51
EXPECTED_STATUS = "PASS"

# Pins for the shipped explorer data files (measured 2026-11-06).
EXPECTED_SHA256 = {
    "docs/explorer/local_20k_data.json":
        "fa010d1cf8ca54b1a0bbe7bb8c40def5d8fefaeac8abe78c5a643c4c47f57c34",
    "docs/explorer/data/corpus.js":
        "991b5dc6720bb0905d36b531d8bd1607843af15efe5bcc4a22d07f21813c3e6e",
    "docs/explorer/data/replay.js":
        "a8d5175452d62a6931cc49e2735e2e7ed8ed883136e47ab814ab3054a244e443",
}

REL_MANIFEST = "docs/reproduction/repro-20k/MANIFEST.json"
REL_RESULT = "docs/reproduction/repro-20k/pilot-20k-out2/result.json"
REL_LOCAL = "docs/explorer/local_20k_data.json"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(root, rel):
    """Return (obj, error). error is a MISMATCH line or None."""
    path = os.path.join(root, rel)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, "MISMATCH input %s: file missing" % rel
    except OSError as exc:
        return None, "MISMATCH input %s: unreadable (%s)" % (rel, exc)
    except ValueError as exc:
        return None, "MISMATCH input %s: invalid JSON (%s)" % (rel, exc)


def get(obj, *keys):
    cur = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None, False
        cur = cur[key]
    return cur, True


def check_eq(check, rel, field, got, want):
    if got != want:
        return "MISMATCH %s %s %s: got %r want %r" % (check, rel, field, got, want)
    return None


def verify(root):
    """Return None when everything matches, else the first MISMATCH line."""
    manifest, err = load_json(root, REL_MANIFEST)
    if err:
        return err
    result, err = load_json(root, REL_RESULT)
    if err:
        return err
    local, err = load_json(root, REL_LOCAL)
    if err:
        return err

    # ---- tokens: 20,030 ----
    for rel, obj, keys in (
        (REL_MANIFEST, manifest, ("prefix_20k", "actual_tokens")),
        (REL_RESULT, result, ("input", "actual_tokens")),
        (REL_LOCAL, local, ("manifest", "actual_tokens")),
    ):
        got, _found = get(obj, *keys)
        bad = check_eq("tokens", rel, ".".join(keys), got, EXPECTED_TOKENS)
        if bad:
            return bad

    # ---- atoms: 144 ----
    atoms_wants = (
        (REL_MANIFEST, manifest, ("prefix_20k", "atoms")),
        (REL_RESULT, result, ("input", "atoms")),
        (REL_RESULT, result, ("final", "atoms")),
        (REL_LOCAL, local, ("manifest", "atoms_count")),
    )
    for rel, obj, keys in atoms_wants:
        got, _found = get(obj, *keys)
        bad = check_eq("atoms", rel, ".".join(keys), got, EXPECTED_ATOMS)
        if bad:
            return bad
    atoms = local.get("atoms")
    bad = check_eq("atoms", REL_LOCAL, "len(atoms)",
                   len(atoms) if isinstance(atoms, list) else atoms, EXPECTED_ATOMS)
    if bad:
        return bad

    # ---- leaves: 81 ----
    leaves_wants = (
        (REL_RESULT, result, ("final", "leaves")),
        (REL_LOCAL, local, ("manifest", "leaves_count")),
    )
    for rel, obj, keys in leaves_wants:
        got, _found = get(obj, *keys)
        bad = check_eq("leaves", rel, ".".join(keys), got, EXPECTED_LEAVES)
        if bad:
            return bad
    leaves = local.get("leaves")
    bad = check_eq("leaves", REL_LOCAL, "len(leaves)",
                   len(leaves) if isinstance(leaves, list) else leaves, EXPECTED_LEAVES)
    if bad:
        return bad

    # ---- parents: 51 ----
    parents_wants = (
        (REL_RESULT, result, ("final", "parents")),
        (REL_LOCAL, local, ("manifest", "parents_count")),
    )
    for rel, obj, keys in parents_wants:
        got, _found = get(obj, *keys)
        bad = check_eq("parents", rel, ".".join(keys), got, EXPECTED_PARENTS)
        if bad:
            return bad
    parents = local.get("parents")
    bad = check_eq("parents", REL_LOCAL, "len(parents)",
                   len(parents) if isinstance(parents, list) else parents, EXPECTED_PARENTS)
    if bad:
        return bad

    # ---- manifest: PASS everywhere ----
    ver, _found = get(manifest, "verify_local", "result")
    if not (isinstance(ver, str) and ver.startswith(EXPECTED_STATUS)):
        return check_eq("manifest", REL_MANIFEST, "verify_local.result",
                        ver, EXPECTED_STATUS + " (...)")
    for rel, obj, keys in (
        (REL_MANIFEST, manifest, ("small_pilot", "status")),
        (REL_RESULT, result, ("status",)),
        (REL_LOCAL, local, ("manifest", "status")),
    ):
        got, _found = get(obj, *keys)
        bad = check_eq("manifest", rel, ".".join(keys), got, EXPECTED_STATUS)
        if bad:
            return bad

    # ---- bytes: explorer data files match fresh pins ----
    for rel in sorted(EXPECTED_SHA256):
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            return "MISMATCH bytes %s: file missing" % rel
        try:
            got = sha256_file(path)
        except OSError as exc:
            return "MISMATCH bytes %s: unreadable (%s)" % (rel, exc)
        want = EXPECTED_SHA256[rel]
        if got != want:
            return "MISMATCH bytes %s: sha256 got %s want %s" % (rel, got, want)

    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify the shipped 20k prefix.")
    parser.add_argument("--root", default=None,
                        help="Repo root (default: parent of the tools directory).")
    args = parser.parse_args(argv)
    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mismatch = verify(root)
    if mismatch is None:
        print("IDENTICAL")
        return 0
    print(mismatch)
    return 1


if __name__ == "__main__":
    sys.exit(main())
