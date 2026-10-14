"""Per-generation Narrow index, built from COMMITTED data only.

Build: read ACCEPT_ATOMS commits at/below the pinned generation ->
pub_refs -> meta artifacts (digest-verified) -> atoms/holons/BM25.
Atom TEXTS are read at build (budget-accounted, once per generation);
query-time display reads stay late (Q15.1a) via store_if.read_artifact.

Legs (Q1.2 P0):
  lexical: own BM25 token index over atom texts (k1=1.2, b=0.75).
  dense:   cosine over per-doc-holon centroid descriptors (Q2.1:
           dense descriptor-similarity over ACTIVE holon descriptors).
"""

import contextlib
import copy
import json
import math
import os
from collections.abc import MutableMapping

import numpy as np

from tlsys.identity import ATOM_SCHEME
from tlsys.hnsw_candidates import StaleGenerationError
from tlsys.place import LiveAuditCache, NavCounters, OrdinalCache
from tlsys.serving.lexical import B, K1, idf_of, toks

assert (K1, B) == (1.2, 0.75), "frozen BM25 constants (C2 parity)"
assert toks("Ab  C") == ["ab", "c"], "frozen tokenizer (C2 parity)"


class _UseAttached:
    pass


_USE_ATTACHED = _UseAttached()


class ReferenceNarrowIndex:
    """C1 per-generation Narrow index, build-once from committed data.

    C2 role: the BIT-IDENTICAL reference oracle (flag-off backend and
    D1 differential oracle). Everything below this docstring is the
    pre-C2 implementation, unchanged except for the two additive
    exact membership helpers (is_live_atom/live_atom_set). Product
    default is the NarrowIndex compat facade (same surface,
    segmented serving underneath; flag/env selects this class).
    """
    def __init__(self, tlstore, pinned, candidate_search=None,
                 atom_candidate_search=None):
        self.tlstore = tlstore
        self.birth, self.epoch, self.max_seq, self.triple = pinned
        self.atoms = {}   # aid -> dict(seq,doc_id,span,text_art,text_digest)
        self.holons = {}  # doc_id -> dict(seq,members,descriptor np)
        self.doc_atoms = {}
        # Lane-2 retirement: doc-level exclusion consumed at build
        # (same committed scan, no extra storage reads). Retired
        # docs' atoms never enter atoms/BM25/doc_atoms and their
        # per-doc holon never enters holons; retired_aids lets
        # descent paths distinguish retired skips from dangling refs.
        self.retired_docs = []
        self.retired_atoms = 0
        self.retired_aids = set()
        # R7-B candidate discovery (default OFF): None keeps the exact
        # dense-holon leg bit-identical. Attach a HolonCandidateIndex
        # (attach_candidate_search, generation-checked) to route
        # dense_holons through bounded HNSW discovery + exact rescore.
        # R8-B: same for the dense-atom leg (atom_candidate_search /
        # attach_atom_search); both legs default OFF, flags preserved.
        self._candidate_search = None
        self._atom_candidate_search = None
        self.last_candidate_report = None
        self.last_atom_candidate_report = None
        # M1-C separate audit state per population: one
        # caller-owned audit cache AND one ordinal cache per leg,
        # so alternating holon/atom legs no longer evict each
        # other's audit (the R8-B single-entry cache re-audited on
        # every alternation). Versions bump in _build; any
        # post-build population change must go through
        # note_population_changed.
        self._audit_cache_holons = LiveAuditCache()
        self._audit_cache_atoms = LiveAuditCache()
        self._ordinal_cache_holons = OrdinalCache()
        self._ordinal_cache_atoms = OrdinalCache()
        # M1-C work evidence: every dense-leg call (exact AND
        # via-search) records discovered/visited/rescored here.
        # Additive (new attribute); return values unchanged.
        self.nav_counters = NavCounters()
        self._holons_version = 0
        self._atoms_version = 0
        if candidate_search is not None:
            self.attach_candidate_search(candidate_search)
        if atom_candidate_search is not None:
            self.attach_atom_search(atom_candidate_search)
        self._build()
        self._build_bm25()

    @property
    def candidate_search(self):
        """Attached dense-holon discovery search, or None (M1-C
        read-only accessor for the query router)."""
        return self._candidate_search

    @property
    def atom_candidate_search(self):
        """Attached dense-atom discovery search, or None (M1-C
        read-only accessor for the query router)."""
        return self._atom_candidate_search

    def attach_candidate_search(self, search):
        """Attach HNSW discovery to the dense-holon leg (opt-in).

        Generation-checked: a search built at another pin raises
        StaleGenerationError (no cross-generation mixing). Detach
        with detach_candidate_search() to restore the exact path.
        Re-attach after a same-object search rebuild (the cached
        audit is dropped on attach).
        """
        if search.generation != self.triple:
            raise StaleGenerationError(
                f"candidate index at {search.generation}, serving "
                f"index at {self.triple}: rebuild, no mixing")
        self._candidate_search = search
        self._audit_cache_holons.invalidate()
        self._ordinal_cache_holons.invalidate()

    def detach_candidate_search(self):
        """Restore the exact dense-holon leg (flag-off behavior)."""
        self._candidate_search = None
        self.last_candidate_report = None
        self._audit_cache_holons.invalidate()
        self._ordinal_cache_holons.invalidate()

    def attach_atom_search(self, search):
        """Attach HNSW discovery to the dense-atom leg (opt-in).

        Same contract as attach_candidate_search (generation-checked,
        re-attach after a same-object rebuild, detach restores the
        exact path), for idx.dense_atoms.
        """
        if search.generation != self.triple:
            raise StaleGenerationError(
                f"candidate index at {search.generation}, serving "
                f"index at {self.triple}: rebuild, no mixing")
        self._atom_candidate_search = search
        self._audit_cache_atoms.invalidate()
        self._ordinal_cache_atoms.invalidate()

    def detach_atom_search(self):
        """Restore the exact dense-atom leg (flag-off behavior)."""
        self._atom_candidate_search = None
        self.last_atom_candidate_report = None
        self._audit_cache_atoms.invalidate()
        self._ordinal_cache_atoms.invalidate()

    def note_population_changed(self, which):
        """Bump the live-view version after a post-build change.

        which: "holons" or "atoms". The R8-B incremental audit keys
        on this version: any direct post-build mutation of
        self.holons/self.atoms (no product path does this today;
        populations are build-once per generation) must call this
        first or the next discovery call reuses a stale audit.
        """
        if which == "holons":
            self._holons_version += 1
        elif which == "atoms":
            self._atoms_version += 1
        else:
            raise ValueError(f"which must be 'holons'|'atoms': {which!r}")

    def is_live_atom(self, aid):
        """O(1) live-membership predicate (C2 facade API; exact here)."""
        return aid in self.atoms

    def live_atom_set(self):
        """Live atom ids as a frozenset (C2 facade API; exact here)."""
        return frozenset(self.atoms.keys())

    @property
    def seg_leaves(self):
        """{leaf_id: entry} over committed kind="seg-leaf" holons."""
        return {h: v for h, v in self.holons.items()
                if v.get("kind") == "seg-leaf"}

    @property
    def seg_parents(self):
        """{parent_id: entry} over kind="seg-parent" holons."""
        return {h: v for h, v in self.holons.items()
                if v.get("kind") == "seg-parent"}

    def _build(self):
        # R8-B (R7-A proposal C adoption): unbounded read via min_seq
        # frontiers (read_commits_all) + single-connection batched
        # artifact rows (same call shape as
        # ingest._committed_doc_state). Identical populations to the
        # pre-R8-B loop at every scale the old 1M window covered.
        rows = self.tlstore.read_commits_all(
            self.birth, self.epoch, self.max_seq, kind="ACCEPT_ATOMS")
        seqs = [r[0] for r in rows]
        refs = self.tlstore.pub_refs(seqs)
        arows = self.tlstore.artifact_rows(
            [a for seq in seqs for a in refs.get(seq, [])])
        by_seq = {r[0]: r for r in rows}
        retired = set()
        for seq in seqs:
            op_id = by_seq[seq][1]
            for art_id in refs.get(seq, []):
                arow = arows.get(art_id)
                if arow is None:
                    continue
                body = self.tlstore.read_artifact(art_id,
                                                  expect_digest=arow[4])
                try:
                    meta = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue  # text artifact, not meta
                if not isinstance(meta, dict):
                    continue
                if "local_repair" in meta:
                    from tlsys.local_repair import membership_metas
                    for entry in membership_metas(meta):
                        self.holons[entry["holon"]] = {
                            "seq": seq, "op_id": op_id,
                            "members": list(entry["members"]),
                            "descriptor": np.array(entry["descriptor"], dtype=np.float64),
                            "kind": entry["kind"],
                            "children": list(entry.get("children", []))}
                    continue
                ret = meta.get("retirement")
                if isinstance(ret, dict) \
                        and isinstance(ret.get("doc"), str):
                    if meta.get("atom_scheme") != ATOM_SCHEME:
                        raise ValueError(
                            f"op seq {seq}: retirement meta scheme "
                            f"{meta.get('atom_scheme')!r} != "
                            f"{ATOM_SCHEME!r}")
                    retired.add(ret["doc"])
                    continue
                if ("atom" in meta or "holon" in meta) and \
                        meta.get("atom_scheme") != ATOM_SCHEME:
                    raise ValueError(
                        f"op seq {seq}: meta scheme "
                        f"{meta.get('atom_scheme')!r} != "
                        f"{ATOM_SCHEME!r}: committed data predates "
                        "tl-sys occurrence identity; rebuild the "
                        "scratch store (no migration; see "
                        "tl-sys/ORGANIZATION-CONFORMANCE.md "
                        "section 4)")
                if "atom" in meta and "text_artifact" in meta:
                    self.atoms[meta["atom"]] = {
                        "seq": seq, "op_id": op_id,
                        "doc_id": meta["doc_id"], "span": meta["span"],
                        "text_art": meta["text_artifact"],
                        "text_digest": meta["text_digest"],
                        "descriptor": np.array(
                            meta.get("descriptor", []),
                            dtype=np.float64)}
                    self.doc_atoms.setdefault(meta["doc_id"],
                                              []).append(meta["atom"])
                elif "holon" in meta and "descriptor" in meta:
                    self.holons[meta["holon"]] = {
                        "seq": seq, "op_id": op_id,
                        "members": meta["members"],
                        "descriptor": np.array(meta["descriptor"],
                                               dtype=np.float64),
                        # M2-A hierarchy (additive): kind/children ride
                        # the entry when the committed meta carries
                        # them; default legs ignore these keys.
                        "kind": meta.get("kind"),
                        "children": list(
                            meta.get("children") or [])}
        if retired:
            # Doc-level exclusion (retirement is permanent, so the
            # filter applies regardless of marker position in the
            # scan). Per-doc holon keys are doc ids; hierarchy ids
            # carry kind prefixes doc ids can never take.
            for aid in [a for a, e in self.atoms.items()
                        if e["doc_id"] in retired]:
                self.retired_aids.add(aid)
                del self.atoms[aid]
            self.retired_atoms = len(self.retired_aids)
            for doc in retired:
                self.doc_atoms.pop(doc, None)
                ent = self.holons.get(doc)
                if ent is not None and ent.get("kind") is None:
                    # Per-doc holon only (kind-tagged hierarchy
                    # entries are never removed by doc retirement).
                    del self.holons[doc]
            self.retired_docs = sorted(retired)
        self._holons_version += 1
        self._atoms_version += 1

    def _build_bm25(self):
        self.atom_text = {}
        self.doc_len = {}
        df = {}
        postings = {}  # term -> [(aid, tf)] in atom-insertion order
        total = 0
        for aid, a in self.atoms.items():
            body = self.tlstore.read_artifact(a["text_art"],
                                              expect_digest=a["text_digest"])
            text = body.decode("utf-8")
            self.atom_text[aid] = text
            ts = toks(text)
            total += len(ts)
            self.doc_len[aid] = len(ts)
            tf = {}
            for t in ts:
                tf[t] = tf.get(t, 0) + 1
            for t, f in tf.items():
                df[t] = df.get(t, 0) + 1
                postings.setdefault(t, []).append((aid, f))
        n = max(1, len(self.atom_text))
        self.avgdl = total / n
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5))
                    for t, c in df.items()}
        self.postings = postings

    # -- legs ------------------------------------------------------
    def bm25(self, query):
        """{aid: score} over atoms with any query term.

        Posting-indexed: visits only atoms containing a query term
        (the 10M full-scan regime this replaces cost ~2.5 s/query;
        see PHASE2-REPORT §4c). Scores match bm25_fullscan up to
        floating-point summation order; query terms iterate sorted
        (deterministic, PYTHONHASHSEED-independent) and the result
        is emitted in atom-insertion order so downstream stable
        sorts tie-break exactly as the full scan did.
        """
        out = {}
        for t in sorted(set(toks(query))):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for aid, f in self.postings[t]:
                dl = self.doc_len[aid]
                num = f * (K1 + 1)
                den = f + K1 * (1 - B + B * dl / self.avgdl)
                out[aid] = out.get(aid, 0.0) + idf * num / den
        if out:
            out = {aid: out[aid] for aid in self.atom_text if aid in out}
        return out

    def bm25_fullscan(self, query):
        """Reference full-scan BM25 (pre-index implementation).

        Kept as the tested equivalence oracle for bm25(); not on
        the product path. Identical formula, constants, and
        tokenizer; iterates every atom.
        """
        qf = {}
        for t in toks(query):
            qf[t] = qf.get(t, 0) + 1
        out = {}
        for aid, text in self.atom_text.items():
            dl = self.doc_len[aid]
            tf = {}
            for t in toks(text):
                if t in qf:
                    tf[t] = tf.get(t, 0) + 1
            if not tf:
                continue
            s = 0.0
            for t, f in tf.items():
                num = f * (K1 + 1)
                den = f + K1 * (1 - B + B * dl / self.avgdl)
                s += self.idf.get(t, 0.0) * num / den
            out[aid] = s
        return out

    def dense_holons(self, qvec, candidate_search=_USE_ATTACHED,
                     candidate_k=200, ef=None,
                     include_unpublished=True):
        """[(doc_id, cosine)] over active holons, desc.

        R7-B candidate discovery (default OFF): with no search
        attached (or candidate_search=None explicitly), the exact
        full-population scan below (bit-identical flag-off behavior).
        With a HolonCandidateIndex (attached or passed explicitly),
        bounded HNSW discovery + exact rescore from live descriptors:
        stale indexed versions are reported and rescored from live
        data (never the indexed vector) when include_unpublished is
        True; unpublished live holons are unioned in and exactly
        scored. Generation mismatch raises StaleGenerationError.
        Per-call accounting lands in self.last_candidate_report.
        R8-B: the stale/unpublished audit is version-tracked (first
        call audits O(N), repeats reuse O(1); same semantics).
        M1-C: per-population audit/ordinal caches, direct-fetch
        rescore ordered by stable published ordinals, explicit
        changed_ids, and NavCounters records (exact leg too).
        """
        if candidate_search is _USE_ATTACHED:
            search = self._candidate_search
        else:
            search = candidate_search
        if search is None:
            q = np.asarray(qvec, dtype=np.float64)
            qn = float(np.linalg.norm(q)) or 1.0
            out = []
            for doc_id, h in self.holons.items():
                d = h["descriptor"]
                dn = float(np.linalg.norm(d)) or 1.0
                out.append((doc_id, float(q @ d / (qn * dn))))
            out.sort(key=lambda x: -x[1])
            self.nav_counters.record(
                "dense-holons-exact", discovered=len(out),
                visited=len(out), rescored=len(out))
            return out
        return self._dense_holons_via_search(qvec, search,
                                             candidate_k, ef,
                                             include_unpublished)

    def _dense_holons_via_search(self, qvec, search, candidate_k, ef,
                                 include_unpublished):
        if search.generation != self.triple:
            raise StaleGenerationError(
                f"candidate index at {search.generation}, serving "
                f"index at {self.triple}: rebuild, no mixing")
        q = search.query(qvec=qvec, k=candidate_k, ef=ef,
                         generation=self.triple, live=self.holons)
        audit, audit_cached = self._audit_cache_holons.audit(
            search, self.holons,
            ("narrow-holons", self.triple, self._holons_version))
        stale_live = [h for h in audit["stale"] if h in self.holons]
        cands = list(q["hids"])
        unioned = 0
        if include_unpublished:
            seen = set(cands)
            for h in stale_live + audit["unpublished"]:
                if h not in seen:
                    seen.add(h)
                    cands.append(h)
                    unioned += 1
        # M1-C exact rescore from LIVE descriptors: same cosine math
        # as the exact leg (float64, 1.0 zero-norm fallback), but
        # selected IDs are fetched DIRECTLY (keyed gets -- no
        # population loop) and ordered by stable published ordinals
        # (cached live-insertion positions: identical tie-breaks to
        # the exact leg's stable sort over the discovered subset).
        omap, ord_cached = self._ordinal_cache_holons.ordinals(
            self.holons,
            ("narrow-holons", self.triple, self._holons_version))
        qq = np.asarray(qvec, dtype=np.float64)
        qn = float(np.linalg.norm(qq)) or 1.0
        scored = []
        unknown = 0
        for doc_id in cands:
            h = self.holons.get(doc_id)
            if h is None:
                unknown += 1
                continue
            d = h["descriptor"]
            dn = float(np.linalg.norm(d)) or 1.0
            scored.append((float(qq @ d / (qn * dn)),
                           omap[doc_id], doc_id))
        scored.sort(key=lambda t: (-t[0], t[1]))
        out = [(doc_id, s) for s, _o, doc_id in scored]
        changed_ids = sorted(set(stale_live)
                             | set(audit["unpublished"]))
        self.last_candidate_report = {
            "k": q["k"], "ef": q["ef"], "search_ms": q["ms"],
            "audit_cached": audit_cached,
            "n_candidates": len(q["hids"]),
            "stale_dropped": q["stale_dropped"],
            "stale_rescored_live": stale_live
            if include_unpublished else [],
            "unpublished": audit["unpublished"],
            "include_unpublished": include_unpublished,
            "rescored": len(out),
            "n_scored_native_unknown":
                q["n_scored_native_unknown"],
            "discovered": len(q["hids"]),
            "unioned": unioned,
            "visited": len(out),
            "unknown": unknown,
            "changed_ids": changed_ids,
            "ordinals_cached": ord_cached}
        self.nav_counters.record(
            "dense-holons-nav", discovered=len(q["hids"]),
            unioned=unioned, visited=len(out),
            rescored=len(out), changed=len(changed_ids))
        return out

    def dense_atoms(self, qvec, candidate_search=_USE_ATTACHED,
                    candidate_k=200, ef=None,
                    include_unpublished=True):
        """[(aid, cosine)] over atoms, desc. Same cosine definition
        as dense_holons; used by the E1 EMIT_DENSE_ATOMS arm and by
        nothing on the default path (flag-off behavior unchanged).

        R8-B candidate discovery (default OFF, flags preserved): with
        no atom search attached (or candidate_search=None explicitly),
        the exact full-population scan below (bit-identical flag-off
        behavior). With a HolonCandidateIndex built over the atom
        population (attached via attach_atom_search or passed
        explicitly), bounded HNSW discovery + exact rescore from live
        atom descriptors, same stale/unpublished contract as
        dense_holons. Generation mismatch raises StaleGenerationError.
        Per-call accounting lands in self.last_atom_candidate_report.
        M1-C: same per-population caches, direct-fetch rescore,
        changed_ids, and NavCounters records as dense_holons.
        """
        if candidate_search is _USE_ATTACHED:
            search = self._atom_candidate_search
        else:
            search = candidate_search
        if search is None:
            q = np.asarray(qvec, dtype=np.float64)
            qn = float(np.linalg.norm(q)) or 1.0
            out = []
            for aid, a in self.atoms.items():
                dv = np.asarray(a["descriptor"], dtype=np.float64)
                dn = float(np.linalg.norm(dv)) or 1.0
                out.append((aid, float(q @ dv / (qn * dn))))
            out.sort(key=lambda x: -x[1])
            self.nav_counters.record(
                "dense-atoms-exact", discovered=len(out),
                visited=len(out), rescored=len(out))
            return out
        return self._dense_atoms_via_search(qvec, search,
                                            candidate_k, ef,
                                            include_unpublished)

    def _dense_atoms_via_search(self, qvec, search, candidate_k, ef,
                                include_unpublished):
        if search.generation != self.triple:
            raise StaleGenerationError(
                f"candidate index at {search.generation}, serving "
                f"index at {self.triple}: rebuild, no mixing")
        q = search.query(qvec=qvec, k=candidate_k, ef=ef,
                         generation=self.triple, live=self.atoms)
        audit, audit_cached = self._audit_cache_atoms.audit(
            search, self.atoms,
            ("narrow-atoms", self.triple, self._atoms_version))
        stale_live = [h for h in audit["stale"] if h in self.atoms]
        cands = list(q["hids"])
        unioned = 0
        if include_unpublished:
            seen = set(cands)
            for h in stale_live + audit["unpublished"]:
                if h not in seen:
                    seen.add(h)
                    cands.append(h)
                    unioned += 1
        # M1-C exact rescore from LIVE descriptors: same cosine math
        # as the exact leg (float64, 1.0 zero-norm fallback), but
        # selected IDs are fetched DIRECTLY (keyed gets -- no
        # population loop) and ordered by stable published ordinals
        # (cached live-insertion positions: identical tie-breaks to
        # the exact leg's stable sort over the discovered subset).
        omap, ord_cached = self._ordinal_cache_atoms.ordinals(
            self.atoms,
            ("narrow-atoms", self.triple, self._atoms_version))
        qq = np.asarray(qvec, dtype=np.float64)
        qn = float(np.linalg.norm(qq)) or 1.0
        scored = []
        unknown = 0
        for aid in cands:
            a = self.atoms.get(aid)
            if a is None:
                unknown += 1
                continue
            dv = np.asarray(a["descriptor"], dtype=np.float64)
            dn = float(np.linalg.norm(dv)) or 1.0
            scored.append((float(qq @ dv / (qn * dn)),
                           omap[aid], aid))
        scored.sort(key=lambda t: (-t[0], t[1]))
        out = [(aid, s) for s, _o, aid in scored]
        changed_ids = sorted(set(stale_live)
                             | set(audit["unpublished"]))
        self.last_atom_candidate_report = {
            "k": q["k"], "ef": q["ef"], "search_ms": q["ms"],
            "audit_cached": audit_cached,
            "n_candidates": len(q["hids"]),
            "stale_dropped": q["stale_dropped"],
            "stale_rescored_live": stale_live
            if include_unpublished else [],
            "unpublished": audit["unpublished"],
            "include_unpublished": include_unpublished,
            "rescored": len(out),
            "n_scored_native_unknown":
                q["n_scored_native_unknown"],
            "discovered": len(q["hids"]),
            "unioned": unioned,
            "visited": len(out),
            "unknown": unknown,
            "changed_ids": changed_ids,
            "ordinals_cached": ord_cached}
        self.nav_counters.record(
            "dense-atoms-nav", discovered=len(q["hids"]),
            unioned=unioned, visited=len(out),
            rescored=len(out), changed=len(changed_ids))
        return out


# ---------------------------------------------------------------------------
# C2 compat facade (Lane S; serving contract section 5).
#
# NarrowIndex keeps the Reference surface (query.py/dossier.py run
# unchanged) over a pinned ServingView: advance is O(Delta), legs are
# exact (bitwise lexical; loop-identical dense), post-build mappings
# stay mutable with eager exact derived rebuilds. Backend selection:
# explicit use_reference arg > TL_C2_REFERENCE_INDEX=1 env > explicit
# Lane-G-shaped profile's flags.serving_segmented > default C2.
# Bare stubs (object.__new__, e.g. the frozen B2 seed) default to the
# reference path via getattr guards on every override.
# ---------------------------------------------------------------------------

_REFERENCE_ENV = "TL_C2_REFERENCE_INDEX"

# S-4: explicit serving persistence (R2). Resolution order for the
# serving dir: explicit serving_dir arg > TL_C2_SERVING_DIR env >
# None (in-memory pool, no seal persistence/checkpoint/attach).
SERVING_DIR_ENV = "TL_C2_SERVING_DIR"


def _resolve_serving_dir(serving_dir):
    """(path_or_None, source). Explicit arg wins; empty env = unset."""
    if serving_dir is not None:
        return serving_dir, "explicit-arg"
    env = os.environ.get(SERVING_DIR_ENV)
    if env:
        return env, "env:" + SERVING_DIR_ENV
    return None, None


class DenseOrderDiverged(Exception):
    """Served atom assembly order drifted from mapping order.

    The segmented assembly iterates global ordinal order while the
    legacy pop iterates live-mapping order; the two agree on every
    product-reachable lifecycle path (occurrence identity forbids
    the reinsertion that would split them). If they ever disagree,
    the query path falls back to the legacy pop, tagged (never
    silently, never reordered).
    """


def _is_reference_backend(use_reference, profile):
    if use_reference is not None:
        return bool(use_reference)
    if os.environ.get(_REFERENCE_ENV) == "1":
        return True
    if isinstance(profile, dict):
        flags = profile.get("flags")
        if isinstance(flags, dict) and "serving_segmented" in flags:
            return not bool(flags["serving_segmented"])
    return False


class _ViewMapping(MutableMapping):
    """Mutable live-dict view over the facade's current ServingView.

    Reads brief-lock under the pool lock (snapshot iteration is safe
    across a concurrent advance); the bound view follows
    facade.advance_to, so mappings (and query objects holding the
    facade) stay valid across hops. Mutations apply to the live dict
    plus an eager exact derived rebuild (O(N), test-only path;
    product paths never mutate; note_population_changed as before).
    """

    def __init__(self, facade, attr):
        self._facade = facade
        self._attr = attr

    def __repr__(self):
        try:
            n = len(self)
        except Exception:  # noqa: BLE001 (debug repr only)
            n = "?"
        return f"_ViewMapping({self._attr}, n={n})"

    def __getitem__(self, key):
        with self._facade._locked_view() as view:
            row = getattr(view, self._attr)[key]
            if getattr(self._facade, "_shared_view_pool", False):
                # Same-pin facades share one live ServingView: hand out
                # an independent copy so caller mutation cannot corrupt
                # the shared view (map mutators alone do not cover this).
                # Default path keeps the exact prior alias (zero-cost).
                return copy.deepcopy(row)
            return row

    def __iter__(self):
        with self._facade._locked_view() as view:
            return iter(list(getattr(view, self._attr).keys()))

    def __len__(self):
        with self._facade._locked_view() as view:
            return len(getattr(view, self._attr))

    def __contains__(self, key):
        with self._facade._locked_view() as view:
            return key in getattr(view, self._attr)

    def __reversed__(self):
        with self._facade._locked_view() as view:
            return reversed(list(getattr(view, self._attr).keys()))

    def __setitem__(self, key, value):
        if getattr(self._facade, "_shared_view_pool", False):
            raise TypeError("shared pool mappings are read-only")
        with self._facade._locked_view() as view:
            getattr(view, self._attr)[key] = value
            view._rebuild_derived_from_live()

    def __delitem__(self, key):
        if getattr(self._facade, "_shared_view_pool", False):
            raise TypeError("shared pool mappings are read-only")
        with self._facade._locked_view() as view:
            del getattr(view, self._attr)[key]
            view._rebuild_derived_from_live()

    # Single-rebuild bulk ops (the MutableMapping mixins would
    # rebuild per key).
    def pop(self, key, *default):
        if getattr(self._facade, "_shared_view_pool", False):
            raise TypeError("shared pool mappings are read-only")
        with self._facade._locked_view() as view:
            d = getattr(view, self._attr)
            if key in d:
                out = d.pop(key)
                view._rebuild_derived_from_live()
                return out
            if default:
                return default[0]
            raise KeyError(key)

    def popitem(self):
        if getattr(self._facade, "_shared_view_pool", False):
            raise TypeError("shared pool mappings are read-only")
        with self._facade._locked_view() as view:
            d = getattr(view, self._attr)
            out = d.popitem()
            view._rebuild_derived_from_live()
            return out

    def clear(self):
        if getattr(self._facade, "_shared_view_pool", False):
            raise TypeError("shared pool mappings are read-only")
        with self._facade._locked_view() as view:
            getattr(view, self._attr).clear()
            view._rebuild_derived_from_live()

    def update(self, *args, **kw):
        if getattr(self._facade, "_shared_view_pool", False):
            raise TypeError("shared pool mappings are read-only")
        with self._facade._locked_view() as view:
            getattr(view, self._attr).update(*args, **kw)
            view._rebuild_derived_from_live()

    def setdefault(self, key, default=None):
        if getattr(self._facade, "_shared_view_pool", False):
            raise TypeError("shared pool mappings are read-only")
        with self._facade._locked_view() as view:
            d = getattr(view, self._attr)
            if key in d:
                return d[key]
            d[key] = default
            view._rebuild_derived_from_live()
            return default


class _LazyCopyMapping(MutableMapping):
    """Lazy derived mapping with copy-on-write mutation.

    Reads compute from the live view under a brief pool lock.
    Iteration order is sorted-key order (C1's first-seen order is
    not reproduced; content and legs are identical). The first
    mutation snapshots the full content to a plain dict (C1-analog
    staleness: the copy never reflects later view changes, exactly
    like C1's build-once dicts never reflect post-build mutation).
    """

    def __init__(self, facade):
        self._facade = facade
        self._copy = None

    def _live_get(self, view, key):
        raise NotImplementedError

    def _live_keys(self, view):
        raise NotImplementedError

    def _live_len(self, view):
        return len(self._live_keys(view))

    def __getitem__(self, key):
        if self._copy is not None:
            return self._copy[key]
        with self._facade._locked_view() as view:
            return self._live_get(view, key)

    def __iter__(self):
        if self._copy is not None:
            return iter(list(self._copy.keys()))
        with self._facade._locked_view() as view:
            return iter(list(self._live_keys(view)))

    def __len__(self):
        if self._copy is not None:
            return len(self._copy)
        with self._facade._locked_view() as view:
            return self._live_len(view)

    def __contains__(self, key):
        if self._copy is not None:
            return key in self._copy
        try:
            self.__getitem__(key)
            return True
        except KeyError:
            return False

    def __reversed__(self):
        return reversed(list(iter(self)))

    def _materialize(self):
        if self._copy is None:
            with self._facade._locked_view() as view:
                self._copy = {k: self._live_get(view, k)
                              for k in self._live_keys(view)}
        return self._copy

    def __setitem__(self, key, value):
        self._materialize()[key] = value

    def __delitem__(self, key):
        del self._materialize()[key]

    def pop(self, key, *default):
        c = self._materialize()
        if key in c:
            return c.pop(key)
        if default:
            return default[0]
        raise KeyError(key)

    def popitem(self):
        return self._materialize().popitem()

    def clear(self):
        self._materialize().clear()

    def update(self, *args, **kw):
        self._materialize().update(*args, **kw)

    def setdefault(self, key, default=None):
        return self._materialize().setdefault(key, default)


def _live_postings_run(view, term):
    """[(aid, tf)] for one term in global ordinal order (live only).

    Raises KeyError when no live row carries the term (C1 dict
    semantics: absent terms are absent keys)."""
    run = []
    if getattr(view, "_is_gen", False):
        return _live_postings_run_gen(view, term)
    for s in view.segments:
        o_arr, f_arr = s.lex.postings_of(term)
        for o, f in zip(o_arr.tolist(), f_arr.tolist()):
            aid = s.aid_of_ord.get(int(o))
            if aid in view.atoms:
                run.append((int(o), aid, int(f)))
    for o, f in view.delta.postings.get(term, ()):
        aid = view.aid_of_ord.get(int(o))
        if aid in view.atoms:
            run.append((int(o), aid, int(f)))
    if not run:
        raise KeyError(term)
    run.sort(key=lambda t: t[0])
    return [(aid, f) for _o, aid, f in run]


def _live_postings_run_gen(view, term):
    """Gen-v2 twin: base global run + overlay run, ordinal order."""
    run = []
    o_arr, f_arr = view._reader.postings_of(term)
    for o, f in zip(o_arr.tolist(), f_arr.tolist()):
        aid = view._reader.aids[int(o)]
        if aid in view.atoms:
            run.append((int(o), aid, int(f)))
    for o, f in view.delta.postings.get(term, ()):
        aid = view.ov_aid_of_ord.get(int(o))
        if aid is None:
            try:
                aid = view._reader.aid_of_ord(int(o))
            except KeyError:
                continue
        if aid in view.atoms:
            run.append((int(o), aid, int(f)))
    if not run:
        raise KeyError(term)
    run.sort(key=lambda t: t[0])
    return [(aid, f) for _o, aid, f in run]


class _PostingsMapping(_LazyCopyMapping):
    def _live_get(self, view, key):
        return _live_postings_run(view, key)

    def _live_keys(self, view):
        return sorted(view.df)

    def _live_len(self, view):
        return len(view.df)


class _IdfMapping(_LazyCopyMapping):
    def _live_get(self, view, key):
        c = view.df.get(key)
        if c is None:
            raise KeyError(key)
        return idf_of(max(1, view.live_n), c)

    def _live_keys(self, view):
        return sorted(view.df)

    def _live_len(self, view):
        return len(view.df)


class _DocLenMapping(_LazyCopyMapping):
    def _live_get(self, view, key):
        if key not in view.atoms:
            raise KeyError(key)
        return view.doclen_of[view.ord_atom[key]]

    def _live_keys(self, view):
        return list(view.atoms.keys())

    def _live_len(self, view):
        return len(view.atoms)


class NarrowIndex(ReferenceNarrowIndex):
    """C2 compat facade: the Reference surface over ServingViews.

    Default backend is segmented serving (immutable segments + delta
    + tombstones, pinned views, O(Delta) advance). use_reference=True
    (or TL_C2_REFERENCE_INDEX=1, or an explicit Lane-G-shaped profile
    with flags.serving_segmented=False) selects the bit-identical
    Reference behavior. query.py/dossier.py run unchanged; hot paths
    use live_atom_set()/nomination_maps(). advance_to(pin) hops this
    object to a new pin (mappings stay valid); downstream caches
    (query._dense_pop, HierQuery maps, relquery views) key on the
    triple/version and rebuild. Same-facade concurrent query +
    advance_to is caller error (documented); pool-level multi-pin
    concurrency is the supported shape.
    """

    def __init__(self, tlstore, pinned, candidate_search=None,
                 atom_candidate_search=None, use_reference=None,
                 serving_dir=None, profile=None, stages=None, view_pool=None):
        self._use_reference = _is_reference_backend(use_reference,
                                                    profile)
        self._serving_dir, self._serving_source = _resolve_serving_dir(
            serving_dir)
        self._profile_arg = profile
        # S5S: optional attach stage-split sink for the construction
        # acquire (additive; None preserves exact prior behavior).
        self._stages_arg = stages
        if view_pool is not None:
            if self._use_reference:
                raise ValueError("view_pool requires segmented serving")
            if view_pool.tlstore is not tlstore or (view_pool.birth, view_pool.epoch) != tuple(pinned[:2]):
                raise ValueError("view_pool belongs to a different source incarnation")
            if view_pool.serving_dir != self._serving_dir or view_pool.config != self._serving_config():
                raise ValueError("view_pool serving configuration differs")
        self._shared_view_pool = view_pool is not None
        self._pool = view_pool
        self._view = None
        super().__init__(tlstore, pinned, candidate_search,
                         atom_candidate_search)

    @contextlib.contextmanager
    def _locked_view(self):
        view = getattr(self, "_view", None)
        if view is None:
            yield None
            return
        lock = view._pool_lock
        if lock is None:
            view._require_live()
            yield view
        else:
            with lock:
                view._require_live()
                yield view

    def _serving_config(self):
        from tlsys.serving.provisional import serving_config
        return serving_config(self._profile_arg)

    # -- build (branched; reference path is super()'s exact code) --
    def _build(self):
        if getattr(self, "_use_reference", True):
            super()._build()
            return
        from tlsys.serving.view import ViewPool
        if self._pool is None:
            self._pool = ViewPool(
                self.tlstore, self.birth, self.epoch,
                serving_dir=self._serving_dir,
                config=self._serving_config())
        self._view = self._pool.acquire(
            (self.birth, self.epoch, self.max_seq, self.triple),
            stages=getattr(self, "_stages_arg", None))
        self.atoms = _ViewMapping(self, "atoms")
        self.holons = _ViewMapping(self, "holons")
        self.doc_atoms = _ViewMapping(self, "doc_atoms")
        self.retired_docs = self._view.retired_docs
        self.retired_atoms = self._view.retired_atoms
        self.retired_aids = self._view.retired_aids_set
        self._holons_version += 1
        self._atoms_version += 1

    def _build_bm25(self):
        if getattr(self, "_use_reference", True):
            super()._build_bm25()
            return
        self.atom_text = _ViewMapping(self, "atom_text")
        self.doc_len = _DocLenMapping(self)
        self.postings = _PostingsMapping(self)
        self.idf = _IdfMapping(self)
        self.avgdl = self._view.avgdl

    # -- legs (reference path: super()'s exact code, incl. stubs) --
    @property
    def seg_leaves(self):
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_view", None) is None:
            return super().seg_leaves
        with self._locked_view() as view:
            # View property (v1-identical values; gen-correct merge).
            return dict(view.seg_leaves)

    @property
    def seg_parents(self):
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_view", None) is None:
            return super().seg_parents
        with self._locked_view() as view:
            # View property (v1-identical values; gen-correct merge).
            return dict(view.seg_parents)

    def bm25(self, query):
        if getattr(self, "_use_reference", True):
            return super().bm25(query)
        with self._locked_view() as view:
            return view.bm25(query)

    def bm25_fullscan(self, query):
        if getattr(self, "_use_reference", True):
            return super().bm25_fullscan(query)
        with self._locked_view() as view:
            return view.bm25_fullscan(query)

    def dense_holons(self, qvec, candidate_search=_USE_ATTACHED,
                     candidate_k=200, ef=None,
                     include_unpublished=True):
        if getattr(self, "_use_reference", True):
            return super().dense_holons(
                qvec, candidate_search, candidate_k, ef,
                include_unpublished)
        with self._locked_view():
            # Inherited exact loop + via-search paths over the live
            # mappings (loop-identical to the reference leg).
            return super().dense_holons(
                qvec, candidate_search, candidate_k, ef,
                include_unpublished)

    def dense_atoms(self, qvec, candidate_search=_USE_ATTACHED,
                    candidate_k=200, ef=None,
                    include_unpublished=True):
        if getattr(self, "_use_reference", True):
            return super().dense_atoms(
                qvec, candidate_search, candidate_k, ef,
                include_unpublished)
        with self._locked_view():
            return super().dense_atoms(
                qvec, candidate_search, candidate_k, ef,
                include_unpublished)

    # -- C2 additive API (contract section 5) --
    def is_live_atom(self, aid):
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_view", None) is None:
            return super().is_live_atom(aid)
        with self._locked_view() as view:
            return aid in view.atoms

    def live_atom_set(self):
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_view", None) is None:
            return super().live_atom_set()
        with self._locked_view() as view:
            return view.live_atom_set()

    def nomination_maps(self):
        """(atom_leaves, leaf_parents, key), incrementally maintained.

        Shared read-only refs; HierQuery delegates when present and
        builds as before otherwise (reference backend / stubs raise
        AttributeError here and take the fallback).
        """
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_view", None) is None:
            raise AttributeError("no serving view (reference backend)")
        with self._locked_view() as view:
            return (view.atom_leaves, view.leaf_parents,
                    (id(self), self.triple, self._holons_version,
                     len(view.atom_leaves), len(view.leaf_parents)))

    @property
    def serving_view(self):
        return getattr(self, "_view", None)

    @property
    def serving_dir(self):
        """Resolved persistence dir (explicit arg > env > None)."""
        return getattr(self, "_serving_dir", None)

    @property
    def serving_source(self):
        """Where serving_dir resolved from (S-4 receipt field)."""
        return getattr(self, "_serving_source", None)

    def dense_served_pop(self, which):
        """(ids, f64 mat, norms) from serving state, mapping order.

        S-4: the segmented dense assembly for the Narrow vec legs.
        Reads the serving view's segment-aware cached assembly
        (segments FP32 + exact overrides + delta, one stack per view
        shared across query objects) and verifies mapping order
        against the live dict (O(N) key compare on assembly only;
        the BLAS inputs are then bitwise the legacy pop's). Returns
        None without a serving view (reference backend / stubs:
        caller takes the legacy pop, tagged); raises
        DenseOrderDiverged if mapping order ever drifts from ordinal
        order (caller falls back to the legacy pop, tagged). Other
        errors propagate (never a silent legacy fallback).
        """
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_view", None) is None:
            return None
        with self._locked_view() as view:
            if which == "holons":
                return view._dense_holons_assembled()
            asm_ids, mat, norms = view._dense_atoms_assembled()
            if list(view.atoms.keys()) != list(asm_ids):
                raise DenseOrderDiverged(
                    "mapping order drifted from ordinal assembly "
                    "order; caller falls back to the legacy pop")
            return list(asm_ids), mat, norms

    def dense_served_head(self, which, qvec, topk):
        """Exact served head without assembling any triple (gen v2).

        Closure S: generation-backed views rank base + overlay
        blocks separately and merge (no restack, no full sort for
        heads). Returns the ranked head list, or None without a
        generation-backed serving view (caller takes the pop path).
        Counts executed rows on the view (same keys as the full
        legs); the caller must NOT double-count via note_dense.
        """
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_view", None) is None:
            return None
        with self._locked_view() as view:
            if not getattr(view, "_is_gen", False):
                return None
            if which == "holons":
                return view.dense_holons_head(qvec, topk)
            return view.dense_atoms_head(qvec, topk)

    def note_dense_scored(self, which, n):
        """Record one executed served vec-leg call (R5 units).

        n = executed native rows this call (the full population is
        scored every call on the exact path; there is no eligibility
        mask here). Uses the same keys as the view full legs, so
        Lane-G export units match: atoms -> dense_rescore_rows,
        holons -> holon_rows_scored. In-RAM matvec operand bytes are
        deliberately NOT folded into bytes_read (physical file bytes
        only); the executed logical bytes are n*(dim*8+8), derived.
        """
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_view", None) is None:
            raise AttributeError("no serving view (reference backend)")
        with self._locked_view() as view:
            if which == "atoms":
                view.counters.record(dense_rescore_rows=n)
            else:
                view.counters.record(holon_rows_scored=n)

    def seal_now(self):
        """Seal the current delta to a segment (S-4 explicit persist).

        Persists when serving_dir is set; returns the sealed Segment
        (None when the delta is empty). C2 backend only.
        """
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_pool", None) is None:
            raise AttributeError("no serving view (reference backend)")
        with self._pool.guarded():
            return self._pool.seal_locked(self._view)

    def checkpoint_now(self):
        """Seal fully + persist manifest + checkpoint file (S-4).

        Returns the manifest payload. Requires serving_dir (else
        CheckpointError from the pool). C2 backend only.
        """
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_pool", None) is None:
            raise AttributeError("no serving view (reference backend)")
        return self._pool.checkpoint(self._view)

    def advance_to(self, pin):
        """Hop this facade to `pin` (same object; mappings stay valid).

        C2: O(Delta) pool advance (retired/avgdl refreshed, versions
        bumped so downstream caches rebuild; a (birth, epoch) change
        transparently swaps pools; older pins route to
        ancestor-advance/cold-build). Reference: in-place rebuild
        (attached searches go stale-generation, fail-closed typed).
        """
        if getattr(self, "_shared_view_pool", False):
            raise RuntimeError("shared pool facade is fixed; acquire a new facade")
        if getattr(self, "_use_reference", True):
            self.birth, self.epoch, self.max_seq, self.triple = pin
            self.atoms = {}
            self.holons = {}
            self.doc_atoms = {}
            self.retired_docs = []
            self.retired_atoms = 0
            self.retired_aids = set()
            self._build()
            self._build_bm25()
            return self
        from tlsys.serving.view import (
            EpochChangedError, RewindError, ViewPool)
        with self._pool.guarded():
            old = self._view
            try:
                new = self._pool.advance(old, pin)
            except EpochChangedError:
                old_pool = self._pool
                self._pool = ViewPool(
                    self.tlstore, pin[0], pin[1],
                    serving_dir=self._serving_dir,
                    config=self._serving_config())
                new = self._pool.acquire(pin)
                old_pool.release(old)
            except RewindError:
                # Older pin: pool routes to ancestor-advance/cold-build.
                new = self._pool.acquire(pin)
                self._pool.release(old)
            else:
                self._pool.release(old)
            self._view = new
            self.birth, self.epoch, self.max_seq, self.triple = pin
            self.retired_docs = new.retired_docs
            self.retired_atoms = new.retired_atoms
            self.retired_aids = new.retired_aids_set
            self.avgdl = new.avgdl
            self._holons_version += 1
            self._atoms_version += 1
            return self

    def serve_counters(self):
        """Serving receipt: backend, config source, pool/view stats."""
        if getattr(self, "_use_reference", True) or \
                getattr(self, "_pool", None) is None:
            return {"backend": "reference", "pin": self.triple}
        with self._pool.guarded():
            st = self._pool.stats()
        st["backend"] = "c2"
        st["pin"] = self.triple
        # S-4 persistence receipt (additive; None when in-memory).
        st["serving_dir"] = getattr(self, "_serving_dir", None)
        st["serving_source"] = getattr(self, "_serving_source", None)
        st["checkpoint_present"] = self._pool._has_checkpoint()
        return st
