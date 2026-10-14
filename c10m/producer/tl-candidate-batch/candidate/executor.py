"""Checkpoint executor (CEx) — proposal §2 traced build, 9 items + no-lag-signal rule.

Traced items:
 1. Executor.tick as committer-thread subroutine (EXEC-1 A; DESIGN:44-49).
 2. Checkpoint row in the commit DB, generation triple (EXEC-2 A; ICEx.1).
 3. Single txn advancing checkpoint + E + deletes in ONE transactional
    database (EXEC-3 A; boundary ADOPT10:218-224). External storage cleanup
    explicitly NOT covered.
 4. EXEC-4 C scheduling: frozen opportunity set {(a),(d),(e)} + re-evaluation
    events {(i)-(iv)} + dedup-row watermark (NOT WAL bytes) + no-busy-retry
    (AMEND:89-117); ordered scan + volatile cursor + full-pass exhaustion +
    anti-starvation (AMEND:68-87); pressure-vs-eligibility split +
    zero-delete rule (AMEND:38-66); WAL-reducing op named as the engine WAL
    checkpoint/truncate, never Replay.prune (AMEND:50-57).
 5. Accounting examined + deleted + internal_touches, ADDITIVE D-21 metric,
    count-or-bound per component (AMEND:124-138); time/resource ceilings as
    co-bound, atomic-or-abort tick (AMEND:139-146); per-tick diagnostics,
    no batch-to-backlog inference (AMEND:148-159).
 6. Read-only diagnostic accessor (EXEC-6 B; no attach-shared lock, no
    correctness dependency on attach/commit/ACK paths).
 7. Executor writes fenced (ICEx.5); P1 single-committer preserved — the
    executor NEVER acquires/releases the fence itself (shares the
    committer's fence object); no second committer, no fence-gap window.
 8. Crash semantics FCEx.1/FCEx.2 (atomic txn: uncommitted effects
    invisible; committed prune stands) + FCEx.5 fence-loss (abort, no
    partial effects).
 9. Falsifier enforcement surface: retreat/monotonicity checks inline
    (retreat attempt refused); all other falsifiers asserted by probes.
NO lag signal: EXEC-5(i) backpressure-only; lag-vs-retained distinguished
via diagnostics + P9 records only. No new control mechanism exists here.

Frozen values (coordinator-confirmed 2026-09-20, FREEZE-CHECKLIST-PROPOSED.md):
scan order (ts_ms, op_id); volatile cursor; opportunities (a) T_cad=100ms,
(d) W_row=1000 dedup rows, (e) explicit; events (i)-(iv); N_ex=500,
N_del=200, K_adapt=2/row; T_tick=5s, B_read=64MiB, B_write=16MiB.

Mechanical encodings of adopted terms (no new semantics):
- `checkpoint` table: EXEC-2 A adopted row (birth, epoch, seq), single row.
- `recovery_holds(op_id, ...)`: encodes the adopted predicate term "which
  no recovery scan requires" (P5/DESIGN:50-60) and "needed recovery
  records". Writers = recovery-scan side (probes drive it here; production
  scan integration is future work — the hold functions are the seam).
- `meta.scan_rev`: encodes the frozen view's "scan-requirements revision".
- REJECTED-attempt tombstones: NO tombstone table exists in the adopted
  Stage-A base; the P5 tombstone term is VACUOUS in this build (introducing
  a new store would be machinery without a falsifier). Documented, not silent.
- IN_PROGRESS rows are NEVER deleted (covers live claims conservatively;
  ABANDONED conversion is P3/HELD recovery territory, not the executor's).
"""
import sqlite3
import time

from common import FailClosed, Reject, Retryable
import replay

# ---- frozen values (AMEND §3 checklist, coordinator-confirmed) ----
T_CAD_S = 0.100          # (a) periodic cadence slot period
W_ROW = 1000             # (d) dedup-row watermark (NOT WAL bytes)
OPPORTUNITIES = ("a", "d", "e")  # (b)/(c) excluded: never fire
N_EX = 500               # rows_examined hard cap per tick
N_DEL = 200              # rows_deleted hard cap per tick
K_ADAPT = 2              # adapter-internal overhead bound per examined row
T_TICK_S = 5.0           # per-tick wall ceiling
B_READ = 64 * 1024**2    # per-tick bytes-read ceiling
B_WRITE = 16 * 1024**2   # per-tick bytes-written ceiling
TICK_BUSY_TIMEOUT_S = 1.0  # tick refuses on commit-path contention (never wedges)

EVENTS = ("i", "ii", "iii", "iv")

SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoint(birth TEXT NOT NULL, epoch INTEGER NOT NULL,
  seq INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS recovery_holds(op_id TEXT PRIMARY KEY,
  holder TEXT NOT NULL, created_at REAL NOT NULL);
"""


def ensure_schema(con):
    """Idempotent executor schema + single-row init. Runs outside tick txns."""
    con.executescript(SCHEMA)
    if con.execute("SELECT COUNT(*) FROM checkpoint").fetchone()[0] == 0:
        erow = con.execute("SELECT birth,epoch FROM epoch_row").fetchone()
        if erow is None:
            raise FailClosed("epoch row missing: cannot init checkpoint row")
        con.execute("INSERT INTO checkpoint(birth,epoch,seq) VALUES(?,?,0)",
                    (erow[0], int(erow[1])))
        con.commit()
    if con.execute("SELECT v FROM meta WHERE k='scan_rev'").fetchone() is None:
        con.execute("INSERT INTO meta(k,v) VALUES('scan_rev','0')")
        con.commit()


def _parse_triple(s):
    try:
        b, e, q = s.split(":")
        return (b, int(e), int(q))
    except (ValueError, AttributeError):
        return None


def engine_wal_checkpoint_truncate(store):
    """THE operation that can reduce WAL bytes (AMEND §1.1): the commit-engine
    WAL checkpoint/truncate — a physical engine operation distinct from both
    the TL durable checkpoint (generation marker) and dedup-row pruning.
    This is the ONLY wal_checkpoint call site in the codebase; tick()/prune
    never call it and never claim WAL reduction (falsifier A1)."""
    con = store.open_db()
    try:
        return con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    finally:
        con.close()


class CheckpointView:
    """EXEC-6 B read-only diagnostic accessor for probes/overlap evidence.
    Own short-lived read connection per call; acquires NO fence, NO
    committer.lock, NO shm/pin-table lock; no correctness dependency on
    attach/commit/ACK paths (a wrong/slow read changes no verdict)."""

    @staticmethod
    def current(store):
        con = store.open_db()
        try:
            tables = {r[0] for r in
                      con.execute("SELECT name FROM sqlite_master WHERE "
                                  "type='table'")}
            ck = con.execute("SELECT birth,epoch,seq FROM checkpoint"
                             ).fetchone() if "checkpoint" in tables else None
            e = con.execute("SELECT v FROM meta WHERE k='E'").fetchone()
            sr = con.execute("SELECT v FROM meta WHERE k='scan_rev'"
                             ).fetchone() if "checkpoint" in tables else None
            nh = con.execute("SELECT COUNT(*) FROM recovery_holds"
                             ).fetchone()[0] if "recovery_holds" in tables else 0
            nd = con.execute("SELECT COUNT(*) FROM dedup").fetchone()[0]
            return {"checkpoint": {"birth": ck[0], "epoch": int(ck[1]),
                                   "seq": int(ck[2])} if ck else None,
                    "E": float(e[0]) if e else 0.0,
                    "scan_rev": int(sr[0]) if sr else 0,
                    "holds": int(nh), "dedup_rows": int(nd)}
        finally:
            con.close()


class Executor:
    """Committer-thread subroutine (EXEC-1 A). Shares the committer's Fence
    object; never acquires/releases it. Construct per fence-holding process."""

    def __init__(self, store, fence):
        self.store = store
        self.fence = fence
        con = store.open_db()
        try:
            ensure_schema(con)
        finally:
            con.close()
        # Volatile pass/cursor state (cursor void after crash -> new pass).
        self._pass_id = 0
        self._view = None          # (E, (birth,epoch,seq), scan_rev)
        self._cursor = None        # last-examined (ts, op_id) key
        self._pass_deletions = 0
        self._pass_open_events = []  # internal: notified + detected + (iv)
        # No-busy-retry guard state (AMEND §1.4; falsifier A4). The executor
        # is one-shot (never self-fires); the guard additionally refuses
        # caller-driven unbounded immediate re-tick chains after a
        # no-op/zero-delete tick, while preserving (a)-slot revisit (else
        # time-created eligibility would starve — AMEND:108-112).
        self._ext_pending = False  # notify_event()/add_hold() since last tick
        self._last_progress = None  # None (first tick) | True | False
        self._last_a_slot = None   # cadence slot of last executed (a) tick
        self._last_d_count = None  # dedup count at last executed (d) tick
        self._last_outcome = None  # 'work' | 'noop' | 'zero-delete'
        self.txns_attempted = 0    # instrumentation: DB txns opened by ticks
        self.d_reads = 0           # instrumentation: read-only (d) checks
        self._test_hook = None     # probe instrumentation: called inside tick txn
        self.history = []          # per-tick diagnostic records (volatile)

    # ---- opportunity/event interface (frozen sets) ----
    def notify_event(self, ev):
        """Record a re-evaluation event (i)-(iv). Anything else: refuse."""
        if ev not in EVENTS:
            raise FailClosed(f"untraced re-evaluation event {ev!r}: refused")
        self._pass_open_events.append(ev)
        self._ext_pending = True

    # ---- recovery-hold seam (fenced; recovery-scan side writers) ----
    def add_hold(self, op_id, holder):
        self._require_fence()
        con = self.store.open_db()
        try:
            con.execute("BEGIN IMMEDIATE;")
            try:
                self.fence.check(con)
                con.execute("INSERT OR IGNORE INTO recovery_holds(op_id,holder,"
                            "created_at) VALUES(?,?,?)", (op_id, holder, time.time()))
                con.execute("UPDATE meta SET v=CAST(v AS INTEGER)+1 "
                            "WHERE k='scan_rev'")
                con.execute("COMMIT;")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK;")
                raise
        finally:
            con.close()
        self._ext_pending = True

    def release_hold(self, op_id):
        self._require_fence()
        con = self.store.open_db()
        try:
            con.execute("BEGIN IMMEDIATE;")
            try:
                self.fence.check(con)
                con.execute("DELETE FROM recovery_holds WHERE op_id=?", (op_id,))
                con.execute("UPDATE meta SET v=CAST(v AS INTEGER)+1 "
                            "WHERE k='scan_rev'")
                con.execute("COMMIT;")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK;")
                raise
        finally:
            con.close()
        self.notify_event("iii")

    def _require_fence(self):
        if self.fence.fd is None:
            raise Retryable("fence unavailable: refuse, never partial")

    def _open_tick_con(self):
        con = sqlite3.connect(self.store.db_path, timeout=TICK_BUSY_TIMEOUT_S,
                              isolation_level=None)
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=FULL;")
        return con

    def _classify(self, row, view_e, ckpt, holds):
        """P5 prune predicate under the frozen view. Returns
        'eligible' | 'protected' | 'ineligible'. Uncertainty retains."""
        op_id, _ph, _oc, state, decided_gen, ts, _lo = row
        if state == "IN_PROGRESS":
            return "protected"  # live claims + P3-pending rows: never delete
        if state == "COMMITTED":
            if op_id in holds:
                return "protected"  # needed recovery record
            t = _parse_triple(decided_gen) if decided_gen else None
            if t is None:
                return "protected"  # malformed identity: uncertainty retains
            _b, _e, q = t
            same_gen = (_b == ckpt[0] and _e == ckpt[1])
            if not (ts < view_e and same_gen and q <= ckpt[2]):
                # ts>=E or generation beyond checkpoint: not yet eligible
                return "ineligible"
            return "eligible"
        if state in ("ABANDONED", "TERMINAL_REJECTED"):
            # TERMINAL_REJECTED prunable once ts<E (subsume rule ->
            # REJECT_EXPIRED after); terminal identities with ts>=E protected.
            return "eligible" if ts < view_e else ("protected"
                    if state == "TERMINAL_REJECTED" else "ineligible")
        return "protected"  # unknown state: uncertainty retains

    def tick(self, opportunity, now=None):
        """One bounded unit (EXEC-1 A). opportunity ∈ {a,d,e} else refuse.
        Returns the per-tick diagnostic record. Raises Retryable on
        fence-unavailable / contention / busy-retry-idle refusal (no DB
        effects); Reject(STALE_EPOCH) on fence mismatch (FCEx.5 abort)."""
        if opportunity not in OPPORTUNITIES:
            raise FailClosed(f"untraced tick opportunity {opportunity!r}: "
                             f"frozen set is {OPPORTUNITIES}")
        now = time.time() if now is None else now
        # No-busy-retry guard (AMEND §1.4; falsifier A4). Execute iff first
        # tick, external event pending, last tick made progress, the pass is
        # incomplete (segments remain), or the opportunity itself is fresh
        # ((a) in a new cadence slot; (d) with a changed watermark level).
        # Otherwise idle WITHOUT opening a txn.
        pass_incomplete = self._cursor is not None
        fresh = (self._last_progress is None or self._ext_pending
                 or self._last_progress or pass_incomplete)
        if not fresh and opportunity == "a":
            slot = int(now / T_CAD_S)
            fresh = (self._last_a_slot is None or slot != self._last_a_slot)
        if not fresh and opportunity == "d":
            con0 = self.store.open_db()
            try:
                n = int(con0.execute("SELECT COUNT(*) FROM dedup"
                                     ).fetchone()[0])
            finally:
                con0.close()
            self.d_reads += 1
            fresh = (n >= W_ROW and n != self._last_d_count)
            if fresh:
                self._last_d_count = n
        if not fresh:
            return {"tick": False, "reason": "idle: no new opportunity/event "
                    "since no-op/zero-delete tick (no-busy-retry)",
                    "opportunity": opportunity,
                    "txns_attempted": self.txns_attempted}
        if opportunity == "a":
            self._last_a_slot = int(now / T_CAD_S)
        if opportunity == "d":
            con0 = self.store.open_db()
            try:
                self._last_d_count = int(con0.execute("SELECT COUNT(*) FROM "
                                                      "dedup").fetchone()[0])
            finally:
                con0.close()
        self._ext_pending = False
        self._require_fence()
        t_start = time.monotonic()
        con = self._open_tick_con()
        try:
            try:
                con.execute("BEGIN IMMEDIATE;")
            except sqlite3.OperationalError:
                raise Retryable("commit-path contention: tick refuses, "
                                "never partial, never wedges")
            self.txns_attempted += 1
            try:
                self.fence.check(con)  # FIRST read (ICEx.5); stale -> abort
                # ---- frozen view (durable truth at txn start) ----
                e_old = float(con.execute("SELECT v FROM meta WHERE k='E'"
                                          ).fetchone()[0])
                ck = con.execute("SELECT birth,epoch,seq FROM checkpoint"
                                 ).fetchone()
                ck_old = (ck[0], int(ck[1]), int(ck[2]))
                scan_rev = int(con.execute("SELECT v FROM meta WHERE "
                                           "k='scan_rev'").fetchone()[0])
                e_new = max(e_old, now - replay.HORIZON_S)  # I5.5: txn-only
                mx = con.execute("SELECT COALESCE(MAX(seq),0) FROM commits "
                                 "WHERE birth=? AND epoch=?",
                                 (self.fence.birth, self.fence.epoch)).fetchone()
                ck_new = (self.fence.birth, self.fence.epoch,
                          max(ck_old[2], int(mx[0])))
                if ck_new[2] < ck_old[2]:
                    raise FailClosed("checkpoint retreat refused")  # ICEx.1
                events = list(self._pass_open_events)
                if e_new > e_old:
                    events.append("i")
                if ck_new[2] > ck_old[2]:
                    events.append("ii")
                new_view = (e_new, ck_new, scan_rev)
                if self._view is None or new_view != self._view:
                    self._pass_id += 1
                    self._view = new_view
                    self._cursor = None
                    self._pass_deletions = 0
                view_e, view_ckpt, view_sr = self._view
                holds = {r[0] for r in con.execute("SELECT op_id FROM "
                                                   "recovery_holds")}
                # ---- bounded scan (frozen order, keyset resume) ----
                examined = deleted = skipped_p = skipped_i = 0
                bytes_read = bytes_written = 0
                to_delete = []
                ceiling_hit = "none"
                cts, cid = self._cursor if self._cursor else (-1.0, "")
                start_key = [cts, cid]
                seg_exhausted = False
                while True:
                    if examined >= N_EX:
                        ceiling_hit = "work"
                        break
                    if len(to_delete) >= N_DEL:
                        ceiling_hit = "work"
                        break
                    if time.monotonic() - t_start >= T_TICK_S:
                        ceiling_hit = "time"
                        break
                    if bytes_read >= B_READ:
                        ceiling_hit = "bytes_read"
                        break
                    if bytes_written >= B_WRITE:
                        ceiling_hit = "bytes_written"
                        break
                    batch = con.execute(
                        "SELECT op_id,payload_hash,outcome,state,"
                        "decided_generation,ts,lease_owner FROM dedup "
                        "WHERE (ts>:cts) OR (ts=:cts AND op_id>:cid) "
                        "ORDER BY ts,op_id LIMIT 100",
                        {"cts": cts, "cid": cid}).fetchall()
                    if not batch:
                        seg_exhausted = True
                        break
                    for row in batch:
                        if examined >= N_EX or len(to_delete) >= N_DEL:
                            ceiling_hit = "work"
                            break
                        if time.monotonic() - t_start >= T_TICK_S:
                            ceiling_hit = "time"
                            break
                        bytes_read += sum(len(str(v or "")) for v in row)
                        if bytes_read >= B_READ:
                            ceiling_hit = "bytes_read"
                            break
                        cls = self._classify(row, view_e, view_ckpt, holds)
                        examined += 1
                        cts, cid = row[5], row[0]
                        if cls == "eligible":
                            to_delete.append(row[0])
                            bytes_written += len(row[0]) + 64
                        elif cls == "protected":
                            skipped_p += 1
                        else:
                            skipped_i += 1
                    else:
                        continue
                    break
                # ---- single atomic advance: checkpoint + E + deletes ----
                if self._test_hook is not None:
                    self._test_hook(self, con)  # probe instrumentation only
                if to_delete:
                    con.execute("UPDATE meta SET v=? WHERE k='E'", (str(e_new),))
                    con.execute("UPDATE checkpoint SET birth=?,epoch=?,seq=?",
                                (ck_new[0], ck_new[1], ck_new[2]))
                    for oid in to_delete:
                        con.execute("DELETE FROM dedup WHERE op_id=?", (oid,))
                    bytes_written += 128
                elif e_new != e_old or ck_new[2] != ck_old[2]:
                    # View advanced with no deletes: persist E/checkpoint so a
                    # re-evaluation event is durable (still one bounded txn).
                    con.execute("UPDATE meta SET v=? WHERE k='E'", (str(e_new),))
                    con.execute("UPDATE checkpoint SET birth=?,epoch=?,seq=?",
                                (ck_new[0], ck_new[1], ck_new[2]))
                    bytes_written += 128
                con.execute("COMMIT;")
                wrote = bool(to_delete) or e_new != e_old or ck_new[2] != ck_old[2]
            except (Reject, Retryable, FailClosed):
                if con.in_transaction:
                    con.execute("ROLLBACK;")
                raise
            except sqlite3.OperationalError as e:
                if con.in_transaction:
                    con.execute("ROLLBACK;")
                raise Retryable(f"tick storage contention, aborted without "
                                f"partial effects: {e}")
            # ---- post-commit bookkeeping (volatile only) ----
            deleted = len(to_delete)
            self._pass_deletions += deleted
            if seg_exhausted:
                if self._pass_deletions == 0:
                    exhausted = True  # full pass, one view, zero deletions
                else:
                    exhausted = False
                self._cursor = None  # wrap scheduled; next tick opens new pass
                self._view = None
                self._pass_open_events = ["iv"]
            else:
                exhausted = False
                self._cursor = (cts, cid)
                self._pass_open_events = []
            if examined == 0 and deleted == 0 and not wrote:
                self._last_outcome = "noop"
            elif deleted == 0:
                self._last_outcome = "zero-delete"
            else:
                self._last_outcome = "work"
            # Progress = deletions. E/checkpoint advances are consumed WITHIN
            # the tick that made them (its scan already runs under the new
            # view), and E creeps with the wall clock on every tick — so a
            # bare E/ckpt write must NOT re-arm execution, else the
            # no-busy-retry guard could never idle (falsifier A4).
            self._last_progress = deleted > 0
            counted = examined + deleted + (1 if wrote else 0)
            diag = {
                "tick": True, "pass_id": self._pass_id,
                "view": {"E_ms": int(view_e * 1000), "E": view_e,
                         "checkpoint": list(view_ckpt), "scan_rev": view_sr},
                "view_identity": f"E={int(view_e * 1000)};ckpt={view_ckpt[0]},"
                                 f"{view_ckpt[1]},{view_ckpt[2]};scanrev={view_sr};"
                                 f"pass={self._pass_id}",
                "cursor_start": start_key,
                "cursor_end": [cts, cid] if examined else None,
                "rows_examined": examined, "rows_deleted": deleted,
                "rows_skipped_protected": skipped_p,
                "rows_skipped_ineligible": skipped_i,
                "internal_touches": {"counted": counted,
                                     "bound_cited": f"K_adapt={K_ADAPT}/row",
                                     "count_rule": "examined(index entries,1/row)"
                                     "+deleted(cascade/tombstone,1/row)"
                                     "+E/checkpoint-row write(0/1); uncounted "
                                     "b-tree/adapter touches bounded by K_adapt"},
                "accounted_work": examined + deleted + counted,
                "ceiling_hit": ceiling_hit,
                "bytes_read": bytes_read, "bytes_written": bytes_written,
                "exhaustion": exhausted,
                "segment_complete": (not seg_exhausted) and ceiling_hit != "none",
                "opportunity": opportunity, "events": sorted(set(events)),
                "tick_wall_s": round(time.monotonic() - t_start, 4),
                "txns_attempted": self.txns_attempted,
            }
            self.history.append(diag)
            return diag
        finally:
            con.close()
