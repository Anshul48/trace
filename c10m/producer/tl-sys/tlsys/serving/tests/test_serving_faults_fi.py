"""Lane S fault injection: spec section 4 rows 4,5,6,7,10,22.

FI-4 kill before/after each segment/manifest write stage; FI-5 byte
flip + truncation per file; FI-6 config/analyzer skew; FI-7
mixed-generation stress (triple equality per answer); FI-10 merge
tails under load (kill-mid-merge itself lives in
test_serving_compact.py); FI-22 ENOSPC + long reader.

Run: tl-sys/.venv/bin/python tl-sys/tlsys/serving/tests/test_serving_faults_fi.py
"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from fixture import emb_votes, make_docs, make_store  # noqa: E402
from tlsys.serving import compact as compact_mod  # noqa: E402
from tlsys.serving import faults as faults_mod  # noqa: E402
from tlsys.serving import segments as seg_mod  # noqa: E402
from tlsys.serving.view import ViewPool  # noqa: E402
from tlsys.index import ReferenceNarrowIndex  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def ref_digest_of(ref):
    from tlsys.serving.digest import canonical_digest
    df = {}
    total = 0
    for text in ref.atom_text.values():
        ts = text.lower().split()
        total += len(ts)
        for t in set(ts):
            df[t] = df.get(t, 0) + 1
    return canonical_digest(ref.atoms, ref.holons, ref.atom_text,
                            ref.retired_docs, ref.retired_aids,
                            len(ref.atom_text), total, df)


def small_store(tag, n=8, seed=101):
    docs = [(f"{tag}-{i}", t) for i, (_d, t) in
            enumerate(make_docs(n, seed=seed))]
    tl, tmp, pin = make_store(docs, emb_votes,
                              prefix=f"tlsys-lanes-fi-{tag}-")
    return tl, tmp, pin


def test_fi4_kill_points():
    # Each stage hook trips -> retry succeeds -> digest stable.
    seal_hooks = ["pre_vectors", "post_vectors", "pre_csr",
                  "post_csr", "pre_text", "post_text", "pre_header",
                  "post_header", "pre_rename", "post_rename"]
    man_hooks = ["pre_manifest", "post_manifest"]
    for h in seal_hooks + man_hooks:
        tl, tmp, pin0 = small_store(f"fi4{h}", n=6, seed=102)
        sdir = os.path.join(tmp, "serving")
        pool = ViewPool(tl, pin0[0], pin0[1], serving_dir=sdir,
                        config={"delta_flush_atoms": 1000})
        v = pool.acquire(pin0)
        faults_mod.arm(h)
        try:
            if h in man_hooks:
                pool.checkpoint(v)
            else:
                pool.seal_locked(v)
            raised = False
        except faults_mod.FaultTripped:
            raised = True
        finally:
            faults_mod.disarm(h)
        check(f"fi4-{h}-trips", raised)
        if h in man_hooks:
            pool.checkpoint(v)
        else:
            seg = pool.seal_locked(v)
            check(f"fi4-{h}-retry-seals", seg is not None)
        ref = ReferenceNarrowIndex(tl, pin0)
        check(f"fi4-{h}-digest",
              v.canonical_digest() == ref_digest_of(ref))
        pool.release(v)
        tl.close()


def test_fi5_corruption_and_truncation():
    files = list(seg_mod.Segment._FILES) + ["header.json"]
    for name in files:
        for mode in ("flip", "truncate"):
            tl, tmp, pin = small_store("fi5", n=4, seed=103)
            sdir = os.path.join(tmp, "serving")
            pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                            config={"delta_flush_atoms": 1})
            v = pool.acquire(pin)
            pool.checkpoint(v)
            pool.release(v)
            segdir = os.path.join(sdir, v.segments[0].segid)
            path = os.path.join(segdir, name)
            with open(path, "rb") as f:
                body = f.read()
            if mode == "flip":
                pos = len(body) // 2
                body = (body[:pos]
                        + bytes([(body[pos] + 1) % 256])
                        + body[pos + 1:])
            else:
                body = body[:max(1, len(body) // 2)]
            with open(path, "wb") as f:
                f.write(body)
            pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
            va = pool2.acquire(pin)
            ref = ReferenceNarrowIndex(tl, pin)
            check(f"fi5-{name}-{mode}",
                  va.canonical_digest() == ref_digest_of(ref))
            q = pool2.counters.totals()["quarantines"]
            check(f"fi5-{name}-{mode}-quarantined", q >= 1, f"q={q}")
            pool2.release(va)
            tl.close()


def test_fi6_config_skew():
    # Header config/analyzer skew -> quarantine + rebuild.
    for field, bad in (("config_id", "c2-serving-v9"),
                       ("analyzer_id", "other-tok")):
        tl, tmp, pin = small_store("fi6", n=4, seed=104)
        sdir = os.path.join(tmp, "serving")
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                        config={"delta_flush_atoms": 1})
        v = pool.acquire(pin)
        pool.checkpoint(v)
        pool.release(v)
        segdir = os.path.join(sdir, v.segments[0].segid)
        hpath = os.path.join(segdir, "header.json")
        with open(hpath) as f:
            header = json.load(f)
        header[field] = bad
        with open(hpath, "w") as f:
            json.dump(header, f)
        pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
        va = pool2.acquire(pin)
        ref = ReferenceNarrowIndex(tl, pin)
        check(f"fi6-{field}",
              va.canonical_digest() == ref_digest_of(ref))
        pool2.release(va)
        tl.close()
    # Manifest skew -> fail-closed cold fallback, same digest.
    tl, tmp, pin = small_store("fi6m", n=4, seed=105)
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 1})
    v = pool.acquire(pin)
    pool.checkpoint(v)
    pool.release(v)
    mpath = os.path.join(sdir, "manifest.json")
    with open(mpath) as f:
        man = json.load(f)
    man["config_id"] = "bogus"
    with open(mpath, "w") as f:
        json.dump(man, f)
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    va = pool2.acquire(pin)
    ref = ReferenceNarrowIndex(tl, pin)
    check("fi6-manifest-fallback",
          va.canonical_digest() == ref_digest_of(ref))
    pool2.release(va)
    tl.close()


def test_fi7_mixed_generation_stress():
    tl, tmp, pin1 = small_store("fi7", n=10, seed=106)
    docs2 = [(f"fi7b-{i}", t) for i, (_d, t) in
             enumerate(make_docs(6, seed=107))]
    ingest_docs(tl, docs2, emb_votes)
    pin2 = tl.pin()
    docs3 = [(f"fi7c-{i}", t) for i, (_d, t) in
             enumerate(make_docs(6, seed=108))]
    ingest_docs(tl, docs3, emb_votes)
    pin3 = tl.pin()
    pins = [pin1, pin2, pin3]
    live = {}
    for p in pins:
        r = ReferenceNarrowIndex(tl, p)
        live[p[2]] = (set(r.atoms), dict(r.atom_text))
    pool = ViewPool(tl, pin1[0], pin1[1],
                    config={"delta_flush_atoms": 4})
    stop = threading.Event()
    errors = []

    def hammer(tid):
        try:
            rng_q = ["fi7", "the", "alpha w1x2", "zxqy"]
            for i in range(25):
                p = pins[(tid + i) % 3]
                v = pool.acquire(p)
                try:
                    if v.pin != p or v.triple != p[3]:
                        errors.append(f"pin mismatch: {v.pin} vs {p}")
                        return
                    with pool.guarded():
                        got = v.bm25(rng_q[i % len(rng_q)])
                        full = v.bm25_fullscan(rng_q[i % len(rng_q)])
                    live_aids, texts = live[p[2]]
                    if set(got) - live_aids:
                        errors.append(f"non-live aids at {p[2]}")
                        return
                    if set(got) != set(full):
                        errors.append(f"bm25/fullscan keys at {p[2]}")
                        return
                    terms = set(rng_q[i % len(rng_q)].lower().split())
                    for aid in got:
                        if terms.isdisjoint(
                                set(texts[aid].lower().split())):
                            errors.append(f"unscored-term hit {aid}")
                            return
                finally:
                    pool.release(v)
        except Exception as e:  # noqa: BLE001 (stress capture)
            errors.append(f"{type(e).__name__}: {e}")

    def advancer():
        try:
            v = pool.acquire(pin1)
            for p in (pin2, pin3, pin2, pin3):
                if stop.is_set():
                    break
                old = v
                if p[2] >= v.frontier:
                    v = pool.advance(v, p)
                else:
                    v = pool.acquire(p)
                pool.release(old)
                time.sleep(0.002)
            pool.release(v)
        except Exception as e:  # noqa: BLE001 (stress capture)
            errors.append(f"advancer {type(e).__name__}: {e}")

    def compactor():
        try:
            for _ in range(4):
                if stop.is_set():
                    break
                try:
                    compact_mod.run_compaction(pool, mode="inprocess")
                except Exception as e:  # noqa: BLE001
                    errors.append(f"compact {type(e).__name__}: {e}")
                    break
                time.sleep(0.005)
        except Exception as e:  # noqa: BLE001 (stress capture)
            errors.append(f"compactor {type(e).__name__}: {e}")

    threads = ([threading.Thread(target=hammer, args=(t,))
                for t in range(4)]
               + [threading.Thread(target=advancer),
                  threading.Thread(target=compactor)])
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    stop.set()
    alive = [t for t in threads if t.is_alive()]
    check("fi7-no-hang", not alive, f"{len(alive)} stuck")
    check("fi7-no-errors", not errors, f"{errors[:3]}")
    tl.close()


def test_fi10_merge_tails():
    tl, tmp, pin = small_store("fi10", n=40, seed=109)
    pool = ViewPool(tl, pin[0], pin[1],
                    config={"delta_flush_atoms": 2,
                            "max_live_segments": 2,
                            "merge_fan_in": 2})
    mx = pin[2]
    cuts = [0, mx // 4, mx // 2, 3 * mx // 4, mx]
    v = pool.cold_build(
        pin, ranges=[(cuts[i], cuts[i + 1]) for i in range(4)])
    qs = ["the", "alpha beta", "fi10 sport", "w1x2 w3x4"]
    solo = []
    for _ in range(20):
        t0 = time.time()
        with pool.guarded():
            for q in qs:
                v.bm25(q)
        solo.append((time.time() - t0) * 1000.0)
    loaded = []
    stop = threading.Event()

    def merger():
        while not stop.is_set():
            try:
                compact_mod.run_compaction(pool, mode="inprocess")
            except Exception:  # noqa: BLE001 (tails only)
                break
            time.sleep(0.001)

    mt = threading.Thread(target=merger)
    mt.start()
    try:
        for _ in range(20):
            t0 = time.time()
            with pool.guarded():
                for q in qs:
                    v.bm25(q)
            loaded.append((time.time() - t0) * 1000.0)
    finally:
        stop.set()
        mt.join(timeout=60)
    import statistics
    s50, s99 = sorted(solo)[10], sorted(solo)[-1]
    l50, l99 = sorted(loaded)[10], sorted(loaded)[-1]
    print(f"fi10 tails: solo p50={s50:.2f}ms max={s99:.2f} | "
          f"loaded p50={l50:.2f}ms max={l99:.2f}")
    check("fi10-completes", len(loaded) == 20)
    ref = ReferenceNarrowIndex(tl, pin)
    check("fi10-digest-stable",
          v.canonical_digest() == ref_digest_of(ref))
    pool.release(v)
    tl.close()


def test_fi22_enospc_and_long_reader():
    tl, tmp, pin1 = small_store("fi22", n=8, seed=110)
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin1[0], pin1[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 1000})
    v = pool.acquire(pin1)
    faults_mod.arm("enospc_segment")
    try:
        pool.seal_locked(v)
        raised = False
    except faults_mod.FaultTripped:
        raised = True
    finally:
        faults_mod.disarm("enospc_segment")
    check("fi22-enospc-trips", raised)
    # The log is untouched: still committable + serving from delta.
    docs = [(f"fi22b-{i}", t) for i, (_d, t) in
            enumerate(make_docs(2, seed=111))]
    ingest_docs(tl, docs, emb_votes)
    pin2 = tl.pin()
    v2 = pool.advance(v, pin2)
    ref2 = ReferenceNarrowIndex(tl, pin2)
    check("fi22-log-alive",
          v2.canonical_digest() == ref_digest_of(ref2))
    check("fi22-delta-intact", len(v2.delta.atom_rows) > 0)
    seg = pool.seal_locked(v2)
    check("fi22-retry-seals", seg is not None)
    # Long reader: held views are never evicted (kept over K cap).
    poolK = ViewPool(tl, pin1[0], pin1[1],
                     config={"retained_generations_K": 1})
    held = poolK.acquire(pin1)
    d_held = held.canonical_digest()
    poolK.acquire(pin2)
    st = poolK.stats()
    check("fi22-held-kept", pin1[2] in st["retained"]
          and len(st["retained"]) == 2, f"{st['retained']}")
    check("fi22-held-serves", held.canonical_digest() == d_held)
    poolK.release(held)
    poolK.acquire(pin2)
    st = poolK.stats()
    check("fi22-bounded-after-release", len(st["retained"]) <= 1,
          f"{st['retained']}")
    pool.release(v)
    pool.release(v2)
    tl.close()


def main():
    import traceback
    for fn in (test_fi4_kill_points, test_fi5_corruption_and_truncation,
               test_fi6_config_skew, test_fi7_mixed_generation_stress,
               test_fi10_merge_tails, test_fi22_enospc_and_long_reader):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=6))
    print("scratch: /tmp/tlsys-lanes-fi-*")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
