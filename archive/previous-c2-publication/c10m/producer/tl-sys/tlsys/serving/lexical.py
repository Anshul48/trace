"""Lexical CSR + exact BM25 (bit-identical to ReferenceNarrowIndex.bm25).

Single source of truth for the frozen lexical constants; tlsys.index
re-exports K1/B/toks from here. Exactness rules (spec section 3.4):
math.log idf on integer df/N, integer-derived avgdl, sorted unique query
terms, per-term float64 accumulation visiting postings in global ordinal
order, emission in ordinal order.
"""

import math

import numpy as np

# Frozen for parity (from tlsys.index pre-C2 values; asserted equal in
# tlsys/serving/tests + facade import check).
K1 = 1.2
B = 0.75

# Packed postings (contract A13): global ordinals int32 + term frequencies
# uint16 (6 B/posting on disk, was 16 B int64/int64). Values outside the
# packed range fail closed (never silently truncated).
ORD_DTYPE = np.int32
TF_DTYPE = np.uint16
ORD_MAX = int(np.iinfo(ORD_DTYPE).max)
TF_MAX = int(np.iinfo(TF_DTYPE).max)


def toks(text):
    return text.lower().split()


def idf_of(n, df):
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


def _exact_cast(vals, dtype, vmax, what):
    """asarray(dtype) with exact range validation (fail closed).

    Accepts any integer dtype (incl. legacy int64 postings files) or
    python-int sequences; rejects negatives, overflow, and non-integers.
    Empty input yields an empty packed array."""
    arr = np.asarray(vals)
    if arr.size == 0:
        return np.empty((0,), dtype=dtype)
    if arr.dtype.kind == "f":
        raise ValueError(f"postings {what}: float values not exactly "
                         "representable (fail closed)")
    if arr.dtype.kind not in ("i", "u"):
        # Object/odd input: force exact python-int validation elementwise.
        flat = arr.ravel().tolist()
        for x in flat:
            if not isinstance(x, int) or isinstance(x, bool) \
                    or x < 0 or x > vmax:
                raise ValueError(
                    f"postings {what} {x!r} outside [0, {vmax}] "
                    "(fail closed)")
        return np.asarray(flat, dtype=dtype).reshape(arr.shape)
    if bool((arr < 0).any()):
        raise ValueError(f"postings {what}: negative value (fail closed)")
    if bool((arr > vmax).any()):
        raise ValueError(f"postings {what} exceeds {vmax} (fail closed; "
                         "repack range)")
    return np.asarray(arr, dtype=dtype)


class TermLexicon:
    """Sorted term list + postings in ordinal order for ONE row set.

    Built over live-or-all rows (caller decides; views build over all rows
    and skip tombstoned ordinals at score time so incremental == cold).
    No re-tokenization on merge: merge() remaps term ids and concatenates
    posting runs in ordinal order.
    """

    def __init__(self, terms, offsets, post_ord, post_tf, doclen, df,
                 ordinals):
        # terms: sorted list[str]; offsets: int64 (V+1) into post_*;
        # post_ord: int32 global ordinals ascending within each term;
        # post_tf: uint16 tf values; doclen: {ordinal: n_tokens};
        # df: int array (V,) over indexed rows; ordinals: row ordinals asc.
        # Values are range-checked exact (A13): overflow fails closed.
        self.terms = list(terms)
        self.tid = {t: i for i, t in enumerate(self.terms)}
        self.offsets = np.asarray(offsets, dtype=np.int64)
        self.post_ord = _exact_cast(post_ord, ORD_DTYPE, ORD_MAX, "ordinal")
        self.post_tf = _exact_cast(post_tf, TF_DTYPE, TF_MAX, "tf")
        self.doclen = dict(doclen)
        self.df = np.asarray(df, dtype=np.int64)
        self.ordinals = list(ordinals)

    @classmethod
    def build(cls, row_texts):
        """row_texts: [(ordinal, text)] in any order. One tokenization."""
        per_row = []
        df = {}
        for o, text in row_texts:
            ts = toks(text)
            tf = {}
            for t in ts:
                tf[t] = tf.get(t, 0) + 1
            per_row.append((o, len(ts), tf))
            for t in tf:
                df[t] = df.get(t, 0) + 1
        terms = sorted(df)
        tid = {t: i for i, t in enumerate(terms)}
        posts = [[] for _ in terms]
        doclen = {}
        for o, dl, tf in per_row:
            doclen[o] = dl
            for t, f in tf.items():
                posts[tid[t]].append((o, f))
        offsets = [0]
        po = []
        pt = []
        for run in posts:
            run.sort(key=lambda r: r[0])
            for o, f in run:
                po.append(o)
                pt.append(f)
            offsets.append(len(po))
        return cls(terms, offsets, po, pt, doclen,
                   [df[t] for t in terms],
                   sorted(o for o, _ in row_texts))

    @classmethod
    def from_tf(cls, rows):
        """Build from cached (ordinal, doclen, {term: tf}) WITHOUT
        re-tokenizing (delta seal path; each row tokenized once per
        lifetime)."""
        df = {}
        for _o, _dl, tf in rows:
            for t in tf:
                df[t] = df.get(t, 0) + 1
        terms = sorted(df)
        tid = {t: i for i, t in enumerate(terms)}
        posts = [[] for _ in terms]
        doclen = {}
        for o, dl, tf in rows:
            doclen[o] = dl
            for t, f in tf.items():
                posts[tid[t]].append((o, f))
        offsets = [0]
        po = []
        pt = []
        for run in posts:
            run.sort(key=lambda r: r[0])
            for o, f in run:
                po.append(o)
                pt.append(f)
            offsets.append(len(po))
        return cls(terms, offsets, po, pt, doclen,
                   [df[t] for t in terms],
                   sorted(o for o, _dl, _tf in rows))

    @classmethod
    def merge(cls, parts):
        """Tiered merge: term-id remap + ordinal concat, no re-tokenization.
        parts: [TermLexicon] with disjoint ordinal sets."""
        df = {}
        per_term_runs = {}
        doclen = {}
        ords = []
        for p in parts:
            doclen.update(p.doclen)
            ords.extend(p.ordinals)
            for i, t in enumerate(p.terms):
                s, e = int(p.offsets[i]), int(p.offsets[i + 1])
                run = list(zip(p.post_ord[s:e].tolist(),
                               p.post_tf[s:e].tolist()))
                per_term_runs.setdefault(t, []).append(run)
                df[t] = df.get(t, 0) + int(p.df[i])
        terms = sorted(per_term_runs)
        offsets = [0]
        po = []
        pt = []
        for t in terms:
            merged = sorted((o, f) for run in per_term_runs[t] for o, f in run)
            for o, f in merged:
                po.append(o)
                pt.append(f)
            offsets.append(len(po))
        return cls(terms, offsets, po, pt, doclen,
                   [df[t] for t in terms], sorted(ords))

    def postings_of(self, term):
        i = self.tid.get(term)
        if i is None:
            # Empty arrays (callers use .tolist(); must not branch).
            return self.post_ord[0:0], self.post_tf[0:0]
        s, e = int(self.offsets[i]), int(self.offsets[i + 1])
        return self.post_ord[s:e], self.post_tf[s:e]


def bm25_accumulate_vectorized(sorted_terms, df_of, n, avgdl,
                                 runs_of, live_ord, doclen_arr,
                                 aid_of_ord, counters=None):
    """Exact BM25 accumulation over blocked array runs (Stage B).

    Same arithmetic, order, and emission as bm25_accumulate (bitwise
    identical, differential-pinned): terms in sorted order; within a
    term, runs in the caller-supplied block order (segments in view
    order, then the delta overlay) with ordinals ascending inside
    each run; float64 accumulation; emission in ascending ordinal
    order. No Python loop per posting: per-term work is vectorized
    (gather, live mask, BM25 math, ordered np.add.at accumulation).
    runs_of(term) -> [(ord_array, tf_array)] with array-likes of
    ints; live_ord/doclen_arr index by ordinal; aid_of_ord[ord].
    """
    import numpy as _np
    n_ord = int(_np.asarray(live_ord).shape[0])
    acc = _np.zeros((n_ord,), dtype=_np.float64)
    touched_any = _np.zeros((n_ord,), dtype=bool)
    touched = 0
    k1p1 = K1 + 1.0
    for t in sorted_terms:
        df = df_of(t)
        if df is None:
            continue
        idf = idf_of(n, df)
        for o_arr, f_arr in runs_of(t):
            o = _np.asarray(o_arr, dtype=_np.int64).ravel()
            if o.size == 0:
                continue
            f = _np.asarray(f_arr, dtype=_np.float64).ravel()
            mask = _np.asarray(live_ord)[o]
            o = o[mask]
            if o.size == 0:
                continue
            f = f[mask]
            dl = _np.asarray(doclen_arr, dtype=_np.float64)[o]
            num = f * k1p1
            den = f + K1 * (1.0 - B + B * dl / avgdl)
            contrib = idf * num / den
            # Sequential in occurrence order (same op order as the
            # scalar loop: terms outer, run order inner).
            _np.add.at(acc, o, contrib)
            touched_any[o] = True
            touched += int(o.size)
    if counters is not None:
        counters.record(lex_postings_scanned=touched)
    ords = _np.nonzero(touched_any)[0].tolist()
    return {aid_of_ord[int(o)]: float(acc[int(o)]) for o in ords}


def bm25_accumulate(sorted_terms, df_of, n, avgdl, postings_of, live_of,
                    aid_of, doclen_of, ord_of, counters=None):
    """Exact BM25 accumulation. postings_of(term) yields (ordinal, tf) in
    ASCENDING ordinal order across the whole view (segments in ordinal
    order, then delta). live_of(ordinal)->bool skips tombstones.
    Returns {aid: score} emitted in ascending ordinal order (dict
    insertion order), matching C1's atom_text-ordered emission."""
    acc = {}
    touched = 0
    for t in sorted_terms:
        df = df_of(t)
        if df is None:
            continue
        idf = idf_of(n, df)
        for o, f in postings_of(t):
            o = int(o)
            if not live_of(o):
                continue
            # Python-int scalars: identical float ops to C1's loop
            # (numpy scalars would still be IEEE-correct, but int() is
            # exact and removes all doubt).
            f = int(f)
            dl = int(doclen_of(o))
            num = f * (K1 + 1)
            den = f + K1 * (1 - B + B * dl / avgdl)
            aid = aid_of(int(o))
            acc[aid] = acc.get(aid, 0.0) + idf * num / den
            touched += 1
    if counters is not None:
        counters.record(lex_postings_scanned=touched)
    return {aid: acc[aid]
            for aid in sorted(acc, key=lambda a: ord_of(a))}
