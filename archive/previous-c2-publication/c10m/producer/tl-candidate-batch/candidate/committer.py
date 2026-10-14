"""W1 committer + W2 publication (P1/P2/P7). Single commit txn establishes:
op outcome + dedup record + delta refs + exclusion refs + generation advance +
publication refs + artifact identity (I1.2), gated by fence check (first read)
+ P6 gate + P5 claim, all inside BEGIN IMMEDIATE."""
import json
import os
import time
import uuid as _uuid

from common import FailClosed, Reject, Retryable, raise_retryable_on_eio, sha256
import approval
import intake as _intake
import replay
from store import fsync_dir, fsync_file

# Terminal-marking set (S-01 P8 F6.1): Rejects with these codes land a
# TERMINAL_REJECTED row; all other Rejects propagate with nothing marked.
F6_TERMINAL_CODES = ("APPROVAL_MISSING", "REF_MALFORMED",
                       "STAGE1_NOT_ALLOWLISTED", "ENTRY1_MISSING_PA",
                       "POLICY_NOT_ACTIVE", "GRANT_INVALID", "POLICY_STALE",
                       "REF_MISUSE")

# Batch ceiling (Q1 authorization): at most 10 ops share one txn/COMMIT.
BATCH_MAX_OPS = 10


def _next_seq(con, birth, epoch):
    row = con.execute("SELECT COALESCE(MAX(seq),0) FROM commits WHERE birth=? AND epoch=?",
                      (birth, epoch)).fetchone()
    return int(row[0]) + 1


def current_triple(con):
    row = con.execute("SELECT birth,epoch,COALESCE(MAX(seq),0) FROM commits").fetchone()
    if row[0] is None:
        erow = con.execute("SELECT birth,epoch FROM epoch_row").fetchone()
        return (erow[0], int(erow[1]), 0)
    return (row[0], int(row[1]), int(row[2]))


def prepare_artifact(store, content_bytes, store_id):
    """P2 steps 1-2: bytes durable + fsync'd before any commit references them."""
    aid = f"a-{_uuid.uuid4().hex[:16]}"
    path = os.path.join(store.artdir, aid)
    try:
        with open(path, "wb") as f:
            f.write(content_bytes)
            f.flush()
            os.fsync(f.fileno())
        fsync_dir(store.artdir)
    except OSError as e:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise_retryable_on_eio(e, "prepare_artifact")
    return {"artifact_id": aid, "store_id": store_id,
            "extent": "whole-immutable-file", "length": len(content_bytes),
            "digest": "sha256:" + sha256(content_bytes)}


class Committer:
    def __init__(self, store, fence, caps=None, lease_owner=None):
        self.store = store
        self.fence = fence
        self.caps = caps or dict(_intake.CAPS)
        self.lease_owner = lease_owner or f"committer-{os.getpid()}"
        self.pointer = None  # optional shm pointer publisher (W5 link)

    def commit_op(self, op_id, kind, payload_obj, disclosure, approval_ref=None,
                  artifacts=(), scope=None, material=1):
        """Full path: reserve (outside txn) -> BEGIN IMMEDIATE -> fence check
        FIRST -> P6 gate -> P5 claim -> generation+publish -> COMMIT.
        Returns (outcome, triple)."""
        now = time.time()
        payload_s = json.dumps(payload_obj, sort_keys=True)
        # U-03 in-place slice: reserve and the commit txn share ONE connection
        # per op instead of opening two. Each op still opens and closes its
        # own connection on the way out, so last-close checkpointing (WAL-0)
        # and the no-cross-op-pooling shape are unchanged; only the second
        # fresh-connect cost inside the timed region is removed.
        con = self.store.open_db()
        try:
            _g, tok = _intake.reserve(con, len(payload_s), self.caps, now, kind)
        except BaseException:
            con.close()
            raise
        marked = False  # D12: terminal row already written by the early path
        try:
            _et = approval.early_terminal_for(kind, payload_obj, approval_ref)
            if _et is not None:
                # D12 early terminal: the verdict for this kind is derived from
                # the kind alone (approval.EARLY_TERMINAL, the gate's own
                # table), so the baseline's abort-then-record pair of txns
                # collapses into ONE txn on the op's ONE connection: the same
                # fence first-read, the same TERMINAL_REJECTED row, the same
                # Reject code+detail -- minus one BEGIN/ROLLBACK and one
                # fresh connection per denied op.
                con.execute("BEGIN IMMEDIATE;")
                try:
                    self.fence.check(con)  # FIRST read (R1c)
                    self._mark_terminal_row(con, op_id, payload_s, _et[0])
                    con.execute("COMMIT;")
                except BaseException:
                    if con.in_transaction:
                        con.execute("ROLLBACK;")
                    raise
                marked = True
                raise Reject(_et[0], _et[1])
            con.execute("BEGIN IMMEDIATE;")
            try:
                self.fence.check(con)  # FIRST read (R1c)
                approval.gate(con, kind, payload_obj, approval_ref,
                              disclosure, time.time())
                st, outcome, gen = replay.submit_claim(con, op_id, payload_s,
                                                      time.time(), self.lease_owner)
                if st == "COMMITTED":
                    con.execute("COMMIT;")
                    return (outcome, gen)  # idempotent: mint nothing (I1.4)
                if st == "TERMINAL":
                    con.execute("COMMIT;")
                    raise Reject("TERMINAL_REPLAY", outcome)
                # CLAIMED -> execute + commit
                seq = _next_seq(con, self.fence.birth, self.fence.epoch)
                triple = f"{self.fence.birth}:{self.fence.epoch}:{seq}"
                outcome = json.dumps({"committed": True, "seq": seq,
                                      "triple": triple, "kind": kind})
                # artifacts must already be durable (P2/I1.3): verify presence+digest
                for a in artifacts:
                    p = os.path.join(self.store.artdir, a["artifact_id"])
                    if not os.path.isfile(p):
                        raise Reject("ARTIFACT_NOT_DURABLE",
                                     f"{a['artifact_id']} not prepared")
                    with open(p, "rb") as f:
                        body = f.read()
                    if len(body) != a["length"] or \
                       "sha256:" + sha256(body) != a["digest"]:
                        raise Reject("ARTIFACT_NOT_DURABLE", "identity/length/digest gap")
                    con.execute("INSERT INTO artifacts(artifact_id,store_id,extent,length,"
                                "digest,durable,op_seq) VALUES(?,?,?,?,?,1,?)",
                                (a["artifact_id"], a["store_id"], a["extent"],
                                 a["length"], a["digest"], seq))
                    con.execute("INSERT INTO pub_refs(seq,artifact_id) VALUES(?,?)",
                                (seq, a["artifact_id"]))
                con.execute("INSERT INTO commits(seq,birth,epoch,op_id,kind,payload_hash,"
                            "outcome,disclosure,approval_ref,decided_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (seq, self.fence.birth, self.fence.epoch, op_id, kind,
                             sha256(payload_s.encode()), outcome,
                             json.dumps(disclosure, sort_keys=True),
                             json.dumps(approval_ref, sort_keys=True) if approval_ref else None,
                             time.time()))
                con.execute("INSERT INTO change_log(seq,scope,material) VALUES(?,?,?)",
                            (seq, scope or kind, material))
                replay.mark_committed(con, op_id, outcome, triple)
                con.execute("COMMIT;")
            except (Reject, Retryable):
                if con.in_transaction:
                    con.execute("ROLLBACK;")
                # P6 default-deny terminal recording (F6.1): missing/invalid ref on a
                # consequential op -> TERMINAL_REJECTED under a NEW txn (not the aborted one)
                raise
            except OSError as e:
                if con.in_transaction:
                    con.execute("ROLLBACK;")
                raise_retryable_on_eio(e, "commit_op")
            # F6.1 terminal marking happens outside the aborted txn (separate txn below)
            if self.pointer is not None:
                self.pointer.publish(self.fence.birth, self.fence.epoch, seq)
            return (outcome, triple)
        except Reject as r:
            if (not marked) and r.code in F6_TERMINAL_CODES and tok:
                # Same txn shape as before (new txn after the abort), but on
                # the op's already-open connection instead of a third one.
                self._mark_terminal_newtxn(op_id, payload_s, r.code, con=con)
            raise
        finally:
            _intake.release(tok)
            con.close()

    def _mark_terminal_row(self, con, op_id, payload_s, verdict):
        """F6.1 terminal record under the caller's open txn. Verbatim body of
        the original _mark_terminal_newtxn txn. Returns True iff a row was
        written (no-op over a pre-existing COMMITTED/TERMINAL_REJECTED
        row -- the caller must propagate that to reconcile)."""
        row = replay.lookup(con, op_id)
        if row is None:
            import replay as _r
            ts = _r.validate_id(op_id, time.time())
            con.execute("INSERT INTO dedup(op_id,payload_hash,outcome,state,"
                        "decided_generation,ts,lease_owner) VALUES(?,?,?,"
                        "'TERMINAL_REJECTED',NULL,?,?)",
                        (op_id, sha256(payload_s.encode()),
                         verdict, ts, self.lease_owner))
            return True
        elif row[3] == "IN_PROGRESS":
            replay.mark_terminal(con, op_id, verdict)
            return True
        return False

    def _mark_terminal_newtxn(self, op_id, payload_s, verdict, con=None):
        own = con is None
        if own:
            con = self.store.open_db()
        try:
            con.execute("BEGIN IMMEDIATE;")
            try:
                self.fence.check(con)
                self._mark_terminal_row(con, op_id, payload_s, verdict)
                con.execute("COMMIT;")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK;")
                raise
        finally:
            if own:
                con.close()



    # ---------------- batch transactions (Q1) ----------------
    def commit_batch(self, ops):
        """Commit up to BATCH_MAX_OPS serially-submitted ops in ONE txn/COMMIT.

        ops: list of 1..10 dicts {op_id, kind, payload, disclosure,
        approval_ref=None, artifacts=()}. Anything else -> ValueError
        before any effect.
        Returns (results, batch_info). results[i] per-op dict, status in
        committed|terminal|raised|retryable|not_attempted (see module doc
        of the batch manifest). batch_info carries path/abort/reserves.
        Per-op reserve (outside txn, in order), per-op fence-check (R1c),
        per-op gate+claim, seq in submission order, synchronous=FULL.
        Mid-batch error -> ROLLBACK (confirmed abort) -> fallback-serial
        via unmodified commit_op. Ambiguous COMMIT -> reconcile on a
        fresh conn before any replay. ACK (returned outcome) only after
        durability for that op's batch is established.
        """
        if not isinstance(ops, list) or not (1 <= len(ops) <= BATCH_MAX_OPS):
            raise ValueError("commit_batch: 1..%d ops required" % BATCH_MAX_OPS)
        norm = []
        for i, o in enumerate(ops):
            try:
                norm.append({"op_id": o["op_id"], "kind": o["kind"],
                             "payload": o["payload"], "disclosure": o["disclosure"],
                             "approval_ref": o.get("approval_ref"),
                             "artifacts": tuple(o.get("artifacts", ()))})
            except (KeyError, TypeError, AttributeError):
                raise ValueError("commit_batch: op %d malformed" % i)
        now = time.time()
        payloads = [json.dumps(o["payload"], sort_keys=True) for o in norm]
        con = self.store.open_db()
        toks = []
        try:
            # Stage 1: per-op reserve OUTSIDE any txn, in order (I9.2),
            # with staged admission accounting. Reserves see DURABLE state,
            # which does not advance during staging -- so without a staged
            # term a batch would over-admit beyond caps (e.g. 8 commits
            # against max 5). Each op is footprint-classified pre-txn
            # (pure early-terminal check + one read-only lookup; race-free:
            # single writer, no txn open, same thread through BEGIN).
            # Staged-over is deterministic (self-inflicted, no transient can
            # clear it), so it rejects immediately with an honest (staged)
            # qualifier -- the WAIT-to-deadline of P9 governs reserve()'s
            # durable-over path, which is preserved unchanged below.
            durable = _intake.accounting(con)
            staged_delta = staged_dedup = 0
            staged_ids = set()
            reserve_outcomes = []
            for i, o in enumerate(norm):
                if o["op_id"] in staged_ids:
                    # Second-in-batch occurrence is always a logical resubmit
                    # of the first (in-txn state is determined by it) or the
                    # batch aborts (counts moot): exact footprint is zero.
                    fp_delta, fp_dedup = 0, 0
                else:
                    fp_delta, fp_dedup = self._batch_footprint(con, o)
                    staged_ids.add(o["op_id"])
                eff_delta = durable["delta_entries"] + staged_delta
                eff_dedup = durable["dedup_rows"] + staged_dedup
                over_cap = None
                # Staged-immediate fires ONLY when the staged term is what
                # pushes over (durable < max <= durable+staged). When
                # durable ALONE is at cap, fall through to reserve() so the
                # op takes the honest P9 WAIT-to-deadline path with the
                # (deadline) flavor -- identical to serial commit_op.
                max_delta = self.caps["max_delta_entries"]
                max_dedup = self.caps["max_dedup_rows"]
                if (fp_delta and eff_delta >= max_delta
                        and durable["delta_entries"] < max_delta):
                    over_cap = "max_delta_entries"
                elif (fp_dedup and eff_dedup >= max_dedup
                        and durable["dedup_rows"] < max_dedup):
                    over_cap = "max_dedup_rows"
                if over_cap is not None:
                    maxv = self.caps[over_cap]
                    eff = eff_delta if over_cap == "max_delta_entries" \
                        else eff_dedup
                    retiring = o["kind"] in ("RETRACT", "SUPERSEDE_ATOMS")
                    if retiring and (maxv - eff) < self.caps[
                            "retirement_headroom_entries"]:
                        err = Retryable(
                            "REJECT_CAPACITY(headroom-exhausted): retryable; "
                            "blocking cause: staged delta incl. retirement "
                            "reserve")
                    else:
                        err = Retryable(
                            "REJECT_CAPACITY(staged): retryable; batch would "
                            "exceed %s (durable %d + staged %d >= max %d)"
                            % (over_cap,
                               durable["delta_entries"]
                               if over_cap == "max_delta_entries"
                               else durable["dedup_rows"],
                               staged_delta
                               if over_cap == "max_delta_entries"
                               else staged_dedup, maxv))
                    for t in toks:
                        _intake.release(t)
                    toks = []
                    return self._batch_not_attempted(
                        norm, reserve_outcomes, i, err)
                try:
                    _g, tok = _intake.reserve(con, len(payloads[i]), self.caps,
                                              now, o["kind"])
                except (Reject, Retryable) as e:
                    for t in toks:
                        _intake.release(t)
                    toks = []
                    return self._batch_not_attempted(
                        norm, reserve_outcomes, i, e)
                toks.append(tok)
                staged_delta += fp_delta
                staged_dedup += fp_dedup
                reserve_outcomes.append({"op_id": o["op_id"],
                                         "admission": "GRANT"})
            # Stage 2: one txn for the batch.
            con.execute("BEGIN IMMEDIATE;")
            results, wrote = [], []
            failed_at = None
            try:
                for idx, o in enumerate(norm):
                    failed_at = idx
                    res, w = self._batch_commit_one(con, o, payloads[idx], now)
                    results.append(res)
                    wrote.append(w)
            except (Reject, Retryable, OSError) as e:
                con.execute("ROLLBACK;")
                # Release batch reservations BEFORE fallback: the batch txn
                # is dead, and fallback reserves must see only durable
                # state (else, under tight max_reservations, every fallback
                # op WAIT-burns against our own dead tokens).
                for t in toks:
                    _intake.release(t)
                toks = []
                fb = self._batch_fallback_serial(norm)
                return fb, {"path": "fallback-serial",
                            "batch_size": len(norm),
                            "abort": {"op_index": failed_at,
                                      "op_id": norm[failed_at]["op_id"],
                                      "error_type": type(e).__name__,
                                      "message": str(e)},
                            "reserve_outcomes": reserve_outcomes}
            except BaseException:
                if con.in_transaction:
                    con.execute("ROLLBACK;")
                raise
            try:
                con.execute("COMMIT;")
            except Exception as e:
                # The batch txn is over (applied or ambiguous); its admission
                # tokens are dead. Release BEFORE reconcile so a fallback
                # re-drive reserves against durable state only (P9: the error
                # must reflect real capacity, not our own dead tokens).
                for t in toks:
                    _intake.release(t)
                toks = []
                return self._reconcile_commit(norm, payloads, results, wrote,
                                              reserve_outcomes, e)
            if self.pointer is not None:
                for res, w in zip(results, wrote):
                    if res["status"] == "committed" and w:
                        self.pointer.publish(self.fence.birth, self.fence.epoch,
                                             res["seq"])
            return results, {"path": "batch", "batch_size": len(norm),
                             "abort": None, "reserve_outcomes": reserve_outcomes}
        finally:
            for t in toks:
                _intake.release(t)
            con.close()

    def _batch_not_attempted(self, norm, reserve_outcomes, fail_idx, err):
        results = []
        for i, o in enumerate(norm):
            if i < fail_idx:
                results.append({"op_id": o["op_id"], "status": "not_attempted",
                                "reason": "batch pre-commit abort: %s: %s"
                                % (type(err).__name__, err)})
            elif i == fail_idx:
                results.append({"op_id": o["op_id"], "status": "retryable"
                                if isinstance(err, Retryable) else "raised",
                                "message": "%s: %s" % (type(err).__name__, err)})
            else:
                results.append({"op_id": o["op_id"], "status": "not_attempted",
                                "reason": "batch pre-commit abort"})
        return results, {"path": "pre-commit-abort", "batch_size": len(norm),
                         "abort": {"op_index": fail_idx,
                                   "op_id": norm[fail_idx]["op_id"],
                                   "error_type": type(err).__name__,
                                   "message": str(err)},
                         "reserve_outcomes": reserve_outcomes}

    def _batch_footprint(self, con, o):
        """Pre-txn row footprint (delta_rows, dedup_rows) for staged admission.

        Pure early-terminal check + one read-only lookup. Rules mirror the
        in-txn writer exactly: early-terminal with no pre-existing row
        writes one dedup row; with any pre-existing row it is a no-op;
        gate-path resubmits (COMMITTED/TERMINAL) write nothing; fresh
        claims and IN_PROGRESS rows count full (an IN_PROGRESS row either
        resolves to a write or aborts the batch, mooting counts).
        """
        _et = approval.early_terminal_for(kind=o["kind"],
                                          payload_obj=o["payload"],
                                          approval_ref=o["approval_ref"])
        row = replay.lookup(con, o["op_id"])
        if _et is not None:
            return (0, 0) if row is not None else (0, 1)
        if row is None:
            return (1, 1)
        if row[3] in ("COMMITTED", "TERMINAL_REJECTED"):
            return (0, 0)
        return (1, 1)

    def _batch_commit_one(self, con, o, payload_s, now):
        """One op inside the batch txn. Returns (result, wrote). Mirrors
        commit_op's in-txn section statement-for-statement (duplicated,
        not refactored, to leave the proven path untouched)."""
        op_id, kind = o["op_id"], o["kind"]
        self.fence.check(con)  # per-op FIRST read (R1c)
        _et = approval.early_terminal_for(kind, o["payload"], o["approval_ref"])
        if _et is not None:
            w = self._mark_terminal_row(con, op_id, payload_s, _et[0])
            return ({"op_id": op_id, "status": "terminal", "code": _et[0],
                     "detail": _et[1]}, w)
        approval.gate(con, kind, o["payload"], o["approval_ref"], o["disclosure"],
                      time.time())
        st, outcome, gen = replay.submit_claim(con, op_id, payload_s, time.time(),
                                               self.lease_owner)
        if st == "COMMITTED":
            return ({"op_id": op_id, "status": "committed", "outcome": outcome,
                     "triple": gen}, False)
        if st == "TERMINAL":
            return ({"op_id": op_id, "status": "raised", "code": "TERMINAL_REPLAY",
                     "detail": outcome}, False)
        seq = _next_seq(con, self.fence.birth, self.fence.epoch)
        triple = f"{self.fence.birth}:{self.fence.epoch}:{seq}"
        outcome = json.dumps({"committed": True, "seq": seq,
                              "triple": triple, "kind": kind})
        # artifacts must already be durable (P2/I1.3): verify presence+digest
        for a in o["artifacts"]:
            p = os.path.join(self.store.artdir, a["artifact_id"])
            if not os.path.isfile(p):
                raise Reject("ARTIFACT_NOT_DURABLE",
                             f"{a['artifact_id']} not prepared")
            with open(p, "rb") as f:
                body = f.read()
            if len(body) != a["length"] or \
               "sha256:" + sha256(body) != a["digest"]:
                raise Reject("ARTIFACT_NOT_DURABLE", "identity/length/digest gap")
            con.execute("INSERT INTO artifacts(artifact_id,store_id,extent,length,"
                        "digest,durable,op_seq) VALUES(?,?,?,?,?,1,?)",
                        (a["artifact_id"], a["store_id"], a["extent"],
                         a["length"], a["digest"], seq))
            con.execute("INSERT INTO pub_refs(seq,artifact_id) VALUES(?,?)",
                        (seq, a["artifact_id"]))
        con.execute("INSERT INTO commits("
                    "seq,birth,epoch,op_id,kind,payload_hash,outcome,"
                    "disclosure,approval_ref,decided_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (seq, self.fence.birth, self.fence.epoch, op_id, kind,
                     sha256(payload_s.encode()), outcome,
                     json.dumps(o["disclosure"], sort_keys=True),
                     json.dumps(o["approval_ref"], sort_keys=True)
                     if o["approval_ref"] else None, time.time()))
        scope = kind
        material = 1
        con.execute("INSERT INTO change_log(seq,scope,material) VALUES(?,?,?)",
                    (seq, scope or kind, material))
        replay.mark_committed(con, op_id, outcome, triple)
        return ({"op_id": op_id, "status": "committed", "outcome": outcome,
                 "triple": triple, "seq": seq}, True)

    def _batch_fallback_serial(self, norm):
        """Re-drive every batch op via unmodified commit_op (abort already
        confirmed: the batch txn rolled back, nothing durable from it).
        Per-op outcomes mirror serial caller-observed behavior exactly."""
        out = []
        for o in norm:
            try:
                outcome, triple = self.commit_op(
                    o["op_id"], o["kind"], o["payload"], o["disclosure"],
                    o["approval_ref"], o["artifacts"])
                out.append({"op_id": o["op_id"], "status": "committed",
                            "outcome": outcome, "triple": triple})
            except Reject as r:
                st = "terminal" if r.code in F6_TERMINAL_CODES else "raised"
                out.append({"op_id": o["op_id"], "status": st, "code": r.code,
                            "detail": r.detail})
            except Retryable as r:
                out.append({"op_id": o["op_id"], "status": "retryable",
                            "message": str(r)})
        return out

    def _reconcile_commit(self, norm, payloads, results, wrote,
                          reserve_outcomes, commit_error):
        """Ambiguous COMMIT: reconcile durable state on a FRESH conn before
        any replay. All-wrote-present -> committed (response lost, outcomes
        stand). All-absent -> fallback-serial. Mixed -> FAIL-STOP (impossible
        under atomic COMMIT; persisted via the raised evidence)."""
        checks = []
        for o, ps, res, w in zip(norm, payloads, results, wrote):
            if not w:
                continue  # read-only op: pre-existing state
            checks.append({"op_id": o["op_id"], "payload_s": ps,
                           "expect": ("committed"
                                      if res["status"] == "committed"
                                      else "terminal"),
                           "code": res.get("code")})
        con2 = self.store.open_db()
        try:
            verdicts = self._reconcile_batch(con2, checks)
        finally:
            con2.close()
        info_base = {"batch_size": len(norm),
                     "commit_error": "%s: %s" % (type(commit_error).__name__,
                                                 commit_error),
                     "verdicts": verdicts, "reserve_outcomes": reserve_outcomes}
        if not checks:
            info = dict(info_base, path="reconciled-readonly", abort=None)
            return results, info
        matched = sum(1 for c in checks
                      if verdicts[c["op_id"]]["status"] == "match")
        absent = sum(1 for c in checks
                     if verdicts[c["op_id"]]["status"] == "absent")
        if matched == len(checks):
            info = dict(info_base, path="reconciled-committed", abort=None)
            return results, info
        if absent == len(checks):
            fb = self._batch_fallback_serial(norm)
            info = dict(info_base, path="reconciled-absent",
                        abort={"op_index": None, "op_id": None,
                               "error_type": type(commit_error).__name__,
                               "message": str(commit_error)})
            return fb, info
        raise FailClosed("batch reconcile mixed state (impossible): %r"
                         % (verdicts,))

    def _reconcile_batch(self, con, items):
        """Read-only reconcile read. items: op_id strings or dicts
        {op_id, payload_s?, expect?} (expect defaults "committed").
        Returns {op_id: {"status": match|absent|mismatch, ...}} with
        reconstructed outcome/triple on match. Never writes. Caller
        manages con (use a fresh conn after a commit error)."""
        out = {}
        for it in items:
            if isinstance(it, str):
                oid, ps, exp, code = it, None, "committed", None
            else:
                oid = it["op_id"]
                ps, exp, code = (it.get("payload_s"), it.get("expect", "committed"),
                                 it.get("code"))
            row = replay.lookup(con, oid)
            if row is None:
                out[oid] = {"status": "absent"}
                continue
            _id, ph, outcome, state, gen = row[0], row[1], row[2], row[3], row[4]
            if exp == "committed":
                hok = ps is None or ph == sha256(ps.encode())
                if state == "COMMITTED" and hok:
                    out[oid] = {"status": "match", "outcome": outcome,
                                "triple": gen}
                else:
                    out[oid] = {"status": "mismatch",
                                "detail": "state=%s hash_ok=%s" % (state, hok)}
            else:
                if state == "TERMINAL_REJECTED" and (code is None or outcome == code):
                    out[oid] = {"status": "match", "outcome": outcome,
                                "triple": gen}
                else:
                    out[oid] = {"status": "mismatch",
                                "detail": "state=%s outcome=%s" % (state, outcome)}
        return out

    def notify(self, op_id):
        """ACK path: outcome from dedup + queryable-path condition (§1)."""
        con = self.store.open_db()
        try:
            row = replay.lookup(con, op_id)
            if row is None or row[3] != "COMMITTED":
                raise Retryable(f"WAIT: {op_id} has no committed outcome")
            outcome, gen = row[2], row[4]
            # queryable-path condition: committed content servable (delta coverage)
            o = json.loads(outcome)
            seq = o.get("seq")
            c = con.execute("SELECT outcome FROM commits WHERE seq=?", (seq,)).fetchone()
            if c is None:
                raise Retryable("WAIT: commit not yet queryable")
            return (outcome, gen)
        finally:
            con.close()

    def read_at(self, seq):
        """Serve committed state at seq (delta coverage for committed content)."""
        con = self.store.open_db()
        try:
            rows = con.execute("SELECT seq,op_id,kind,outcome FROM commits WHERE seq<=? "
                               "ORDER BY seq", (seq,)).fetchall()
            return rows
        finally:
            con.close()
