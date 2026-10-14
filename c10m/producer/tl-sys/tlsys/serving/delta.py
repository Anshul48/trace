"""DeltaSegment: mutable (hi_last, frontier] overlay. Same scoring
interfaces as a sealed Segment. advance() copies (bounded by flush size);
the old object freezes (retained views keep it by reference).
"""

import numpy as np


class DeltaSegment:
    def __init__(self, lo=0):
        self.lo = lo          # sealed frontier below the delta
        self.hi = lo          # consumed frontier (exclusive top)
        self.atom_rows = []   # [{aid, ordinal, seq, op_id, doc_id, span,
                              #   text_art, text_digest}] ordinal-asc
        self.texts = []       # parallel to atom_rows
        self.holon_rows = []  # [{hid, ordinal, seq, op_id, members,
                              #   descriptor(list f64), kind, children}]
        self.retired_docs = set()  # retirement markers in (lo, hi]
        self.op_ids = []      # commit op_ids in scan order (validation)
        self.n_commit_rows = 0
        # Lexical incrementals (no retokenization on seal: tf_cache rides).
        self.tf_cache = {}    # ordinal -> (doclen, {term: tf})
        self.postings = {}    # term -> [(ordinal, tf)] ordinal-asc
        self.df_delta = {}    # term -> doc count over delta rows
        self.doclen = {}      # ordinal -> doclen
        # Dense incrementals.
        self.vec_rows = []    # [float32 array] parallel to atom_rows
        self.overrides = {}   # position -> float64 exact row
        self._frozen = False

    def _check(self):
        if self._frozen:
            raise ValueError("DeltaSegment is frozen (retained view)")

    def freeze(self):
        self._frozen = True

    def copy(self):
        """Bounded shallow copy for advance (row objects shared)."""
        d = DeltaSegment(self.lo)
        d.hi = self.hi
        d.atom_rows = list(self.atom_rows)
        d.texts = list(self.texts)
        d.holon_rows = list(self.holon_rows)
        d.retired_docs = set(self.retired_docs)
        d.op_ids = list(self.op_ids)
        d.n_commit_rows = self.n_commit_rows
        d.tf_cache = dict(self.tf_cache)
        d.postings = {t: list(run) for t, run in self.postings.items()}
        d.df_delta = dict(self.df_delta)
        d.doclen = dict(self.doclen)
        d.vec_rows = list(self.vec_rows)
        d.overrides = dict(self.overrides)
        return d

    def append_atom(self, row, text, vec_f64, dl, tf):
        self._check()
        o = row["ordinal"]
        self.atom_rows.append(row)
        self.texts.append(text)
        v32 = np.asarray(vec_f64, dtype=np.float32)
        self.vec_rows.append(np.ascontiguousarray(v32))
        if np.any(v32.astype(np.float64) != np.asarray(vec_f64,
                                                       dtype=np.float64)):
            self.overrides[len(self.vec_rows) - 1] = np.asarray(
                vec_f64, dtype=np.float64).copy()
        self.tf_cache[o] = (dl, dict(tf))
        self.doclen[o] = dl
        for t, f in tf.items():
            self.postings.setdefault(t, []).append((o, f))
            self.df_delta[t] = self.df_delta.get(t, 0) + 1

    def append_holon(self, row):
        self._check()
        self.holon_rows.append(row)

    def note_commit(self, op_id):
        self._check()
        self.op_ids.append(op_id)
        self.n_commit_rows += 1

    def mat32(self):
        if not self.vec_rows:
            return np.empty((0, 0), dtype=np.float32)
        return np.stack(self.vec_rows).astype(np.float32)

    def n_atoms(self):
        return len(self.atom_rows)

    def resort(self):
        """Restore ordinal-ascending row order (external-mutation path).

        Sorts atom_rows/texts/vec_rows by ordinal, remaps override
        positions, and re-sorts posting runs (tf_cache/doclen keyed
        by ordinal are order-free; df counts are order-free).
        """
        if self.atom_rows:
            order = sorted(range(len(self.atom_rows)),
                           key=lambda i: self.atom_rows[i]["ordinal"])
            self.atom_rows = [self.atom_rows[i] for i in order]
            self.texts = [self.texts[i] for i in order]
            self.vec_rows = [self.vec_rows[i] for i in order]
            new_ov = {}
            for new_i, old_i in enumerate(order):
                if old_i in self.overrides:
                    new_ov[new_i] = self.overrides[old_i]
            self.overrides = new_ov
        for run in self.postings.values():
            run.sort(key=lambda p: p[0])

    def norms64(self):
        """ float64 norms parallel to atom_rows (C1 zero->1.0 rule).

        Override rows use their exact float64 vector; the rest use the
        FP32 row (identical to build_fp32 for exactly-held rows)."""
        n = len(self.vec_rows)
        out = np.empty((n,), dtype=np.float64)
        for i, v in enumerate(self.vec_rows):
            ov = self.overrides.get(i)
            r = np.asarray(ov if ov is not None else v,
                           dtype=np.float64)
            out[i] = float(np.linalg.norm(r))
        out[out == 0.0] = 1.0
        return out
