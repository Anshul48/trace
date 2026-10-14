"""C2 S-F1: publish over retired history (build tolerance, A29).

Demo finding F1: publish_generation over any store whose history
contains a retirement raised KeyError on the retired doc-holon
ordinal (retired doc-holons keep their ord_holon slots while their
records are gone). Fix: build tolerance — the generation builder
persists live holons only (compacted ordinals, latest-only), with
fail-closed checks on any live reference to a non-live hid.

Smallest maintained pins over scratch stores with deterministic fake
encoders (no weights). Bounds are on WORK (deterministic), never on
wall-clock time. OOM guardrail: fixtures only (<= 14 docs).

Run: HF_HOME=<repo>/local-data/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
  tl-sys/.venv/bin/python tl-sys/tests/test_c2_sf1_retire_publish.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "tlsys",
    "serving", "tests")))

import numpy as np  # noqa: E402

from fixture import emb_votes, make_docs, make_store  # noqa: E402
from tlsys.index import ReferenceNarrowIndex  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.lifecycle import retire_docs  # noqa: E402
from tlsys.maint import organize_segments  # noqa: E402
from tlsys.store_if import TLStore  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def _items_equal(a, b):
    return list(a.items()) == list(b.items())


def _entry_equal(a, b):
    if set(a) != set(b):
        return False
    for k in a:
        if k == "descriptor":
            if not (np.asarray(a[k]) == np.asarray(b[k])).all():
                return False
        elif a[k] != b[k]:
            return False
    return True


def _seg_entries_equal(a, b):
    if set(a) != set(b):
        return False
    return all(_entry_equal(a[k], b[k]) for k in a)


def _ref_dense_atoms(ref):
    ids = list(ref.atoms.keys())
    mat = np.stack([np.asarray(ref.atoms[i]["descriptor"],
                               dtype=np.float64) for i in ids]) \
        if ids else np.empty((0, 0))
    norms = np.linalg.norm(mat, axis=1) if ids else np.empty((0,))
    norms[norms == 0.0] = 1.0
    return ids, mat, norms


def _sf1_store(tag, n_docs=8, seed=11, retire_ix=(1, 4), organize=False,
               flush=4):
    from tlsys.serving.view import ViewPool
    docs = make_docs(n_docs, seed=seed)
    retired = [docs[i][0] for i in retire_ix] if retire_ix else []
    tl, tmp, pin = make_store(
        docs, emb_votes, retire=retired or None, organize=organize,
        prefix=f"tlsys-sf1-{tag}-")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": flush})
    v = pool.cold_build(pin)
    return tl, tmp, pin, sdir, pool, v, docs, retired


def _close(tl):
    try:
        tl.close()
    except Exception:
        pass


def _fresh_gen(tl, pin, sdir, stages=None):
    from tlsys.serving.view import ViewPool
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 4})
    g = pool.acquire(pin, stages=stages if stages is not None else {})
    return pool, g


# -- the F1 pin: publish over retired history ------------------------
def test_sf1_publish_over_retired_history():
    from tlsys.serving import generation as gen_mod
    for tag, organize in (("retire-no-organize", False),
                          ("retire-plus-organize", True)):
        tl, tmp, pin, sdir, pool, v, docs, retired = _sf1_store(
            tag, organize=organize)
        try:
            stale = [h for h in v.ord_holon if h not in v.holons]
            check(f"sf1-{tag}/stale-is-retired-only",
                  sorted(stale) == sorted(retired), stale)
            receipt = pool.publish_generation(v)
            check(f"sf1-{tag}/published",
                  receipt["publish"].get("frontier") == pin[2], receipt)
            d0 = v.canonical_digest()
            pool2, g = _fresh_gen(tl, pin, sdir)
            try:
                check(f"sf1-{tag}/kind",
                      type(g).__name__ == "GenerationView",
                      type(g).__name__)
                check(f"sf1-{tag}/digest",
                      g.canonical_digest() == d0,
                      f"{g.canonical_digest()} vs {d0}")
                check(f"sf1-{tag}/retired-exact",
                      g.retired_docs == sorted(retired),
                      g.retired_docs)
                reader = g._reader
                want_hids = sorted(v.holons, key=lambda h: v.ord_holon[h])
                check(f"sf1-{tag}/holon-count",
                      int(reader.root["holon_count"]) == len(v.holons),
                      (reader.root["holon_count"], len(v.holons)))
                check(f"sf1-{tag}/hids-live-ord",
                      reader.hids.tolist() == want_hids,
                      reader.hids.tolist()[:4])
                for hid in retired:
                    check(f"sf1-{tag}/reader-excludes/{hid}",
                          not reader.has_hid(hid), hid)
                    try:
                        reader.holon_entry(hid)
                        check(f"sf1-{tag}/entry-refuses/{hid}", False,
                              "served a retired holon!")
                    except KeyError:
                        check(f"sf1-{tag}/entry-refuses/{hid}", True)
                ref = ReferenceNarrowIndex(tl, pin)
                for q in ("quasar pulsar", "sport medic"):
                    check(f"sf1-{tag}/bm25/{q}",
                          _items_equal(g.bm25(q), ref.bm25(q)), q)
                n_live = 0
                for aid in ref.atoms:
                    n_live += 1
                    check(f"sf1-{tag}/text-live/{aid}",
                          g.atom_text[aid] == ref.atom_text[aid], aid)
                    if n_live >= 6:
                        break
                check(f"sf1-{tag}/texts-n", n_live > 0, n_live)
                for aid in ref.retired_aids:
                    check(f"sf1-{tag}/text-gone/{aid}",
                          aid not in g.atom_text, aid)
            finally:
                pool2.release(g)
        finally:
            _close(tl)
    # Control: retire-free history publishes (before AND after fix).
    tl, tmp, pin, sdir, pool, v, docs, retired = _sf1_store(
        "control-no-retire", retire_ix=())
    try:
        check("sf1-control/stale-empty",
              [h for h in v.ord_holon if h not in v.holons] == [],
              len(v.ord_holon))
        receipt = pool.publish_generation(v)
        check("sf1-control/published",
              receipt["publish"].get("frontier") == pin[2], receipt)
        pool2, g = _fresh_gen(tl, pin, sdir)
        try:
            check("sf1-control/digest",
                  g.canonical_digest() == v.canonical_digest(), pin[2])
        finally:
            pool2.release(g)
    finally:
        _close(tl)


# -- legs parity battery over retired history (steady-state rules) ----
def test_sf1_legs_parity_retired():
    from tlsys.query import _dense_rank
    tl, tmp, pin, sdir, pool, v, docs, retired = _sf1_store(
        "legs", n_docs=10, seed=23, organize=True)
    try:
        pool.publish_generation(v)
        pool2, g = _fresh_gen(tl, pin, sdir)
        try:
            ref = ReferenceNarrowIndex(tl, pin)
            for q in ("quasar pulsar", "sport medic", "alpha",
                      "nonexistent xyz"):
                check(f"sf1-legs/bm25/{q}",
                      _items_equal(g.bm25(q), ref.bm25(q)), q)
            for attr in ("atoms", "holons", "atom_text", "doc_atoms"):
                gm, rm = getattr(g, attr), getattr(ref, attr)
                check(f"sf1-legs/{attr}-keys",
                      list(gm.keys()) == list(rm.keys()), attr)
                ok = all(_entry_equal(gm[k], rm[k]) for k in rm) \
                    if attr in ("atoms", "holons") else \
                    all(gm[k] == rm[k] for k in rm)
                check(f"sf1-legs/{attr}-entries", ok, attr)
            for term in ("quasar", "sport", "alpha"):
                try:
                    want = ref.postings[term]
                except KeyError:
                    want = None
                try:
                    from tlsys.index import _live_postings_run
                    got = _live_postings_run(g, term)
                except KeyError:
                    got = None
                check(f"sf1-legs/postings/{term}", got == want,
                      (got, want))
            for term in ("quasar", "sport", "alpha", "missing"):
                check(f"sf1-legs/idf/{term}",
                      g.idf_live().get(term) == ref.idf.get(term),
                      term)
            check("sf1-legs/doclen",
                  g.doc_len_live() ==
                  {a: ref.doc_len[a] for a in ref.atoms}, "")
            check("sf1-legs/live-set",
                  g.live_atom_set() == frozenset(ref.atoms), "")
            check("sf1-legs/avgdl", g.avgdl == ref.avgdl,
                  (g.avgdl, ref.avgdl))
            check("sf1-legs/digest",
                  g.canonical_digest() == v.canonical_digest(), "")
            qv = np.arange(8, dtype=np.float64)
            full = g.dense_atoms_full(qv)
            rids, rmat, rnorms = _ref_dense_atoms(ref)
            want_full = _dense_rank(qv, rids, rmat, rnorms)
            check("sf1-legs/dense-full-bitwise", full == want_full,
                  len(full))
            top = g.dense_atoms_topk(qv, 5)
            check("sf1-legs/dense-topk",
                  [a for a, _s in top] ==
                  [a for a, _s in want_full[:5]]
                  and (not top or max(
                      abs(a - b) for (_x, a), (_y, b)
                      in zip(top, want_full[:5])) <= 1e-12),
                  top)
            gal, glp = g.nomination_maps()
            check("sf1-legs/nom-al",
                  dict(gal) == dict(v.atom_leaves), "")
            check("sf1-legs/nom-lp",
                  dict(glp) == dict(v.leaf_parents), "")
            check("sf1-legs/seg-leaves",
                  _seg_entries_equal(g.seg_leaves, v.seg_leaves), "")
            check("sf1-legs/seg-parents",
                  _seg_entries_equal(g.seg_parents, v.seg_parents),
                  "")
            check("sf1-legs/retired",
                  g.retired_docs == sorted(ref.retired_docs)
                  and g.retired_aids_set == set(ref.retired_aids),
                  "")
        finally:
            pool2.release(g)
    finally:
        _close(tl)


# -- no-op when nothing is retired + deterministic builds --------------
def test_sf1_noop_when_nothing_retired():
    from tlsys.serving import generation as gen_mod
    tl, tmp, pin, sdir, pool, v, docs, retired = _sf1_store(
        "noop", retire_ix=(), organize=True)
    try:
        out1 = os.path.join(tmp, "gen-a")
        out2 = os.path.join(tmp, "gen-b")
        root1, _r1 = gen_mod.build_generation_blocks(v, out1)
        root2, _r2 = gen_mod.build_generation_blocks(v, out2)
        check("sf1-noop/holon-count",
              int(root1["holon_count"]) == len(v.ord_holon),
              (root1["holon_count"], len(v.ord_holon)))
        hids = np.load(os.path.join(out1, "hids.npy"),
                       allow_pickle=True).tolist()
        want = sorted(v.ord_holon, key=lambda h: v.ord_holon[h])
        check("sf1-noop/hids-ord-order", hids == want, hids[:4])
        check("sf1-noop/root-deterministic",
              json.dumps(root1, sort_keys=True, default=str) ==
              json.dumps(root2, sort_keys=True, default=str), "")
        check("sf1-noop/blocks-deterministic",
              root1["blocks"] == root2["blocks"], "")
    finally:
        _close(tl)


# -- corruption model: live refs to non-live hids fail closed ----------
def test_sf1_live_edge_fail_closed():
    from tlsys.serving import generation as gen_mod
    from tlsys.serving.view import ViewPool
    docs = make_docs(8, seed=11)
    retired = [docs[1][0]]
    tl, tmp, pin = make_store(docs, emb_votes, retire=retired,
                              organize=True, prefix="tlsys-sf1-fc-")
    try:
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=None,
                        config={"delta_flush_atoms": 1000})
        v0 = pool.cold_build(pin)
        parents = [h for h, e in v0.holons.items()
                   if e.get("kind") == "seg-parent" and e.get("children")]
        check("sf1-fc/has-parent", len(parents) > 0,
              sorted(v0.holons)[:4])
        if not parents:
            return
        parent, victim = parents[0], retired[0]
        al_aid = next(iter(v0.atom_leaves))
        lp_leaf = next(iter(v0.leaf_parents))

        def _expect_refusal(tag, mutate):
            v = pool.cold_build(pin)
            mutate(v)
            try:
                gen_mod.build_generation_blocks(
                    v, os.path.join(tmp, f"gen-{tag}"))
                check(f"sf1-fc/{tag}", False, "built over a bad edge!")
            except gen_mod.GenerationError:
                check(f"sf1-fc/{tag}", True)
            except KeyError as e:
                check(f"sf1-fc/{tag}", False,
                      f"raw KeyError instead of refusal: {e}")

        _expect_refusal("child-to-retired",
                        lambda v: v.holons[parent]["children"].append(
                            victim))
        _expect_refusal("atom-leaves-to-retired",
                        lambda v: v.atom_leaves[al_aid].append(victim))
        _expect_refusal("leaf-parents-to-retired",
                        lambda v: v.leaf_parents[lp_leaf].append(victim))
        _expect_refusal("leaf-parents-key-retired",
                        lambda v: v.leaf_parents.__setitem__(
                            victim, [parent]))
    finally:
        _close(tl)


# -- corruption model: tamper over retired history fails closed ---------
def test_sf1_tamper_holon_blocks():
    from tlsys.serving import generation as gen_mod
    tl, tmp, pin, sdir, pool, v, docs, retired = _sf1_store(
        "tamper", organize=True)
    try:
        pool.publish_generation(v)
        gendir = os.path.join(sdir, "generation")
        root = gen_mod.read_root(gendir)
        for key in ("hids.npy", "holon_vectors.npy", "hmem_vals.npy",
                    "hch_vals.npy", "edge_al_vals.npy",
                    "edge_lp_vals.npy"):
            backup = os.path.join(tmp, "bak-" + key)
            target = os.path.join(gendir, key)
            shutil.copyfile(target, backup)
            with open(target, "r+b") as f:
                f.seek(10)
                b = f.read(1)
                f.seek(10)
                f.write(bytes([b[0] ^ 0x01]))
            try:
                gen_mod.GenerationReader(gendir, root)
                check(f"sf1-tamper/{key}", False, "served bad bytes!")
            except gen_mod.GenerationError:
                check(f"sf1-tamper/{key}", True)
            shutil.copyfile(backup, target)
        # Attach over a tampered holon block: fallback digest-stable.
        target = os.path.join(gendir, "holon_vectors.npy")
        with open(target, "r+b") as f:
            f.seek(100)
            b = f.read(1)
            f.seek(100)
            f.write(bytes([b[0] ^ 0xFF]))
        from tlsys.serving.view import ViewPool
        p3 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                      config={"delta_flush_atoms": 4})
        st = {}
        g3 = p3.acquire(pin, stages=st)
        tot = p3.counters.totals()
        check("sf1-tamper/fallback",
              g3.canonical_digest() == v.canonical_digest()
              and tot["quarantines"] >= 1, (st, tot))
        p3.release(g3)
    finally:
        _close(tl)


# -- steady-state re-publish after retirement (rebase over history) -----
def test_sf1_republish_steady_state():
    from tlsys.serving.view import ViewPool
    docs = make_docs(10, seed=73)
    tl, tmp, pin = make_store(docs, emb_votes,
                              prefix="tlsys-sf1-rs-")
    try:
        sdir = os.path.join(tmp, "serving")
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                        config={"delta_flush_atoms": 4,
                                "gen_overlay_max_atoms": 2})
        v = pool.cold_build(pin)
        pool.publish_generation(v)
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                        config={"delta_flush_atoms": 4,
                                "gen_overlay_max_atoms": 2})
        g = pool.acquire(pin)
        assert type(g).__name__ == "GenerationView", type(g).__name__
        ingest_docs(tl, [(f"d-sf1-{i}", f"quasar ledger {i}")
                         for i in range(3)], emb_votes)
        organize_segments(tl)
        victim = docs[0][0]
        retire_docs(tl, [victim], reason="sf1-republish",
                    approvals={victim: {"type": "user",
                                        "approval_id": "fx-sf1-rs"}})
        pin1 = tl.pin()
        g2 = pool.advance(g, pin1)  # triggers rebase (bound 2)
        rb = getattr(g2, "_last_rebase", None) or {}
        check("sf1-republish/rebase", rb.get("status") == "published",
              rb)
        if rb.get("status") != "published":
            return
        pool3 = ViewPool(tl, pin1[0], pin1[1], serving_dir=sdir,
                         config={"delta_flush_atoms": 4})
        g3 = pool3.acquire(pin1)
        pv = ViewPool(tl, pin1[0], pin1[1], serving_dir=None,
                      config={"delta_flush_atoms": 1000})
        vv = pv.cold_build(pin1)
        check("sf1-republish/fresh-digest",
              g3.canonical_digest() == vv.canonical_digest()
              and type(g3).__name__ == "GenerationView",
              type(g3).__name__)
        check("sf1-republish/retired-excluded",
              victim in g3.retired_docs
              and not g3._reader.has_hid(victim), g3.retired_docs)
        pool.release(g2)
        pool3.release(g3)
    finally:
        _close(tl)


TESTS = (test_sf1_publish_over_retired_history,
         test_sf1_legs_parity_retired,
         test_sf1_noop_when_nothing_retired,
         test_sf1_live_edge_fail_closed,
         test_sf1_tamper_holon_blocks,
         test_sf1_republish_steady_state)


def main():
    import traceback
    for fn in TESTS:
        before = len(FAILS)
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=6))
        if len(FAILS) > before and fn.__name__ not in FAILS:
            FAILS.append(fn.__name__)
    print("scratch: /tmp/tlsys-sf1-*")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())