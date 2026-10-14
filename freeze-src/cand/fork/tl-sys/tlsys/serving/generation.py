"""Persisted query-ready serving generations (Closure S, gen v2).

A generation is the persisted CURRENT serving state: indexed immutable
binary blocks (ordinals, locations, statistics, eligibility, reverse
indexes) plus a small delta overlay for the unpublished suffix. Fresh
attach opens the generation root + indexes and consumes only the
suffix -- no replay of sealed rows, no eager corpus-sized Python dict
rebuilds. History stays in the source log, retained generations, and
export; current serving never replays historical holon versions
(only the latest row per hid is persisted).

Layout (serving_dir/):
  manifest.json            v1 (format 1) or v2 pointer (format 2)
  manifest.v1.json         retained v1 pointer (after first v2 publish)
  checkpoint.json / checkpoint.v1.json (v1 restart pointers)
  s<lo>-<hi>/              v1 segments (retained read-only after v2)
  generation/              current gen-v2 root + blocks (atomic swap)
  generations/gen-<frontier>/  retained old generations (reader safety)
  quarantined/             failed generations/segments (never served)

Old-reader refusal: v2 publish rewrites manifest.json with
format_version 2, which v1 readers reject (fail closed, loud).
New readers route: generation/ present -> v2; else v1 manifest.
Mmap is an access mechanism only: every block is hash-verified
against the root BEFORE parsing (verify-then-parse, exact bytes),
and source text is digest-verified when read.
"""

import hashlib
import io
import json
import os
import shutil
import time

import numpy as np

from tlsys.serving import ANALYZER_ID, CONFIG_ID
from tlsys.serving import faults as faults_mod
from tlsys.serving.lexical import ORD_DTYPE, ORD_MAX, TF_DTYPE, TF_MAX

GEN_VERSION = 2
GEN_FORMAT_VERSION = 2
GEN_DIRNAME = "generation"
GEN_FILENAME = "generation.json"
GEN_RETAINED_DIRNAME = "generations"
GEN_TMP_PREFIX = "generation.tmp-"
V1_MANIFEST_BACKUP = "manifest.v1.json"
V1_CHECKPOINT_BACKUP = "checkpoint.v1.json"

# Logical block key -> filename under generation/.
BLOCK_FILES = {
    "aids": "aids.npy",
    "aid_sorted": "aid_sorted.npy",
    "aid_sorted_ord": "aid_sorted_ord.npy",
    "vectors": "vectors.npy",
    "norms_f64": "norms_f64.npy",
    "ov_ord": "ov_ord.npy",
    "ov_mat": "ov_mat.npy",
    "live": "live.npy",
    "doclen": "doclen.npy",
    "terms": "terms.json",
    "term_offsets": "term_offsets.npy",
    "post_ord": "post_ord.npy",
    "post_tf": "post_tf.npy",
    "term_df": "term_df.npy",
    "text_blob": "text.blob",
    "text_idx": "text.idx.npy",
    "docs": "docs.json",
    "docs_sorted": "docs_sorted.npy",
    "docs_sorted_pos": "docs_sorted_pos.npy",
    "doc_offsets": "doc_offsets.npy",
    "doc_ords": "doc_ords.npy",
    "meta_seq": "meta_seq.npy",
    "meta_doc": "meta_doc.npy",
    "meta_span": "meta_span.npy",
    "meta_op": "meta_op.npy",
    "meta_tart": "meta_tart.npy",
    "meta_tdigest": "meta_tdigest.npy",
    "hids": "hids.npy",
    "hid_sorted": "hid_sorted.npy",
    "hid_sorted_ord": "hid_sorted_ord.npy",
    "holon_vectors": "holon_vectors.npy",
    "hseq": "hseq.npy",
    "hop": "hop.npy",
    "hkind": "hkind.npy",
    "hmem_offsets": "hmem_offsets.npy",
    "hmem_vals": "hmem_vals.npy",
    "hch_offsets": "hch_offsets.npy",
    "hch_vals": "hch_vals.npy",
    "edge_al_keys": "edge_al_keys.npy",
    "edge_al_offsets": "edge_al_offsets.npy",
    "edge_al_vals": "edge_al_vals.npy",
    "edge_lp_keys": "edge_lp_keys.npy",
    "edge_lp_offsets": "edge_lp_offsets.npy",
    "edge_lp_vals": "edge_lp_vals.npy",
    "tombstones": "tombstones.json",
}


class GenerationError(Exception):
    pass


def _sha_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def root_digest_of(payload):
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _read_verified(gendir, name, digests):
    """Read a generation file ONCE, hash-as-read, verify-before-parse.

    Returns the file bytes. Raises GenerationError on a missing pin
    or a digest mismatch (caller quarantines; never serve unsure).
    """
    want = digests.get(name)
    if want is None:
        raise GenerationError(f"{gendir}/{name}: no pinned digest "
                              "(fail closed)")
    with open(os.path.join(gendir, name), "rb") as f:
        data = f.read()
    if _sha_bytes(data) != want:
        raise GenerationError(f"{gendir}/{name}: digest mismatch "
                              "(quarantine)")
    return data


def read_root(gendir):
    """Read + self-verify the generation root (fail closed)."""
    path = os.path.join(gendir, GEN_FILENAME)
    with open(path, "rb") as f:
        raw = f.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise GenerationError(f"{path}: root is not valid JSON: {e}")
    digest = payload.pop("digest", None)
    if payload.get("gen_version") != GEN_VERSION:
        raise GenerationError(
            f"{path}: gen_version {payload.get('gen_version')} != "
            f"{GEN_VERSION} (fail closed)")
    if payload.get("config_id") != CONFIG_ID or \
            payload.get("analyzer_id") != ANALYZER_ID:
        raise GenerationError(f"{path}: config/analyzer skew (fail closed)")
    if digest != root_digest_of(payload):
        raise GenerationError(f"{path}: root digest mismatch (fail closed)")
    payload["digest"] = digest
    return payload


def serving_pointer(serving_dir):
    """Classify a serving directory: 'gen2', 'v1', or 'empty'.

    gen2: generation/generation.json verifies (root only; blocks are
    verified at open). v1: manifest.json with format_version 1 (or a
    v1 backup pair). Anything else fails closed (GenerationError),
    including a v2 manifest pointer without a verifiable generation.
    """
    if serving_dir is None:
        return "empty"
    gendir = os.path.join(serving_dir, GEN_DIRNAME)
    if os.path.isfile(os.path.join(gendir, GEN_FILENAME)):
        read_root(gendir)  # raises when unverifiable
        return "gen2"
    man = os.path.join(serving_dir, "manifest.json")
    if os.path.isfile(man):
        with open(man) as f:
            try:
                payload = json.load(f)
            except ValueError as e:
                raise GenerationError(f"{man}: invalid JSON: {e}")
        if payload.get("format_version") == GEN_FORMAT_VERSION:
            raise GenerationError(
                f"{man}: v2 pointer without a verifiable generation "
                "(fail closed)")
        return "v1"
    if os.path.isfile(os.path.join(serving_dir, V1_MANIFEST_BACKUP)):
        return "v1"
    return "empty"


def _exact_f64_rows(view):
    """Exact f64 descriptor row per ordinal (all ords, live+retired).

    Same precedence as the view dense assembly (live _atom_overrides
    > sealed segment rows > delta rows), so generation dense inputs
    are bitwise the view's. Returns (rows dict ord->f64 array, dim).
    """
    pos = {}
    for s in view.segments:
        for o, i in s.idx_of_ord.items():
            pos[int(o)] = ("seg", s, int(i))
    for i, r in enumerate(view.delta.atom_rows):
        pos[int(r["ordinal"])] = ("delta", None, int(i))
    rows = {}
    dim = int(getattr(view, "dim", 0) or 0)
    for o in range(len(view.ord_atom)):
        ov = view._atom_overrides.get(o)
        if ov is not None:
            rows[o] = np.asarray(ov, dtype=np.float64).copy()
            continue
        hit = pos.get(o)
        if hit is None:
            raise GenerationError(
                f"ordinal {o}: no sealed/delta row (fail closed)")
        kind, s, i = hit
        if kind == "seg":
            rows[o] = s.atom_descriptor_f64(i)
        else:
            d = view.delta.atom_rows[i].get("descriptor")
            if d is None:
                rows[o] = view.delta.vec_rows[i].astype(np.float64)
            else:
                rows[o] = np.asarray(d, dtype=np.float64)
        if rows[o].size and not dim:
            dim = int(rows[o].size)
    for o, r in rows.items():
        if r.size != dim:
            raise GenerationError(
                f"ordinal {o}: heterogeneous dim {r.size} != {dim} "
                "(fail closed)")
    return rows, dim


def _gather_ord_meta(view):
    """ord -> atom meta (sealed/delta rows, live entries win).

    Covers every ordinal 0..N-1 (fail closed on gaps). Live entry
    meta wins (re-commit latest seq/op, like C1 overwrite).
    """
    meta = {}
    for s in view.segments:
        for r in s.atom_rows:
            meta[int(r["ordinal"])] = {
                "aid": r["aid"], "seq": r["seq"],
                "op_id": r["op_id"], "doc_id": r["doc_id"],
                "span": r["span"], "text_art": r["text_art"],
                "text_digest": r["text_digest"]}
    for r in view.delta.atom_rows:
        meta[int(r["ordinal"])] = {
            "aid": r["aid"], "seq": r["seq"], "op_id": r["op_id"],
            "doc_id": r["doc_id"], "span": r["span"],
            "text_art": r.get("text_art"),
            "text_digest": r.get("text_digest")}
    for aid, e in view.atoms.items():
        o = view.ord_atom[aid]
        meta[int(o)] = {
            "aid": aid, "seq": e.get("seq"),
            "op_id": e.get("op_id"), "doc_id": e.get("doc_id"),
            "span": e.get("span"), "text_art": e.get("text_art"),
            "text_digest": e.get("text_digest")}
    missing = [o for o in range(len(view.ord_atom)) if o not in meta]
    if missing:
        raise GenerationError(
            f"ordinals without meta rows: {missing[:8]} (fail closed)")
    for o, m in meta.items():
        if m["aid"] != view.aid_of_ord.get(o):
            raise GenerationError(
                f"ordinal {o}: meta aid drift (fail closed)")
    return meta


def _gather_ord_texts(view, ord_meta):
    """ord -> text (live texts win; sealed/delta rows cover retired)."""
    texts = {}
    for s in view.segments:
        for r, t in zip(s.atom_rows, s.texts):
            texts[int(r["ordinal"])] = t
    for r, t in zip(view.delta.atom_rows, view.delta.texts):
        texts[int(r["ordinal"])] = t
    for aid, t in view.atom_text.items():
        if aid in view.atoms:
            texts[int(view.ord_atom[aid])] = t
    missing = [o for o in range(len(view.ord_atom)) if o not in texts]
    if missing:
        raise GenerationError(
            f"ordinals without texts: {missing[:8]} (fail closed)")
    return texts


def _global_postings(view):
    """term -> global ordinal-ascending run (segments + delta).

    Segments are disjoint + view-ordered and the delta holds newer
    ordinals, so concatenation is ordinal-ascending; verified here
    (fail closed) rather than assumed.
    """
    runs = {}
    for s in view.segments:
        for i, t in enumerate(s.lex.terms):
            a, b = int(s.lex.offsets[i]), int(s.lex.offsets[i + 1])
            ro = s.lex.post_ord[a:b].astype(np.int64).tolist()
            rf = s.lex.post_tf[a:b].astype(np.int64).tolist()
            if ro:
                runs.setdefault(t, []).append((ro, rf))
    for t, run in view.delta.postings.items():
        if run:
            runs.setdefault(t, []).append(
                ([int(o) for o, _f in run],
                 [int(f) for _o, f in run]))
    out = {}
    for t, parts in runs.items():
        o_all = [o for ro, _rf in parts for o in ro]
        f_all = [f for _ro, rf in parts for f in rf]
        if any(b < a for a, b in zip(o_all, o_all[1:])):
            raise GenerationError(
                f"term {t!r}: global run not ordinal-ascending "
                "(fail closed)")
        if len(set(o_all)) != len(o_all):
            raise GenerationError(
                f"term {t!r}: duplicate ordinals (fail closed)")
        out[t] = (o_all, f_all)
    return out


def _csr_from_map(keys_sorted, vals_of):
    """CSR (keys, offsets, vals) over sorted keys; vals int lists."""
    offsets = [0]
    vals = []
    for k in keys_sorted:
        v = [int(x) for x in vals_of(k)]
        vals.extend(v)
        offsets.append(len(vals))
    return (np.array(keys_sorted, dtype=object),
            np.array(offsets, dtype=np.int64),
            np.array(vals, dtype=np.int64))


def build_generation_blocks(view, tmpdir, counters=None):
    """Derive + verify every block from a live v1 view (no source I/O).

    Returns the root payload WITHOUT digest (caller adds source
    verification + digest), and a work receipt. Raises
    GenerationError (fail closed) on any gap or incoherence.
    Construction work is population work (counted by the caller).
    Holons persist live-only in v1-ordinal order (A29); retired
    ord_holon slots are absorbed, live refs to non-live hids refuse.
    """
    t0 = time.monotonic()
    os.makedirs(tmpdir, exist_ok=True)
    n_ord = len(view.ord_atom)
    for o in range(n_ord):
        if view.aid_of_ord.get(o) is None or \
                view.ord_atom.get(view.aid_of_ord[o]) != o:
            raise GenerationError(
                f"ordinal map not contiguous at {o} (fail closed)")
    aids = [view.aid_of_ord[o] for o in range(n_ord)]
    live = np.zeros((n_ord,), dtype=bool)
    for aid in view.atoms:
        live[int(view.ord_atom[aid])] = True
    doclen = np.zeros((n_ord,), dtype=np.int64)
    for o, dl in view.doclen_of.items():
        doclen[int(o)] = int(dl)
    # -- meta + texts (verified against pinned digests) --------------
    ord_meta = _gather_ord_meta(view)
    ord_texts = _gather_ord_texts(view, ord_meta)
    unverified = []
    for o in range(n_ord):
        want = ord_meta[o].get("text_digest")
        body = ord_texts[o].encode("utf-8")
        if want is None:
            unverified.append(o)
            continue
        if _sha_bytes(body) != want:
            raise GenerationError(
                f"ordinal {o}: text bytes fail pinned digest "
                "(fail closed)")
    # -- dense exact rows --------------------------------------------
    rows, dim = _exact_f64_rows(view)
    mat64 = np.stack([rows[o] for o in range(n_ord)]).reshape(
        n_ord, dim) if n_ord else np.empty((0, 0))
    mat32 = np.ascontiguousarray(mat64.astype(np.float32))
    norms = np.linalg.norm(mat64, axis=1) if n_ord \
        else np.empty((0,))
    norms = np.asarray(norms, dtype=np.float64)
    norms[norms == 0.0] = 1.0
    back = mat32.astype(np.float64).reshape(n_ord, dim) if n_ord \
        else np.empty((0, 0))
    ov_ord = np.nonzero([bool(np.any(back[o] != mat64[o]))
                         for o in range(n_ord)])[0].astype(np.int64) \
        if n_ord else np.empty((0,), dtype=np.int64)
    ov_mat = np.ascontiguousarray(mat64[ov_ord]) if len(ov_ord) \
        else np.empty((0, dim))
    # -- global lexicon ----------------------------------------------
    post = _global_postings(view)
    terms = sorted(post)
    # df self-check: pinned live df equals live postings per term.
    for t in terms:
        o_all, _f = post[t]
        live_c = sum(1 for o in o_all if live[o])
        if int(view.df.get(t, 0)) != live_c:
            raise GenerationError(
                f"term {t!r}: pinned df {view.df.get(t, 0)} != live "
                f"postings {live_c} (fail closed)")
    extra_df = [t for t in view.df if t not in post]
    if extra_df:
        raise GenerationError(
            f"df terms without postings: {extra_df[:5]} (fail closed)")
    # doclen self-check: tf sums per ord equal pinned doclen.
    tf_sum = np.zeros((n_ord,), dtype=np.int64)
    for _t, (o_all, f_all) in post.items():
        for o, f in zip(o_all, f_all):
            tf_sum[o] += f
    if n_ord and bool(np.any(tf_sum != doclen)):
        bad = np.nonzero(tf_sum != doclen)[0][:5].tolist()
        raise GenerationError(
            f"doclen/tf-sum mismatch at {bad} (fail closed)")
    offsets = [0]
    po_all = []
    pf_all = []
    for t in terms:
        o_all, f_all = post[t]
        if o_all and (min(o_all) < 0 or max(o_all) > ORD_MAX):
            raise GenerationError(
                f"term {t!r}: ordinal outside packed range (fail closed)")
        if f_all and max(f_all) > TF_MAX:
            raise GenerationError(
                f"term {t!r}: tf outside packed range (fail closed)")
        po_all.extend(o_all)
        pf_all.extend(f_all)
        offsets.append(len(po_all))
    # -- docs adjacency (C1 first-seen doc order + sorted index) ----
    # doc_offsets/doc_ords follow first-seen doc order (D1 order
    # parity); docs_sorted (+positions) serves name lookup.
    docs = list(view.doc_atoms)
    docs_sorted = sorted(docs)
    doc_offsets = [0]
    doc_ords = []
    for d in docs:
        run = [view.ord_atom[a] for a in view.doc_atoms[d]]
        doc_ords.extend(int(o) for o in run)
        doc_offsets.append(len(doc_ords))
    doc_idx = {d: i for i, d in enumerate(docs)}
    # -- holons latest-only (no version replay) ----------------------
    # A29 (S-F1 build tolerance): retired doc-holons keep their v1
    # ord_holon slots while their records are gone (v1 holon
    # ordinals are append-only identity, verified on restore, so
    # the view never renumbers them). The generation persists
    # LIVE holons only, in v1-ordinal order (deterministic; a
    # no-op when nothing is retired), with compacted
    # generation-local ordinals. Any live reference to a
    # non-live hid fails closed below (never silently skipped).
    if sorted(view.ord_holon.values()) != \
            list(range(len(view.ord_holon))):
        raise GenerationError("holon ordinals not contiguous (fail closed)")
    live_h = set(view.holons)
    live_pairs = []
    for hid in live_h:
        if hid not in view.ord_holon:
            raise GenerationError(
                f"live holon {hid} has no ordinal (fail closed)")
        live_pairs.append((view.ord_holon[hid], hid))
    live_pairs.sort(key=lambda p: (p[0], p[1]))
    hids = [hid for _o, hid in live_pairs]
    n_hol = len(hids)
    gord = {hid: i for i, hid in enumerate(hids)}
    hmat = np.stack(
        [np.asarray(view.holons[h]["descriptor"], dtype=np.float64)
         for h in hids]).reshape(n_hol, -1) if n_hol \
        else np.empty((0, 0))
    hseq = np.zeros((n_hol,), dtype=np.int64)
    hop = []
    hkind = []
    hmem_off = [0]
    hmem_vals = []
    hch_off = [0]
    hch_vals = []
    for ho, hid in enumerate(hids):
        e = view.holons[hid]
        hseq[ho] = int(e.get("seq", 0) or 0)
        hop.append(e.get("op_id"))
        hkind.append(e.get("kind"))
        for a in e.get("members", []):
            if a not in view.ord_atom:
                raise GenerationError(
                    f"holon {hid}: member {a} has no ordinal "
                    "(fail closed)")
            hmem_vals.append(int(view.ord_atom[a]))
        hmem_off.append(len(hmem_vals))
        for c in e.get("children") or []:
            if c not in live_h:
                raise GenerationError(
                    f"holon {hid}: child {c} not live "
                    "(fail closed)")
            hch_vals.append(int(gord[c]))
        hch_off.append(len(hch_vals))
    # -- hierarchy reverse indexes (CSR over sorted keys) -------------
    al_keys = sorted(view.atom_leaves)
    for a in al_keys:
        if a not in view.ord_atom:
            raise GenerationError(f"atom_leaves key {a} has no ordinal")
    al_off = [0]
    al_vals = []
    for a in al_keys:
        for h in view.atom_leaves[a]:
            if h not in live_h:
                raise GenerationError(
                    f"atom_leaves val {h} not live (fail closed)")
            al_vals.append(int(gord[h]))
        al_off.append(len(al_vals))
    lp_keys = sorted(view.leaf_parents)
    for h in lp_keys:
        if h not in live_h:
            raise GenerationError(
                f"leaf_parents key {h} not live (fail closed)")
    lp_off = [0]
    lp_vals = []
    for h in lp_keys:
        for p in view.leaf_parents[h]:
            if p not in live_h:
                raise GenerationError(
                    f"leaf_parents val {p} not live (fail closed)")
            lp_vals.append(int(gord[p]))
        lp_off.append(len(lp_vals))
    # -- text blob ----------------------------------------------------
    blob_parts = []
    text_idx = [0]
    for o in range(n_ord):
        b = ord_texts[o].encode("utf-8")
        blob_parts.append(b)
        text_idx.append(text_idx[-1] + len(b))
    blob = b"".join(blob_parts)
    # -- meta columns -------------------------------------------------
    meta_seq = np.array([int(ord_meta[o].get("seq", 0) or 0)
                         for o in range(n_ord)], dtype=np.int64)
    meta_doc = np.array([doc_idx.get(ord_meta[o].get("doc_id"), -1)
                         for o in range(n_ord)], dtype=np.int64)
    spans = []
    for o in range(n_ord):
        sp = ord_meta[o].get("span")
        if not isinstance(sp, (list, tuple)) or len(sp) != 2 or \
                not all(isinstance(x, int) for x in sp):
            raise GenerationError(
                f"ordinal {o}: non int-pair span {sp!r} (fail closed)")
        spans.append((sp[0], sp[1]))
    meta_span = np.array(spans, dtype=np.int64).reshape(n_ord, 2) \
        if n_ord else np.empty((0, 2), dtype=np.int64)
    meta_op = np.array([ord_meta[o].get("op_id") for o in range(n_ord)],
                       dtype=object)
    meta_tart = np.array([ord_meta[o].get("text_art")
                          for o in range(n_ord)], dtype=object)
    meta_tdigest = np.array([ord_meta[o].get("text_digest")
                             for o in range(n_ord)], dtype=object)
    # -- aid/hid sorted indexes (binary search, exact equality) ------
    aid_order = sorted(range(n_ord), key=lambda o: aids[o])
    hid_order = sorted(range(n_hol), key=lambda o: hids[o])
    tomb = sorted(view.tomb.materialize())
    # -- write blocks -------------------------------------------------
    faults_mod.fire("enospc_gen", tmpdir=tmpdir)
    payloads = {
        "aids": np.array(aids, dtype=object),
        "aid_sorted": np.array([aids[o] for o in aid_order],
                               dtype=object),
        "aid_sorted_ord": np.array(aid_order, dtype=np.int64),
        "vectors": mat32,
        "norms_f64": np.asarray(norms, dtype=np.float64),
        "ov_ord": ov_ord,
        "ov_mat": np.asarray(ov_mat, dtype=np.float64),
        "live": live,
        "doclen": doclen,
        "term_offsets": np.array(offsets, dtype=np.int64),
        "post_ord": np.array(po_all, dtype=ORD_DTYPE),
        "post_tf": np.array(pf_all, dtype=TF_DTYPE),
        "term_df": np.array([int(view.df.get(t, 0)) for t in terms],
                            dtype=np.int64),
        "text_idx": np.array(text_idx, dtype=np.int64),
        "docs_sorted": np.array(docs_sorted, dtype=object),
        "docs_sorted_pos": np.array(
            [doc_idx[d] for d in docs_sorted], dtype=np.int64),
        "doc_offsets": np.array(doc_offsets, dtype=np.int64),
        "doc_ords": np.array(doc_ords, dtype=np.int64),
        "meta_seq": meta_seq,
        "meta_doc": meta_doc,
        "meta_span": meta_span,
        "meta_op": meta_op,
        "meta_tart": meta_tart,
        "meta_tdigest": meta_tdigest,
        "hids": np.array(hids, dtype=object),
        "hid_sorted": np.array([hids[o] for o in hid_order],
                               dtype=object),
        "hid_sorted_ord": np.array(hid_order, dtype=np.int64),
        "holon_vectors": np.ascontiguousarray(
            np.asarray(hmat, dtype=np.float64)),
        "hseq": hseq,
        "hop": np.array(hop, dtype=object),
        "hkind": np.array(hkind, dtype=object),
        "hmem_offsets": np.array(hmem_off, dtype=np.int64),
        "hmem_vals": np.array(hmem_vals, dtype=np.int64),
        "hch_offsets": np.array(hch_off, dtype=np.int64),
        "hch_vals": np.array(hch_vals, dtype=np.int64),
        "edge_al_keys": np.array(al_keys, dtype=object),
        "edge_al_offsets": np.array(al_off, dtype=np.int64),
        "edge_al_vals": np.array(al_vals, dtype=np.int64),
        "edge_lp_keys": np.array(lp_keys, dtype=object),
        "edge_lp_offsets": np.array(lp_off, dtype=np.int64),
        "edge_lp_vals": np.array(lp_vals, dtype=np.int64),
    }
    for key, arr in payloads.items():
        faults_mod.fire("pre_gen_block", block=key)
        np.save(os.path.join(tmpdir, BLOCK_FILES[key]),
                np.ascontiguousarray(arr))
        faults_mod.fire("post_gen_block", block=key)
    with open(os.path.join(tmpdir, BLOCK_FILES["terms"]), "w") as f:
        json.dump({"terms": terms}, f)
    with open(os.path.join(tmpdir, BLOCK_FILES["docs"]), "w") as f:
        json.dump({"docs": docs}, f)
    with open(os.path.join(tmpdir, BLOCK_FILES["tombstones"]), "w") as f:
        json.dump({"retired_docs": tomb}, f)
    with open(os.path.join(tmpdir, BLOCK_FILES["text_blob"]), "wb") as f:
        f.write(blob)
    digests = {BLOCK_FILES[k]: _sha_file(os.path.join(tmpdir,
                                                      BLOCK_FILES[k]))
               for k in list(payloads) + ["terms", "docs",
                                         "tombstones", "text_blob"]}
    from tlsys.serving.segments import op_hash_of as _oph
    ranges = [(int(s.lo), int(s.hi), s.op_hash) for s in view.segments]
    d = view.delta
    if int(d.hi) > int(d.lo):
        ranges.append((int(d.lo), int(d.hi), _oph(list(d.op_ids))))
    root = {
        "gen_version": GEN_VERSION, "format_version": GEN_FORMAT_VERSION,
        "config_id": CONFIG_ID, "analyzer_id": ANALYZER_ID,
        "birth": view.birth, "epoch": view.epoch,
        "frontier": int(view.frontier), "triple": view.triple,
        "live_n": int(view.live_n),
        "total_tokens": int(view.total_tokens),
        "atom_ordinals": int(n_ord), "holon_count": int(n_hol),
        "term_count": int(len(terms)), "doc_count": int(len(docs)),
        "dim": int(dim),
        "tombstone_version": "sha256:" + hashlib.sha256(
            "\n".join(tomb).encode("utf-8")).hexdigest(),
        "range_summary": {
            # Per-range op hashes (v1 segment + delta ranges, or the
            # base generation's ranges + the suffix range for gen
            # sources). The global op_hash is derived from the
            # authoritative scan at verification time (source truth),
            # never from assembled view state.
            "ranges": ranges,
            "n_commit_rows": int(sum(
                s.n_commit_rows for s in view.segments)
                + d.n_commit_rows)},
        "blocks": digests,
        "indexes": {"terms_sorted": True,
                    "postings_order": "ord-asc",
                    "ordinals": "first-seen-contiguous",
                    "holons": "latest-only"},
        "unverified_text_ords": len(unverified),
    }
    receipt = {
        "atom_ordinals": n_ord, "holon_count": n_hol,
        "term_count": len(terms), "postings": len(po_all),
        "overrides": int(len(ov_ord)),
        "text_bytes": len(blob),
        "unverified_text_ords": len(unverified),
        "build_ms": (time.monotonic() - t0) * 1000.0,
    }
    if counters is not None:
        total = sum(os.path.getsize(os.path.join(tmpdir, v))
                    for v in digests)
        counters.record(bytes_written=total,
                         files_touched=len(digests))
    return root, receipt


def verify_against_source(root, tlstore, birth, epoch, scan_fn,
                          counters=None, prev_root=None,
                          prefix_op_slices=None, prev_gendir=None):
    """Verify derived/source correspondence for a built root.

    scan_fn(lo, hi) -> (commit_rows, metas, texts) over the
    authoritative log (the pool's _scan). Checks: ranges partition
    (0, frontier] contiguously; op-id sequence hash matches the
    range summary; commit-row count matches; retired-doc union
    matches the log's retirement markers. Genuine immutable-prefix
    identity via op-id hashes (never mtimes/sequence alone).
    Returns a verification receipt. Raises GenerationError.

    Fix-2: prev_root None (default) runs the from-zero path exactly as
    before (receipt gains verify_mode/chain_ok only). With prev_root
    (the live, digest-pinned previous root) a suffix proof is attempted
    first; ANY chain break falls back to the FULL rescan, receipted
    (verify_mode full, chain_ok False, fallback reason). A full-verify
    failure still raises (fail closed), as before.
    """
    if prev_root is not None:
        try:
            return verify_suffix_against_source(
                root, prev_root, scan_fn,
                prefix_op_slices=prefix_op_slices,
                prev_gendir=prev_gendir, counters=counters)
        except GenerationError as exc:
            fallback_reason = str(exc)
        except (OSError, ValueError) as exc:
            fallback_reason = "suffix-input-unreadable: %r" % (exc,)
    else:
        fallback_reason = None
    from tlsys.serving.segments import op_hash_of as _oph
    frontier = int(root["frontier"])
    ranges = [tuple(r) for r in root["range_summary"]["ranges"]]
    lo = 0
    for rlo, rhi, _ophash in ranges:
        if int(rlo) != lo or int(rhi) <= lo:
            raise GenerationError(
                f"ranges do not partition (0, {frontier}]: gap at {lo} "
                "(fail closed)")
        lo = int(rhi)
    if lo != frontier:
        raise GenerationError(
            f"ranges cover (0, {lo}], frontier is {frontier} "
            "(fail closed)")
    rows, metas, _texts = scan_fn(0, frontier)
    op_ids = [r[1] for r in rows]
    seqs = [r[0] for r in rows]
    if len(rows) != int(root["range_summary"]["n_commit_rows"]):
        raise GenerationError(
            f"source rows {len(rows)} != root "
            f"{root['range_summary']['n_commit_rows']} (fail closed)")
    # Per-range op-hash proof over the authoritative rows, then the
    # global op_hash is DERIVED from source truth (returned for the
    # root; never assembled from view state).
    import bisect as _bisect
    for rlo, rhi, rh in ranges:
        part = [op for sq, op in zip(seqs, op_ids)
                if int(rlo) < sq <= int(rhi)]
        if _oph(part) != rh:
            raise GenerationError(
                f"range ({rlo}, {rhi}] op-hash != source (fail closed)")
    op_hash = _oph(op_ids)
    retired = sorted({m[4]["retirement"]["doc"] for m in metas
                      if m[3] == "retirement"})
    if "sha256:" + hashlib.sha256(
            "\n".join(retired).encode("utf-8")).hexdigest() != \
            root["tombstone_version"]:
        raise GenerationError(
            "source retirement union != tombstone_version (fail closed)")
    receipt = {"source_rows": len(rows), "source_retired": len(retired),
               "ranges": len(ranges), "op_hash": op_hash,
               "op_hash_ok": True}
    # Fix-2 additive keys (legacy five keys byte-identical above): a full
    # verify re-anchors the binding chain; chain_ok False names a broken
    # suffix link that fell back here.
    receipt["verify_mode"] = "full"
    if fallback_reason is None:
        receipt["chain_ok"] = True
    else:
        receipt["chain_ok"] = False
        receipt["fallback"] = fallback_reason
    return receipt


def verify_suffix_against_source(root, prev_root, scan_fn,
                                 prefix_op_slices=None,
                                 prev_gendir=None, counters=None):
    """Suffix-only verify against a digest-pinned previous root (Fix-2).

    Prefix check O(ranges), no scan: the new root's ranges covering
    (0, F_prev] must equal the previous root's ranges exactly, and the
    previous root must self-verify (digest) and carry a verified
    source_verification receipt (chain link). Suffix proof O(suffix):
    scan (F_prev, F_new] only; per-range op-hash proof over suffix
    ranges; commit-row count delta check; retirement union of the
    previous generation's verified tombstones plus suffix retirement
    markers (the one O(retired) term, receipted as tombstone_union_ms).
    The global op_hash is derived from chain-verified prefix op-id
    slices (each re-hashed against its chained range hash) plus the
    suffix scan's op-ids -- identical to the from-zero derivation for
    the same frontier. Any mismatch raises GenerationError (the caller
    falls back to a FULL rescan).
    """
    from tlsys.serving.segments import op_hash_of as _oph
    frontier = int(root["frontier"])
    try:
        prev_frontier = int(prev_root["frontier"])
    except (KeyError, TypeError, ValueError):
        raise GenerationError("suffix needs a previous root with frontier")
    if not 0 <= prev_frontier < frontier:
        raise GenerationError(
            f"suffix needs 0 <= F_prev < F_new, got {prev_frontier}/{frontier}")
    # Chain link: the previous root self-verifies and carries a verified
    # receipt from its own publication (binding is per-publication).
    prev_digest = prev_root.get("digest")
    _rest = {k: v for k, v in prev_root.items() if k != "digest"}
    if prev_digest != root_digest_of(_rest):
        raise GenerationError("previous root digest mismatch (fail closed)")
    if not isinstance(prev_root.get("source_verification"), dict) or \
            prev_root["source_verification"].get("op_hash_ok") is not True:
        raise GenerationError("previous root lacks a verified receipt")
    if (prev_root.get("birth"), prev_root.get("epoch")) != \
            (root.get("birth"), root.get("epoch")):
        raise GenerationError("previous root birth/epoch != new root")
    ranges = [tuple(r) for r in root["range_summary"]["ranges"]]
    prev_ranges = [tuple(r)
                   for r in prev_root["range_summary"]["ranges"]]
    lo = 0
    for rlo, rhi, _ophash in ranges:
        if int(rlo) != lo or int(rhi) <= lo:
            raise GenerationError(
                f"ranges do not partition (0, {frontier}]: gap at {lo} "
                "(fail closed)")
        lo = int(rhi)
    if lo != frontier:
        raise GenerationError(
            f"ranges cover (0, {lo}], frontier is {frontier} "
            "(fail closed)")
    # Prefix equality with exact boundary alignment at F_prev.
    n_prefix = sum(1 for _rlo, rhi, _rh in ranges if int(rhi) <= prev_frontier)
    if list(ranges[:n_prefix]) != list(prev_ranges):
        raise GenerationError(
            "prefix ranges != previous verified ranges (fail closed)")
    if n_prefix < len(ranges) and int(ranges[n_prefix][0]) != prev_frontier:
        raise GenerationError(
            "no range boundary at F_prev (fail closed)")
    suffix_ranges = ranges[n_prefix:]
    rows, metas, _texts = scan_fn(prev_frontier, frontier)
    op_ids = [r[1] for r in rows]
    seqs = [r[0] for r in rows]
    n_prev = int(prev_root["range_summary"]["n_commit_rows"])
    if len(rows) != int(root["range_summary"]["n_commit_rows"]) - n_prev:
        raise GenerationError(
            f"suffix rows {len(rows)} != commit delta "
            f"{int(root['range_summary']['n_commit_rows']) - n_prev} "
            "(fail closed)")
    for rlo, rhi, rh in suffix_ranges:
        part = [op for sq, op in zip(seqs, op_ids)
                if int(rlo) < sq <= int(rhi)]
        if _oph(part) != rh:
            raise GenerationError(
                f"suffix range ({rlo}, {rhi}] op-hash != source (fail closed)")
    # Retirement union: previous verified tombstones (hash-pinned blocks;
    # written from the same view state as the verified tombstone_version
    # at the previous publication) plus suffix retirement markers.
    t_union = time.monotonic()
    if prev_gendir is None:
        raise GenerationError("suffix needs prev_gendir for tombstone union")
    try:
        raw = _read_verified(prev_gendir, BLOCK_FILES["tombstones"],
                             prev_root["blocks"])
        prev_retired = json.loads(raw.decode("utf-8"))["retired_docs"]
    except (GenerationError, OSError, ValueError, KeyError) as exc:
        raise GenerationError(
            f"previous tombstones unreadable: {exc!r} (fail closed)")
    if counters is not None:
        counters.record(bytes_read=len(raw), files_touched=1)
    suffix_retired = sorted({m[4]["retirement"]["doc"] for m in metas
                             if m[3] == "retirement"})
    retired = sorted(set(prev_retired) | set(suffix_retired))
    if "sha256:" + hashlib.sha256(
            "\n".join(retired).encode("utf-8")).hexdigest() != \
            root["tombstone_version"]:
        raise GenerationError(
            "source retirement union != tombstone_version (fail closed)")
    union_ms = (time.monotonic() - t_union) * 1000.0
    # Global op_hash: chain-verified prefix slices (each re-hashed against
    # its chained range hash -- verified, never trusted) + suffix scan
    # op-ids in scan order. Identical preimage to from-zero derivation.
    # Only slices fully inside the prefix window qualify; anything else
    # (suffix segments, straddlers) fails the count/alignment below.
    slices = [(int(slo), int(shi), list(sops))
              for slo, shi, sops in (prefix_op_slices or [])
              if int(shi) <= prev_frontier]
    if len(slices) != n_prefix:
        raise GenerationError(
            f"prefix slices {len(slices)} != prefix ranges {n_prefix}")
    prefix_ops = []
    for (slo, shi, sops), (rlo, rhi, rh) in zip(slices, ranges[:n_prefix]):
        if int(slo) != int(rlo) or int(shi) != int(rhi):
            raise GenerationError("prefix slice misaligned (fail closed)")
        if _oph(list(sops)) != rh:
            raise GenerationError(
                f"prefix range ({rlo}, {rhi}] slice != chained hash")
        prefix_ops.extend(list(sops))
    op_hash = _oph(prefix_ops + op_ids)
    return {"source_rows": len(rows), "source_retired": len(retired),
            "ranges": len(ranges), "op_hash": op_hash,
            "op_hash_ok": True, "verify_mode": "suffix", "chain_ok": True,
            "prev_frontier": prev_frontier, "prev_digest": prev_digest,
            "prefix_ranges": n_prefix, "suffix_ranges": len(suffix_ranges),
            "tombstone_union_ms": union_ms}


class GenerationReader:
    """Indexed reader over verified generation blocks (no eager dicts).

    All blocks are hash-verified against the root before parsing.
    Lookups are indexed (ordinal arrays, binary search + exact string
    equality for aids/terms/hids/docs); the reader builds no
    corpus-sized Python dicts. Source text is digest-verified when
    read. Counters record physical verified bytes (mmap would only
    change access, never integrity or first-read I/O).
    """

    def __init__(self, gendir, root, counters=None):
        self.gendir = gendir
        self.root = root
        self.counters = counters
        digests = root["blocks"]
        t0 = time.monotonic()
        raw = {}
        for key, name in BLOCK_FILES.items():
            raw[key] = _read_verified(gendir, name, digests)
        if counters is not None:
            counters.record(bytes_read=sum(len(v) for v in raw.values()),
                             files_touched=len(raw))
        self._terms = json.loads(raw["terms"].decode("utf-8"))["terms"]
        self._docs = json.loads(raw["docs"].decode("utf-8"))["docs"]
        self._tomb = json.loads(raw["tombstones"].decode("utf-8"))[
            "retired_docs"]
        self._blob = raw["text_blob"]

        def _np(key):
            return np.load(io.BytesIO(raw[key]), allow_pickle=True)
        self.aids = _np("aids")
        self.aid_sorted = _np("aid_sorted")
        self.aid_sorted_ord = _np("aid_sorted_ord")
        self.vectors = _np("vectors")
        self.norms_f64 = _np("norms_f64")
        self.ov_ord = _np("ov_ord")
        self.ov_mat = _np("ov_mat")
        self.live = _np("live")
        self.doclen = _np("doclen")
        self.term_offsets = _np("term_offsets")
        self.post_ord = _np("post_ord")
        self.post_tf = _np("post_tf")
        self.term_df = _np("term_df")
        self.text_idx = _np("text_idx")
        self.docs_sorted = _np("docs_sorted")
        self.docs_sorted_pos = _np("docs_sorted_pos")
        self.doc_offsets = _np("doc_offsets")
        self.doc_ords = _np("doc_ords")
        self.meta_seq = _np("meta_seq")
        self.meta_doc = _np("meta_doc")
        self.meta_span = _np("meta_span")
        self.meta_op = _np("meta_op")
        self.meta_tart = _np("meta_tart")
        self.meta_tdigest = _np("meta_tdigest")
        self.hids = _np("hids")
        self.hid_sorted = _np("hid_sorted")
        self.hid_sorted_ord = _np("hid_sorted_ord")
        self.holon_vectors = _np("holon_vectors")
        self.hseq = _np("hseq")
        self.hop = _np("hop")
        self.hkind = _np("hkind")
        self.hmem_offsets = _np("hmem_offsets")
        self.hmem_vals = _np("hmem_vals")
        self.hch_offsets = _np("hch_offsets")
        self.hch_vals = _np("hch_vals")
        self.edge_al_keys = _np("edge_al_keys")
        self.edge_al_offsets = _np("edge_al_offsets")
        self.edge_al_vals = _np("edge_al_vals")
        self.edge_lp_keys = _np("edge_lp_keys")
        self.edge_lp_offsets = _np("edge_lp_offsets")
        self.edge_lp_vals = _np("edge_lp_vals")
        self._check_shapes()
        # Cached sorted-list indexes (the persisted blocks, in RAM):
        # every lookup below is O(log N) binary search + exact
        # equality, never an eager dict rebuild.
        self._aid_list = self.aid_sorted.tolist()
        self._docs_sorted_list = self.docs_sorted.tolist()
        self._hid_list = self.hid_sorted.tolist()
        self._ov_list = self.ov_ord.tolist()
        self._eal_list = self.edge_al_keys.tolist()
        self._elp_list = self.edge_lp_keys.tolist()
        self.open_ms = (time.monotonic() - t0) * 1000.0

    def _check_shapes(self):
        n = int(self.root["atom_ordinals"])
        h = int(self.root["holon_count"])
        v = int(self.root["term_count"])
        d = int(self.root["doc_count"])
        shapes = [("aids", len(self.aids), n),
                  ("live", len(self.live), n),
                  ("doclen", len(self.doclen), n),
                  ("terms", len(self._terms), v),
                  ("term_offsets", len(self.term_offsets), v + 1),
                  ("term_df", len(self.term_df), v),
                  ("text_idx", len(self.text_idx), n + 1),
                  ("docs", len(self._docs), d),
                  ("doc_offsets", len(self.doc_offsets), d + 1),
                  ("hids", len(self.hids), h),
                  ("holon_vectors", len(self.holon_vectors), h),
                  ("hmem_offsets", len(self.hmem_offsets), h + 1),
                  ("hch_offsets", len(self.hch_offsets), h + 1)]
        for name, got, want in shapes:
            if got != want:
                raise GenerationError(
                    f"block {name}: shape {got} != root {want} "
                    "(fail closed)")
        if list(self._terms) != sorted(self._terms):
            raise GenerationError("terms not sorted (fail closed)")
        if list(self.docs_sorted.tolist()) != sorted(self._docs):
            raise GenerationError("docs_sorted index incoherent")
        if sorted(self.docs_sorted_pos.tolist()) != list(range(len(
                self._docs))):
            raise GenerationError("docs_sorted positions incoherent")
        if int(self.term_offsets[0]) != 0 or \
                bool(np.any(np.diff(self.term_offsets) < 0)):
            raise GenerationError("term offsets not monotonic")

    # -- indexed lookups (binary search + exact equality) ------------
    @staticmethod
    def _bsearch(sorted_arr, key):
        import bisect as _bisect
        i = _bisect.bisect_left(sorted_arr, key)
        if i < len(sorted_arr) and sorted_arr[i] == key:
            return int(i)
        return None

    def ord_of_aid(self, aid):
        i = self._bsearch(self._aid_list, aid)
        if i is None:
            raise KeyError(aid)
        return int(self.aid_sorted_ord[i])

    def has_aid(self, aid):
        return self._bsearch(self._aid_list, aid) is not None

    def aid_of_ord(self, o):
        if 0 <= int(o) < len(self.aids):
            return self.aids[int(o)]
        raise KeyError(o)

    def is_live_ord(self, o):
        return bool(self.live[int(o)])

    def doclen_of(self, o):
        return int(self.doclen[int(o)])

    def df_of(self, term):
        i = self._bsearch(self._terms, term)
        if i is None:
            return None
        return int(self.term_df[i])

    def postings_of(self, term):
        i = self._bsearch(self._terms, term)
        if i is None:
            return self.post_ord[0:0], self.post_tf[0:0]
        a, b = int(self.term_offsets[i]), int(self.term_offsets[i + 1])
        return self.post_ord[a:b], self.post_tf[a:b]

    def text_of_ord(self, o, verify=True):
        o = int(o)
        a, b = int(self.text_idx[o]), int(self.text_idx[o + 1])
        body = self._blob[a:b]
        if verify:
            want = self.meta_tdigest[o]
            if want is not None and _sha_bytes(body) != want:
                raise GenerationError(
                    f"ordinal {o}: text fails pinned digest (fail closed)")
        return body.decode("utf-8")

    def atom_entry(self, o):
        """C1-shaped live entry for ordinal o (fresh dict per call)."""
        o = int(o)
        return {"seq": int(self.meta_seq[o]),
                "op_id": self.meta_op[o],
                "doc_id": self._docs[int(self.meta_doc[o])]
                if int(self.meta_doc[o]) >= 0 else None,
                "span": [int(self.meta_span[o][0]),
                         int(self.meta_span[o][1])],
                "text_art": self.meta_tart[o],
                "text_digest": self.meta_tdigest[o],
                "descriptor": self.atom_row_f64(o)}

    def atom_row_f64(self, o):
        o = int(o)
        import bisect as _bisect
        i = _bisect.bisect_left(self._ov_list, o)
        if i < len(self.ov_ord) and int(self.ov_ord[i]) == o:
            return np.asarray(self.ov_mat[i], dtype=np.float64).copy()
        return self.vectors[o].astype(np.float64)

    def norm_of(self, o):
        return float(self.norms_f64[int(o)])

    def hord_of_hid(self, hid):
        i = self._bsearch(self._hid_list, hid)
        if i is None:
            raise KeyError(hid)
        return int(self.hid_sorted_ord[i])

    def has_hid(self, hid):
        return self._bsearch(self._hid_list, hid) is not None

    def holon_entry(self, hid):
        ho = self.hord_of_hid(hid)
        a, b = int(self.hmem_offsets[ho]), int(self.hmem_offsets[ho + 1])
        c, e = int(self.hch_offsets[ho]), int(self.hch_offsets[ho + 1])
        return {"seq": int(self.hseq[ho]), "op_id": self.hop[ho],
                "members": [self.aids[int(o)]
                            for o in self.hmem_vals[a:b].tolist()],
                "descriptor": np.asarray(
                    self.holon_vectors[ho], dtype=np.float64).copy(),
                "kind": (None if self.hkind[ho] is None
                         else str(self.hkind[ho])),
                "children": [self.hids[int(o)]
                             for o in self.hch_vals[c:e].tolist()]}

    def leaves_of(self, aid):
        i = self._bsearch(self._eal_list, aid)
        if i is None:
            return []
        a, b = int(self.edge_al_offsets[i]), \
            int(self.edge_al_offsets[i + 1])
        return [self.hids[int(o)]
                for o in self.edge_al_vals[a:b].tolist()]

    def parents_of(self, leaf):
        i = self._bsearch(self._elp_list, leaf)
        if i is None:
            return []
        a, b = int(self.edge_lp_offsets[i]), \
            int(self.edge_lp_offsets[i + 1])
        return [self.hids[int(o)]
                for o in self.edge_lp_vals[a:b].tolist()]

    def doc_ordinals(self, doc):
        i = self._bsearch(self._docs_sorted_list, doc)
        if i is None:
            raise KeyError(doc)
        p = int(self.docs_sorted_pos[i])
        a, b = int(self.doc_offsets[p]), int(self.doc_offsets[p + 1])
        return self.doc_ords[a:b].astype(np.int64)

    def live_ordinals(self):
        return np.nonzero(self.live)[0]

    def retired_aids(self):
        return {self.aids[int(o)]
                for o in np.nonzero(~self.live)[0].tolist()}

    def retired_docs(self):
        return list(self._tomb)


def open_generation(serving_dir, birth, epoch, counters=None):
    """Open + verify the current generation (fail closed).

    Verifies the root self-digest, gen/config/birth/epoch binding,
    then every block hash before parsing. Returns (root, reader).
    """
    gendir = os.path.join(serving_dir, GEN_DIRNAME)
    root = read_root(gendir)
    if (root.get("birth"), root.get("epoch")) != (birth, epoch):
        raise GenerationError(
            f"{gendir}: birth/epoch {root.get('birth')}/"
            f"{root.get('epoch')} != pool {birth}/{epoch} (fail closed)")
    reader = GenerationReader(gendir, root, counters=counters)
    return root, reader


def _fsync_dir(path):
    dfd = os.open(path or ".", os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def publish_generation(tmpdir, root, serving_dir, verify_receipt,
                       counters=None, gc_keep=None, gc_pinned=()):
    """Atomically publish a built + source-verified generation.

    Finishes the root (source verification + digest), writes it,
    swaps generation/ into place, retains the replaced generation,
    and rewrites manifest.json as a v2 pointer (old readers refuse).
    The v1 pointer pair is retained once for new-reader fallback.
    Returns the publication receipt. Raises GenerationError.

    Fix-5: gc_keep None (default) runs no GC (byte-identical receipts).
    Otherwise a gen_gc.collect() pass runs LAST, strictly after the
    manifest pointer write has succeeded; its receipt keys merge flat
    into the publication receipt.
    """
    from tlsys.serving import manifest as manifest_mod
    t0 = time.monotonic()
    root = dict(root)
    root = dict(root, range_summary=dict(
        root["range_summary"], op_hash=verify_receipt["op_hash"]))
    root["source_verification"] = verify_receipt
    root["digest"] = root_digest_of(root)
    with open(os.path.join(tmpdir, GEN_FILENAME), "w") as f:
        json.dump(root, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    faults_mod.fire("pre_gen_swap", tmpdir=tmpdir)
    gendir = os.path.join(serving_dir, GEN_DIRNAME)
    retained = os.path.join(serving_dir, GEN_RETAINED_DIRNAME)
    os.makedirs(serving_dir, exist_ok=True)
    os.makedirs(retained, exist_ok=True)
    if os.path.isdir(gendir):
        try:
            prev = read_root(gendir)
            prev_name = f"gen-{int(prev['frontier'])}"
        except GenerationError:
            prev_name = f"gen-broken-{int(time.time())}"
        dest = os.path.join(retained, prev_name)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.rename(gendir, dest)
    os.rename(tmpdir, gendir)
    _fsync_dir(serving_dir)
    faults_mod.fire("post_gen_swap", gendir=gendir)
    # Retain the v1 pointer pair once (new-reader fallback/rollback).
    man = os.path.join(serving_dir, manifest_mod.FILENAME)
    if os.path.isfile(man):
        with open(man) as f:
            try:
                old = json.load(f)
            except ValueError:
                old = {}
        if old.get("format_version") == 1 and not os.path.isfile(
                os.path.join(serving_dir, V1_MANIFEST_BACKUP)):
            shutil.copyfile(
                man, os.path.join(serving_dir, V1_MANIFEST_BACKUP))
            ckpt = os.path.join(serving_dir, "checkpoint.json")
            if os.path.isfile(ckpt):
                shutil.copyfile(
                    ckpt, os.path.join(serving_dir,
                                       V1_CHECKPOINT_BACKUP))
    # v2 pointer: old (v1) readers refuse format 2 (fail closed).
    pointer = {"format_version": GEN_FORMAT_VERSION,
               "gen_version": GEN_VERSION,
               "generation": GEN_DIRNAME,
               "frontier": int(root["frontier"]),
               "birth": root["birth"], "epoch": root["epoch"],
               "root_digest": root["digest"]}
    pointer["digest"] = root_digest_of(pointer)
    manifest_mod.atomic_write(man, pointer, counters=counters)
    receipt = {"frontier": int(root["frontier"]),
               "blocks": len(root["blocks"]),
               "publish_ms": (time.monotonic() - t0) * 1000.0,
               "root_digest": root["digest"]}
    # Fix-5 GC: LAST step, only after the pointer commit succeeded.
    # gc_keep None (default) -> no GC pass, receipt byte-identical.
    if gc_keep is not None:
        from tlsys.serving import gen_gc as _gen_gc
        receipt.update(_gen_gc.collect(
            serving_dir, int(gc_keep), pinned=tuple(gc_pinned)))
    return receipt


def background_rebase(tlstore, serving_dir, pin, birth, epoch,
                      config=None, time_budget_s=0, counters=None):
    """Abortable maintenance rebase: cold v1 at pin -> publish v2.

    Runs in a private pool (own lock + maintenance counters, never
    the serving pool's) so serving is undisturbed. Cold-builds v1
    at `pin` (no v1 persist: flush disabled), verifies, publishes
    atomically. Phase time checks against `time_budget_s` (> 0):
    exceeding the budget ABORTS (tmpdir discarded, current
    generation untouched, debt carried explicitly and receipted).
    Serving correctness never depends on rebase (the overlay holds
    the suffix either way). Returns (receipt, maint_counters).
    Receipt status: published | aborted | failed (all receipted;
    failed/aborted never swap).
    """
    from tlsys.serving.counters import ServeCounters
    from tlsys.serving.view import ViewPool
    t0 = time.monotonic()
    maint = ServeCounters() if counters is None else counters
    receipt = {"status": "failed", "pin": list(pin)}

    def _over():
        return time_budget_s and (time.monotonic() - t0) > time_budget_s

    try:
        cfg = dict(config or {})
        cfg["delta_flush_atoms"] = 1 << 62  # never seal/persist v1
        pool = ViewPool(tlstore, birth, epoch, serving_dir=serving_dir,
                        config=cfg)
        pool.counters = maint
        view = pool.cold_build(pin)
        if _over():
            receipt.update(
                {"status": "aborted", "phase": "cold-build",
                 "elapsed_s": time.monotonic() - t0})
            return receipt, maint
        out = background_rebase_publish(pool, view, _over)
        if out.get("orphan"):
            receipt.update({"status": "aborted",
                            "phase": out.get("abort_phase"),
                            "elapsed_s": time.monotonic() - t0})
            return receipt, maint
        receipt.update(out)
        receipt["status"] = "published"
        receipt["elapsed_s"] = time.monotonic() - t0
        return receipt, maint
    except Exception as e:  # noqa: BLE001 (maintenance containment)
        receipt.update({"status": "failed", "error": repr(e),
                        "elapsed_s": time.monotonic() - t0})
        return receipt, maint


def background_rebase_publish(pool, view, over_fn):
    """Publish leg of background_rebase (budget-checked phases)."""
    tmpdir = os.path.join(
        pool.serving_dir, f"{GEN_TMP_PREFIX}{view.frontier}-"
        f"rebase-{int(time.time() * 1000)}")
    try:
        root, build_receipt = build_generation_blocks(
            view, tmpdir, counters=pool.counters)
        if over_fn():
            return {"orphan": True, "abort_phase": "build"}
        verify_receipt = verify_against_source(
            root, pool.tlstore, pool.birth, pool.epoch, pool._scan,
            counters=pool.counters)
        if over_fn():
            return {"orphan": True, "abort_phase": "verify"}
        pub_receipt = publish_generation(
            tmpdir, root, pool.serving_dir, verify_receipt,
            counters=pool.counters)
        return {"build": build_receipt, "verify": verify_receipt,
                "publish": pub_receipt}
    finally:
        if os.path.isdir(tmpdir) and os.path.basename(tmpdir).startswith(
                GEN_TMP_PREFIX):
            # Tmpdir survives only when the swap never happened
            # (abort/failure paths) or publish renamed it away
            # (rename success removes the source name).
            try:
                if os.path.isdir(tmpdir):
                    shutil.rmtree(tmpdir)
            except OSError:
                pass


def debt_metrics_for_view(view):
    """Maintenance debt metrics: atom AND holon rows, edges, bytes.

    Counts sealed + delta rows (a holon-only segment is not
    zero-cost), child/member edges, and segment byte sizes.
    Pure reads (no mutation); the pool enforces bounds.
    """
    atom_rows = sum(len(s.atom_rows) for s in view.segments)
    holon_rows = sum(len(s.holon_rows) for s in view.segments)
    edges = 0
    for s in view.segments:
        for r in s.holon_rows:
            edges += len(r.get("members", [])) + \
                len(r.get("children") or [])
    d = view.delta
    atom_rows += len(d.atom_rows)
    holon_rows += len(d.holon_rows)
    for r in d.holon_rows:
        edges += len(r.get("members", [])) + \
            len(r.get("children") or [])
    nbytes = 0
    for s in view.segments:
        try:
            nbytes += int(np.asarray(s.mat32).nbytes)
        except (AttributeError, ValueError, TypeError):
            pass
    return {"atom_rows": int(atom_rows), "holon_rows": int(holon_rows),
            "edges": int(edges), "segments": len(view.segments),
            "delta_rows": len(d.atom_rows) + len(d.holon_rows),
            "mat_bytes": int(nbytes)}


def debt_metrics_for_reader(reader):
    root = reader.root
    edges = int(len(reader.hmem_vals) + len(reader.hch_vals)
                + len(reader.edge_al_vals) + len(reader.edge_lp_vals))
    nbytes = int(reader.vectors.nbytes + reader.norms_f64.nbytes
                 + reader.post_ord.nbytes + reader.post_tf.nbytes
                 + len(reader._blob))
    return {"atom_rows": int(root["atom_ordinals"]),
            "holon_rows": int(root["holon_count"]),
            "edges": edges, "segments": 1, "delta_rows": 0,
            "mat_bytes": nbytes}
