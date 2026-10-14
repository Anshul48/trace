#!/usr/bin/env python3
"""Portable exact-prefix preparation for the TRACE stack-fork 38c66bef protocol.

The 10M qualification consumed a VM-only data dir (`~/beam/pkg/data`:
`docs-100m.jsonl` + `emb_cache/`, format `tl-gpu-embcache-v1`). This script
closes clean-checkout reproduction at small scale WITHOUT copying that tree:

  export-vm : stream a READ-ONLY exporter to the qualification VM over the
              existing gcloud SSH auth. The exporter writes nothing on the
              VM; it emits a small tar.gz on stdout containing the exact
              complete-document TOK_V1 prefix up to --tokens, the verbatim
              cache meta.json, and a repacked emb_cache (same keys, same
              FP32 vector bytes, rows renumbered from 0 in one shard).
  unpack    : extract that tar.gz into a local data dir.
  verify    : run the FROZEN `tools/real_prefix.RealPrefix` (pin-checked
              against SOURCEFREEZE 38c66bef) over the local data dir and
              compare its receipt against the exporter's full-cache receipt:
              prefix_raw_sha256 and used_vector_sha256 MUST match exactly;
              cache_index_sha256 differs by construction (subset index) and
              cache_meta_sha256 MUST match (meta is verbatim).
  verify-freeze : rehash all 207 SOURCEFREEZE files under a candidate root.

After `verify` passes, the small-scale protocol runs from a clean checkout:

  PYTHONPATH=<cand>/fork/tl-sys:<cand>/fork/tl-candidate-batch/candidate:<cand>/tools \
  python -B <cand>/tools/product_pilot.py --tokens 20000 --profile local \
      --out <outdir> --source-root <cand> --data-dir <this-data-dir>

This reproduces the protocol at small scale with the actual frozen engine
and actual cached vectors. It does NOT reproduce the 10M qualification
numbers; those remain the recorded VM receipts (see PROTOCOL.md).
"""
import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

FREEZE_SHA = "38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54"
HARNESS_SHA = "9f516288a098eff7b2a52373ad0eaf6b9ad1664377a9f7be4f974701b8d9b1a0"
VM = dict(instance="trace-build500", project="reflecting-zone-482108-h0",
          zone="us-central1-a")

# Read-only exporter executed on the VM via stdin (no VM writes).
# Args after '-': sys.argv[1] = target tokens.
EXPORTER = r'''
import hashlib, io, json, sys, tarfile
from pathlib import Path
sys.path.insert(0, "/home/anshul/exec-claude-stack-20261013T0045Z/stack-fork/cand/fork/tl-sys")
sys.path.insert(0, "/home/anshul/exec-claude-stack-20261013T0045Z/stack-fork/cand/tools")
from real_prefix import RealPrefix, TOK
from tlsys.ingest import chunk_text

target = int(sys.argv[1])
DATA = Path("/home/anshul/beam/pkg/data")
rp = RealPrefix(target, data_dir=DATA)

# Exact raw prefix lines (complete documents, same stop rule as RealPrefix).
lines, total = [], 0
with open(DATA / "docs-100m.jsonl", "rb") as f:
    for line in f:
        if not line.strip():
            continue
        row = json.loads(line)
        lines.append(line)
        total += len(TOK.findall(row["text"]))
        if total >= target:
            break
docs_bytes = b"".join(lines)
assert hashlib.sha256(docs_bytes).hexdigest() == rp.receipt["prefix_raw_sha256"], "prefix mismatch"
assert len(lines) == rp.receipt["complete_documents"], "doc count mismatch"

# Wanted keys with (chunk_sha256, byte_len), recomputed exactly as RealPrefix.
wanted = {}
for _doc, text in rp.docs:
    for chunk in (chunk_text(text) or [(0, 0, "", 0, 0)]):
        body = chunk[2].encode("utf-8")
        wanted[rp.key(body)] = (hashlib.sha256(body).hexdigest(), len(body))
assert set(wanted) == set(rp.vectors), "key set mismatch"

# Original index rows for wanted keys (preserve model_tokens/truncated).
orig = {}
with open(DATA / "emb_cache/index.jsonl", "rb") as f:
    for line in f:
        r = json.loads(line)
        if r["key"] in wanted:
            orig[r["key"]] = r
assert set(orig) == set(wanted), "index coverage mismatch"

keys = sorted(wanted)
index_lines, shard = [], io.BytesIO()
for i, k in enumerate(keys):
    r = dict(orig[k]); r["row"] = i; r["shard"] = 0
    index_lines.append(json.dumps(r, sort_keys=True).encode() + b"\n")
    shard.write(rp.vectors[k].astype("<f4").tobytes())
meta_bytes = (DATA / "emb_cache/meta.json").read_bytes()
receipt = dict(rp.receipt)
receipt["export_note"] = ("rows renumbered 0..N-1 in shard_000000; vector bytes, keys, "
                          "meta.json verbatim; cache_index_sha256 of the subset index "
                          "differs from this full-cache receipt by construction")
members = {
    "docs-100m.jsonl": docs_bytes,
    "emb_cache/meta.json": meta_bytes,
    "emb_cache/index.jsonl": b"".join(index_lines),
    "emb_cache/shard_000000.f32": shard.getvalue(),
    "exporter-receipt.json": (json.dumps(receipt, indent=1, sort_keys=True) + "\n").encode(),
}
out = io.BytesIO()
with tarfile.open(fileobj=out, mode="w:gz") as tf:
    for name, body in members.items():
        info = tarfile.TarInfo(name); info.size = len(body); info.mtime = 0
        tf.addfile(info, io.BytesIO(body))
sys.stdout.buffer.write(out.getvalue())
'''


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cmd_export_vm(a):
    cmd = ["gcloud", "compute", "ssh", VM["instance"],
           f"--project={VM['project']}", f"--zone={VM['zone']}",
           "--command", f"~/venv/bin/python -B - {a.tokens}"]
    print("+", " ".join(cmd), " < exporter (read-only, stdout tar.gz)", file=sys.stderr)
    proc = subprocess.run(cmd, input=EXPORTER.encode(), capture_output=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode(errors="replace")[-3000:])
        return 1
    Path(a.out).write_bytes(proc.stdout)
    print(f"wrote {a.out}  {len(proc.stdout)} bytes  sha256 {hashlib.sha256(proc.stdout).hexdigest()}")
    return 0


def cmd_unpack(a):
    dest = Path(a.data_dir)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(a.tar, "r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile():
                (dest / m.name).parent.mkdir(parents=True, exist_ok=True)
                (dest / m.name).write_bytes(tf.extractfile(m).read())
                print(" ", m.name, m.size)
    return 0


def cmd_verify_freeze(a):
    root = Path(a.cand)
    freeze = root / "SOURCEFREEZE.json"
    got = sha256_file(freeze)
    assert got == FREEZE_SHA, f"SOURCEFREEZE.json sha {got} != {FREEZE_SHA}"
    files = json.loads(freeze.read_text())["files"]
    bad = [rel for rel, want in files.items()
           if not (root / rel).is_file() or sha256_file(root / rel) != want]
    assert sha256_file(root / "tools/product_pilot.py") == HARNESS_SHA, "harness pin drift"
    print(f"FREEZE PASS  {len(files) - len(bad)}/{len(files)} files match, harness pin ok")
    return 0 if not bad else 1


def cmd_verify(a):
    cand = Path(a.cand).resolve()
    assert sha256_file(cand / "tools/real_prefix.py") == \
        json.loads((cand / "SOURCEFREEZE.json").read_text())["files"]["tools/real_prefix.py"], \
        "real_prefix.py not at frozen pin"
    sys.path.insert(0, str(cand / "fork/tl-sys"))
    sys.path.insert(0, str(cand / "tools"))
    from real_prefix import RealPrefix
    rp = RealPrefix(a.tokens, data_dir=Path(a.data_dir))
    local = rp.receipt
    gold = json.loads(Path(a.data_dir, "exporter-receipt.json").read_text())
    checks = {
        "actual_tokens": local["actual_tokens"] == gold["actual_tokens"],
        "complete_documents": local["complete_documents"] == gold["complete_documents"],
        "atoms": local["atoms"] == gold["atoms"],
        "distinct_chunks": local["distinct_chunks"] == gold["distinct_chunks"],
        "cache_misses==0": local["cache_misses"] == 0,
        "prefix_raw_sha256": local["prefix_raw_sha256"] == gold["prefix_raw_sha256"],
        "used_vector_sha256": local["used_vector_sha256"] == gold["used_vector_sha256"],
        "cache_meta_sha256 (verbatim meta)": local["cache_meta_sha256"] == gold["cache_meta_sha256"],
    }
    for k, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {k}")
    print(json.dumps({k: local[k] for k in
                      ("actual_tokens", "complete_documents", "atoms", "distinct_chunks",
                       "prefix_raw_sha256", "used_vector_sha256", "cache_index_sha256")}, indent=1))
    print("note: local cache_index_sha256 hashes the subset index.jsonl and "
          "therefore differs from the full-cache receipt value by construction.")
    ok = all(checks.values())
    print("VERIFY", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export-vm"); e.add_argument("--tokens", type=int, default=20000)
    e.add_argument("--out", default="small-prefix.tar.gz"); e.set_defaults(fn=cmd_export_vm)
    u = sub.add_parser("unpack"); u.add_argument("--tar", default="small-prefix.tar.gz")
    u.add_argument("--data-dir", required=True); u.set_defaults(fn=cmd_unpack)
    v = sub.add_parser("verify"); v.add_argument("--tokens", type=int, default=20000)
    v.add_argument("--cand", required=True); v.add_argument("--data-dir", required=True)
    v.set_defaults(fn=cmd_verify)
    f = sub.add_parser("verify-freeze"); f.add_argument("--cand", required=True)
    f.set_defaults(fn=cmd_verify_freeze)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
