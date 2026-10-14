"""W1 commit+epoch+fencing core + W2 publication + P7 generations (scratch).
R1: (a) DB epoch-row authority, manifest keeps non-fenced labels only;
(c) BEGIN IMMEDIATE + epoch first-read validation; (e) lock-path identity;
(f) O_CLOEXEC + no-inherit discipline. R1(b)/(d) takeover execution HELD.
"""
try:
    import fcntl
except ImportError:  # POSIX-only; absent on Windows
    fcntl = None
import json
import os
import sqlite3
import struct
import time

from common import (SCRATCH, FailClosed, HeldError, Reject, Retryable,
                    parse_uuidv7, sha256)

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS epoch_row(birth TEXT NOT NULL, epoch INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS commits(seq INTEGER PRIMARY KEY, birth TEXT NOT NULL,
  epoch INTEGER NOT NULL, op_id TEXT NOT NULL, kind TEXT NOT NULL,
  payload_hash TEXT NOT NULL, outcome TEXT NOT NULL, disclosure TEXT NOT NULL,
  approval_ref TEXT, decided_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS dedup(op_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL,
  outcome TEXT, state TEXT NOT NULL, decided_generation TEXT,
  ts REAL NOT NULL, lease_owner TEXT);
CREATE TABLE IF NOT EXISTS intake(op_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
  kind TEXT NOT NULL, state TEXT NOT NULL, attempt INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS grants(grant_id TEXT PRIMARY KEY, scope TEXT NOT NULL,
  limits TEXT NOT NULL, revoked INTEGER NOT NULL, policy_version TEXT NOT NULL,
  expires_at REAL NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS policy(version TEXT PRIMARY KEY, allowlist TEXT NOT NULL,
  active INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts(artifact_id TEXT PRIMARY KEY, store_id TEXT NOT NULL,
  extent TEXT NOT NULL, length INTEGER NOT NULL, digest TEXT NOT NULL,
  durable INTEGER NOT NULL, op_seq INTEGER);
CREATE TABLE IF NOT EXISTS pub_refs(seq INTEGER NOT NULL, artifact_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS change_log(seq INTEGER NOT NULL, scope TEXT NOT NULL,
  material INTEGER NOT NULL);
-- U-02 (O(1) admission ledger): the three counts intake.accounting() used to
-- re-derive with a COUNT(*) scan per reserve() are maintained in-transaction
-- by the triggers below. Trigger effects are part of the mutation's own txn
-- (they commit or roll back with it), so the ledger stays EXACT; and every
-- mutation of commits/dedup/intake is DML, so no path can bypass them.
-- intake.accounting() reads this in one O(1) lookup; intake.recount()
-- re-derives from the durable tables and re-seeds (recovery step R6 uses it).
CREATE TABLE IF NOT EXISTS counters(k TEXT PRIMARY KEY, v INTEGER NOT NULL);
INSERT OR IGNORE INTO counters(k,v) VALUES
  ('delta_entries',0),('dedup_rows',0),('intake_backlog',0);
CREATE TRIGGER IF NOT EXISTS ct_commits_ai AFTER INSERT ON commits BEGIN
  UPDATE counters SET v=v+1 WHERE k='delta_entries'; END;
CREATE TRIGGER IF NOT EXISTS ct_commits_ad AFTER DELETE ON commits BEGIN
  UPDATE counters SET v=v-1 WHERE k='delta_entries'; END;
CREATE TRIGGER IF NOT EXISTS ct_dedup_ai AFTER INSERT ON dedup BEGIN
  UPDATE counters SET v=v+1 WHERE k='dedup_rows'; END;
CREATE TRIGGER IF NOT EXISTS ct_dedup_ad AFTER DELETE ON dedup BEGIN
  UPDATE counters SET v=v-1 WHERE k='dedup_rows'; END;
CREATE TRIGGER IF NOT EXISTS ct_intake_ai AFTER INSERT ON intake
  WHEN NEW.state='PENDING' BEGIN
  UPDATE counters SET v=v+1 WHERE k='intake_backlog'; END;
CREATE TRIGGER IF NOT EXISTS ct_intake_ad AFTER DELETE ON intake
  WHEN OLD.state='PENDING' BEGIN
  UPDATE counters SET v=v-1 WHERE k='intake_backlog'; END;
CREATE TRIGGER IF NOT EXISTS ct_intake_au AFTER UPDATE OF state ON intake BEGIN
  UPDATE counters SET v = v
    + (CASE WHEN NEW.state='PENDING' THEN 1 ELSE 0 END)
    - (CASE WHEN OLD.state='PENDING' THEN 1 ELSE 0 END)
    WHERE k='intake_backlog'; END;
"""


def _connect(db_path, timeout=30.0):
    con = sqlite3.connect(db_path, timeout=timeout, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=FULL;")
    return con


# ---- WAL keeper (gen-1 sibling v1_sync_keeper, merged into v4) -------------
# Measured on the frozen control (10K-row store, 300-op in-situ census): the
# two fresh connections each commit_op opens and closes are, one after the
# other, the LAST connection on the DB, so SQLite's last-close path runs a
# full WAL checkpoint + WAL/SHM unlink + directory fsync *twice per op*
# (~5.8 ms/op of the 17.6 ms/op mean).  Those checkpoints are not durability
# events: with synchronous=FULL every COMMIT already fsyncs the WAL, which is
# the durable artifact; the checkpoint only copies WAL pages into the main DB
# and drops the WAL.  A keeper handle held for the lifetime of the fence keeps
# the WAL (and its two fds) alive across the op, so the checkpoint happens
# ONCE - at fence release - instead of twice per op.  The keeper holds no
# transaction, no locks and no read snapshot; every per-op connection is still
# opened and closed exactly as before, at the same points, with the same
# pragmas, and every COMMIT is still synchronous=FULL.  No admission, schema,
# ordering or barrier semantics change.
_IMPORT_PID = os.getpid()
_KEEPERS = {}


def keeper_open(store):
    """Attach an idle keeper handle to the store's DB (writer lifetime)."""
    if os.getpid() != _IMPORT_PID:
        return  # forked child (M4b restore): keeps the frozen close shape
    if store.db_path in _KEEPERS:
        return
    _KEEPERS[store.db_path] = _connect(store.db_path)


def keeper_release(store):
    """Drop the keeper: its close is the single end-of-run checkpoint that
    copies the WAL back into commit.db and truncates it (wal_final_bytes 0)."""
    con = _KEEPERS.pop(store.db_path, None)
    if con is not None:
        con.close()


class Store:
    """Fresh-store creation only. Restart recovery lives in recovery.py (HELD)."""

    def __init__(self, root):
        self.root = root
        self.db_path = os.path.join(root, "commit.db")
        self.lock_path = os.path.join(root, "committer.lock")
        self.manifest_path = os.path.join(root, "manifest.json")
        self.spool = os.path.join(root, "spool")
        self.artdir = os.path.join(root, "artifacts")

    @staticmethod
    def create(root, birth=None, store_label="stage-a-scratch", engine="sqlite-wal"):
        import uuid as _uuid
        os.makedirs(root, exist_ok=True)
        st = Store(root)
        os.makedirs(st.spool, exist_ok=True)
        os.makedirs(st.artdir, exist_ok=True)
        birth = birth or str(_uuid.uuid4())
        # lock file + recorded identity (R1e)
        fd = os.open(st.lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
        try:
            s = os.fstat(fd)
            dev, ino = s.st_dev, s.st_ino
        finally:
            os.close(fd)
        con = _connect(st.db_path)
        try:
            con.executescript(SCHEMA)
            con.execute("BEGIN IMMEDIATE;")
            con.execute("INSERT INTO meta(k,v) VALUES('birth_uuid',?),( 'lock_dev',?)"
                        ",('lock_ino',?),('store_id',?),('E',?)",
                        (birth, str(dev), str(ino), store_label, "0"))
            con.execute("INSERT INTO epoch_row(birth,epoch) VALUES(?,0)", (birth,))
            # policy v0: effective Stage-1 allowlist admits nothing (D-23/P-A absent)
            con.execute("INSERT INTO policy(version,allowlist,active) VALUES('v0','[]',1)")
            con.execute("COMMIT;")
        except Exception:
            con.execute("ROLLBACK;")
            raise
        finally:
            con.close()
        # Manifest: NON-FENCED labels only (R1a). No epoch/birth authority here.
        with open(st.manifest_path, "w") as f:
            json.dump({"store_label": store_label, "engine": engine,
                       "created_at": time.time(),
                       "non_authoritative_note": "epoch authority is the DB epoch_row; "
                       "this file carries deployment labels only"}, f, indent=1)
        return st

    def open_db(self):
        return _connect(self.db_path)


class Fence:
    """P4 fence. acquire/check/release. Re-acquire-after-loss not exercised (HELD paths)."""

    def __init__(self, store):
        self.store = store
        self.fd = None
        self.birth = None
        self.epoch = None

    def acquire(self):
        if fcntl is None:
            raise FailClosed("OFD locks unavailable on this platform: fail closed")
        if self.fd is not None:
            raise FailClosed("fence already held by this process")
        fd = os.open(self.store.lock_path, os.O_RDWR | os.O_CLOEXEC)
        # OFD write lock, non-blocking (R1/P4). No flock/POSIX-record locks.
        lk = struct.pack("hhqqih", fcntl.F_WRLCK, 0, 0, 0, 0, 0)
        try:
            fcntl.fcntl(fd, fcntl.F_OFD_SETLK, lk)
        except OSError:
            os.close(fd)
            raise Retryable("fence held by a live committer; refusing to serve")
        # lock-path identity (R1e): fstat(fd) vs stat(path) vs recorded
        try:
            fst = os.fstat(fd)
            pst = os.stat(self.store.lock_path)
            if (fst.st_dev, fst.st_ino) != (pst.st_dev, pst.st_ino):
                raise FailClosed("lock-path identity mismatch (fd vs path): fail closed")
            con = self.store.open_db()
            try:
                row = con.execute("SELECT v FROM meta WHERE k='lock_dev'").fetchone()
                row2 = con.execute("SELECT v FROM meta WHERE k='lock_ino'").fetchone()
                if row is None or row2 is None:
                    raise FailClosed("lock-identity record missing: fail closed")
                if (fst.st_dev, fst.st_ino) != (int(row[0]), int(row2[0])):
                    raise FailClosed("lock-path replaced (dev/ino mismatch): fail closed")
                erow = con.execute("SELECT birth,epoch FROM epoch_row").fetchone()
                if erow is None:
                    raise FailClosed("epoch row missing: fail closed")
            finally:
                con.close()
        except Exception:
            self._unlock(fd)
            os.close(fd)
            raise
        self.fd = fd
        self.birth, self.epoch = erow[0], int(erow[1])
        keeper_open(self.store)  # WAL keeper: hold the WAL live for the fence
        return (self.birth, self.epoch)

    @staticmethod
    def _unlock(fd):
        try:
            fcntl.fcntl(fd, fcntl.F_OFD_SETLK, struct.pack("hhqqih", fcntl.F_UNLCK, 0, 0, 0, 0, 0))
        except OSError:
            pass

    def check(self, con):
        """In-txn first-read validation. Caller holds BEGIN IMMEDIATE already."""
        row = con.execute("SELECT birth,epoch FROM epoch_row").fetchone()
        if row is None or row[0] != self.birth or int(row[1]) != self.epoch:
            raise Reject("STALE_EPOCH", "fenced epoch mismatch: abort, no partial effects")

    def release(self):
        if self.fd is not None:
            self._unlock(self.fd)
            os.close(self.fd)  # O_CLOEXEC, no inheritance: last ref closes here
            self.fd = None
        # End of the writer's lifetime: dropping the keeper is what performs
        # the single checkpoint of the run (WAL -> commit.db, WAL truncated).
        keeper_release(self.store)


def fsync_file(path):
    fd = os.open(path, os.O_RDWR)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_dir(d):
    fd = os.open(d, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
