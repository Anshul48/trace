"""Lane BUILD100M: re-key a scratch store copy per gate_lib.snapshot_store.

Adapted from Lane A-2's a2_rekey.py (lane-relaunch guard).
Importable rekey() plus CLI. Operates ONLY on the scratch copy given
by --store; never touches the live store or the bucket.
Usage on the VM:
  python3 b100m_rekey.py --store /srv/tl/lane-relaunch/scratch/<name>
"""
import argparse
import os
import sqlite3


GUARD = "lane-relaunch"


def rekey(store):
    if GUARD not in os.path.abspath(store):
        raise SystemExit(
            "refusing: target is not under /srv/tl/lane-relaunch")
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
        con.execute("UPDATE meta SET v=? WHERE k='lock_dev'",
                    (str(dev),))
        con.execute("UPDATE meta SET v=? WHERE k='lock_ino'",
                    (str(ino),))
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
