"""W6 delta + exclusion structures + bounds (Stage-B scratch, Linux reference).

Dep: W1 (commit txn), W2 (generations). Deltas ride the commit txn via a
SQLite trigger: complete + queryable before ACK by construction. D-30: read
paths verify contiguous coverage; gaps raise, never silent-skip.
"""
import os
import time

from common import FailClosed, Reject, Retryable

W6_SCHEMA = """
CREATE TABLE IF NOT EXISTS deltas(seq INTEGER PRIMARY KEY, triple TEXT NOT NULL,
  op_id TEXT NOT NULL, kind TEXT NOT NULL, outcome TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exclusions(excl_id TEXT PRIMARY KEY, scope TEXT NOT NULL,
  reason TEXT NOT NULL, created_seq INTEGER NOT NULL, retired_seq INTEGER);
CREATE TRIGGER IF NOT EXISTS w6_delta_after_commit AFTER INSERT ON commits BEGIN
  INSERT INTO deltas(seq,triple,op_id,kind,outcome) VALUES(NEW.seq,
    NEW.birth || ':' || NEW.epoch || ':' || NEW.seq, NEW.op_id, NEW.kind, NEW.outcome);
END;
"""

# Experimental bounds (D-12), recorded per run, enforced once configured.
W6_CAPS = {
    "max_delta_entries": 100000,
    "max_delta_bytes": 512 * 1024 * 1024,
    "reserve_deadline_s": 5.0,
}


def ensure_schema(con):
    con.executescript(W6_SCHEMA)


def delta_accounting(con):
    n = con.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(outcome)),0) FROM deltas").fetchone()
    return {"delta_entries": int(n[0]), "delta_bytes": int(n[1])}


def reserve_delta(con, est_bytes, caps, now=None):
    """W6 admission check. Raises explicit retryable capacity error when over."""
    now = time.time() if now is None else now
    use = delta_accounting(con)
    over = (use["delta_entries"] >= caps["max_delta_entries"]
            or use["delta_bytes"] + est_bytes > caps["max_delta_bytes"])
    if not over:
        return ("GRANT", use)
    deadline = now + caps["reserve_deadline_s"]
    while time.time() < deadline:
        time.sleep(0.05)
        use = delta_accounting(con)
        if not (use["delta_entries"] >= caps["max_delta_entries"]
                or use["delta_bytes"] + est_bytes > caps["max_delta_bytes"]):
            return ("GRANT", use)
    raise Retryable("REJECT_CAPACITY(delta): explicit retryable capacity error; "
                    f"blocking cause: delta bounds {use} vs caps {caps}")


def read_deltas(con, lo, hi):
    """Queryable deltas for [lo,hi]. D-30: gaps raise FailClosed, never silent."""
    rows = con.execute("SELECT seq,triple,op_id,kind,outcome FROM deltas "
                       "WHERE seq>=? AND seq<=? ORDER BY seq", (lo, hi)).fetchall()
    seqs = [r[0] for r in rows]
    expect = list(range(lo, hi + 1))
    if seqs != expect:
        missing = sorted(set(expect) - set(seqs))
        raise FailClosed(f"DELTA_GAP: no silent omission; missing seqs {missing[:8]}")
    return rows


def add_exclusion(con, excl_id, scope, reason, created_seq):
    con.execute("INSERT INTO exclusions(excl_id,scope,reason,created_seq,retired_seq) "
                "VALUES(?,?,?,?,NULL)", (excl_id, scope, reason, created_seq))


def retire_exclusion(con, excl_id, retired_seq):
    con.execute("UPDATE exclusions SET retired_seq=? WHERE excl_id=?", (retired_seq, excl_id))


def active_scopes(con):
    rows = con.execute("SELECT scope FROM exclusions WHERE retired_seq IS NULL").fetchall()
    return {r[0] for r in rows}


def select_seeds(candidates, excluded_scopes):
    """Exclusions applied BEFORE final seed selection. candidates: list of
    dicts with 'seed_id' + 'scope'. All-excluded -> explicit Reject, never
    silent empty selection."""
    scopes = set(excluded_scopes)
    kept = [c for c in candidates if c.get("scope") not in scopes]
    if candidates and not kept:
        raise Reject("SEED_EXHAUSTED",
                     f"all {len(candidates)} candidates excluded by {sorted(scopes)}; "
                     "explicit exhaustion, nothing selected silently")
    return kept


def wal_bytes(db_path):
    try:
        return os.path.getsize(db_path + "-wal")
    except OSError:
        return 0


def checkpoint(con):
    return con.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
