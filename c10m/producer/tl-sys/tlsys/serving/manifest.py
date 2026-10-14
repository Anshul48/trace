"""Manifest: the single atomic pointer over live segments."""

import hashlib
import json
import os

from tlsys.serving import ANALYZER_ID, CONFIG_ID, FORMAT_VERSION
from tlsys.serving import faults

FILENAME = "manifest.json"
STAGED = "manifest.staged.json"


def digest_of(payload):
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def build(segs, tombstone_version, checkpoint_frontier, live_n,
          total_tokens):
    payload = {
        "format_version": FORMAT_VERSION, "config_id": CONFIG_ID,
        "analyzer_id": ANALYZER_ID,
        "segments": [{"segid": s.segid, "lo": s.lo, "hi": s.hi,
                      "atoms": len(s.atom_rows),
                      "holons": len(s.holon_rows),
                      "op_hash": s.op_hash} for s in segs],
        "tombstone_version": tombstone_version,
        "checkpoint_frontier": checkpoint_frontier,
        "live_n": live_n, "total_tokens": total_tokens}
    payload["digest"] = digest_of(payload)
    return payload


def atomic_write(path, payload, counters=None):
    faults.fire("pre_manifest", path=path)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, path)
    dfd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    faults.fire("post_manifest", path=path)
    if counters is not None:
        counters.record(files_touched=1,
                        bytes_written=os.path.getsize(path))


def read_validated(path):
    with open(path) as f:
        payload = json.load(f)
    digest = payload.pop("digest", None)
    if payload.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"{path}: bad format_version (fail closed)")
    if payload.get("config_id") != CONFIG_ID or \
            payload.get("analyzer_id") != ANALYZER_ID:
        raise ValueError(f"{path}: config/analyzer skew (fail closed)")
    if digest != digest_of(payload):
        raise ValueError(f"{path}: manifest digest mismatch (fail closed)")
    payload["digest"] = digest
    return payload
