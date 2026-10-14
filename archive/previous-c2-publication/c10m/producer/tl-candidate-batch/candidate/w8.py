"""W8 logical reclamation per S-03 section 4a-4c Final (scratch).

LOGICAL ONLY (Stage-B boundary): quarantine-as-state, incarnation-
identified delete AUTHORIZATION, section 4c two-part proof. Physical
removal is NOT implemented: physical_delete() always raises NotAuthorized.
No routing repair, marker subsystem, C1 integration, or eligibility
materialization (B-01 neutrality).
"""
import time
import uuid as _uuid

from common import FailClosed, Reject, Retryable

W8_SCHEMA = """
CREATE TABLE IF NOT EXISTS quarantine(artifact_id TEXT PRIMARY KEY,
  incarnation INTEGER NOT NULL, state TEXT NOT NULL, reason TEXT NOT NULL,
  bytes INTEGER NOT NULL, protected_gen TEXT, updated_at REAL NOT NULL);
"""

CANDIDATE, QUARANTINED, DELETE_AUTHORIZED, RETAINED = (
    "CANDIDATE", "QUARANTINED", "DELETE_AUTHORIZED", "RETAINED")

# Experimental bound (D-12), recorded per run.
W8_CAPS = {"max_quarantine_bytes": 256 * 1024 * 1024}


class NotAuthorized(Exception):
    """Stage-B W8 boundary: physical removal never authorized here."""


def ensure_schema(con):
    con.executescript(W8_SCHEMA)


class Owner:
    """The section 4a logical reclamation owner (role, not a process)."""

    def __init__(self, owner_id=None):
        self.owner_id = owner_id or f"reclaim-owner-{_uuid.uuid4().hex[:8]}"


def nominate(con, artifact_id, incarnation, nbytes, reason, protected_gen=None):
    con.execute("INSERT OR REPLACE INTO quarantine(artifact_id,incarnation,state,"
                "reason,bytes,protected_gen,updated_at) VALUES(?,?,?,?,?,?,?)",
                (artifact_id, incarnation, CANDIDATE, reason, nbytes,
                 protected_gen, time.time()))


def quarantine_accounting(con):
    row = con.execute("SELECT COUNT(*), COALESCE(SUM(bytes),0) FROM quarantine "
                      "WHERE state IN ('QUARANTINED','DELETE_AUTHORIZED')").fetchone()
    return {"quarantined_entries": int(row[0]), "quarantined_bytes": int(row[1])}


def move_to_quarantine(con, artifact_id, incarnation, cap_bytes):
    row = con.execute("SELECT incarnation,state,bytes FROM quarantine "
                      "WHERE artifact_id=?", (artifact_id,)).fetchone()
    if row is None:
        raise Reject("UNKNOWN_ARTIFACT", f"{artifact_id}: uncertainty retains; "
                     "nothing authorized for unknown artifacts")
    if int(row[0]) != int(incarnation):
        raise Reject("INCARNATION_MISMATCH",
                     f"{artifact_id}: authorization names incarnation {incarnation}, "
                     f"current is {row[0]}: refused")
    use = quarantine_accounting(con)
    if use["quarantined_bytes"] + int(row[2]) > cap_bytes:
        raise Retryable("REJECT_CAPACITY(quarantine): explicit retryable capacity "
                        f"error; blocking cause: quarantine {use} vs cap {cap_bytes}")
    con.execute("UPDATE quarantine SET state='QUARANTINED', updated_at=? "
                "WHERE artifact_id=?", (time.time(), artifact_id))
    return quarantine_accounting(con)


def scan(con, live_pins_fn, owner):
    """One bounded reclamation-scan pass over CANDIDATEs. live_pins_fn()
    returns the live protected-gen set from the production pin registry.
    Safe direction is over-retention: any uncertainty retains. Returns a
    retention record with full coverage.

    RECTIFY 2026-09-19 (C2-03 falsifier firing: spans-true pin quarantined
    in 2/15 runs): the live set is read FRESH per candidate, AFTER its row
    was observed CANDIDATE. A single snapshot before the SELECT goes stale
    against concurrent claim+nominate (snapshot misses, row visible ->
    under-retention). Per-decision freshness guarantees every pin held at
    decision time is seen; the residual race (claim between the fresh read
    and the UPDATE) can only catch pins claimed after the pass started.
    """
    rows = con.execute("SELECT artifact_id,incarnation,protected_gen "
                       "FROM quarantine WHERE state='CANDIDATE' "
                       "ORDER BY artifact_id").fetchall()
    cov, retained, quar, deferred = [], [], [], []
    uncertain, uncertainty = False, None
    for aid, inc, pg in rows:
        cov.append(aid)
        try:
            live = set(live_pins_fn())
        except Exception as e:  # registry unreadable: this one retains
            uncertain, uncertainty = True, f"{type(e).__name__}: {e}"
            retained.append(aid)
            deferred.append(aid)
            continue
        if pg is not None and pg in live:
            con.execute("UPDATE quarantine SET state='RETAINED', reason=?, "
                        "updated_at=? WHERE artifact_id=?",
                        (f"pin-protected: {pg} live", time.time(), aid))
            retained.append(aid)
        else:
            try:
                move_to_quarantine(con, aid, inc, W8_CAPS["max_quarantine_bytes"])
                quar.append(aid)
            except Retryable:  # cap-hit: stays CANDIDATE (deferred, retained)
                retained.append(aid)
                deferred.append(aid)
    rec = {"owner": owner.owner_id, "coverage": cov, "retention_set": retained,
           "quarantined": quar, "uncertain": uncertain}
    if deferred:
        rec["deferred"] = deferred
    if uncertainty is not None:
        rec["uncertainty"] = uncertainty
    return rec


def authorize_delete(con, artifact_id, incarnation):
    """Incarnation-identified delete AUTHORIZATION (logical). Idempotent on
    retry with the same incarnation; interruption-safe; fail-closed."""
    row = con.execute("SELECT incarnation,state FROM quarantine "
                      "WHERE artifact_id=?", (artifact_id,)).fetchone()
    if row is None:
        raise Reject("UNKNOWN_ARTIFACT", f"{artifact_id}: uncertainty retains")
    if int(row[0]) != int(incarnation):
        raise Reject("INCARNATION_MISMATCH",
                     f"{artifact_id}: names {incarnation}, current {row[0]}")
    if row[1] == DELETE_AUTHORIZED:
        return DELETE_AUTHORIZED  # retried cleanup: safe, same result
    if row[1] != QUARANTINED:
        raise Reject("NOT_QUARANTINED",
                     f"{artifact_id}: state {row[1]}; only QUARANTINED authorizes")
    con.execute("UPDATE quarantine SET state='DELETE_AUTHORIZED', updated_at=? "
                "WHERE artifact_id=?", (time.time(), artifact_id))
    return DELETE_AUTHORIZED


def physical_delete(artifact_id, incarnation):
    """Stage-B boundary: physical removal is never authorized here."""
    raise NotAuthorized("W8 logical-only boundary: physical removal of "
                        f"{artifact_id}#{incarnation} is not authorized in Stage B")


# ---- section 4c abandoned-reader stop-and-drain ----
P1_OK = ("fencing-verified", "cooperative-release")
P2_OK = ("verified-drain", "cooperative-release-complete",
         "platform-termination-covering-access")


def release_abandoned_pin(pin_table, table_id, slot, incarnation, p1, p2):
    """Two-part proof required: (1) no further access can begin AND (2) all
    protected existing access ended. Anything less -> RETAINED. Returns
    (outcome, reason). Cancellation-request-alone is explicitly insufficient."""
    if p1 not in P1_OK:
        return ("RETAINED", f"part1 unproven ({p1!r}): blocking new acquisitions "
                "alone is insufficient")
    if p2 == "cancellation-requested":
        return ("RETAINED", "part2 unproven: a cancellation request alone does "
                "not establish completion")
    if p2 not in P2_OK:
        return ("RETAINED", f"part2 unproven ({p2!r}): safe drain unestablished, "
                "pin retained")
    gen = pin_table.validate(table_id, slot, incarnation)
    if gen is None:
        return ("RETAINED", "registration not held by this incarnation "
                "(no-reuse: never revalidates)")
    ok = pin_table.release(slot, incarnation)
    if not ok:
        return ("RETAINED", "release raced; retained fail-closed")
    return ("RELEASED", f"two-part proof accepted (p1={p1}, p2={p2})")


def collect_orphans(con, live_pins_fn, owner, budget, cursor=None):
    """Bounded resumable orphan collection. Budgets bound effort, never force
    deletion. Returns (per_item, new_cursor, more).

    RECTIFY 2026-09-19 sibling of the scan() stale-snapshot fix: the live
    set is read fresh per candidate, after its row was observed CANDIDATE.
    """
    rows = con.execute("SELECT artifact_id,incarnation,protected_gen FROM quarantine "
                       "WHERE state='CANDIDATE' AND artifact_id>? ORDER BY artifact_id",
                       (cursor or "",)).fetchall()
    out = []
    new_cursor = cursor
    for aid, inc, pg in rows[:budget]:
        new_cursor = aid
        try:
            live = set(live_pins_fn())
        except Exception:
            out.append((aid, CANDIDATE))  # uncertainty retains (stays CANDIDATE)
            continue
        if pg is not None and pg in live:
            con.execute("UPDATE quarantine SET state='RETAINED', reason=?, "
                        "updated_at=? WHERE artifact_id=?",
                        ("orphan-check: still pinned", time.time(), aid))
            out.append((aid, RETAINED))
        else:
            try:
                move_to_quarantine(con, aid, inc, W8_CAPS["max_quarantine_bytes"])
                out.append((aid, QUARANTINED))
            except Retryable:
                out.append((aid, CANDIDATE))
    return (out, new_cursor, len(rows) > budget)
