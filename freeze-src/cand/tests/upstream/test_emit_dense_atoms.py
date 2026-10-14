"""Focused E1 test: dense-atom emission arm (EMIT_DENSE_ATOMS cfg flag).

Behavior contract:
- Flag off (default): emission is fused lex/holon RRF only; an atom with
  no lexical support emits 0.0 and is deferred below TAU_SEL.
- Flag on: emission adds a dense-atom RRF term (rank-only, k=60); the
  same atom clears admission on dense support alone.
- Region ranking is identical in both arms (the arm touches emission
  only); receipt carries emit_dense_atoms diagnostics.

Deterministic fake encoder through the documented embed seam (README:
any encoder), so no model weights are needed. Needs the venv for
blake3. Scratch store under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_emit_dense_atoms.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 8


def pad(v):
    return [float(x) for x in v] + [0.0] * (DIM - len(v))


# Query is lexically about docA but vector-close to docB only.
V_Q = pad([1.0, 0.0, 0.0])
V_A = pad([0.0, 1.0, 0.0])
V_B = pad([0.99, 0.01, 0.0])
V_C = pad([0.0, 0.0, 1.0])

DOCA = "apple banana cherry"
DOCB = "quantum entanglement paradox"
DOCC = "zebra xylophone quartz"
QUERY = "apple"

VECS = {DOCA: V_A, DOCB: V_B, DOCC: V_C, QUERY: V_Q}


def emb(texts):
    return [list(VECS[t]) for t in texts]


def emb1(q):
    return list(VECS[q])


def main():
    tmp = tempfile.mkdtemp(prefix="tl-e1-test-")
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="e1-test")
    rep = ingest_docs(tl, [("docA", DOCA), ("docB", DOCB), ("docC", DOCC)],
                      emb, store_id="e1-test")
    check("ingest-3-atoms-3-holons",
          rep["n_atoms"] == 3 and rep["n_holons"] == 3, repr(rep))
    idx = NarrowIndex(tl, tl.pin())

    # Index leg sanity: dense-atom top hit is the docB atom.
    da = idx.dense_atoms(V_Q)
    top_aid = da[0][0]
    check("dense-atoms-ranks-docB-first",
          idx.atoms[top_aid]["doc_id"] == "docB",
          repr([(idx.atoms[a]["doc_id"], round(s, 4)) for a, s in da]))

    OFF = {"EMIT_DENSE_ATOMS": False, "REGION_DENSE_ATOMS": False,
           "PRUNE_SPLIT": False, "DISCLOSE_TOP1_CUT": None}
    off = NarrowQuery(tl, idx, emb1, cfg=dict(OFF))
    dos_off, rec_off = off.run(QUERY)
    on = NarrowQuery(tl, idx, emb1, cfg=dict(
        OFF, EMIT_DENSE_ATOMS=True, DENSE_WEIGHT=1.0))
    dos_on, rec_on = on.run(QUERY)

    served_off = [e["doc_id"] for e in dos_off["entries"]]
    served_on = [e["doc_id"] for e in dos_on["entries"]]
    check("flag-off-serves-docA-not-docB",
          "docA" in served_off and "docB" not in served_off,
          repr(served_off))
    check("flag-on-serves-docB-on-dense-support",
          "docA" in served_on and "docB" in served_on,
          repr(served_on))
    b_on = [e for e in dos_on["entries"] if e["doc_id"] == "docB"][0]
    check("flag-on-docB-emission-is-dense-rrf-rank0",
          abs(b_on["emitted_score"] - 1.0 / 60.0) < 1e-9,
          repr(b_on["emitted_score"]))

    m_off = rec_off["metrics"]
    m_on = rec_on["metrics"]
    check("region-ranking-identical-across-arms",
          m_off["regions_ranked"] == m_on["regions_ranked"]
          and m_off["R_regions"] == m_on["R_regions"]
          and abs(m_off["top_region_score"] - m_on["top_region_score"]) < 1e-12,
          repr({k: (m_off.get(k), m_on.get(k)) for k in
                ("regions_ranked", "R_regions", "top_region_score")}))
    check("receipt-diag-flag-off",
          m_off["emit_dense_atoms"] is False
          and m_off["dense_atom_seeds"] == 0,
          repr({k: m_off.get(k) for k in
                ("emit_dense_atoms", "dense_atom_seeds")}))
    check("receipt-diag-flag-on",
          m_on["emit_dense_atoms"] is True
          and m_on["dense_atom_seeds"] == 3
          and m_on["dense_cos_top1"] > 0.99
          and m_on["dense_cos_margin"] > 0.9,
          repr({k: m_on.get(k) for k in
                ("emit_dense_atoms", "dense_atom_seeds",
                 "dense_cos_top1", "dense_cos_margin")}))
    check("budget-counts-arm-present-only-when-on",
          "seed-dense-atoms" not in m_off["op_class_counts"]
          and m_on["op_class_counts"].get("seed-dense-atoms") == 3,
          repr((m_off["op_class_counts"], m_on["op_class_counts"])))

    # -- E1b: DENSE_WEIGHT uniform scale ------------------------------
    # (An earlier per-rank guard variant inverted rankings via a scale
    # schism — curated S2 nDCG 0.666 -> 0.259 — and was removed. The
    # weight must stay uniform across atoms; see query.py comment.)
    half = NarrowQuery(tl, idx, emb1, cfg={"EMIT_DENSE_ATOMS": True,
                                           "DENSE_WEIGHT": 0.5})
    dos_half, _rec_half = half.run(QUERY)
    b_half = [e for e in dos_half["entries"] if e["doc_id"] == "docB"][0]
    check("weight-half-scales-dense-term",
          abs(b_half["emitted_score"] - 0.5 / 60.0) < 1e-9,
          repr(b_half["emitted_score"]))
    zero = NarrowQuery(tl, idx, emb1, cfg=dict(
        OFF, EMIT_DENSE_ATOMS=True, DENSE_WEIGHT=0.0))
    dos_zero, _rec_zero = zero.run(QUERY)
    check("weight-zero-equals-flag-off",
          [(e["doc_id"], e["emitted_score"])
           for e in dos_zero["entries"]] ==
          [(e["doc_id"], e["emitted_score"])
           for e in dos_off["entries"]],
          repr(([e["doc_id"] for e in dos_zero["entries"]],
                [e["doc_id"] for e in dos_off["entries"]])))

    # -- E2: DISCLOSE_TOP1_CUT trigger --------------------------------
    # Fixture top1 cosine is ~0.9999 (query vector ~ docB atom vector).
    lo = NarrowQuery(tl, idx, emb1, cfg={"EMIT_DENSE_ATOMS": True,
                                         "DISCLOSE_TOP1_CUT": 0.99999})
    dos_lo, rec_lo = lo.run(QUERY)
    check("top1-trigger-fires-below-cut",
          rec_lo["flags"]["routing_uncertain_Q3.3"] is True
          and rec_lo["flags"]["low_retrieval_similarity_Q3.3"] is True
          and rec_lo["metrics"]["top1_trigger_fired"] is True
          and rec_lo["uncertainty_presentation"]
          == "not sure (low retrieval similarity)",
          repr((rec_lo["flags"], rec_lo["metrics"].get("top1_trigger_fired"),
                rec_lo["uncertainty_presentation"])))
    check("top1-trigger-never-withholds",
          [e["doc_id"] for e in dos_lo["entries"]] ==
          [e["doc_id"] for e in dos_on["entries"]],
          repr([e["doc_id"] for e in dos_lo["entries"]]))
    hi = NarrowQuery(tl, idx, emb1, cfg={"EMIT_DENSE_ATOMS": True,
                                         "DISCLOSE_TOP1_CUT": 0.5})
    _dos_hi, rec_hi = hi.run(QUERY)
    check("top1-trigger-silent-above-cut",
          rec_hi["metrics"]["top1_trigger_fired"] is False
          and rec_hi["flags"]["routing_uncertain_Q3.3"] is False
          and rec_hi["flags"]["low_retrieval_similarity_Q3.3"] is False
          and rec_hi["uncertainty_presentation"]
          == "unassessed (similarity above floor; "
             "not an answerability claim)",
          repr((rec_hi["flags"], rec_hi["uncertainty_presentation"])))
    nosig = NarrowQuery(tl, idx, emb1,
                        cfg=dict(OFF, DISCLOSE_TOP1_CUT=0.99999))
    _dos_ns, rec_ns = nosig.run(QUERY)
    check("top1-trigger-silent-without-dense-scan",
          rec_ns["metrics"]["top1_trigger_fired"] is False,
          repr(rec_ns["metrics"].get("top1_trigger_fired")))

    # -- S4 honest disclosure (2026-10-04) -------------------------------
    # Per-entry support labels + always-on dossier support counts;
    # silence presents as "unassessed", never "sure". Fixture: docA
    # has lex+dense, docB/docC dense-only (cf. funnel-support-mix).
    sup = {e["doc_id"]: e.get("support") for e in dos_on["entries"]}
    check("support-labels-per-entry",
          sup == {"docA": "both", "docB": "dense-only",
                  "docC": "dense-only"},
          repr(sup))
    check("support-counts-always-on",
          m_on.get("support_counts")
          == {"lex_only": 0, "dense_only": 2,
              "both": 1, "neither": 0},
          repr(m_on.get("support_counts")))
    gate = NarrowQuery(tl, idx, emb1, cfg={"EMIT_DENSE_ATOMS": True,
                                           "DISCLOSE_TOP1_CUT": 0.5,
                                           "TAU": 1.0})
    _dos_g, rec_g = gate.run(QUERY)
    check("gate-uncertainty-attributes-region-support",
          rec_g["metrics"]["top1_trigger_fired"] is False
          and rec_g["flags"]["routing_uncertain_Q3.3"] is True
          and rec_g["uncertainty_presentation"]
          == "not sure (low region support)",
          repr((rec_g["flags"],
                rec_g["metrics"].get("top1_trigger_fired"),
                rec_g["uncertainty_presentation"])))

    # -- promoted defaults (2026-10-04): no-cfg entry point --------
    dflt = NarrowQuery(tl, idx, emb1)
    _dos_d, rec_d = dflt.run(QUERY)
    m_d = rec_d["metrics"]
    check("defaults-emit-dense-on",
          m_d["emit_dense_atoms"] is True
          and m_d["dense_atom_seeds"] == 3,
          repr({k: m_d.get(k) for k in
                ("emit_dense_atoms", "dense_atom_seeds")}))
    check("defaults-trigger-silent-high-sim",
          m_d.get("top1_trigger_fired") is False,
          repr(m_d.get("top1_trigger_fired")))
    import tlsys.query as _qq
    check("defaults-module-pins",
          _qq.EMIT_DENSE_ATOMS is True
          and _qq.DENSE_WEIGHT == 0.5
          and _qq.DISCLOSE_TOP1_CUT == 0.30
          and _qq.REGION_DENSE_ATOMS is True
          and _qq.REGION_DENSE_WEIGHT == 0.3
          and _qq.PRUNE_SPLIT is True
          and _qq.M_REGIONS == 20,
          repr([(k, getattr(_qq, k)) for k in
                ("EMIT_DENSE_ATOMS", "DENSE_WEIGHT",
                 "DISCLOSE_TOP1_CUT", "REGION_DENSE_ATOMS",
                 "REGION_DENSE_WEIGHT", "PRUNE_SPLIT",
                 "M_REGIONS")]))

    # -- E3 prep: TRACE_FUNNEL ----------------------------------------
    tr = NarrowQuery(tl, idx, emb1, cfg={"EMIT_DENSE_ATOMS": True,
                                         "TRACE_FUNNEL": True})
    _dos_tr, rec_tr = tr.run(QUERY)
    fun = rec_tr["metrics"]["funnel"]
    check("funnel-present-with-counts",
          isinstance(fun, dict)
          and fun["candidates"] == 3
          and fun["cand_both"] + fun["cand_lex_only"]
          + fun["cand_dense_only"] + fun["cand_neither"] == 3
          and fun["prune_in"] == 3 and fun["admitted"] == 3
          and fun["entries"] == 3
          and fun["integrity_withheld"] == 0
          and len(fun["pre_prune_top10"]) == 3,
          repr(fun))
    check("funnel-support-mix",
          fun["cand_both"] == 1 and fun["cand_dense_only"] == 2
          and fun["cand_lex_only"] == 0 and fun["cand_neither"] == 0,
          repr({k: fun[k] for k in
                ("cand_both", "cand_dense_only",
                 "cand_lex_only", "cand_neither")}))
    check("funnel-absent-when-off",
          rec_off["metrics"]["funnel"] is None,
          repr(rec_off["metrics"].get("funnel")))

    tl.close()
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
