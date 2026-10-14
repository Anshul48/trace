"""Keyed committed-state projections with consumed frontiers (M2-C).

Repairs the repeated-global-decode finding (independent
MAINTENANCE-FOLLOWUP 2026-10-06): organize_segments used to decode
every ACCEPT_ATOMS commit + artifact per target document, and every
call re-read the hierarchy from seq 0. This module maintains two
keyed views over the SAME committed truth:

  doc atoms ... {doc_id: [atom records]} for keyed per-doc reads;
  hierarchy ... {leaf_id: entry} + {parent_id: entry} latest-wins,
                same classification rules as read_seg_hierarchy;
  xdoc ...... {xdoc_id: entry} latest-wins, same classification
                rules as read_xholons (legacy cross-doc placement).

Consumption is frontier-bounded: update() reads only commits with
seq > frontier (read_commits_all(min_seq=...)) and decodes only
their artifacts. A cold build scans once; an ordinary local
append/correction consumes only its own new commits. The checkpoint
sidecar (PROJ_NAME next to the ingest manifest) persists the keyed
state + frontier across processes; on load it is validated
(version, birth/epoch, frontier <= pinned max) and anything
doubtful falls back to a cold rebuild -- committed ops stay the
source of truth, so a lost or corrupt checkpoint can never certify
wrong state, only cost one rescan.

Disclosure/publication are untouched: this module commits nothing
and publishes nothing; organize/drain commit through their existing
authority and the next update() consumes those versions.

Checkpoint I/O (lane-2 closure): the original checkpoint rewrote +
reparsed the full keyed state on every owned call (O(committed state)
per append). The checkpoint now keeps a full snapshot (PROJ_NAME)
plus an append-only delta journal (PROJ_JOURNAL_NAME): save() persists only
entries dirtied since the last persist, and cached() reuses a
signature-validated warm object across owned calls, so steady-state
per-append checkpoint I/O is one small append + one stat. compact()
rewrites the full snapshot (run boundaries only). The checkpoint stays
a cache: committed ops are the source of truth, so any doubtful file
still falls back to cold rebuild.

Lazy maps (C2 Lane O-7): the snapshot is split into a small meta file
(PROJ_NAME: frontier/triple/xdoc/retired + the doc-id index) plus a
docs file (PROJ_DOCS_NAME, the bulk: per-doc atom records) and a
hierarchy file (PROJ_HIER_NAME: leaves/parents). load() parses only
the meta file; docs/hierarchy parse on first access (_ensure_docs /
_ensure_hier) and reverse maps rebuild on first reverse access, so an
ingest-shaped first-in-process call (xdoc view only) never parses the
bulk. Commits consumed while a map is unloaded accumulate in an
in-memory overlay and merge on ensure; the journal format is
unchanged. Layout-1 single-file snapshots still load (eagerly, with
lazy reverse maps). Old readers treat layout-2 metas as doubtful and
cold-rebuild (safe: only a rescan).
"""

import json
import os

from tlsys.identity import ATOM_SCHEME
from tlsys.place import PARENT_PREFIX, SEG_PREFIX

PROJ_VERSION = 1
PROJ_NAME = "tl_projections.json"
PROJ_DOCS_NAME = "tl_projections_docs.json"
PROJ_HIER_NAME = "tl_projections_hier.json"
PROJ_JOURNAL_NAME = "tl_projections.journal.jsonl"
# Snapshot layout: 1 = single file (docs+leaves+parents+xdoc+retired
# in PROJ_NAME; no "layout" key); 2 = split meta + docs + hier files.
# New snapshots always write layout 2; both load.
PROJ_LAYOUT = 2
# P-2 (Sec 5.7): default projection-compaction bounds. The debt hook
# compacts when the journal exceeds max(max_journal_bytes,
# max_journal_ratio * snapshot_bytes) or max_journal_lines. A store's
# recorded candidate binding may override these (validated there);
# None anywhere below means "this default".
PROJ_COMPACT_DEFAULTS = {"max_journal_bytes": 1048576,
                         "max_journal_ratio": 0.25,
                         "max_journal_lines": 4096}


def validate_compact_bounds(bounds):
    """Normalized compact bounds (defaults + validated overrides)."""
    out = dict(PROJ_COMPACT_DEFAULTS)
    if bounds is None:
        return out
    if not isinstance(bounds, dict):
        raise ValueError("compact bounds must be a dict or None")
    for key in bounds:
        if key not in out:
            raise ValueError(f"unknown compact bound {key!r}")
    for key in ("max_journal_bytes", "max_journal_lines"):
        val = bounds.get(key, out[key])
        if not isinstance(val, int) or isinstance(val, bool) \
                or val < 0:
            raise ValueError(
                f"compact bound {key} must be a nonneg int, got "
                f"{val!r}")
        out[key] = val
    ratio = bounds.get("max_journal_ratio", out["max_journal_ratio"])
    if not isinstance(ratio, (int, float)) \
            or isinstance(ratio, bool) or ratio < 0:
        raise ValueError(
            "compact bound max_journal_ratio must be a nonneg "
            f"number, got {ratio!r}")
    out["max_journal_ratio"] = float(ratio)
    return out

# Warm per-store reuse for the owned lifecycle (cached()): root ->
# {"sig", "obj"}. A cache hit still runs update(), which validates
# against the live pin (foreign/rewound stores reset + cold-rebuild),
# so a stale object can never certify wrong state -- at worst one
# rescan. Callers on one store are serialized (same rule as ingest).
_WARM = {}


class Projections:
    """Caller-owned keyed views + consumed frontier (one per store).

    update(tlstore) advances the frontier to the current pin and
    returns a catch-up receipt {"cold", "commits", "artifacts",
    "bytes", "frontier", "triple"}. doc_rows(doc_id) and
    hierarchy_view() serve keyed reads with no storage access.
    save(tlstore)/load(tlstore) checkpoint the state; load of a
    missing/corrupt/incompatible file returns a fresh object that
    cold-rebuilds on the next update().
    """

    def __init__(self):
        self.version = PROJ_VERSION
        self.birth = None
        self.epoch = None
        self.frontier = 0
        self.triple = None
        self._docs = {}    # doc_id -> {atom: record}
        self._leaves = {}  # leaf_id -> entry (read_seg_hierarchy shape)
        self._parents = {}  # parent_id -> entry (same shape)
        self._xdoc = {}    # xdoc_id -> entry (read_xholons shape)
        self._retired = {}  # doc_id -> {seq, op_id, reason} (lifecycle)
        # C2 Lane O keyed reverse maps (derived from the entries above;
        # maintained incrementally in _ingest_meta, rebuilt from edges
        # after checkpoint load; never persisted, so the checkpoint
        # format is unchanged and a lost map costs one rebuild).
        self._leaf_parents = {}  # leaf_id -> set(parent_id)
        self._parent_children = {}  # parent_id -> set(leaf_id)
        self._atom_leaves = {}  # atom_id -> set(leaf_id)
        # Delta-journal bookkeeping: keys dirtied since the last
        # persist, per map. _dirty_all (fresh/cold objects) forces a
        # full snapshot on the next save; _snap_* describe the disk
        # state this object believes is persisted.
        self._dirty = {"docs": set(), "leaves": set(),
                       "parents": set(), "xdoc": set(),
                       "retired": set()}
        self._dirty_all = True
        self._snap_sig = None
        self._snap_frontier = 0
        # O-7 lazy state. Fresh objects own fully-live maps; load()
        # of a layout-2 snapshot sets _docs/_leaves/_parents to None
        # (unloaded) and fills them on first access. _docs_new /
        # _hier_new are overlays for commits consumed while unloaded
        # (merged on ensure). _base_doc_ids is the snapshot-time doc
        # set (completeness gate for journaling partial overlays).
        # _store_root + _last_tlstore serve deferred loads/heals.
        self._docs_loaded = True
        self._hier_loaded = True
        self._maps_built = True
        self._docs_new = {}
        self._hier_new = {"leaves": {}, "parents": {}}
        self._base_doc_ids = None
        self._store_root = None
        self._last_tlstore = None

    # -- keyed reads (no storage) ------------------------------------
    def doc_rows(self, doc_id):
        """[(aid, vec, chunk_ix, span, byte_span)] in chunk order.

        Same row shape + fail-closed contract as
        maint._doc_atom_rows (RuntimeError when the doc has no
        committed atoms in the consumed prefix).
        """
        self._ensure_docs()
        recs = self._docs.get(doc_id)
        if not recs:
            raise RuntimeError(
                f"organize: doc {doc_id!r} has no committed atoms; "
                "stays unorganized (never half-placed)")
        rows = [(a, list(r["descriptor"]), r["chunk_ix"],
                 list(r["span"]), list(r["byte_span"]))
                for a, r in recs.items()]
        rows.sort(key=lambda t: (t[2] is None, t[2]))
        return rows

    def doc_vecs(self, doc_id):
        """[(aid, vec)] in chunk order (maint._doc_vecs shape)."""
        return [(a, v) for a, v, _c, _s, _b
                in self.doc_rows(doc_id)]

    def hierarchy_view(self):
        """{"leaves", "parents"} latest-wins over the consumed prefix.

        Same entry shape as read_seg_hierarchy (members/descriptor/
        segments|children + seq). Returned dicts are the live
        projection maps: callers overlaying uncommitted versions
        must copy first.
        """
        self._ensure_hier()
        return {"leaves": self._leaves, "parents": self._parents}

    def xholons_view(self):
        """{xdoc_id: entry} latest-wins (read_xholons shape).

        Same aliasing note as hierarchy_view: callers overlaying
        uncommitted versions must copy first.
        """
        return self._xdoc

    def retired_view(self):
        """{doc_id: {"seq", "op_id", "reason"}} latest-wins.

        Same shape as lifecycle.read_retirements (the parity oracle).
        Same aliasing note as hierarchy_view.
        """
        return self._retired

    # -- keyed reverse maps (C2 Lane O; derived, never persisted) -------
    def leaf_parents_view(self):
        """{leaf_id: set(parent_id)} over the consumed prefix.

        Live sets: callers must not mutate them (copy first).
        """
        self._ensure_reverse_maps()
        return self._leaf_parents

    def parent_children_view(self):
        """{parent_id: set(child_id)} membership mirror of children lists.

        Children ORDER still lives in the parent entries; this map is
        membership only. Live sets: callers must not mutate them.
        """
        self._ensure_reverse_maps()
        return self._parent_children

    def atom_leaves_view(self):
        """{atom_id: set(leaf_id)} over the consumed prefix.

        Live sets: callers must not mutate them (copy first).
        """
        self._ensure_reverse_maps()
        return self._atom_leaves

    def _relink_leaf(self, hid, old_members, new_members):
        if not self._maps_built:
            # Lazy maps: entries are recorded (base/overlay) and the
            # maps rebuild from the merged edges on first reverse
            # access, so incremental relink is skipped, not lost.
            return
        gone = set(old_members) - set(new_members)
        for aid in gone:
            owners = self._atom_leaves.get(aid)
            if owners is not None:
                owners.discard(hid)
                if not owners:
                    del self._atom_leaves[aid]
        for aid in set(new_members) - set(old_members):
            self._atom_leaves.setdefault(aid, set()).add(hid)

    def _relink_parent(self, hid, old_children, new_children):
        if not self._maps_built:
            # Lazy maps: see _relink_leaf (rebuild covers the edge).
            return
        gone = set(old_children) - set(new_children)
        for lid in gone:
            pars = self._leaf_parents.get(lid)
            if pars is not None:
                pars.discard(hid)
                if not pars:
                    del self._leaf_parents[lid]
        for lid in set(new_children):
            self._leaf_parents.setdefault(lid, set()).add(hid)
        self._parent_children[hid] = set(new_children)

    def rebuild_reverse_maps(self):
        """Rebuild all reverse maps from the current entries (edges win).

        The repair path for FI-19 drift: entries are the truth, maps
        are derived. Returns {"leaf_edges", "atom_edges"} counts.
        """
        self._ensure_hier()
        self._maps_built = True
        self._leaf_parents = {}
        self._parent_children = {}
        self._atom_leaves = {}
        for hid, entry in self._leaves.items():
            for aid in set(entry.get("members", ())):
                self._atom_leaves.setdefault(aid, set()).add(hid)
        for hid, entry in self._parents.items():
            kids = set(entry.get("children", ()))
            self._parent_children[hid] = set(kids)
            for lid in kids:
                self._leaf_parents.setdefault(lid, set()).add(hid)
        return {"leaf_edges": sum(len(v) for v in
                                  self._leaf_parents.values()),
                "atom_edges": sum(len(v) for v in
                                  self._atom_leaves.values())}

    def validate_reverse_maps(self):
        """Compare maintained maps against a from-edges rebuild.

        Returns {"ok": bool, "mismatches": [...]} with at most 8
        mismatch records {map, key, maintained, rebuilt}. Pure read:
        never repairs (call rebuild_reverse_maps explicitly).
        Filling the derived cache on a lazily-loaded object is not a
        repair (entries untouched; values identical to eager load).
        """
        self._ensure_reverse_maps()
        keep_lp = self._leaf_parents
        keep_pc = self._parent_children
        keep_al = self._atom_leaves
        self._leaf_parents = {}
        self._parent_children = {}
        self._atom_leaves = {}
        self.rebuild_reverse_maps()
        fresh_lp = self._leaf_parents
        fresh_pc = self._parent_children
        fresh_al = self._atom_leaves
        self._leaf_parents = keep_lp
        self._parent_children = keep_pc
        self._atom_leaves = keep_al
        bad = []

        def _cmp(name, maintained, rebuilt):
            for key in set(maintained) | set(rebuilt):
                if bad and len(bad) >= 8:
                    return
                if maintained.get(key, set()) != rebuilt.get(key, set()):
                    bad.append(
                        {"map": name, "key": key,
                         "maintained": sorted(maintained.get(key, ())),
                         "rebuilt": sorted(rebuilt.get(key, ()))})
        _cmp("leaf_parents", keep_lp, fresh_lp)
        _cmp("parent_children", keep_pc, fresh_pc)
        _cmp("atom_leaves", keep_al, fresh_al)
        return {"ok": not bad, "mismatches": bad}

    # -- frontier-bounded consumption --------------------------------
    def update(self, tlstore):
        """Consume new commits through the current pin; catch-up receipt."""
        birth, epoch, mx, triple = tlstore.pin()
        self._store_root = tlstore.store.root
        self._last_tlstore = tlstore
        if self.birth is None or self.birth != birth \
                or self.epoch != epoch or self.frontier > mx:
            # New/foreign/rewound store: reset, then cold-consume.
            self.__init__()
            self._store_root = tlstore.store.root
            self._last_tlstore = tlstore
            self.birth, self.epoch = birth, epoch
            cold = True
        else:
            docs_live = self._docs if self._docs_loaded else self._docs_new
            leaves_live = self._leaves if self._hier_loaded \
                else self._hier_new["leaves"]
            parents_live = self._parents if self._hier_loaded \
                else self._hier_new["parents"]
            cold = self.frontier == 0 and not docs_live \
                and not leaves_live and not parents_live \
                and not self._xdoc and not self._retired
            # A warm checkpoint at frontier 0 with empty state is
            # still a cold consume; otherwise incremental.
            if self.triple == triple and self.frontier == mx:
                return {"cold": False, "commits": 0, "artifacts": 0,
                        "bytes": 0, "frontier": self.frontier,
                        "triple": triple}
        rows = tlstore.read_commits_all(birth, epoch, mx,
                                        kind="ACCEPT_ATOMS",
                                        min_seq=self.frontier)
        seqs = [r[0] for r in rows]
        op_of_seq = {r[0]: r[1] for r in rows}
        refs = tlstore.pub_refs(seqs)
        arows = tlstore.artifact_rows(
            [a for seq in seqs for a in refs.get(seq, [])])
        n_art = n_bytes = 0
        for seq in seqs:
            for art_id in refs.get(seq, []):
                arow = arows.get(art_id)
                if arow is None:
                    continue
                body = tlstore.read_artifact(art_id,
                                             expect_digest=arow[4])
                n_art += 1
                n_bytes += len(body)
                try:
                    meta = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue  # text artifact, not meta
                if not isinstance(meta, dict):
                    continue
                self._ingest_meta(meta, seq, op_of_seq.get(seq))
            if seq > self.frontier:
                self.frontier = seq
        self.triple = triple
        return {"cold": cold, "commits": len(seqs),
                "artifacts": n_art, "bytes": n_bytes,
                "frontier": self.frontier, "triple": triple}

    def _ingest_meta(self, meta, seq, op_id=None):
        # Atom records: same acceptance rule as _doc_atom_rows
        # (doc_id + atom + descriptor present). While the docs base
        # is unloaded, records accumulate in the overlay (merged per
        # atom on ensure; the journal gate in save() keeps partial
        # per-doc dicts off disk).
        if "atom" in meta and "descriptor" in meta \
                and "doc_id" in meta:
            doc = meta["doc_id"]
            if isinstance(doc, str):
                target = self._docs if self._docs_loaded \
                    else self._docs_new
                target.setdefault(doc, {})[meta["atom"]] = {
                    "descriptor": [float(x)
                                   for x in meta["descriptor"]],
                    "chunk_ix": meta.get("chunk_ix"),
                    "span": list(meta.get("span", [])),
                    "byte_span": list(meta.get("byte_span", [])),
                    "seq": seq}
                self._dirty["docs"].add(doc)
        # Retirement markers: same rule as read_retirements (the
        # parity oracle); latest-wins per doc.
        ret = meta.get("retirement")
        if isinstance(ret, dict) and isinstance(ret.get("doc"), str):
            if meta.get("atom_scheme") != ATOM_SCHEME:
                raise ValueError(
                    f"op seq {seq}: retirement meta scheme "
                    f"{meta.get('atom_scheme')!r} != {ATOM_SCHEME!r}")
            doc = ret["doc"]
            self._retired[doc] = {"seq": seq, "op_id": op_id,
                                  "reason": str(ret.get("reason", ""))}
            self._dirty["retired"].add(doc)
        # Hierarchy records: same classification + scheme rules as
        # read_seg_hierarchy (kind tag, never the bare prefix).
        hid = meta.get("holon")
        kind = meta.get("kind")
        if not isinstance(hid, str):
            return
        if kind == "seg-leaf" and hid.startswith(SEG_PREFIX):
            if meta.get("atom_scheme") != ATOM_SCHEME:
                raise ValueError(
                    f"op seq {seq}: seg-leaf meta scheme "
                    f"{meta.get('atom_scheme')!r} != {ATOM_SCHEME!r}")
            # Whole-entry latest-wins: the overlay value is always a
            # complete entry, so no completeness gate is needed here
            # (unlike the per-atom docs merge).
            target = self._leaves if self._hier_loaded \
                else self._hier_new["leaves"]
            old = target.get(hid)
            target[hid] = {
                "members": list(meta.get("members", [])),
                "descriptor": list(meta.get("descriptor", [])),
                "segments": list(meta.get("segments", [])),
                "seq": seq}
            self._dirty["leaves"].add(hid)
            self._relink_leaf(hid,
                              old.get("members", ()) if old else (),
                              target[hid]["members"])
        elif kind == "seg-parent" and hid.startswith(PARENT_PREFIX):
            if meta.get("atom_scheme") != ATOM_SCHEME:
                raise ValueError(
                    f"op seq {seq}: seg-parent meta scheme "
                    f"{meta.get('atom_scheme')!r} != {ATOM_SCHEME!r}")
            target = self._parents if self._hier_loaded \
                else self._hier_new["parents"]
            old = target.get(hid)
            target[hid] = {
                "members": list(meta.get("members", [])),
                "children": list(meta.get("children", [])),
                "descriptor": list(meta.get("descriptor", [])),
                "seq": seq}
            self._dirty["parents"].add(hid)
            self._relink_parent(hid,
                                old.get("children", ()) if old else (),
                                target[hid]["children"])
        # Legacy xdoc holons: same rule as read_xholons (bare
        # "xdoc-" prefix; per-doc holons use doc ids and the
        # prefix is refused for doc ids at placement).
        if hid.startswith("xdoc-"):
            if meta.get("atom_scheme") != ATOM_SCHEME:
                raise ValueError(
                    f"op seq {seq}: xholon meta scheme "
                    f"{meta.get('atom_scheme')!r} != {ATOM_SCHEME!r}")
            self._xdoc[hid] = {
                "members": list(meta.get("members", [])),
                "descriptor": list(meta.get("descriptor", [])),
                "seq": seq}
            self._dirty["xdoc"].add(hid)

    # -- checkpoint (snapshot + delta journal) -------------------------
    @staticmethod
    def checkpoint_path(tlstore):
        return os.path.join(tlstore.store.root, PROJ_NAME)

    @staticmethod
    def docs_path(tlstore):
        return os.path.join(tlstore.store.root, PROJ_DOCS_NAME)

    @staticmethod
    def hier_path(tlstore):
        return os.path.join(tlstore.store.root, PROJ_HIER_NAME)

    @staticmethod
    def journal_path(tlstore):
        return os.path.join(tlstore.store.root, PROJ_JOURNAL_NAME)

    @staticmethod
    def checkpoint_bytes(tlstore):
        """Total checkpoint bytes on disk (snapshot files + journal)."""
        total = 0
        for path in (Projections.checkpoint_path(tlstore),
                     Projections.docs_path(tlstore),
                     Projections.hier_path(tlstore),
                     Projections.journal_path(tlstore)):
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        return total

    @staticmethod
    def _disk_sig(tlstore):
        """O(1) disk signature: per-file stat pairs (meta, docs, hier,
        journal). In-memory only; never compared across versions."""
        sig = []
        for path in (Projections.checkpoint_path(tlstore),
                     Projections.docs_path(tlstore),
                     Projections.hier_path(tlstore),
                     Projections.journal_path(tlstore)):
            try:
                st = os.stat(path)
            except OSError:
                sig.append(None)
            else:
                sig.append((st.st_mtime_ns, st.st_size))
        return tuple(sig)

    def _meta_payload(self):
        # Layout-2 meta: everything EXCEPT the lazy maps, plus the
        # doc-id index (the save-time completeness gate for partial
        # docs overlays). Callers must _ensure_all first.
        return {"version": self.version, "layout": PROJ_LAYOUT,
                "birth": self.birth, "epoch": self.epoch,
                "frontier": self.frontier, "triple": self.triple,
                "xdoc": self._xdoc, "retired": self._retired,
                "doc_ids": sorted(self._docs)}

    def _docs_payload(self):
        # Bare docs dict (callers must _ensure_docs first).
        return self._docs

    def _hier_payload(self):
        # Leaves + parents (callers must _ensure_hier first).
        return {"leaves": self._leaves, "parents": self._parents}

    @staticmethod
    def _atomic_write_json(path, payload):
        tmp_path = path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

    def _write_snapshot(self, tlstore):
        """Atomic full-snapshot persist; truncates the journal.

        Writes docs + hier BEFORE the meta file, then truncates the
        journal: every crash interleaving stays correct (journal
        replay is idempotent latest-wins, so a newer base file with
        an older meta simply replays already-covered deltas).
        """
        self._ensure_all(tlstore)
        self._atomic_write_json(self.docs_path(tlstore),
                                self._docs_payload())
        self._atomic_write_json(self.hier_path(tlstore),
                                self._hier_payload())
        path = self.checkpoint_path(tlstore)
        self._atomic_write_json(path, self._meta_payload())
        jpath = self.journal_path(tlstore)
        try:
            if os.path.isfile(jpath):
                os.remove(jpath)
        except OSError:
            pass
        return path

    def _clear_dirty(self, tlstore):
        for keys in self._dirty.values():
            keys.clear()
        self._dirty_all = False
        self._snap_frontier = self.frontier
        self._snap_sig = self._disk_sig(tlstore)
        _WARM[tlstore.store.root] = {"sig": self._snap_sig,
                                     "obj": self}

    def save(self, tlstore):
        """Persist checkpoint state; returns the snapshot path.

        Steady state is a delta append: one journal line carrying
        only entries dirtied since the last persist plus the
        frontier (O(new commits), not O(committed state)). A full
        snapshot is written only when this object is fresh/cold, the
        disk state is unknown/foreign, or the disk files changed
        underneath it. A persist that advances nothing is a no-op.
        """
        if not self._dirty_all and self._snap_sig is not None \
                and self._snap_sig == self._disk_sig(tlstore) \
                and self.frontier >= self._snap_frontier:
            if self.frontier == self._snap_frontier and not any(
                    self._dirty.values()):
                return self.checkpoint_path(tlstore)
            # O-7 docs completeness gate: journal replay REPLACES
            # whole per-doc dicts, so a partial overlay dict (a base
            # doc with only some atoms consumed while unloaded) must
            # never hit the journal. Docs absent from the snapshot
            # base are complete in the overlay and journal directly;
            # otherwise merge first (hier overlays are always whole
            # entries and need no gate).
            if not self._docs_loaded and self._base_doc_ids is not None \
                    and any(d in self._base_doc_ids
                            for d in self._dirty["docs"]):
                self._ensure_docs(tlstore)
            docs_src = self._docs if self._docs_loaded \
                else self._docs_new
            leaves_src = self._leaves if self._hier_loaded \
                else self._hier_new["leaves"]
            parents_src = self._parents if self._hier_loaded \
                else self._hier_new["parents"]
            line = {"frontier": self.frontier, "triple": self.triple,
                    "docs": {k: docs_src[k]
                             for k in sorted(self._dirty["docs"])
                             if k in docs_src},
                    "leaves": {k: leaves_src[k]
                               for k in sorted(self._dirty["leaves"])
                               if k in leaves_src},
                    "parents": {k: parents_src[k]
                                for k in sorted(self._dirty["parents"])
                                if k in parents_src},
                    "xdoc": {k: self._xdoc[k]
                             for k in sorted(self._dirty["xdoc"])
                             if k in self._xdoc},
                    "retired": {k: self._retired[k]
                                for k in sorted(self._dirty["retired"])
                                if k in self._retired}}
            jpath = self.journal_path(tlstore)
            with open(jpath, "a") as f:
                f.write(json.dumps(line, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._clear_dirty(tlstore)
            return self.checkpoint_path(tlstore)
        path = self._write_snapshot(tlstore)
        self._clear_dirty(tlstore)
        return path

    def compact(self, tlstore):
        """Rewrite the full snapshot + truncate the journal.

        Explicit boundary op for run ends (never the append path):
        bounds journal growth across long runs. Returns the path.
        """
        self._dirty_all = True
        return self.save(tlstore)

    @staticmethod
    def journal_debt(tlstore, line_cap=None):
        """Bounded checkpoint-debt census (stats + capped line count).

        line_cap bounds the journal read (default: default max
        lines + 1, so lines_capped ⟺ over the default lines
        bound). Never parses the snapshot or the journal; a journal
        read error leaves journal_lines None (bytes still known).
        """
        if line_cap is None:
            line_cap = PROJ_COMPACT_DEFAULTS["max_journal_lines"] + 1
        snap = 0
        for path in (Projections.checkpoint_path(tlstore),
                     Projections.docs_path(tlstore),
                     Projections.hier_path(tlstore)):
            try:
                snap += os.path.getsize(path)
            except OSError:
                pass
        jpath = Projections.journal_path(tlstore)
        try:
            jbytes = os.path.getsize(jpath)
        except OSError:
            return {"journal_bytes": 0, "journal_lines": 0,
                    "lines_capped": False, "snapshot_bytes": snap}
        lines, capped, error = 0, False, None
        try:
            with open(jpath, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        break
                    lines += chunk.count(b"\n")
                    if lines >= line_cap:
                        lines, capped = line_cap, True
                        break
        except OSError as e:
            error = f"{type(e).__name__}: {e}"
        out = {"journal_bytes": jbytes,
               "journal_lines": None if error else lines,
               "lines_capped": capped, "snapshot_bytes": snap}
        if error:
            out["journal_error"] = error
        return out

    @staticmethod
    def maybe_compact(tlstore, bounds=None, reason="debt-hook"):
        """Compact the checkpoint iff journal debt trips the bounds.

        The bounded lifecycle/debt hook: a stat + capped line count
        when clean (no snapshot parse, no rewrite); a full snapshot
        + journal truncate with charged work ONLY past the bound.
        Never runs on the foreground small-edit path (callers:
        maintenance entries + explicit run boundaries). The receipt
        carries {checked, compacted, reason, bounds, byte_limit,
        debt_before, debt_after?, catchup?, work?}.
        """
        b = validate_compact_bounds(bounds)
        debt = Projections.journal_debt(
            tlstore, line_cap=b["max_journal_lines"] + 1)
        limit = max(b["max_journal_bytes"],
                    b["max_journal_ratio"] * debt["snapshot_bytes"])
        over_lines = debt["journal_lines"] is not None \
            and debt["journal_lines"] > b["max_journal_lines"]
        over = debt["journal_bytes"] > limit or over_lines
        receipt = {"checked": True, "compacted": False,
                   "reason": reason, "bounds": b,
                   "byte_limit": limit, "debt_before": debt}
        if not over:
            return receipt
        obj = Projections.cached(tlstore)
        catchup = obj.update(tlstore)
        maps_loaded = bool(obj._docs_loaded and obj._hier_loaded)
        obj.compact(tlstore)
        after = Projections.journal_debt(
            tlstore, line_cap=b["max_journal_lines"] + 1)
        receipt.update(
            compacted=True, catchup=catchup, debt_after=after,
            work={"journal_bytes_retired":
                  debt["journal_bytes"] - after["journal_bytes"],
                  "journal_lines_before": debt["journal_lines"],
                  "snapshot_bytes_before": debt["snapshot_bytes"],
                  "snapshot_bytes_after": after["snapshot_bytes"],
                  "snapshot_bytes_written":
                  after["snapshot_bytes"],
                  "base_parsed": not maps_loaded})
        return receipt

    @staticmethod
    def compact_now(tlstore, reason="run-boundary"):
        """Explicit run-boundary compaction (idempotent when clean).

        Zero bounds: any journal content compacts (a layout-1
        snapshot migrates to layout 2 as part of the rewrite); an
        already-compact checkpoint is a receipted no-op.
        """
        receipt = Projections.maybe_compact(
            tlstore,
            bounds={"max_journal_bytes": 0,
                    "max_journal_ratio": 0.0,
                    "max_journal_lines": 0},
            reason=reason)
        receipt["forced"] = True
        return receipt

    @classmethod
    def load(cls, tlstore):
        """Load snapshot + journal replay; anything doubtful -> fresh.

        Missing file, unparsable JSON, version/shape mismatch, or a
        corrupt/out-of-order journal line all return a fresh
        (cold-rebuild) object -- never a half-trusted view. The
        frontier-vs-pin check happens in update(), which owns the
        live pin. Pure disk read (no warm cache); see cached().

        Layout 1 (single file) loads eagerly with lazy reverse maps;
        layout 2 (split) parses only the meta file here -- docs/hier
        parse on first access, and a deferred base-file failure heals
        via cold rebuild on access (the checkpoint stays a cache).
        """
        obj = cls()
        obj._store_root = tlstore.store.root
        obj._last_tlstore = tlstore
        path = cls.checkpoint_path(tlstore)
        if not os.path.isfile(path):
            return obj
        try:
            with open(path) as f:
                payload = json.load(f)
        except (ValueError, OSError, UnicodeDecodeError):
            return obj
        if not isinstance(payload, dict):
            return obj
        if payload.get("version") != PROJ_VERSION:
            return obj
        if payload.get("layout", 1) == PROJ_LAYOUT:
            return cls._load_layout2(tlstore, obj, payload)
        if payload.get("layout", 1) != 1 or "docs" not in payload:
            return obj
        return cls._load_layout1(tlstore, obj, payload)

    @classmethod
    def _replay_journal(cls, tlstore, frontier, obj, targets):
        """Replay journal lines into target maps; (frontier, ok).

        Strictly increasing frontiers, dict maps only; any failure
        invalidates the whole load. targets maps journal keys to the
        dicts to update (base maps for layout 1, overlays for the
        lazy layout-2 maps).
        """
        jpath = cls.journal_path(tlstore)
        if not os.path.isfile(jpath):
            return frontier, True
        try:
            with open(jpath) as f:
                lines = list(f)
        except (OSError, UnicodeDecodeError):
            return frontier, False
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                return frontier, False
            if not isinstance(rec, dict):
                return frontier, False
            fline = rec.get("frontier")
            if not isinstance(fline, int) or fline <= frontier:
                return frontier, False
            for key, target in targets:
                part = rec.get(key, {})
                if not isinstance(part, dict):
                    return frontier, False
                target.update(part)
            frontier = fline
            obj.triple = rec.get("triple")
        return frontier, True

    @classmethod
    def _fresh_for(cls, tlstore):
        """Fresh object carrying this store's root/handle."""
        obj = cls()
        obj._store_root = tlstore.store.root
        obj._last_tlstore = tlstore
        return obj

    @classmethod
    def _finish_load(cls, tlstore, obj, frontier):
        for keys in obj._dirty.values():
            keys.clear()
        obj._dirty_all = False
        obj._snap_frontier = frontier
        obj._snap_sig = cls._disk_sig(tlstore)
        return obj

    @classmethod
    def _load_layout1(cls, tlstore, obj, payload):
        """Eager single-file load (legacy snapshots; maps lazy)."""
        birth, epoch = payload.get("birth"), payload.get("epoch")
        frontier = payload.get("frontier")
        if not isinstance(frontier, int) or frontier < 0:
            return obj
        docs = payload.get("docs")
        leaves = payload.get("leaves")
        parents = payload.get("parents")
        xdoc = payload.get("xdoc", {})
        retired = payload.get("retired", {})
        if not isinstance(docs, dict) \
                or not isinstance(leaves, dict) \
                or not isinstance(parents, dict) \
                or not isinstance(xdoc, dict) \
                or not isinstance(retired, dict):
            return obj
        frontier, ok = cls._replay_journal(
            tlstore, frontier, obj,
            (("docs", docs), ("leaves", leaves), ("parents", parents),
             ("xdoc", xdoc), ("retired", retired)))
        if not ok:
            return cls._fresh_for(tlstore)
        if obj.triple is None:
            obj.triple = payload.get("triple")
        obj.birth, obj.epoch = birth, epoch
        obj.frontier = frontier
        obj._docs = docs
        obj._leaves = leaves
        obj._parents = parents
        obj._xdoc = xdoc
        obj._retired = retired
        obj._docs_loaded = True
        obj._hier_loaded = True
        # Reverse maps stay lazy (O-7): journal replay bypasses
        # _ingest_meta, so the maps rebuild from the loaded edges on
        # first reverse access instead of here.
        obj._maps_built = False
        return cls._finish_load(tlstore, obj, frontier)

    @classmethod
    def _load_layout2(cls, tlstore, obj, payload):
        """Meta-only load (split snapshots; docs/hier/maps lazy)."""
        birth, epoch = payload.get("birth"), payload.get("epoch")
        frontier = payload.get("frontier")
        if not isinstance(frontier, int) or frontier < 0:
            return obj
        xdoc = payload.get("xdoc", {})
        retired = payload.get("retired", {})
        doc_ids = payload.get("doc_ids")
        if not isinstance(xdoc, dict) \
                or not isinstance(retired, dict) \
                or not isinstance(doc_ids, list) \
                or not all(isinstance(d, str) for d in doc_ids):
            return obj
        # Split files must all be present (content validates on
        # access, with cold-rebuild heal); a missing file is
        # doubtful -> fresh.
        if not os.path.isfile(cls.docs_path(tlstore)) \
                or not os.path.isfile(cls.hier_path(tlstore)):
            return obj
        docs_new = {}
        hier_new = {"leaves": {}, "parents": {}}
        frontier, ok = cls._replay_journal(
            tlstore, frontier, obj,
            (("docs", docs_new), ("leaves", hier_new["leaves"]),
             ("parents", hier_new["parents"]), ("xdoc", xdoc),
             ("retired", retired)))
        if not ok:
            return cls._fresh_for(tlstore)
        if obj.triple is None:
            obj.triple = payload.get("triple")
        obj.birth, obj.epoch = birth, epoch
        obj.frontier = frontier
        obj._docs = None
        obj._leaves = None
        obj._parents = None
        obj._xdoc = xdoc
        obj._retired = retired
        obj._docs_loaded = False
        obj._hier_loaded = False
        obj._maps_built = False
        obj._docs_new = docs_new
        obj._hier_new = hier_new
        obj._base_doc_ids = set(doc_ids)
        return cls._finish_load(tlstore, obj, frontier)

    def _read_split_file(self, name):
        """Parse a lazy base file; None on any problem (heal path)."""
        try:
            if self._store_root is None:
                return None
            with open(os.path.join(self._store_root, name)) as f:
                payload = json.load(f)
        except (ValueError, OSError, UnicodeDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _heal_from_commits(self, tlstore):
        """Cold-reset + rescan after a deferred base-file failure.

        The checkpoint is a cache: committed ops are the source of
        truth, so a corrupt split file costs one rescan, never wrong
        state. The next save() snapshots (healing the disk files).
        """
        if tlstore is None:
            raise RuntimeError(
                "proj checkpoint base file unreadable and no store "
                "handle to rebuild from; refusing to serve partial "
                "state")
        root = self._store_root or tlstore.store.root
        self.__init__()
        self._store_root = root
        self._last_tlstore = tlstore
        self.update(tlstore)
        # Force a snapshot on the next save (heals the disk files).
        self._snap_sig = None
        self._dirty_all = True

    def _ensure_docs(self, tlstore=None):
        """Load + merge the docs base on first docs access."""
        if self._docs_loaded:
            return
        base = self._read_split_file(PROJ_DOCS_NAME)
        if base is None:
            self._heal_from_commits(
                tlstore or self._last_tlstore)
            return
        try:
            for doc, recs in self._docs_new.items():
                if doc in base:
                    base[doc].update(recs)
                else:
                    base[doc] = recs
        except (AttributeError, ValueError, TypeError):
            self._heal_from_commits(
                tlstore or self._last_tlstore)
            return
        self._docs = base
        self._docs_new = {}
        self._docs_loaded = True
        self._base_doc_ids = None

    def _ensure_hier(self, tlstore=None):
        """Load + merge the hierarchy base on first hier access."""
        if self._hier_loaded:
            return
        base = self._read_split_file(PROJ_HIER_NAME)
        if base is None or not isinstance(base.get("leaves"), dict) \
                or not isinstance(base.get("parents"), dict):
            self._heal_from_commits(
                tlstore or self._last_tlstore)
            return
        base["leaves"].update(self._hier_new["leaves"])
        base["parents"].update(self._hier_new["parents"])
        self._leaves = base["leaves"]
        self._parents = base["parents"]
        self._hier_new = {"leaves": {}, "parents": {}}
        self._hier_loaded = True

    def _ensure_reverse_maps(self, tlstore=None):
        """Rebuild reverse maps on first reverse access (lazy)."""
        self._ensure_hier(tlstore)
        if not self._maps_built:
            self.rebuild_reverse_maps()

    def _ensure_all(self, tlstore=None):
        """Load every lazy map (snapshot/compact/retained paths)."""
        self._ensure_docs(tlstore)
        self._ensure_hier(tlstore)

    @classmethod
    def cached(cls, tlstore):
        """Signature-validated warm reuse for the owned lifecycle.

        Same object back when the disk files are unchanged since our
        last persist/load (steady state: one stat, zero JSON parse);
        any change falls back to disk load() (which still fails safe
        to cold rebuild). Callers must run update() next, as with
        load(). Pure-disk readers should keep using load().
        """
        root = tlstore.store.root
        sig = cls._disk_sig(tlstore)
        hit = _WARM.get(root)
        if hit is not None and hit["sig"] == sig:
            return hit["obj"]
        obj = cls.load(tlstore)
        _WARM[root] = {"sig": cls._disk_sig(tlstore), "obj": obj}
        return obj

    @staticmethod
    def suffix_metas(tlstore, from_seq):
        """Decoded ACCEPT_ATOMS metas above a validated frontier.

        Closure P (§5.2): the bounded resume primitive. Reads seqs in
        (from_seq, pin-max] only -- never a prefix rescan -- and
        returns ([(seq, op_id, meta)], {commits, artifacts, bytes}).
        Text (non-meta) artifacts are skipped, exactly like update().
        Fails closed on any read failure (callers must never resume
        blind); artifact integrity errors propagate loud.
        """
        birth, epoch, mx, _triple = tlstore.pin()
        try:
            rows = tlstore.read_commits_all(birth, epoch, mx,
                                            kind="ACCEPT_ATOMS",
                                            min_seq=from_seq)
        except Exception as e:
            raise RuntimeError(
                "suffix consumption refused: commit read failed "
                f"({e}); coverage cannot be proven") from e
        seqs = [r[0] for r in rows]
        op_of_seq = {r[0]: r[1] for r in rows}
        try:
            refs = tlstore.pub_refs(seqs)
        except Exception as e:
            raise RuntimeError(
                "suffix consumption refused: pub_refs failed "
                f"({e}); coverage cannot be proven") from e
        try:
            arows = tlstore.artifact_rows(
                [a for seq in seqs for a in refs.get(seq, [])])
        except Exception as e:
            raise RuntimeError(
                "suffix consumption refused: artifact scan failed "
                f"({e}); coverage cannot be proven") from e
        out = []
        n_art = n_bytes = 0
        for seq in seqs:
            for art_id in refs.get(seq, []):
                arow = arows.get(art_id)
                if arow is None:
                    continue
                body = tlstore.read_artifact(art_id,
                                             expect_digest=arow[4])
                n_art += 1
                n_bytes += len(body)
                try:
                    meta = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue  # text artifact, not meta
                if not isinstance(meta, dict):
                    continue
                out.append((seq, op_of_seq.get(seq), meta))
        return out, {"commits": len(seqs), "artifacts": n_art,
                     "bytes": n_bytes}

    # -- retained-view accounting --------------------------------------
    def retained(self):
        """Entry counts for debt/retained reporting (no storage)."""
        self._ensure_all()
        self._ensure_reverse_maps()
        return {"docs": len(self._docs),
                "atoms": sum(len(v) for v in self._docs.values()),
                "leaves": len(self._leaves),
                "parents": len(self._parents),
                "xdoc": len(self._xdoc),
                "retired": len(self._retired),
                "leaf_parent_edges": sum(
                    len(v) for v in self._leaf_parents.values()),
                "atom_leaf_edges": sum(
                    len(v) for v in self._atom_leaves.values()),
                "frontier": self.frontier}
