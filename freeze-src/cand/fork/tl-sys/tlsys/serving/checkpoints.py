"""Checkpoint helpers: restart resumes advance from the manifest frontier."""

import json
import os


def save_checkpoint(path, birth, epoch, frontier, tombstone_version,
                    manifest_digest):
    tmp = path + ".tmp"
    payload = {"birth": birth, "epoch": epoch, "frontier": frontier,
               "tombstone_version": tombstone_version,
               "manifest_digest": manifest_digest}
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
    return payload


def load_checkpoint(path):
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)
