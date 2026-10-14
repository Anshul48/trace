"""Lane BUILD100M: keyed≡legacy slice-scale differential (10M).

Compares the keyed 10M build (store A) against the C1 10M store copy
(store B) at occurrence level. Atom IDs bind per-store revision IDs,
so cross-store identity is (doc_id, chunk_ix) occurrence signatures
(O-series convention); store-internal UUIDs (op_ids, revision_ids,
atom ids, relation rids) are normalized away, never compared.

Levels:
  L1 occurrences: per-doc chunk spans + chunk text digests.
  L2 xdoc: {xdoc_id: sorted(member occs)} + exact descriptors.
  L3 seg: leaves {lid: sorted(member occs)} + parents {pid:
      (children order, sorted(member occs))} + exact descriptors.
  L4 relations: multiset of (rel_type, [(role, occ)],
      qualifiers, status, sorted(grounding occs)).

Descriptor vectors compare bitwise (same code path, same op order);
any max-abs-diff > 0 is reported with magnitude for classification.

Writes DIFF-RECEIPT.json {verdict: PASS|FAIL, levels, counts,
mismatches (bounded)}. Exit 0 on PASS, 1 on FAIL (STOP-and-classify).

Usage on the VM:
  PYTHONHASHSEED=0 /srv/tl/venv/bin/python b100m_diff10m.py \\
    --root /srv/tl/lane-relaunch/work \\
    --store-a /srv/tl/lane-relaunch/scratch/build-10m-c2/store \\
    --store-b /srv/tl/lane-relaunch/scratch/c1-10m-c2 \\
    --out /srv/tl/lane-relaunch/scratch/build-10m-c2/DIFF-RECEIPT.json

RELAUNCH: guard lane-relaunch; comparison logic unchanged.
"""
import argparse
import hashlib
import json
import os
import sys
import time


GUARD = "lane-relaunch"
MAX_MISMATCH = 25


def log(msg):
    print(f"[b100m-diff {time.strftime('%H:%M:%S', time.gmtime())}Z] "
          f"{msg}", flush=True)


def sha16(b):
    return hashlib.sha256(b).hexdigest()[:16]


def load_state(tl, label):
    """Normalized committed state for occurrence compare."""
    from tlsys.index import NarrowIndex
    from tlsys.proj import Projections
    from tlsys import relations as _relations
    log(f"{label}: opening index + projections…")
    pin = tl.pin()
    idx = NarrowIndex(tl, pin)
    proj = Projections.cached(tl)
    proj.update(tl)
    occ_of = {}  # aid -> (doc_id, chunk_ix)
    occ_text = {}  # (doc_id, chunk_ix) -> text sha16
    doc_chunks = {}  # doc_id -> [(chunk_ix, span, text sha16)]
    for aid, meta in idx.atoms.items():
        doc = meta.get("doc_id")
        span = tuple((meta.get("span") or [0, 0])[:2])
        body = tl.read_artifact(meta["text_art"],
                                expect_digest=meta["text_digest"])
        # chunk_ix from committed projection rows (authoritative),
        # fallback to span order below.
        occ_of[aid] = (doc, span, sha16(body))
        doc_chunks.setdefault(doc, []).append((span, sha16(body)))
    # Assign chunk_ix by span order per doc (== committed chunk order:
    # spans are non-overlapping ascending by construction).
    for doc, rows in doc_chunks.items():
        rows.sort(key=lambda t: (t[0][0], t[0][1]))
    order_of = {}
    for doc, rows in doc_chunks.items():
        for ix, (span, th) in enumerate(rows):
            order_of[(doc, span)] = ix
    occ = {}  # aid -> (doc_id, chunk_ix)
    for aid, (doc, span, _th) in occ_of.items():
        occ[aid] = (doc, order_of[(doc, span)])
    for doc, rows in doc_chunks.items():
        doc_chunks[doc] = [(ix, list(span), th)
                           for ix, (span, th) in enumerate(rows)]

    def norm_members(aids):
        return sorted(occ[a] for a in aids)

    xdoc = {}
    for hid, ent in proj.xholons_view().items():
        xdoc[hid] = {"members": norm_members(ent["members"]),
                     "descriptor": list(ent["descriptor"])}
    hier = proj.hierarchy_view()
    leaves = {}
    for lid, ent in hier["leaves"].items():
        leaves[lid] = {"members": norm_members(ent["members"]),
                       "descriptor": list(ent["descriptor"])}
    parents = {}
    for pid, ent in hier["parents"].items():
        parents[pid] = {"children": list(ent.get("children") or []),
                        "members": norm_members(ent["members"]),
                        "descriptor": list(ent["descriptor"])}
    rels = []
    for _rid, row in _relations.read_relations(tl, pin).items():
        rec = row["record"]
        rels.append({
            "rel_type": rec["rel_type"],
            "endpoints": sorted(
                (role, occ[aid]) for role, aid in rec["endpoints"]),
            "qualifiers": rec["qualifiers"],
            "status": rec["status"],
            "grounding": sorted(occ[g] for g in rec["grounding"]),
        })
    rels.sort(key=lambda r: json.dumps(r, sort_keys=True, default=str))
    return {"pin": pin[3], "n_atoms": len(idx.atoms),
            "doc_chunks": doc_chunks, "xdoc": xdoc,
            "leaves": leaves, "parents": parents, "relations": rels}


def max_abs_diff(a, b):
    m = 0.0
    for x, y in zip(a, b):
        d = abs(x - y)
        if d > m:
            m = d
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--store-a", required=True)
    ap.add_argument("--store-b", required=True)
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    for p in (ns.store_a, ns.store_b, ns.out):
        if GUARD not in os.path.abspath(p):
            print(f"refusing: {p} not under {GUARD}", flush=True)
            return 2
    sys.path.insert(0, os.path.join(ns.root, "tl-sys"))
    from tlsys.store_if import TLStore

    tla = TLStore(ns.store_a, create=False,
                  lease_owner=f"b100m-diff-a-{os.getpid()}")
    tlb = TLStore(ns.store_b, create=False,
                  lease_owner=f"b100m-diff-b-{os.getpid()}")
    try:
        sta = load_state(tla, "A(keyed)")
        stb = load_state(tlb, "B(c1)")
    finally:
        tla.close()
        tlb.close()

    levels, mismatches = {}, []

    def mismatch(level, where, a, b):
        if len(mismatches) < MAX_MISMATCH:
            mismatches.append({"level": level, "where": where,
                               "a": a, "b": b})

    # L1 occurrences
    ok = True
    if set(sta["doc_chunks"]) != set(stb["doc_chunks"]):
        ok = False
        only_a = sorted(set(sta["doc_chunks"])
                        - set(stb["doc_chunks"]))[:5]
        only_b = sorted(set(stb["doc_chunks"])
                        - set(sta["doc_chunks"]))[:5]
        mismatch("L1", "doc-set", only_a, only_b)
    n_chunks = 0
    for doc in sta["doc_chunks"]:
        ra, rb = sta["doc_chunks"][doc], stb["doc_chunks"].get(doc)
        if ra != rb:
            ok = False
            mismatch("L1", doc, ra[:4], (rb or [])[:4])
        n_chunks += len(ra)
    levels["L1_occurrences"] = {"pass": ok, "n_docs": len(
        sta["doc_chunks"]), "n_chunks": n_chunks}

    # L2/L3 holon sets
    for level, key, sub in (("L2_xdoc", "xdoc", None),
                            ("L3_leaves", "leaves", None),
                            ("L3_parents", "parents", "children")):
        ok = True
        ka, kb = sta[key], stb[key]
        if set(ka) != set(kb):
            ok = False
            mismatch(level, "id-set",
                     sorted(set(ka) - set(kb))[:5],
                     sorted(set(kb) - set(ka))[:5])
        worst, worst_id = 0.0, None
        for hid in ka:
            if hid not in kb:
                continue
            ea, eb = ka[hid], kb[hid]
            if ea["members"] != eb["members"]:
                ok = False
                mismatch(level, hid,
                         ea["members"][:6], eb["members"][:6])
            if sub and ea[sub] != eb[sub]:
                ok = False
                mismatch(level, hid + "." + sub,
                         ea[sub][:6], eb[sub][:6])
            if len(ea["descriptor"]) != len(eb["descriptor"]):
                ok = False
                mismatch(level, hid + ".dim",
                         len(ea["descriptor"]),
                         len(eb["descriptor"]))
            else:
                d = max_abs_diff(ea["descriptor"], eb["descriptor"])
                if d > worst:
                    worst, worst_id = d, hid
                if d != 0.0:
                    ok = False
                    if len(mismatches) < MAX_MISMATCH:
                        mismatches.append(
                            {"level": level, "where": hid + ".desc",
                             "max_abs_diff": d})
        levels[level] = {"pass": ok, "n": len(ka),
                         "worst_desc_diff": worst,
                         "worst_desc_id": worst_id}

    # L4 relations
    ok = sta["relations"] == stb["relations"]
    if not ok:
        mismatch("L4", "records", sta["relations"][:6],
                 stb["relations"][:6])
    levels["L4_relations"] = {"pass": ok,
                              "n": len(sta["relations"])}

    verdict = "PASS" if all(v["pass"] for v in levels.values()) \
        else "FAIL"
    receipt = {
        "verdict": verdict,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "store_a": ns.store_a, "store_b": ns.store_b,
        "pin_a": sta["pin"], "pin_b": stb["pin"],
        "n_atoms_a": sta["n_atoms"], "n_atoms_b": stb["n_atoms"],
        "levels": levels, "mismatches": mismatches,
    }
    with open(ns.out, "w") as f:
        json.dump(receipt, f, indent=1, sort_keys=True, default=str)
    for lv, v in levels.items():
        log(f"{lv}: {'PASS' if v['pass'] else 'FAIL'} {v}")
    log(f"DIFF {verdict} -> {ns.out}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
