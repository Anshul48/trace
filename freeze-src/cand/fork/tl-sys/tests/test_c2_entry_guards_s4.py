"""C2 Lane S-4: segmented dense wiring guards + parity + persistence + R8.

Proves the segmented dense scorer executes on the REAL NarrowQuery path
with exact (bitwise) parity to the legacy whole-population _dense_pop,
with explicit serving persistence (seal/checkpoint/attach) and an
explicit profile/counter dependency (R8, no date-specific import):

- Guards (failing-first: FAIL on arrived code, PASS after S-4 wiring):
  backend tags read "denseserve", the legacy mapping enumeration does
  not fire on the wired path, the query cache aliases the served
  assembly, persistence resolves explicit-arg > TL_C2_SERVING_DIR env,
  and product sources carry no date-specific Lane-G import.
- Parity differentials (PASS before and after: on arrived code both
  arms are legacy; after wiring they compare wired vs legacy through
  the same entry points): full narrow runs (floats bitwise via JSON),
  direct legs (ids + scores ==), advance, attach-from-disk, zero
  vectors, duplicates/ties, cross-backend facade-vs-reference.
- New-default pins (complement the retained legacy-scoped M1-D
  assertions, followup S1 disposition): counter units (executed native
  rows per call; physical file bytes unmoved by in-RAM scoring),
  cache/advance behavior (reuse, invalidation, no silent work in
  advance), seal/checkpoint/attach lifecycle, staged-runtime R8 proof
  (fresh process, explicit Lane-G dir, stdlib shadowing check).

Deterministic fake encoder; scratch stores under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_entry_guards_s4.py
"""
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import ReferenceNarrowIndex, NarrowIndex  # noqa: E402
from tlsys.index import _ViewMapping  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys.lifecycle import retire_docs  # noqa: E402
from tlsys.serving import provisional as _prov_mod  # noqa: E402
from tlsys.serving.counters import to_lane_g  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def canon(obj):
    return json.dumps(obj, sort_keys=True, default=str)


def norm_run(obj):
    """Normalize runs for comparison (wall clocks only)."""
    def _walk(o):
        if isinstance(o, dict):
            return {k: (-1.0 if k in ("T_ms", "ms", "wall_ms") else _walk(v))
                    for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_walk(v) for v in o]
        return o
    return _walk(obj)


DIMS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]


def vec(text):
    t = text.lower()
    if "zero-vec" in t:
        return [0.0] * len(DIMS)
    out = [1.0 if w in t else 0.0 for w in DIMS]
    if not any(out):
        return [0.2] * len(DIMS)
    return out


def emb(texts):
    return [vec(t) for t in texts]


def emb1(q):
    return vec(q)


DOCS = [
    ("d0", "alpha norms govern the alpha baseline completely."),
    ("d1", "bravo rules handle the bravo cases entirely."),
    ("d2", "charlie axioms cover the charlie domain fully."),
    ("d3", "delta statutes span the delta regime wholly."),
    ("d4", "echo remarks touch sundry matters lightly."),
    ("d5", "foxtrot clauses bind the foxtrot parties duly."),
    ("d6", "identical tie text here alpha."),
    ("d7", "identical tie text here alpha."),
    ("d8", "ZERO-VEC null descriptor probe."),
]

QUERIES = ["alpha baseline", "bravo rules entirely",
           "identical tie text here alpha", "zzz nothing here",
           "ZERO-VEC null descriptor probe"]


@contextlib.contextmanager
def _env(**kw):
    """Temporarily set (value None = unset) env vars; always restore."""
    saved = {k: os.environ.get(k) for k in kw}
    try:
        for k, v in kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def _patched(obj, name, new):
    old = getattr(obj, name)
    setattr(obj, name, new)
    try:
        yield
    finally:
        setattr(obj, name, old)


def _legs_equal(a, b):
    return ([x[0] for x in a] == [x[0] for x in b]
            and len(a) == len(b)
            and all(x[1] == y[1] for x, y in zip(a, b)))


_S4_ENV_KEYS = ("TL_C2_DENSESERVE", "TL_C2_SERVING_DIR", "TL_C2_LANE_G_DIR")
_SAVED_ENV = {k: os.environ.get(k) for k in _S4_ENV_KEYS}
for _k in _SAVED_ENV:
    os.environ.pop(_k, None)
try:
    root = tempfile.mkdtemp(prefix="tl-s4-")
    tl = TLStore(os.path.join(root, "store"), create=True,
                 lease_owner="test-c2-s4")
    rep = ingest_docs(tl, DOCS, emb)
    check("ingest/atoms", rep["n_atoms"] == 9, rep)
    pin1 = tl.pin()
    ref1 = ReferenceNarrowIndex(tl, pin1)
    fac1 = NarrowIndex(tl, pin1)
    check("harness/facade-is-c2",
          fac1.serve_counters().get("backend") == "c2",
          fac1.serve_counters())
    check("harness/nine-atoms",
          len(fac1.atoms) == 9 and len(ref1.atoms) == 9,
          (len(fac1.atoms), len(ref1.atoms)))
    NATOMS = len(fac1.atoms)
    NHOLONS = len(fac1.holons)
    check("harness/populations", NATOMS == 9 and NHOLONS == 16,
          (NATOMS, NHOLONS))

    # -- guards: the segmented dense backend executes by default --
    for tag, index in (("ref", ref1), ("fac", fac1)):
        nq = NarrowQuery(tl, index, emb1, cfg={})
        with _env(TL_C2_DENSESERVE=None):
            nq.run("alpha baseline")
        want = "denseserve" if tag == "fac" else "densepop"
        check(f"guard/{tag}/backend-tag",
              getattr(nq, "last_dense_backend", None) == want,
              getattr(nq, "last_dense_backend", None))

    # Served legs must not enumerate the facade mappings (the R1
    # whole-population enumeration); they read serving state directly.
    for which, leg in (("atoms", "_dense_atoms_vec"),
                       ("holons", "_dense_holons_vec")):
        nq = NarrowQuery(tl, fac1, emb1, cfg={})
        calls = []
        orig_iter = _ViewMapping.__iter__

        def _spy(self, _o=orig_iter):
            calls.append(1)
            return _o(self)

        with _env(TL_C2_DENSESERVE=None):
            with _patched(_ViewMapping, "__iter__", _spy):
                getattr(nq, leg)(emb1("alpha baseline"), topk=5)
        check(f"guard/fac/no-mapping-enum-{which}", calls == [], calls)

    # The query cache aliases the served per-view assembly (one f64
    # stack per view shared across query objects, not per query).
    try:
        nq = NarrowQuery(tl, fac1, emb1, cfg={})
        with _env(TL_C2_DENSESERVE=None):
            nq._dense_atoms_vec(emb1("alpha"), topk=3)
        view = fac1.serving_view
        asm = view._dense_atoms_assembled()
        cached = nq._dense_cache.get("atoms")
        shared = (cached is not None and cached["mat"] is asm[1]
                  and cached["norms"] is asm[2]
                  and cached["ids"] == asm[0])
        detail = ("no cache entry" if cached is None
                  else "fresh stack, not the served assembly")
    except (AttributeError, KeyError) as e:
        shared, detail = False, f"{type(e).__name__}: {e}"
    check("guard/fac/cache-aliases-served-assembly", shared, detail)

    # -- guards: explicit opt-outs route to the legacy pop --------
    for tag, index in (("ref", ref1), ("fac", fac1)):
        try:
            nq = NarrowQuery(tl, index, emb1,
                             cfg={"DENSESERVE_WIRED": False})
            with _env(TL_C2_DENSESERVE=None):
                nq.run("alpha baseline")
            cfg_ok = (getattr(nq, "last_dense_backend", None)
                      == "densepop")
            detail = getattr(nq, "last_dense_backend", None)
        except ValueError as e:
            cfg_ok, detail = False, str(e)
        check(f"guard/{tag}/cfg-denseserve-off", cfg_ok, detail)
        nq = NarrowQuery(tl, index, emb1, cfg={})
        with _env(TL_C2_DENSESERVE="0"):
            nq.run("alpha baseline")
        check(f"guard/{tag}/env-denseserve-off",
              getattr(nq, "last_dense_backend", None) == "densepop",
              getattr(nq, "last_dense_backend", None))

    # -- guards: explicit serving persistence resolution ---------
    sdir_exp = os.path.join(root, "serving-explicit")
    sdir_env = os.path.join(root, "serving-env")
    try:
        idx_e = NarrowIndex(tl, pin1, serving_dir=sdir_exp)
        exp_ok = idx_e.serving_dir == sdir_exp
        detail = getattr(idx_e, "serving_dir", None)
    except (AttributeError, TypeError) as e:
        exp_ok, detail = False, f"{type(e).__name__}: {e}"
    check("guard/fac/persist-explicit-arg", exp_ok, detail)
    with _env(TL_C2_SERVING_DIR=sdir_env):
        try:
            idx_v = NarrowIndex(tl, pin1)
            env_ok = idx_v.serving_dir == sdir_env
            detail = getattr(idx_v, "serving_dir", None)
        except (AttributeError, TypeError) as e:
            env_ok, detail = False, f"{type(e).__name__}: {e}"
    check("guard/fac/persist-env", env_ok, detail)
    with _env(TL_C2_SERVING_DIR=sdir_env):
        try:
            idx_b = NarrowIndex(tl, pin1, serving_dir=sdir_exp)
            both_ok = idx_b.serving_dir == sdir_exp
            detail = getattr(idx_b, "serving_dir", None)
        except (AttributeError, TypeError) as e:
            both_ok, detail = False, f"{type(e).__name__}: {e}"
    check("guard/fac/persist-explicit-beats-env", both_ok, detail)

    # -- guards: R8 explicit profile/counter dependency -----------
    tlsys_dir = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "tlsys"))
    dated = []
    for dirpath, dirnames, filenames in os.walk(tlsys_dir):
        dirnames[:] = [d for d in dirnames
                       if d not in ("tests", "__pycache__")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                if "c2-work-20261006T1925Z" in f.read():
                    dated.append(os.path.relpath(
                        os.path.join(dirpath, fn), tlsys_dir))
    check("guard/r8-no-date-literal", dated == [], dated)

    # Staged Lane-G copy: the explicit dir wins, validated, no repo
    # layout needed for the dependency itself.
    lane_g_live = os.path.normpath(os.path.join(
        tlsys_dir, "..", "..", "coordination", "c2-work-20261006T1925Z",
        "lane-G"))
    stage = os.path.join(root, "lane-g-staged")
    os.makedirs(stage)
    for mod in ("profile.py", "counters.py", "profile-counters.md"):
        shutil.copy(os.path.join(lane_g_live, mod),
                    os.path.join(stage, mod))
    with _env(TL_C2_LANE_G_DIR=stage):
        amb = _prov_mod.serving_config(force_refresh=True)
    check("guard/r8-env-dir-wins",
          stage in amb.get("source", ""), amb.get("source"))
    # Explicit Lane-G-shaped profile arg (existing path, pinned).
    profmod = _prov_mod._load_lane_g_module("profile")
    raw = profmod.default_profile("s4-pin")
    cfg = _prov_mod.serving_config(raw)
    check("pin/r8-explicit-profile-arg",
          cfg.get("source") == "explicit-lane-G-arg"
          and cfg.get("merge_fan_in") == 8
          and cfg.get("lane_g_validated") is True, cfg)

    # -- parity differentials: wired vs legacy, same entry -------
    # Env flip: TL_C2_DENSESERVE=0 forces legacy. On arrived code the
    # env is ignored (both arms legacy -> equal); after wiring this
    # is the wired-vs-legacy entry differential.
    def _narrow_pair(index, cfg, q):
        with _env(TL_C2_DENSESERVE=None):
            d1, r1 = NarrowQuery(
                tl, index, emb1, cfg=dict(cfg)).run(q)
        with _env(TL_C2_DENSESERVE="0"):
            d0, r0 = NarrowQuery(
                tl, index, emb1, cfg=dict(cfg)).run(q)
        return d1, r1, d0, r0

    for tag, index in (("ref", ref1), ("fac", fac1)):
        for q in QUERIES:
            d1, r1, d0, r0 = _narrow_pair(index, {}, q)
            check(f"parity/{tag}/narrow-default:{q[:12]}",
                  norm_run((d1, r1)) == norm_run((d0, r0)),
                  "wired narrow run diverges from legacy")
        d1, r1, d0, r0 = _narrow_pair(
            index, {"EMIT_DENSE_ATOMS": False}, "alpha baseline")
        check(f"parity/{tag}/narrow-emit-off",
              norm_run((d1, r1)) == norm_run((d0, r0)),
              "holons-only run diverges from legacy")

    # Direct legs, bitwise ids AND scores (ties/zero/cutoff visible).
    for tag, index in (("ref", ref1), ("fac", fac1)):
        for q in QUERIES:
            qv = emb1(q)
            for topk in (None, 1, 5):
                with _env(TL_C2_DENSESERVE=None):
                    nq1 = NarrowQuery(tl, index, emb1, cfg={})
                    a1 = nq1._dense_atoms_vec(qv, topk=topk)
                    h1 = nq1._dense_holons_vec(qv, topk=topk)
                with _env(TL_C2_DENSESERVE="0"):
                    nq0 = NarrowQuery(tl, index, emb1, cfg={})
                    a0 = nq0._dense_atoms_vec(qv, topk=topk)
                    h0 = nq0._dense_holons_vec(qv, topk=topk)
                check(f"parity/{tag}/legs:{q[:12]}:{topk}",
                      _legs_equal(a1, a0) and _legs_equal(h1, h0),
                      "served leg diverges from legacy pop")

    # Cross-backend: facade default == reference default.
    for q in QUERIES:
        with _env(TL_C2_DENSESERVE=None):
            df, rf = NarrowQuery(tl, fac1, emb1, cfg={}).run(q)
            dr, rr = NarrowQuery(tl, ref1, emb1, cfg={}).run(q)
        check(f"parity/xbackend/narrow:{q[:12]}",
              norm_run((df, rf)) == norm_run((dr, rr)),
              "facade run diverges from reference")

    # Re-poll live bindings (undo the staged-dir cache above).
    with _env(TL_C2_LANE_G_DIR=None):
        _prov_mod.serving_config(force_refresh=True)

    # -- parity across advance (new + retired docs) ---------------
    ingest_docs(tl, [("d9", "alpha alpha brand new alpha doc here."),
                     ("d10", "bravo bravo another fresh bravo doc.")],
                emb)
    rrep = retire_docs(tl, ["d4"], reason="s4-advance",
                       approvals={"d4": {"type": "user",
                                         "approval_id": "fx-s4"}})
    check("retire/report", rrep["retired"] == ["d4"], rrep)
    pin2 = tl.pin()
    fac1.advance_to(pin2)
    ref2 = ReferenceNarrowIndex(tl, pin2)
    check("advance/populations",
          len(fac1.atoms) == 10 and len(ref2.atoms) == 10,
          (len(fac1.atoms), len(ref2.atoms)))
    for tag, index in (("ref", ref2), ("fac", fac1)):
        for q in QUERIES:
            d1, r1, d0, r0 = _narrow_pair(index, {}, q)
            check(f"parity/{tag}/advance:{q[:12]}",
                  norm_run((d1, r1)) == norm_run((d0, r0)),
                  "post-advance wired run diverges from legacy")

    # -- counter units on the new default (executed native rows) --
    pool = fac1._pool
    base = pool.counters.totals()
    with _env(TL_C2_DENSESERVE=None):
        nq = NarrowQuery(tl, fac1, emb1, cfg={})
        nq.run("alpha baseline")
    delta = {k: pool.counters.totals()[k] - base[k] for k in base}
    check("counters/fac/executed-rows",
          delta["dense_rescore_rows"] == len(fac1.atoms)
          and delta["holon_rows_scored"] == len(fac1.holons),
          {k: delta[k] for k in ("dense_rescore_rows",
                                 "holon_rows_scored")})
    check("counters/fac/no-physical-bytes",
          delta["bytes_read"] == 0 and delta["files_touched"] == 0
          and delta["artifacts_read"] == 0,
          {k: delta[k] for k in ("bytes_read", "files_touched",
                                 "artifacts_read")})
    lg, extra, note = to_lane_g(pool.counters, scope="s4-units")
    c = lg.snapshot()["counters"]
    tot = pool.counters.totals()
    check("counters/fac/lane-g-units",
          c["scoring_evals.dense_atoms"]
          == tot["dense_fp32_rows"] + tot["dense_rescore_rows"]
          and c["scoring_evals.dense_holons"]
          == tot["holon_rows_scored"]
          and c["native_work_units"] == tot["dense_fp32_rows"]
          and tot["dense_rescore_rows"] > 0, c)
    check("counters/fac/full-path-native-note",
          tot["dense_fp32_rows"] == 0,
          "exact-full-path executed work rides rescore rows, "
          "not FP32 scan rows")

    # -- cache / advance behavior pins ---------------------------
    nq = NarrowQuery(tl, fac1, emb1, cfg={})
    with _env(TL_C2_DENSESERVE=None):
        nq._dense_atoms_vec(emb1("alpha"), topk=3)
        e0 = nq._dense_cache["atoms"]
        m0 = e0["mat"]
        nq._dense_atoms_vec(emb1("bravo"), topk=3)
        e1 = nq._dense_cache["atoms"]
    check("cache/fac/query-reuse",
          e1 is e0 and e1["mat"] is m0, "served assembly rebuilt")
    # Advance performs no dense work itself (O(Delta) hop; the next
    # served call assembles explicitly and is counted).
    ingest_docs(tl, [("d11", "charlie newcomers arrive duly.")], emb)
    pin3 = tl.pin()
    base = pool.counters.totals()
    fac1.advance_to(pin3)
    delta = {k: pool.counters.totals()[k] - base[k] for k in base}
    check("cache/fac/no-silent-advance-work",
          delta["dense_rescore_rows"] == 0
          and delta["holon_rows_scored"] == 0, delta)
    check("cache/fac/advance-clears-view-assembly",
          "dense_atoms" not in fac1.serving_view._caches
          and "dense_holons" not in fac1.serving_view._caches,
          sorted(fac1.serving_view._caches))
    nq2 = NarrowQuery(tl, fac1, emb1, cfg={})
    with _env(TL_C2_DENSESERVE=None):
        nq2._dense_atoms_vec(emb1("alpha"), topk=3)
    check("cache/fac/advance-rebuilds",
          nq2._dense_cache["atoms"]["triple"] == fac1.triple
          and nq2._dense_cache["atoms"]["n"] == len(fac1.atoms),
          nq2._dense_cache["atoms"]["triple"])
    # Post-advance outputs equal a fresh index at the same pin.
    fac_fresh = NarrowIndex(tl, pin3)
    with _env(TL_C2_DENSESERVE=None):
        da, ra = NarrowQuery(tl, fac1, emb1, cfg={}).run(
            "alpha baseline")
        db, rb = NarrowQuery(tl, fac_fresh, emb1, cfg={}).run(
            "alpha baseline")
    check("cache/fac/advance-eq-fresh",
          norm_run((da, ra)) == norm_run((db, rb)),
          "advanced index diverges from fresh index")

    # -- explicit persistence lifecycle on the real path ---------
    pdir = os.path.join(root, "serving-persist")
    idx_p = NarrowIndex(tl, pin3, serving_dir=pdir)
    with _env(TL_C2_DENSESERVE=None):
        dp, rp = NarrowQuery(tl, idx_p, emb1, cfg={}).run(
            "identical tie text here alpha")
    try:
        seg = idx_p.seal_now()
        payload = idx_p.checkpoint_now()
        ck_ok = (payload is not None
                 and os.path.isfile(os.path.join(pdir, "manifest.json"))
                 and os.path.isfile(
                     os.path.join(pdir, "checkpoint.json")))
        detail = sorted(os.listdir(pdir))
    except (AttributeError, TypeError) as e:
        ck_ok, detail = False, f"{type(e).__name__}: {e}"
        payload = None
    check("persist/fac/seal-checkpoint-files", ck_ok, detail)
    try:
        sc = idx_p.serve_counters()
        sc_ok = (sc.get("backend") == "c2"
                 and sc.get("serving_dir") == pdir
                 and sc.get("checkpoint_present") is True)
        detail = sc
    except (AttributeError, TypeError) as e:
        sc_ok, detail = False, f"{type(e).__name__}: {e}"
    check("persist/fac/serve-counters-shape", sc_ok, detail)
    # Fresh index on the same dir attaches (no cold fallback) and
    # serves bitwise-identical runs (ties make order visible).
    idx_a = NarrowIndex(tl, pin3, serving_dir=pdir)
    with _env(TL_C2_DENSESERVE=None):
        da2, ra2 = NarrowQuery(tl, idx_a, emb1, cfg={}).run(
            "identical tie text here alpha")
    check("parity/fac/attach",
          norm_run((da2, ra2)) == norm_run((dp, rp)),
          "attached index diverges from sealed index")
    try:
        from tlsys.serving.view import ViewPool  # noqa: E402
        pool2 = ViewPool(tl, pin3[0], pin3[1], serving_dir=pdir)
        stages = {}
        v2 = pool2.attach(pin3, stages=stages)
        att_ok = stages.get("cold_fallback") is None
        detail = stages.get("cold_fallback")
        pool2.release(v2)
    except Exception as e:  # noqa: BLE001 (lifecycle probe)
        att_ok, detail = False, f"{type(e).__name__}: {e}"
    check("persist/fac/attach-no-cold-fallback", att_ok, detail)

    # -- R8 staged runtime: fresh process, explicit Lane-G dir ----
    probe = os.path.join(root, "s4_stage_probe.py")
    with open(probe, "w", encoding="utf-8") as f:
        f.write(
            "import importlib.util\n"
            "import os\n"
            "import sys\n"
            "sys.path.insert(0, os.environ[\"S4_TLSYS\"])\n"
            "from tlsys.serving import provisional as prov\n"
            "from tlsys.serving.counters import (\n"
            "    ServeCounters, to_lane_g)\n"
            "stage = os.environ[\"TL_C2_LANE_G_DIR\"]\n"
            "cfg = prov.serving_config(force_refresh=True)\n"
            "assert stage in cfg.get(\"source\", \"\"), cfg\n"
            "print(\"pass stage/source\", cfg[\"source\"])\n"
            "sc = ServeCounters()\n"
            "sc.record(dense_rescore_rows=3)\n"
            "lg, extra, note = to_lane_g(sc, scope=\"s4-stage\")\n"
            "c = lg.snapshot()[\"counters\"]\n"
            "assert c[\"scoring_evals.dense_atoms\"] == 3, c\n"
            "print(\"pass stage/export\")\n"
            "import profile as stdprof\n"
            "assert stage not in (stdprof.__file__ or \"\"), \\\n"
            "    stdprof.__file__\n"
            "assert not any(stage in p or \"lane-g\" in p.lower()\n"
            "               for p in sys.path), sys.path\n"
            "print(\"pass stage/no-shadow\", stdprof.__file__)\n")
    penv = {"PATH": os.environ.get("PATH", ""),
            "TL_C2_LANE_G_DIR": stage,
            "S4_TLSYS": os.path.normpath(os.path.join(
                tlsys_dir, "..")),
            "PYTHONHASHSEED": "0"}
    proc = subprocess.run(
        [sys.executable, probe], cwd=root, env=penv,
        capture_output=True, text=True, timeout=120)
    check("stage/r8-clean-runtime", proc.returncode == 0,
          (proc.stdout + proc.stderr)[-800:])
    # In-process shadowing pin: serving imports never pollute
    # sys.path, and stdlib `profile` stays stdlib.
    import profile as _stdprof  # noqa: E402
    check("pin/r8-no-shadowing",
          not any("lane-G" in p for p in sys.path)
          and "lane" not in (_stdprof.__file__ or "").lower(),
          _stdprof.__file__)
finally:
    for _k, _v in _SAVED_ENV.items():
        if _v is None:
            os.environ.pop(_k, None)
        else:
            os.environ[_k] = _v

print(f"s4-checks done: {len(FAILS)} failures")
try:
    import resource  # noqa: E402
    _rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    print(f"s4-peak-rss-mb: {_rss:.1f}")
except ImportError:
    print("s4-peak-rss-mb: n/a")
if FAILS:
    print("FAILURES:", FAILS)
    sys.exit(1)
print("ALL S4 CHECKS PASS")
sys.exit(0)
