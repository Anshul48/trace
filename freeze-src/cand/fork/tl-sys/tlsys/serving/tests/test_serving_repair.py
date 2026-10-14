"""Lane S repair batch R1-R5: inherited-package coherence fixes.

Failing-first: each repair below failed on the arrived package (see
lane-S/REPORT.md for the arrived-state review). Run:
tl-sys/.venv/bin/python tl-sys/tlsys/serving/tests/test_serving_repair.py
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from fixture import (  # noqa: E402
    emb_votes, fixture_approval, make_docs, make_store)
from tlsys.serving import segments as seg_mod  # noqa: E402
from tlsys.serving import provisional  # noqa: E402
from tlsys.serving.view import ServingView  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.lifecycle import retire_docs  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def test_r1_apply_range_consumes_log():
    # R1: apply_range must consume scan_range output (arrived: raised
    # AssertionError via meta_seq_of on every call).
    docs = make_docs(12, seed=11)
    tl, _tmp, pin = make_store(docs, emb_votes)
    birth, epoch, mx, _t = pin
    rows, metas = seg_mod.scan_range(tl, birth, epoch, 0, mx)
    atom_metas = [m for m in metas if m[3] == "atom"]
    texts = seg_mod.read_atom_texts(
        tl, [(s, o, a, m) for s, o, a, _k, m in atom_metas])
    view = ServingView(birth, epoch)
    view.apply_range(rows, metas, texts)
    view.frontier = mx
    view.pin = pin
    ref = NarrowIndex(tl, pin)
    check("r1-apply-no-raise", True)
    check("r1-live-atoms", set(view.atoms) == set(ref.atoms),
          f"{len(view.atoms)} vs {len(ref.atoms)}")
    check("r1-live-holons", set(view.holons) == set(ref.holons),
          f"{len(view.holons)} vs {len(ref.holons)}")
    check("r1-live-n", view.live_n == len(ref.atom_text),
          f"{view.live_n} vs {len(ref.atom_text)}")
    check("r1-total-tokens",
          view.total_tokens == sum(len(t.split())
                                   for t in ref.atom_text.values()),
          f"{view.total_tokens}")
    check("r1-df", dict(view.df) == _df_of(ref),
          "df mismatch vs reference")
    check("r1-atom-text", dict(view.atom_text) == dict(ref.atom_text),
          "atom_text mismatch vs reference")


def _df_of(ref):
    df = {}
    for text in ref.atom_text.values():
        for t in set(text.lower().split()):
            df[t] = df.get(t, 0) + 1
    return df


def test_r1_retirement_mid_log():
    # Markers apply regardless of position (C1 end-filter equivalence).
    docs = make_docs(10, seed=12)
    tl, _tmp, _p0 = make_store(docs, emb_votes)
    retire_docs(tl, ["sdoc-1", "sdoc-3"], reason="r1",
                approvals={d: fixture_approval(f"r1-{d}")
                           for d in ("sdoc-1", "sdoc-3")})
    pin = tl.pin()
    birth, epoch, mx, _t = pin
    rows, metas = seg_mod.scan_range(tl, birth, epoch, 0, mx)
    atom_metas = [m for m in metas if m[3] == "atom"]
    texts = seg_mod.read_atom_texts(
        tl, [(s, o, a, m) for s, o, a, _k, m in atom_metas])
    view = ServingView(birth, epoch)
    view.apply_range(rows, metas, texts)
    view.frontier = mx
    view.pin = pin
    ref = NarrowIndex(tl, pin)
    check("r1-ret-atoms", set(view.atoms) == set(ref.atoms))
    check("r1-ret-docs", sorted(view.tomb.materialize())
          == sorted(ref.retired_docs),
          f"{sorted(view.tomb.materialize())} vs {ref.retired_docs}")
    check("r1-ret-aids", set(view.retired_aids) == set(ref.retired_aids))
    check("r1-ret-live-n", view.live_n == len(ref.atom_text),
          f"{view.live_n} vs {len(ref.atom_text)}")
    check("r1-ret-df", dict(view.df) == _df_of(ref))


def test_r2_reversion_idempotent():
    # R2: same-aid re-insert with identical content must not double-count
    # live stats (arrived: live_n/total/df incremented twice).
    view = ServingView("b", "e")
    meta = {"atom": "a1", "doc_id": "d1", "span": [0, 5],
            "text_artifact": "t1", "text_digest": "dg1",
            "descriptor": [1.0, 0.0]}
    view._insert_atom(10, "op1", meta, "hello world")
    n1, tot1, df1 = view.live_n, view.total_tokens, dict(view.df)
    dn1 = len(view.delta.atom_rows)
    view._insert_atom(11, "op2", dict(meta), "hello world")
    check("r2-live-n-once", view.live_n == n1 == 1, f"{view.live_n}")
    check("r2-total-once", view.total_tokens == tot1 == 2,
          f"{view.total_tokens}")
    check("r2-df-once", dict(view.df) == df1 == {"hello": 1, "world": 1},
          f"{view.df}")
    check("r2-delta-once", len(view.delta.atom_rows) == dn1 == 1,
          f"{len(view.delta.atom_rows)}")
    # C1 append-always parity for doc_atoms (dupes on re-commit).
    check("r2-doc-atoms-append",
          view.doc_atoms["d1"] == ["a1", "a1"], f"{view.doc_atoms}")
    # Same-id text change still fails closed (identity violation).
    try:
        view._insert_atom(12, "op3", dict(meta), "different text here")
        check("r2-identity-raise", False, "no raise on text change")
    except ValueError:
        check("r2-identity-raise", True)


def test_r3_materialize_last_wins():
    # R3: retained-snapshot materialize keeps LAST content at FIRST
    # position (arrived: kept FIRST content, diverging from live).
    docs = make_docs(8, seed=13)
    tl, _tmp, pin = make_store(docs, emb_votes)
    birth, epoch, mx, _t = pin
    rows, metas = seg_mod.scan_range(tl, birth, epoch, 0, mx)
    atom_metas = [m for m in metas if m[3] == "atom"]
    texts = seg_mod.read_atom_texts(
        tl, [(s, o, a, m) for s, o, a, _k, m in atom_metas])
    view = ServingView(birth, epoch)
    view.apply_range(rows, metas, texts)
    view.frontier = mx
    view.pin = pin
    before = view.canonical_digest()
    order_before = list(view.atoms)
    view.freeze()
    view.materialize()
    check("r3-digest-stable", view.canonical_digest() == before)
    check("r3-order-stable", list(view.atoms) == order_before)
    # Hand-crafted cross-seal re-version: two rows, same aid+ordinal.
    v2 = ServingView("b", "e")
    m1 = {"atom": "ax", "doc_id": "dx", "span": [0, 3],
          "text_artifact": "t", "text_digest": "g",
          "descriptor": [1.0, 0.0]}
    v2._insert_atom(1, "o1", m1, "aa bb")
    v2._atom_overrides[v2.ord_atom["ax"]] = np.array([0.0, 1.0])
    v2.delta.atom_rows.append(dict(v2.delta.atom_rows[0]))
    v2.delta.texts.append("aa bb")
    v2.freeze()
    v2.materialize()
    got = np.asarray(v2.atoms["ax"]["descriptor"], dtype=np.float64)
    check("r3-last-wins", bool(np.all(got == np.array([0.0, 1.0]))),
          f"{got}")
    check("r3-first-position", list(v2.atoms) == ["ax"]
          and v2.ord_atom["ax"] == 0)


def test_r4_provisional_lane_g():
    # R4: provisional must consume the LIVE lane-G dir (arrived: pointed
    # at a nonexistent evidence-tree path, always fell back to seeds).
    provisional._cache = None
    provisional._polls = 0
    bound, note = provisional.find_lane_g_bindings()
    live = os.path.join("coordination", "c2-work-20261006T1925Z", "lane-G")
    check("r4-live-dir", os.path.isdir(provisional._lane_g_dir())
          and provisional._lane_g_dir().endswith(
              os.path.normpath(live)),
          provisional._lane_g_dir())
    cfg = provisional.serving_config(force_refresh=True)
    check("r4-source-recorded", cfg.get("source", "").startswith("lane-G:")
          or "poll_note" in cfg, f"{cfg.get('source')}")
    check("r4-seeds-shape",
          all(k in cfg for k in provisional.SEEDS), f"{sorted(cfg)}")


def test_r5_segment_dim_edges():
    # R5: empty segments keep dim; merges take dim from first non-empty.
    seg = seg_mod.Segment("s0000000000-0000000001", 0, 1, "b", "e",
                          [], [], [], set(), ["op1"], 1,
                          mat32=np.empty((0, 8), np.float32))
    check("r5-empty-dim", seg.dim == 8, f"{seg.dim}")
    other = seg_mod.Segment("s0000000001-0000000002", 1, 2, "b", "e",
                            [], [], [], set(), ["op2"], 1,
                            mat32=np.empty((0, 8), np.float32))
    merged = seg_mod.merge_segments([seg, other])
    check("r5-merge-dim", merged.dim == 8, f"{merged.dim}")
    check("r5-merge-range", (merged.lo, merged.hi) == (0, 2))


def main():
    import traceback
    for fn in (test_r1_apply_range_consumes_log,
               test_r1_retirement_mid_log,
               test_r2_reversion_idempotent,
               test_r3_materialize_last_wins,
               test_r4_provisional_lane_g,
               test_r5_segment_dim_edges):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=3))
    print("scratch: /tmp/tlsys-lanes-* (see fixture)")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
