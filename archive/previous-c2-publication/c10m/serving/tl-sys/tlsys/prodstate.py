"""Indexed TL-owned SQLite producer-state sidecar (C2 Closure P, §5.2).

Replaces the foreground whole-manifest path with keyed reads/writes:
source declarations, revision identity/hash/expected coverage,
committed op IDs, historical xdoc attribution, document/organization
state, ordered pending work, exact counts, and the projection
frontier. Field meanings + ordering match the legacy JSON manifest,
which is materialized ONLY at explicit compatibility boundaries
(call ends), never in the foreground.

Durability/discipline (owning commit DB + ten-op protocol UNCHANGED):
  - Single writer: all access runs under the caller's TLStore fence
    (same caller-serialized rule as the manifest). SQLite transactions
    are BEGIN IMMEDIATE with a short busy timeout; a lock error fails
    closed (fence violation), never waits out a peer writer.
  - Declaration evidence is durable (committed txn) BEFORE the first
    core commit of a revision; per-flush derived progress advances in
    ONE atomic txn AFTER commit_batch reports committed. Derived
    progress never leads committed truth.
  - Crash-after-commit adopts committed ops on restart via the pinned
    suffix after the validated frontier (no whole-prefix rescan);
    missing/corrupt state raises a NAMED error, never invents identity.
  - Legacy writers refuse a store carrying this sidecar BEFORE
    committing (StaleProducerError); legacy readers keep working off
    the boundary-materialized manifest.

Also holds the R_cat pre-execution cost model (§5.2 item 5) and the
producer-session routing reuse (§5.2 item 3): session catalogs/reverse
indexes keyed by incarnation/frontier with committed deltas, plus
persisted restart-ready routing snapshots (digest-validated).
"""

import hashlib
import json
import os
import re
import sqlite3
import struct

from tlsys.identity import ATOM_SCHEME

SIDECAR_NAME = "producer_state.db"
SIDECAR_FORMAT = 1
# P-2 (Sec 5.7): recorded candidate version binding the keyed
# configuration. Ordinary keyed calls skip the JSON export; the
# legacy manifest materializes only on explicit archive requests.
CANDIDATE_VERSION = "c2-keyed-1"
KEYED_BACKEND_ID = "keyed-sqlite"
ARCHIVE_POLICY_EXPLICIT = "explicit-only"
# Stale-snapshot marker: manifest_path + this suffix. Presence means
# the JSON beside it predates keyed progress (readers must use the
# keyed reads or request an archive). O(1) bytes, never O(N).
MANIFEST_STALE_SUFFIX = ".stale.json"
# Bounded diagnostics: at most this many pending/remaining ids ride a
# report; exact totals ride alongside as counts (never truncated).
REMAINING_SAMPLE = 64
# Chunked target fetch for unbounded budgets (bounded memory, exact
# coverage via queue cursor).
TARGET_WINDOW = 512

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS docs(
  doc_id TEXT PRIMARY KEY, decl_seq INTEGER,
  revision_id TEXT, source_sha256 TEXT, revision_len INTEGER,
  n_chunks_expected INTEGER, source_verified INTEGER, status TEXT,
  holon_op TEXT, holon_members TEXT, updated_seq INTEGER);
CREATE TABLE IF NOT EXISTS doc_atoms(
  doc_id TEXT, chunk_ix INTEGER, op_id TEXT, aid TEXT,
  b0 INTEGER, b1 INTEGER, text_digest TEXT, revision_id TEXT,
  n_chunks INTEGER, seq INTEGER, ord_seq INTEGER,
  PRIMARY KEY(doc_id, chunk_ix));
CREATE INDEX IF NOT EXISTS doc_atoms_ord ON doc_atoms(doc_id, ord_seq);
CREATE INDEX IF NOT EXISTS doc_atoms_aid ON doc_atoms(aid);
CREATE TABLE IF NOT EXISTS doc_xdoc(
  doc_id TEXT, op_id TEXT, seq INTEGER, ord_seq INTEGER,
  PRIMARY KEY(doc_id, op_id));
CREATE INDEX IF NOT EXISTS doc_xdoc_ord ON doc_xdoc(doc_id, ord_seq);
CREATE TABLE IF NOT EXISTS doc_seg(
  doc_id TEXT, op_id TEXT, seq INTEGER, ord_seq INTEGER,
  PRIMARY KEY(doc_id, op_id));
CREATE INDEX IF NOT EXISTS doc_seg_ord ON doc_seg(doc_id, ord_seq);
CREATE TABLE IF NOT EXISTS xdoc_ops(
  op_id TEXT PRIMARY KEY, xdoc_id TEXT, seq INTEGER);
CREATE TABLE IF NOT EXISTS pending(
  doc_id TEXT PRIMARY KEY, queue_seq INTEGER);
CREATE INDEX IF NOT EXISTS pending_order ON pending(queue_seq);
CREATE TABLE IF NOT EXISTS seg_organized(
  doc_id TEXT PRIMARY KEY, queue_seq INTEGER);
CREATE TABLE IF NOT EXISTS retired(
  doc_id TEXT PRIMARY KEY, queue_seq INTEGER);
CREATE TABLE IF NOT EXISTS counters(name TEXT PRIMARY KEY, value INTEGER);
CREATE TABLE IF NOT EXISTS routing_populations(
  population TEXT PRIMARY KEY, frontier INTEGER, n INTEGER, dim INTEGER,
  rcat INTEGER, digest TEXT, blob BLOB);
"""


class SidecarError(RuntimeError):
    """Base for named producer-state failures (never silent)."""


class StaleProducerError(SidecarError):
    """A legacy writer met a store carrying keyed producer state.

    Raised BEFORE any commit. Recovery: rerun with keyed_state=True,
    or archive/remove the sidecar (the boundary-materialized legacy
    manifest is complete) to return the store to legacy writers.
    """


class SidecarMissingError(SidecarError):
    """A keyed call needs the sidecar but the file is absent.

    Named recovery: reconcile_manifest(..., keyed_state=True) rebuilds
    it from committed truth (cold_rebuild receipt).
    """


class SidecarCorruptError(SidecarError):
    """The sidecar is unreadable, foreign-format, or generation-mismatched.

    Nothing is trusted or invented; the operator path is quarantine +
    keyed reconcile rebuild from committed truth.
    """


class SidecarConflictError(SidecarError):
    """A declaration/record conflicts with recorded producer truth.

    Mixed revisions under one doc_id, duplicate chunk effects, frontier
    rewinds, and session incarnation changes fail loud here.
    """


class RoutingMismatch(SidecarError):
    """A persisted routing snapshot failed validation (digest/shape/
    profile). The session takes the named rebuild path (receipted);
    never a silent trust of the bytes.
    """


class OverBudgetRejected(SidecarError):
    """An R_cat pre-execution gate refused a decision BEFORE any scan.

    Carries the full pre-execution cost estimate (.estimate). The doc
    defers (ingest/drain backlog) or fails named (organize); no
    over-budget work executes and no population is truncated.
    """

    def __init__(self, message, estimate):
        super().__init__(message)
        self.estimate = estimate


class CandidateMissingError(SidecarError):
    """A qualification entry point needs a candidate binding, unbound.

    Named recovery: bind_candidate_store(...) records the binding
    before confirmation use; require_candidate refuses until then.
    """


class CandidateMismatchError(SidecarError):
    """A candidate binding exists but the version/generation mismatches.

    Wrong recorded version or a foreign store generation: refusing
    rather than running an undeclared configuration.
    """


def sidecar_path(store):
    return os.path.join(store.root, SIDECAR_NAME)


def sidecar_exists(store):
    return os.path.isfile(sidecar_path(store))


def refuse_legacy_writer(store):
    """Stale-writer fence: legacy writers refuse sidecar stores first."""
    if sidecar_exists(store):
        raise StaleProducerError(
            f"store {store.root!r} carries keyed producer state "
            f"({SIDECAR_NAME}); legacy writers refuse before committing "
            "(rerun with keyed_state=True)")


def incarnation_of(pin):
    """Producer incarnation: generation + scheme + sidecar format."""
    birth, epoch = pin[0], pin[1]
    return f"{birth}:{epoch}:{ATOM_SCHEME}:{SIDECAR_FORMAT}"


def _is_prebirth_incarnation(inc):
    """True when an incarnation string carries an unborn generation.

    incarnation_of formats birth:epoch:scheme:format; an empty store
    pins (None, None), so its incarnation reads "None:None:...". A
    stored pre-birth incarnation is UNBOUND (mirrors
    ProducerState._set_frontier, which stamps a (None, None) stored
    generation instead of reporting a mismatch).
    """
    if not isinstance(inc, str):
        return False
    parts = inc.split(":")
    return len(parts) >= 2 and parts[0] == "None" \
        and parts[1] == "None"


class ProducerState:
    """One open sidecar handle (caller-serialized, fence-held).

    Keyed reads/writes only; every mutation runs in one explicit
    transaction. .io_snapshot() exposes bounded-I/O counters for
    receipts/tests (reads/writes = statements+txns, rows = rows
    fetched + rows changed).
    """

    def __init__(self, tlstore, con):
        self._tlstore = tlstore
        self._con = con
        self._io = {"reads": 0, "writes": 0, "rows": 0}

    # -- open / create / migrate ------------------------------------
    @classmethod
    def _connect(cls, path):
        try:
            con = sqlite3.connect(path, timeout=2.0,
                                  isolation_level=None)
        except sqlite3.Error as e:
            raise SidecarCorruptError(
                f"producer sidecar {path!r} unreadable: {e}") from e
        try:
            con.execute("PRAGMA journal_mode=DELETE")
            con.execute("PRAGMA synchronous=FULL")
        except sqlite3.DatabaseError as e:
            con.close()
            raise SidecarCorruptError(
                f"producer sidecar {path!r} unreadable: {e}") from e
        return con

    @classmethod
    def open(cls, tlstore):
        """Open an existing sidecar (validated, else a named error)."""
        path = sidecar_path(tlstore.store)
        if not os.path.isfile(path):
            raise SidecarMissingError(
                f"producer sidecar {path!r} absent (named recovery: "
                "reconcile_manifest(..., keyed_state=True) rebuilds "
                "it from committed truth)")
        con = cls._connect(path)
        obj = cls(tlstore, con)
        try:
            fmt = obj.meta("format")
            scheme = obj.meta("scheme")
        except SidecarError:
            con.close()
            raise
        if fmt != str(SIDECAR_FORMAT) or scheme != ATOM_SCHEME:
            con.close()
            raise SidecarCorruptError(
                f"producer sidecar {path!r}: foreign format "
                f"(format={fmt!r} scheme={scheme!r}; want "
                f"{SIDECAR_FORMAT}/{ATOM_SCHEME})")
        obj._check_generation()
        return obj

    def _check_generation(self):
        """Refuse a sidecar from a different store generation."""
        birth = self.meta("gen_birth")
        epoch = self.meta("gen_epoch")
        if birth is None and epoch is None:
            return  # pre-commit store: nothing to check yet
        pin = self._tlstore.pin()
        if str(pin[0]) != str(birth) or str(pin[1]) != str(epoch):
            raise SidecarCorruptError(
                "producer sidecar generation "
                f"({birth}:{epoch}) != live pin ({pin[0]}:{pin[1]}): "
                "refusing to mix generations")

    @classmethod
    def create_or_migrate(cls, tlstore, manifest, missing_ok=False):
        """Create the sidecar, migrating a legacy manifest when present.

        manifest: the parsed legacy dict ({} when no manifest file
        exists). On an existing sidecar this is open() (the sidecar is
        authoritative; the manifest is ignored). Migration joins
        manifest op_ids against committed truth in ONE bounded
        attribution pass, adopts crash-window ops, and records the
        frontier. Returns (state, receipt). A manifest stamped
        _sidecar_seq without its sidecar means the sidecar was LOST:
        that refuses with SidecarMissingError unless missing_ok (the
        named reconcile rebuild path) -- never silent re-creation.
        P-2: ordinary calls write no manifest, so a lingering stale
        marker is an equivalent loss witness and refuses the same
        way (only the named reconcile path rebuilds).
        """
        if sidecar_exists(tlstore.store):
            return cls.open(tlstore), {"migrated_docs": 0,
                                       "existing": True}
        if not missing_ok:
            if manifest.get("_sidecar_seq") is not None:
                raise SidecarMissingError(
                    f"store {tlstore.store.root!r}: the manifest "
                    "carries keyed producer state (_sidecar_seq) but "
                    f"{SIDECAR_NAME} is absent (lost sidecar; named "
                    "recovery: reconcile_manifest(..., "
                    "keyed_state=True) rebuilds it from committed "
                    "truth)")
            from tlsys.ingest import MANIFEST_NAME as _MAN
            _mpath = os.path.join(tlstore.store.root, _MAN)
            if os.path.isfile(_mpath + MANIFEST_STALE_SUFFIX):
                raise SidecarMissingError(
                    f"store {tlstore.store.root!r}: a stale marker "
                    f"lingers but {SIDECAR_NAME} is absent (lost "
                    "sidecar; named recovery: reconcile_manifest("
                    "..., keyed_state=True) rebuilds it from "
                    "committed truth)")
        if any(not k.startswith("_") for k in manifest):
            found = manifest.get("_scheme")
            if found != ATOM_SCHEME:
                raise SidecarError(
                    f"ingest manifest scheme {found!r} != "
                    f"{ATOM_SCHEME!r}: store was organized under a "
                    "different atom-identity scheme; rebuild the "
                    "scratch store (no migration)")
        path = sidecar_path(tlstore.store)
        con = cls._connect(path)
        obj = cls(tlstore, con)
        try:
            with obj._txn():
                for stmt in _SCHEMA.split(";"):
                    if stmt.strip():
                        obj._x(stmt)
                obj._set_meta("format", str(SIDECAR_FORMAT))
                obj._set_meta("scheme", ATOM_SCHEME)
                obj._set_meta("progress_seq", "0")
                for name in ("docs_declared", "atoms_committed",
                             "holons_committed", "xdoc_committed",
                             "xdoc_versions", "seg_committed",
                             "pending_depth", "organized_count",
                             "retired_count", "docs_with_atoms",
                             "retired_unorganized",
                             "decl_seq", "queue_pending",
                             "queue_organized", "queue_retired"):
                    obj._set_counter(name, 0)
        except SidecarError:
            con.close()
            raise
        receipt = obj._migrate_from_manifest(manifest)
        obj._check_generation()
        return obj, receipt

    def close(self):
        con, self._con = self._con, None
        if con is not None:
            con.close()

    # -- statement plumbing (counted, named errors) -------------------
    def _q(self, sql, args=()):
        """Counted read; DatabaseError -> SidecarCorruptError."""
        try:
            cur = self._con.execute(sql, args)
            rows = cur.fetchall()
        except sqlite3.DatabaseError as e:
            raise SidecarCorruptError(
                f"producer sidecar unreadable: {e}") from e
        self._io["reads"] += 1
        self._io["rows"] += len(rows)
        return rows

    def _x(self, sql, args=()):
        """Counted write (inside an explicit txn)."""
        try:
            cur = self._con.execute(sql, args)
        except sqlite3.IntegrityError as e:
            raise SidecarConflictError(
                f"producer state conflict ({e}); refusing duplicate "
                "or mixed effects") from e
        except sqlite3.DatabaseError as e:
            raise SidecarCorruptError(
                f"producer sidecar unreadable: {e}") from e
        except sqlite3.OperationalError as e:
            raise SidecarError(
                "producer sidecar write failed "
                f"({e}); the single-writer fence owns this store") from e
        self._io["rows"] += max(cur.rowcount, 0)
        return cur

    class _txn_ctx:
        def __init__(self, outer):
            self._outer = outer

        def __enter__(self):
            try:
                self._outer._con.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as e:
                raise SidecarError(
                    "producer sidecar busy: another writer holds it "
                    f"({e}); callers must serialize under the fence"
                ) from e
            return self._outer

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                self._outer._con.execute("COMMIT")
                self._outer._io["writes"] += 1
            else:
                try:
                    self._outer._con.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            return False

    def _txn(self):
        return ProducerState._txn_ctx(self)

    def io_snapshot(self):
        return dict(self._io)

    def io_reset(self):
        for k in self._io:
            self._io[k] = 0

    # -- meta / counters ----------------------------------------------
    def meta(self, key):
        rows = self._q("SELECT value FROM meta WHERE key=?", (key,))
        return rows[0][0] if rows else None

    def _set_meta(self, key, value):
        self._x("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)",
                (key, value))

    def _get_counter(self, name):
        rows = self._q("SELECT value FROM counters WHERE name=?",
                       (name,))
        return rows[0][0] if rows else 0

    def _set_counter(self, name, value):
        self._x("INSERT OR REPLACE INTO counters(name, value) "
                "VALUES(?,?)", (name, value))

    def _bump_counter(self, name, delta=1):
        self._x("UPDATE counters SET value=value+? WHERE name=?",
                (delta, name))

    def _next_seq(self, counter):
        self._bump_counter(counter, 1)
        return self._get_counter(counter)

    def _bump_progress(self):
        cur = int(self.meta("progress_seq") or "0") + 1
        self._set_meta("progress_seq", str(cur))
        return cur

    def counters(self):
        rows = self._q("SELECT name, value FROM counters")
        return {k: v for k, v in rows
                if not k.startswith(("queue_", "decl_seq"))}

    # -- declarations ---------------------------------------------------
    def declare_revision(self, doc_id, revision_id, source_sha256,
                         revision_len, n_chunks_expected):
        """Durably declare a source revision (pre-commit evidence).

        Idempotent for the same revision; a different revision under
        the same doc_id fails loud (SidecarConflictError).
        """
        with self._txn():
            rows = self._q("SELECT revision_id FROM docs WHERE "
                           "doc_id=?", (doc_id,))
            if rows:
                if rows[0][0] != revision_id:
                    raise SidecarConflictError(
                        f"doc {doc_id!r}: conflicting revision "
                        f"declaration ({rows[0][0]!r} vs "
                        f"{revision_id!r})")
                return {"inserted": False}
            decl = self._next_seq("decl_seq")
            self._x("INSERT INTO docs(doc_id, decl_seq, revision_id, "
                    "source_sha256, revision_len, n_chunks_expected, "
                    "source_verified, status, holon_op, holon_members,"
                    " updated_seq) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (doc_id, decl, revision_id, source_sha256,
                     revision_len, n_chunks_expected, 1, "started",
                     None, None, None))
            self._bump_counter("docs_declared")
            self._bump_progress()
            return {"inserted": True}

    def adopt_declaration(self, doc_id, revision_id=None,
                          source_sha256=None, revision_len=None,
                          n_chunks_expected=None):
        """Fill unknown declaration fields after verification (one txn).

        Each non-None arg fills its field only when currently unknown
        (NULL/''/UNKNOWN for the hash, NULL otherwise); a differing
        KNOWN value fails loud (SidecarConflictError).
        """
        with self._txn():
            rows = self._q("SELECT revision_id, source_sha256, "
                           "revision_len, n_chunks_expected FROM docs "
                           "WHERE doc_id=?", (doc_id,))
            if not rows:
                raise SidecarConflictError(
                    f"doc {doc_id!r}: adoption without a declaration")
            have_rev, have_hash, _hlen, have_exp = rows[0]
            filled = []
            if revision_id is not None:
                if have_rev is None:
                    self._x("UPDATE docs SET revision_id=? WHERE "
                            "doc_id=?", (revision_id, doc_id))
                    filled.append("revision_id")
                elif have_rev != revision_id:
                    raise SidecarConflictError(
                        f"doc {doc_id!r}: revision conflict on adopt")
            if source_sha256 is not None:
                if have_hash in (None, "", "UNKNOWN"):
                    self._x("UPDATE docs SET source_sha256=?, "
                            "revision_len=?, source_verified=1 WHERE "
                            "doc_id=?",
                            (source_sha256, revision_len, doc_id))
                    filled.append("source_sha256")
                elif have_hash != source_sha256:
                    raise SidecarConflictError(
                        f"doc {doc_id!r}: source conflict on adopt")
            if n_chunks_expected is not None:
                if have_exp is None:
                    self._x("UPDATE docs SET n_chunks_expected=? "
                            "WHERE doc_id=?",
                            (n_chunks_expected, doc_id))
                    filled.append("n_chunks_expected")
                elif have_exp != n_chunks_expected:
                    raise SidecarConflictError(
                        f"doc {doc_id!r}: coverage conflict on adopt")
            if filled:
                self._bump_progress()
            return {"adopted": filled}

    # -- keyed reads ------------------------------------------------------
    def get_doc(self, doc_id):
        """Legacy-shaped doc entry (atoms/holon/xdoc/seg + coverage).

        None when undeclared. Keyed reads only (no table scans).
        """
        rows = self._q("SELECT revision_id, source_sha256, revision_len,"
                       " n_chunks_expected, source_verified, status,"
                       " holon_op FROM docs WHERE doc_id=?", (doc_id,))
        if not rows:
            return None
        (rev, hsh, rlen, exp, verified, status, holon) = rows[0]
        atoms = [r[0] for r in self._q(
            "SELECT op_id FROM doc_atoms WHERE doc_id=? ORDER BY "
            "ord_seq", (doc_id,))]
        xdoc = [r[0] for r in self._q(
            "SELECT op_id FROM doc_xdoc WHERE doc_id=? ORDER BY "
            "ord_seq", (doc_id,))]
        seg = [r[0] for r in self._q(
            "SELECT op_id FROM doc_seg WHERE doc_id=? ORDER BY "
            "ord_seq", (doc_id,))]
        return {"atoms": atoms, "holon": holon, "xdoc": xdoc,
                "seg": seg, "revision_id": rev,
                "source_sha256": hsh, "revision_len": rlen,
                "n_chunks_expected": exp,
                "source_verified": bool(verified), "status": status}

    def doc_detail(self, doc_id):
        """Committed-op detail for resume verification (keyed).

        Returns {"by_ix": {ix: {...}}, "lingering": [op_ids without
        chunk detail], "holon_op": op|None, "xdoc": [op_ids]}.
        """
        rows = self._q("SELECT chunk_ix, op_id, aid, b0, b1, "
                       "text_digest, revision_id, n_chunks, seq FROM "
                       "doc_atoms WHERE doc_id=?", (doc_id,))
        by_ix, lingering = {}, []
        for (ix, op_id, aid, b0, b1, dgst, rev, nch, seq) in rows:
            if ix is None:
                lingering.append(op_id)
                continue
            by_ix[ix] = {"op_id": op_id, "aid": aid,
                         "byte_span": (b0, b1),
                         "text_digest": dgst, "revision_id": rev,
                         "n_chunks": nch, "seq": seq}
        hol = self._q("SELECT holon_op, holon_members FROM docs "
                      "WHERE doc_id=?", (doc_id,))
        xdoc = [r[0] for r in self._q(
            "SELECT op_id FROM doc_xdoc WHERE doc_id=?", (doc_id,))]
        members = None
        if hol and hol[0][1] is not None:
            try:
                members = json.loads(hol[0][1])
            except ValueError:
                members = None
        return {"by_ix": by_ix, "lingering": lingering,
                "holon_op": hol[0][0] if hol else None,
                "holon_members": members, "xdoc": xdoc}

    def is_pending(self, doc_id):
        return bool(self._q("SELECT 1 FROM pending WHERE doc_id=?",
                            (doc_id,)))

    def is_retired(self, doc_id):
        return bool(self._q("SELECT 1 FROM retired WHERE doc_id=?",
                            (doc_id,)))

    def is_organized(self, doc_id):
        return bool(self._q("SELECT 1 FROM seg_organized WHERE "
                            "doc_id=?", (doc_id,)))

    def pending_window(self, limit, after=0):
        """[(doc_id, queue_seq)] in queue order (LIMIT + cursor)."""
        return [(d, s) for d, s in self._q(
            "SELECT doc_id, queue_seq FROM pending WHERE queue_seq>? "
            "ORDER BY queue_seq LIMIT ?", (after, limit))]

    def pending_count(self):
        return self._get_counter("pending_depth")

    def pending_sample(self, limit=REMAINING_SAMPLE):
        return [d for d, _s in self.pending_window(limit)]

    def unorganized_window(self, limit, after=0):
        """[(doc_id, decl_seq)] acknowledged-with-atoms, unorganized."""
        return [(d, s) for d, s in self._q(
            "SELECT d.doc_id, d.decl_seq FROM docs d WHERE "
            "d.decl_seq>? AND EXISTS (SELECT 1 FROM doc_atoms a "
            "WHERE a.doc_id=d.doc_id) AND NOT EXISTS (SELECT 1 FROM "
            "seg_organized s WHERE s.doc_id=d.doc_id) ORDER BY "
            "d.decl_seq LIMIT ?", (after, limit))]

    def unorganized_count(self):
        return (self._get_counter("docs_with_atoms")
                - self._get_counter("organized_count"))

    # -- derived-progress advance (atomic, post-commit only) ------------
    def record_flush(self, op_records, statuses=None, frontier=None,
                     backlog_add=None, backlog_del=None,
                     organized=None, retired=None):
        """Advance derived progress in ONE atomic txn (post-commit).

        op_records: [{doc, kind, op_id, seq, ...}] with kind in
        (atom, holon, xholon, seg). atom carries chunk_ix/aid/
        byte_span/text_digest/revision_id/n_chunks; xholon carries
        xdoc_id. statuses: {doc: status}. frontier: (birth, epoch,
        seq, triple). organized: [doc_id]; retired: [doc_id].
        """
        statuses = statuses or {}
        recorded = 0
        with self._txn():
            for rec in op_records:
                self._record_op(rec)
                recorded += 1
            for doc, st in statuses.items():
                self._x("UPDATE docs SET status=? WHERE doc_id=?",
                        (st, doc))
            for doc in backlog_add or []:
                cur = self._x(
                    "INSERT OR IGNORE INTO pending(doc_id, queue_seq)"
                    " VALUES(?,?)",
                    (doc, self._next_seq("queue_pending")))
                if cur.rowcount:
                    self._bump_counter("pending_depth")
            for doc in backlog_del or []:
                cur = self._x("DELETE FROM pending WHERE doc_id=?",
                              (doc,))
                if cur.rowcount:
                    self._bump_counter("pending_depth", -1)
            for doc in organized or []:
                cur = self._x(
                    "INSERT OR IGNORE INTO seg_organized(doc_id, "
                    "queue_seq) VALUES(?,?)",
                    (doc, self._next_seq("queue_organized")))
                if cur.rowcount:
                    self._bump_counter("organized_count")
            for doc in retired or []:
                self._note_retired(doc)
            if frontier is not None:
                self._set_frontier(*frontier)
            pseq = self._bump_progress()
        return {"ops_recorded": recorded, "progress_seq": pseq}

    def _next_ord(self, table, doc_id):
        rows = self._q(f"SELECT MAX(ord_seq) FROM {table} WHERE "
                       "doc_id=?", (doc_id,))
        return (rows[0][0] or 0) + 1 if rows and rows[0][0] is not None \
            else 1

    def _record_op(self, rec):
        doc, kind, op_id = rec["doc"], rec["kind"], rec["op_id"]
        seq = rec.get("seq")
        if kind == "atom":
            b0, b1 = rec["byte_span"]
            first = not self._q("SELECT 1 FROM doc_atoms WHERE "
                                "doc_id=? LIMIT 1", (doc,))
            self._x("INSERT INTO doc_atoms(doc_id, chunk_ix, op_id, "
                    "aid, b0, b1, text_digest, revision_id, n_chunks,"
                    " seq, ord_seq) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (doc, rec["chunk_ix"], op_id, rec["aid"], b0, b1,
                     rec["text_digest"], rec["revision_id"],
                     rec["n_chunks"], seq,
                     self._next_ord("doc_atoms", doc)))
            self._bump_counter("atoms_committed")
            if first:
                self._bump_counter("docs_with_atoms")
        elif kind == "holon":
            members = rec.get("members")
            self._x("UPDATE docs SET holon_op=?, holon_members=? "
                    "WHERE doc_id=?",
                    (op_id,
                     json.dumps(list(members)) if members is not None
                     else None, doc))
            self._bump_counter("holons_committed")
        elif kind == "xholon":
            cur = self._x("INSERT OR IGNORE INTO doc_xdoc(doc_id, "
                          "op_id, seq, ord_seq) VALUES(?,?,?,?)",
                          (doc, op_id, seq,
                           self._next_ord("doc_xdoc", doc)))
            if cur.rowcount:
                self._bump_counter("xdoc_committed")
            cur = self._x("INSERT OR IGNORE INTO xdoc_ops(op_id, "
                          "xdoc_id, seq) VALUES(?,?,?)",
                          (op_id, rec.get("xdoc_id"), seq))
            if cur.rowcount:
                self._bump_counter("xdoc_versions")
        elif kind == "seg":
            self._x("INSERT INTO doc_seg(doc_id, op_id, seq, ord_seq)"
                    " VALUES(?,?,?,?)",
                    (doc, op_id, seq,
                     self._next_ord("doc_seg", doc)))
            self._bump_counter("seg_committed")
        else:
            raise SidecarError(f"unknown op kind {kind!r}")

    def _note_retired(self, doc_id):
        """Advisory retired mark + retired-unorganized count (in-txn)."""
        cur = self._x("INSERT OR IGNORE INTO retired(doc_id, "
                      "queue_seq) VALUES(?,?)",
                      (doc_id, self._next_seq("queue_retired")))
        if not cur.rowcount:
            return
        self._bump_counter("retired_count")
        has_atoms = self._q("SELECT 1 FROM doc_atoms WHERE doc_id=? "
                            "LIMIT 1", (doc_id,))
        organized = self._q("SELECT 1 FROM seg_organized WHERE "
                            "doc_id=?", (doc_id,))
        if has_atoms and not organized:
            self._bump_counter("retired_unorganized")

    def backlog_add(self, doc_id):
        return self.record_flush([], backlog_add=[doc_id])

    def backlog_del(self, doc_id):
        return self.record_flush([], backlog_del=[doc_id])

    def mark_organized(self, doc_id, seg_op_ids=()):
        recs = [{"doc": doc_id, "kind": "seg", "op_id": op,
                 "seq": None} for op in seg_op_ids]
        return self.record_flush(recs, organized=[doc_id])

    def mark_retired(self, doc_id):
        return self.record_flush([], retired=[doc_id])

    # -- projection frontier ----------------------------------------------
    def frontier(self):
        birth = self.meta("frontier_birth")
        epoch = self.meta("frontier_epoch")
        seq = self.meta("frontier_seq")
        triple = self.meta("frontier_triple")
        return {"birth": birth, "epoch": epoch,
                "seq": int(seq) if seq is not None else 0,
                "triple": triple}

    def _set_frontier(self, birth, epoch, seq, triple):
        have = self.frontier()
        gen_have = (have["birth"], have["epoch"])
        gen_now = (None if birth is None else str(birth),
                   None if epoch is None else str(epoch))
        if gen_now != (None, None):
            if gen_have == (None, None):
                self._set_meta("gen_birth", gen_now[0])
                self._set_meta("gen_epoch", gen_now[1])
            elif gen_have != gen_now:
                raise SidecarConflictError(
                    f"frontier generation changed ({gen_have[0]}:"
                    f"{gen_have[1]} -> {gen_now[0]}:{gen_now[1]})")
        if seq < have["seq"]:
            raise SidecarConflictError(
                f"frontier rewind refused ({have['seq']} -> {seq})")
        # NOTE: meta values stay NULL (never the string "None") while
        # the store generation is unborn (empty pin).
        self._x("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)",
                ("frontier_birth", gen_now[0]))
        self._x("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)",
                ("frontier_epoch", gen_now[1]))
        self._set_meta("frontier_seq", str(seq))
        self._set_meta("frontier_triple", triple)

    def set_frontier(self, birth, epoch, seq, triple):
        with self._txn():
            self._set_frontier(birth, epoch, seq, triple)
            return self._bump_progress()

    def validated_suffix_seq(self, pin):
        """Validated frontier seq for suffix consumption (or named error).

        The pin's generation must match; a sidecar frontier ahead of
        the pin (rewound store) fails loud. Returns the exclusive
        lower bound (consume seqs above it).
        """
        birth, epoch, mx = pin[0], pin[1], pin[2]
        have = self.frontier()
        if have["birth"] is not None and have["epoch"] is not None:
            if str(have["birth"]) != str(birth) \
                    or str(have["epoch"]) != str(epoch):
                raise SidecarCorruptError(
                    "producer sidecar generation "
                    f"({have['birth']}:{have['epoch']}) != live pin "
                    f"({birth}:{epoch})")
        if have["seq"] > mx:
            raise SidecarCorruptError(
                f"producer sidecar frontier {have['seq']} ahead of pin "
                f"max {mx} (store rewound; refusing)")
        return have["seq"]

    # -- candidate binding + export record (P-2, Sec 5.7) --------------
    def candidate_record(self):
        """The recorded candidate binding, or None when unbound."""
        raw = self.meta("candidate_json")
        if raw is None:
            if self.meta("candidate_version") is not None:
                raise SidecarCorruptError(
                    "producer sidecar candidate binding half-recorded "
                    "(version without record); refusing")
            return None
        try:
            rec = json.loads(raw)
        except ValueError as e:
            raise SidecarCorruptError(
                f"producer sidecar candidate binding unreadable: {e}"
            ) from e
        if not isinstance(rec, dict):
            raise SidecarCorruptError(
                "producer sidecar candidate binding is not an object; "
                "refusing")
        return rec

    def bind_candidate(self, profile=None, profile_id=None,
                       profile_sha256=None, compact_bounds=None,
                       archive_policy=ARCHIVE_POLICY_EXPLICIT):
        """Record the candidate configuration binding (once, immutable).

        Binds CANDIDATE_VERSION + backend + sidecar format/scheme +
        bind-time generation + catalog profile identity + archive
        policy + compaction bounds. Same-configuration rebinds are
        idempotent (the generation is recorded, not compared: the
        store generation is assigned at first commit, so a pre-commit
        bind cannot pin it); any configuration difference fails loud
        (SidecarConflictError). A bad profile, bad bounds, or a
        foreign archive policy fails closed BEFORE any write. The
        binding never bumps progress_seq: it is invisible to manifest
        derivation, so an archive stays current across a bind.
        """
        from tlsys.catalog import (catalog_row_budget,
                                   catalog_routing_enabled)
        from tlsys.proj import \
            validate_compact_bounds as _validate_bounds
        routing = catalog_routing_enabled(profile)
        rcat = catalog_row_budget(profile) if routing else None
        if archive_policy != ARCHIVE_POLICY_EXPLICIT:
            raise ValueError(
                f"unknown archive policy {archive_policy!r} (want "
                f"{ARCHIVE_POLICY_EXPLICIT!r})")
        bounds = _validate_bounds(compact_bounds)
        pin = self._tlstore.pin()
        record = {"version": CANDIDATE_VERSION,
                  "backend": KEYED_BACKEND_ID,
                  "sidecar_format": SIDECAR_FORMAT,
                  "scheme": ATOM_SCHEME,
                  "generation": [pin[0], pin[1]],
                  "profile": {"catalog_routing": routing,
                              "rcat": rcat, "profile_id": profile_id,
                              "profile_sha256": profile_sha256},
                  "archive_policy": archive_policy,
                  "compact": bounds, "bound_at_seq": None}
        with self._txn():
            have = self.candidate_record()
            if have is not None:
                skip = {"bound_at_seq", "generation"}
                canon_have = {k: v for k, v in have.items()
                              if k not in skip}
                canon_new = {k: v for k, v in record.items()
                             if k not in skip}
                if canon_have == canon_new:
                    return {"binding": have, "existing": True}
                raise SidecarConflictError(
                    "candidate binding already recorded with a "
                    "different configuration; refusing to rebind a "
                    "bound store")
            record["bound_at_seq"] = int(
                self.meta("progress_seq") or "0")
            self._set_meta("candidate_version", CANDIDATE_VERSION)
            self._set_meta("candidate_json",
                           json.dumps(record, sort_keys=True))
            return {"binding": record, "existing": False}

    def export_status(self):
        """Last archive vs current progress (currency verdict)."""
        exp = self.meta("export_seq")
        prog = int(self.meta("progress_seq") or "0")
        exp_i = int(exp) if exp is not None else None
        return {"exported_seq": exp_i, "progress_seq": prog,
                "current": exp_i is not None and exp_i == prog,
                "kind": self.meta("export_kind"),
                "reason": self.meta("export_reason")}

    def record_export(self, kind, reason):
        """Record an explicit archive at current progress (one txn).

        Never bumps progress_seq: the export reflects exactly this
        progress, so the archive is current until the next mutation.
        """
        with self._txn():
            prog = int(self.meta("progress_seq") or "0")
            self._set_meta("export_seq", str(prog))
            self._set_meta("export_kind", kind)
            self._set_meta("export_reason", reason)
            return {"exported_seq": prog, "progress_seq": prog}

    # -- legacy-manifest boundary -----------------------------------------
    def materialize_manifest(self):
        """Full legacy-shaped manifest dict (explicit archive ONLY).

        Field meanings + ordering match the legacy writer: doc entries
        in declaration order, op lists in record order, queues in queue
        order, stored statuses verbatim. Explicit archive requests
        call this exactly once; ordinary calls and the foreground
        never do (P-2, Sec 5.7).
        """
        out = {}
        for (doc,) in self._q("SELECT doc_id FROM docs ORDER BY "
                              "decl_seq"):
            e = self.get_doc(doc)
            out[doc] = {"atoms": e["atoms"], "holon": e["holon"],
                        "xdoc": e["xdoc"],
                        "revision_id": e["revision_id"],
                        "source_sha256": e["source_sha256"],
                        "revision_len": e["revision_len"],
                        "n_chunks_expected": e["n_chunks_expected"],
                        "source_verified": e["source_verified"],
                        "status": e["status"]}
            if e["seg"]:
                out[doc]["seg"] = list(e["seg"])
        out["_scheme"] = ATOM_SCHEME
        out["_pending_placement"] = [r[0] for r in self._q(
            "SELECT doc_id FROM pending ORDER BY queue_seq")]
        out["_seg_organized"] = [r[0] for r in self._q(
            "SELECT doc_id FROM seg_organized ORDER BY queue_seq")]
        out["_retired"] = [r[0] for r in self._q(
            "SELECT doc_id FROM retired ORDER BY queue_seq")]
        out["_sidecar_seq"] = int(self.meta("progress_seq") or "0")
        return out

    # -- migration (legacy manifest + committed truth join) ---------------
    def _migrate_from_manifest(self, manifest):
        """One-time adoption: manifest rows + crash-window adoption.

        A single committed-truth pass joins manifest op_ids to their
        chunk detail (ordering preserved via ord_seq), adopts
        committed-but-unrecorded ops (the crash window, like
        reconcile_manifest), attributes xdoc versions to member docs,
        and stamps the frontier at the pin. Receipted; statuses kept
        verbatim (keyed flows re-derive touched docs).
        """
        import json as _json
        tlstore = self._tlstore
        birth, epoch, mx, triple = tlstore.pin()
        rows = tlstore.read_commits_all(birth, epoch, mx,
                                        kind="ACCEPT_ATOMS")
        seqs = [r[0] for r in rows]
        op_of_seq = {r[0]: r[1] for r in rows}
        refs = tlstore.pub_refs(seqs)
        arows = tlstore.artifact_rows(
            [a for seq in seqs for a in refs.get(seq, [])])
        atom_by_op, holon_latest, xdoc_metas = {}, {}, []
        holon_members_by_op = {}
        aid_doc, retired_truth = {}, set()
        for seq in seqs:
            for art_id in refs.get(seq, []):
                arow = arows.get(art_id)
                if arow is None:
                    continue
                try:
                    body = tlstore.read_artifact(
                        art_id, expect_digest=arow[4])
                    meta = _json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(meta, dict):
                    continue
                if meta.get("atom_scheme") != ATOM_SCHEME:
                    continue
                ret = meta.get("retirement")
                if isinstance(ret, dict) \
                        and isinstance(ret.get("doc"), str):
                    retired_truth.add(ret["doc"])
                    continue
                op_id = op_of_seq[seq]
                if "atom" in meta and "doc_id" in meta:
                    atom_by_op[op_id] = {
                        "doc": meta["doc_id"], "seq": seq,
                        "chunk_ix": meta.get("chunk_ix"),
                        "aid": meta.get("atom"),
                        "byte_span": tuple(
                            meta.get("byte_span", ())),
                        "text_digest": meta.get("text_digest"),
                        "revision_id": meta.get("revision_id"),
                        "n_chunks": meta.get("n_chunks")}
                    aid_doc.setdefault(meta["atom"], meta["doc_id"])
                elif "holon" in meta and "members" in meta:
                    hid = meta["holon"]
                    if meta.get("kind") in ("seg-leaf", "seg-parent"):
                        continue  # seg history: organize marks only
                    if isinstance(hid, str) and hid.startswith("xdoc-"):
                        xdoc_metas.append(
                            (op_id, hid,
                             list(meta.get("members", [])), seq))
                    elif isinstance(hid, str):
                        holon_latest[hid] = op_id
                        holon_members_by_op[op_id] = list(
                            meta.get("members", []))
        # xdoc attribution (reconcile rule): every version joins every
        # member doc's history; placed = any-aid-membership.
        xdoc_by_doc, placed_docs = {}, set()
        for op_id, _hid, members, _seq in xdoc_metas:
            for aid in members:
                doc = aid_doc.get(aid)
                if doc is None:
                    continue
                placed_docs.add(doc)
                xdoc_by_doc.setdefault(doc, []).append(op_id)
        migrated, adopted, mop = 0, 0, 0
        with self._txn():
            for doc, entry in manifest.items():
                if doc.startswith("_") \
                        or not isinstance(entry, dict):
                    continue
                atoms = entry.get("atoms") or []
                have_ops = set(atoms)
                detail = []
                for pos, op_id in enumerate(atoms):
                    d = atom_by_op.get(op_id)
                    if d is not None and d["doc"] == doc:
                        detail.append((d, pos))
                    else:
                        detail.append((None, pos))  # lingering
                # Crash-window adoption: committed but unrecorded.
                extra = sorted(
                    (d["seq"], op_id)
                    for op_id, d in atom_by_op.items()
                    if d["doc"] == doc and op_id not in have_ops)
                decl = self._next_seq("decl_seq")
                holon = entry.get("holon") \
                    or holon_latest.get(doc)
                members = holon_members_by_op.get(holon)
                rev = entry.get("revision_id")
                if rev is None:
                    # Reconcile rule: first committed revision in seq
                    # order (resume refines/refuses from here).
                    crevs = sorted(
                        (d["seq"], d["revision_id"])
                        for op_id, d in atom_by_op.items()
                        if d["doc"] == doc
                        and d["revision_id"] is not None)
                    rev = crevs[0][1] if crevs else None
                self._x("INSERT INTO docs(doc_id, decl_seq, "
                        "revision_id, source_sha256, revision_len, "
                        "n_chunks_expected, source_verified, status,"
                        " holon_op, holon_members, updated_seq) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (doc, decl, rev,
                         entry.get("source_sha256"),
                         entry.get("revision_len"),
                         entry.get("n_chunks_expected"),
                         1 if entry.get("source_verified") else 0,
                         entry.get("status"), holon,
                         json.dumps(members) if members is not None
                         else None, None))
                self._bump_counter("docs_declared")
                if holon:
                    self._bump_counter("holons_committed")
                ordn = 0
                for d, _pos in detail:
                    ordn += 1
                    mop += 1
                    if d is None:
                        self._x("INSERT INTO doc_atoms(doc_id, "
                                "chunk_ix, op_id, ord_seq) VALUES("
                                "?,?,?,?)",
                                (doc, None, atoms[_pos], ordn))
                        self._bump_counter("atoms_committed")
                        continue
                    b0, b1 = (d["byte_span"] + (None, None))[:2]
                    self._x("INSERT INTO doc_atoms(doc_id, chunk_ix,"
                            " op_id, aid, b0, b1, text_digest, "
                            "revision_id, n_chunks, seq, ord_seq) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (doc, d["chunk_ix"], atoms[_pos],
                             d["aid"], b0, b1, d["text_digest"],
                             d["revision_id"], d["n_chunks"], d["seq"],
                             ordn))
                    self._bump_counter("atoms_committed")
                for _seq, op_id in extra:
                    d = atom_by_op[op_id]
                    ordn += 1
                    adopted += 1
                    b0, b1 = (d["byte_span"] + (None, None))[:2]
                    self._x("INSERT INTO doc_atoms(doc_id, chunk_ix,"
                            " op_id, aid, b0, b1, text_digest, "
                            "revision_id, n_chunks, seq, ord_seq) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (doc, d["chunk_ix"], op_id, d["aid"], b0,
                             b1, d["text_digest"], d["revision_id"],
                             d["n_chunks"], d["seq"], ordn))
                    self._bump_counter("atoms_committed")
                if detail or extra:
                    self._bump_counter("docs_with_atoms")
                xord = 0
                seen_x = set()
                for op_id in (entry.get("xdoc") or []):
                    if op_id in seen_x:
                        continue
                    seen_x.add(op_id)
                    xord += 1
                    mop += 1
                    cur = self._x("INSERT OR IGNORE INTO doc_xdoc("
                                  "doc_id, op_id, seq, ord_seq) "
                                  "VALUES(?,?,?,?)",
                                  (doc, op_id, None, xord))
                    if cur.rowcount:
                        self._bump_counter("xdoc_committed")
                for op_id in xdoc_by_doc.get(doc, []):
                    if op_id in seen_x:
                        continue
                    seen_x.add(op_id)
                    xord += 1
                    adopted += 1
                    seq = next((s for o, _h, _m, s in xdoc_metas
                                if o == op_id), None)
                    cur = self._x("INSERT OR IGNORE INTO doc_xdoc("
                                  "doc_id, op_id, seq, ord_seq) "
                                  "VALUES(?,?,?,?)",
                                  (doc, op_id, seq, xord))
                    if cur.rowcount:
                        self._bump_counter("xdoc_committed")
                sord = 0
                for op_id in (entry.get("seg") or []):
                    sord += 1
                    mop += 1
                    cur = self._x("INSERT OR IGNORE INTO doc_seg("
                                  "doc_id, op_id, seq, ord_seq) "
                                  "VALUES(?,?,?,?)",
                                  (doc, op_id, None, sord))
                    if cur.rowcount:
                        self._bump_counter("seg_committed")
                migrated += 1
            # Sourceless recovery (reconcile rule): committed atoms
            # for docs with no manifest entry declare minimally
            # (UNKNOWN source; R8-C applies on next supplied bytes).
            # Coverage pins to committed truth when unambiguous.
            manifest_docs = {doc for doc, entry in manifest.items()
                             if not doc.startswith("_")
                             and isinstance(entry, dict)}
            committed_docs = {d["doc"] for d in atom_by_op.values()}
            committed_docs |= {h for h in holon_latest
                               if not h.startswith("xdoc-")}
            sourceless = []
            for doc in sorted(committed_docs - manifest_docs):
                if doc.startswith("xdoc-"):
                    continue
                datoms = sorted(
                    (d["seq"], op_id)
                    for op_id, d in atom_by_op.items()
                    if d["doc"] == doc)
                rev = next((atom_by_op[o]["revision_id"]
                            for _s, o in datoms
                            if atom_by_op[o]["revision_id"] is not None),
                           None)
                nch = {atom_by_op[o]["n_chunks"] for _s, o in datoms}
                nch.discard(None)
                decl = self._next_seq("decl_seq")
                holon = holon_latest.get(doc)
                members = holon_members_by_op.get(holon)
                self._x("INSERT INTO docs(doc_id, decl_seq, "
                        "revision_id, source_sha256, revision_len, "
                        "n_chunks_expected, source_verified, status,"
                        " holon_op, holon_members, updated_seq) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (doc, decl, rev, "UNKNOWN", None,
                         next(iter(nch)) if len(nch) == 1 else None,
                         0, None, holon,
                         _json.dumps(members)
                         if members is not None else None, None))
                self._bump_counter("docs_declared")
                if holon:
                    self._bump_counter("holons_committed")
                ordn = 0
                for _seq, op_id in datoms:
                    d = atom_by_op[op_id]
                    ordn += 1
                    adopted += 1
                    b0, b1 = (d["byte_span"] + (None, None))[:2]
                    self._x("INSERT INTO doc_atoms(doc_id, chunk_ix,"
                            " op_id, aid, b0, b1, text_digest, "
                            "revision_id, n_chunks, seq, ord_seq) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (doc, d["chunk_ix"], op_id, d["aid"], b0,
                             b1, d["text_digest"], d["revision_id"],
                             d["n_chunks"], d["seq"], ordn))
                    self._bump_counter("atoms_committed")
                if datoms:
                    self._bump_counter("docs_with_atoms")
                xord = 0
                for op_id in xdoc_by_doc.get(doc, []):
                    xord += 1
                    adopted += 1
                    seq = next((s for o, _h, _m, s in xdoc_metas
                                if o == op_id), None)
                    cur = self._x("INSERT OR IGNORE INTO doc_xdoc("
                                  "doc_id, op_id, seq, ord_seq) "
                                  "VALUES(?,?,?,?)",
                                  (doc, op_id, seq, xord))
                    if cur.rowcount:
                        self._bump_counter("xdoc_committed")
                sourceless.append(doc)
            for op_id, hid, _members, seq in xdoc_metas:
                cur = self._x("INSERT OR IGNORE INTO xdoc_ops(op_id, "
                              "xdoc_id, seq) VALUES(?,?,?)",
                              (op_id, hid, seq))
                if cur.rowcount:
                    self._bump_counter("xdoc_versions")
            for doc in manifest.get("_pending_placement", []):
                cur = self._x("INSERT OR IGNORE INTO pending(doc_id, "
                              "queue_seq) VALUES(?,?)",
                              (doc, self._next_seq("queue_pending")))
                if cur.rowcount:
                    self._bump_counter("pending_depth")
            # Backlog recompute (reconcile rule): acknowledged +
            # committed but never placed and not pending -> pending.
            for doc, entry in manifest.items():
                if doc.startswith("_") \
                        or not isinstance(entry, dict):
                    continue
                if doc not in placed_docs \
                        and not (entry.get("xdoc") or []) \
                        and not xdoc_by_doc.get(doc) \
                        and not self._q("SELECT 1 FROM pending WHERE"
                                        " doc_id=?", (doc,)):
                    cur = self._x("INSERT OR IGNORE INTO pending("
                                  "doc_id, queue_seq) VALUES(?,?)",
                                  (doc, self._next_seq(
                                      "queue_pending")))
                    if cur.rowcount:
                        self._bump_counter("pending_depth")
            for doc in sourceless:
                if doc not in placed_docs \
                        and not xdoc_by_doc.get(doc):
                    cur = self._x("INSERT OR IGNORE INTO pending("
                                  "doc_id, queue_seq) VALUES(?,?)",
                                  (doc, self._next_seq(
                                      "queue_pending")))
                    if cur.rowcount:
                        self._bump_counter("pending_depth")
            for doc in manifest.get("_seg_organized", []):
                cur = self._x("INSERT OR IGNORE INTO seg_organized("
                              "doc_id, queue_seq) VALUES(?,?)",
                              (doc, self._next_seq("queue_organized")))
                if cur.rowcount:
                    self._bump_counter("organized_count")
            for doc in list(manifest.get("_retired", [])) + sorted(
                    retired_truth):
                self._note_retired(doc)
            self._set_frontier(birth, epoch, mx, triple)
            self._bump_progress()
        return {"migrated_docs": migrated, "migrated_ops": mop,
                "adopted_ops": adopted, "sourceless": sourceless,
                "meta_join_commits": len(seqs), "frontier": mx}

    # -- persisted routing snapshots --------------------------------------
    @staticmethod
    def _pack_routing(population, n, dim, rcat, frontier, ids, mat,
                      norms, counts):
        import numpy as _np
        mat_b = _np.ascontiguousarray(mat, dtype=_np.float64).tobytes()
        norms_b = _np.ascontiguousarray(norms,
                                        dtype=_np.float64).tobytes()
        counts_b = _np.ascontiguousarray(counts,
                                         dtype=_np.int64).tobytes()
        header = {"population": population, "n": int(n),
                  "dim": int(dim), "rcat": int(rcat),
                  "frontier": int(frontier), "ids": list(ids)}
        canon = json.dumps(header, sort_keys=True,
                           separators=(",", ":")).encode()
        digest = hashlib.sha256(canon + mat_b + norms_b
                                + counts_b).hexdigest()
        header["digest"] = digest
        hbytes = json.dumps(header, sort_keys=True,
                            separators=(",", ":")).encode()
        return (struct.pack("<I", len(hbytes)) + hbytes + mat_b
                + norms_b + counts_b), digest

    @staticmethod
    def _unpack_routing(blob):
        import numpy as _np
        if len(blob) < 4:
            raise RoutingMismatch("routing snapshot truncated")
        (hlen,) = struct.unpack("<I", blob[:4])
        try:
            header = json.loads(blob[4:4 + hlen].decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise RoutingMismatch(
                f"routing snapshot header corrupt: {e}") from e
        n, dim = header.get("n"), header.get("dim")
        if not isinstance(n, int) or not isinstance(dim, int) \
                or n < 0 or dim <= 0:
            raise RoutingMismatch("routing snapshot shape invalid")
        if not isinstance(header.get("ids"), list) \
                or len(header["ids"]) != n \
                or len(set(header["ids"])) != n:
            raise RoutingMismatch(
                "routing snapshot ordinal map invalid")
        want = 4 + hlen + n * dim * 8 + n * 8 + n * 8
        if len(blob) != want:
            raise RoutingMismatch(
                f"routing snapshot size {len(blob)} != {want}")
        off = 4 + hlen
        mat_b = blob[off:off + n * dim * 8]
        off += n * dim * 8
        norms_b = blob[off:off + n * 8]
        off += n * 8
        counts_b = blob[off:off + n * 8]
        digest = header.pop("digest", None)
        canon = json.dumps(header, sort_keys=True,
                           separators=(",", ":")).encode()
        actual = hashlib.sha256(canon + mat_b + norms_b
                                + counts_b).hexdigest()
        if digest != actual:
            raise RoutingMismatch(
                "routing snapshot digest mismatch (bytes changed; "
                "rebuilding)")
        mat = _np.frombuffer(mat_b, dtype=_np.float64).reshape(n, dim)
        norms = _np.frombuffer(norms_b, dtype=_np.float64).reshape(n)
        counts = _np.frombuffer(counts_b, dtype=_np.int64).reshape(n)
        return {"population": header.get("population"), "n": n,
                "dim": dim, "rcat": header.get("rcat"),
                "frontier": header.get("frontier"),
                "ids": header.get("ids"), "mat": mat.copy(),
                "norms": norms.copy(), "counts": counts.copy()}

    def store_routing(self, population, n, dim, rcat, frontier, ids,
                      mat, norms, counts):
        """Persist one population's routing snapshot (boundary write)."""
        blob, digest = self._pack_routing(
            population, n, dim, rcat, frontier, ids, mat, norms,
            counts)
        with self._txn():
            self._x("INSERT OR REPLACE INTO routing_populations("
                    "population, frontier, n, dim, rcat, digest, blob)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (population, frontier, n, dim, rcat, digest, blob))
        return {"population": population, "n": n, "digest": digest,
                "bytes": len(blob)}

    def load_routing(self, population):
        """Load one snapshot (None when absent; RoutingMismatch when bad)."""
        rows = self._q("SELECT blob FROM routing_populations WHERE "
                       "population=?", (population,))
        if not rows:
            return None
        return self._unpack_routing(bytes(rows[0][0]))

    def fill_atom_detail(self, doc_id, op_id, chunk_ix, aid, byte_span,
                         text_digest, revision_id, n_chunks, seq):
        """Fill a lingering op's chunk detail (named recovery only).

        Updates the recorded-but-detail-less row; unknown op_ids insert
        (crash-window adoption). One atomic txn.
        """
        b0, b1 = byte_span
        with self._txn():
            rows = self._q("SELECT chunk_ix FROM doc_atoms WHERE "
                           "doc_id=? AND op_id=?", (doc_id, op_id))
            if rows and rows[0][0] is None:
                self._x("UPDATE doc_atoms SET chunk_ix=?, aid=?, "
                        "b0=?, b1=?, text_digest=?, revision_id=?, "
                        "n_chunks=?, seq=? WHERE doc_id=? AND op_id=?",
                        (chunk_ix, aid, b0, b1, text_digest,
                         revision_id, n_chunks, seq, doc_id, op_id))
                self._bump_counter("atoms_committed")
            elif not rows:
                self._x("INSERT INTO doc_atoms(doc_id, chunk_ix, "
                        "op_id, aid, b0, b1, text_digest, "
                        "revision_id, n_chunks, seq, ord_seq) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (doc_id, chunk_ix, op_id, aid, b0, b1,
                         text_digest, revision_id, n_chunks, seq,
                         self._next_ord("doc_atoms", doc_id)))
                self._bump_counter("atoms_committed")
            # else: already detailed (idempotent retry): no-op.
            self._bump_progress()


# ---------------------------------------------------------------------------
# Suffix adoption (§5.2 item 2)
# ---------------------------------------------------------------------------

def consume_suffix(tlstore, state, touched=None):
    """Adopt every committed op in the pinned suffix (bounded, receipted).

    Every keyed mutating call runs this first: it validates the sidecar
    frontier against the live pin, decodes ONLY seqs above it (never a
    prefix rescan), adopts all crash-window ops (atoms/holons/xdoc
    attribution/retirements, all docs -- not just the touched one, so
    the frontier can advance without stranding truth), and advances the
    frontier to the pin max in the same atomic txn. Clean calls (no new
    commits) cost one pin + one compare and read nothing. Seg versions
    are intentionally not adopted (reconcile rule: seg history grows
    through organize marks only). touched (optional list) collects
    touched doc ids for recovery receipts.
    """
    from tlsys.proj import Projections
    pin = tlstore.pin()
    birth, epoch, mx, triple = pin
    from_seq = state.validated_suffix_seq(pin)
    if from_seq >= mx:
        return {"suffix_commits": 0, "suffix_artifacts": 0,
                "suffix_bytes": 0, "adopted_ops": 0, "frontier": mx}
    metas, counts = Projections.suffix_metas(tlstore, from_seq)
    adopted = 0
    with state._txn():
        for seq, op_id, meta in metas:
            adopted += _adopt_meta(state, seq, op_id, meta, touched)
        state._set_frontier(birth, epoch, mx, triple)
        state._bump_progress()
    return {"suffix_commits": counts["commits"],
            "suffix_artifacts": counts["artifacts"],
            "suffix_bytes": counts["bytes"], "adopted_ops": adopted,
            "frontier": mx}


def _adopt_meta(state, seq, op_id, meta, touched=None):
    """Adopt one suffix meta into the sidecar (in-txn). Returns 0/1+."""
    if meta.get("atom_scheme") != ATOM_SCHEME:
        return 0  # foreign scheme: refused by readers, not adopted
    ret = meta.get("retirement")
    if isinstance(ret, dict) and isinstance(ret.get("doc"), str):
        before = state._get_counter("retired_count")
        state._note_retired(ret["doc"])
        if touched is not None:
            touched.append(ret["doc"])
        return 1 if state._get_counter("retired_count") > before \
            else 0
    if "atom" in meta and "doc_id" in meta:
        doc = meta["doc_id"]
        if not isinstance(doc, str):
            return 0
        if not state._q("SELECT 1 FROM docs WHERE doc_id=?", (doc,)):
            # Sourceless recovery (reconcile rule): committed atoms
            # for an undeclared doc declare minimally; R8-C rules
            # apply when source is next supplied.
            state._x("INSERT INTO docs(doc_id, decl_seq, revision_id,"
                    " source_sha256, revision_len, "
                    "n_chunks_expected, source_verified, status, "
                    "holon_op, holon_members, updated_seq) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (doc, state._next_seq("decl_seq"),
                     meta.get("revision_id"), "UNKNOWN", None,
                     meta.get("n_chunks"), 0, None, None, None,
                     None))
            state._bump_counter("docs_declared")
        rows = state._q("SELECT chunk_ix FROM doc_atoms WHERE doc_id=?"
                        " AND op_id=?", (doc, op_id))
        if rows and rows[0][0] is not None:
            return 0  # already recorded
        bspan = tuple(meta.get("byte_span", ())) + (None, None)
        if rows:
            state._x("UPDATE doc_atoms SET chunk_ix=?, aid=?, b0=?, "
                     "b1=?, text_digest=?, revision_id=?, n_chunks=?,"
                     " seq=? WHERE doc_id=? AND op_id=?",
                     (meta.get("chunk_ix"), meta.get("atom"), bspan[0],
                      bspan[1], meta.get("text_digest"),
                      meta.get("revision_id"), meta.get("n_chunks"),
                      seq, doc, op_id))
        else:
            first = not state._q("SELECT 1 FROM doc_atoms WHERE "
                                 "doc_id=? LIMIT 1", (doc,))
            state._x("INSERT INTO doc_atoms(doc_id, chunk_ix, op_id,"
                    " aid, b0, b1, text_digest, revision_id, "
                    "n_chunks, seq, ord_seq) VALUES(?,?,?,?,?,?,?,?,"
                    "?,?,?)",
                    (doc, meta.get("chunk_ix"), op_id,
                     meta.get("atom"), bspan[0], bspan[1],
                     meta.get("text_digest"), meta.get("revision_id"),
                     meta.get("n_chunks"), seq,
                     state._next_ord("doc_atoms", doc)))
            if first:
                state._bump_counter("docs_with_atoms")
        state._bump_counter("atoms_committed")
        if touched is not None:
            touched.append(doc)
        return 1
    hid = meta.get("holon")
    if not isinstance(hid, str) or "members" not in meta:
        return 0
    if meta.get("kind") in ("seg-leaf", "seg-parent"):
        return 0  # seg history grows through organize marks only
    members = list(meta.get("members", []))
    if hid.startswith("xdoc-"):
        n = 0
        seen_docs = set()
        for aid in members:
            for (doc,) in state._q("SELECT doc_id FROM doc_atoms "
                                   "WHERE aid=?", (aid,)):
                if doc in seen_docs:
                    continue
                seen_docs.add(doc)
                if touched is not None:
                    touched.append(doc)
                cur = state._x("INSERT OR IGNORE INTO doc_xdoc(doc_id,"
                              " op_id, seq, ord_seq) VALUES(?,?,?,?)",
                              (doc, op_id, seq,
                               state._next_ord("doc_xdoc", doc)))
                if cur.rowcount:
                    state._bump_counter("xdoc_committed")
                    n += 1
        cur = state._x("INSERT OR IGNORE INTO xdoc_ops(op_id, "
                         "xdoc_id, seq) VALUES(?,?,?)",
                         (op_id, hid, seq))
        if cur.rowcount:
            state._bump_counter("xdoc_versions")
        return n
    # Per-doc holon: latest wins (ascending seqs); members recorded
    # for the resume-vs-bytes check (exact legacy correspondence).
    if not state._q("SELECT 1 FROM docs WHERE doc_id=?", (hid,)):
        state._x("INSERT INTO docs(doc_id, decl_seq, revision_id,"
                " source_sha256, revision_len, n_chunks_expected, "
                "source_verified, status, holon_op, holon_members, "
                "updated_seq) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (hid, state._next_seq("decl_seq"), None, "UNKNOWN",
                 None, None, 0, None, None, None, None))
        state._bump_counter("docs_declared")
    state._x("UPDATE docs SET holon_op=?, holon_members=? WHERE "
             "doc_id=?", (op_id, json.dumps(members), hid))
    state._bump_counter("holons_committed")
    if touched is not None:
        touched.append(hid)
    return 1


# ---------------------------------------------------------------------------
# R_cat pre-execution cost model (§5.2 item 5)
#
# One operation = all top_k calls the decision executes (xdoc/parent: 1;
# leaf: 2 — eligible + full masks). The estimate counts native rows,
# both leaf masks, analytic head-copy/sort-temp bounds, and calls
# BEFORE any scan runs. Score-dependent terms (m_qual) are unknowable
# pre-execution without scoring, so they ride as analytic UPPER bounds
# (O-7 ledger form); the gate itself uses the score-independent native-
# rows bound (n per call). Over budget -> OverBudgetRejected BEFORE any
# top_k executes; under budget runs the full exact scan (never a
# truncated population).
# ---------------------------------------------------------------------------

def estimate_op_cost(population, n, rows_per_call, dim, k_per_call,
                     rcat=None):
    """Pre-execution cost estimate for one exact decision operation."""
    rows_per_call = [int(r) for r in rows_per_call]
    k_per_call = [int(k) for k in k_per_call]
    calls = len(rows_per_call)
    if calls != len(k_per_call):
        raise ValueError("rows_per_call/k_per_call length mismatch")
    bound_native = int(n) * calls
    budget = (int(rcat) * calls) if rcat is not None else None
    # Each call's mask is computed twice (gate estimate + decide
    # exact): int64 count-vector read + bool write per computation.
    mask_bytes = calls * 2 * int(n) * 16
    sort_temp = 0
    head_copy = 0
    for rows, k in zip(rows_per_call, k_per_call):
        sort_temp += max(rows * 8 * 4, rows * 8 * 3 + 512)
        head_copy += min(max(k, 0), rows) * 16
    d8 = int(dim) * 8
    return {"population": population, "n": int(n), "calls": calls,
            "mask_rows": rows_per_call,
            "bound_native_rows": bound_native,
            "budget_rows": budget,
            "over_budget": bool(budget is not None
                                and bound_native > budget),
            "mask_bytes": mask_bytes,
            "sort_temp_bound_B": sort_temp,
            "head_copy_bound_B": head_copy,
            "descriptor_bound_B": bound_native * d8,
            "copy_bound_B": sum(2 * r * d8 for r in rows_per_call),
            "scores_norms_bound_B": calls * int(n) * 64}


def gate_decision(population, n, dim, rows_per_call, k_per_call, rcat,
                  where):
    """Estimate + enforce the R_cat pre-execution boundary.

    Returns the estimate when the operation fits; raises
    OverBudgetRejected (carrying .estimate) BEFORE any scan otherwise.
    """
    est = estimate_op_cost(population, n, rows_per_call, dim,
                           k_per_call, rcat=rcat)
    if est["over_budget"]:
        raise OverBudgetRejected(
            f"{where}: over-budget: operation needs "
            f"{est['bound_native_rows']} native rows over "
            f"{est['calls']} call(s), budget {est['budget_rows']} "
            f"(R_cat {rcat}); refusing before any scan",
            est)
    return est


# ---------------------------------------------------------------------------
# Producer-session routing reuse (§5.2 item 3)
# ---------------------------------------------------------------------------

def _catalog_from_payload(population, payload, rcat):
    """Materialize a Catalog from a validated snapshot (no rebuild).

    Same-package private fill (layout-pinned, digest-validated bytes);
    growth/ordering behavior identical to a fresh build reaching n.
    """
    import numpy as _np
    from tlsys.catalog import Catalog
    n, dim = payload["n"], payload["dim"]
    cat = Catalog(population, dim, rcat)
    cap = 256
    while cap < n:
        cap *= 2
    mat = _np.zeros((cap, dim), dtype=_np.float64)
    mat[:n] = payload["mat"]
    norms = _np.ones((cap,), dtype=_np.float64)
    norms[:n] = payload["norms"]
    counts = _np.zeros((cap,), dtype=_np.int64)
    counts[:n] = payload["counts"]
    cat._mat, cat._norms, cat._counts = mat, norms, counts
    cat._ids = list(payload["ids"])
    cat._ordinal = {h: i for i, h in enumerate(cat._ids)}
    cat._n = n
    cat._cap = cap
    cat._snap = None
    cat.budget_exceeded = False
    return cat


def _seq_of(entry):
    seq = entry.get("seq")
    return seq if isinstance(seq, int) else 0


class ProducerSession:
    """Producer-process routing reuse (catalogs + reverse indexes).

    Legs (xdoc / hier) hold committed-mirror working state keyed by
    incarnation + synced frontier. First use builds from projection
    views (receipted full pass) or restores catalog matrices from
    persisted snapshots (digest-validated, zero rebuild rows); later
    uses advance by committed delta (seq-sorted upserts preserving
    first-seen ordinal order, D2-identical to fresh builds).
    Same-call emissions absorb directly (as today); leg_sync() at call
    end refreshes touched entries from post-commit views and moves the
    synced frontier. persist() writes restart-ready snapshots for
    engaged+dirty legs (skipped when clean, so steady calls persist
    nothing). Reverse indexes + membership dicts reuse in memory;
    after a restart they re-derive from the checkpoint on first leg
    use (counted residual; catalog matrices never rebuild).
    """

    def __init__(self, profile=None):
        self._profile = profile
        self._incarnation = None
        self._snapshots = {}
        self._xdoc = None
        self._hier = None
        self._call = None

    # -- attach ---------------------------------------------------------
    def attach(self, tlstore, state=None):
        """Bind to a store incarnation; validate routing snapshots.

        A stored PRE-BIRTH incarnation is unbound: when the only
        change is empty→born, attach re-binds to the live born
        incarnation (receipted as rebound_prebirth) and keeps the
        legs, which already mirror this store's committed truth. Every
        other mismatch (born→born', born→pre-birth, cross-store)
        still refuses: one session serves one store generation.
        """
        from tlsys.catalog import (catalog_row_budget,
                                   catalog_routing_enabled)
        pin = tlstore.pin()
        inc = incarnation_of(pin)
        rebound = False
        if self._incarnation is None or self._incarnation == inc:
            self._incarnation = inc
        elif _is_prebirth_incarnation(self._incarnation) \
                and not _is_prebirth_incarnation(inc):
            self._incarnation = inc
            rebound = True
        else:
            raise SidecarConflictError(
                f"session incarnation {self._incarnation} != live "
                f"{inc}: one session serves one store generation")
        rec = {"attached": True, "incarnation": inc,
               "routing_restored": False, "restored_pops": [],
               "mismatched_pops": [], "profile_changed_pops": [],
               "digest_mismatch": False, "rebuilt_rows": 0,
               "rebound_prebirth": rebound}
        routing_on = False
        rcat = None
        if self._profile is not None:
            routing_on = catalog_routing_enabled(self._profile)
            if routing_on:
                rcat = catalog_row_budget(self._profile)
        if not routing_on:
            rec["reason"] = "catalog routing off"
            return rec
        if self._xdoc is not None or self._hier is not None:
            # Warm legs are authoritative (they advanced past any
            # snapshot); skip snapshot I/O on re-attach.
            rec["reason"] = "legs warm"
            return rec
        own = state is None
        if own:
            try:
                state = ProducerState.open(tlstore)
            except SidecarMissingError:
                rec["reason"] = "no sidecar yet"
                return rec
        try:
            for pop in ("xholon", "leaf", "parent"):
                try:
                    payload = state.load_routing(pop)
                except RoutingMismatch:
                    rec["mismatched_pops"].append(pop)
                    continue
                if payload is None:
                    continue
                if payload.get("rcat") != rcat:
                    rec["profile_changed_pops"].append(pop)
                    continue
                self._snapshots[pop] = payload
                rec["restored_pops"].append(pop)
        finally:
            if own:
                state.close()
        rec["digest_mismatch"] = bool(rec["mismatched_pops"])
        rec["routing_restored"] = bool(rec["restored_pops"]) \
            and not rec["mismatched_pops"] \
            and not rec["profile_changed_pops"]
        return rec

    def begin_call(self):
        self._call = {"built_from_views": False, "rebuilt_rows": 0,
                      "view_rows": 0, "advance_upserts": 0,
                      "restored": [], "persisted": [],
                      "snapshot_dropped": []}

    def call_receipt(self):
        return dict(self._call) if self._call is not None else {}

    def _ensure_call(self):
        if self._call is None:
            self.begin_call()

    def _live_rcat(self):
        from tlsys.catalog import catalog_row_budget
        return catalog_row_budget(self._profile)

    # -- xdoc leg ---------------------------------------------------------
    def ensure_xdoc(self, views, frontier, with_atom_index=False):
        """(xdict, atom_idx|None); dicts advanced to frontier.

        views: {hid: entry} with members/descriptor/seq (projection
        xholon view). Catalogs come from xdoc_catalog(dim).
        """
        from tlsys.catalog import AtomIndex
        self._ensure_call()
        if self._xdoc is None:
            xdict = {hid: {"members": list(e["members"]),
                           "descriptor": list(e["descriptor"]),
                           "seq": e.get("seq")}
                     for hid, e in views.items()}
            self._call["view_rows"] += len(xdict)
            self._call["built_from_views"] = True
            atom_idx = AtomIndex().build(xdict) \
                if with_atom_index else None
            self._xdoc = {"xdict": xdict, "xcat": None,
                          "atom_idx": atom_idx, "dim": None,
                          "rcat": None, "synced": frontier,
                          "cat_frontier": None, "dirty": False}
            return xdict, atom_idx
        leg = self._xdoc
        if frontier > leg["synced"]:
            delta = sorted(
                (_seq_of(e), hid) for hid, e in views.items()
                if _seq_of(e) > leg["synced"]
                and _seq_of(e) <= frontier)
            for _seq, hid in delta:
                e = views[hid]
                old = leg["xdict"].get(hid)
                old_members = set(old["members"]) if old else set()
                leg["xdict"][hid] = {
                    "members": list(e["members"]),
                    "descriptor": list(e["descriptor"]),
                    "seq": e.get("seq")}
                fresh = set(e["members"]) - old_members
                if fresh and leg["atom_idx"] is not None:
                    leg["atom_idx"].add(hid, fresh)
                if leg["xcat"] is not None:
                    leg["xcat"].upsert(hid, e["descriptor"],
                                       len(e["members"]))
                self._call["advance_upserts"] += 1
            if delta:
                leg["dirty"] = True
            leg["synced"] = frontier
        if with_atom_index and leg["atom_idx"] is None:
            leg["atom_idx"] = AtomIndex().build(leg["xdict"])
            self._call["view_rows"] += len(leg["xdict"])
        return leg["xdict"], leg["atom_idx"]

    def xdoc_catalog(self, dim):
        """Committed-mirror xholon Catalog (restore, build, or warm)."""
        from tlsys.catalog import Catalog
        self._ensure_call()
        leg = self._xdoc
        if leg is None:
            raise SidecarError("xdoc_catalog before ensure_xdoc")
        rcat = self._live_rcat()
        if leg["xcat"] is not None:
            if leg["dim"] != dim or leg["rcat"] != rcat:
                raise SidecarConflictError(
                    "xdoc catalog dim/budget changed mid-session")
            return leg["xcat"]
        payload = self._snapshots.pop("xholon", None)
        if payload is not None and (payload["dim"] != dim
                                    or payload.get("rcat") != rcat):
            self._call["snapshot_dropped"].append("xholon")
            payload = None
        if payload is not None:
            cat = _catalog_from_payload("xholon", payload, rcat)
            snap_f = payload.get("frontier") or 0
            for _seq, hid in sorted(
                    (_seq_of(e), hid)
                    for hid, e in leg["xdict"].items()
                    if _seq_of(e) > snap_f):
                e = leg["xdict"][hid]
                cat.upsert(hid, e["descriptor"], len(e["members"]))
                self._call["advance_upserts"] += 1
            leg["xcat"] = cat
            leg["dim"], leg["rcat"] = dim, rcat
            leg["cat_frontier"] = leg["synced"]
            self._call["restored"].append("xholon")
            return cat
        cat = Catalog("xholon", dim, rcat)
        cat.build((hid, e["descriptor"], len(e["members"]))
                  for hid, e in leg["xdict"].items())
        self._call["rebuilt_rows"] += len(leg["xdict"])
        self._call["built_from_views"] = True
        leg["xcat"] = cat
        leg["dim"], leg["rcat"] = dim, rcat
        leg["cat_frontier"] = leg["synced"]
        leg["dirty"] = True
        return cat

    # -- hier leg ---------------------------------------------------------
    def ensure_hier(self, views, frontier):
        """(live_l, live_p, edge, memidx, ovc) advanced to frontier.

        views: {"leaves", "parents"} projection hierarchy view.
        Catalogs come from hier_catalogs(dim).
        """
        from tlsys.catalog import (LeafParentIndex, MemberIndex,
                                   OverflowCounters, TouchMap)
        self._ensure_call()
        leaves, parents = views["leaves"], views["parents"]
        if self._hier is None:
            live_l = TouchMap(
                {k: {"members": list(v["members"]),
                     "descriptor": list(v["descriptor"]),
                     "segments": list(v.get("segments", [])),
                     "seq": v.get("seq")}
                 for k, v in leaves.items()})
            live_p = TouchMap(
                {k: {"members": list(v["members"]),
                     "children": list(v.get("children", [])),
                     "descriptor": list(v["descriptor"]),
                     "seq": v.get("seq")}
                 for k, v in parents.items()})
            edge = LeafParentIndex().build(live_p)
            memidx = MemberIndex().build(live_p, live_l)
            ovc = OverflowCounters()
            ovc.seed(live_l)
            self._call["view_rows"] += len(live_l) + len(live_p)
            self._call["built_from_views"] = True
            self._hier = {"live_l": live_l, "live_p": live_p,
                          "edge": edge, "memidx": memidx, "ovc": ovc,
                          "leaf_cat": None, "parent_cat": None,
                          "dim": None, "rcat": None,
                          "synced": frontier, "dirty": False}
            return live_l, live_p, edge, memidx, ovc
        leg = self._hier
        if frontier > leg["synced"]:
            leaf_delta = sorted(
                (_seq_of(e), lid) for lid, e in leaves.items()
                if _seq_of(e) > leg["synced"]
                and _seq_of(e) <= frontier)
            parent_delta = sorted(
                (_seq_of(e), pid) for pid, e in parents.items()
                if _seq_of(e) > leg["synced"]
                and _seq_of(e) <= frontier)
            grown = {}
            for _seq, lid in leaf_delta:
                e = leaves[lid]
                old = leg["live_l"].get(lid)
                if old is None:
                    # New id: cached overflow bases advance (exact
                    # next_n propagation mirror); uncached stay lazy.
                    self._ovc_note_id(leg["ovc"], lid)
                else:
                    new_aids = set(e["members"]) - set(old["members"])
                    if new_aids:
                        grown[lid] = new_aids
                leg["live_l"][lid] = {
                    "members": list(e["members"]),
                    "descriptor": list(e["descriptor"]),
                    "segments": list(e.get("segments", [])),
                    "seq": e.get("seq")}
                if leg["leaf_cat"] is not None:
                    leg["leaf_cat"].upsert(lid, e["descriptor"],
                                           len(e["members"]))
                self._call["advance_upserts"] += 1
            for _seq, pid in parent_delta:
                e = parents[pid]
                old = leg["live_p"].get(pid)
                old_children = set(old["children"]) if old else set()
                leg["live_p"][pid] = {
                    "members": list(e["members"]),
                    "children": list(e.get("children", [])),
                    "descriptor": list(e["descriptor"]),
                    "seq": e.get("seq")}
                new_kids = set(e.get("children", ())) - old_children
                if old is None:
                    leg["memidx"].ensure(pid, e.get("members", ()))
                for lid in sorted(new_kids):
                    leg["edge"].add_edge(pid, lid)
                    leaf = leg["live_l"].get(lid)
                    if leaf is not None:
                        for aid in leaf.get("members", ()):
                            leg["memidx"].add(pid, aid)
                if leg["parent_cat"] is not None:
                    leg["parent_cat"].upsert(
                        pid, e["descriptor"], len(e.get("children",
                                                        ())))
                self._call["advance_upserts"] += 1
            for lid, aids in grown.items():
                for pid in leg["edge"].parents_of(lid):
                    for aid in aids:
                        leg["memidx"].add(pid, aid)
            if leaf_delta or parent_delta:
                leg["dirty"] = True
            leg["synced"] = frontier
        return (leg["live_l"], leg["live_p"], leg["edge"],
                leg["memidx"], leg["ovc"])

    @staticmethod
    def _ovc_note_id(ovc, lid):
        """Advance cached overflow bases for a committed new id."""
        counts = ovc._counts  # same-package committed-mint mirror
        i = lid.find("-ov")
        seen = set()
        while i != -1:
            base = lid[:i]
            if base in counts and base not in seen:
                counts[base] += 1
                seen.add(base)
            i = lid.find("-ov", i + 1)

    def hier_catalogs(self, dim):
        """(leaf_cat, parent_cat): restore, build, or warm mirrors."""
        from tlsys.catalog import Catalog
        self._ensure_call()
        leg = self._hier
        if leg is None:
            raise SidecarError("hier_catalogs before ensure_hier")
        rcat = self._live_rcat()
        if leg["leaf_cat"] is not None:
            if leg["dim"] != dim or leg["rcat"] != rcat:
                raise SidecarConflictError(
                    "hier catalog dim/budget changed mid-session")
            return leg["leaf_cat"], leg["parent_cat"]
        out = []
        for pop, live, count_of in (
                ("leaf", leg["live_l"], lambda e: len(e["members"])),
                ("parent", leg["live_p"],
                 lambda e: len(e.get("children", ())))):
            payload = self._snapshots.pop(pop, None)
            if payload is not None and (payload["dim"] != dim
                                        or payload.get("rcat") != rcat):
                self._call["snapshot_dropped"].append(pop)
                payload = None
            if payload is not None:
                cat = _catalog_from_payload(pop, payload, rcat)
                snap_f = payload.get("frontier") or 0
                for _seq, hid in sorted(
                        (_seq_of(e), hid) for hid, e in live.items()
                        if _seq_of(e) > snap_f):
                    e = live[hid]
                    cat.upsert(hid, e["descriptor"], count_of(e))
                    self._call["advance_upserts"] += 1
                self._call["restored"].append(pop)
            else:
                cat = Catalog(pop, dim, rcat)
                cat.build((hid, e["descriptor"], count_of(e))
                          for hid, e in live.items())
                self._call["rebuilt_rows"] += len(live)
                self._call["built_from_views"] = True
                leg["dirty"] = True
            out.append(cat)
        leg["leaf_cat"], leg["parent_cat"] = out
        leg["dim"], leg["rcat"] = dim, rcat
        return out[0], out[1]

    # -- call-end sync + persist --------------------------------------------
    def leg_sync(self, leg_name, views, touched_ids, frontier):
        """Refresh touched entries from post-commit views; move frontier.

        Same-call emissions land with seq None; the post-update views
        carry their committed seqs. touched_ids bounds the refresh.
        """
        leg = self._xdoc if leg_name == "xdoc" else self._hier
        if leg is None:
            return
        if leg_name == "xdoc":
            for hid in touched_ids:
                e = views.get(hid)
                if e is not None:
                    leg["xdict"][hid] = {
                        "members": list(e["members"]),
                        "descriptor": list(e["descriptor"]),
                        "seq": e.get("seq")}
        else:
            leaves, parents = views["leaves"], views["parents"]
            for hid in touched_ids:
                if hid in leaves:
                    e = leaves[hid]
                    leg["live_l"][hid] = {
                        "members": list(e["members"]),
                        "descriptor": list(e["descriptor"]),
                        "segments": list(e.get("segments", [])),
                        "seq": e.get("seq")}
                elif hid in parents:
                    e = parents[hid]
                    leg["live_p"][hid] = {
                        "members": list(e["members"]),
                        "children": list(e.get("children", [])),
                        "descriptor": list(e["descriptor"]),
                        "seq": e.get("seq")}
        leg["synced"] = frontier

    def note_dirty(self, leg_name):
        leg = self._xdoc if leg_name == "xdoc" else self._hier
        if leg is not None:
            leg["dirty"] = True

    def drop_leg(self, leg_name):
        """Forget one leg (failure-path resync; next use rebuilds)."""
        if leg_name == "xdoc":
            self._xdoc = None
        else:
            self._hier = None

    def persist(self, state):
        """Store restart-ready snapshots for engaged+dirty legs."""
        self._ensure_call()
        if _is_prebirth_incarnation(self._incarnation):
            # A minting call born the store mid-call: stamp the live
            # born incarnation now (monotonic, mirrors _set_frontier),
            # so later cross-store attaches refuse instead of
            # silently re-binding legs that mirror this store.
            live = incarnation_of(
                state._tlstore.pin())  # same-package store read
            if not _is_prebirth_incarnation(live):
                self._incarnation = live
        if self._xdoc is not None and self._xdoc["dirty"] \
                and self._xdoc["xcat"] is not None \
                and self._xdoc["xcat"].n:
            cat = self._xdoc["xcat"]
            state.store_routing(
                "xholon", cat.n, cat.dim, self._xdoc["rcat"],
                self._xdoc["synced"], list(cat.ids),
                cat._mat[:cat.n], cat._norms[:cat.n],
                cat._counts[:cat.n])
            self._call["persisted"].append("xholon")
            self._xdoc["dirty"] = False
        if self._hier is not None and self._hier["dirty"]:
            for pop, cat in (("leaf", self._hier["leaf_cat"]),
                             ("parent", self._hier["parent_cat"])):
                if cat is not None and cat.n:
                    state.store_routing(
                        pop, cat.n, cat.dim, self._hier["rcat"],
                        self._hier["synced"], list(cat.ids),
                        cat._mat[:cat.n], cat._norms[:cat.n],
                        cat._counts[:cat.n])
                    self._call["persisted"].append(pop)
            if self._call["persisted"]:
                self._hier["dirty"] = False


# ---------------------------------------------------------------------------
# P-2 (Sec 5.7): explicit-archive export, stale markers, keyed
# operational reads, and the recorded candidate version.
#
# Ordinary keyed calls (add/correct/retire/maintenance) NEVER
# materialize the legacy JSON manifest. The manifest is written only
# on explicit archive/compatibility requests; every ordinary call
# that advances progress past the last export writes the O(1)
# stale marker instead, so file-level readers cannot mistake the
# JSON for current state. Operational progress/eligibility reads go
# through the read-only keyed API below (no fence, no mutation).
# ---------------------------------------------------------------------------

def stale_marker_path(manifest_path):
    """The O(1) staleness sidecar beside a JSON manifest."""
    return manifest_path + MANIFEST_STALE_SUFFIX


def write_stale_marker(manifest_path, record):
    """Atomically write the stale marker (tmp + fsync + replace)."""
    target = stale_marker_path(manifest_path)
    tmp_path = target + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(record, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target)


def clear_stale_marker(manifest_path):
    """Remove the stale marker (missing-ok; OSError-safe)."""
    try:
        os.remove(stale_marker_path(manifest_path))
    except OSError:
        pass


def read_stale_marker(manifest_path):
    """The stale marker dict, or None when absent/unreadable."""
    try:
        with open(stale_marker_path(manifest_path)) as f:
            rec = json.load(f)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return rec if isinstance(rec, dict) else None


def close_out_keyed_call(state, manifest_path, archive_manifest=False,
                         reason="ordinary", export_kind="archive"):
    """End-of-keyed-call manifest boundary (explicit-archive rule).

    archive_manifest=True: materialize + atomically save the legacy
    JSON (an explicit compatibility/archive request), record the
    export in the sidecar, clear the stale marker. Returns (manifest,
    receipt). False (ordinary): NO materialization and NO save; when
    progress advanced past the last export, write the O(1) stale
    marker. Returns (None, receipt). A marker write failure is
    receipted (stale_marker_error), never raised: the commits
    already succeeded, and the seq-compare API still reports the
    currency honestly.
    """
    status = state.export_status()
    prog, exp = status["progress_seq"], status["exported_seq"]
    cand_v = state.meta("candidate_version")
    if archive_manifest:
        man = state.materialize_manifest()
        from tlsys.ingest import _save_manifest as _save
        _save(manifest_path, man)
        rec = state.record_export(export_kind, reason)
        clear_stale_marker(manifest_path)
        return man, {"exported": True,
                     "exported_seq": rec["exported_seq"],
                     "progress_seq": rec["progress_seq"],
                     "manifest_current": True, "kind": export_kind,
                     "reason": reason, "candidate_version": cand_v,
                     "stale_marker": False}
    receipt = {"exported": False, "exported_seq": exp,
               "progress_seq": prog, "kind": None,
               "reason": reason, "candidate_version": cand_v,
               "stale_marker_error": None}
    advanced = (exp is None and prog > 0) \
        or (exp is not None and prog > exp)
    if advanced:
        marker = {"stale": True,
                  "manifest": os.path.basename(manifest_path),
                  "exported_seq": exp, "progress_seq": prog,
                  "reason": "keyed-ordinary-skip",
                  "candidate_version": cand_v}
        try:
            write_stale_marker(manifest_path, marker)
        except OSError as e:
            receipt["stale_marker_error"] = (
                f"{type(e).__name__}: {e}")
        receipt["stale_marker"] = True
        receipt["manifest_current"] = False
    else:
        # No advance this call: current only when an export exactly
        # covers progress, no marker lingers, and the JSON exists.
        marked = os.path.isfile(stale_marker_path(manifest_path))
        have_json = os.path.isfile(manifest_path)
        receipt["stale_marker"] = marked
        receipt["manifest_current"] = (not marked) and have_json \
            and exp is not None and exp == prog
    return None, receipt


def export_manifest_archive(tlstore, reason="explicit-archive",
                            export_kind="archive"):
    """Explicit once-per-boundary JSON compatibility snapshot (counted).

    Adopts the crash window first (bounded suffix), then
    materializes + saves + records the export. Fails closed
    (SidecarMissingError) on stores without keyed state: legacy
    stores already own their manifest. Returns the counted receipt.
    """
    from tlsys.ingest import MANIFEST_NAME as _MAN
    state = ProducerState.open(tlstore)
    try:
        sufrec = consume_suffix(tlstore, state)
        mpath = os.path.join(tlstore.store.root, _MAN)
        man, receipt = close_out_keyed_call(
            state, mpath, archive_manifest=True, reason=reason,
            export_kind=export_kind)
        try:
            mbytes = os.path.getsize(mpath)
        except OSError:
            mbytes = 0
        receipt["suffix"] = sufrec
        receipt["docs"] = sum(1 for k in man
                              if not k.startswith("_"))
        receipt["manifest_bytes"] = mbytes
        receipt["manifest"] = os.path.basename(mpath)
        return receipt
    finally:
        state.close()


def bind_candidate_store(tlstore, profile=None, profile_id=None,
                         profile_sha256=None, compact_bounds=None,
                         archive_policy=ARCHIVE_POLICY_EXPLICIT):
    """Record the candidate version binding (before confirmation use).

    Opens (or creates+migrates) the sidecar, then records the
    immutable binding (see ProducerState.bind_candidate). Returns
    {"binding", "existing", "migrated"}.
    """
    from tlsys.ingest import MANIFEST_NAME as _MAN
    manifest = {}
    mpath = os.path.join(tlstore.store.root, _MAN)
    if os.path.isfile(mpath):
        with open(mpath) as f:
            manifest = json.load(f)
    state, migrec = ProducerState.create_or_migrate(tlstore, manifest)
    try:
        out = state.bind_candidate(
            profile=profile, profile_id=profile_id,
            profile_sha256=profile_sha256,
            compact_bounds=compact_bounds,
            archive_policy=archive_policy)
    finally:
        state.close()
    out["migrated"] = migrec
    return out


# -- read-only keyed operational reads (Q seam; no fence) -----------

def _ro_open(store_root):
    """Read-only sidecar handle (mode=ro; never mutates or locks).

    Format/scheme validated; the generation check is skipped (no
    live pin on the read path -- writable opens still enforce it).
    """
    import sqlite3 as _sqlite3
    from urllib.parse import quote as _quote
    path = os.path.join(store_root, SIDECAR_NAME)
    if not os.path.isfile(path):
        raise SidecarMissingError(
            f"producer sidecar {path!r} absent (no keyed state to "
            "read; named recovery: reconcile_manifest(..., "
            "keyed_state=True) rebuilds it from committed truth)")
    try:
        con = _sqlite3.connect("file:%s?mode=ro" % _quote(path),
                               uri=True, timeout=2.0)
    except _sqlite3.Error as e:
        raise SidecarCorruptError(
            f"producer sidecar {path!r} unreadable: {e}") from e
    obj = ProducerState(None, con)
    try:
        fmt = obj.meta("format")
        scheme = obj.meta("scheme")
    except SidecarError:
        con.close()
        raise
    if fmt != str(SIDECAR_FORMAT) or scheme != ATOM_SCHEME:
        con.close()
        raise SidecarCorruptError(
            f"producer sidecar {path!r}: foreign format "
            f"(format={fmt!r} scheme={scheme!r}; want "
            f"{SIDECAR_FORMAT}/{ATOM_SCHEME})")
    return obj


def read_progress(store_root):
    """Operational progress snapshot (keyed; replaces manifest scans)."""
    st = _ro_open(store_root)
    try:
        return {"backend": KEYED_BACKEND_ID,
                "format": SIDECAR_FORMAT, "scheme": ATOM_SCHEME,
                "progress_seq": int(st.meta("progress_seq") or "0"),
                "counters": st.counters(),
                "frontier": st.frontier(),
                "pending_count": st.pending_count(),
                "pending_sample": st.pending_sample(),
                "unorganized_count": st.unorganized_count(),
                "export": st.export_status(),
                "candidate": st.candidate_record()}
    finally:
        st.close()


def read_doc(store_root, doc_id):
    """One keyed doc entry (get_doc shape), or None when undeclared."""
    st = _ro_open(store_root)
    try:
        return st.get_doc(doc_id)
    finally:
        st.close()


def read_eligibility(store_root, doc_id):
    """Per-doc eligibility bits (acknowledged/pending/organized/retired)."""
    st = _ro_open(store_root)
    try:
        e = st.get_doc(doc_id)
        if e is None:
            return {"acknowledged": False, "status": None,
                    "pending": False, "organized": False,
                    "retired": False}
        return {"acknowledged": True, "status": e["status"],
                "pending": st.is_pending(doc_id),
                "organized": st.is_organized(doc_id),
                "retired": st.is_retired(doc_id)}
    finally:
        st.close()


def read_candidate(store_root):
    """The recorded candidate binding, or None when unbound/absent."""
    if not os.path.isfile(os.path.join(store_root, SIDECAR_NAME)):
        return None
    st = _ro_open(store_root)
    try:
        return st.candidate_record()
    finally:
        st.close()


_MANIFEST_SEQ_RE = re.compile(rb'"_sidecar_seq"\s*:\s*(\d+)')


def _scan_manifest_seq(manifest_path):
    """Bounded _sidecar_seq scan (1MB chunks; never a full parse)."""
    try:
        f = open(manifest_path, "rb")
    except OSError:
        return None
    with f:
        tail = b""
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                return None
            m = _MANIFEST_SEQ_RE.search(tail + chunk)
            if m:
                return int(m.group(1))
            tail = (tail + chunk)[-32:]


def manifest_currency(store_root):
    """JSON-vs-sidecar currency verdict (bounded; no full parse).

    current means the on-disk JSON reflects adopted keyed progress
    (no stale marker and _sidecar_seq == progress_seq). Stores
    without keyed state report current whenever no stale marker
    lingers (legacy/empty: the JSON is the truth).
    """
    from tlsys.ingest import MANIFEST_NAME as _MAN
    mpath = os.path.join(store_root, _MAN)
    present = os.path.isfile(mpath)
    try:
        mbytes = os.path.getsize(mpath) if present else 0
    except OSError:
        mbytes = 0
    marker = os.path.isfile(stale_marker_path(mpath))
    if not os.path.isfile(os.path.join(store_root, SIDECAR_NAME)):
        return {"backend": None, "manifest_present": present,
                "manifest_bytes": mbytes,
                "manifest_seq": _scan_manifest_seq(mpath)
                if present else None,
                "progress_seq": None, "stale_marker": marker,
                "current": not marker}
    st = _ro_open(store_root)
    try:
        prog = int(st.meta("progress_seq") or "0")
    finally:
        st.close()
    mseq = _scan_manifest_seq(mpath) if present else None
    return {"backend": KEYED_BACKEND_ID,
            "manifest_present": present, "manifest_bytes": mbytes,
            "manifest_seq": mseq, "progress_seq": prog,
            "stale_marker": marker,
            "current": (not marker) and present and mseq == prog}


def require_candidate(store_root, version=None, pin=None):
    """Pre-open candidate gate for qualification entry points (Q seam).

    Returns the binding record. Unbound -> CandidateMissingError;
    version/generation mismatch -> CandidateMismatchError. The
    generation is enforced only when the binding pinned one (a
    pre-commit bind records an unborn generation, which cannot pin).
    """
    rec = read_candidate(store_root)
    if rec is None:
        raise CandidateMissingError(
            f"store {store_root!r} carries no recorded candidate "
            "binding (bind_candidate_store(...) before confirmation "
            "use); refusing")
    want = CANDIDATE_VERSION if version is None else version
    if rec.get("version") != want:
        raise CandidateMismatchError(
            f"store {store_root!r} candidate version "
            f"{rec.get('version')!r} != {want!r}; refusing")
    gen = rec.get("generation")
    if pin is not None and gen not in (None, [None, None]):
        if str(gen[0]) != str(pin[0]) \
                or str(gen[1]) != str(pin[1]):
            raise CandidateMismatchError(
                f"store {store_root!r} candidate generation "
                f"({gen[0]}:{gen[1]}) != live pin "
                f"({pin[0]}:{pin[1]}); refusing")
    return rec


def read_checkpoint_debt(store_root):
    """Projection checkpoint debt for work accounting (stat-bounded)."""
    from tlsys.proj import Projections as _P

    class _Store:
        def __init__(self, root):
            self.root = root

    class _TL:
        def __init__(self, root):
            self.store = _Store(root)

    tl = _TL(store_root)
    debt = _P.journal_debt(tl)
    debt["checkpoint_bytes"] = _P.checkpoint_bytes(tl)
    return debt
