"""P3 recovery + R1(b) atomic takeover. IMPLEMENTED BUT HELD: execution
refuses unless the S-01 reconciliation is recorded (env TL_S01_RECONCILED=1).
This makes silent execution of held paths impossible (BI-1)."""
import os

from common import HeldError, Reject


def _reconciliation_recorded():
    return os.environ.get("TL_S01_RECONCILED") == "1"


def restore(store_root):
    """P3 Recovery.restore: fence acquire -> authoritative G -> step-3
    validation -> queryable path -> lease resolution -> accounting rebuild ->
    publish+admit. Includes the R1(b) epoch-bump transaction on unclean restart.
    HELD: refuses without recorded reconciliation."""
    if not _reconciliation_recorded():
        raise HeldError(
            "Recovery.restore HELD: bg S-01 reconciliation not recorded "
            "(coordinator order 2026-09-19). Concrete conflict would return "
            "to coordinator/user; never silent proceed.")
    return _restore_inner(store_root)


def _restore_inner(store_root):
    from store import Store, Fence
    store = Store(store_root)
    fence = Fence(store)
    birth, epoch = fence.acquire()  # P3 step 1; fail closed if held
    con = store.open_db()
    try:
        # step 2: authoritative G
        row = con.execute("SELECT birth,epoch,COALESCE(MAX(seq),0) FROM commits").fetchone()
        # unclean restart => epoch bump in ONE txn before admission (R1b/P7)
        con.execute("BEGIN IMMEDIATE;")
        try:
            erow = con.execute("SELECT birth,epoch FROM epoch_row").fetchone()
            if erow is None or erow[0] != birth:
                raise Exception("epoch row missing/birth mismatch: fail closed")
            if int(erow[1]) < epoch:
                raise Exception("epoch regression: fail closed")
            con.execute("UPDATE epoch_row SET epoch=epoch+1")
            con.execute("COMMIT;")
        except Exception:
            con.execute("ROLLBACK;")
            raise
        # P3 steps 3-7 (REM: contract-entailed bodies; HELD gate above untouched).
        # R3 step-3 validation: exactly one bump, sole holder, meta intact.
        vrow = con.execute("SELECT birth,epoch FROM epoch_row").fetchone()
        mrow = con.execute("SELECT v FROM meta WHERE k='lock_dev'").fetchone()
        mrow2 = con.execute("SELECT v FROM meta WHERE k='lock_ino'").fetchone()
        if vrow is None or vrow[0] != birth or int(vrow[1]) != epoch + 1:
            raise Reject("STEP3_VALIDATION",
                         "epoch row mismatch post-bump: fail closed")
        if mrow is None or mrow2 is None:
            raise Reject("STEP3_VALIDATION",
                         "fence identity rows absent: fail closed")
        step3 = {"birth": birth, "epoch": int(vrow[1])}
        # R4 queryable path: serving reads function on fresh statements.
        step4 = {
            "commits": con.execute("SELECT COUNT(*) FROM commits").fetchone()[0],
            "dedup": con.execute("SELECT COUNT(*) FROM dedup").fetchone()[0],
            "intake": con.execute("SELECT COUNT(*) FROM intake").fetchone()[0],
        }
        # R5 lease resolution: exclusive fence + bumped epoch prove all other
        # owners dead; IN_PROGRESS becomes reclaimable ABANDONED (replay
        # submit_claim re-claims same id+payload; mismatches still reject).
        converted = [r[0] for r in con.execute(
            "SELECT op_id FROM dedup WHERE state='IN_PROGRESS'")]
        con.execute("BEGIN IMMEDIATE;")
        try:
            con.execute("UPDATE dedup SET state='ABANDONED' "
                        "WHERE state='IN_PROGRESS'")
            con.execute("COMMIT;")
        except Exception:
            con.execute("ROLLBACK;")
            raise
        step5 = {"abandoned": converted}
        # R6 accounting rebuild: recompute from durable tables (adopted rebuild).
        # U-02: the rebuild is still a true recount (recount re-derives every
        # count with the pre-U-02 COUNT(*) definition and re-seeds the O(1)
        # ledger); the returned record keeps its previous shape.
        import intake as _intake
        _intake.recount(con)
        step6 = _intake.accounting(con)
        # R7 publish+admit: epoch_row is the publication; admit the successor.
        return {"authoritative": row, "step3": step3, "queryable": step4,
                "step5": step5, "step6": step6,
                "admitted": {"birth": birth, "epoch": int(vrow[1])},
                "note": "restore executed post-reconciliation"}
    finally:
        con.close()
