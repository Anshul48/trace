"""W3 intake queue + backpressure + ACK path (P1/P9).
Serving submits via a separately-fsync'd spool journal (F1.3 option 2):
NO serving-process DB writes. Worker drains spool -> intake table.
Admission.reserve BEFORE the commit txn; WAIT outside with deadline."""
import json
import os
import time

from common import Reject, Retryable, raise_retryable_on_eio, sha256
from store import fsync_dir, fsync_file

# Experimental values (D-12), recorded per run, enforced once configured.
CAPS = {
    "max_delta_entries": 100000,
    "max_delta_bytes": 512 * 1024 * 1024,
    "max_dedup_rows": 1000000,
    "max_intake_backlog": 10000,
    "max_reservations": 64,
    "reserve_deadline_s": 5.0,
    "retirement_headroom_entries": 1000,
}

_reservations = {}  # token -> (estimate_bytes, deadline); volatile


def recount(con):
    """U-02: exact re-derivation of the admission ledger from the durable
    tables (the pre-U-02 definition, verbatim), re-seeding the O(1) counter
    rows. Recovery R6 calls this so a restored store's ledger is rebuilt from
    durable state, never inherited. Returns (delta_entries, dedup_rows,
    intake_backlog)."""
    n_delta = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
    n_dedup = con.execute("SELECT COUNT(*) FROM dedup").fetchone()[0]
    n_backlog = con.execute("SELECT COUNT(*) FROM intake WHERE state='PENDING'").fetchone()[0]
    if not con.in_transaction:
        try:
            con.execute("BEGIN IMMEDIATE;")
            try:
                con.execute("INSERT OR REPLACE INTO counters(k,v) VALUES"
                            "('delta_entries',?),('dedup_rows',?),"
                            "('intake_backlog',?)", (n_delta, n_dedup, n_backlog))
                con.execute("COMMIT;")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK;")
                raise
        except Exception:
            pass  # read-mostly caller: a failed repair never blocks admission
    return (int(n_delta), int(n_dedup), int(n_backlog))


def _ledger(con):
    """U-02: O(1) ledger read (single row per counter). Falls back to an exact
    recount, and repairs the counters, if the table is absent/unreadable."""
    try:
        rows = dict(con.execute("SELECT k,v FROM counters").fetchall())
        return (int(rows["delta_entries"]), int(rows["dedup_rows"]),
                int(rows["intake_backlog"]))
    except Exception:
        return recount(con)


def accounting(con, art_bytes=0):
    n_delta, n_dedup, n_backlog = _ledger(con)
    wal = 0
    try:
        wal = os.path.getsize(con.execute("PRAGMA database_list").fetchall()[0][2] + "-wal")
    except OSError:
        pass
    return {"delta_entries": n_delta, "delta_bytes_est": art_bytes,
            "dedup_rows": n_dedup, "intake_backlog": n_backlog,
            "wal_bytes": wal, "reservations": len(_reservations)}


def submit_spool(store, op_id, kind, payload_obj, disclosure):
    """Serving-side: journal only, no DB access (I1.5/G2)."""
    rec = {"op_id": op_id, "kind": kind, "payload": payload_obj,
           "disclosure": disclosure, "t": time.time()}
    path = os.path.join(store.spool, op_id + ".json")
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(rec, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, path)
        fsync_dir(store.spool)
    except OSError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise_retryable_on_eio(e, "submit_spool")
    return op_id


def drain_spool(store, con):
    """Worker-side: move spooled ops into the intake table (fenced txn by caller)."""
    moved = []
    for fn in sorted(os.listdir(store.spool)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(store.spool, fn)
        with open(path) as f:
            rec = json.load(f)
        try:
            con.execute("INSERT INTO intake(op_id,payload,kind,state,attempt) "
                        "VALUES(?,?,?,'PENDING',0)",
                        (rec["op_id"], json.dumps(rec["payload"], sort_keys=True),
                         rec["kind"]))
        except Exception:
            pass  # already drained (idempotent)
        os.remove(path)
        moved.append(rec["op_id"])
    return moved


def reserve(con, op_estimate_bytes, caps, now, kind="EDIT"):
    """Admission.reserve. Returns ('GRANT', token) | raises Retryable(WAIT-deadline)
    as REJECT_CAPACITY-shaped retryable error. WAIT happens here, outside any txn."""
    use = accounting(con)
    retiring = kind in ("RETRACT", "SUPERSEDE_ATOMS")
    head = caps["retirement_headroom_entries"]
    over = (use["delta_entries"] >= caps["max_delta_entries"]
            or use["dedup_rows"] >= caps["max_dedup_rows"]
            or use["intake_backlog"] >= caps["max_intake_backlog"]
            or len(_reservations) >= caps["max_reservations"])
    if over:
        if retiring and (caps["max_delta_entries"] - use["delta_entries"]) < head:
            # finite headroom exhausted too
            raise Retryable("REJECT_CAPACITY(headroom-exhausted): retryable; "
                            "blocking cause: delta capacity incl. retirement reserve")
        deadline = now + caps["reserve_deadline_s"]
        while now < deadline:
            time.sleep(0.05)
            now = time.time()
            use = accounting(con)
            if not (use["delta_entries"] >= caps["max_delta_entries"]
                    or use["dedup_rows"] >= caps["max_dedup_rows"]
                    or use["intake_backlog"] >= caps["max_intake_backlog"]
                    or len(_reservations) >= caps["max_reservations"]):
                break
        else:
            raise Retryable("REJECT_CAPACITY(deadline): explicit retryable capacity error")
    tok = f"rsv-{len(_reservations)}-{now:.3f}"
    _reservations[tok] = (op_estimate_bytes, now)
    return ("GRANT", tok)


def release(token):
    _reservations.pop(token, None)
