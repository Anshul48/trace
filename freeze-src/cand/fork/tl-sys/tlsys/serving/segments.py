"""Immutable Segment: build from a log range, persist, load, validate.

On-disk layout v1 (see serving-contract.md section 3). Validation against
the log (counts + op-id hash over kind-filtered rows + per-file digests +
config/analyzer ids) precedes every serve; mismatch quarantines.
"""

import hashlib
import io
import json
import os
import shutil

import numpy as np

from tlsys.serving import ANALYZER_ID, CONFIG_ID, FORMAT_VERSION
from tlsys.serving import faults
from tlsys.serving.lexical import (ORD_DTYPE, TF_DTYPE, TermLexicon,
                                   toks)

KIND = "ACCEPT_ATOMS"


class SegmentError(Exception):
    pass


class QuarantinedSegmentError(SegmentError):
    pass


class OrdinalMismatchError(SegmentError):
    """Persisted ordinals diverge from seq-order first-seen ranks.

    Raised by the attach replay check (S-5 bulk restore verifies that
    stored ordinals reproduce C1 assignment exactly instead of
    silently trusting them). Carries the offending segid so the
    caller quarantines + rebuilds exactly that range (the same path
    as a log-validation failure)."""

    def __init__(self, segid, detail=""):
        super().__init__(f"{segid}: persisted ordinals do not match "
                         f"C1 order ({detail})")
        self.segid = segid


class LexCoherenceError(SegmentError):
    """Persisted segment structure consumed by the bulk restore is
    incoherent (lexicon terms/df/offsets lengths disagree, a row
    ordinal is missing from doclen, or a sealed override key is
    out of range).

    Raised by the attach bulk restore, which consumes the sealed
    structures directly. Carries the offending segid so the caller
    quarantines + rebuilds exactly that range (the same path as a
    log-validation failure) instead of serving wrong stats."""

    def __init__(self, segid, detail=""):
        super().__init__(f"{segid}: persisted lexicon incoherent "
                         f"({detail})")
        self.segid = segid


# Holon columnar sidecars (S-5 read-once load): holon descriptors as
# exact f64 rows + slim metadata lines. Dual-written with the full
# holons.jsonl (old readers ignore the sidecars; new readers verify
# all three digests and parse the sidecars, skipping the ~14M-float
# JSON scan at 10M scale). FORMAT_VERSION stays 1 (no flag day).
HOLON_VEC_FILE = "holon_vectors.npy"
HOLON_META_FILE = "holon_meta.jsonl"
HOLON_ENCODING_V1 = "meta-jsonl+vec-f64-npy-v1"


def _read_verified(segdir, name, digests):
    """Read a segment file ONCE, hash-as-read, verify-before-parse.

    Returns the file bytes. Raises SegmentError on a missing pin or a
    digest mismatch (caller quarantines). Hashing responsibility lives
    HERE: every parsed byte is hashed, and the hash covers exactly the
    parsed bytes — strictly stronger than the old hash-then-parse
    double read (which also left a TOCTOU window between passes).
    """
    want = digests.get(name)
    if want is None:
        raise SegmentError(f"{segdir}/{name}: no pinned digest "
                           "(fail closed)")
    with open(os.path.join(segdir, name), "rb") as f:
        data = f.read()
    got = "sha256:" + hashlib.sha256(data).hexdigest()
    if got != want:
        raise SegmentError(f"{segdir}/{name}: digest mismatch "
                           "(quarantine)")
    return data


def segid_of(lo, hi):
    return f"s{lo:010d}-{hi:010d}"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def op_hash_of(op_ids):
    return "sha256:" + hashlib.sha256(
        "\n".join(op_ids).encode("utf-8")).hexdigest()


def scan_range(tlstore, birth, epoch, lo, hi, counters=None):
    """C1-_build-equivalent scan of (lo, hi] (kind-filtered, batched
    readers only). Returns (commit_rows, metas) where metas is
    [(seq, op_id, art_id, kind, meta)] with kind in
    {atom, holon, retirement} in exact C1 scan order
    (seq ASC, artifact_id ASC). Texts are NOT read here (caller reads
    atom texts in the same batched shape as _build_bm25)."""
    rows = tlstore.read_commits_all(birth, epoch, hi, kind=KIND,
                                    min_seq=lo)
    if counters is not None:
        counters.record(log_rows_read=len(rows))
    seqs = [r[0] for r in rows]
    refs = tlstore.pub_refs(seqs)
    arows = tlstore.artifact_rows(
        [a for seq in seqs for a in refs.get(seq, [])])
    by_seq = {r[0]: r for r in rows}
    from tlsys.identity import ATOM_SCHEME
    metas = []
    for seq in seqs:
        op_id = by_seq[seq][1]
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id, expect_digest=arow[4])
            if counters is not None:
                counters.record(artifacts_read=1, bytes_read=len(body))
            try:
                meta = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue  # text artifact, not meta
            if not isinstance(meta, dict):
                continue
            if "local_repair" in meta:
                from tlsys.local_repair import membership_metas
                for entry in membership_metas(meta):
                    metas.append((seq, op_id, art_id, "holon", entry))
                continue
            ret = meta.get("retirement")
            if isinstance(ret, dict) and isinstance(ret.get("doc"), str):
                if meta.get("atom_scheme") != ATOM_SCHEME:
                    raise ValueError(
                        f"op seq {seq}: retirement meta scheme mismatch")
                metas.append((seq, op_id, art_id, "retirement", meta))
                continue
            if ("atom" in meta or "holon" in meta) and \
                    meta.get("atom_scheme") != ATOM_SCHEME:
                raise ValueError(
                    f"op seq {seq}: meta scheme mismatch "
                    f"{meta.get('atom_scheme')!r}")
            if "atom" in meta and "text_artifact" in meta:
                metas.append((seq, op_id, art_id, "atom", meta))
            elif "holon" in meta and "descriptor" in meta:
                metas.append((seq, op_id, art_id, "holon", meta))
    return rows, metas


def read_atom_texts(tlstore, atom_metas, counters=None):
    """{aid: text} via single-connection batched reads (same shape as
    _build_bm25's per-atom reads, minus the per-row SQL)."""
    out = {}
    for _seq, _op, _art, meta in atom_metas:
        body = tlstore.read_artifact(meta["text_artifact"],
                                     expect_digest=meta["text_digest"])
        if counters is not None:
            counters.record(artifacts_read=1, bytes_read=len(body))
        out[meta["atom"]] = body.decode("utf-8")
    return out


class Segment:
    """Immutable in-memory segment (rows in global-ordinal order)."""

    def __init__(self, segid, lo, hi, birth, epoch, atom_rows, texts,
                 holon_rows, retired_docs, op_ids, n_commit_rows,
                 lex=None, mat32=None, norms64=None, overrides=None):
        self.segid = segid
        self.lo = lo
        self.hi = hi
        self.birth = birth
        self.epoch = epoch
        self.atom_rows = list(atom_rows)
        self.texts = list(texts)
        self.holon_rows = list(holon_rows)
        self.retired_docs = set(retired_docs)
        self.op_ids = list(op_ids)
        self.n_commit_rows = n_commit_rows
        self.op_hash = op_hash_of(self.op_ids)
        self.ord_of_aid = {r["aid"]: r["ordinal"] for r in self.atom_rows}
        self.aid_of_ord = {r["ordinal"]: r["aid"] for r in self.atom_rows}
        self.idx_of_ord = {r["ordinal"]: i
                            for i, r in enumerate(self.atom_rows)}
        self.hord_of_hid = {r["hid"]: r["ordinal"]
                             for r in self.holon_rows}
        if lex is None:
            pairs = [(r["ordinal"], t) for r, t in
                     zip(self.atom_rows, self.texts)]
            lex = TermLexicon.build(pairs)
        self.lex = lex
        if mat32 is None:
            vecs = [r["descriptor"] for r in self.atom_rows]
            dim = len(vecs[0]) if vecs else 0
            from tlsys.serving.dense import build_fp32
            mat32, _inv, norms64_b, overrides_b = build_fp32(vecs)
            if overrides is None:
                overrides = overrides_b
            if norms64 is None:
                norms64 = norms64_b
        else:
            # Preserve the passed dim even with zero rows (empty range).
            dim = int(np.asarray(mat32).shape[1])
        self.mat32 = np.ascontiguousarray(
            np.asarray(mat32, dtype=np.float32).reshape(len(self.atom_rows),
                                                        dim))
        if norms64 is None:
            norms64 = np.linalg.norm(
                self.mat32.astype(np.float64), axis=1) \
                if len(self.atom_rows) else np.empty((0,))
            norms64 = np.asarray(norms64, dtype=np.float64)
            norms64[norms64 == 0.0] = 1.0
        self.norms64 = np.asarray(norms64, dtype=np.float64)
        self.overrides = {int(k): np.asarray(v, dtype=np.float64)
                          for k, v in (overrides or {}).items()}
        self.dim = int(self.mat32.shape[1]) if self.mat32.size else dim
        self.digests = {}

    # -- persistence -------------------------------------------------
    _FILES = ("atoms.jsonl", "holons.jsonl", HOLON_META_FILE,
              "vectors.npy", "invnorms.npy", HOLON_VEC_FILE,
              "overrides.json", "lex_terms.json", "lex_postings_ord.npy",
              "lex_postings_tf.npy", "lex_doclen.npy", "lex_df.npy",
              "text.blob", "text.idx.npy", "tombstones.json")

    def save(self, segdir, counters=None):
        faults.fire("enospc_segment", segdir=segdir)
        tmp = segdir + ".tmp"
        if os.path.isdir(tmp):
            shutil.rmtree(tmp)
        os.makedirs(tmp)
        faults.fire("pre_vectors", segdir=segdir)
        np.save(os.path.join(tmp, "vectors.npy"), self.mat32)
        inv = (1.0 / self.norms64).astype(np.float32) \
            if len(self.norms64) else np.empty((0,), np.float32)
        np.save(os.path.join(tmp, "invnorms.npy"), inv)
        with open(os.path.join(tmp, "overrides.json"), "w") as f:
            json.dump({str(k): v.tolist()
                       for k, v in self.overrides.items()}, f)
        # Holon descriptor column (S-5): exact f64 rows parallel to
        # holon_rows (ordinal order). Dual-written with the full
        # holons.jsonl below so old readers keep working (no flag
        # day); new readers parse this instead of the float lists.
        hvecs = [np.asarray(r.get("descriptor"), dtype=np.float64)
                 for r in self.holon_rows]
        hdim = max((v.size for v in hvecs), default=0)
        try:
            hmat = np.stack(hvecs).reshape(len(hvecs), hdim) \
                if hvecs else np.empty((0, 0), np.float64)
        except ValueError:
            raise SegmentError("ragged holon descriptors (fail closed)")
        np.save(os.path.join(tmp, HOLON_VEC_FILE),
                np.ascontiguousarray(hmat))
        faults.fire("post_vectors", segdir=segdir)
        faults.fire("pre_csr", segdir=segdir)
        with open(os.path.join(tmp, "atoms.jsonl"), "w") as f:
            for r in self.atom_rows:
                f.write(json.dumps({
                    "aid": r["aid"], "ordinal": r["ordinal"],
                    "seq": r["seq"], "op_id": r["op_id"],
                    "doc_id": r["doc_id"], "span": r["span"],
                    "text_art": r["text_art"],
                    "text_digest": r["text_digest"]}) + "\n")
        with open(os.path.join(tmp, "holons.jsonl"), "w") as f:
            for r in self.holon_rows:
                f.write(json.dumps({
                    "hid": r["hid"], "ordinal": r["ordinal"],
                    "seq": r["seq"], "op_id": r["op_id"],
                    "members": r["members"],
                    "descriptor": [float(x) for x in r["descriptor"]],
                    "kind": r.get("kind"), "children": r.get("children",
                                                             [])}) + "\n")
        # Slim holon metadata (S-5): same rows without the descriptor
        # lists (descriptors ride holon_vectors.npy). Exact for the
        # str/int/list/None fields it carries (no floats to round).
        with open(os.path.join(tmp, HOLON_META_FILE), "w") as f:
            for r in self.holon_rows:
                f.write(json.dumps({
                    "hid": r["hid"], "ordinal": r["ordinal"],
                    "seq": r["seq"], "op_id": r["op_id"],
                    "members": r["members"],
                    "kind": r.get("kind"), "children": r.get("children",
                                                             [])}) + "\n")
        # NB: no "df" list here (S-5): it duplicated lex_df.npy and no
        # reader consumes it (load uses the .npy). Legacy files that
        # carry it still load (the key is ignored, as before).
        with open(os.path.join(tmp, "lex_terms.json"), "w") as f:
            json.dump({"terms": self.lex.terms,
                       "offsets": [int(x) for x in self.lex.offsets]}, f)
        # Packed postings (A13): int32 ordinals + uint16 tfs (6 B/posting,
        # exact values; the TermLexicon constructor already range-checked).
        np.save(os.path.join(tmp, "lex_postings_ord.npy"),
                np.asarray(self.lex.post_ord, dtype=ORD_DTYPE))
        np.save(os.path.join(tmp, "lex_postings_tf.npy"),
                np.asarray(self.lex.post_tf, dtype=TF_DTYPE))
        np.save(os.path.join(tmp, "lex_doclen.npy"),
                np.array([self.lex.doclen.get(r["ordinal"], 0)
                          for r in self.atom_rows], dtype=np.int64))
        np.save(os.path.join(tmp, "lex_df.npy"),
                np.asarray(self.lex.df, dtype=np.int64))
        faults.fire("post_csr", segdir=segdir)
        faults.fire("pre_text", segdir=segdir)
        blob = "".join(self.texts).encode("utf-8")
        offs = [0]
        for t in self.texts:
            offs.append(offs[-1] + len(t.encode("utf-8")))
        with open(os.path.join(tmp, "text.blob"), "wb") as f:
            f.write(blob)
        np.save(os.path.join(tmp, "text.idx.npy"),
                np.array(offs, dtype=np.int64))
        with open(os.path.join(tmp, "tombstones.json"), "w") as f:
            json.dump({"retired_docs": sorted(self.retired_docs)}, f)
        faults.fire("post_text", segdir=segdir)
        faults.fire("pre_header", segdir=segdir)
        digests = {name: sha256_file(os.path.join(tmp, name))
                   for name in self._FILES}
        header = {"format_version": FORMAT_VERSION, "config_id": CONFIG_ID,
                  "analyzer_id": ANALYZER_ID, "dim": self.dim,
                  "segid": self.segid, "birth": self.birth,
                  "epoch": self.epoch,
                  "lo_seq": self.lo, "hi_seq": self.hi,
                  "atom_count": len(self.atom_rows),
                  "holon_count": len(self.holon_rows),
                  "n_commit_rows": self.n_commit_rows,
                  "op_hash": self.op_hash, "op_ids": self.op_ids,
                  "postings_packing": "ord-i32-tf-u16",
                  "holon_encoding": HOLON_ENCODING_V1,
                  "files": digests}
        with open(os.path.join(tmp, "header.json"), "w") as f:
            json.dump(header, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        faults.fire("post_header", segdir=segdir)
        faults.fire("pre_rename", segdir=segdir)
        if os.path.isdir(segdir):
            shutil.rmtree(segdir)
        os.rename(tmp, segdir)
        dfd = os.open(os.path.dirname(segdir) or ".", os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        faults.fire("post_rename", segdir=segdir)
        if counters is not None:
            total = sum(os.path.getsize(os.path.join(segdir, n))
                        for n in list(self._FILES) + ["header.json"])
            counters.record(bytes_written=total,
                             files_touched=len(self._FILES) + 1)
        self.digests = digests
        return header

    @classmethod
    def load(cls, segdir, counters=None):
        hpath = os.path.join(segdir, "header.json")
        with open(hpath, "rb") as f:
            header = json.loads(f.read())
        if header.get("format_version") != FORMAT_VERSION:
            raise SegmentError(
                f"{segdir}: format {header.get('format_version')} != "
                f"{FORMAT_VERSION} (fail closed)")
        if header.get("config_id") != CONFIG_ID or \
                header.get("analyzer_id") != ANALYZER_ID:
            raise SegmentError(
                f"{segdir}: config/analyzer skew "
                f"{header.get('config_id')}/{header.get('analyzer_id')}")
        # Read-once (S-5): each file below is opened EXACTLY once;
        # bytes are hashed during the read and verified before
        # parsing (_read_verified). Parsed values are identical to
        # the old hash-then-parse path.
        digests = header["files"]
        atom_rows = [json.loads(line) for line in
                     _read_verified(segdir, "atoms.jsonl",
                                    digests).splitlines()]
        # Descriptors ride vectors.npy; rows carry metadata only.
        mat32 = np.load(io.BytesIO(_read_verified(
            segdir, "vectors.npy", digests)))
        _inv = np.load(io.BytesIO(_read_verified(
            segdir, "invnorms.npy", digests)))
        overrides = {int(k): np.asarray(v, dtype=np.float64)
                     for k, v in json.loads(_read_verified(
                         segdir, "overrides.json", digests)).items()}
        lt = json.loads(_read_verified(segdir, "lex_terms.json",
                                       digests))
        po = np.load(io.BytesIO(_read_verified(
            segdir, "lex_postings_ord.npy", digests)))
        pt = np.load(io.BytesIO(_read_verified(
            segdir, "lex_postings_tf.npy", digests)))
        # Packed (int32/uint16) or legacy int64 postings both load (A13);
        # anything else fails closed. Exact range validation happens in
        # the TermLexicon constructor (overflow -> ValueError).
        if po.dtype not in (ORD_DTYPE, np.dtype(np.int64)):
            raise SegmentError(
                f"{segdir}/lex_postings_ord.npy: dtype {po.dtype} "
                "(fail closed)")
        if pt.dtype not in (TF_DTYPE, np.dtype(np.int64)):
            raise SegmentError(
                f"{segdir}/lex_postings_tf.npy: dtype {pt.dtype} "
                "(fail closed)")
        dl = np.load(io.BytesIO(_read_verified(
            segdir, "lex_doclen.npy", digests)))
        dfa = np.load(io.BytesIO(_read_verified(
            segdir, "lex_df.npy", digests)))
        blob = _read_verified(segdir, "text.blob", digests)
        offs = np.load(io.BytesIO(_read_verified(
            segdir, "text.idx.npy", digests)))
        texts = [blob[int(offs[i]):int(offs[i + 1])].decode("utf-8")
                 for i in range(len(atom_rows))]
        if HOLON_VEC_FILE in digests and HOLON_META_FILE in digests:
            # Columnar fast path: slim metadata + exact f64 rows.
            # The full holons.jsonl is still integrity-verified
            # (pinned digest) but its float lists are never parsed.
            # Row descriptors here are f64 arrays (build-path rows
            # carry lists); every consumer takes np.asarray/iteration
            # over either form, and values are exactly equal.
            meta_rows = [json.loads(line) for line in
                         _read_verified(segdir, HOLON_META_FILE,
                                        digests).splitlines()]
            hmat = np.load(io.BytesIO(_read_verified(
                segdir, HOLON_VEC_FILE, digests)))
            if hmat.shape[0] != len(meta_rows):
                raise SegmentError(
                    f"{segdir}/{HOLON_VEC_FILE}: {hmat.shape[0]} rows "
                    f"!= {len(meta_rows)} meta rows (fail closed)")
            holon_rows = []
            for r, vec in zip(meta_rows, hmat):
                rr = dict(r)
                rr["descriptor"] = np.asarray(
                    vec, dtype=np.float64).copy()
                holon_rows.append(rr)
            _read_verified(segdir, "holons.jsonl", digests)
        else:
            # Legacy dirs (no sidecars): parse the full JSON exactly
            # as before (slower, correct).
            holon_rows = [json.loads(line) for line in
                          _read_verified(segdir, "holons.jsonl",
                                         digests).splitlines()]
        # Every other header-pinned file is verified too (same
        # strictness as the old whole-header pre-hash: unknown
        # pinned files fail closed, never load silently).
        for name in digests:
            if name not in cls._FILES:
                _read_verified(segdir, name, digests)
        retired = set(json.loads(_read_verified(
            segdir, "tombstones.json", digests))["retired_docs"])
        for r, t in zip(atom_rows, texts):
            r["descriptor"] = None  # materialized via mat32/overrides
        lex = TermLexicon(lt["terms"], lt["offsets"], po, pt,
                          {r["ordinal"]: int(dl[i])
                           for i, r in enumerate(atom_rows)},
                          dfa, [r["ordinal"] for r in atom_rows])
        # Sanity: header counts match files (I4).
        if header["atom_count"] != len(atom_rows) or \
                header["holon_count"] != len(holon_rows):
            raise SegmentError(f"{segdir}: header/file count mismatch")
        norms = np.linalg.norm(mat32.astype(np.float64), axis=1) \
            if len(atom_rows) else np.empty((0,))
        norms = np.asarray(norms, dtype=np.float64)
        norms[norms == 0.0] = 1.0
        seg = cls(header.get("segid", os.path.basename(segdir)),
                  header["lo_seq"], header["hi_seq"],
                  header.get("birth"), header.get("epoch"),
                  atom_rows, texts, holon_rows, retired,
                  header.get("op_ids", []), header["n_commit_rows"],
                  lex=lex, mat32=mat32,
                  norms64=norms, overrides=overrides)
        seg.op_hash = header["op_hash"]
        seg.digests = dict(header["files"])
        if counters is not None:
            # Account the files actually present (legacy dirs lack
            # the columnar sidecars; unknown pinned files were
            # verified above and count too).
            names = set(list(cls._FILES) + ["header.json"])
            names.update(digests.keys())
            total, count = 0, 0
            for n in names:
                p = os.path.join(segdir, n)
                if os.path.isfile(p):
                    total += os.path.getsize(p)
                    count += 1
            counters.record(bytes_read=total, files_touched=count)
        return seg

    def validate_against_log(self, tlstore, birth, epoch,
                             counters=None):
        """(count, op-hash) over the kind-filtered range vs the substrate.
        Raises SegmentError on any mismatch (caller quarantines).
        The validation scan rows are counted (log_rows_read) when a
        counter holder is passed (S-5 closes the S-3 section 6.5 gap
        through the existing key; ops are not decoded, so
        log_ops_read stays untouched)."""
        rows = tlstore.read_commits_all(birth, epoch, self.hi, kind=KIND,
                                        min_seq=self.lo)
        if counters is not None:
            counters.record(log_rows_read=len(rows))
        if len(rows) != self.n_commit_rows:
            raise SegmentError(
                f"{self.segid}: count {self.n_commit_rows} != log "
                f"{len(rows)} for ({self.lo}, {self.hi}]")
        if op_hash_of([r[1] for r in rows]) != self.op_hash:
            raise SegmentError(f"{self.segid}: op-hash mismatch vs log")
        if (self.birth, self.epoch) != (birth, epoch) and \
                self.birth is not None:
            raise SegmentError(f"{self.segid}: birth/epoch skew")
        return True

    def check_against_rows(self, rows, birth, epoch):
        """Same checks as validate_against_log over PRE-READ rows.

        rows: read_commits_all output rows with lo < seq <= hi (the
        caller slices one substrate scan per range). Raises SegmentError
        identically; the batched attach path uses this (A15)."""
        rows = [r for r in rows if self.lo < r[0] <= self.hi]
        if len(rows) != self.n_commit_rows:
            raise SegmentError(
                f"{self.segid}: count {self.n_commit_rows} != log "
                f"{len(rows)} for ({self.lo}, {self.hi}]")
        if op_hash_of([r[1] for r in rows]) != self.op_hash:
            raise SegmentError(f"{self.segid}: op-hash mismatch vs log")
        if (self.birth, self.epoch) != (birth, epoch) and \
                self.birth is not None:
            raise SegmentError(f"{self.segid}: birth/epoch skew")
        return True

    def atom_descriptor_f64(self, pos):
        ov = self.overrides.get(int(pos))
        if ov is not None:
            return np.asarray(ov, dtype=np.float64)
        return self.mat32[int(pos)].astype(np.float64)


def build_segment_from_scan(segid, lo, hi, birth, epoch, rows, metas,
                            texts, ord_atom, ord_holon, counters=None):
    """Assemble an in-memory Segment from scan_range output. ord_atom /
    ord_holon assign global ordinals (dicts aid->ordinal, mutated)."""
    atom_rows = []
    holon_rows = []
    retired = set()
    op_ids = [r[1] for r in rows]
    for seq, op_id, _art, kind, meta in metas:
        if kind == "retirement":
            retired.add(meta["retirement"]["doc"])
        elif kind == "atom":
            aid = meta["atom"]
            if aid not in ord_atom:
                ord_atom[aid] = len(ord_atom)
            atom_rows.append({
                "aid": aid, "ordinal": ord_atom[aid], "seq": seq,
                "op_id": op_id, "doc_id": meta["doc_id"],
                "span": meta["span"],
                "text_art": meta["text_artifact"],
                "text_digest": meta["text_digest"],
                "descriptor": [float(x) for x in
                               np.asarray(meta.get("descriptor", []),
                                          dtype=np.float64)]})
        elif kind == "holon":
            hid = meta["holon"]
            if hid not in ord_holon:
                ord_holon[hid] = len(ord_holon)
            holon_rows.append({
                "hid": hid, "ordinal": ord_holon[hid], "seq": seq,
                "op_id": op_id, "members": list(meta["members"]),
                "descriptor": [float(x) for x in
                               np.asarray(meta["descriptor"],
                                          dtype=np.float64)],
                "kind": meta.get("kind"),
                "children": list(meta.get("children") or [])})
    atom_rows.sort(key=lambda r: r["ordinal"])
    holon_rows.sort(key=lambda r: r["ordinal"])
    seg_texts = [texts[r["aid"]] for r in atom_rows]
    return Segment(segid, lo, hi, birth, epoch, atom_rows, seg_texts,
                   holon_rows, retired, op_ids, len(rows))


def merge_segments(segments, segid=None):
    """Tiered merge of ADJACENT segments (in order): term-id remap +
    ordinal concat, no re-tokenization. Raises on non-adjacency."""
    segments = list(segments)
    if len(segments) == 1:
        return segments[0]
    for a, b in zip(segments, segments[1:]):
        if a.hi != b.lo or a.birth != b.birth or a.epoch != b.epoch:
            raise SegmentError("merge requires adjacent same-store ranges")
    dims = {s.dim for s in segments if len(s.atom_rows)}
    if len(dims) > 1:
        raise SegmentError(f"merge requires homogeneous dim, got {dims}")
    lo, hi = segments[0].lo, segments[-1].hi
    segid = segid or segid_of(lo, hi)
    # New row dicts (never mutate the sealed inputs).
    atom_rows = [dict(r) for s in segments for r in s.atom_rows]
    texts = [t for s in segments for t in s.texts]
    holon_rows = [dict(r) for s in segments for r in s.holon_rows]
    retired = set().union(*[s.retired_docs for s in segments]) \
        if segments else set()
    op_ids = [o for s in segments for o in s.op_ids]
    n_commit = sum(s.n_commit_rows for s in segments)
    lex = TermLexicon.merge([s.lex for s in segments])
    dim = next((s.dim for s in segments if len(s.atom_rows)),
               segments[0].dim if segments else 0)
    mat32 = np.ascontiguousarray(np.vstack(
        [s.mat32.reshape(len(s.atom_rows), dim) for s in segments])
        if sum(len(s.atom_rows) for s in segments) else
        np.empty((0, dim), np.float32))
    base = 0
    overrides = {}
    norms = []
    for s in segments:
        norms.append(s.norms64)
        for k, v in s.overrides.items():
            overrides[base + int(k)] = v
        base += len(s.atom_rows)
    norms64 = np.concatenate(norms) if norms else np.empty((0,))
    # op_ids persist in every header, so the merged range's op_hash is
    # the plain range hash and validates against the log like any build.
    return Segment(segid, lo, hi, segments[0].birth, segments[0].epoch,
                   atom_rows, texts, holon_rows, retired, op_ids,
                   n_commit, lex=lex, mat32=mat32, norms64=norms64,
                   overrides=overrides)


def pre_touch(segdir):
    """Page-cache warm a segment dir before publishing a swap (F4).

    Sequentially reads every file (posix_fadvise WILLNEED first when
    available). Returns bytes touched. Best-effort: read errors raise
    (fail closed: the swap must not publish an unreadable segment).
    """
    total = 0
    try:
        advise = os.posix_fadvise
    except AttributeError:  # pragma: no cover (non-POSIX)
        advise = None
    for name in sorted(os.listdir(segdir)):
        path = os.path.join(segdir, name)
        if not os.path.isfile(path):
            continue
        fd = os.open(path, os.O_RDONLY)
        try:
            if advise is not None:
                try:
                    advise(fd, 0, 0, os.POSIX_FADV_WILLNEED)
                except OSError:
                    pass
            while True:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                total += len(chunk)
        finally:
            os.close(fd)
    return total


def quarantine(segdir, quarantined_root, counters=None):
    """Move a failed segment aside (never serve it). Returns new path."""
    os.makedirs(quarantined_root, exist_ok=True)
    dest = os.path.join(quarantined_root,
                        os.path.basename(segdir) + ".quarantined")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.move(segdir, dest)
    if counters is not None:
        counters.record(quarantines=1)
    return dest
