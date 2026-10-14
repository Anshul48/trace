"""HNSW candidate-search interface over holon descriptors (R7-B).

Authority: R6-D NAV-EXPERIMENT selection
(tl-eval/evidence/round6-2026-10-05/trackD/NAV-EXPERIMENT.md section 4:
HNSW wins) + arch record
(handoffs/TL-INGEST-NAVIGATION-ARCHITECTURE-2026-10-05.md sections 3/5,
section 10.3 candidate-search boundary).

Role: candidate DISCOVERY for placement (tlsys.place) and retrieval
(tlsys.index dense-holon leg). Exact local scoring stays with the callers:
this module proposes a bounded candidate set; callers re-score with the
same cosine math as the exact path and apply eligibility/capacity policy.
Semantic holon organization, versioned membership, and the unresolved
path are untouched.

Versioning: a candidate index binds to one committed generation (the
store pin triple) plus per-holon commit seqs. A generation mismatch
refuses loudly (StaleGenerationError: no cross-generation mixing);
per-holon seq mismatches against a live view are dropped and reported;
live holons absent from the index are reported as unpublished (callers
choose exact-scan fallback via include_unpublished).

Memory discipline (arch record section 3: do not duplicate every vector
in several parallel indexes without measuring): by default this module
retains NO descriptor matrix -- only the hnswlib index itself plus
hid<->label/seq maps. The transient float32 input matrix bytes and the
serialized index bytes are both measured and reported via cost().
Callers exact-rescore from their own live descriptors (zero new copies).
Pass retain_matrix=True only for offline analysis; its bytes are then
reported separately.

hnswlib is an OPTIONAL dependency pinned to 0.8.0. Import is lazy:
flag-off product paths never import it. Flag-on paths raise a clear
error when it is missing or the version differs from the pin.

Threading: one hnswlib instance disallows concurrent query/add
(hnswlib parameters doc; arch record section 10.3). One owning writer
builds/updates; serving generations are immutable once published.
"""

import os
import tempfile
import time

HNSW_PIN = "0.8.0"
HNSW_M = 16
HNSW_EF_CONSTRUCTION = 200
HNSW_SEED = 100  # hnswlib init_index default; fixed for determinism
HNSW_SPACE = "cosine"
# ef floor: hnswlib clamps ef >= k, so an ef below k is a silent
# no-op (R6-D section 2 fidelity notes). Queries default to
# max(k, HNSW_MIN_EF), always explicit in the report.
HNSW_MIN_EF = 50


class StaleGenerationError(ValueError):
    """Candidate index generation != caller's pinned generation."""


def check_hnsw_version(version):
    """Raise unless version == HNSW_PIN (pure helper, testable)."""
    if version != HNSW_PIN:
        raise ValueError(
            f"hnswlib version {version!r} != pinned {HNSW_PIN!r}: "
            "refusing (R7-B candidate search is pinned to hnswlib "
            f"{HNSW_PIN})")


def load_hnswlib():
    """Import hnswlib with the R7-B version pin enforced."""
    try:
        import hnswlib
    except ImportError as e:
        raise ImportError(
            "HNSW candidate search needs hnswlib==0.8.0 "
            f"(R7-B pin): {e}") from e
    try:
        from importlib.metadata import version as _dist_version
        check_hnsw_version(_dist_version("hnswlib"))
    except ValueError:
        raise
    except Exception as e:  # pragma: no cover - metadata failure
        raise ValueError(
            f"cannot verify hnswlib=={HNSW_PIN} pin: {e}") from e
    return hnswlib


def normalize_f32(vec, dim=None):
    """L2-normalized float32 vector (hnswlib cosine-space input)."""
    import numpy as np
    v = np.asarray(vec, dtype=np.float64).reshape(-1)
    if dim is not None and v.shape[0] != dim:
        raise ValueError(
            f"descriptor dim {v.shape[0]} != index dim {dim}")
    n = float(np.linalg.norm(v)) or 1.0
    return (v / n).astype(np.float32)


def exact_cosine_topk(qvec, items, k):
    """Reference exact top-k cosine over {hid: descriptor} (float64).

    Same cosine definition as tlsys.index.NarrowIndex.dense_holons and
    tlsys.place._cos: dot over L2 norms with a 1.0 fallback for zero
    vectors. Test/parity oracle only; not on the product path.
    """
    import numpy as np
    q = np.asarray(qvec, dtype=np.float64).reshape(-1)
    qn = float(np.linalg.norm(q)) or 1.0
    scored = []
    for hid, desc in items.items():
        d = np.asarray(desc, dtype=np.float64).reshape(-1)
        dn = float(np.linalg.norm(d)) or 1.0
        scored.append((hid, float(q @ d / (qn * dn))))
    scored.sort(key=lambda kv: -kv[1])
    return scored[:max(0, k)]


class HolonCandidateIndex:
    """Versioned HNSW candidate search over one holon population.

    Lifecycle: build() once at a generation pin (immutable serving
    generation), then query(). Incremental add() is supported for
    append measurement but a rebuilt generation is the preferred
    serving update (hnswlib has no concurrent query/add).
    """

    def __init__(self):
        self._p = None  # hnswlib.Index or None when n == 0
        self.hids = []  # label -> hid (sorted at build: deterministic)
        self._label = {}  # hid -> label
        self._seq = {}  # hid -> committed seq at build
        self.generation = None  # store pin triple string
        self.dim = None
        self.n = 0
        self.params = {"space": HNSW_SPACE, "M": HNSW_M,
                       "ef_construction": HNSW_EF_CONSTRUCTION,
                       "seed": HNSW_SEED}
        self._matrix = None  # only when retain_matrix=True
        self._cost = {"build_s": 0.0, "update_s": 0.0,
                      "update_count": 0, "index_bytes": 0,
                      "vector_input_bytes": 0,
                      "retained_matrix_bytes": 0, "map_entries": 0}

    # -- build / update --------------------------------------------
    def build(self, holons, generation, m=HNSW_M,
              ef_construction=HNSW_EF_CONSTRUCTION, seed=HNSW_SEED,
              retain_matrix=False):
        """Build over {hid: {descriptor, seq}} at generation pin.

        holons entries need "descriptor" ([float]); "seq" (int commit
        seq) is the versioned ref -- missing seq is recorded as None
        (unversioned, e.g. same-batch pending) and never claimed fresh.
        Deterministic for fixed (holons, m, ef_construction, seed):
        labels follow sorted hid order and hnswlib takes random_seed.
        """
        import numpy as np
        t0 = time.perf_counter()
        hids = sorted(holons.keys())
        self.params = {"space": HNSW_SPACE, "M": m,
                       "ef_construction": ef_construction, "seed": seed}
        self.generation = generation
        self.hids = hids
        self._label = {h: i for i, h in enumerate(hids)}
        self._seq = {h: holons[h].get("seq") for h in hids}
        mat = None
        if hids:
            hnswlib = load_hnswlib()
            mat = np.stack([normalize_f32(holons[h]["descriptor"])
                            for h in hids])
            self.dim = int(mat.shape[1])
            p = hnswlib.Index(space=HNSW_SPACE, dim=self.dim)
            p.init_index(max_elements=len(hids),
                         ef_construction=ef_construction, M=m,
                         random_seed=seed)
            p.add_items(mat, np.arange(len(hids)))
            p.set_ef(max(HNSW_MIN_EF, min(len(hids), 200)))
            self._p = p
            self._cost["vector_input_bytes"] = int(mat.nbytes)
        else:
            self.dim = None
            self._p = None
            self._cost["vector_input_bytes"] = 0
        self.n = len(hids)
        self._cost["build_s"] = time.perf_counter() - t0
        self._cost["index_bytes"] = self._measure_bytes()
        self._cost["map_entries"] = len(hids)
        if retain_matrix and mat is not None:
            self._matrix = mat.copy()
            self._cost["retained_matrix_bytes"] = int(mat.nbytes)
        else:
            self._matrix = None
            self._cost["retained_matrix_bytes"] = 0
        return self

    def add(self, holons, generation):
        """Incrementally add {hid: {descriptor, seq}} (same generation).

        Raises StaleGenerationError on generation mismatch. New hids
        only (re-add of an indexed hid is a no-op returning 0 added;
        changed descriptors need a rebuild: no in-place vector update
        in hnswlib). Returns count added. Update wall + new index
        bytes are folded into cost().
        """
        import numpy as np
        if generation != self.generation:
            raise StaleGenerationError(
                f"candidate index at {self.generation}, "
                f"add at {generation}: rebuild, no mixing")
        fresh = [h for h in sorted(holons.keys())
                 if h not in self._label]
        if not fresh:
            return 0
        if self._p is None:
            # Empty index becomes a real one via rebuild path.
            merged = {h: {"descriptor": holons[h]["descriptor"],
                          "seq": holons[h].get("seq")} for h in fresh}
            base = self.generation
            params = dict(self.params)
            self.build(merged, base, m=params["M"],
                       ef_construction=params["ef_construction"],
                       seed=params["seed"],
                       retain_matrix=self._matrix is not None)
            return len(fresh)
        t0 = time.perf_counter()
        mat = np.stack([normalize_f32(holons[h]["descriptor"],
                                      dim=self.dim) for h in fresh])
        base = self.n
        self._p.resize_index(base + len(fresh))
        self._p.add_items(mat, np.arange(base, base + len(fresh)))
        for i, h in enumerate(fresh):
            self._label[h] = base + i
            self.hids.append(h)
            self._seq[h] = holons[h].get("seq")
        self.n = len(self.hids)
        dt = time.perf_counter() - t0
        self._cost["update_s"] += dt
        self._cost["update_count"] += 1
        self._cost["update_last_s"] = dt
        self._cost["update_last_added"] = len(fresh)
        self._cost["vector_input_bytes"] += int(mat.nbytes)
        self._cost["index_bytes"] = self._measure_bytes()
        self._cost["map_entries"] = self.n
        if self._matrix is not None:
            self._matrix = np.vstack([self._matrix, mat])
            self._cost["retained_matrix_bytes"] = int(
                self._matrix.nbytes)
        return len(fresh)

    def _measure_bytes(self):
        if self._p is None:
            return 0
        fd, path = tempfile.mkstemp(prefix="tl-hnsw-size-",
                                    suffix=".bin")
        try:
            os.close(fd)
            self._p.save_index(path)
            return os.path.getsize(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    # -- query ------------------------------------------------------
    def query(self, qvec, k=200, ef=None, generation=None, live=None):
        """Top-k candidate hids for qvec (bounded discovery).

        k is clamped to the indexed population. ef defaults to
        max(k, HNSW_MIN_EF) and is always reported. generation, when
        given, must equal the build generation (else
        StaleGenerationError). live, when given ({hid: {seq}}), drops
        candidates whose live seq differs from the indexed seq
        (reported as stale_dropped, never silently rescored).

        Returns {"hids", "scores" (cosine sim), "k", "ef", "ms",
        "stale_dropped", "n_scored_native_unknown": True}: hnswlib
        exposes no visited/distance-call counter (R6-D section 2), so
        native work stays explicitly unknown; callers report their own
        exact-rescore counts.
        """
        import numpy as np
        if generation is not None and generation != self.generation:
            raise StaleGenerationError(
                f"candidate index at {self.generation}, "
                f"queried at {generation}: rebuild, no mixing")
        kk = max(0, min(int(k), self.n))
        if ef is None:
            ef = max(kk, HNSW_MIN_EF)
        rep = {"hids": [], "scores": [], "k": kk, "ef": int(ef),
               "ms": 0.0, "stale_dropped": [],
               "n_scored_native_unknown": True}
        if kk == 0 or self._p is None:
            return rep
        q = normalize_f32(qvec, dim=self.dim).reshape(1, -1)
        t0 = time.perf_counter()
        self._p.set_ef(int(ef))
        labels, dists = self._p.knn_query(q, k=kk)
        rep["ms"] = (time.perf_counter() - t0) * 1000.0
        for lab, dist in zip(labels[0], dists[0]):
            hid = self.hids[int(lab)]
            if live is not None:
                lv = live.get(hid)
                if lv is None or lv.get("seq") != self._seq.get(hid):
                    rep["stale_dropped"].append(hid)
                    continue
            rep["hids"].append(hid)
            rep["scores"].append(float(1.0 - dist))
        return rep

    def coverage(self, live):
        """Version audit of a live {hid: {seq}} view against the index.

        Returns {"indexed", "live", "stale", "unpublished"}: stale =
        indexed hids whose live seq differs (or which vanished);
        unpublished = live hids absent from the index (committed after
        build, or same-batch pending without seq).
        """
        live_ids = set(live.keys())
        indexed_ids = set(self._label.keys())
        stale = sorted(h for h in indexed_ids
                       if h not in live
                       or live[h].get("seq") != self._seq.get(h))
        unpublished = sorted(live_ids - indexed_ids)
        return {"indexed": len(indexed_ids), "live": len(live_ids),
                "stale": stale, "unpublished": unpublished}

    def cost(self):
        """Measured build/update/memory accounting (JSON-safe)."""
        out = dict(self._cost)
        out.update({"n": self.n, "dim": self.dim,
                    "generation": self.generation,
                    "hnswlib_pin": HNSW_PIN})
        out.update({f"param_{k}": v
                    for k, v in self.params.items()})
        return out
