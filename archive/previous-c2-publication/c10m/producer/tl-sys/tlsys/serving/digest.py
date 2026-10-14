"""Canonical logical digest (D3: incremental == cold at the same pin).

Order-independent hash over the LOGICAL content: live atoms (id, seq,
op, doc, span, text bytes, float64 descriptor bits), live holons (id,
seq, op, members in stored order, descriptor bits, kind, children),
retired docs/aids (sorted), live stats (N, total, per-term df sorted).
Two views built by different paths (incremental advance vs cold build
vs cold load from segments) agree iff they would serve identically.
"""

import hashlib
import json

import numpy as np


def _h():
    return hashlib.sha256()


def canonical_digest(atoms, holons, atom_text, retired_docs, retired_aids,
                     live_n, total_tokens, df):
    """atoms/holons: live dicts (C1-shaped entries); atom_text: live map;
    df: live term->int. All ordering canonicalized here."""
    h = _h()
    for aid in sorted(atoms):
        e = atoms[aid]
        h.update(b"A\x00" + aid.encode("utf-8") + b"\x00")
        h.update(json.dumps(
            {"seq": e["seq"], "op": e.get("op_id"), "doc": e["doc_id"],
             "span": list(e["span"]), "tart": e["text_art"],
             "tdigest": e["text_digest"]}, sort_keys=True).encode())
        h.update(b"\x00" + atom_text[aid].encode("utf-8") + b"\x00")
        h.update(np.asarray(e["descriptor"],
                            dtype=np.float64).tobytes() + b"\x00")
    for hid in sorted(holons):
        e = holons[hid]
        h.update(b"H\x00" + hid.encode("utf-8") + b"\x00")
        h.update(json.dumps(
            {"seq": e["seq"], "op": e.get("op_id"),
             "members": list(e["members"]),
             "kind": e.get("kind"),
             "children": list(e.get("children") or [])},
            sort_keys=True).encode())
        h.update(np.asarray(e["descriptor"],
                            dtype=np.float64).tobytes() + b"\x00")
    h.update(b"R\x00" + json.dumps(
        {"docs": sorted(retired_docs),
         "aids": sorted(retired_aids)}).encode() + b"\x00")
    h.update(b"S\x00" + json.dumps(
        {"n": live_n, "total": total_tokens,
         "df": {t: df[t] for t in sorted(df)}}).encode())
    return "sha256:" + h.hexdigest()
