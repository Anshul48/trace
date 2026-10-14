"""ServingView: pinned composition of segments + delta + tombstones.

Current views are LIVE (flat structures, mutated in place by advance:
O(|Delta|)). advance() returns a NEW view object sharing sealed segments;
the old object freezes to a lightweight retained snapshot (segments +
frozen delta + tombstone node + stat ints) and materializes on demand for
stragglers. Refcounted generations via ViewPool (K cap + lease).
"""

import contextlib
import hashlib
import math
import os
import threading
import time
from collections.abc import Mapping, MutableMapping, Set as AbstractSet
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from tlsys.serving import faults as faults_mod
from tlsys.serving import manifest as manifest_mod
from tlsys.serving import segments as seg_mod
from tlsys.serving.counters import ServeCounters
from tlsys.serving.delta import DeltaSegment
from tlsys.serving.digest import canonical_digest
from tlsys.serving.lexical import (bm25_accumulate,
                                   bm25_accumulate_vectorized,
                                   idf_of, toks)
from tlsys.serving.provisional import serving_config
from tlsys.serving.tombstones import Tombstones, token_adjustments


class StaleViewError(Exception):
    pass


class RewindError(Exception):
    pass


def _triple(birth, epoch, mx):
    return f"{birth}:{epoch}:{mx}" if birth else "empty:0:0"


class ServingView:
    """One pinned view. Use ViewPool to build/advance/retain."""

    _is_gen = False

    def __init__(self, birth, epoch, config=None, counters=None):
        self.birth = birth
        self.epoch = epoch
        self.config = serving_config(config)
        self.counters = counters or ServeCounters()
        self.pin = (birth, epoch, 0, _triple(birth, epoch, 0))
        self.frontier = 0
        self.segments = ()
        self.delta = DeltaSegment(0)
        self.tomb = Tombstones.live_empty()
        self.atoms = {}
        self.holons = {}
        self.doc_atoms = {}
        self.atom_text = {}
        self.retired_aids = set()
        self.df = {}
        self.total_tokens = 0
        self.live_n = 0
        self.ord_atom = {}
        self.ord_holon = {}
        self.aid_of_ord = {}
        self.atom_order = []
        self.doclen_of = {}
        self.atom_leaves = {}
        self.leaf_parents = {}
        self.seg_leaves_cache = {}
        self.seg_parents_cache = {}
        self._atom_overrides = {}  # ord -> f64 (sealed-row re-version)
        self._caches = {}
        self._live = True
        self._snapshot = None
        self._refs = 0
        self._leased_until = 0.0
        self._pool_lock = None  # set by ViewPool; None = standalone
        self.dim = 0
        # Replay-only flag: skip delta appends while rebuilding sealed
        # live state (the replay delta is unconditionally discarded
        # afterwards, so the skipped writes are pure overhead — A17).
        self._no_delta = False

    # -- live-state helpers ----------------------------------------
    def _invalidate(self):
        self._caches = {}

    def _rebuild_derived_from_live(self):
        """Re-derive incremental structures from the live dicts.

        External-mutation path ONLY (facade mappings; product paths
        never mutate): O(N) eager rebuild so every leg stays
        self-consistent. Extends ordinals for new keys (dict order),
        recomputes df/doclen over atoms∩atom_text, appends delta rows
        for uncovered ordinals (resorted), records dense overrides
        for drifted descriptors, appends delta holon versions for
        changed hids, and rebuilds edge maps + seg caches from the
        live holons. Removed keys need no row surgery (legs filter
        by live). Mutation contract: keep atoms/atom_text/descriptor
        consistent (text-only keys stay invisible to legs).
        """
        self._require_live()
        for aid in self.atoms:
            if aid not in self.ord_atom:
                o = len(self.ord_atom)
                self.ord_atom[aid] = o
                self.aid_of_ord[o] = aid
                self.atom_order.append(aid)
        for hid in self.holons:
            if hid not in self.ord_holon:
                self.ord_holon[hid] = len(self.ord_holon)
        df = {}
        doclen_of = {}
        for aid, text in self.atom_text.items():
            if aid not in self.atoms:
                continue
            o = self.ord_atom[aid]
            ts = toks(text)
            doclen_of[o] = len(ts)
            for t in set(ts):
                df[t] = df.get(t, 0) + 1
        self.df = df
        self.doclen_of = doclen_of
        self.live_n = len(doclen_of)
        self.total_tokens = sum(doclen_of.values())
        covered = set()
        for s in self.segments:
            covered.update(s.ord_of_aid.values())
        covered.update(r["ordinal"] for r in self.delta.atom_rows)
        for aid in sorted(self.atoms, key=lambda a: self.ord_atom[a]):
            o = self.ord_atom[aid]
            if o in covered:
                self._override_if_drifted(aid, o)
                if aid in self.atom_text:
                    self._refresh_delta_text(aid, o,
                                             self.atom_text[aid])
                continue
            e = self.atoms[aid]
            text = self.atom_text.get(aid, "")
            vec = np.asarray(e.get("descriptor", []), dtype=np.float64)
            if vec.size and not self.dim:
                self.dim = int(vec.size)
            ts = toks(text)
            tf = {}
            for t in ts:
                tf[t] = tf.get(t, 0) + 1
            self.delta.append_atom(
                {"aid": aid, "ordinal": o, "seq": e.get("seq", 0),
                 "op_id": e.get("op_id"),
                 "doc_id": e.get("doc_id"), "span": e.get("span"),
                 "text_art": e.get("text_art"),
                 "text_digest": e.get("text_digest"),
                 "descriptor": [float(x) for x in vec]},
                text, vec, len(ts), tf)
        self.delta.resort()
        have_h = {(r["hid"], r.get("seq"), r.get("op_id"))
                  for s in self.segments for r in s.holon_rows}
        have_h.update((r["hid"], r.get("seq"), r.get("op_id"))
                      for r in self.delta.holon_rows)
        for hid in sorted(self.holons,
                          key=lambda h: self.ord_holon[h]):
            e = self.holons[hid]
            if (hid, e.get("seq"), e.get("op_id")) in have_h:
                continue
            vec = np.asarray(e.get("descriptor", []), dtype=np.float64)
            self.delta.append_holon(
                {"hid": hid, "ordinal": self.ord_holon[hid],
                 "seq": e.get("seq", 0), "op_id": e.get("op_id"),
                 "members": list(e.get("members", [])),
                 "descriptor": [float(x) for x in vec],
                 "kind": e.get("kind"),
                 "children": list(e.get("children") or [])})
        self.atom_leaves = {}
        self.leaf_parents = {}
        self.seg_leaves_cache = {}
        self.seg_parents_cache = {}
        for hid, e in self.holons.items():
            self._extend_holon_edges(hid, e)
        self._invalidate()

    def _refresh_delta_text(self, aid, o, text):
        """Refresh a mutable delta row's text/tf on drift (external
        mutation only; sealed rows are immutable and stay lenient).
        Makes per-key mutation order-independent: the rebuild
        converges once atoms/atom_text are consistent."""
        for i, r in enumerate(self.delta.atom_rows):
            if r["ordinal"] != o:
                continue
            if self.delta.texts[i] == text:
                return
            _dl, old_tf = self.delta.tf_cache.get(o, (0, {}))
            for t in old_tf:
                run = self.delta.postings.get(t)
                if run is not None:
                    self.delta.postings[t] = [(oo, ff) for oo, ff in run
                                              if oo != o]
                    left = self.delta.df_delta.get(t, 0) - 1
                    if left > 0:
                        self.delta.df_delta[t] = left
                    else:
                        self.delta.df_delta.pop(t, None)
            ts = toks(text)
            tf = {}
            for t in ts:
                tf[t] = tf.get(t, 0) + 1
            self.delta.texts[i] = text
            self.delta.tf_cache[o] = (len(ts), tf)
            self.delta.doclen[o] = len(ts)
            for t, f in tf.items():
                self.delta.postings.setdefault(t, []).append((o, f))
                self.delta.df_delta[t] = \
                    self.delta.df_delta.get(t, 0) + 1
            return

    def _override_if_drifted(self, aid, o):
        """Record a dense override when a covered ordinal's live
        descriptor differs from its row (external mutation only)."""
        live = np.asarray(self.atoms[aid].get("descriptor", []),
                         dtype=np.float64)
        for s in self.segments:
            i = s.idx_of_ord.get(o)
            if i is not None:
                row = s.atom_descriptor_f64(i)
                if row.shape != live.shape or bool(np.any(row != live)):
                    self._atom_overrides[o] = live.copy()
                return
        for i, r in enumerate(self.delta.atom_rows):
            if r["ordinal"] == o:
                d = r.get("descriptor")
                row = (self.delta.vec_rows[i].astype(np.float64)
                       if d is None else np.asarray(d, dtype=np.float64))
                if row.shape != live.shape or bool(np.any(row != live)):
                    self._atom_overrides[o] = live.copy()
                return

    @property
    def triple(self):
        return self.pin[3]

    @property
    def max_seq(self):
        return self.pin[2]

    def _require_live(self):
        if not self._live:
            self.materialize()

    # -- apply path (C1-_build/_build_bm25 equivalent, incremental) --
    def _insert_atom(self, seq, op_id, meta, text):
        from tlsys.serving.dense import build_fp32  # noqa (shape only)
        aid = meta["atom"]
        first = aid not in self.ord_atom
        if first:
            self.ord_atom[aid] = len(self.ord_atom)
            self.aid_of_ord[self.ord_atom[aid]] = aid
            self.atom_order.append(aid)
        o = self.ord_atom[aid]
        entry = {"seq": seq, "op_id": op_id, "doc_id": meta["doc_id"],
                 "span": meta["span"],
                 "text_art": meta["text_artifact"],
                 "text_digest": meta["text_digest"],
                 "descriptor": np.array(meta.get("descriptor", []),
                                        dtype=np.float64)}
        if entry["descriptor"].size:
            if not self.dim:
                self.dim = int(entry["descriptor"].size)
            elif int(entry["descriptor"].size) != self.dim:
                raise ValueError("heterogeneous atom dim (fail closed)")
        retired = meta["doc_id"] in self.tomb
        if not retired and aid in self.atoms:
            # Same-aid re-insert (re-commit; occurrence identity forbids
            # content change): idempotent for live stats/postings/delta
            # (the first row already covers them); the entry is
            # overwritten like C1 (latest seq/op) and doc_atoms appends
            # like C1 (append-always). A vector change is recorded as a
            # dense override; a text change fails closed.
            old = self.atoms[aid]
            if self.atom_text.get(aid) != text:
                raise ValueError(
                    f"aid {aid}: same-id text change (identity violation)")
            old_d = np.asarray(old["descriptor"], dtype=np.float64)
            new_d = np.asarray(entry["descriptor"], dtype=np.float64)
            if old_d.shape != new_d.shape or bool(np.any(old_d != new_d)):
                self._atom_overrides[o] = new_d.copy()
            self.atoms[aid] = entry  # overwrite keeps position (C1)
            self.doc_atoms.setdefault(meta["doc_id"], []).append(aid)
            self._invalidate()
            return
        self.atoms[aid] = entry  # in-place overwrite keeps position
        self.doc_atoms.setdefault(meta["doc_id"], []).append(aid)
        if retired:
            # Late atom of an already-retired doc: excluded like C1's
            # end-of-scan filter (markers apply regardless of position).
            del self.atoms[aid]
            self.doc_atoms.pop(meta["doc_id"], None)
            self.retired_aids.add(aid)
            return
        self.atom_text[aid] = text
        ts = toks(text)
        self.doclen_of[o] = len(ts)
        tf = {}
        for t in ts:
            tf[t] = tf.get(t, 0) + 1
        self.total_tokens += len(ts)
        self.live_n += 1
        for t in tf:
            self.df[t] = self.df.get(t, 0) + 1
        if not self._no_delta:
            self.delta.append_atom(
                {"aid": aid, "ordinal": o, "seq": seq, "op_id": op_id,
                 "doc_id": meta["doc_id"], "span": meta["span"],
                 "text_art": meta["text_artifact"],
                 "text_digest": meta["text_digest"],
                 "descriptor": [float(x) for x in entry["descriptor"]]},
                text, entry["descriptor"], len(ts), tf)

    def _insert_holon(self, seq, op_id, meta):
        hid = meta["holon"]
        first = hid not in self.ord_holon
        if first:
            self.ord_holon[hid] = len(self.ord_holon)
        entry = {"seq": seq, "op_id": op_id,
                 "members": list(meta["members"]),
                 "descriptor": np.array(meta["descriptor"],
                                        dtype=np.float64),
                 "kind": meta.get("kind"),
                 "children": list(meta.get("children") or [])}
        if hid in self.holons:
            self._retract_holon_edges(hid, self.holons[hid])
        if meta.get("kind") is None and hid in self.tomb:
            # Per-doc holon of a retired doc: excluded (C1 end-filter).
            if not self._no_delta:
                self.delta.append_holon(
                    {"hid": hid, "ordinal": self.ord_holon[hid],
                     "seq": seq, "op_id": op_id,
                     "members": list(entry["members"]),
                     "descriptor": [float(x)
                                    for x in entry["descriptor"]],
                     "kind": None, "children": []})
            return
        self.holons[hid] = entry
        self._extend_holon_edges(hid, entry)
        if not self._no_delta:
            self.delta.append_holon(
                {"hid": hid, "ordinal": self.ord_holon[hid], "seq": seq,
                 "op_id": op_id, "members": list(entry["members"]),
                 "descriptor": [float(x) for x in entry["descriptor"]],
                 "kind": entry["kind"],
                 "children": list(entry["children"])})

    def _retract_holon_edges(self, hid, old):
        if old.get("kind") == "seg-leaf":
            for aid in old["members"]:
                lst = self.atom_leaves.get(aid)
                if lst and hid in lst:
                    lst.remove(hid)
                    if not lst:
                        del self.atom_leaves[aid]
            self.seg_leaves_cache.pop(hid, None)
        elif old.get("kind") == "seg-parent":
            for child in old.get("children", []):
                lst = self.leaf_parents.get(child)
                if lst and hid in lst:
                    lst.remove(hid)
                    if not lst:
                        del self.leaf_parents[child]
            self.seg_parents_cache.pop(hid, None)

    def _extend_holon_edges(self, hid, entry):
        if entry.get("kind") == "seg-leaf":
            for aid in entry["members"]:
                self.atom_leaves.setdefault(aid, []).append(hid)
            self.seg_leaves_cache[hid] = entry
        elif entry.get("kind") == "seg-parent":
            for child in entry.get("children", []):
                self.leaf_parents.setdefault(child, []).append(hid)
            self.seg_parents_cache[hid] = entry

    def _retire_docs(self, docs):
        new = [d for d in docs if d not in self.tomb]
        if not new:
            return
        self.tomb.add_live(new)
        for doc in new:
            aids = self.doc_atoms.pop(doc, [])
            texts = []
            for aid in aids:
                e = self.atoms.pop(aid, None)
                if e is None:
                    continue
                self.retired_aids.add(aid)
                t = self.atom_text.pop(aid, None)
                if t is not None:
                    texts.append(t)
            total, dfmap = token_adjustments(texts)
            self.total_tokens -= total
            self.live_n -= len(texts)
            for t, c in dfmap.items():
                left = self.df.get(t, 0) - c
                if left > 0:
                    self.df[t] = left
                else:
                    self.df.pop(t, None)
            ent = self.holons.get(doc)
            if ent is not None and ent.get("kind") is None:
                self._retract_holon_edges(doc, ent)
                del self.holons[doc]
        self._invalidate()

    def apply_range(self, rows, metas, texts):
        """Apply scan_range output (C1 scan order). O(range)."""
        for seq, op_id, _art, kind, meta in metas:
            if kind == "retirement":
                doc = meta["retirement"]["doc"]
                self.delta.retired_docs.add(doc)
                self._retire_docs([doc])
            elif kind == "atom":
                self._insert_atom(seq, op_id, meta,
                                  texts[meta["atom"]])
            elif kind == "holon":
                self._insert_holon(seq, op_id, meta)
        for r in rows:
            self.delta.note_commit(r[1])
        self._invalidate()

    # -- legs --------------------------------------------------------
    def _postings_of(self, term):
        for s in self.segments:
            o_arr, f_arr = s.lex.postings_of(term)
            for o, f in zip(o_arr.tolist(), f_arr.tolist()):
                yield int(o), int(f)
        for o, f in self.delta.postings.get(term, ()):
            yield int(o), int(f)

    def _columnar_for_bm25(self):
        """Cached ordinal-indexed columns for the BM25 leg (Stage B).

        live_ord/doclen/aids over 0..len(ord_atom); seal-invariant
        (live-state-derived), cached under _caches like the dense
        assembly (same invalidation points). Retired ordinals read
        doclen 0 and live False (never consumed: the live mask
        filters first, exactly like the scalar leg).
        """
        hit = self._caches.get("bm25_cols")
        if hit is not None:
            return hit
        self._require_live()
        n_ord = len(self.ord_atom)
        live = np.zeros((n_ord,), dtype=bool)
        doclen = np.zeros((n_ord,), dtype=np.int64)
        aids = [None] * n_ord
        for aid in self.atoms:
            o = self.ord_atom[aid]
            live[o] = True
            aids[o] = aid
        for o, dl in self.doclen_of.items():
            doclen[int(o)] = int(dl)
        for o, aid in self.aid_of_ord.items():
            if aids[int(o)] is None:
                aids[int(o)] = aid
        hit = {"live_ord": live, "doclen": doclen, "aids": aids}
        self._caches["bm25_cols"] = hit
        return hit

    def _bm25_runs_of(self, term):
        """Per-term posting runs in legacy accumulation order.

        Segments in view order (zero-copy slices), then the delta
        overlay run (small arrays; the overlay is flush-bounded).
        Same run sequence as _postings_of, so the vectorized kernel
        accumulates in the identical op order (bitwise).
        """
        runs = []
        for s in self.segments:
            o_arr, f_arr = s.lex.postings_of(term)
            if len(o_arr):
                runs.append((o_arr, f_arr))
        run = self.delta.postings.get(term)
        if run:
            runs.append((
                np.array([p[0] for p in run], dtype=np.int64),
                np.array([p[1] for p in run], dtype=np.int64)))
        return runs

    def bm25(self, query):
        from tlsys.serving.lexical import K1, B  # noqa (doc anchor)
        self._require_live()
        n = max(1, self.live_n)
        avgdl = self.total_tokens / n
        terms = sorted(set(toks(query)))
        cols = self._columnar_for_bm25()
        return bm25_accumulate_vectorized(
            terms, self.df.get, n, avgdl, self._bm25_runs_of,
            cols["live_ord"], cols["doclen"], cols["aids"],
            self.counters)

    def bm25_fullscan(self, query):
        """Reference full-scan oracle (C1's implementation, live dicts)."""
        from tlsys.serving.lexical import K1, B
        self._require_live()
        qf = {}
        for t in toks(query):
            qf[t] = qf.get(t, 0) + 1
        idf = {t: idf_of(max(1, self.live_n), c)
               for t, c in self.df.items()}
        avgdl = self.total_tokens / max(1, self.live_n)
        out = {}
        for aid, text in self.atom_text.items():
            dl = len(toks(text))
            tf = {}
            for t in toks(text):
                if t in qf:
                    tf[t] = tf.get(t, 0) + 1
            if not tf:
                continue
            s = 0.0
            for t, f in tf.items():
                num = f * (K1 + 1)
                den = f + K1 * (1 - B + B * dl / avgdl)
                s += idf.get(t, 0.0) * num / den
            out[aid] = s
        return out

    def _live_atom_ordinals(self):
        self._require_live()
        return sorted(o for o, aid in self.aid_of_ord.items()
                      if aid in self.atoms)

    def _dense_atoms_assembled(self):
        hit = self._caches.get("dense_atoms")
        if hit is not None:
            return hit
        self._require_live()
        ords = self._live_atom_ordinals()
        pos_of = {}
        for s in self.segments:
            for o, i in s.idx_of_ord.items():
                pos_of[o] = ("seg", s, i)
        for i, r in enumerate(self.delta.atom_rows):
            pos_of[r["ordinal"]] = ("delta", None, i)
        ids = [self.aid_of_ord[o] for o in ords]
        mat = np.empty((len(ords), self.dim or 0))
        for j, o in enumerate(ords):
            ov = self._atom_overrides.get(o)
            if ov is not None:
                mat[j] = ov
                continue
            kind, s, i = pos_of[o]
            if kind == "seg":
                mat[j] = s.atom_descriptor_f64(i)
            else:
                d = self.delta.atom_rows[i].get("descriptor")
                if d is None:
                    mat[j] = self.delta.vec_rows[i].astype(np.float64)
                else:
                    mat[j] = np.asarray(d, dtype=np.float64)
        norms = np.linalg.norm(mat, axis=1) if len(ords) else np.empty((0,))
        norms[norms == 0.0] = 1.0
        hit = (ids, mat, norms)
        self._caches["dense_atoms"] = hit
        return hit

    def dense_atoms_full(self, qvec):
        from tlsys.query import _dense_rank
        ids, mat, norms = self._dense_atoms_assembled()
        self.counters.record(holon_rows_scored=0,
                             dense_rescore_rows=len(ids))
        return _dense_rank(qvec, ids, mat, norms)

    def dense_atoms_topk(self, qvec, k):
        """Certified top-k (E2 protocol) over live rows, no full assembly:
        per-segment FP32 scans (views) + delta + override parts."""
        from tlsys.serving.dense import certified_topk
        self._require_live()
        if self.live_n == 0:
            return []
        m = self.config["shortlist_margin_m"]
        eps = self.config["dense_eps"]
        parts = []
        for s in self.segments:
            live_pos = [i for i, r in enumerate(s.atom_rows)
                        if r["aid"] in self.atoms
                        and r["ordinal"] not in self._atom_overrides]
            if not live_pos:
                continue
            mat = s.mat32[np.array(live_pos)]
            ids = [s.atom_rows[i]["aid"] for i in live_pos]
            norms = s.norms64[np.array(live_pos)]
            ov = {}
            for new_j, i in enumerate(live_pos):
                if i in s.overrides:
                    ov[new_j] = s.overrides[i]
            parts.append((ids, mat, norms, ov,
                          [s.atom_rows[i]["ordinal"] for i in live_pos]))
        d_live = [(i, r) for i, r in enumerate(self.delta.atom_rows)
                  if r["aid"] in self.atoms
                  and r["ordinal"] not in self._atom_overrides]
        if d_live:
            mat = np.stack(
                [self.delta.vec_rows[i] for i, _r in d_live]).astype(
                    np.float32)
            ids = [r["aid"] for _i, r in d_live]
            mat64 = mat.astype(np.float64)
            norms = np.linalg.norm(mat64, axis=1)
            norms[norms == 0.0] = 1.0
            ov = {}
            for new_j, (i, _r) in enumerate(d_live):
                if i in self.delta.overrides:
                    ov[new_j] = self.delta.overrides[i]
            parts.append((ids, mat, norms, ov,
                          [r["ordinal"] for _i, r in d_live]))
        if self._atom_overrides:
            oids = sorted(self._atom_overrides)
            rows = [np.asarray(self._atom_overrides[o]) for o in oids]
            mat = np.stack(rows).astype(np.float32)
            mat64 = np.stack(rows).astype(np.float64)
            norms = np.linalg.norm(mat64, axis=1)
            norms[norms == 0.0] = 1.0
            parts.append(([self.aid_of_ord[o] for o in oids], mat, norms,
                          {j: rows[j] for j in range(len(rows))}, oids))
        # Concatenate parts in global ordinal order (parts may interleave
        # only via overrides, which sort correctly below).
        rows = []
        for ids, mat, norms, ov, ords in parts:
            for j in range(len(ids)):
                rows.append((ords[j], ids[j], mat[j], norms[j],
                             ov.get(j)))
        rows.sort(key=lambda r: r[0])
        cids = [r[1] for r in rows]
        cmat = np.stack([r[2] for r in rows]).astype(np.float32) \
            if rows else np.empty((0, self.dim or 0), np.float32)
        cnorms = np.array([r[3] for r in rows]) if rows else np.empty((0,))
        cov = {j: r[4] for j, r in enumerate(rows) if r[4] is not None}
        out, cert = certified_topk(qvec, k, cids, cmat, cnorms, cov, m=m,
                                   eps=eps, counters=self.counters)
        self._last_cert = cert
        return out

    def _dense_holons_assembled(self):
        hit = self._caches.get("dense_holons")
        if hit is not None:
            return hit
        self._require_live()
        ids = list(self.holons.keys())
        mat = (np.stack([np.asarray(self.holons[i]["descriptor"],
                                    dtype=np.float64) for i in ids])
               if ids else np.empty((0, 0)))
        norms = (np.linalg.norm(mat, axis=1)
                 if ids else np.empty((0,)))
        norms[norms == 0.0] = 1.0
        hit = (ids, mat, norms)
        self._caches["dense_holons"] = hit
        return hit

    def dense_holons_full(self, qvec):
        from tlsys.query import _dense_rank
        ids, mat, norms = self._dense_holons_assembled()
        self.counters.record(holon_rows_scored=len(ids))
        return _dense_rank(qvec, ids, mat, norms)

    # -- facade-shaped accessors (live) --------------------------------
    @property
    def seg_leaves(self):
        self._require_live()
        return dict(self.seg_leaves_cache)

    @property
    def seg_parents(self):
        self._require_live()
        return dict(self.seg_parents_cache)

    @property
    def retired_docs(self):
        if self._live:
            return sorted(self.tomb.materialize())
        return sorted(self._snapshot["tomb"].materialize())

    @property
    def retired_atoms(self):
        self._require_live()
        return len(self.retired_aids)

    @property
    def retired_aids_set(self):
        self._require_live()
        return set(self.retired_aids)

    @property
    def avgdl(self):
        n = max(1, self.live_n if self._live
                else self._snapshot["live_n"])
        total = self.total_tokens if self._live \
            else self._snapshot["total"]
        return total / n

    def postings_live(self):
        hit = self._caches.get("postings")
        if hit is not None:
            return hit
        self._require_live()
        post = {}
        collect = {}
        for s in self.segments:
            for i, t in enumerate(s.lex.terms):
                a, b = int(s.lex.offsets[i]), int(s.lex.offsets[i + 1])
                for o, f in zip(s.lex.post_ord[a:b].tolist(),
                                s.lex.post_tf[a:b].tolist()):
                    aid = s.aid_of_ord.get(int(o))
                    if aid in self.atoms:
                        collect.setdefault(t, []).append((aid, int(f)))
        for t, run in self.delta.postings.items():
            for o, f in run:
                aid = self.aid_of_ord.get(int(o))
                if aid in self.atoms:
                    collect.setdefault(t, []).append((aid, int(f)))
        for t, run in collect.items():
            run.sort(key=lambda p: self.ord_atom[p[0]])
            post[t] = run
        # Drop terms with no live rows (C1 shape: df over live only).
        post = {t: run for t, run in post.items() if run}
        self._caches["postings"] = post
        return post

    def idf_live(self):
        hit = self._caches.get("idf")
        if hit is None:
            self._require_live()
            n = max(1, self.live_n)
            hit = {t: idf_of(n, c) for t, c in self.df.items()}
            self._caches["idf"] = hit
        return hit

    def doc_len_live(self):
        hit = self._caches.get("doc_len")
        if hit is None:
            self._require_live()
            hit = {self.aid_of_ord[o]: dl
                   for o, dl in self.doclen_of.items()
                   if self.aid_of_ord.get(o) in self.atoms}
            self._caches["doc_len"] = hit
        return hit

    def live_atom_set(self):
        hit = self._caches.get("live_set")
        if hit is None:
            self._require_live()
            hit = frozenset(self.atoms.keys())
            self._caches["live_set"] = hit
        return hit

    def nomination_maps(self):
        self._require_live()
        return dict(self.atom_leaves), dict(self.leaf_parents)

    def canonical_digest(self):
        self._require_live()
        return canonical_digest(self.atoms, self.holons, self.atom_text,
                                self.tomb.materialize(), self.retired_aids,
                                self.live_n, self.total_tokens, self.df)

    # -- retention -----------------------------------------------------
    def freeze(self):
        """Convert in place to a retained snapshot (ownership of live
        dicts moves to the caller's new view)."""
        if not self._live:
            return self
        self.delta.freeze()
        self._snapshot = {
            "pin": self.pin, "segments": self.segments,
            "delta": self.delta, "tomb": self.tomb.snapshot(),
            "live_n": self.live_n, "total": self.total_tokens,
            "dim": self.dim,
            "atom_overrides": dict(self._atom_overrides)}
        self._live = False
        self.atoms = None
        self.holons = None
        self.doc_atoms = None
        self.atom_text = None
        self.retired_aids = None
        self.df = None
        self.ord_atom = None
        self.ord_holon = None
        self.aid_of_ord = None
        self.atom_order = None
        self.doclen_of = None
        self.atom_leaves = None
        self.leaf_parents = None
        self.seg_leaves_cache = None
        self.seg_parents_cache = None
        self._atom_overrides = None
        self._caches = {}
        return self

    def materialize(self):
        """Rebuild live state from the retained snapshot (stragglers;
        O(N), rare, counted)."""
        if self._live:
            return self
        snap = self._snapshot
        t0 = time.time()
        tomb_docs = snap["tomb"].materialize()
        atoms = {}
        holons = {}
        doc_atoms = {}
        atom_text = {}
        retired_aids = set()
        ord_atom = {}
        ord_holon = {}
        aid_of_ord = {}
        atom_order = []
        doclen_of = {}
        df = {}
        total = 0
        live_n = 0
        # Replay in global ordinal order (== original insertion order;
        # overwrites keep first position, matching C1 dict semantics).
        arows = []
        for s in snap["segments"]:
            for i, r in enumerate(s.atom_rows):
                arows.append((r["ordinal"], "seg", s, i, r))
        for i, r in enumerate(snap["delta"].atom_rows):
            arows.append((r["ordinal"], "delta", None, i, r))
        arows.sort(key=lambda x: x[0])
        texts_of = {}
        for s in snap["segments"]:
            for r, t in zip(s.atom_rows, s.texts):
                texts_of[r["aid"]] = t
        for r, t in zip(snap["delta"].atom_rows, snap["delta"].texts):
            texts_of[r["aid"]] = t
        for o, kind, s, i, r in arows:
            aid = r["aid"]
            if kind == "seg":
                d = s.atom_descriptor_f64(i)
            else:
                d = np.asarray(r.get("descriptor"), dtype=np.float64)
            ov = snap["atom_overrides"].get(o)
            if ov is not None:
                d = np.asarray(ov, dtype=np.float64)
            entry = {"seq": r["seq"], "op_id": r["op_id"],
                     "doc_id": r["doc_id"], "span": r["span"],
                     "text_art": r["text_art"],
                     "text_digest": r["text_digest"], "descriptor": d}
            if aid in ord_atom:
                # Re-commit row: last content wins at the first
                # position (live _insert_atom overwrites); doc_atoms
                # appends like C1. Stats were counted once already.
                if r["doc_id"] in tomb_docs:
                    retired_aids.add(aid)
                elif aid in atoms:
                    atoms[aid] = entry
                    atom_text[aid] = texts_of[aid]
                    doc_atoms.setdefault(r["doc_id"], []).append(aid)
                else:
                    # Defensive (impossible: same aid binds same doc):
                    # treat as a fresh live insert minus ordinals.
                    atoms[aid] = entry
                    atom_text[aid] = texts_of[aid]
                    doc_atoms.setdefault(r["doc_id"], []).append(aid)
                    ts = toks(texts_of[aid])
                    doclen_of[o] = len(ts)
                    total += len(ts)
                    live_n += 1
                    for term in set(ts):
                        df[term] = df.get(term, 0) + 1
                continue
            ord_atom[aid] = o
            aid_of_ord[o] = aid
            atom_order.append(aid)
            doc_atoms.setdefault(r["doc_id"], []).append(aid)
            if r["doc_id"] in tomb_docs:
                retired_aids.add(aid)
                continue
            atoms[aid] = entry
            t = texts_of[aid]
            atom_text[aid] = t
            ts = toks(t)
            doclen_of[o] = len(ts)
            total += len(ts)
            live_n += 1
            for term in set(ts):
                df[term] = df.get(term, 0) + 1
        # NOTE: retired docs' doc_atoms entries are dropped (C1 end-filter).
        for doc in tomb_docs:
            doc_atoms.pop(doc, None)
        hrows = []
        for s in snap["segments"]:
            hrows.extend(s.holon_rows)
        hrows.extend(snap["delta"].holon_rows)
        hrows.sort(key=lambda r: r["ordinal"])
        atom_leaves = {}
        leaf_parents = {}
        seg_l = {}
        seg_p = {}
        for r in hrows:
            hid = r["hid"]
            if hid not in ord_holon:
                ord_holon[hid] = r["ordinal"]
            entry = {"seq": r["seq"], "op_id": r["op_id"],
                     "members": list(r["members"]),
                     "descriptor": np.asarray(r["descriptor"],
                                              dtype=np.float64),
                     "kind": r.get("kind"),
                     "children": list(r.get("children") or [])}
            if entry["kind"] is None and hid in tomb_docs:
                continue
            if hid in holons:  # supersession: retract old edges first
                old = holons[hid]
                if old.get("kind") == "seg-leaf":
                    for a in old["members"]:
                        lst = atom_leaves.get(a)
                        if lst and hid in lst:
                            lst.remove(hid)
                            if not lst:
                                del atom_leaves[a]
                    seg_l.pop(hid, None)
                elif old.get("kind") == "seg-parent":
                    for c in old.get("children", []):
                        lst = leaf_parents.get(c)
                        if lst and hid in lst:
                            lst.remove(hid)
                            if not lst:
                                del leaf_parents[c]
                    seg_p.pop(hid, None)
            holons[hid] = entry
            if entry.get("kind") == "seg-leaf":
                for a in entry["members"]:
                    atom_leaves.setdefault(a, []).append(hid)
                seg_l[hid] = entry
            elif entry.get("kind") == "seg-parent":
                for c in entry.get("children", []):
                    leaf_parents.setdefault(c, []).append(hid)
                seg_p[hid] = entry
        self.atoms = atoms
        self.holons = holons
        self.doc_atoms = doc_atoms
        self.atom_text = atom_text
        self.retired_aids = retired_aids
        self.df = df
        self.total_tokens = total
        self.live_n = live_n
        self.ord_atom = ord_atom
        self.ord_holon = ord_holon
        self.aid_of_ord = aid_of_ord
        self.atom_order = atom_order
        self.doclen_of = doclen_of
        self.atom_leaves = atom_leaves
        self.leaf_parents = leaf_parents
        self.seg_leaves_cache = seg_l
        self.seg_parents_cache = seg_p
        self._atom_overrides = dict(snap["atom_overrides"])
        self.dim = snap["dim"]
        # Rebuild segments/delta handles (shared refs, read-only use).
        self.segments = snap["segments"]
        self.delta = snap["delta"]
        live_tomb = Tombstones.live_empty()
        for d in tomb_docs:
            live_tomb._live.add(d)
        self.tomb = live_tomb
        self._live = True
        self.counters.record(straggler_rebuilds=1)
        self._materialize_ms = (time.time() - t0) * 1000.0
        return self


# -- Generation-backed views (Closure S, gen v2) ---------------------
# A GenerationView serves a persisted generation base (immutable,
# indexed GenerationReader) plus a small unpublished-suffix overlay
# (O(Delta) dicts). Merged mappings below provide the C1-ordered
# read surface WITHOUT eager corpus-sized Python dict rebuilds;
# overlay mutations route to the O(Delta) stores. Base ordinals are
# 0..base_n; overlay ordinals continue at base_n (same for holons).

_GEN_OV_ATTRS = (
    "ov_atoms", "ov_holons", "ov_atom_text", "ov_doc_atoms", "ov_df",
    "ov_doclen", "ov_ord_atom", "ov_aid_of_ord", "ov_ord_holon",
    "ov_atom_leaves", "ov_leaf_parents", "ov_retired_aids",
    "ov_retired_hids", "ov_doc_gone", "ov_text_gone", "ov_al_new",
    "ov_al_gone", "ov_lp_new", "ov_lp_gone", "ov_atom_overrides",
    "ov_seg_leaves", "ov_seg_parents", "ov_seg_leaves_gone",
    "ov_seg_parents_gone",
)

_GEN_OV_INTS = ("ov_df_nonzero", "ov_holon_live")


class _GenOrdAtom(Mapping):
    """aid -> ordinal over base + overlay-new aids (C1 order)."""

    def __init__(self, view):
        self._v = view

    def __getitem__(self, aid):
        o = self._v.ov_ord_atom.get(aid)
        if o is not None:
            return o
        return self._v._reader.ord_of_aid(aid)

    def __contains__(self, aid):
        return aid in self._v.ov_ord_atom or \
            self._v._reader.has_aid(aid)

    def __len__(self):
        return self._v._base_n + len(self._v.ov_ord_atom)

    def __iter__(self):
        yield from self._v._reader.aids.tolist()
        ov = self._v.ov_ord_atom
        for aid in sorted(ov, key=lambda a: ov[a]):
            yield aid


class _GenAidOfOrd(Mapping):
    """ordinal -> aid over 0..M (base then overlay)."""

    def __init__(self, view):
        self._v = view

    def __getitem__(self, o):
        o = int(o)
        if o < 0 or o >= len(self):
            raise KeyError(o)
        if o < self._v._base_n:
            return self._v._reader.aid_of_ord(o)
        return self._v.ov_aid_of_ord[o]

    def __contains__(self, o):
        try:
            o = int(o)
        except (TypeError, ValueError):
            return False
        return 0 <= o < len(self)

    def __len__(self):
        return self._v._base_n + len(self._v.ov_ord_atom)

    def __iter__(self):
        return iter(range(len(self)))


class _GenAtoms(MutableMapping):
    """Live aid -> C1 entry (overlay wins, base indexed, C1 order)."""

    def __init__(self, view):
        self._v = view

    def _live(self, aid):
        v = self._v
        if aid in v.ov_atoms:
            return True
        if aid in v.ov_retired_aids:
            return False
        try:
            o = v._reader.ord_of_aid(aid)
        except KeyError:
            return False
        return bool(v._reader.live[int(o)])

    def __getitem__(self, aid):
        v = self._v
        if aid in v.ov_atoms:
            return v.ov_atoms[aid]
        if aid in v.ov_retired_aids:
            raise KeyError(aid)
        try:
            o = v._reader.ord_of_aid(aid)
        except KeyError:
            raise KeyError(aid)
        if not v._reader.live[int(o)]:
            raise KeyError(aid)
        return v._reader.atom_entry(int(o))

    def __contains__(self, aid):
        try:
            return self._live(aid)
        except (TypeError, ValueError):
            return False

    def __len__(self):
        return int(self._v.live_n)

    def __iter__(self):
        v = self._v
        n = v._base_n + len(v.ov_ord_atom)
        for o in range(n):
            aid = v._reader.aids[o] if o < v._base_n \
                else v.ov_aid_of_ord[o]
            if self._live(aid):
                yield aid

    def __setitem__(self, aid, value):
        # External mutation only (product paths never mutate):
        # overlay wins; the caller rebuilds derived state.
        self._v.ov_atoms[aid] = value

    def __delitem__(self, aid):
        v = self._v
        try:
            o = v._reader.ord_of_aid(aid)
            base_live = bool(v._reader.live[int(o)])
        except KeyError:
            base_live = False
        existed = aid in v.ov_atoms or (
            base_live and aid not in v.ov_retired_aids)
        if not existed:
            raise KeyError(aid)
        v.ov_atoms.pop(aid, None)
        if v._reader.has_aid(aid):
            v.ov_retired_aids.add(aid)


class _GenHolons(MutableMapping):
    """Live hid -> C1 entry (overlay wins, base indexed, hord order)."""

    def __init__(self, view):
        self._v = view

    def _live(self, hid):
        v = self._v
        if hid in v.ov_holons:
            return True
        if hid in v.ov_retired_hids:
            return False
        return v._reader.has_hid(hid)

    def __getitem__(self, hid):
        v = self._v
        if hid in v.ov_holons:
            return v.ov_holons[hid]
        if hid in v.ov_retired_hids or not v._reader.has_hid(hid):
            raise KeyError(hid)
        return v._reader.holon_entry(hid)

    def __contains__(self, hid):
        try:
            return self._live(hid)
        except (TypeError, ValueError):
            return False

    def __len__(self):
        return int(self._v.ov_holon_live)

    def __iter__(self):
        v = self._v
        for hid in v._reader.hids.tolist():
            if self._live(hid):
                yield hid
        base = set(v._reader.hids.tolist())
        ov = {h: v.ov_ord_holon[h] for h in v.ov_holons
              if h not in base and h in v.ov_ord_holon}
        for hid in sorted(ov, key=lambda h: ov[h]):
            yield hid

    def __setitem__(self, hid, value):
        self._v.ov_holons[hid] = value
        self._v.ov_retired_hids.discard(hid)

    def __delitem__(self, hid):
        v = self._v
        existed = hid in v.ov_holons or (
            v._reader.has_hid(hid) and hid not in v.ov_retired_hids)
        if not existed:
            raise KeyError(hid)
        v.ov_holons.pop(hid, None)
        if v._reader.has_hid(hid):
            v.ov_retired_hids.add(hid)


class _GenAtomText(MutableMapping):
    """Live aid -> text for atoms∩texts (base verified, C1 order)."""

    def __init__(self, view):
        self._v = view

    def _has(self, aid):
        v = self._v
        if aid not in v.atoms:
            return False
        if aid in v.ov_text_gone:
            return False
        if aid in v.ov_atom_text:
            return True
        return v._reader.has_aid(aid)

    def __getitem__(self, aid):
        v = self._v
        if aid not in v.atoms or aid in v.ov_text_gone:
            raise KeyError(aid)
        if aid in v.ov_atom_text:
            return v.ov_atom_text[aid]
        try:
            o = v._reader.ord_of_aid(aid)
        except KeyError:
            raise KeyError(aid)
        return v._reader.text_of_ord(int(o))

    def __contains__(self, aid):
        try:
            return self._has(aid)
        except (TypeError, ValueError):
            return False

    def __len__(self):
        hit = self._v._caches.get("atom_text_len")
        if hit is not None:
            return hit
        n = sum(1 for _ in self)
        self._v._caches["atom_text_len"] = n
        return n

    def __iter__(self):
        for aid in self._v.atoms:
            if self._has(aid):
                yield aid

    def __setitem__(self, aid, value):
        self._v.ov_atom_text[aid] = value
        self._v.ov_text_gone.discard(aid)

    def __delitem__(self, aid):
        v = self._v
        if aid not in v.atoms:
            raise KeyError(aid)
        if aid not in v.ov_atom_text and not v._reader.has_aid(aid):
            raise KeyError(aid)
        v.ov_atom_text.pop(aid, None)
        if v._reader.has_aid(aid):
            v.ov_text_gone.add(aid)


class _GenDocAtoms(MutableMapping):
    """doc -> [aids] (base runs + overlay appends, first-seen order)."""

    def __init__(self, view):
        self._v = view

    def _docs_live(self, doc):
        v = self._v
        if doc in v.ov_doc_gone or doc in v.tomb:
            return False
        return doc in v._reader._docs_sorted_list or \
            doc in v.ov_doc_atoms

    def __getitem__(self, doc):
        v = self._v
        if doc in v.ov_doc_gone or doc in v.tomb:
            raise KeyError(doc)
        out = []
        if doc in v._reader._docs_sorted_list:
            for o in v._reader.doc_ordinals(doc).tolist():
                out.append(v._reader.aids[int(o)])
        if doc in v.ov_doc_atoms:
            out.extend(v.ov_doc_atoms[doc])
        if not out and doc not in v._reader._docs_sorted_list \
                and doc not in v.ov_doc_atoms:
            raise KeyError(doc)
        return out

    def __contains__(self, doc):
        try:
            return self._docs_live(doc)
        except (TypeError, ValueError):
            return False

    def __len__(self):
        v = self._v
        n = 0
        for d in v._reader._docs:
            if d not in v.ov_doc_gone and d not in v.tomb:
                n += 1
        base = set(v._reader._docs)
        for d in v.ov_doc_atoms:
            if d not in base and d not in v.ov_doc_gone \
                    and d not in v.tomb:
                n += 1
        return n

    def __iter__(self):
        v = self._v
        for d in v._reader._docs:
            if d not in v.ov_doc_gone and d not in v.tomb:
                yield d
        base = set(v._reader._docs)
        for d in v.ov_doc_atoms:
            if d not in base and d not in v.ov_doc_gone \
                    and d not in v.tomb:
                yield d

    def __setitem__(self, doc, value):
        # Replacement semantics (dict set replaces the run).
        self._v.ov_doc_atoms[doc] = list(value)
        self._v.ov_doc_gone.discard(doc)

    def __delitem__(self, doc):
        v = self._v
        if doc not in self:
            raise KeyError(doc)
        v.ov_doc_atoms.pop(doc, None)
        if doc in v._reader._docs_sorted_list:
            v.ov_doc_gone.add(doc)


class _GenDf(Mapping):
    """term -> merged live df (base + overlay adjustments)."""

    def __init__(self, view):
        self._v = view

    def _merged(self, term):
        v = self._v
        base = v._reader.df_of(term)
        return (base if base is not None else 0) + \
            v.ov_df.get(term, 0)

    def __getitem__(self, term):
        if self._merged(term) <= 0:
            raise KeyError(term)
        return self._merged(term)

    def __contains__(self, term):
        try:
            return self._merged(term) > 0
        except (TypeError, ValueError):
            return False

    def __len__(self):
        return int(self._v.ov_df_nonzero)

    def __iter__(self):
        v = self._v
        terms = set(v._reader._terms) | set(v.ov_df)
        for t in sorted(terms):
            if self._merged(t) > 0:
                yield t


class _GenDoclen(Mapping):
    """ordinal -> doclen over 0..M (overlay wins, base indexed)."""

    def __init__(self, view):
        self._v = view

    def __getitem__(self, o):
        v = self._v
        try:
            o = int(o)
        except (TypeError, ValueError):
            raise KeyError(o)
        if o in v.ov_doclen:
            return int(v.ov_doclen[o])
        if 0 <= o < v._base_n:
            return int(v._reader.doclen[o])
        raise KeyError(o)

    def __contains__(self, o):
        try:
            o = int(o)
        except (TypeError, ValueError):
            return False
        return o in self._v.ov_doclen or 0 <= o < self._v._base_n

    def __len__(self):
        return self._v._base_n + len(self._v.ov_ord_atom)

    def __iter__(self):
        return iter(range(len(self)))


class _GenOrdHolon(Mapping):
    """hid -> hord over base + overlay-new hids."""

    def __init__(self, view):
        self._v = view

    def __getitem__(self, hid):
        if hid in self._v.ov_ord_holon:
            return self._v.ov_ord_holon[hid]
        return self._v._reader.hord_of_hid(hid)

    def __contains__(self, hid):
        return hid in self._v.ov_ord_holon or \
            self._v._reader.has_hid(hid)

    def __len__(self):
        return self._v._base_h + len(self._v.ov_ord_holon)

    def __iter__(self):
        yield from self._v._reader.hids.tolist()
        ov = self._v.ov_ord_holon
        for hid in sorted(ov, key=lambda h: ov[h]):
            yield hid


class _GenEdges(Mapping):
    """Merged hierarchy reverse index (replacements + base CSR)."""

    def __init__(self, view, kind):
        self._v = view
        self._kind = kind  # "al" (aid->leaves) or "lp" (leaf->parents)

    def _stores(self):
        v = self._v
        if self._kind == "al":
            return (v.ov_atom_leaves, v.ov_al_new, v.ov_al_gone,
                    v._reader._eal_list)
        return (v.ov_leaf_parents, v.ov_lp_new, v.ov_lp_gone,
                v._reader._elp_list)

    def _base_list(self, key):
        if self._kind == "al":
            return self._v._reader.leaves_of(key)
        return self._v._reader.parents_of(key)

    def __getitem__(self, key):
        ov, _new, gone, base_keys = self._stores()
        if key in ov:
            return list(ov[key])
        if key in gone:
            raise KeyError(key)
        import bisect as _bisect
        i = _bisect.bisect_left(base_keys, key)
        if i < len(base_keys) and base_keys[i] == key:
            return self._base_list(key)
        raise KeyError(key)

    def __contains__(self, key):
        try:
            ov, _new, gone, base_keys = self._stores()
            if key in ov:
                return True
            if key in gone:
                return False
            import bisect as _bisect
            i = _bisect.bisect_left(base_keys, key)
            return i < len(base_keys) and base_keys[i] == key
        except (TypeError, ValueError):
            return False

    def __len__(self):
        ov, new, gone, base_keys = self._stores()
        return len(base_keys) + len(new) - len(gone)

    def __iter__(self):
        ov, new, gone, base_keys = self._stores()
        base_set = set(base_keys)
        for k in base_keys:
            if k not in gone:
                yield k
        for k in ov:
            if k not in base_set and k not in gone:
                yield k


class _GenRetiredAids(AbstractSet):
    """Merged retired aids (base frozenset + overlay set)."""

    def __init__(self, view):
        self._v = view

    def _base(self):
        r = self._v._reader
        hit = getattr(r, "_retired_aids_cache", None)
        if hit is None:
            hit = frozenset(r.retired_aids())
            r._retired_aids_cache = hit
        return hit

    def __contains__(self, aid):
        return aid in self._v.ov_retired_aids or aid in self._base()

    def __iter__(self):
        yield from self._base()
        base = self._base()
        for aid in self._v.ov_retired_aids:
            if aid not in base:
                yield aid

    def __len__(self):
        base = self._base()
        return len(base) + sum(
            1 for aid in self._v.ov_retired_aids if aid not in base)


class GenerationView(ServingView):
    """Pinned view over a persisted generation + suffix overlay.

    Base state serves from the immutable indexed GenerationReader
    (no eager dicts, no sealed replay); the unpublished suffix
    (seqs above the generation frontier) applies to small overlay
    stores through the C1-equivalent insert/retire paths. Advance
    shares the reader by reference and moves overlay stores O(1);
    only changed keys are ever copied (freeze snapshots O(Delta)).
    """

    _is_gen = True

    def __init__(self, birth, epoch, reader, config=None, counters=None):
        super().__init__(birth, epoch, config=config, counters=counters)
        self._reader = reader
        self._base_n = int(reader.root["atom_ordinals"])
        self._base_h = int(reader.root["holon_count"])
        self._base_tomb = frozenset(reader.retired_docs())
        for attr in _GEN_OV_ATTRS:
            setattr(self, attr, set() if attr in (
                "ov_retired_aids", "ov_retired_hids", "ov_doc_gone",
                "ov_text_gone", "ov_al_new", "ov_al_gone", "ov_lp_new",
                "ov_lp_gone", "ov_seg_leaves_gone",
                "ov_seg_parents_gone") else {})
        self.ov_df_nonzero = int((reader.term_df > 0).sum())
        self.ov_holon_live = int(self._base_h)
        self.atoms = _GenAtoms(self)
        self.holons = _GenHolons(self)
        self.atom_text = _GenAtomText(self)
        self.doc_atoms = _GenDocAtoms(self)
        self.df = _GenDf(self)
        self.doclen_of = _GenDoclen(self)
        self.ord_atom = _GenOrdAtom(self)
        self.aid_of_ord = _GenAidOfOrd(self)
        self.ord_holon = _GenOrdHolon(self)
        self.atom_leaves = _GenEdges(self, "al")
        self.leaf_parents = _GenEdges(self, "lp")
        self.retired_aids = _GenRetiredAids(self)
        self.seg_leaves_cache = self.ov_seg_leaves
        self.seg_parents_cache = self.ov_seg_parents
        self._atom_overrides = self.ov_atom_overrides
        self.tomb = Tombstones.live_empty()
        self.live_n = int(reader.root["live_n"])
        self.total_tokens = int(reader.root["total_tokens"])
        self.dim = int(reader.root.get("dim", 0) or 0)
        self.segments = ()
        self.delta = DeltaSegment(int(reader.root["frontier"]))
        self.frontier = int(reader.root["frontier"])
        self.atom_order = []
        self._last_rebase = None
        self._last_rebase = None

    # -- merged helpers --------------------------------------------
    def _tomb_contains(self, doc):
        return doc in self.tomb or doc in self._base_tomb

    def _live_aid(self, aid):
        if aid in self.ov_atoms:
            return True
        if aid in self.ov_retired_aids:
            return False
        try:
            o = self._reader.ord_of_aid(aid)
        except KeyError:
            return False
        return bool(self._reader.live[int(o)])

    def _df_bump(self, term, delta):
        base = self._reader.df_of(term)
        base = base if base is not None else 0
        old = self.ov_df.get(term, 0)
        new = old + delta
        if new:
            self.ov_df[term] = new
        else:
            self.ov_df.pop(term, None)
        if (base + old > 0) != (base + new > 0):
            self.ov_df_nonzero += 1 if base + new > 0 else -1

    def _edge_current(self, kind, key):
        if kind == "al":
            if key in self.ov_atom_leaves:
                return list(self.ov_atom_leaves[key])
            return self._reader.leaves_of(key)
        if key in self.ov_leaf_parents:
            return list(self.ov_leaf_parents[key])
        return self._reader.parents_of(key)

    def _edge_has_base(self, kind, key):
        import bisect as _bisect
        keys = self._reader._eal_list if kind == "al" \
            else self._reader._elp_list
        i = _bisect.bisect_left(keys, key)
        return i < len(keys) and keys[i] == key

    # -- overlay mutation paths (C1-equivalent, base-oracle reads) --
    def _insert_atom(self, seq, op_id, meta, text):
        aid = meta["atom"]
        o_known = self.ov_ord_atom.get(aid)
        base_known = self._reader.has_aid(aid)
        if o_known is None and not base_known:
            o = self._base_n + len(self.ov_ord_atom)
            self.ov_ord_atom[aid] = o
            self.ov_aid_of_ord[o] = aid
        else:
            o = o_known if o_known is not None \
                else self._reader.ord_of_aid(aid)
        entry = {"seq": seq, "op_id": op_id, "doc_id": meta["doc_id"],
                 "span": meta["span"],
                 "text_art": meta["text_artifact"],
                 "text_digest": meta["text_digest"],
                 "descriptor": np.array(meta.get("descriptor", []),
                                        dtype=np.float64)}
        if entry["descriptor"].size:
            if not self.dim:
                self.dim = int(entry["descriptor"].size)
            elif int(entry["descriptor"].size) != self.dim:
                raise ValueError("heterogeneous atom dim (fail closed)")
        retired = self._tomb_contains(meta["doc_id"])
        if not retired and self._live_aid(aid):
            if aid in self.ov_atom_text:
                old_text = self.ov_atom_text[aid]
            elif base_known:
                old_text = self._reader.text_of_ord(
                    self._reader.ord_of_aid(aid))
            else:
                old_text = None
            if old_text != text:
                raise ValueError(
                    f"aid {aid}: same-id text change (identity violation)")
            old_e = self.ov_atoms.get(aid)
            old_d = np.asarray(
                old_e["descriptor"] if old_e is not None
                else self._reader.atom_row_f64(
                    self._reader.ord_of_aid(aid)), dtype=np.float64)
            new_d = np.asarray(entry["descriptor"], dtype=np.float64)
            if old_d.shape != new_d.shape or bool(np.any(old_d != new_d)):
                self.ov_atom_overrides[o] = new_d.copy()
            self.ov_atoms[aid] = entry
            self.ov_doc_atoms.setdefault(meta["doc_id"], []).append(aid)
            self._invalidate()
            return
        self.ov_atoms[aid] = entry
        self.ov_doc_atoms.setdefault(meta["doc_id"], []).append(aid)
        if retired:
            self.ov_atoms.pop(aid, None)
            self.ov_doc_atoms.pop(meta["doc_id"], None)
            self.ov_retired_aids.add(aid)
            return
        self.ov_retired_aids.discard(aid)
        self.ov_atom_text[aid] = text
        ts = toks(text)
        self.ov_doclen[o] = len(ts)
        tf = {}
        for t in ts:
            tf[t] = tf.get(t, 0) + 1
        self.total_tokens += len(ts)
        self.live_n += 1
        for t in tf:
            self._df_bump(t, 1)
        if not self._no_delta:
            self.delta.append_atom(
                {"aid": aid, "ordinal": o, "seq": seq, "op_id": op_id,
                 "doc_id": meta["doc_id"], "span": meta["span"],
                 "text_art": meta["text_artifact"],
                 "text_digest": meta["text_digest"],
                 "descriptor": [float(x) for x in entry["descriptor"]]},
                text, entry["descriptor"], len(ts), tf)

    def _insert_holon(self, seq, op_id, meta):
        hid = meta["holon"]
        o_known = self.ov_ord_holon.get(hid)
        base_known = self._reader.has_hid(hid)
        new_hid = o_known is None and not base_known
        if new_hid:
            self.ov_ord_holon[hid] = self._base_h + len(self.ov_ord_holon)
        entry = {"seq": seq, "op_id": op_id,
                 "members": list(meta["members"]),
                 "descriptor": np.array(meta["descriptor"],
                                        dtype=np.float64),
                 "kind": meta.get("kind"),
                 "children": list(meta.get("children") or [])}
        hord = self.ov_ord_holon.get(hid)
        if hord is None:
            hord = self._reader.hord_of_hid(hid)
        if meta.get("kind") is None and self._tomb_contains(hid):
            if not self._no_delta:
                self.delta.append_holon(
                    {"hid": hid, "ordinal": hord,
                     "seq": seq, "op_id": op_id,
                     "members": list(entry["members"]),
                     "descriptor": [float(x)
                                    for x in entry["descriptor"]],
                     "kind": None, "children": []})
            return
        if hid in self.ov_holons:
            self._retract_holon_edges(hid, self.ov_holons[hid])
        elif base_known and hid not in self.ov_retired_hids:
            self._retract_holon_edges(hid, self._reader.holon_entry(hid))
        elif hid in self.ov_retired_hids:
            self.ov_retired_hids.discard(hid)
            self.ov_holon_live += 1
        elif new_hid:
            self.ov_holon_live += 1
        self.ov_holons[hid] = entry
        self._extend_holon_edges(hid, entry)
        if not self._no_delta:
            self.delta.append_holon(
                {"hid": hid, "ordinal": hord, "seq": seq,
                 "op_id": op_id, "members": list(entry["members"]),
                 "descriptor": [float(x) for x in entry["descriptor"]],
                 "kind": entry["kind"],
                 "children": list(entry["children"])})

    def _retract_holon_edges(self, hid, old):
        if old.get("kind") == "seg-leaf":
            for aid in old["members"]:
                cur = [h for h in self._edge_current("al", aid)
                       if h != hid]
                self.ov_atom_leaves[aid] = cur
                if not cur:
                    if self._edge_has_base("al", aid):
                        self.ov_al_gone.add(aid)
                    else:
                        self.ov_al_new.discard(aid)
                        self.ov_atom_leaves.pop(aid, None)
            if self._reader.has_hid(hid):
                self.ov_seg_leaves_gone.add(hid)
            self.ov_seg_leaves.pop(hid, None)
        elif old.get("kind") == "seg-parent":
            for child in old.get("children", []):
                cur = [h for h in self._edge_current("lp", child)
                       if h != hid]
                self.ov_leaf_parents[child] = cur
                if not cur:
                    if self._edge_has_base("lp", child):
                        self.ov_lp_gone.add(child)
                    else:
                        self.ov_lp_new.discard(child)
                        self.ov_leaf_parents.pop(child, None)
            if self._reader.has_hid(hid):
                self.ov_seg_parents_gone.add(hid)
            self.ov_seg_parents.pop(hid, None)

    def _extend_holon_edges(self, hid, entry):
        if entry.get("kind") == "seg-leaf":
            for aid in entry["members"]:
                cur = self._edge_current("al", aid)
                if hid not in cur:
                    cur = cur + [hid]
                self.ov_atom_leaves[aid] = cur
                if not self._edge_has_base("al", aid):
                    self.ov_al_new.add(aid)
                self.ov_al_gone.discard(aid)
            self.ov_seg_leaves[hid] = entry
            self.ov_seg_leaves_gone.discard(hid)
        elif entry.get("kind") == "seg-parent":
            for child in entry.get("children", []):
                cur = self._edge_current("lp", child)
                if hid not in cur:
                    cur = cur + [hid]
                self.ov_leaf_parents[child] = cur
                if not self._edge_has_base("lp", child):
                    self.ov_lp_new.add(child)
                self.ov_lp_gone.discard(child)
            self.ov_seg_parents[hid] = entry
            self.ov_seg_parents_gone.discard(hid)

    def _retire_docs(self, docs):
        new = [d for d in docs if not self._tomb_contains(d)]
        if not new:
            return
        self.tomb.add_live(new)
        for doc in new:
            ov_aids = self.ov_doc_atoms.pop(doc, [])
            base_aids = []
            try:
                for o in self._reader.doc_ordinals(doc).tolist():
                    base_aids.append(self._reader.aids[int(o)])
            except KeyError:
                pass
            texts = []
            for aid in ov_aids:
                e = self.ov_atoms.pop(aid, None)
                if e is None:
                    continue
                self.ov_retired_aids.add(aid)
                t = self.ov_atom_text.pop(aid, None)
                if t is not None:
                    texts.append(t)
            for aid in base_aids:
                if aid in self.ov_retired_aids:
                    continue
                if aid in self.ov_atoms:
                    self.ov_atoms.pop(aid, None)
                    t = self.ov_atom_text.pop(aid, None)
                    if t is None:
                        t = self._reader.text_of_ord(
                            self._reader.ord_of_aid(aid))
                else:
                    o = self._reader.ord_of_aid(aid)
                    if not self._reader.live[int(o)]:
                        continue
                    t = self._reader.text_of_ord(int(o))
                self.ov_retired_aids.add(aid)
                texts.append(t)
            total, dfmap = token_adjustments(texts)
            self.total_tokens -= total
            self.live_n -= len(texts)
            for t, c in dfmap.items():
                self._df_bump(t, -c)
            ent = self.ov_holons.get(doc)
            if ent is not None and ent.get("kind") is None:
                self._retract_holon_edges(doc, ent)
                del self.ov_holons[doc]
                self.ov_retired_hids.add(doc)
                self.ov_holon_live -= 1
            elif self._reader.has_hid(doc):
                bent = self._reader.holon_entry(doc)
                if bent.get("kind") is None and \
                        doc not in self.ov_retired_hids:
                    self._retract_holon_edges(doc, bent)
                    self.ov_retired_hids.add(doc)
                    self.ov_holon_live -= 1
        self._invalidate()

    def _rebuild_derived_from_live(self):
        """Overlay-scoped derived rebuild (external mutation only).

        Mirrors ServingView._rebuild_derived_from_live, but the base
        generation is immutable: only overlay adjustments are
        recomputed (ordinals for new overlay keys, df/doclen/counter
        adjustments, delta rows, overrides, edge replacements).
        Product paths never mutate.
        """
        self._require_live()
        r = self._reader
        for aid in self.ov_atoms:
            if aid not in self.ov_ord_atom and not r.has_aid(aid):
                o = self._base_n + len(self.ov_ord_atom)
                self.ov_ord_atom[aid] = o
                self.ov_aid_of_ord[o] = aid
        for hid in self.ov_holons:
            if hid not in self.ov_ord_holon and not r.has_hid(hid):
                self.ov_ord_holon[hid] = self._base_h + len(
                    self.ov_ord_holon)
        # Reset overlay derived state; the base is immutable truth.
        self.ov_df = {}
        self.ov_doclen = {}
        self.ov_df_nonzero = int((r.term_df > 0).sum())
        self.live_n = int(r.root["live_n"])
        self.total_tokens = int(r.root["total_tokens"])
        # Un-retire overlay-live base aids (external set resurrects
        # for legs, mirroring v1 atoms-membership liveness).
        for aid in list(self.ov_atoms):
            if aid in self.ov_retired_aids and r.has_aid(aid):
                self.ov_retired_aids.discard(aid)
        # Subtract base aids retired in the overlay.
        for aid in sorted(self.ov_retired_aids):
            if not r.has_aid(aid):
                continue
            o = r.ord_of_aid(aid)
            if not r.live[int(o)]:
                continue
            t = r.text_of_ord(int(o))
            ts = toks(t)
            self.total_tokens -= len(ts)
            self.live_n -= 1
            for term in set(ts):
                self._df_bump(term, -1)
        # Add overlay-origin live rows (recommits are idempotent:
        # their df already rides the base).
        for aid in sorted(
                self.ov_atoms,
                key=lambda a: self.ov_ord_atom.get(
                    a, r.ord_of_aid(a) if r.has_aid(a) else -1)):
            if r.has_aid(aid):
                continue  # recommit: base already covers stats
            text = self.ov_atom_text.get(aid)
            if text is None:
                continue  # text-only keys stay invisible (v1 rule)
            o = self.ov_ord_atom[aid]
            ts = toks(text)
            self.ov_doclen[o] = len(ts)
            self.total_tokens += len(ts)
            self.live_n += 1
            for term in set(ts):
                self._df_bump(term, 1)
        # Delta rows for uncovered overlay ordinals (base ordinals
        # are covered by the reader, never by the delta).
        covered = {int(rr["ordinal"]) for rr in self.delta.atom_rows}
        for aid in sorted(self.ov_atoms,
                          key=lambda a: self.ord_atom[a]):
            o = self.ord_atom[aid]
            if o < self._base_n:
                self._gen_override_if_drifted(aid, o)
                continue
            if o in covered:
                continue
            e = self.ov_atoms[aid]
            text = self.ov_atom_text.get(aid, "")
            vec = np.asarray(e.get("descriptor", []), dtype=np.float64)
            if vec.size and not self.dim:
                self.dim = int(vec.size)
            ts = toks(text)
            tf = {}
            for t in ts:
                tf[t] = tf.get(t, 0) + 1
            self.delta.append_atom(
                {"aid": aid, "ordinal": o, "seq": e.get("seq", 0),
                 "op_id": e.get("op_id"),
                 "doc_id": e.get("doc_id"), "span": e.get("span"),
                 "text_art": e.get("text_art"),
                 "text_digest": e.get("text_digest"),
                 "descriptor": [float(x) for x in vec]},
                text, vec, len(ts), tf)
        self.delta.resort()
        # Holon live count + edge stores recomputed over overlay.
        self.ov_holon_live = int(self._base_h)
        for hid in self.ov_retired_hids:
            if r.has_hid(hid):
                self.ov_holon_live -= 1
        for hid in self.ov_holons:
            if not r.has_hid(hid):
                self.ov_holon_live += 1
        for attr in ("ov_atom_leaves", "ov_leaf_parents", "ov_al_new",
                     "ov_al_gone", "ov_lp_new", "ov_lp_gone",
                     "ov_seg_leaves", "ov_seg_parents",
                     "ov_seg_leaves_gone", "ov_seg_parents_gone"):
            cur = getattr(self, attr)
            if isinstance(cur, set):
                cur.clear()
            else:
                cur.clear()
        for hid in self.ov_retired_hids:
            if r.has_hid(hid):
                self._retract_holon_edges(hid, r.holon_entry(hid))
        for hid, e in self.ov_holons.items():
            if r.has_hid(hid) and hid not in self.ov_retired_hids:
                self._retract_holon_edges(hid, r.holon_entry(hid))
            self._extend_holon_edges(hid, e)
        self._invalidate()

    def _gen_override_if_drifted(self, aid, o):
        live = np.asarray(self.ov_atoms[aid].get("descriptor", []),
                          dtype=np.float64)
        row = self._reader.atom_row_f64(int(o))
        if row.shape != live.shape or bool(np.any(row != live)):
            self.ov_atom_overrides[int(o)] = live.copy()

    def _rebase_in_place(self, reader):
        """Swap onto a new generation at the same pin (overlay reset).

        Pool-locked maintenance only (post-publish). The pin does
        not move (the new generation is published AT this pin), so
        every merged mapping stays valid; overlay stores reset to
        empty and base constants rebind. Facade mappings (which
        delegate per call) observe the new base transparently.
        """
        if int(reader.root["frontier"]) != int(self.frontier):
            raise ValueError(
                "rebase generation frontier != view pin (fail closed)")
        self._reader = reader
        self._base_n = int(reader.root["atom_ordinals"])
        self._base_h = int(reader.root["holon_count"])
        self._base_tomb = frozenset(reader.retired_docs())
        for attr in _GEN_OV_ATTRS:
            setattr(self, attr, set() if isinstance(
                getattr(self, attr), set) else {})
        self.ov_df_nonzero = int((reader.term_df > 0).sum())
        self.ov_holon_live = int(self._base_h)
        self.live_n = int(reader.root["live_n"])
        self.total_tokens = int(reader.root["total_tokens"])
        self.dim = int(reader.root.get("dim", 0) or self.dim)
        self.seg_leaves_cache = self.ov_seg_leaves
        self.seg_parents_cache = self.ov_seg_parents
        self._atom_overrides = self.ov_atom_overrides
        self.tomb = Tombstones.live_empty()
        self.delta = DeltaSegment(int(self.frontier))
        self._caches = {}

    # -- retained lifetime (overlay O(Delta) snapshots, reader shared)
    def freeze(self):
        if not self._live:
            return self
        self.delta.freeze()
        snap = {}
        for attr in _GEN_OV_ATTRS:
            cur = getattr(self, attr)
            snap[attr] = set(cur) if isinstance(cur, set) else dict(cur)
        for attr in _GEN_OV_INTS:
            snap[attr] = getattr(self, attr)
        self._snapshot = {
            "pin": self.pin, "reader": self._reader, "overlay": snap,
            "delta": self.delta, "tomb": self.tomb.snapshot(),
            "live_n": self.live_n, "total": self.total_tokens,
            "dim": self.dim}
        self._live = False
        for attr in _GEN_OV_ATTRS:
            setattr(self, attr, None)
        self.live_n = None
        self.total_tokens = None
        self._caches = {}
        return self

    def materialize(self):
        if self._live:
            return self
        t0 = time.time()
        snap = self._snapshot
        for attr in _GEN_OV_ATTRS:
            setattr(self, attr, snap["overlay"][attr])
        for attr in _GEN_OV_INTS:
            setattr(self, attr, snap["overlay"][attr])
        self.delta = snap["delta"]
        live_tomb = Tombstones.live_empty()
        for d in snap["tomb"].materialize():
            live_tomb._live.add(d)
        self.tomb = live_tomb
        self.live_n = snap["live_n"]
        self.total_tokens = snap["total"]
        self.dim = snap["dim"]
        self.seg_leaves_cache = self.ov_seg_leaves
        self.seg_parents_cache = self.ov_seg_parents
        self._atom_overrides = self.ov_atom_overrides
        self._live = True
        self.counters.record(straggler_rebuilds=1)
        self._materialize_ms = (time.time() - t0) * 1000.0
        return self

    # -- legs (block-aware base + delta, no restack/sort/loop) ------
    def _postings_of(self, term):
        o_arr, f_arr = self._reader.postings_of(term)
        for o, f in zip(o_arr.tolist(), f_arr.tolist()):
            yield int(o), int(f)
        for o, f in self.delta.postings.get(term, ()):
            yield int(o), int(f)

    def _columnar_for_bm25(self):
        hit = self._caches.get("bm25_cols")
        if hit is not None:
            return hit
        self._require_live()
        r = self._reader
        n_ov = len(self.ov_ord_atom)
        live = np.zeros((self._base_n + n_ov,), dtype=bool)
        live[:self._base_n] = r.live
        doclen = np.zeros((self._base_n + n_ov,), dtype=np.int64)
        doclen[:self._base_n] = r.doclen
        aids = [None] * (self._base_n + n_ov)
        for o in range(self._base_n):
            aids[o] = r.aids[o]
        for aid, o in self.ov_ord_atom.items():
            aids[o] = aid
            if aid in self.ov_atoms:
                live[o] = True
                doclen[o] = self.ov_doclen.get(o, 0)
        for aid in self.ov_retired_aids:
            o = self.ov_ord_atom.get(aid)
            if o is None and r.has_aid(aid):
                o = r.ord_of_aid(aid)
            if o is not None:
                live[int(o)] = False
        hit = {"live_ord": live, "doclen": doclen, "aids": aids}
        self._caches["bm25_cols"] = hit
        return hit

    def _bm25_runs_of(self, term):
        runs = []
        o_arr, f_arr = self._reader.postings_of(term)
        if len(o_arr):
            runs.append((o_arr, f_arr))
        run = self.delta.postings.get(term)
        if run:
            runs.append((
                np.array([p[0] for p in run], dtype=np.int64),
                np.array([p[1] for p in run], dtype=np.int64)))
        return runs

    def bm25(self, query):
        from tlsys.serving.lexical import K1, B  # noqa (doc anchor)
        self._require_live()
        n = max(1, self.live_n)
        avgdl = self.total_tokens / n
        terms = sorted(set(toks(query)))
        cols = self._columnar_for_bm25()
        return bm25_accumulate_vectorized(
            terms, self.df.get, n, avgdl, self._bm25_runs_of,
            cols["live_ord"], cols["doclen"], cols["aids"],
            self.counters)

    def _base_atom_dense(self):
        """Reader-cached base live assembly (built once per generation).

        (live_ord, mat64, norms, overrides, aids): exact f64 inputs
        shared by every view/pin on this reader (no restack per
        advance or per query). Overlay merges per view on top.
        """
        hit = getattr(self._reader, "_atom_dense_cache", None)
        if hit is not None:
            return hit
        r = self._reader
        live_ord = r.live_ordinals()
        mat = r.vectors[live_ord].astype(np.float64) if len(live_ord) \
            else np.empty((0, r.vectors.shape[1] if r.vectors.size
                           else 0))
        for j, o in enumerate(live_ord.tolist()):
            import bisect as _bisect
            i = _bisect.bisect_left(r._ov_list, int(o))
            if i < len(r._ov_list) and r._ov_list[i] == int(o):
                mat[j] = r.ov_mat[i]
        norms = r.norms_f64[live_ord].astype(np.float64).copy() \
            if len(live_ord) else np.empty((0,))
        aids = [r.aids[int(o)] for o in live_ord.tolist()]
        hit = {"live_ord": live_ord, "mat": mat, "norms": norms,
               "aids": aids}
        self._reader._atom_dense_cache = hit
        return hit

    def _overlay_atom_rows(self):
        """Live overlay rows in ordinal order: [(ord, aid, f64 row)]."""
        out = []
        for aid, o in sorted(self.ov_ord_atom.items(),
                             key=lambda kv: kv[1]):
            if aid not in self.ov_atoms:
                continue
            ov = self.ov_atom_overrides.get(o)
            if ov is not None:
                out.append((o, aid, np.asarray(ov, dtype=np.float64)))
                continue
            hit = None
            for i, rr in enumerate(self.delta.atom_rows):
                if int(rr["ordinal"]) == o:
                    hit = i
                    break
            if hit is None:
                continue
            d = self.delta.atom_rows[hit].get("descriptor")
            if d is None:
                out.append((o, aid, self.delta.vec_rows[hit].astype(
                    np.float64)))
            else:
                out.append((o, aid, np.asarray(d, dtype=np.float64)))
        return out

    def _dense_atoms_assembled(self):
        hit = self._caches.get("dense_atoms")
        if hit is not None:
            return hit
        self._require_live()
        base = self._base_atom_dense()
        ov_rows = self._overlay_atom_rows()
        recom = {aid for aid in self.ov_atoms
                 if aid not in self.ov_ord_atom}
        if not ov_rows and not recom and not self.ov_retired_aids \
                and not self.ov_atom_overrides:
            # Steady state: the reader-cached triple, zero-copy.
            hit = (list(base["aids"]), base["mat"], base["norms"])
            self._caches["dense_atoms"] = hit
            return hit
        # Overlay-perturbed: gather merged live rows in ordinal
        # order (base cache rows, rescored recommits, overlay rows).
        base_pos = {int(o): j for j, o in
                    enumerate(base["live_ord"].tolist())}
        ov_by_ord = {o: (aid, row) for o, aid, row in ov_rows}
        want = []
        for o in base["live_ord"].tolist():
            aid = base["aids"][base_pos[int(o)]]
            if aid in self.ov_retired_aids:
                continue
            want.append(int(o))
        for aid in recom:
            o = int(self._reader.ord_of_aid(aid))
            if aid not in self.ov_retired_aids and o not in base_pos:
                want.append(o)
        want.extend(o for o, _a, _r in ov_rows)
        want.sort()
        rows = []
        aids = []
        for o in want:
            if o in ov_by_ord:
                aid, row = ov_by_ord[o]
            elif o in base_pos and base["aids"][base_pos[o]] in \
                    self.ov_atoms:
                aid = base["aids"][base_pos[o]]
                row = np.asarray(self.ov_atoms[aid]["descriptor"],
                                 dtype=np.float64)
            elif o in base_pos:
                aid = base["aids"][base_pos[o]]
                row = base["mat"][base_pos[o]]
            else:
                aid = self._reader.aid_of_ord(o)
                row = np.asarray(self.ov_atoms[aid]["descriptor"],
                                 dtype=np.float64)
            aids.append(aid)
            rows.append(row)
        if not rows:
            dim = base["mat"].shape[1] if base["mat"].size else 0
            hit = ([], np.empty((0, dim)), np.empty((0,)))
            self._caches["dense_atoms"] = hit
            return hit
        mat = np.stack(rows)
        norms = np.linalg.norm(mat, axis=1)
        norms[norms == 0.0] = 1.0
        hit = (aids, mat, norms)
        self._caches["dense_atoms"] = hit
        return hit

    def dense_atoms_full(self, qvec):
        from tlsys.query import _dense_rank
        self._require_live()
        ids, mat, norms = self._dense_atoms_assembled()
        self.counters.record(dense_rescore_rows=len(ids))
        return _dense_rank(qvec, ids, mat, norms)

    def dense_atoms_topk(self, qvec, k):
        """Certified block-aware top-k (no assembly, no full sort).

        Base head via the E2-certified shortlist over the full base
        blocks (k + every non-live base row, non-live filtered: the
        live top-k provably survives); overlay head exact over its
        small matrix; ord-free merge. Rescored overlay rows ride the
        shortlist must-set (certificate stays sound for arbitrary
        re-version vectors, not just FP32 rounding). Widenings and
        fallback are counted honestly.
        """
        from tlsys.serving.dense import certified_topk
        self._require_live()
        if self.live_n == 0 or k <= 0:
            return []
        r = self._reader
        n_retired_base = int((~r.live).sum())
        ov_ret_base = sum(1 for a in self.ov_retired_aids
                          if r.has_aid(a))
        kk = min(int(k) + n_retired_base + ov_ret_base, len(r.aids))
        m = self.config["shortlist_margin_m"]
        eps = self.config["dense_eps"]
        ov_dict = {int(o): np.asarray(r.ov_mat[i], dtype=np.float64)
                   for i, o in enumerate(r._ov_list)}
        # Rescored overlay rows ride the overrides dict, which the
        # E2 protocol always forces into the shortlist (sound for
        # arbitrary re-version vectors, not just FP32 rounding).
        for aid in self.ov_atoms:
            if aid in self.ov_ord_atom or not r.has_aid(aid):
                continue
            o = int(r.ord_of_aid(aid))
            ov_dict[o] = np.asarray(
                self.ov_atoms[aid]["descriptor"], dtype=np.float64)
        for o, row in self.ov_atom_overrides.items():
            if int(o) < self._base_n and int(o) not in ov_dict:
                ov_dict[int(o)] = np.asarray(row, dtype=np.float64)
        aids_all = getattr(r, "_aids_list_cache", None)
        if aids_all is None:
            aids_all = r.aids.tolist()
            r._aids_list_cache = aids_all
        out_b, cert = certified_topk(
            qvec, kk, aids_all, np.ascontiguousarray(r.vectors),
            np.asarray(r.norms_f64, dtype=np.float64), ov_dict, m=m,
            eps=eps, counters=self.counters)
        self._last_cert = cert
        live_b = [(a, s) for a, s in out_b
                  if a not in self.ov_retired_aids
                  and self._live_aid(a)][:int(k)]
        ov_rows = self._overlay_atom_rows()
        if ov_rows:
            from tlsys.query import _dense_rank
            omat = np.stack([row for _o, _a, row in ov_rows])
            onorms = np.linalg.norm(omat, axis=1)
            onorms[onorms == 0.0] = 1.0
            oids = [aid for _o, aid, _row in ov_rows]
            self.counters.record(dense_rescore_rows=len(oids))
            live_o = _dense_rank(qvec, oids, omat, onorms,
                                 topk=int(k))
        else:
            live_o = []
        out = []
        i = j = 0
        while i < len(live_b) and j < len(live_o) and \
                len(out) < int(k):
            if live_b[i][1] >= live_o[j][1]:
                out.append(live_b[i])
                i += 1
            else:
                out.append(live_o[j])
                j += 1
        while i < len(live_b) and len(out) < int(k):
            out.append(live_b[i])
            i += 1
        while j < len(live_o) and len(out) < int(k):
            out.append(live_o[j])
            j += 1
        return out

    def _base_holon_dense(self):
        hit = getattr(self._reader, "_holon_dense_cache", None)
        if hit is not None:
            return hit
        r = self._reader
        hids = r.hids.tolist()
        mat = np.ascontiguousarray(r.holon_vectors)
        norms = np.linalg.norm(mat, axis=1) if hids \
            else np.empty((0,))
        norms[norms == 0.0] = 1.0
        hit = {"aids": hids, "mat": mat, "norms": norms}
        self._reader._holon_dense_cache = hit
        return hit

    def dense_atoms_head(self, qvec, k):
        """Exact base+overlay head without assembling any triple.

        Base scores come from one matvec over the reader-cached
        assembly (shared, never copied); overlay scores from its
        small matrix; heads merge ord-free (every base ordinal
        precedes every overlay ordinal). k=None ranks fully. No
        restack, no full sort for heads, no Python loop per row.
        Counts executed rows honestly (full matvecs both blocks).
        """
        from tlsys.query import _dense_rank
        from tlsys.serving.dense import stable_head
        self._require_live()
        base = self._base_atom_dense()
        q = np.asarray(qvec, dtype=np.float64)
        qn = float(np.linalg.norm(q)) or 1.0
        ov_rows = self._overlay_atom_rows()
        recom = {aid for aid in self.ov_atoms
                 if aid not in self.ov_ord_atom}
        retired = set(self.ov_retired_aids)
        n_scored = 0
        if recom or retired or self.ov_atom_overrides:
            # Overlay-perturbed base rows: one exact matvec over
            # the merged base set (retired filtered, recommits
            # rescored; the shared base is never copied).
            live_ord = base["live_ord"].tolist()
            keep = [j for j, o in enumerate(live_ord)
                    if base["aids"][j] not in retired]
            bmat = base["mat"][keep] if len(keep) != len(live_ord) \
                else base["mat"]
            bnorms = base["norms"][keep] \
                if len(keep) != len(live_ord) else base["norms"]
            baids = [base["aids"][j] for j in keep]
            rescore_idx = [jj for jj, a in enumerate(baids)
                           if a in self.ov_atoms]
            if rescore_idx:
                bmat = bmat.copy()
                bnorms = bnorms.copy()
                for jj in rescore_idx:
                    row = np.asarray(
                        self.ov_atoms[baids[jj]]["descriptor"],
                        dtype=np.float64)
                    bmat[jj] = row
                    n = float(np.linalg.norm(row))
                    bnorms[jj] = n if n else 1.0
            n_scored += len(baids)
            bord = stable_head((bmat @ q) / (qn * bnorms), baids,
                               len(baids) if k is None else int(k)) \
                if len(baids) else []
        elif len(base["aids"]):
            s = (base["mat"] @ q) / (qn * base["norms"])
            n_scored += len(base["aids"])
            bord = stable_head(s, base["aids"], len(base["aids"])
                               if k is None else int(k))
        else:
            bord = []
        if ov_rows:
            omat = np.stack([row for _o, _a, row in ov_rows])
            onorms = np.linalg.norm(omat, axis=1)
            onorms[onorms == 0.0] = 1.0
            oids = [aid for _o, aid, _row in ov_rows]
            n_scored += len(oids)
            oord = _dense_rank(qvec, oids, omat, onorms,
                               topk=None if k is None else int(k))
        else:
            oord = []
        self.counters.record(dense_rescore_rows=n_scored)
        out = []
        i = j = 0
        lim = None if k is None else int(k)
        while i < len(bord) and j < len(oord) and \
                (lim is None or len(out) < lim):
            if bord[i][1] >= oord[j][1]:
                out.append(bord[i])
                i += 1
            else:
                out.append(oord[j])
                j += 1
        # One side is exhausted (or the head is full): the remaining
        # tail is already ordered; base wins cross-side ties.
        rest = bord[i:] + oord[j:] if j >= len(oord) \
            else oord[j:] + bord[i:]
        out.extend(rest if lim is None else rest[:lim - len(out)])
        return out

    def dense_holons_head(self, qvec, k):
        """Exact holon base+overlay head (same contract as atoms)."""
        from tlsys.query import _dense_rank
        from tlsys.serving.dense import stable_head
        self._require_live()
        base = self._base_holon_dense()
        q = np.asarray(qvec, dtype=np.float64)
        qn = float(np.linalg.norm(q)) or 1.0
        ov_new = [(self.ov_ord_holon[h], h) for h in self.ov_holons
                  if not self._reader.has_hid(h)]
        recom = [h for h in self.ov_holons
                 if self._reader.has_hid(h)]
        retired = [h for h in self.ov_retired_hids
                   if self._reader.has_hid(h)]
        n_scored = len(base["aids"])
        if not ov_new and not recom and not retired:
            s = (base["mat"] @ q) / (qn * base["norms"]) \
                if len(base["aids"]) else np.empty((0,))
            out = stable_head(s, base["aids"], len(base["aids"])
                              if k is None else int(k)) \
                if len(base["aids"]) else []
            self.counters.record(holon_rows_scored=n_scored)
            return out
        mat = base["mat"].copy()
        norms = base["norms"].copy()
        hids = list(base["aids"])
        pos = {h: j for j, h in enumerate(hids)}
        for h in recom:
            row = np.asarray(self.ov_holons[h]["descriptor"],
                             dtype=np.float64)
            mat[pos[h]] = row
            n = float(np.linalg.norm(row))
            norms[pos[h]] = n if n else 1.0
        drop = {pos[h] for h in retired if h in pos}
        if drop:
            keep = [j for j in range(len(hids)) if j not in drop]
            mat = mat[keep]
            norms = norms[keep]
            hids = [hids[j] for j in keep]
        if ov_new:
            rows = [np.asarray(self.ov_holons[h]["descriptor"],
                               dtype=np.float64)
                    for _o, h in sorted(ov_new)]
            omat = np.stack(rows)
            onorms = np.linalg.norm(omat, axis=1)
            onorms[onorms == 0.0] = 1.0
            mat = np.vstack([mat, omat]) if hids else omat
            norms = np.concatenate([norms, onorms]) if hids else onorms
            hids = hids + [h for _o, h in sorted(ov_new)]
            n_scored += len(ov_new)
        self.counters.record(holon_rows_scored=n_scored)
        return _dense_rank(qvec, hids, mat, norms, topk=k)

    def _dense_holons_assembled(self):
        hit = self._caches.get("dense_holons")
        if hit is not None:
            return hit
        self._require_live()
        base = self._base_holon_dense()
        ov_new = [(self.ov_ord_holon[h], h) for h in self.ov_holons
                  if not self._reader.has_hid(h)]
        recom = [h for h in self.ov_holons
                 if self._reader.has_hid(h)]
        retired = [h for h in self.ov_retired_hids
                   if self._reader.has_hid(h)]
        if not ov_new and not recom and not retired:
            hit = (list(base["aids"]), base["mat"], base["norms"])
            self._caches["dense_holons"] = hit
            return hit
        mat = base["mat"].copy()
        norms = base["norms"].copy()
        hids = list(base["aids"])
        pos = {h: j for j, h in enumerate(hids)}
        for h in recom:
            row = np.asarray(self.ov_holons[h]["descriptor"],
                             dtype=np.float64)
            mat[pos[h]] = row
            n = float(np.linalg.norm(row))
            norms[pos[h]] = n if n else 1.0
        drop = {pos[h] for h in retired if h in pos}
        if drop:
            keep = [j for j in range(len(hids)) if j not in drop]
            mat = mat[keep]
            norms = norms[keep]
            hids = [hids[j] for j in keep]
        if ov_new:
            rows = [np.asarray(self.ov_holons[h]["descriptor"],
                               dtype=np.float64)
                    for _o, h in sorted(ov_new)]
            omat = np.stack(rows)
            onorms = np.linalg.norm(omat, axis=1)
            onorms[onorms == 0.0] = 1.0
            mat = np.vstack([mat, omat]) if hids else omat
            norms = np.concatenate([norms, onorms]) if hids else onorms
            hids = hids + [h for _o, h in sorted(ov_new)]
        hit = (hids, mat, norms)
        self._caches["dense_holons"] = hit
        return hit

    # -- facade-shaped accessors (merged) ------------------------------
    @property
    def seg_leaves(self):
        self._require_live()
        base = getattr(self._reader, "_seg_leaves_cache", None)
        if base is None:
            base = {}
            for ho, hid in enumerate(self._reader.hids.tolist()):
                if self._reader.hkind[ho] is not None and str(
                        self._reader.hkind[ho]) == "seg-leaf":
                    base[hid] = self._reader.holon_entry(hid)
            self._reader._seg_leaves_cache = base
        out = {h: e for h, e in base.items()
               if h not in self.ov_seg_leaves_gone}
        out.update(self.ov_seg_leaves)
        return out

    @property
    def seg_parents(self):
        self._require_live()
        base = getattr(self._reader, "_seg_parents_cache", None)
        if base is None:
            base = {}
            for ho, hid in enumerate(self._reader.hids.tolist()):
                if self._reader.hkind[ho] is not None and str(
                        self._reader.hkind[ho]) == "seg-parent":
                    base[hid] = self._reader.holon_entry(hid)
            self._reader._seg_parents_cache = base
        out = {h: e for h, e in base.items()
               if h not in self.ov_seg_parents_gone}
        out.update(self.ov_seg_parents)
        return out

    @property
    def retired_docs(self):
        if self._live:
            return sorted(set(self._base_tomb) |
                          self.tomb.materialize())
        return sorted(set(self._reader.retired_docs()) |
                      self._snapshot["tomb"].materialize())

    @property
    def retired_atoms(self):
        self._require_live()
        return len(self.retired_aids)

    @property
    def retired_aids_set(self):
        self._require_live()
        return set(self.retired_aids)

    @property
    def avgdl(self):
        n = max(1, self.live_n if self._live
                else self._snapshot["live_n"])
        total = self.total_tokens if self._live \
            else self._snapshot["total"]
        return total / n

    def postings_live(self):
        hit = self._caches.get("postings")
        if hit is not None:
            return hit
        self._require_live()
        r = self._reader
        collect = {}
        for i, t in enumerate(r._terms):
            a, b = int(r.term_offsets[i]), int(r.term_offsets[i + 1])
            for o, f in zip(r.post_ord[a:b].tolist(),
                            r.post_tf[a:b].tolist()):
                if r.live[int(o)] and r.aids[int(o)] not in \
                        self.ov_retired_aids:
                    collect.setdefault(t, []).append(
                        (r.aids[int(o)], int(f)))
        for t, run in self.delta.postings.items():
            for o, f in run:
                aid = self.ov_aid_of_ord.get(int(o))
                if aid is None:
                    try:
                        aid = r.aid_of_ord(int(o))
                    except KeyError:
                        continue
                if aid in self.atoms:
                    collect.setdefault(t, []).append((aid, int(f)))
        post = {}
        for t, run in collect.items():
            run.sort(key=lambda p: self.ord_atom[p[0]])
            if run:
                post[t] = run
        self._caches["postings"] = post
        return post

    def idf_live(self):
        hit = self._caches.get("idf")
        if hit is None:
            self._require_live()
            n = max(1, self.live_n)
            hit = {t: idf_of(n, self.df[t]) for t in self.df}
            self._caches["idf"] = hit
        return hit

    def doc_len_live(self):
        hit = self._caches.get("doc_len")
        if hit is None:
            self._require_live()
            hit = {aid: self.doclen_of[self.ord_atom[aid]]
                   for aid in self.atoms}
            self._caches["doc_len"] = hit
        return hit

    def live_atom_set(self):
        hit = self._caches.get("live_set")
        if hit is None:
            self._require_live()
            hit = frozenset(self.atoms)
            self._caches["live_set"] = hit
        return hit

    def nomination_maps(self):
        self._require_live()
        return self.atom_leaves, self.leaf_parents

    def canonical_digest(self):
        self._require_live()
        return canonical_digest(
            self.atoms, self.holons, self.atom_text,
            self.retired_docs, self.retired_aids_set, self.live_n,
            self.total_tokens, self.df)


class EpochChangedError(StaleViewError):
    pass


class CheckpointError(Exception):
    pass


# Live-dict attributes moved (O(1)) from the base view to its successor
# on advance; the base freezes to a retained snapshot.
_LIVE_ATTRS = (
    "atoms", "holons", "doc_atoms", "atom_text", "retired_aids", "df",
    "total_tokens", "live_n", "ord_atom", "ord_holon", "aid_of_ord",
    "atom_order", "doclen_of", "atom_leaves", "leaf_parents",
    "seg_leaves_cache", "seg_parents_cache", "_atom_overrides", "dim",
)

CHECKPOINT_FILENAME = "checkpoint.json"
QUARANTINE_DIRNAME = "quarantined"
# Segment-load parallel threshold (S-5): chains at/above this many
# on-disk bytes load concurrently (the 10M chain is 727MB); below
# it, serial load wins (thread/GIL overhead dominates tiny chains).
PARALLEL_LOAD_BYTES = 32 << 20


def tombstone_version_of(retired_docs):
    """Manifest tombstone_version: digest of the sorted retired-doc union
    of the sealed segments (exact; validated on attach)."""
    body = "\n".join(sorted(retired_docs)).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


class ViewPool:
    """Pinned-view lifecycle: build/advance/retain/evict + persistence.

    Single-writer discipline: advance/seal/checkpoint/attach-publish
    hold an internal RLock. Direct view legs must run under
    pool.guarded() whenever an advance may run concurrently (the
    facade holds it for every leg; see the serving contract). A view
    answers for exactly one pin; advancing freezes the old object,
    which materializes on demand for stragglers (same pin).
    """

    def __init__(self, tlstore, birth, epoch, serving_dir=None,
                 config=None, counters=None):
        self.tlstore = tlstore
        self.birth = birth
        self.epoch = epoch
        self.serving_dir = serving_dir
        self.config = serving_config(config)
        self.counters = counters or ServeCounters()
        self._lock = threading.RLock()
        self._retained = {}  # max_seq -> ServingView (published)
        self._order = []     # max_seq, oldest first (K eviction)
        self._current = None
        if serving_dir is not None:
            os.makedirs(serving_dir, exist_ok=True)

    # -- locking ---------------------------------------------------
    @contextlib.contextmanager
    def guarded(self):
        """Hold the pool lock (direct-leg readers use this)."""
        with self._lock:
            yield

    # -- Scanning (one helper records log counters uniformly) ------
    def _scan(self, lo, hi):
        rows, metas = seg_mod.scan_range(
            self.tlstore, self.birth, self.epoch, lo, hi,
            counters=self.counters)
        self.counters.record(log_ops_read=len(metas))
        atom_metas = [m for m in metas if m[3] == "atom"]
        texts = seg_mod.read_atom_texts(
            self.tlstore,
            [(s, o, a, m) for s, o, a, _k, m in atom_metas],
            counters=self.counters)
        return rows, metas, texts

    def _new_live(self):
        view = ServingView(self.birth, self.epoch, config=self.config,
                           counters=self.counters)
        view._pool_lock = self._lock
        return view

    def _new_gen_live(self, reader):
        view = GenerationView(self.birth, self.epoch, reader,
                              config=self.config,
                              counters=self.counters)
        view._pool_lock = self._lock
        return view

    # -- persisted generations (Closure S, gen v2) -------------------
    def _gen_pointer(self):
        """('ok', frontier) | ('corrupt', None) | ('absent', None)."""
        from tlsys.serving import generation as gen_mod
        if self.serving_dir is None:
            return "absent", None
        gendir = os.path.join(self.serving_dir, gen_mod.GEN_DIRNAME)
        if not os.path.isfile(os.path.join(
                gendir, gen_mod.GEN_FILENAME)):
            return "absent", None
        try:
            root = gen_mod.read_root(gendir)
        except (gen_mod.GenerationError, OSError, ValueError):
            return "corrupt", None
        if (root.get("birth"), root.get("epoch")) != \
                (self.birth, self.epoch):
            return "corrupt", None
        return "ok", int(root["frontier"])

    def _has_v1_backup(self):
        from tlsys.serving import generation as gen_mod
        return self.serving_dir is not None and os.path.isfile(
            os.path.join(self.serving_dir, gen_mod.V1_MANIFEST_BACKUP))

    def _quarantine_generation(self, reason):
        from tlsys.serving import generation as gen_mod
        gendir = os.path.join(self.serving_dir, gen_mod.GEN_DIRNAME)
        dest = os.path.join(
            self.serving_dir, QUARANTINE_DIRNAME,
            f"gen-{int(time.time() * 1000)}-{reason}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        try:
            os.rename(gendir, dest)
        except OSError:
            pass
        self.counters.record(quarantines=1, rebuild_ranges=1)

    def publish_generation(self, view):
        """Build + verify + atomically publish a gen-v2 generation.

        Stage C: v1 source views (migrate); gen-view rebase publish
        follows in Stage D. Verifies derived/source correspondence
        (ranges, op-hash, counts, tombstones, text digests) before
        the atomic swap; rewrites manifest.json as a v2 pointer
        (old readers refuse). Returns the combined receipt.
        """
        from tlsys.serving import generation as gen_mod
        if self.serving_dir is None:
            raise CheckpointError("publish_generation needs serving_dir")
        with self._lock:
            if view._pool_lock is not self._lock:
                raise StaleViewError("publish of a foreign view")
            if not view._live:
                view.materialize()
            if getattr(view, "_is_gen", False):
                raise gen_mod.GenerationError(
                    "rebase publish from gen views arrives in Stage D")
            tmpdir = os.path.join(
                self.serving_dir,
                f"{gen_mod.GEN_TMP_PREFIX}{view.frontier}-"
                f"{int(time.time() * 1000)}")
            root, build_receipt = gen_mod.build_generation_blocks(
                view, tmpdir, counters=self.counters)
            verify_receipt = gen_mod.verify_against_source(
                root, self.tlstore, self.birth, self.epoch, self._scan,
                counters=self.counters)
            pub_receipt = gen_mod.publish_generation(
                tmpdir, root, self.serving_dir, verify_receipt,
                counters=self.counters)
            return {"build": build_receipt, "verify": verify_receipt,
                    "publish": pub_receipt}

    def _attach_gen_locked(self, pin, stages=None):
        from tlsys.serving import generation as gen_mod
        t_attach0 = time.monotonic()
        split = {"gen_open_ms": 0.0, "gen_suffix_ms": 0.0}

        def _record(extra):
            if stages is not None:
                stages.update(split)
                stages["attach_total_ms"] = \
                    (time.monotonic() - t_attach0) * 1000.0
                stages.update(extra)

        birth, epoch, mx, _t = pin
        if (birth, epoch) != (self.birth, self.epoch):
            raise EpochChangedError("gen attach for a foreign pin")
        t0 = time.monotonic()
        try:
            proot = gen_mod.read_root(os.path.join(
                self.serving_dir, gen_mod.GEN_DIRNAME))
        except (gen_mod.GenerationError, OSError, ValueError) as e:
            split["gen_open_ms"] = (time.monotonic() - t0) * 1000.0
            self._quarantine_generation("root-failed")
            _record({"cold_fallback": f"gen-corrupt: {type(e).__name__}",
                     "generation_frontier": None, "suffix_rows": None})
            return self._attach_v1_or_cold(pin, stages)
        if (proot.get("birth"), proot.get("epoch")) != (birth, epoch):
            # Foreign lineage: not ours to quarantine; v1/cold.
            split["gen_open_ms"] = (time.monotonic() - t0) * 1000.0
            _record({"cold_fallback": "gen-foreign",
                     "generation_frontier": None, "suffix_rows": None})
            return self._attach_v1_or_cold(pin, stages)
        try:
            root, reader = gen_mod.open_generation(
                self.serving_dir, birth, epoch, counters=self.counters)
        except (gen_mod.GenerationError, OSError, ValueError) as e:
            split["gen_open_ms"] = (time.monotonic() - t0) * 1000.0
            self._quarantine_generation("open-failed")
            _record({"cold_fallback": f"gen-corrupt: {type(e).__name__}",
                     "generation_frontier": None, "suffix_rows": None})
            return self._attach_v1_or_cold(pin, stages)
        split["gen_open_ms"] = (time.monotonic() - t0) * 1000.0
        frontier = int(root["frontier"])
        if mx < frontier:
            _record({"cold_fallback": "gen-rewind",
                     "generation_frontier": frontier,
                     "suffix_rows": None})
            return self._attach_v1_or_cold(pin, stages)
        view = self._new_gen_live(reader)
        view.frontier = frontier
        view.delta.lo = frontier
        view.delta.hi = frontier
        suffix_rows = 0
        if mx > frontier:
            t0 = time.monotonic()
            rows, metas, texts = self._scan(frontier, mx)
            view.apply_range(rows, metas, texts)
            suffix_rows = len(rows)
            split["gen_suffix_ms"] = (time.monotonic() - t0) * 1000.0
        view.frontier = mx
        view.pin = pin
        view.delta.hi = mx
        self._publish_locked(view)
        _record({"cold_fallback": None,
                 "generation_frontier": frontier,
                 "suffix_rows": suffix_rows,
                 "blocks_verified": len(root["blocks"]),
                 "max_live_segments": int(
                     self.config["max_live_segments"])})
        return view

    def _attach_v1_or_cold(self, pin, stages=None):
        from tlsys.serving import generation as gen_mod
        if self._has_v1_backup():
            return self._attach_locked(
                pin, stages=stages,
                manifest_path=os.path.join(
                    self.serving_dir, gen_mod.V1_MANIFEST_BACKUP),
                checkpoint_path=os.path.join(
                    self.serving_dir, gen_mod.V1_CHECKPOINT_BACKUP))
        if self._has_checkpoint():
            return self._attach_locked(pin, stages=stages)
        if stages is not None:
            stages["cold_fallback"] = stages.get("cold_fallback") \
                or "gen-no-fallback"
        return self._cold_locked(pin)

    def _advance_gen_locked(self, base, pin):
        new = self._new_gen_live(base._reader)
        new_delta = base.delta.copy()
        snap_node = base.tomb.snapshot()
        new_delta.hi = base.frontier
        # O(1) overlay handoff (changed keys only; the reader and its
        # blocks are never copied): move every overlay store.
        for attr in _GEN_OV_ATTRS:
            setattr(new, attr, getattr(base, attr))
        for attr in _GEN_OV_INTS:
            setattr(new, attr, getattr(base, attr))
        new.live_n = base.live_n
        new.total_tokens = base.total_tokens
        new.dim = base.dim
        new.seg_leaves_cache = new.ov_seg_leaves
        new.seg_parents_cache = new.ov_seg_parents
        new._atom_overrides = new.ov_atom_overrides
        new.delta = new_delta
        live_tomb = Tombstones.live_empty()
        live_tomb._live = base.tomb._live \
            if base.tomb._live is not None \
            else set(base.tomb.materialize())
        live_tomb._head = snap_node
        new.tomb = live_tomb
        new.frontier = base.frontier
        base.freeze()
        base._snapshot["tomb"] = snap_node
        _birth, _epoch, mx, _t = pin
        rows, metas, texts = self._scan(base.frontier, mx)
        new.apply_range(rows, metas, texts)
        new.frontier = mx
        new.pin = pin
        new.delta.hi = mx
        self._publish_locked(new)
        self._enforce_debt_locked(new)
        self._maybe_rebase_locked(new)
        return new

    def _overlay_debt(self, view):
        """Unpublished-suffix debt: atom/holon rows, edges, bytes."""
        d = view.delta
        atom_rows = len(d.atom_rows)
        holon_rows = len(d.holon_rows)
        edges = 0
        for r in d.holon_rows:
            edges += len(r.get("members", [])) + \
                len(r.get("children") or [])
        text_bytes = sum(len(t.encode("utf-8")) for t in d.texts)
        try:
            vec_bytes = int(np.asarray(d.vec_rows).nbytes)
        except (AttributeError, ValueError, TypeError):
            vec_bytes = 0
        return {"atom_rows": int(atom_rows),
                "holon_rows": int(holon_rows), "edges": int(edges),
                "bytes_est": int(text_bytes + vec_bytes)}

    def _maybe_rebase_locked(self, view):
        """Auto-rebase when overlay debt exceeds any enabled bound.

        Publishes a new generation at the view's pin (abortable on
        the maintenance time budget) and swaps the live view onto
        it in place (overlay reset; facade mappings stay valid).
        Abort/failure keeps serving on the overlay (correct, debt
        explicit in stats). Receipt rides view._last_rebase.
        """
        from tlsys.serving import generation as gen_mod
        debt = self._overlay_debt(view)
        bounds = (
            ("atom_rows", "gen_overlay_max_atoms"),
            ("holon_rows", "gen_overlay_max_holons"),
            ("edges", "gen_overlay_max_edges"),
            ("bytes_est", "gen_overlay_max_bytes"))
        hit = [name for name, key in bounds
               if int(self.config.get(key, 0) or 0) > 0
               and debt[name] > int(self.config[key])]
        if not hit:
            view._last_rebase = {"status": "within-bounds",
                                 "debt": debt}
            return view._last_rebase
        if self.serving_dir is None:
            view._last_rebase = {"status": "no-serving-dir",
                                 "debt": debt, "bounds_hit": hit}
            return view._last_rebase
        receipt, maint = gen_mod.background_rebase(
            self.tlstore, self.serving_dir, view.pin, self.birth,
            self.epoch, config=self.config,
            time_budget_s=float(
                self.config.get("maint_time_budget_s", 0) or 0))
        receipt["debt"] = debt
        receipt["bounds_hit"] = hit
        receipt["maint_counters"] = maint.totals()
        if receipt.get("status") == "published":
            _root, reader = gen_mod.open_generation(
                self.serving_dir, self.birth, self.epoch,
                counters=self.counters)
            view._rebase_in_place(reader)
        view._last_rebase = receipt
        return receipt

    # -- publish / retain / evict ----------------------------------
    def _publish_locked(self, view):
        mx = view.max_seq
        self._retained[mx] = view
        if mx in self._order:
            self._order.remove(mx)
        self._order.append(mx)
        if self._current is None or mx >= self._current.max_seq:
            self._current = view
        view._refs += 1
        self._evict_locked(protect=mx)
        self.counters.set_gauge(
            views_retained=len(self._retained),
            segments_live=len(view.segments),
            delta_rows=len(view.delta.atom_rows))

    def _evict_locked(self, protect=None):
        keep = int(self.config["retained_generations_K"])
        while len(self._order) > keep:
            cand = None
            for mx in self._order:
                if mx != protect and self._retained[mx]._refs == 0:
                    cand = mx
                    break
            if cand is None:
                break  # all retained views are held; keep over cap
            del self._retained[cand]
            self._order.remove(cand)

    def acquire(self, pin, stages=None):
        """The view at `pin` (refcounted; caller must release()).

        Builds via advance-from-ancestor or cold build when absent.
        Older-than-all pins cold-build (rewind-safe); foreign
        (birth, epoch) raises EpochChangedError (fail closed).
        stages: optional dict filled by the restart (attach) path
        with its stage-split timings (see attach()); ignored on the
        retained/advance/cold paths.
        """
        birth, epoch, mx, _t = pin
        with self._lock:
            if (birth, epoch) != (self.birth, self.epoch):
                raise EpochChangedError(
                    f"pool at {self.birth}:{self.epoch}, "
                    f"asked {birth}:{epoch}: new pool required")
            if mx in self._retained:
                view = self._retained[mx]
                view._refs += 1
                return view
            cands = [s for s in self._retained if s <= mx]
            if cands:
                base = self._retained[max(cands)]
                if not base._live:
                    base.materialize()
                if getattr(base, "_is_gen", False):
                    return self._advance_gen_locked(base, pin)
                return self._advance_locked(base, pin)
            gen_state, _gen_frontier = self._gen_pointer()
            if gen_state in ("ok", "corrupt"):
                # Gen-v2 restart path: open the generation root +
                # indexes, consume only the unpublished suffix.
                # Corrupt generations quarantine inside and fall
                # back to the v1 pointer pair or a cold build;
                # rewinds below the generation go v1/cold.
                return self._attach_gen_locked(pin, stages=stages)
            if self._has_checkpoint():
                # Restart path: attach persisted segments (validated;
                # falls back to cold build on any failure inside).
                return self._attach_locked(pin, stages=stages)
            return self._cold_locked(pin)

    def _has_checkpoint(self):
        return self.serving_dir is not None and os.path.isfile(
            os.path.join(self.serving_dir, CHECKPOINT_FILENAME))

    def release(self, view):
        with self._lock:
            if view._pool_lock is not self._lock:
                raise StaleViewError("release of a foreign view")
            view._refs = max(0, view._refs - 1)
            self._evict_locked()
            self.counters.set_gauge(views_retained=len(self._retained))

    def advance(self, view, pin):
        """Append-only hop of `view` to `pin` (O(|Delta|)).

        Returns the NEW live view (sharing sealed segments); the old
        object freezes to a retained snapshot at its pin. Older pins
        raise RewindError (acquire() cold-builds those); foreign
        (birth, epoch) raises EpochChangedError.
        """
        with self._lock:
            if view._pool_lock is not self._lock:
                raise StaleViewError("advance of a foreign view")
            birth, epoch, mx, _t = pin
            if (birth, epoch) != (self.birth, self.epoch):
                raise EpochChangedError(
                    f"pool at {self.birth}:{self.epoch}, "
                    f"asked {birth}:{epoch}")
            if mx < view.frontier:
                raise RewindError(
                    f"pin {mx} < view frontier {view.frontier}: "
                    "acquire() cold-builds rewinds")
            if not view._live:
                view.materialize()
            if mx == view.frontier:
                view._refs += 1
                return view
            if getattr(view, "_is_gen", False):
                return self._advance_gen_locked(view, pin)
            return self._advance_locked(view, pin)

    def _advance_locked(self, base, pin):
        new = self._new_live()
        new_delta = base.delta.copy()
        snap_node = base.tomb.snapshot()
        new_delta.hi = base.frontier
        for attr in _LIVE_ATTRS:
            setattr(new, attr, getattr(base, attr))
        new.delta = new_delta
        new.segments = base.segments
        live_tomb = Tombstones.live_empty()
        # O(1) tomb handoff (Closure S: no advance copies the whole
        # tombstone set): the live set object moves to the successor;
        # the frozen base serves stragglers from its immutable
        # snapshot node (never the moved live set).
        live_tomb._live = base.tomb._live \
            if base.tomb._live is not None \
            else set(base.tomb.materialize())
        live_tomb._head = snap_node
        new.tomb = live_tomb
        new.frontier = base.frontier
        base.freeze()
        base._snapshot["tomb"] = snap_node
        _birth, _epoch, mx, _t = pin
        rows, metas, texts = self._scan(base.frontier, mx)
        new.apply_range(rows, metas, texts)
        new.frontier = mx
        new.pin = pin
        new.delta.hi = mx
        self._maybe_seal_locked(new)
        self._publish_locked(new)
        self._enforce_debt_locked(new)
        return new

    def _enforce_debt_locked(self, view):
        """Autonomous segment-debt enforcement (S-5, closure B).

        Runs at the end of every pool advance (the deployed
        incremental transition): while the sealed chain exceeds
        max_live_segments, merge one cheap group (in-process,
        validated vs the log, published) so debt sawtooths at
        the bound instead of growing without limit.
        Group choice is tiered: the leftmost pair of the
        smallest multi-segment level-run first (levels use
        compact's tiering math, so promotion cascades like an
        explicit compaction); when every run is a singleton
        (interleaved shapes), the tail pair as a progress
        fallback. Groups over max_inline_merge_atoms rows are
        skipped, so bulk-built chains keep their pinned
        explicit-compact semantics (visible via the
        segments_live gauge + the attach receipt) and no
        surprise whole-chain merge ever lands inside advance.
        Best-effort maintenance: any failure records
        failed_retried and leaves the (valid, unmerged) chain
        serving — advance never fails because of maintenance.
        """
        try:
            bound = int(self.config["max_live_segments"])
            fan_in = max(2, int(self.config["merge_fan_in"]))
            flush = max(1, int(self.config["delta_flush_atoms"]))
            row_cap = int(self.config.get("max_inline_merge_atoms",
                                          10000))
        except (KeyError, ValueError, TypeError):
            return
        from tlsys.serving import compact as compact_mod
        while len(view.segments) > bound:
            segs = list(view.segments)
            group = self._debt_group_locked(
                segs, flush, fan_in, row_cap, compact_mod)
            if not group:
                return  # no cheap group: explicit compaction owns it
            try:
                merged = compact_mod.merge_group(
                    group, counters=self.counters)
                merged.validate_against_log(
                    self.tlstore, self.birth, self.epoch,
                    counters=self.counters)
                compact_mod.publish(self, [merged], [group])
            except Exception:
                self.counters.record(failed_retried=1)
                return

    @staticmethod
    def _debt_group_locked(segs, flush, fan_in, row_cap,
                           compact_mod):
        """Pick one cheap merge group (or None). Tiered first,
        tail-pair fallback; every candidate is row-capped."""
        levels = [compact_mod._level(len(s.atom_rows), flush,
                                     fan_in) for s in segs]
        best = None
        i = 0
        while i < len(segs):
            j = i
            while j + 1 < len(segs) and levels[j + 1] == levels[i]:
                j += 1
            if j > i and (best is None
                          or levels[i] < levels[best[0]]):
                best = (i, j)
            i = j + 1
        if best is not None:
            i, j = best
            group = segs[i:min(j + 1, i + fan_in)]
            if sum(len(s.atom_rows) for s in group) <= row_cap:
                return group
        if len(segs) >= 2:
            group = segs[-2:]
            if sum(len(s.atom_rows) for s in group) <= row_cap:
                return group
        return None

    # -- seal / cold / attach / checkpoint -------------------------
    def _maybe_seal_locked(self, view):
        if getattr(view, "_is_gen", False):
            return  # gen overlays persist via publish_generation
        if len(view.delta.atom_rows) >= \
                int(self.config["delta_flush_atoms"]):
            self.seal_locked(view)

    def seal_locked(self, view):
        """Seal view.delta to an immutable segment (no re-tokenization).

        Validates the sealed range against the log before serving it;
        on validation failure the delta stays authoritative and the
        seal is skipped (counters record it; never serve unsure).
        Persists when serving_dir is set (persist failure also keeps
        the in-memory seal and records failed_retried).
        Gen views refuse: sealing v1 segments under a generation
        base would mix formats; publish a generation instead.
        """
        if getattr(view, "_is_gen", False):
            from tlsys.serving import generation as gen_mod
            raise gen_mod.GenerationError(
                "seal on generation-backed views is refused; call "
                "publish_generation (v2 persist) instead")
        from tlsys.serving.lexical import TermLexicon
        delta = view.delta
        if not delta.atom_rows and not delta.holon_rows \
                and not delta.retired_docs and not delta.op_ids:
            return None
        segid = seg_mod.segid_of(delta.lo, delta.hi)
        tf_rows = [(o, dl, tf) for o, (dl, tf) in delta.tf_cache.items()]
        lex = TermLexicon.from_tf(tf_rows)
        mat32 = delta.mat32()
        if mat32.shape[1] == 0 and view.dim:
            mat32 = mat32.reshape(0, view.dim)
        seg = seg_mod.Segment(
            segid, delta.lo, delta.hi, self.birth, self.epoch,
            [dict(r) for r in delta.atom_rows], list(delta.texts),
            [dict(r) for r in delta.holon_rows],
            set(delta.retired_docs), list(delta.op_ids),
            delta.n_commit_rows, lex=lex, mat32=mat32,
            norms64=delta.norms64(),
            overrides=dict(delta.overrides))
        try:
            seg.validate_against_log(self.tlstore, self.birth,
                                     self.epoch,
                                     counters=self.counters)
        except seg_mod.SegmentError:
            self.counters.record(rebuild_ranges=1)
            return None
        if self.serving_dir is not None:
            # Persist BEFORE swapping in-memory state: a persist
            # failure (ENOSPC, kill point) leaves the authoritative
            # delta untouched and the seal is cleanly retried later.
            segdir = os.path.join(self.serving_dir, segid)
            try:
                seg.save(segdir, counters=self.counters)
            except faults_mod.FaultTripped:
                self.counters.record(failed_retried=1)
                raise
            except (OSError, seg_mod.SegmentError) as e:
                self.counters.record(failed_retried=1)
                raise CheckpointError(
                    f"seal persist failed for {segid}: {e}")
        view.segments = view.segments + (seg,)
        view.delta = DeltaSegment(delta.hi)
        return seg

    def cold_build(self, pin, ranges=None, parallel=False,
                   max_workers=4):
        """Authoritative build from the log (one scan, seals on flush).

        ranges: explicit [(lo, hi)] partition of (0, max_seq] (validated
        contiguous from 0); default single range. parallel=True scans
        ranges concurrently (artifact I/O + tokenize) and applies them
        in order through the identical apply+seal path (same result).
        """
        with self._lock:
            return self._cold_locked(pin, ranges=ranges,
                                     parallel=parallel,
                                     max_workers=max_workers)

    def _cold_locked(self, pin, ranges=None, parallel=False,
                     max_workers=4):
        birth, epoch, mx, _t = pin
        if (birth, epoch) != (self.birth, self.epoch):
            raise EpochChangedError("cold build for a foreign pin")
        if ranges is None:
            ranges = [(0, mx)]
        else:
            ranges = list(ranges)
            expect = 0
            for lo, hi in ranges:
                if lo != expect or hi < lo:
                    raise ValueError(
                        f"ranges must partition (0, {mx}] from 0: {ranges}")
                expect = hi
            if expect != mx:
                raise ValueError(
                    f"ranges must partition (0, {mx}] from 0: {ranges}")
        view = self._new_live()
        if parallel and len(ranges) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                scanned = list(ex.map(lambda r: self._scan(*r), ranges))
        else:
            scanned = [self._scan(lo, hi) for lo, hi in ranges]
        for (lo, hi), (rows, metas, texts) in zip(ranges, scanned):
            view.apply_range(rows, metas, texts)
            view.frontier = hi
            view.delta.hi = hi
            self._maybe_seal_locked(view)
        view.pin = pin
        self._publish_locked(view)
        return view

    def checkpoint(self, view):
        """Seal fully + persist manifest + checkpoint file (atomic).

        Checkpoints are fully-sealed states (delta empty): attach can
        validate (live_n, total_tokens, tombstone union) exactly.
        Requires serving_dir.
        """
        if self.serving_dir is None:
            raise CheckpointError("checkpoint needs serving_dir")
        with self._lock:
            if view._pool_lock is not self._lock:
                raise StaleViewError("checkpoint of a foreign view")
            if not view._live:
                view.materialize()
            if getattr(view, "_is_gen", False):
                # v2 persist: checkpointing a generation-backed view
                # publishes a generation (same persist-the-state
                # effect, v2 receipt shape {"gen2": True, ...}).
                receipt = self.publish_generation(view)
                receipt["gen2"] = True
                return receipt
            if view.delta.atom_rows or view.delta.holon_rows \
                    or view.delta.retired_docs or view.delta.op_ids:
                seg = self.seal_locked(view)
                if seg is None:
                    raise CheckpointError(
                        "delta seal failed validation; not checkpointed")
            sealed_hi = view.segments[-1].hi if view.segments else 0
            if sealed_hi != view.frontier:
                raise CheckpointError(
                    f"unsealed tail: sealed {sealed_hi} != "
                    f"frontier {view.frontier}")
            union = set()
            for seg in view.segments:
                union |= seg.retired_docs
            payload = manifest_mod.build(
                list(view.segments), tombstone_version_of(union),
                sealed_hi, view.live_n, view.total_tokens)
            manifest_mod.atomic_write(
                os.path.join(self.serving_dir, manifest_mod.FILENAME),
                payload, counters=self.counters)
            from tlsys.serving import checkpoints as ckpt_mod
            ckpt_mod.save_checkpoint(
                os.path.join(self.serving_dir, CHECKPOINT_FILENAME),
                self.birth, self.epoch, sealed_hi,
                payload["tombstone_version"], payload["digest"])
            return payload

    def attach(self, pin, stages=None):
        """Cold start from persisted segments + tail replay (validated).

        Reads manifest + checkpoint, loads segments (per-file digest
        validation each; one batched log check sliced per range —
        identical per-range count + op-hash checks; failures
        quarantine + rebuild that range from the log), replays sealed
        state in seq order (C1 order, so ordinals reproduce exactly),
        validates sealed stats and the tombstone union, replays the
        tail. Never serves an unvalidated state. Requires serving_dir.

        stages: optional dict filled with the attach stage-split
        timings (ms) + validation counts (contract A14; F2 fresh-
        reader attribution). None (default) records nothing and
        behaves identically.
        """
        if self.serving_dir is None:
            raise CheckpointError("attach needs serving_dir")
        with self._lock:
            return self._attach_locked(pin, stages=stages)

    def _attach_locked(self, pin, stages=None, manifest_path=None,
                       checkpoint_path=None):
        from tlsys.serving import checkpoints as ckpt_mod
        t_attach0 = time.monotonic()
        split = {"manifest_read_ms": 0.0, "seg_load_ms": 0.0,
                 "seg_logval_ms": 0.0, "replay_ms": 0.0,
                 "pretouch_ms": 0.0, "tail_ms": 0.0}

        def _record(extra):
            if stages is not None:
                stages.update(split)
                stages["attach_total_ms"] = \
                    (time.monotonic() - t_attach0) * 1000.0
                stages.update(extra)

        birth, epoch, mx, _t = pin
        if (birth, epoch) != (self.birth, self.epoch):
            raise EpochChangedError("attach for a foreign pin")
        ckpt = ckpt_mod.load_checkpoint(
            checkpoint_path if checkpoint_path is not None
            else os.path.join(self.serving_dir, CHECKPOINT_FILENAME))
        if ckpt is None:
            _record({"cold_fallback": "no-checkpoint",
                     "segments_validated": 0, "segments_rebuilt": 0,
                     "segments_attached": 0,
                     "max_live_segments": int(
                         self.config["max_live_segments"])})
            return self._cold_locked(pin)
        if (ckpt.get("birth"), ckpt.get("epoch")) != (birth, epoch):
            _record({"cold_fallback": "birth-epoch",
                     "segments_validated": 0, "segments_rebuilt": 0,
                     "segments_attached": 0,
                     "max_live_segments": int(
                         self.config["max_live_segments"])})
            return self._cold_locked(pin)
        t0 = time.monotonic()
        try:
            manifest = manifest_mod.read_validated(
                manifest_path if manifest_path is not None
                else os.path.join(self.serving_dir,
                                  manifest_mod.FILENAME))
        except (OSError, ValueError):
            self.counters.record(quarantines=1, rebuild_ranges=1)
            split["manifest_read_ms"] = (time.monotonic() - t0) * 1000.0
            _record({"cold_fallback": "manifest",
                     "segments_validated": 0, "segments_rebuilt": 0,
                     "segments_attached": 0,
                     "max_live_segments": int(
                         self.config["max_live_segments"])})
            return self._cold_locked(pin)
        split["manifest_read_ms"] = (time.monotonic() - t0) * 1000.0
        sealed_hi = int(manifest["checkpoint_frontier"])
        if mx < sealed_hi:
            # Rewind below the checkpoint: cold-build the older pin.
            _record({"cold_fallback": "rewind",
                     "segments_validated": 0, "segments_rebuilt": 0,
                     "segments_attached": 0,
                     "max_live_segments": int(
                         self.config["max_live_segments"])})
            return self._cold_locked(pin)
        # 1a. Load segments (per-file digests validated inside load);
        # load failures quarantine + re-scan their range fresh.
        # Segments are independent (pure load + locked counters),
        # so multi-segment chains load concurrently (S-5); the
        # quarantine/rescan below still runs sequentially in
        # manifest order, so behavior stays deterministic.
        good = []   # [(entry, seg)]
        fresh = []  # [(entry, rows, metas, texts)]
        loaded = []  # [(entry, seg)] pending the batched log check
        t0 = time.monotonic()
        entries = list(manifest["segments"])

        def _load_one(entry):
            segdir = os.path.join(self.serving_dir, entry["segid"])
            try:
                return (entry, seg_mod.Segment.load(
                    segdir, counters=self.counters), None)
            except (OSError, ValueError, seg_mod.SegmentError) as e:
                return (entry, None, e)

        # Parallel load only pays above ~32MB of segment bytes
        # (thread/GIL overhead dominates for tiny chains; the 10M
        # chain is 727MB). Size-gated, deterministic either way.
        parallel = False
        if len(entries) > 1:
            total_hint = 0
            for entry in entries:
                segdir = os.path.join(self.serving_dir,
                                      entry["segid"])
                try:
                    names = os.listdir(segdir)
                except OSError:
                    continue  # load below fails closed as usual
                for name in names:
                    try:
                        total_hint += os.path.getsize(
                            os.path.join(segdir, name))
                    except OSError:
                        pass
            parallel = total_hint >= PARALLEL_LOAD_BYTES
        if parallel:
            with ThreadPoolExecutor(
                    max_workers=min(8, len(entries))) as ex:
                outcomes = list(ex.map(_load_one, entries))
        else:
            outcomes = [_load_one(entry) for entry in entries]
        for entry, seg, exc in outcomes:
            if exc is None:
                loaded.append((entry, seg))
                continue
            self.counters.record(quarantines=1)
            seg_mod.quarantine(
                os.path.join(self.serving_dir, entry["segid"]),
                os.path.join(self.serving_dir, QUARANTINE_DIRNAME),
                counters=self.counters)
            t1 = time.monotonic()
            rows, metas, texts = self._scan(entry["lo"],
                                            entry["hi"])
            split["seg_logval_ms"] += (time.monotonic() - t1) * 1000.0
            fresh.append((entry, rows, metas, texts))
        split["seg_load_ms"] = (time.monotonic() - t0) * 1000.0
        # 1b. ONE substrate scan for every loaded range (A15): the same
        # per-range count + op-hash + birth/epoch checks as N
        # validate_against_log calls (measured 6.2x fewer substrate
        # round-trips locally), sliced per range. Failures take the
        # identical quarantine + fresh-rescan path as load failures.
        t0 = time.monotonic()
        if loaded:
            himax = max(seg.hi for _e, seg in loaded)
            all_rows = self.tlstore.read_commits_all(
                birth, epoch, himax, kind=seg_mod.KIND, min_seq=0)
            # Sealed-validation rows are real substrate reads: count
            # them (S-3 section 6.5 gap, closed through the existing
            # log_rows_read key; ops are not decoded, so log_ops
            # stays untouched).
            self.counters.record(log_rows_read=len(all_rows))
            seqs = [r[0] for r in all_rows]
            ordered = True
            for a, b in zip(seqs, seqs[1:]):
                if b < a:
                    ordered = False
                    break
            import bisect as _bisect
            for entry, seg in loaded:
                if ordered:
                    i0 = _bisect.bisect_right(seqs, seg.lo)
                    i1 = _bisect.bisect_right(seqs, seg.hi)
                    rows = all_rows[i0:i1]
                else:
                    rows = all_rows  # check filters per range
                try:
                    seg.check_against_rows(rows, birth, epoch)
                    good.append((entry, seg))
                except (OSError, ValueError, seg_mod.SegmentError):
                    self.counters.record(quarantines=1)
                    seg_mod.quarantine(
                        os.path.join(self.serving_dir, entry["segid"]),
                        os.path.join(self.serving_dir,
                                     QUARANTINE_DIRNAME),
                        counters=self.counters)
                    rows, metas, texts = self._scan(entry["lo"],
                                                    entry["hi"])
                    fresh.append((entry, rows, metas, texts))
        split["seg_logval_ms"] += (time.monotonic() - t0) * 1000.0
        # 2. Bulk restore in (seq) order: global ordinals reproduce
        # exactly (C1 scan order across disjoint ranges) and are
        # verified against the persisted values. An ordinal
        # mismatch quarantines + rescans exactly that range (the
        # same path as a log-validation failure) and replays once
        # more on a FRESH view (the half-built one is discarded);
        # each retry shrinks `good` by one, so this terminates.
        # Other errors propagate exactly as before.
        view = None
        t0 = time.monotonic()
        for _attempt in range(len(good) + 1):
            cand = self._new_live()
            cand._no_delta = True
            try:
                self._replay_merged_locked(cand, good, fresh)
            except (seg_mod.OrdinalMismatchError,
                    seg_mod.LexCoherenceError) as e:
                cand._no_delta = False
                self.counters.record(quarantines=1)
                for j, (entry, _seg) in enumerate(good):
                    if entry["segid"] == e.segid:
                        break
                else:
                    raise
                bad = good.pop(j)
                seg_mod.quarantine(
                    os.path.join(self.serving_dir, bad[0]["segid"]),
                    os.path.join(self.serving_dir,
                                 QUARANTINE_DIRNAME),
                    counters=self.counters)
                t1 = time.monotonic()
                rows, metas, texts = self._scan(bad[0]["lo"],
                                                bad[0]["hi"])
                split["seg_logval_ms"] += \
                    (time.monotonic() - t1) * 1000.0
                fresh.append((bad[0], rows, metas, texts))
                continue
            cand._no_delta = False
            view = cand
            break
        split["replay_ms"] = (time.monotonic() - t0) * 1000.0
        # 3. Build replacement segments with the replayed GLOBAL
        # ordinal maps, validate, persist.
        sealed = [seg for _e, seg in good]
        for entry, rows, metas, texts in fresh:
            seg = seg_mod.build_segment_from_scan(
                entry["segid"], entry["lo"], entry["hi"],
                self.birth, self.epoch, rows, metas, texts,
                dict(view.ord_atom), dict(view.ord_holon))
            seg.validate_against_log(self.tlstore, self.birth,
                                     self.epoch,
                                     counters=self.counters)
            seg.save(os.path.join(self.serving_dir, seg.segid),
                     counters=self.counters)
            sealed.append(seg)
            self.counters.record(rebuild_ranges=1)
        sealed.sort(key=lambda s: s.lo)
        view.segments = tuple(sealed)
        # 4. Validate sealed tombstone union + sealed stats vs the
        # manifest; any skew fails closed to a cold build.
        union = set()
        for seg in sealed:
            union |= seg.retired_docs
        if tombstone_version_of(union) != \
                manifest.get("tombstone_version"):
            self.counters.record(quarantines=1, rebuild_ranges=1)
            _record({"cold_fallback": "tombstone-union",
                     "segments_validated": len(good),
                     "segments_rebuilt": len(fresh),
                     "segments_attached": 0,
                     "max_live_segments": int(
                         self.config["max_live_segments"])})
            return self._cold_locked(pin)
        if view.live_n != manifest.get("live_n") or \
                view.total_tokens != manifest.get("total_tokens"):
            self.counters.record(quarantines=1, rebuild_ranges=1)
            _record({"cold_fallback": "sealed-stats",
                     "segments_validated": len(good),
                     "segments_rebuilt": len(fresh),
                     "segments_attached": 0,
                     "max_live_segments": int(
                         self.config["max_live_segments"])})
            return self._cold_locked(pin)
        # NOTE (A16): no pre_touch here. Load just read every segment
        # byte in this process, so a second full re-read only warms
        # already-hot pages; publish keeps its pre-swap pre_touch.
        t0 = time.monotonic()
        if mx > sealed_hi:
            rows, metas, texts = self._scan(sealed_hi, mx)
            view.apply_range(rows, metas, texts)
        split["tail_ms"] = (time.monotonic() - t0) * 1000.0
        view.frontier = mx
        view.delta.hi = mx
        view.pin = pin
        self._maybe_seal_locked(view)
        self._publish_locked(view)
        _record({"cold_fallback": None,
                 "segments_validated": len(good),
                 "segments_rebuilt": len(fresh),
                 "segments_attached": len(view.segments),
                 "max_live_segments": int(
                     self.config["max_live_segments"])})
        return view

    def _replay_merged_locked(self, view, good, fresh):
        """Bulk restore of sealed live state (S-5; exact-equivalent
        to the old per-row insert replay, proven by D3 + the
        synthetic differential + the BM25/dense batteries).

        Same contract: seq-order (C1 order) first-seen ordinal
        assignment, atoms/holons first and retirements last (C1
        end-filter), delta reset to the sealed frontier after. The
        caller sets view._no_delta (replay never touches the delta).
        Differences vs the old path (all proven identical state):
        (a) persisted ordinals are VERIFIED against the walk
        (OrdinalMismatchError -> quarantine + rebuild that range;
        the old path recomputed live ordinals but trusted the
        persisted ones for the segment-lexicon joins without
        checking); (b) descriptors widen in one C-speed pass per
        segment; (c) df/total/doclen derive from the sealed
        lexicons (no live-row retokenization: only retired,
        recommit-extra, and fresh rows are tokenized, with the
        same toks/token_adjustments functions the insert path
        uses); (d) no per-row python insert overhead.
        """
        # 0. Retired set upfront (projection of the old end-filter;
        # the tomb itself is filled at the end, as before).
        retired = set()
        for _entry, seg in good:
            retired |= seg.retired_docs
        for _entry, _rows, metas, _texts in fresh:
            for _s, _op, _art, mkind, meta in metas:
                if mkind == "retirement":
                    retired.add(meta["retirement"]["doc"])
        # One C-speed f64 widening per segment (exact: f32 -> f64 is
        # value-preserving); sealed overrides applied in place with
        # the identical heterogeneous-dim rule the insert path uses.
        seg_mats = {}
        for _entry, seg in good:
            mat64 = np.asarray(seg.mat32, dtype=np.float64)
            for k, v in seg.overrides.items():
                kk = int(k)
                if kk < 0 or kk >= mat64.shape[0]:
                    raise seg_mod.LexCoherenceError(
                        seg.segid, f"override ordinal {kk} out of "
                        f"range (rows {mat64.shape[0]})")
                vv = np.asarray(v, dtype=np.float64)
                if vv.size != mat64.shape[1]:
                    raise ValueError(
                        "heterogeneous atom dim (fail closed)")
                mat64[kk] = vv
            seg_mats[id(seg)] = mat64
        # 1. Atom walk in (seq, source) order over sealed rows +
        # fresh metas INTERLEAVED (fresh ranges sit between good
        # ranges by seq; first-seen ranks need the global order).
        # Source indices run over sealed rows (segment order, row
        # order) then fresh metas (entry order, meta order): the
        # same tie-break the old stable stream sort produced.
        atom_stream = []
        ix = 0
        for _entry, seg in good:
            for i, r in enumerate(seg.atom_rows):
                atom_stream.append((r["seq"], ix, seg, i, r, None))
                ix += 1
        for _entry, _rows, metas, texts in fresh:
            for m in metas:
                if m[3] == "atom":
                    atom_stream.append((m[0], ix, None, 0, m,
                                        texts))
                    ix += 1
        atom_stream.sort(key=lambda s: (s[0], s[1]))
        ord_atom = view.ord_atom
        aid_of_ord = view.aid_of_ord
        atom_order = view.atom_order
        atoms = view.atoms
        doc_atoms = view.doc_atoms
        atom_text = view.atom_text
        retired_aids = view.retired_aids
        doclen_of = view.doclen_of
        nocc = {}
        first_text = {}
        prev_desc = {}
        for _seq, _ix, seg, i, r, texts in atom_stream:
            if seg is not None:
                aid = r["aid"]
                doc = r["doc_id"]
                text = seg.texts[i]
                desc = seg_mats[id(seg)][i]
                seq = r["seq"]
                op_id = r["op_id"]
                span = r["span"]
                text_art = r["text_art"]
                text_digest = r["text_digest"]
            else:
                meta = r[4]
                aid = meta["atom"]
                doc = meta["doc_id"]
                text = texts[aid]
                desc = np.array(meta.get("descriptor", []),
                                dtype=np.float64)
                seq = r[0]
                op_id = r[1]
                span = meta["span"]
                text_art = meta["text_artifact"]
                text_digest = meta["text_digest"]
            first = aid not in ord_atom
            if first:
                o = len(ord_atom)
                ord_atom[aid] = o
                aid_of_ord[o] = aid
                atom_order.append(aid)
                nocc[aid] = 1
                first_text[aid] = text
            else:
                o = ord_atom[aid]
                nocc[aid] += 1
            if seg is not None and r["ordinal"] != o:
                raise seg_mod.OrdinalMismatchError(
                    seg.segid, f"aid {aid}: stored {r['ordinal']} "
                    f"!= C1 rank {o}")
            if first and seg is not None and o not in doclen_of:
                # _retire_docs never pops doclen_of, so retired
                # ords stay too (reproduced exactly). A missing
                # ordinal is lexicon incoherence (fail closed to
                # quarantine + rebuild, never a silent zero).
                try:
                    doclen_of[o] = seg.lex.doclen[r["ordinal"]]
                except KeyError:
                    raise seg_mod.LexCoherenceError(
                        seg.segid, f"doclen lacks ordinal "
                        f"{r['ordinal']}")
            if desc.size:
                if not view.dim:
                    view.dim = int(desc.size)
                elif int(desc.size) != view.dim:
                    raise ValueError(
                        "heterogeneous atom dim (fail closed)")
            if not first:
                # Recommit checks run for live AND retired rows
                # (the tomb is empty mid-replay, exactly as in the
                # insert path): identity first, then the override
                # against the CONSECUTIVE row (prev_desc tracks
                # every row, live or retired).
                if first_text[aid] != text:
                    raise ValueError(
                        f"aid {aid}: same-id text change "
                        "(identity violation)")
                prev = prev_desc[aid]
                if prev.shape != desc.shape or bool(
                        np.any(prev != desc)):
                    view._atom_overrides[o] = np.asarray(
                        desc, dtype=np.float64).copy()
            prev_desc[aid] = desc
            if doc in retired:
                retired_aids.add(aid)
                continue
            atoms[aid] = {
                "seq": seq, "op_id": op_id, "doc_id": doc,
                "span": span, "text_art": text_art,
                "text_digest": text_digest,
                "descriptor": np.asarray(
                    desc, dtype=np.float64).copy()}
            doc_atoms.setdefault(doc, []).append(aid)
            if first:
                atom_text[aid] = text
        # 2. Holon walk in (seq, source) order (same interleave).
        holon_stream = []
        for _entry, seg in good:
            for r in seg.holon_rows:
                holon_stream.append((r["seq"], ix, seg, r, None))
                ix += 1
        for _entry, _rows, metas, _texts in fresh:
            for m in metas:
                if m[3] == "holon":
                    holon_stream.append((m[0], ix, None, m, None))
                    ix += 1
        holon_stream.sort(key=lambda s: (s[0], s[1]))
        ord_holon = view.ord_holon
        holons = view.holons
        for _seq, _ix, seg, r, _t in holon_stream:
            if seg is not None:
                hid = r["hid"]
                desc = np.array(r["descriptor"], dtype=np.float64,
                                copy=True)
                entry = {"seq": r["seq"], "op_id": r["op_id"],
                         "members": list(r["members"]),
                         "descriptor": desc, "kind": r.get("kind"),
                         "children": list(r.get("children") or [])}
                first = hid not in ord_holon
                if first:
                    ord_holon[hid] = len(ord_holon)
                if r["ordinal"] != ord_holon[hid]:
                    raise seg_mod.OrdinalMismatchError(
                        seg.segid, f"hid {hid}: stored "
                        f"{r['ordinal']} != C1 rank "
                        f"{ord_holon[hid]}")
            else:
                meta = r[4]
                hid = meta["holon"]
                entry = {"seq": r[0], "op_id": r[1],
                         "members": list(meta["members"]),
                         "descriptor": np.array(
                             meta["descriptor"], dtype=np.float64),
                         "kind": meta.get("kind"),
                         "children": list(meta.get("children") or [])}
                if hid not in ord_holon:
                    ord_holon[hid] = len(ord_holon)
            # Insert-then-remove (the tomb is empty mid-replay, so
            # the kind-None check never fires here, exactly as in
            # _insert_holon; per-doc holons of retired docs are
            # removed in step 4 like _retire_docs does).
            if hid in holons:
                view._retract_holon_edges(hid, holons[hid])
            holons[hid] = entry
            view._extend_holon_edges(hid, entry)
        # 3. Lex-derived stats (no live-row retokenization).
        # df: sealed per-ROW df sums + fresh-row tokenization
        # (fresh rows are unsealed, like the apply path) minus
        # retired first-occurrences (token_adjustments, the same
        # function _retire_docs uses) minus recommit extras
        # (identity: the same text every occurrence, tokenized
        # once per aid). total: the live doclen sum DIRECTLY
        # (doclen_of is per-ordinal while df is per-row, so total
        # cannot share the df adjustment base; summing live
        # ordinals is exact with no tokenization at all).
        df = {}
        for _entry, seg in good:
            lex = seg.lex
            if len(lex.terms) != len(lex.df) or \
                    len(lex.offsets) != len(lex.terms) + 1:
                raise seg_mod.LexCoherenceError(
                    seg.segid, f"terms/df/offsets lengths "
                    f"{len(lex.terms)}/{len(lex.df)}/"
                    f"{len(lex.offsets)}")
            for t, c in zip(lex.terms, lex.df):
                df[t] = df.get(t, 0) + int(c)
        for _entry, _rows, metas, texts in fresh:
            for m in metas:
                if m[3] != "atom":
                    continue
                aid = m[4]["atom"]
                ts = toks(texts[aid])
                for t in set(ts):
                    df[t] = df.get(t, 0) + 1
                o = ord_atom[aid]
                if o not in doclen_of:
                    doclen_of[o] = len(ts)
        if retired_aids:
            _t_adj, df_adj = token_adjustments(
                [first_text[a] for a in retired_aids])
            for t, c in df_adj.items():
                left = df.get(t, 0) - c
                if left > 0:
                    df[t] = left
                else:
                    df.pop(t, None)
        for aid, n in nocc.items():
            if n > 1:
                ts = toks(first_text[aid])
                for t in set(ts):
                    left = df.get(t, 0) - (n - 1)
                    if left > 0:
                        df[t] = left
                    else:
                        df.pop(t, None)
        view.df = df
        view.total_tokens = sum(
            doclen_of[o] for o, aid in aid_of_ord.items()
            if aid in atoms)
        view.live_n = len(atoms)
        # 4. Tomb + per-doc-holon removal (mirrors _retire_docs).
        view.tomb.add_live(sorted(retired))
        for doc in sorted(retired):
            ent = holons.get(doc)
            if ent is not None and ent.get("kind") is None:
                view._retract_holon_edges(doc, ent)
                del holons[doc]
        his = [seg.hi for _e, seg in good] + \
            [e["hi"] for e, _r, _m, _t in fresh]
        sealed_hi = max(his) if his else 0
        view.delta = DeltaSegment(sealed_hi)
        view.delta.hi = sealed_hi
        view.frontier = sealed_hi

    def stats(self):
        with self._lock:
            cur = self._current
            kind = None
            gen = None
            if cur is not None:
                if getattr(cur, "_is_gen", False):
                    kind = "generation"
                    gen = {"frontier": int(
                        cur._reader.root["frontier"]),
                        "overlay_atom_rows": len(
                            cur.delta.atom_rows),
                        "overlay_holon_rows": len(
                            cur.delta.holon_rows),
                        "overlay_debt": self._overlay_debt(cur),
                        "last_rebase": getattr(
                            cur, "_last_rebase", None)}
                else:
                    kind = "segmented"
            return {
                "birth": self.birth, "epoch": self.epoch,
                "retained": sorted(self._retained),
                "refs": {mx: v._refs
                         for mx, v in self._retained.items()},
                "current": cur.max_seq if cur is not None else None,
                "current_kind": kind,
                "generation": gen,
                "config_source": self.config.get("source"),
                "counters": self.counters.totals(),
            }



