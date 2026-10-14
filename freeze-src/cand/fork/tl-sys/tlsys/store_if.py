"""Candidate store interface: the ONLY module that imports the accepted
batch-storage candidate (tl-candidate-batch/candidate @ rev pinned in
tlsys.__init__). Every benchmark call into storage passes through here,
and every call is trace-logged -> product-path proof (goal item 1).

Generations: triple "<birth>:<epoch>:<seq>". Attach-and-pin (Q1.1 K6,
single-threaded conforming form): pin = current triple at query start;
all reads predicate seq<=pinned seq within (birth,epoch); no
cross-generation mixing. Pin/release bracket every query.
"""

import json
import os
import sqlite3
import sys
import time
from collections import deque

_CANDIDATE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "tl-candidate-batch", "candidate"))
if _CANDIDATE_DIR not in sys.path:
    sys.path.insert(0, _CANDIDATE_DIR)

import committer as _committer_mod  # noqa: E402
import store as _store_mod  # noqa: E402
from common import Reject, Retryable, sha256, uuidv7  # noqa: E402

from tlsys import CANDIDATE_REV  # noqa: E402

Store = _store_mod.Store
Fence = _store_mod.Fence
Committer = _committer_mod.Committer
prepare_artifact = _committer_mod.prepare_artifact
keeper_open = _store_mod.keeper_open
keeper_release = _store_mod.keeper_release

# R7-A (proposal C): max SQL variables per chunked IN-list. 500 keeps
# every chunk far below every observed SQLITE_LIMIT_VARIABLE_NUMBER
# (999/32766/250000) while keeping round-trips low.
SQL_IN_CHUNK = 500
# R7-A (proposal C): default page for read_commits_all frontier scans.
READ_COMMITS_PAGE = 50000
# M1-A (F2): bound on the CallTrace recent-event diagnostic window.
# Aggregates cover every logged event; only this many newest event
# dicts are retained for diagnostics.
TRACE_RECENT_MAX = 1000


def format_commit_failure(result):
    """One-line cause-preserving summary of a non-committed result.

    commit_batch per-op results carry the blocking cause under
    different keys by status: terminal/raised use code (+detail),
    retryable uses message, not_attempted uses reason. The legacy
    f"{status}:{code}" format prints None for the latter two,
    discarding e.g. the REJECT_CAPACITY cause (C2 100M p0: 9,444
    organize failures + the ingest-p1 fatal all read
    "retryable:None"/"not_attempted:None"). Include whichever cause
    fields are present so a STOP-and-classify reader sees the cause
    without rerunning. Never raises on malformed input.
    """
    try:
        op_id = result.get("op_id")
        status = result.get("status")
        cause = result.get("code") or result.get("message") \
            or result.get("reason") or result.get("detail")
        text = "op %s %s:%s" % (op_id, status, cause)
        detail = result.get("detail")
        if detail and detail != cause:
            text += " (%s)" % (detail,)
        return text
    except Exception:  # noqa: BLE001 -- diagnostic best-effort
        return "op %r" % (result,)


class TruncationError(RuntimeError):
    """read_commits hit its limit: the store holds more rows than the
    call window covers. Loud by design (R6-B proposal C(c)): callers
    that need the full prefix must page via read_commits_all instead
    of silently serving the oldest rows."""


class CallTrace:
    """Bounded trace of storage calls (product-path evidence).

    M1-A (F2): the pre-M1 form retained one dict per call in an
    unbounded list (~60-95 MB per heavy oracle query). This form
    aggregates on log (per (op, outcome) counters, so summary()
    output is identical for the same event stream), retains only
    the newest `recent_max` event dicts in a deque for
    diagnostics, and optionally streams full detail to `sink`.

    `sink` is a callable taking each event dict. A return value
    of exactly False means declined/backpressure (counted, not
    an error); a raised exception is caught (telemetry must never
    break the product path) and counted with the first error
    retained. Both are disclosed via dump() + attributes.

    `.calls` (audited M1-A: test_narrow_integration len/dump,
    test_relindex len/slice/eq/iterate, no external mutation,
    no dump-JSON readers) now returns a list snapshot of the
    bounded recent window, oldest->newest. Content is identical
    to the old form whenever total events <= recent_max; beyond
    that, n_total/dropped_detail disclose the truncation.
    """

    def __init__(self, recent_max=TRACE_RECENT_MAX, sink=None):
        if recent_max is None:
            recent_max = TRACE_RECENT_MAX
        self._recent_max = max(0, int(recent_max))
        # maxlen=0 keeps the deque permanently empty (aggregates
        # still complete); None is never passed (unbounded).
        self._recent = deque(maxlen=self._recent_max)
        self._agg = {}
        self._n_total = 0
        self._sink = sink
        self._sink_accepted = 0
        self._sink_dropped = 0
        self._sink_errors = 0
        self._sink_first_error = None

    @property
    def calls(self):
        """Bounded recent events, oldest->newest (list snapshot)."""
        return list(self._recent)

    @property
    def n_total(self):
        """Every event ever logged (aggregates cover all of these)."""
        return self._n_total

    @property
    def recent_max(self):
        return self._recent_max

    @property
    def dropped_detail(self):
        """Events covered by aggregates but evicted from `recent`."""
        return self._n_total - len(self._recent)

    @property
    def sink_accepted(self):
        return self._sink_accepted

    @property
    def sink_dropped(self):
        """Sink-declined (False) + sink-raised events."""
        return self._sink_dropped

    @property
    def sink_errors(self):
        """Events whose sink call raised (subset of sink_dropped)."""
        return self._sink_errors

    @property
    def sink_first_error(self):
        return self._sink_first_error

    def log(self, op, detail, ms, outcome):
        key = (op, outcome)
        cell = self._agg.get(key)
        if cell is None:
            self._agg[key] = [1, ms]
        else:
            cell[0] += 1
            cell[1] += ms
        self._n_total += 1
        event = {"t": time.time(), "op": op, "detail": detail,
                 "ms": ms, "outcome": outcome}
        self._recent.append(event)
        if self._sink is not None:
            try:
                verdict = self._sink(event)
            except Exception as e:  # telemetry never breaks product
                self._sink_errors += 1
                self._sink_dropped += 1
                if self._sink_first_error is None:
                    self._sink_first_error = (
                        f"{type(e).__name__}: {e}")
            else:
                if verdict is False:
                    self._sink_dropped += 1
                else:
                    self._sink_accepted += 1

    def dump(self, path):
        """Aggregates + bounded recent + scope note (bounded bytes).

        Shape differs from the pre-M1 full-`calls` dump by design
        (that shape reached 87 MB at 10M scale); no in-repo reader
        of the old shape exists (audited M1-A: dump call sites are
        write-only in test_narrow_integration + tl-eval drivers).
        """
        payload = {
            "candidate_rev": CANDIDATE_REV,
            "scope_note": (
                "M1-A bounded telemetry: 'summary' aggregates ALL "
                "n_total events; 'recent' holds only the newest "
                "recent_max event dicts (oldest->newest); "
                "dropped_detail events are aggregate-only. Full "
                "per-event detail requires a streamed sink."),
            "n_total": self._n_total,
            "recent_max": self._recent_max,
            "dropped_detail": self.dropped_detail,
            "summary": self.summary(),
            "sink": {"accepted": self._sink_accepted,
                     "dropped": self._sink_dropped,
                     "errors": self._sink_errors,
                     "first_error": self._sink_first_error},
            "recent": list(self._recent),
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=1)

    def summary(self):
        # Aggregate-on-log: same keys, same counts, same float
        # summation order as the pre-M1 loop over all calls, so
        # output is identical for the same event stream.
        return {f"{op}/{oc}": {"n": n, "ms_total": round(tot, 2)}
                for (op, oc), (n, tot) in sorted(self._agg.items())}


class TLStore:
    """Open store + fence + committer with traced calls."""

    def __init__(self, root, create=False, store_label="tl-sys",
                 lease_owner=None, trace=None, caps=None,
                 local_repair=False, repair_config=None):
        self.trace = trace or CallTrace()
        if create:
            self.store = Store.create(root, store_label=store_label)
        else:
            self.store = Store(root)
        self.fence = Fence(self.store)
        t0 = time.time()
        self.fence.acquire()
        self.trace.log("fence.acquire", {"root": root},
                       (time.time() - t0) * 1000.0, "ok")
        # Per-run admission caps (D-12 designed path: "recorded per
        # run, enforced once configured"). None keeps the Committer
        # defaults exactly; a caller dict is copied so later caller
        # mutation cannot change an open store's enforcement.
        self.cm = Committer(self.store, self.fence,
                            caps=dict(caps) if caps is not None else None,
                            lease_owner=lease_owner)
        keeper_open(self.store)
        if local_repair:
            from tlsys.local_repair import TLRepair, RepairConfig
            from dataclasses import replace
            self.local_repair = TLRepair(
                self, replace(repair_config or RepairConfig(), enabled=True))

    def close(self):
        keeper_release(self.store)
        t0 = time.time()
        self.fence.release()
        self.trace.log("fence.release", {}, (time.time() - t0) * 1000.0,
                       "ok")

    # -- writes ------------------------------------------------------
    def commit_batch(self, ops):
        t0 = time.time()
        try:
            results, info = self.cm.commit_batch(ops)
        except (Reject, Retryable) as e:
            self.trace.log("commit_batch", {"n": len(ops)},
                           (time.time() - t0) * 1000.0,
                           f"{type(e).__name__}:{getattr(e, 'code', '?')}")
            raise
        self.trace.log("commit_batch",
                       {"n": len(ops), "path": info.get("path"),
                        "statuses": [r.get("status") for r in results]},
                       (time.time() - t0) * 1000.0, "ok")
        if hasattr(self, "local_repair"):
            self.local_repair.sync()
        return results, info

    # -- generation-pinned reads ------------------------------------
    def repair_step(self, budget):
        """Drain flag-gated local membership repair; default is commit-free."""
        if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
            raise ValueError("budget must be a nonnegative integer")
        if not hasattr(self, "local_repair"):
            return {"enabled": False, "spent": 0, "checked": 0, "debt": 0}
        return self.local_repair.repair_step(budget)

    def pin(self):
        """Attach-and-pin: current triple. All subsequent reads in this
        query predicate on (birth,epoch,seq<=pinned)."""
        con = self.store.open_db()
        try:
            t0 = time.time()
            row = con.execute(
                "SELECT birth,epoch,COALESCE(MAX(seq),0) FROM commits"
            ).fetchone()
            ms = (time.time() - t0) * 1000.0
        finally:
            con.close()
        birth, epoch, mx = row
        triple = f"{birth}:{epoch}:{mx}" if birth else "empty:0:0"
        self.trace.log("pin", {"triple": triple}, ms, "ok")
        return (birth, epoch, mx, triple)

    def current_policy_version(self):
        """Active owning-policy version for approval_ref binding (P6).

        V3 repair: stage-2 approval refs pin the policy version they
        were assessed under; the core gate refuses stale pins
        (POLICY_STALE). Read-only, traced like every adapter read.
        """
        con = self.store.open_db()
        try:
            t0 = time.time()
            row = con.execute(
                "SELECT version FROM policy WHERE active=1").fetchone()
            ms = (time.time() - t0) * 1000.0
        finally:
            con.close()
        if row is None:
            self.trace.log("current_policy_version", {}, ms,
                           "POLICY_MISSING")
            raise ValueError("no active owning policy")
        self.trace.log("current_policy_version", {"version": row[0]},
                       ms, "ok")
        return row[0]

    def _read_commits_page(self, birth, epoch, max_seq, kind, limit,
                             min_seq):
        """Raw page fetch: up to `limit` rows, oldest->newest. No
        truncation signal; read_commits / read_commits_all add it."""
        con = self.store.open_db()
        try:
            q = ("SELECT seq,op_id,kind,payload_hash,outcome,disclosure,"
                 "decided_at FROM commits WHERE birth=? AND epoch=? "
                 "AND seq<=? AND seq>? ")
            args = [birth, epoch, max_seq, min_seq]
            if kind is not None:
                q += "AND kind=? "
                args.append(kind)
            q += "ORDER BY seq LIMIT ?"
            args.append(limit)
            return con.execute(q, args).fetchall()
        finally:
            con.close()

    def read_commits(self, birth, epoch, max_seq, kind=None, limit=100000,
                     min_seq=0):
        """Generation-pinned commit rows (oldest->newest).

        min_seq (exclusive lower bound) supports incremental readers;
        default 0 preserves the full-prefix behavior.

        R7-A fail-loud (proposal C(c)): raises TruncationError when
        the window holds MORE than `limit` rows (probed via
        LIMIT+1, so a store with exactly `limit` rows still reads
        clean). Returned rows are byte-identical to the pre-R7-A
        call whenever no truncation occurs.
        """
        t0 = time.time()
        rows = self._read_commits_page(birth, epoch, max_seq, kind,
                                       limit + 1, min_seq)
        ms = (time.time() - t0) * 1000.0
        if len(rows) > limit:
            self.trace.log("read_commits",
                           {"gen": f"{birth}:{epoch}:{max_seq}",
                            "kind": kind, "limit": limit},
                           ms, "TRUNCATED")
            raise TruncationError(
                f"read_commits window holds >{limit} rows "
                f"({birth}:{epoch}:{max_seq} kind={kind} "
                f"min_seq={min_seq}); refusing a silent oldest-prefix "
                "(page via read_commits_all)")
        self.trace.log("read_commits",
                       {"gen": f"{birth}:{epoch}:{max_seq}", "kind": kind,
                        "n": len(rows)}, ms, "ok")
        return rows

    def _iter_commit_pages(self, birth, epoch, max_seq, kind,
                             min_seq, page):
        """Yield oldest->newest row pages via min_seq frontiers
        (R6-B proposal C(b) loop, shared by the concat + iterator
        forms). One page (+1 probe row) is alive at a time."""
        if page < 1:
            page = 1
        lo = min_seq
        while True:
            rows = self._read_commits_page(birth, epoch, max_seq, kind,
                                           page + 1, lo)
            if len(rows) <= page:
                yield rows
                return
            yield rows[:page]
            lo = rows[page - 1][0]  # ascending seqs: consumed frontier

    def read_commits_all(self, birth, epoch, max_seq, kind=None,
                         min_seq=0, page=READ_COMMITS_PAGE):
        """Unbounded generation-pinned read via min_seq frontiers
        (R6-B proposal C(b)): oldest->newest rows with no silent
        window. The concatenation is byte-identical to a single
        unbounded read. `page` is an internal round-trip size only.

        M1-A: compat concat form over the shared page loop; the
        single "read_commits_all" trace record is unchanged. New
        bounded callers should prefer read_commits_iter."""
        t0 = time.time()
        out = []
        pages = 0
        for rows in self._iter_commit_pages(birth, epoch, max_seq,
                                            kind, min_seq, page):
            pages += 1
            out.extend(rows)
        ms = (time.time() - t0) * 1000.0
        self.trace.log("read_commits_all",
                       {"gen": f"{birth}:{epoch}:{max_seq}", "kind": kind,
                        "n": len(out), "pages": pages}, ms, "ok")
        return out

    def read_commits_iter(self, birth, epoch, max_seq, kind=None,
                          min_seq=0, page=READ_COMMITS_PAGE):
        """Page-incremental generation-pinned read (M1-A): yields
        oldest->newest rows one at a time with bounded working
        memory (one page alive, not the full prefix). The yielded
        sequence is byte-identical to read_commits_all over the
        same window. Each fetched page logs one
        "read_commits_iter" trace event (bounded by design)."""
        gen = f"{birth}:{epoch}:{max_seq}"
        pages = self._iter_commit_pages(birth, epoch, max_seq,
                                        kind, min_seq, page)
        pageno = 0
        while True:
            # ms covers the page fetch only: consumer row time
            # falls between next() calls, outside the window.
            t0 = time.time()
            try:
                rows = next(pages)
            except StopIteration:
                return
            ms = (time.time() - t0) * 1000.0
            pageno += 1
            self.trace.log("read_commits_iter",
                           {"gen": gen, "kind": kind,
                            "page": pageno, "page_rows": len(rows)},
                           ms, "ok")
            for r in rows:
                yield r

    def read_artifact(self, artifact_id, expect_digest=None):
        """Late display-text read (Q15.1a): bytes + digest check."""
        from common import sha256 as _sha256
        path = os.path.join(self.store.artdir, artifact_id)
        t0 = time.time()
        with open(path, "rb") as f:
            body = f.read()
        ms = (time.time() - t0) * 1000.0
        digest = "sha256:" + _sha256(body)
        ok = (expect_digest is None) or (digest == expect_digest)
        self.trace.log("read_artifact",
                       {"id": artifact_id, "len": len(body),
                        "digest_ok": ok}, ms,
                       "ok" if ok else "INTEGRITY_FAILED")
        if not ok:
            raise ValueError(f"artifact {artifact_id}: integrity failed "
                             f"(want {expect_digest}, got {digest})")
        return body

    def pub_refs(self, seqs):
        """seq -> [artifact_id] for display materialization.

        R7-A (proposal C(a)): chunked IN-lists (<=SQL_IN_CHUNK
        params each) over ONE connection, unioned. Byte-identical
        output to the single-IN call at any scale, including past
        every SQLITE_LIMIT_VARIABLE_NUMBER.
        """
        seqs = list(seqs)
        if not seqs:
            return {}
        con = self.store.open_db()
        try:
            t0 = time.time()
            rows = []
            for i in range(0, len(seqs), SQL_IN_CHUNK):
                chunk = seqs[i:i + SQL_IN_CHUNK]
                q = ("SELECT seq,artifact_id FROM pub_refs WHERE seq "
                     "IN (%s)ORDER BY seq,artifact_id"
                     % ",".join("?" * len(chunk)))
                rows.extend(con.execute(q, chunk).fetchall())
            ms = (time.time() - t0) * 1000.0
        finally:
            con.close()
        # Global order, exactly as the single ORDER BY produced it
        # (per-chunk order alone is input-order-dependent).
        rows.sort(key=lambda r: (r[0], r[1]))
        out = {}
        for s, a in rows:
            out.setdefault(s, []).append(a)
        self.trace.log("pub_refs", {"n_seq": len(seqs),
                                    "n_refs": len(rows)}, ms, "ok")
        return out

    def artifact_row(self, artifact_id):
        con = self.store.open_db()
        try:
            row = con.execute(
                "SELECT artifact_id,store_id,extent,length,digest,durable,"
                "op_seq FROM artifacts WHERE artifact_id=?",
                (artifact_id,)).fetchone()
        finally:
            con.close()
        return row

    def artifact_rows(self, artifact_ids):
        """Batch artifact rows: {artifact_id: row} over ONE connection
        (R7-A: kills the per-artifact open+query+close round-trips,
        the 57% dominant term in R6-A DIAGNOSIS §3). Chunked IN-lists
        (<=SQL_IN_CHUNK); each returned row is byte-identical to the
        artifact_row call for that id. Missing ids are absent from
        the dict (artifact_row returns None for them)."""
        ids = list(dict.fromkeys(artifact_ids))
        if not ids:
            return {}
        con = self.store.open_db()
        try:
            out = {}
            for i in range(0, len(ids), SQL_IN_CHUNK):
                chunk = ids[i:i + SQL_IN_CHUNK]
                q = ("SELECT artifact_id,store_id,extent,length,digest,"
                     "durable,op_seq FROM artifacts WHERE artifact_id "
                     "IN (%s)" % ",".join("?" * len(chunk)))
                for row in con.execute(q, chunk).fetchall():
                    out[row[0]] = row
        finally:
            con.close()
        return out
