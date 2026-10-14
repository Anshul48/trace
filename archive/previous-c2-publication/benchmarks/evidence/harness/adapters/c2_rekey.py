"""lane-BENCH10M: re-key the bench's own store COPY (lock identity only).

Same mechanics as lane-BUILD100M-C2 b100m_rekey.py (itself adapted
from lane-A-2): a filesystem copy of a store carries the source's
lock dev/ino in commit.db meta, so TLStore fail-closes with
"lock-path replaced". Re-keying mints a fresh committer.lock and
updates ONLY the lock_dev/lock_ino meta rows. Content (commits,
pins, receipts) is untouched.

Guard: operates ONLY under /srv/tl/lane-bench10m. Run AFTER the
byte-verification against c2-10m-manifest.json (which must pass on
the pristine copy first); afterwards the copy differs from GCS
bytes in exactly these two meta rows + the lock file, recorded
in the probe output.

Usage (on VM):
  python c2_rekey.py --store /srv/tl/lane-bench10m/store/snapshots/pin-final
"""

import argparse
import os
import sqlite3

GUARD = "/srv/tl/lane-bench10m"


def rekey(store):
    if GUARD not in os.path.abspath(store):
        raise SystemExit("refusing: target is not under /srv/tl/lane-bench10m")
    lock_p = os.path.join(store, "committer.lock")
    db_p = os.path.join(store, "commit.db")
    con = sqlite3.connect(db_p, timeout=30)
    old = {r[0]: r[1] for r in con.execute(
        "SELECT k, v FROM meta WHERE k IN ('lock_dev','lock_ino')")}
    con.close()
    print("old meta:", old, flush=True)
    if os.path.exists(lock_p):
        os.remove(lock_p)
    for stale in ("commit.db-shm",):
        p = os.path.join(store, stale)
        if os.path.exists(p):
            os.remove(p)
            print("removed stale", stale, flush=True)
    fd = os.open(lock_p, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        s = os.fstat(fd)
        dev, ino = s.st_dev, s.st_ino
    finally:
        os.close(fd)
    con = sqlite3.connect(db_p, timeout=30)
    try:
        con.execute("UPDATE meta SET v=? WHERE k='lock_dev'", (str(dev),))
        con.execute("UPDATE meta SET v=? WHERE k='lock_ino'", (str(ino),))
        con.commit()
        new = {r[0]: r[1] for r in con.execute(
            "SELECT k, v FROM meta WHERE k IN ('lock_dev','lock_ino')")}
    finally:
        con.close()
    print("fresh lock dev/ino:", dev, ino, flush=True)
    print("new meta:", new, flush=True)
    assert new == {"lock_dev": str(dev), "lock_ino": str(ino)}, new
    print("REKEY_OK", flush=True)
    return {"old": old, "new": new}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True)
    ns = ap.parse_args()
    rekey(ns.store)


if __name__ == "__main__":
    main()
