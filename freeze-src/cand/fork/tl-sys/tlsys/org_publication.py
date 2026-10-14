"""Opt-in organization frontier publication over fixed, independently owned facades.

No change to NarrowIndex/ViewPool lock semantics: by default a worker constructs
a NEW pool for each frontier; reuse_view_pool explicitly shares the existing
pin-safe pool across independent fixed facades. A request owns a pin for its entire query. Durable
publication and retirement cleanup never run under the request handoff lock.
Records and old committed source evidence are retained on disk; no GC/deletes.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import heapq
import fcntl
import json
import os
from pathlib import Path
import threading
import time
from typing import Callable
from types import MappingProxyType
import uuid

import numpy as np


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def readonly(value):
    """Freeze exposed hierarchy snapshots; raw legacy facade stays private."""
    if isinstance(value, dict):
        return MappingProxyType({k: readonly(v) for k, v in value.items()})
    if isinstance(value, (list, tuple, np.ndarray)):
        return tuple(readonly(v) for v in value)
    return value


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_new(path, body):
    with open(path, "xb") as out:
        out.write(body)
        out.flush()
        os.fsync(out.fileno())
    fsync_dir(Path(path).parent)


@dataclass(frozen=True)
class MembershipRevision:
    holon_id: str
    commit_seq: int
    membership_sha256: str


@dataclass(frozen=True)
class OrganizationGeneration:
    generation_id: str
    parent_generation: str | None
    pin: tuple
    membership_revisions: tuple[MembershipRevision, ...]
    pending_documents: tuple[str, ...]
    format: str = "tl-org-generation-v1"

    @classmethod
    def decode(cls, body):
        value = json.loads(body)
        if value.pop("format") != "tl-org-generation-v1":
            raise RuntimeError("unknown organization generation format")
        value["pin"] = tuple(value["pin"])
        value["pending_documents"] = tuple(value["pending_documents"])
        value["membership_revisions"] = tuple(
            MembershipRevision(**r) for r in value["membership_revisions"])
        return cls(**value)


def pending_order(scores, aids, k, fast=False):
    """Exact pending top-k; nonfinite/all-k retain legacy full-sort ordering.

    Every score is still computed. Expand the exact cutoff ties before
    ordering by (-score, actual atom ID); candidate indices stay ascending
    so even duplicate-key stability matches the old literal full sort.
    The fast path additionally bounds cutoff-tie expansion to exactly the
    still-needed slots (heapq.nsmallest on atom ID), so the final sort
    sees exactly k indices even when all N scores tie.
    """
    n = len(scores)
    if not k:
        return []
    if not fast or k == n or not np.isfinite(scores).all():
        return sorted(range(n), key=lambda i: (-scores[i], aids[i]))[:k]
    cutoff = np.partition(scores, n - k)[n - k]
    above = np.flatnonzero(scores > cutoff).tolist()
    need = k - len(above)
    tied = np.flatnonzero(scores == cutoff).tolist()
    if 0 < need < len(tied):
        tied = heapq.nsmallest(need, tied, key=lambda i: aids[i])
    return sorted(above + tied, key=lambda i: (-scores[i], aids[i]))[:k]


class PreparedFacade:
    """Fixed supported facade; advances are intentionally absent from this API.

    Population work and hierarchy validation happen during preparation. Guided
    queries compose HierQuery; pending_search explicitly searches acknowledged
    source atoms whose hierarchy work has not completed at this generation.
    Each query gets its own HierQuery counters/caches. The legacy facade is
    private and never advanced or exposed for mutation by the service API.
    """
    def __init__(self, tlstore, pin, pending_documents, serving_dir=None, *, view_pool=None, fast_pending_topk=True):
        from tlsys.index import NarrowIndex
        self._tl = tlstore
        self._closed = False
        self._fast_pending_topk = bool(fast_pending_topk)
        self._index = NarrowIndex(tlstore, pin, use_reference=False,
                                  serving_dir=serving_dir, view_pool=view_pool)
        try:
            self.leaves = self._index.seg_leaves
            self.parents = self._index.seg_parents
            atoms = self._index.atoms
            for lid, leaf in self.leaves.items():
                if len(set(leaf["members"])) != len(leaf["members"]):
                    raise RuntimeError("duplicate leaf members: " + lid)
                if any(a not in atoms for a in leaf["members"]):
                    raise RuntimeError("missing leaf atom: " + lid)
            for pid, parent in self.parents.items():
                children = parent.get("children", [])
                if len(set(children)) != len(children):
                    raise RuntimeError("duplicate parent children: " + pid)
                if any(c not in self.leaves for c in children):
                    raise RuntimeError("incomplete parent children: " + pid)
                union = {a for c in children for a in self.leaves[c]["members"]}
                if union != set(parent["members"]):
                    raise RuntimeError("incomplete parent member union: " + pid)
            revisions = []
            for hid, h in sorted({**self.leaves, **self.parents}.items()):
                seq = int(h["seq"])
                if not 0 < seq <= pin[2]:
                    raise RuntimeError("membership outside pinned frontier")
                digest = hashlib.sha256(canonical({
                    "members": h["members"], "children": h.get("children", []),
                    "descriptor": [float(x) for x in h["descriptor"]]})).hexdigest()
                revisions.append(MembershipRevision(hid, seq, digest))
            self.membership_revisions = tuple(revisions)
            self.leaves, self.parents = readonly(self.leaves), readonly(self.parents)
            pending = set(pending_documents)
            self._pending_ids = tuple(a for a in atoms
                                      if atoms[a]["doc_id"] in pending)
            dim = len(atoms[next(iter(atoms))]["descriptor"]) if atoms else 0
            self._pending_mat = np.asarray(
                [atoms[a]["descriptor"] for a in self._pending_ids],
                dtype=np.float64).reshape(len(self._pending_ids), dim)
            self._pending_norm = np.linalg.norm(self._pending_mat, axis=1)
            self._pending_norm[self._pending_norm == 0] = 1
            self._pending_mat.setflags(write=False)
            self._pending_norm.setflags(write=False)
            # Warm dense assembly under this independently owned pool lock.
            self._index.dense_served_pop("atoms")
            self.atom_count = len(atoms)
            self.triple = pin[3]
        except BaseException:
            self.close()
            raise

    def guided(self, query, qvec, **kwargs):
        if self._closed:
            raise RuntimeError("prepared facade released")
        from tlsys.query import HierQuery
        return HierQuery(self._tl, self._index, lambda _: qvec).guided(query, **kwargs)

    def search(self, query, qvec, k=10, **kwargs):
        """Supported merged query at one generation/source pin.

        Runs guided over committed hierarchy plus pending_search over
        acknowledged-but-unprepared atoms, deduplicating actual atom IDs
        (guided wins ties). Whole query serves a single generation/pin;
        pass k through to cap total rows (query k clamp).
        """
        if self._closed:
            raise RuntimeError("prepared facade released")
        k = max(0, int(k))
        kwargs.setdefault("top_atoms", k)
        grows, greport = self.guided(query, qvec, **kwargs)
        prows, preport = self.pending_search(qvec, k=k)
        by_id = {}
        for row in list(grows) + list(prows):
            prior = by_id.get(row["aid"])
            if prior is None or float(row["score"]) > float(prior["score"]):
                by_id[row["aid"]] = row
        merged = sorted(by_id.values(), key=lambda row: (-float(row["score"]), row["aid"]))[:k] if k else []
        return merged, {"guided": greport, "pending": preport,
                        "merged_rows": len(merged),
                        "generation": self.triple}

    def pending_search(self, qvec, k=10):
        """Exact dense pending fallback; stable ID ordering across score ties."""
        if self._closed:
            raise RuntimeError("prepared facade released")
        k = min(max(0, int(k)), len(self._pending_ids))
        if not k:
            return [], {"pending_atoms_scored": 0}
        q = np.asarray(qvec, dtype=np.float64)
        scores = self._pending_mat @ q / (self._pending_norm * (np.linalg.norm(q) or 1))
        order = pending_order(scores, self._pending_ids, k,
                              fast=getattr(self, "_fast_pending_topk", True))
        return [{"aid": self._pending_ids[i], "score": float(scores[i]),
                 "doc_id": self._index.atoms[self._pending_ids[i]]["doc_id"],
                 "organization": "pending", "generation": self.triple}
                for i in order], {"pending_atoms_scored": len(scores)}

    def close(self):
        if self._closed:
            return
        self._closed = True
        idx = self._index
        if idx._view is not None:
            idx._pool.release(idx._view)
            idx._view = None
        idx._pool = None
        self._index = None
        self._pending_ids = ()
        self._pending_mat = np.empty((0, 0))
        self._pending_norm = np.empty(0)
        self.leaves = self.parents = MappingProxyType({})


def verify_prepared(facade, pin, tlstore=None):
    """Independently re-verify a prepared facade before publication.

    Recomputes membership digests from the facade's own leaves/parents
    snapshots and re-checks within-leaf duplicate/child-edge/union/seq
    invariants. Across-leaf atom sharing is ALLOWED: the source permits up
    to MAX_SEG_MEMBERSHIPS leaf memberships per atom, so no exclusivity is
    enforced here (single pass, no O(L^2) pairwise loop).

    When tlstore is given, facade membership revisions are additionally
    bound to the actual pinned source via read_seg_hierarchy(tlstore, pin):
    every expected ID, commit seq, and members/children/descriptor digest
    must match. Snapshot self-consistency alone is INSUFFICIENT: a prepare
    stage that mutates snapshots and revisions together (ghost-leaf
    tampering) passes the snapshot check but fails the source binding.
    The publisher always passes its tlstore; tlstore=None keeps only the
    snapshot check for legacy detached-facade callers.
    """
    for lid, leaf in facade.leaves.items():
        members = list(leaf["members"])
        if len(set(members)) != len(members):
            raise RuntimeError("duplicate leaf members: " + lid)
    for pid, parent in facade.parents.items():
        children = list(parent.get("children", []))
        if len(set(children)) != len(children):
            raise RuntimeError("duplicate parent children: " + pid)
        if any(c not in facade.leaves for c in children):
            raise RuntimeError("incomplete parent children: " + pid)
        union = {a for c in children for a in facade.leaves[c]["members"]}
        if union != set(parent["members"]):
            raise RuntimeError("incomplete parent member union: " + pid)
    recomputed = []
    for hid, h in sorted({**facade.leaves, **facade.parents}.items()):
        seq = int(h["seq"])
        if not 0 < seq <= pin[2]:
            raise RuntimeError("membership outside pinned frontier")
        digest = hashlib.sha256(canonical({
            "members": list(h["members"]),
            "children": list(h.get("children", [])),
            "descriptor": [float(x) for x in h["descriptor"]]})).hexdigest()
        recomputed.append(MembershipRevision(hid, seq, digest))
    if tuple(recomputed) != facade.membership_revisions:
        raise RuntimeError("prepared membership revisions fail re-verification")
    if tlstore is not None:
        # Membership-only pinned-source population (no second serving pool
        # or dense build): this read counts as preparation work.
        from tlsys.place import read_seg_hierarchy
        source = read_seg_hierarchy(tlstore, tuple(pin))
        expected = []
        for hid, h in sorted({**source["leaves"], **source["parents"]}.items()):
            seq = int(h["seq"])
            if not 0 < seq <= pin[2]:
                raise RuntimeError("source membership outside pinned frontier")
            digest = hashlib.sha256(canonical({
                "members": list(h["members"]),
                "children": list(h.get("children", [])),
                "descriptor": [float(x) for x in h["descriptor"]]})).hexdigest()
            expected.append(MembershipRevision(hid, seq, digest))
        if tuple(expected) != facade.membership_revisions:
            raise RuntimeError("prepared membership revisions differ from pinned source")
    return True


@dataclass
class _Entry:
    record: OrganizationGeneration
    facade: PreparedFacade
    refs: int = 0


class ReaderPin:
    def __init__(self, owner, entry):
        self._owner, self._entry = owner, entry
        self._released = False

    @property
    def generation(self):
        self._require_live()
        return self._entry.record

    @property
    def facade(self):
        self._require_live()
        return self._entry.facade

    def _require_live(self):
        if self._released:
            raise RuntimeError("reader pin already released")

    def release(self):
        self._owner._release(self)

    def __enter__(self):
        self._require_live()
        return self

    def __exit__(self, *exc):
        self.release()


class GenerationPublisher:
    """One preparation worker and O(1) request pin/pointer/refcount handoff.

    Caller provides stable source pin + debt snapshot under its writer lock.
    One publisher owns a directory (enforced by the service writer lifecycle).
    A failed build/validation leaves current.json and current readers unchanged.
    Records are immutable frozen values, content hashed, and append-only files.
    """
    def __init__(self, tlstore, directory, *, prepare: Callable = PreparedFacade,
                 fault: Callable | None = None, reuse_view_pool: bool = False):
        self.tlstore, self.directory = tlstore, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._ownership = open(self.directory / "publisher-owner.lock", "a+b")
        try:
            fcntl.flock(self._ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._ownership.close()
            raise RuntimeError("generation directory already has a publisher") from exc
        self._view_pool = None
        self._pool_anchor = None
        # Custom factories keep their original three-argument interface.
        # They remain responsible for their own serving backend/lifecycle.
        self._prepare = self._prepare_reusing_pool if reuse_view_pool and prepare is PreparedFacade else prepare
        self.reuse_view_pool = bool(reuse_view_pool and prepare is PreparedFacade)
        self._fault = fault
        self._lock = threading.Lock()
        self._publication_lock = threading.Lock()
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="org-prepare")
        self._current = None
        self._entries = {}
        self._closed = False
        self._frozen = False
        self.last_timings = {}

    def _prepare_reusing_pool(self, tlstore, pin, pending_documents):
        from tlsys.serving.view import ViewPool
        from tlsys.index import _resolve_serving_dir
        if self._view_pool is None:
            self._view_pool = ViewPool(tlstore, pin[0], pin[1],
                                       serving_dir=_resolve_serving_dir(None)[0])
        # Opt-in shared-pool prefetch (single prepare worker only): move
        # the pool to the new pin with the source scan outside the pool
        # lock so retained readers keep serving; the facade build below
        # then takes the retained pin (brief lock, no rescan). The extra
        # reference is released immediately; the anchor below owns the
        # published pin exactly as before. Full verify_prepared still
        # runs on every publication.
        pre = self._view_pool.acquire_shared(tuple(pin))
        try:
            facade = PreparedFacade(tlstore, pin, pending_documents,
                                    view_pool=self._view_pool, fast_pending_topk=True)
        finally:
            self._view_pool.release(pre)
        # A separately owned anchor keeps the latest prepared ancestor alive
        # even when durable publication fails and closes its facade. It grants
        # no visibility: only the durable publisher pointer serves requests.
        anchor = self._view_pool.acquire(tuple(pin))
        previous = self._pool_anchor
        self._pool_anchor = anchor
        if previous is not None:
            self._view_pool.release(previous)
        return facade

    def _release_pool_anchor(self):
        if self._pool_anchor is not None:
            self._view_pool.release(self._pool_anchor)
            self._pool_anchor = None
        # Retained facades independently own their pool and view references.
        self._view_pool = None

    def _inject(self, stage):
        if self._fault:
            self._fault(stage)

    def load_record(self):
        pointer = self.directory / "current.json"
        if not pointer.exists():
            return None
        obj = json.loads(pointer.read_bytes())
        gid = obj["generation_id"]
        if len(gid) != 64 or any(c not in "0123456789abcdef" for c in gid):
            raise RuntimeError("invalid generation pointer")
        body = (self.directory / (gid + ".json")).read_bytes()
        if hashlib.sha256(body).hexdigest() != obj["sha256"]:
            raise RuntimeError("generation digest mismatch")
        record = OrganizationGeneration.decode(body)
        if record.generation_id != gid:
            raise RuntimeError("generation pointer mismatch")
        if hashlib.sha256(canonical(self._identity(record))).hexdigest() != gid:
            raise RuntimeError("generation identity mismatch")
        return record

    @staticmethod
    def _identity(record):
        v = asdict(record)
        v.pop("generation_id")
        return v

    def restore(self):
        """Prepare the last DURABLY published frontier, never the source head."""
        record = self.load_record()
        if record is None:
            return None
        return self._worker.submit(self._restore, record)

    def _restore(self, record):
        facade = self._prepare(self.tlstore, record.pin, record.pending_documents)
        if facade.membership_revisions != record.membership_revisions:
            facade.close()
            raise RuntimeError("restored membership revisions differ")
        verify_prepared(facade, record.pin, self.tlstore)
        with self._lock:
            if self._current is not None or self._closed:
                refused = True
            else:
                entry = _Entry(record, facade)
                self._entries[record.generation_id] = entry
                self._current = entry
                refused = False
        if refused:
            facade.close()
            raise RuntimeError("restore requires an empty open publisher")
        return record

    def submit(self, pin, pending_documents=()):
        if self._closed or self._frozen:
            raise RuntimeError("publisher closed or frozen for reads")
        return self._worker.submit(self._build_publish, tuple(pin), tuple(pending_documents))

    def _build_publish(self, pin, pending_documents):
        started = time.perf_counter()
        pin = tuple(pin)
        pending_norm = tuple(sorted(set(pending_documents)))
        # No-op dedup BEFORE expensive preparation: identical frontier
        # (full 4-field pin + canonical pending) republishes the current
        # record with no prep, no fault injection, no disk writes.
        with self._publication_lock:
            current = self._current
            old = current.record if current else self.load_record()
            if old is not None:
                if pin[:2] != old.pin[:2] or pin[2] < old.pin[2]:
                    raise RuntimeError("foreign incarnation or rewound organization frontier")
                if current is not None and tuple(pin) == tuple(old.pin) and pending_norm == tuple(old.pending_documents):
                    self.last_timings = {"prepare_s": 0.0,
                                         "durable_publication_s": 0.0,
                                         "handoff_s": time.perf_counter() - started,
                                         "dedup": "identical-frontier"}
                    return old
        self._inject("before_prepare")
        facade = self._prepare(self.tlstore, pin, pending_documents)
        published = False
        cleanup = None
        try:
            self._inject("after_prepare")
            prepared_at = time.perf_counter()
            verify_prepared(facade, pin, self.tlstore)
            with self._publication_lock:
                current = self._current
                old = current.record if current else self.load_record()
                if old and (pin[:2] != old.pin[:2] or pin[2] < old.pin[2]):
                    raise RuntimeError("foreign incarnation or rewound organization frontier")
                if old and tuple(pin) == tuple(old.pin) \
                        and tuple(sorted(set(pending_documents))) == tuple(old.pending_documents) \
                        and facade.membership_revisions == old.membership_revisions:
                    if current is None:
                        entry = _Entry(old, facade)
                        with self._lock:
                            if self._closed:
                                raise RuntimeError("publisher closed")
                            self._entries[old.generation_id] = entry
                            self._current = entry
                        published = True
                        self.last_timings = {"prepare_s": prepared_at - started,
                                             "durable_publication_s": 0.0,
                                             "handoff_s": time.perf_counter() - prepared_at,
                                             "dedup": "restored-identical-frontier"}
                        return old
                    published = True
                    self.last_timings = {"prepare_s": prepared_at - started,
                                         "durable_publication_s": 0.0,
                                         "handoff_s": 0.0,
                                         "dedup": "identical-frontier"}
                    facade.close()
                    return old
                prototype = OrganizationGeneration("", old.generation_id if old else None,
                                                   pin, facade.membership_revisions,
                                                   tuple(sorted(set(pending_documents))))
                gid = hashlib.sha256(canonical(self._identity(prototype))).hexdigest()
                record = OrganizationGeneration(gid, prototype.parent_generation, pin,
                                                facade.membership_revisions,
                                                prototype.pending_documents)
                body = canonical(asdict(record))
                path = self.directory / (gid + ".json")
                if path.exists():
                    if path.read_bytes() != body:
                        raise RuntimeError("generation record collision")
                else:
                    durable_new(path, body)
                self._inject("before_pointer")
                ptr = canonical({"generation_id": gid, "sha256": hashlib.sha256(body).hexdigest()})
                tmp = self.directory / ("pointer-" + uuid.uuid4().hex + ".prepared")
                durable_new(tmp, ptr)
                # Filesystem pointer may advance before the in-memory pointer;
                # both reference a complete generation, including after a kill.
                os.replace(tmp, self.directory / "current.json")
                fsync_dir(self.directory)
                self._inject("after_durable_pointer")
                entry = _Entry(record, facade)
                swap_started = time.perf_counter()
                with self._lock:
                    if self._closed:
                        raise RuntimeError("publisher closed")
                    self._entries[gid] = entry
                    previous = self._current
                    self._current = entry
                    if previous is not None and previous.refs == 0:
                        self._entries.pop(previous.record.generation_id)
                        cleanup = previous.facade
                    published = True
                swap_ended = time.perf_counter()
                self.last_timings = {"prepare_s": prepared_at - started,
                                     "durable_publication_s": swap_started - prepared_at,
                                     "handoff_s": swap_ended - swap_started}
            return record
        finally:
            if not published:
                facade.close()
            if cleanup:
                cleanup.close()

    def acquire(self):
        with self._lock:
            if self._closed or self._current is None:
                raise RuntimeError("no prepared organization generation")
            entry = self._current
            entry.refs += 1
            return ReaderPin(self, entry)

    def _release(self, pin):
        cleanup = None
        with self._lock:
            if pin._owner is not self or pin._released:
                raise RuntimeError("foreign or released reader pin")
            pin._released = True
            entry = pin._entry
            pin._entry = None
            entry.refs -= 1
            if entry.refs == 0 and entry is not self._current:
                self._entries.pop(entry.record.generation_id)
                cleanup = entry.facade
        if cleanup:
            cleanup.close()

    def retained(self):
        with self._lock:
            return {gid: entry.refs for gid, entry in self._entries.items()}

    def freeze_for_reads(self):
        """Quiesce the worker, relinquish disk ownership, keep old pins serving.

        The service's serialized writer calls this before a writer restart.
        A new publisher may restore the durable pointer in the same directory;
        this old publisher can only acquire/release fixed reader pins afterward.
        """
        self._frozen = True
        self._worker.shutdown(wait=True)
        self._release_pool_anchor()
        self._ownership.close()

    def close(self):
        self._worker.shutdown(wait=True)
        self._release_pool_anchor()
        cleanup = []
        with self._lock:
            self._closed = True
            self._current = None
            for gid, entry in list(self._entries.items()):
                if entry.refs == 0:
                    cleanup.append(entry.facade)
                    self._entries.pop(gid)
        for facade in cleanup:
            facade.close()
        self._ownership.close()
