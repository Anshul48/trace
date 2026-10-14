"""P6 approval gate + grant records (default-deny, TOCTOU, P6-C1 lifetime).
Runs INSIDE the commit txn (validation bound through commit). Policy v0:
effective Stage-1 allowlist admits nothing (Entry-1 needs verified P-A,
absent; Entries 2-3 excluded)."""
import json
import time

from common import Reject

# Experimental values (D-12), recorded per run.
TOCTOU_WORK_BOUND = 10000  # max change_log rows scanned in recheck

# UQ1 closed act-class vocabulary for grants.
ACT_CLASSES = ("stage2_auto_accept", "urgent_lane", "stop_and_drain")

# Kinds. RETRACT/retiring always consequential. Plain EDIT/ACCEPT_* with no
# retirement effect and passing checks are non-consequential (no ref needed).
ALWAYS_CONSEQUENTIAL = ("RETRACT", "SUPERSEDE_ATOMS")
ENTRY1_KIND = "FOLD_PHYSICAL"
ENTRY2_KIND = "ORPHAN_COLLECT"
ENTRY3_KIND = "DESCRIPTOR_REFRESH"


# D12 early-terminal table: the P6 verdict for these kinds follows from the
# kind ALONE -- no table read, no policy/grant/TOCTOU state -- so the same
# Reject (code and message) can be raised before BEGIN IMMEDIATE without
# changing the verdict. gate() raises from this same table, so the early
# pre-check in committer.commit_op provably cannot diverge from the gate.
EARLY_TERMINAL = {
    ENTRY1_KIND: ("ENTRY1_MISSING_PA",
                  "Entry-1 ref rejected: P-A unverified (D-23)"),
    ENTRY2_KIND: ("POLICY_NOT_ACTIVE",
                  f"{ENTRY2_KIND} excluded from Stage-1 (D-23)"),
    ENTRY3_KIND: ("POLICY_NOT_ACTIVE",
                  f"{ENTRY3_KIND} excluded from Stage-1 (D-23)"),
}


def early_terminal_code(kind):
    """(code, detail) when the P6 verdict is kind-derived and table-free."""
    return EARLY_TERMINAL.get(kind)


def early_terminal_for(kind, payload_obj, approval_ref):
    """(code, detail) when the P6 verdict is table-free; else None.

    D12 (kind-alone) + D12b (kind+payload+ref-presence). classify() is
    pure python (no DB), so a consequential verdict with ref absent, or
    a REF_MISUSE verdict, needs no table state. gate() raises from this
    same function, so early checks provably cannot diverge from the gate.
    """
    _et = EARLY_TERMINAL.get(kind)
    if _et is not None:
        return _et
    if not classify(kind, payload_obj):
        if approval_ref is not None:
            return ("REF_MISUSE",
                    "non-consequential op must not carry approval_ref")
        return None
    if approval_ref is None:
        return ("APPROVAL_MISSING", "consequential op without approval_ref")
    return None


def classify(kind, payload_obj):
    """Consequential unless non-retiring known kind with checks passing."""
    if kind in ALWAYS_CONSEQUENTIAL:
        return True
    if kind in (ENTRY1_KIND, ENTRY2_KIND, ENTRY3_KIND):
        return True  # Stage-1 refs; rejected per D-23 until P-A / never for 2-3
    if kind in ("EDIT", "ACCEPT_ATOMS", "ACCEPT_DELTA"):
        # retiring effect? payload flag 'retires' names retired evidence/assertions
        if payload_obj.get("retires"):
            return True
        return False
    return True  # unknown kind -> consequential


def current_policy(con):
    row = con.execute("SELECT version,allowlist FROM policy WHERE active=1").fetchone()
    if row is None:
        raise Reject("POLICY_MISSING", "no active policy")
    return row[0], json.loads(row[1])


def get_grant(con, grant_id):
    return con.execute("SELECT grant_id,scope,limits,revoked,policy_version,expires_at,"
                       "created_at FROM grants WHERE grant_id=?", (grant_id,)).fetchone()


def toctou_recheck(con, pinned_triple, scope, now):
    """I6.2: no material change in (A,C] over assessed scope. C = current max seq
    within the pinned (birth,epoch); birth/epoch differ => STALE_ASSESSMENT."""
    cur = con.execute("SELECT birth,epoch,COALESCE(MAX(seq),0) FROM commits").fetchone()
    if cur[0] is None:
        cur_max = (None, None, 0)
    else:
        cur_max = (cur[0], int(cur[1]), int(cur[2]))
    try:
        pb, pe, pa = pinned_triple
        pe, pa = int(pe), int(pa)
    except Exception:
        raise Reject("STALE_ASSESSMENT", "unparseable pinned generation")
    if cur_max[0] is not None and (cur_max[0] != pb or cur_max[1] != pe):
        raise Reject("STALE_ASSESSMENT", "birth/epoch differs: no cross-epoch order")
    lo, hi = pa, cur_max[2]
    if hi - lo > TOCTOU_WORK_BOUND:
        raise Reject("STALE_ASSESSMENT", "recheck work bound exceeded: fail closed")
    if lo >= hi:
        return
    rows = con.execute("SELECT COUNT(*) FROM change_log WHERE seq>? AND seq<=? "
                       "AND scope=? AND material=1", (lo, hi, scope)).fetchone()
    if rows[0]:
        raise Reject("STALE_ASSESSMENT", f"{rows[0]} material change(s) in (A,C]")


def gate(con, kind, payload_obj, approval_ref, disclosure, now):
    """P6 commit gate. Raises Reject on any failure. Returns 'ok' note.
    approval_ref: None or dict with stage/pinned_generation/..."""
    _et = early_terminal_for(kind, payload_obj, approval_ref)
    if _et is not None:
        raise Reject(_et[0], _et[1])
    if not classify(kind, payload_obj):
        return "non-consequential: no ref required"
    try:
        stage = int(approval_ref["stage"])
    except Exception:
        raise Reject("REF_MALFORMED", "approval_ref has no stage")
    if stage == 1:
        _gate_stage1(con, kind, approval_ref)
    elif stage == 2:
        _gate_stage2(con, kind, payload_obj, approval_ref, now)
    elif stage == 3:
        _gate_stage3(con, kind, payload_obj, approval_ref, now)
    else:
        raise Reject("REF_MALFORMED", f"unknown stage {stage}")
    return f"stage-{stage} ref accepted"


def _pinned_policy_ok(con, approval_ref, record_version_field="policy_version"):
    cur_ver, _allow = current_policy(con)
    rec_ver = approval_ref.get(record_version_field)
    if rec_ver != cur_ver:
        raise Reject("POLICY_STALE", f"ref under {rec_ver}, current is {cur_ver}")


def _gate_stage1(con, kind, ref):
    _pinned_policy_ok(con, ref)
    _cur, allow = current_policy(con)
    if kind not in allow:
        raise Reject("STAGE1_NOT_ALLOWLISTED", f"{kind} not on v{ _cur} allowlist")


def _gate_stage2(con, kind, payload_obj, ref, now):
    _pinned_policy_ok(con, ref)
    try:
        pinned = tuple(ref["pinned_generation"])
        diff_hash = ref["assessment"]["diff_hash"]
        appr = ref["approval"]
    except Exception:
        raise Reject("REF_MALFORMED", "stage-2 ref missing pinned_generation/assessment/approval")
    from common import sha256
    if diff_hash != sha256(json.dumps(payload_obj, sort_keys=True).encode()):
        raise Reject("REF_MALFORMED", "diff_hash does not cover op payload")
    if not isinstance(appr, dict) or "type" not in appr:
        raise Reject("REF_MALFORMED", "no approval leg (llm output is never approval)")
    if appr["type"] == "user":
        if not appr.get("approval_id"):
            raise Reject("REF_MALFORMED", "user approval without approval_id")
    elif appr["type"] == "grant":
        _check_grant(con, appr.get("grant_id"), kind, now, ref)
    else:
        raise Reject("REF_MALFORMED", f"unknown approval type {appr.get('type')}")
    scope = ref.get("scope", kind)
    toctou_recheck(con, pinned, scope, now)


def _gate_stage3(con, kind, payload_obj, ref, now):
    _pinned_policy_ok(con, ref)
    if not ref.get("decision_id"):
        raise Reject("REF_MALFORMED", "stage-3 ref without decision_id")
    lane = ref.get("lane_or_grant_id")
    if lane:
        _check_grant(con, lane, kind, now, ref)
    scope = ref.get("scope", kind)
    pinned = tuple(ref["pinned_generation"])
    toctou_recheck(con, pinned, scope, now)


def _check_grant(con, grant_id, kind, now, ref):
    g = get_grant(con, grant_id) if grant_id else None
    if g is None:
        raise Reject("GRANT_INVALID", f"grant {grant_id} unknown")
    _id, scope, limits, revoked, gver, exp, _c = g
    if revoked:
        raise Reject("GRANT_INVALID", f"grant {grant_id} revoked")
    if now > float(exp):
        raise Reject("GRANT_INVALID", f"grant {grant_id} expired (P6-C1 lifetime)")
    cur_ver, _a = current_policy(con)
    if gver != cur_ver:
        raise Reject("POLICY_STALE", f"grant under {gver}, current {cur_ver}")
    acts = scope.split(",")
    need = "stage2_auto_accept" if ref.get("stage") == 2 else None
    if scope != "*" and kind not in acts and need not in acts:
        raise Reject("GRANT_INVALID", f"grant {grant_id} scope {scope} covers not {kind}")
    # limits opaque under policy_version: evaluated, never ad-hoc read. v0: none.
    return True
