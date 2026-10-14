"""Flag-gated durable acknowledged-ingest -> single-writer organization service.

Existing ingest/organize functions are unmodified. enabled=False delegates
ingest exactly and creates no queue/publisher/worker. Consumers opt in via
OrganizationService(tlstore, config=ServiceConfig(enabled=True)).
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Mapping, Protocol


class RepairHook(Protocol):
    """Called only by the serialized writer; source evidence remains versioned.

    Hook owns its own durable touched-work queue and must be replay-idempotent.
    budget is a maximum repair unit count. A failure must propagate; publication
    validates the resulting hierarchy before making it visible to readers.
    """
    def repair_step(self, budget: int) -> Mapping: ...


class NoRepair:
    def repair_step(self, budget: int) -> Mapping:
        return {"processed": 0, "remaining": 0, "hook": "stub-no-repair"}


@dataclass(frozen=True)
class ServiceConfig:
    enabled: bool = False
    max_documents_per_drain: int = 8
    drain_budget_seconds: float = 1.0
    repair_units_per_drain: int = 0
    poll_seconds: float = 0.1
    await_visibility_on_ack: bool = False
    batched_drain: bool = False
    reuse_view_pool: bool = False

    def __post_init__(self):
        if self.max_documents_per_drain < 0 or self.drain_budget_seconds < 0 \
                or self.repair_units_per_drain < 0 or self.poll_seconds <= 0:
            raise ValueError("invalid service budget")


class OrganizationService:
    def __init__(self, tlstore, *, config=ServiceConfig(), directory=None,
                 profile=None, keyed_state=False, session=None,
                 repair: RepairHook | None = None, fault=None, publisher_factory=None,
                 organize_kwargs=None):
        self.tlstore, self.config = tlstore, config
        self.profile, self.keyed_state, self.session = profile, keyed_state, session
        self.repair, self.fault = repair or NoRepair(), fault
        self.organize_kwargs = dict(organize_kwargs or {})
        self.directory = Path(directory or (Path(tlstore.store.root) / "organization-service"))
        self.publisher = None
        self.last_future = None
        self.last_error = None
        self.last_ack_visible_s = None
        self._thread = None
        self._stop = threading.Event()
        self._mutex = threading.Lock()
        self._lockfile = None
        self._projections = None
        if config.enabled:
            from tlsys.org_publication import GenerationPublisher
            self.directory.mkdir(parents=True, exist_ok=True)
            self._lockfile = open(self.directory / "writer.lock", "a+b")
            try:
                with self._writer():
                    with self._db() as con:
                        con.execute("CREATE TABLE IF NOT EXISTS jobs (doc_id TEXT PRIMARY KEY, "
                                    "source_sha256 TEXT NOT NULL, revision_id TEXT, "
                                    "state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
                                    "last_error TEXT, acknowledged_seq INTEGER)")
                        con.execute("CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state)")
                    if publisher_factory is not None:
                        # Preserve custom two-argument publisher factory calls.
                        self.publisher = publisher_factory(tlstore, self.directory / "generations")
                    else:
                        self.publisher = GenerationPublisher(
                            tlstore, self.directory / "generations",
                            reuse_view_pool=config.reuse_view_pool)
                    restoring = self.publisher.restore()
                    if restoring is not None:
                        restoring.result()
                    self._recover_waiting()
            except BaseException:
                if self.publisher:
                    self.publisher.close()
                self._lockfile.close()
                raise

    @contextmanager
    def _db(self):
        con = sqlite3.connect(self.directory / "backlog.sqlite3", timeout=30)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        try:
            with con:
                yield con
        finally:
            con.close()

    @contextmanager
    def _writer(self):
        with self._mutex:
            try:
                fcntl.flock(self._lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise RuntimeError("organization writer already active") from e
            try:
                yield
            finally:
                fcntl.flock(self._lockfile, fcntl.LOCK_UN)

    def _inject(self, stage):
        if self.fault:
            self.fault(stage)

    def _doc_state(self, doc):
        from tlsys.ingest import (_load_manifest, _derive_status, P_SOURCE_DURABLE)
        if self.keyed_state:
            from tlsys.prodstate import read_doc, read_eligibility
            entry = read_doc(self.tlstore.store.root, doc)
            eligibility = read_eligibility(self.tlstore.store.root, doc)
            durable = entry is not None and eligibility["status"] in P_SOURCE_DURABLE
            return entry, durable, eligibility["organized"], eligibility["retired"]
        manifest, _ = _load_manifest(self.tlstore.store)
        entry = manifest.get(doc)
        durable = isinstance(entry, dict) and _derive_status(
            entry, doc in manifest.get("_pending_placement", [])) in P_SOURCE_DURABLE
        return entry, durable, doc in manifest.get("_seg_organized", []), \
            doc in manifest.get("_retired", [])

    def _recover_waiting(self):
        with self._db() as con:
            rows = con.execute("SELECT doc_id,source_sha256 FROM jobs WHERE state='waiting'").fetchall()
        for doc, sha in rows:
            entry, durable, organized, retired = self._doc_state(doc)
            if durable and entry.get("source_sha256") == sha:
                with self._db() as con:
                    con.execute("UPDATE jobs SET state=?,revision_id=?,acknowledged_seq=? WHERE doc_id=?",
                                ("done" if organized or retired else "pending", entry["revision_id"],
                                 self.tlstore.pin()[2], doc))

    def _recover_waiting_bulk(self):
        """Bulk queue adoption: one SELECT + one UPDATE transaction.

        Same end states as _recover_waiting (same rows, same values;
        single pin read under the held writer lock, so acknowledged_seq
        is identical). Crash all-or-none: either every eligible waiting
        job is adopted or none is; durable source is never lost because
        adoption only promotes jobs with source-complete revision
        evidence and ingest already committed the source.
        """
        with self._db() as con:
            rows = con.execute("SELECT doc_id,source_sha256 FROM jobs WHERE state='waiting'").fetchall()
            if not rows:
                return
            pin_seq = self.tlstore.pin()[2]
            updates = []
            for doc, sha in rows:
                entry, durable, organized, retired = self._doc_state(doc)
                if durable and entry.get("source_sha256") == sha:
                    updates.append(("done" if organized or retired else "pending",
                                    entry["revision_id"], pin_seq, doc))
            con.executemany("UPDATE jobs SET state=?,revision_id=?,acknowledged_seq=? WHERE doc_id=?",
                            updates)

    def _adopt_waiting(self):
        # Flag-gated bulk adoption; flag-off delegates exactly.
        if self.config.batched_drain:
            self._recover_waiting_bulk()
        else:
            self._recover_waiting()

    def _ingest_locked(self, docs, embed_texts, kwargs):
        """Caller holds the single-writer lock; returns this call's future."""
        from tlsys.ingest import ingest_docs
        docs = list(docs)
        supplied = dict(profile=self.profile, keyed_state=self.keyed_state, session=self.session)
        supplied.update(kwargs)
        if supplied["keyed_state"] != self.keyed_state or supplied["profile"] != self.profile \
                or supplied["session"] is not self.session:
            raise ValueError("service producer configuration must remain fixed")
        # Durable intent closes commit -> enqueue crash window. Waiting jobs
        # are promoted only with source-complete revision evidence.
        with self._db() as con:
            for doc, text in docs:
                sha = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
                row = con.execute("SELECT source_sha256 FROM jobs WHERE doc_id=?", (doc,)).fetchone()
                if row and row[0] != sha:
                    raise ValueError("changed source for queued document " + doc)
                con.execute("INSERT OR IGNORE INTO jobs(doc_id,source_sha256,state) VALUES (?,?,'waiting')",
                            (doc, sha))
        result = ingest_docs(self.tlstore, docs, embed_texts, **supplied)
        source_commit_mark = time.perf_counter()
        self._inject("after_ingest_before_enqueue")
        self._adopt_waiting()
        # The acknowledgment is returned only after durable queue adoption.
        self._inject("after_enqueue")
        future = self.publisher.submit(self.tlstore.pin(), self.pending())
        self.last_future = future
        return result, future, source_commit_mark

    def ingest(self, docs, embed_texts, **kwargs):
        from tlsys.ingest import ingest_docs
        if not self.config.enabled:
            return ingest_docs(self.tlstore, docs, embed_texts, **kwargs)
        with self._writer():
            result, _, _ = self._ingest_locked(docs, embed_texts, kwargs)
        return result

    def ingest_visible(self, docs, embed_texts, **kwargs):
        """Opt-in ACK after this call's prepared frontier; failures propagate.

        Captures the future under the source writer lock, waits outside it.
        Source commit -> ACK excludes source ingestion; total time is separate.
        Disabled service delegates exactly to the legacy ingest API.
        """
        from tlsys.ingest import ingest_docs
        if not self.config.enabled:
            return ingest_docs(self.tlstore, docs, embed_texts, **kwargs)
        if not self.config.await_visibility_on_ack:
            raise RuntimeError("ingest_visible requires await_visibility_on_ack=True")
        started = time.perf_counter()
        with self._writer():
            result, future, source_commit_mark = self._ingest_locked(docs, embed_texts, kwargs)
        try:
            record = future.result()
        except BaseException as exc:
            raise RuntimeError("ingest preparation failed; not acknowledged") from exc
        acknowledged = time.perf_counter()
        self.last_ack_visible_s = acknowledged - source_commit_mark
        return {"ack": result, "generation": record,
                "source_commit_to_ack_s": acknowledged - source_commit_mark,
                "total_ingest_to_ack_s": acknowledged - started}

    def pending(self, limit=None):
        if not self.config.enabled:
            return ()
        with self._db() as con:
            query = "SELECT doc_id FROM jobs WHERE state='pending' ORDER BY rowid"
            args = ()
            if limit is not None:
                if int(limit) < 0:
                    raise ValueError("negative pending window")
                query += " LIMIT ?"
                args = (int(limit),)
            return tuple(r[0] for r in con.execute(query, args))

    def backlog(self):
        if not self.config.enabled:
            return []
        with self._db() as con:
            return [dict(zip(("doc_id", "state", "attempts", "last_error"), r))
                    for r in con.execute("SELECT doc_id,state,attempts,last_error FROM jobs ORDER BY rowid")]

    def publish(self):
        if not self.config.enabled:
            raise RuntimeError("organization service disabled")
        with self._writer():
            self.last_future = self.publisher.submit(self.tlstore.pin(), self.pending())
        return self.last_future

    def detach_readers(self):
        """Stop service work, freeze publication, return a read-only publisher.

        Old reader pins and new requests on the returned publisher remain
        supported while a replacement writer restores the same durable queue
        and published frontier. Caller eventually closes the detached publisher.
        """
        if not self.config.enabled or self.publisher is None:
            raise RuntimeError("no active publisher")
        self._stop.set()
        if self._thread:
            self._thread.join()
            self._thread = None
        with self._writer():
            publisher = self.publisher
            publisher.freeze_for_reads()
            self.publisher = None
        return publisher

    def _drain_budgets(self, max_documents=None, budget_seconds=None, repair_budget=None):
        n = self.config.max_documents_per_drain if max_documents is None else int(max_documents)
        seconds = self.config.drain_budget_seconds if budget_seconds is None else float(budget_seconds)
        rb = self.config.repair_units_per_drain if repair_budget is None else int(repair_budget)
        if n < 0 or seconds < 0 or rb < 0:
            raise ValueError("negative drain budget")
        return n, seconds, rb

    def _drain_locked(self, n, seconds, rb, started):
        """Caller holds _writer(); returns (report, this-call future)."""
        from tlsys.maint import organize_segments
        attempted, completed, failed = [], [], {}
        self._recover_waiting()
        for doc in self.pending(limit=n):
            if time.monotonic() - started >= seconds:
                break
            attempted.append(doc)
            with self._db() as con:
                con.execute("UPDATE jobs SET attempts=attempts+1 WHERE doc_id=?", (doc,))
            self._inject("before_organize")
            _, durable, organized, retired = self._doc_state(doc)
            if not durable:
                raise RuntimeError("pending document lost durable source evidence")
            report = {"failed": {}}
            if not organized and not retired:
                kwargs = dict(self.organize_kwargs)
                if "projections" not in kwargs:
                    from tlsys.proj import Projections
                    if self._projections is None:
                        self._projections = Projections.cached(self.tlstore)
                    kwargs["projections"] = self._projections
                report = organize_segments(self.tlstore, doc_ids=[doc], budget=1,
                                           profile=self.profile, keyed_state=self.keyed_state,
                                           session=self.session, **kwargs)
            # Kill here tests source commit success -> service ack loss.
            self._inject("after_organize_before_ack")
            _, _, organized, retired = self._doc_state(doc)
            error = report.get("failed", {}).get(doc)
            if not (organized or retired):
                error = error or "organizer did not complete document"
                failed[doc] = str(error)
            else:
                completed.append(doc)
            with self._db() as con:
                con.execute("UPDATE jobs SET state=?,last_error=? WHERE doc_id=?",
                            ("done" if organized or retired else "pending", error, doc))
        repair_raw = self.repair.repair_step(rb) if rb and time.monotonic() - started < seconds \
            else {"processed": 0, "budget": rb}
        repair_result = dict(repair_raw)
        repair_result.setdefault("processed", 0)
        repair_result.setdefault("budget", rb)
        repair_result.setdefault("remaining", 0)
        # Supported caller-owned projection: warm reuse per document, one
        # durable checkpoint at the drain boundary. Restart consumes source
        # suffix from committed evidence if killed before this save.
        if self._projections is not None:
            self._projections.update(self.tlstore)
            self._projections.save(self.tlstore)
        self._inject("after_drain_before_publish")
        future = self.publisher.submit(self.tlstore.pin(), self.pending())
        return {"enabled": True, "attempted": len(attempted), "completed": completed,
                "failed": failed, "remaining": len(self.pending()), "repair": repair_result,
                "wall_s": time.monotonic() - started, "budget_seconds": seconds,
                "budget_kind": "cooperative-between-documents"}, future

    def _drain_locked_batched(self, n, seconds, rb, started):
        """Batched drain (flag-gated; flag-off uses _drain_locked).

        One queue-adoption transaction, ONE organize_segments call
        across the admitted batch (amortizing the per-call keyed
        live-hierarchy setup), per-doc attempts/done transactions
        before publisher ACK. A per-doc doc_checkpoint callback
        brackets EACH actual run_doc inside maint, alternating
        before/after in doc order: before checks the cooperative
        wall budget (False stops before starting the next doc),
        persists this doc's attempt, and fires before_organize;
        after fires after_organize_before_ack immediately on
        run_doc return, then classifies and persists this doc's
        done/error state (with the exact failed.get(doc) cause).
        Unstarted docs stay pending untouched: no attempts, no
        failure entries. A callback fault propagates with
        committed source retained pending for restart (restart
        re-runs organize commit-free). Keyed mode only: the
        legacy path has no per-doc callback and fails closed.
        """
        from tlsys.maint import organize_segments
        if not self.keyed_state:
            raise RuntimeError("batched_drain requires keyed_state=True "
                               "(legacy path has no per-doc callback)")
        self._adopt_waiting()
        batch = list(self.pending(limit=n))
        completed, failed, started_docs = [], {}, []

        def _checkpoint(stage, doc_id, error=None):
            if stage == "before":
                # Cooperative wall budget, like the legacy per-doc
                # loop head: stop before starting the next doc.
                if time.monotonic() - started >= seconds:
                    return False
                with self._db() as con:
                    con.execute("UPDATE jobs SET attempts=attempts+1 WHERE doc_id=?",
                                (doc_id,))
                started_docs.append(doc_id)
                self._inject("before_organize")
                _, durable, _, _ = self._doc_state(doc_id)
                if not durable:
                    raise RuntimeError("pending document lost durable source evidence")
                return True
            # After run_doc returned (outside its exception
            # handler): fault first, then classify + persist this
            # doc, so a kill here leaves committed source pending
            # for a commit-free restart.
            self._inject("after_organize_before_ack")
            _, _, organized, retired = self._doc_state(doc_id)
            err = error
            if not (organized or retired):
                err = err or "organizer did not complete document"
                failed[doc_id] = str(err)
            else:
                completed.append(doc_id)
                err = None
            with self._db() as con:
                con.execute("UPDATE jobs SET state=?,last_error=? WHERE doc_id=?",
                            ("done" if organized or retired else "pending",
                             err, doc_id))
            return True

        report = {"failed": {}}
        if batch:
            kwargs = dict(self.organize_kwargs)
            if "projections" not in kwargs:
                from tlsys.proj import Projections
                if self._projections is None:
                    self._projections = Projections.cached(self.tlstore)
                kwargs["projections"] = self._projections
            report = organize_segments(self.tlstore, doc_ids=batch,
                                       profile=self.profile, keyed_state=self.keyed_state,
                                       session=self.session,
                                       doc_checkpoint=_checkpoint, **kwargs)
        repair_raw = self.repair.repair_step(rb) if rb and time.monotonic() - started < seconds \
            else {"processed": 0, "budget": rb}
        repair_result = dict(repair_raw)
        repair_result.setdefault("processed", 0)
        repair_result.setdefault("budget", rb)
        repair_result.setdefault("remaining", 0)
        if self._projections is not None:
            self._projections.update(self.tlstore)
            self._projections.save(self.tlstore)
        self._inject("after_drain_before_publish")
        future = self.publisher.submit(self.tlstore.pin(), self.pending())
        return {"enabled": True, "attempted": len(started_docs), "completed": completed,
                "failed": failed, "remaining": len(self.pending()), "repair": repair_result,
                "wall_s": time.monotonic() - started, "budget_seconds": seconds,
                "budget_kind": "cooperative-between-documents",
                "batched": True}, future

    def drain(self, *, max_documents=None, budget_seconds=None, repair_budget=None):
        if not self.config.enabled:
            return {"enabled": False, "attempted": 0}
        n, seconds, rb = self._drain_budgets(max_documents, budget_seconds, repair_budget)
        started = time.monotonic()
        with self._writer():
            if self.config.batched_drain:
                report, future = self._drain_locked_batched(n, seconds, rb, started)
            else:
                report, future = self._drain_locked(n, seconds, rb, started)
            self.last_future = future
        return report

    def start(self):
        """Opt-in non-daemon lifecycle owned by caller; errors stop the writer."""
        if not self.config.enabled:
            return
        def run():
            try:
                while not self._stop.wait(self.config.poll_seconds):
                    if self.pending() or self.config.repair_units_per_drain:
                        n, seconds, rb = self._drain_budgets()
                        started = time.monotonic()
                        with self._writer():
                            if self.config.batched_drain:
                                _report, own = self._drain_locked_batched(n, seconds, rb, started)
                            else:
                                _report, own = self._drain_locked(n, seconds, rb, started)
                            self.last_future = own
                        own.result()
            except BaseException as exc:
                self.last_error = exc
                self._stop.set()
        with self._mutex:
            thread = self._thread
            if thread is not None:
                if thread.is_alive():
                    raise RuntimeError("service already started")
                thread.join()
                self._thread = None
            self._stop.clear()
            self.last_error = None
            self._thread = threading.Thread(target=run, name="org-drain", daemon=False)
            self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join()
            self._thread = None
        if self.publisher:
            self.publisher.close()
            self.publisher = None
        if self._lockfile:
            self._lockfile.close()
            self._lockfile = None
