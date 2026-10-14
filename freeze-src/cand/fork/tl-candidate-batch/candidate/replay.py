"""W4 replay dedup + expiry (P5). All claim steps run inside the commit txn."""
import time

from common import (Reject, Retryable, parse_uuidv7,
                    raise_retryable_on_eio, sha256)

# Experimental values (D-12): recorded per run, enforced once configured.
HORIZON_S = 3600.0
SKEW_ALLOWANCE_S = 300.0


def cutoff_e(con):
    row = con.execute("SELECT v FROM meta WHERE k='E'").fetchone()
    return float(row[0]) if row else 0.0


def validate_id(op_id, now):
    """Step 1: UUIDv7 + expiry/clock evaluation. Returns (ts, payload-independent)."""
    ts = parse_uuidv7(op_id)
    return ts


def check_expiry(con, ts, now):
    e = cutoff_e(con)
    c = max(e, now - HORIZON_S)
    if ts < c:
        raise Reject("REJECT_EXPIRED", f"id.ts={ts} below cutoff C={c} (E={e})")
    if ts > now + SKEW_ALLOWANCE_S:
        raise Retryable(f"REJECT_CLOCK: id ahead of wall clock (retryable)")
    return c


def lookup(con, op_id):
    return con.execute("SELECT op_id,payload_hash,outcome,state,decided_generation,ts,"
                       "lease_owner FROM dedup WHERE op_id=?", (op_id,)).fetchone()


def submit_claim(con, op_id, payload, now, lease_owner):
    """P5 steps 1-3 inside ONE txn (caller holds BEGIN IMMEDIATE).
    Returns ('COMMITTED', outcome, gen) | ('TERMINAL', verdict) | ('CLAIMED', None, None).
    Raises REJECT_*/WAIT-check signal via Retryable('WAIT') for live leases."""
    phash = sha256(payload.encode())
    ts = validate_id(op_id, now)
    check_expiry(con, ts, now)  # E-read + evaluation in the claiming unit
    row = lookup(con, op_id)
    if row is not None:
        _id, rhash, outcome, state, gen, _ts, owner = row
        if state == "COMMITTED":
            if rhash != phash:
                raise Reject("REJECT_MISMATCH", "payload differs on COMMITTED id; "
                             "original stands, no mutation")
            return ("COMMITTED", outcome, gen)
        if state == "TERMINAL_REJECTED":
            if rhash != phash:
                raise Reject("REJECT_MISMATCH", "payload differs on TERMINAL id")
            return ("TERMINAL", outcome, gen)
        if state == "IN_PROGRESS":
            if rhash != phash:
                raise Reject("REJECT_MISMATCH", "payload differs on IN_PROGRESS id; "
                             "no row mutation")
            raise Retryable("WAIT: live lease held by committer")
        # ABANDONED -> fall through to reclaim
        if rhash != phash:
            raise Reject("REJECT_MISMATCH", "payload differs on ABANDONED id; row stands")
        con.execute("UPDATE dedup SET state='IN_PROGRESS',lease_owner=? WHERE op_id=?",
                    (lease_owner, op_id))
        return ("CLAIMED", None, None)
    con.execute("INSERT INTO dedup(op_id,payload_hash,outcome,state,decided_generation,"
                "ts,lease_owner) VALUES(?,?,NULL,'IN_PROGRESS',NULL,?,?)",
                (op_id, phash, ts, lease_owner))
    return ("CLAIMED", None, None)


def mark_committed(con, op_id, outcome, gen_triple):
    con.execute("UPDATE dedup SET state='COMMITTED',outcome=?,decided_generation=? "
                "WHERE op_id=?", (outcome, gen_triple, op_id))


def mark_terminal(con, op_id, verdict):
    con.execute("UPDATE dedup SET state='TERMINAL_REJECTED',outcome=? WHERE op_id=?",
                (verdict, op_id))


def prune(con, checkpoint_seq, now):
    """P5 prune in one txn with E advance. Returns (E_new, deleted)."""
    e_new = max(cutoff_e(con), now - HORIZON_S)
    con.execute("UPDATE meta SET v=? WHERE k='E'", (str(e_new),))
    cur = con.execute("DELETE FROM dedup WHERE state='COMMITTED' AND ts<? "
                      "AND op_id IN (SELECT d.op_id FROM dedup d JOIN commits c "
                      "ON d.decided_generation=(c.birth||':'||c.epoch||':'||c.seq) "
                      "WHERE c.seq<=?)", (e_new, checkpoint_seq))
    n1 = cur.rowcount
    cur = con.execute("DELETE FROM dedup WHERE state='ABANDONED' AND ts<?", (e_new,))
    n2 = cur.rowcount
    # TERMINAL_REJECTED prunable once ts<E (subsume rule -> REJECT_EXPIRED after)
    cur = con.execute("DELETE FROM dedup WHERE state='TERMINAL_REJECTED' AND ts<?",
                      (e_new,))
    n3 = cur.rowcount
    return (e_new, n1 + n2 + n3)


def prune_txn(store, checkpoint_seq, now):
    """P5 prune as one explicit txn (P-DRIVE shape, in-SUT): BEGIN -> prune
    -> COMMIT. EIO anywhere in the txn aborts with Retryable (freeze §4 F-D
    row); any other error propagates after rollback."""
    con = store.open_db()
    try:
        con.execute("BEGIN IMMEDIATE;")
        try:
            out = prune(con, checkpoint_seq, now)
            con.execute("COMMIT;")
        except OSError as e:
            if con.in_transaction:
                con.execute("ROLLBACK;")
            raise_retryable_on_eio(e, "prune_txn")
        return out
    finally:
        con.close()
