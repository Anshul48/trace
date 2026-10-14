"""Focused maintained tests: fuse.py (RRF/prune/MMR/variable-K).

Pure-python; runs on any interpreter (no numpy/store). Each test pins
a settled S-04 rule. Run: python3 tl-sys/tests/test_fuse.py
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.fuse import (admit, _cos, mmr_order, mmr_order_matrix,
                        rrf_fuse, static_prune)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


# Q2.2: rank-only RRF, k=60, no normalization machinery -------------
w = rrf_fuse([{"a:x": 0}, {"h:y": 0}])
check("rrf-single-each", abs(w["a:x"] - 1 / 60) < 1e-12
      and abs(w["h:y"] - 1 / 60) < 1e-12, f"{w}")
w = rrf_fuse([{"a:x": 0, "a:z": 5}, {"a:x": 3}])
check("rrf-sum-ranks", abs(w["a:x"] - (1 / 60 + 1 / 63)) < 1e-12,
      f"{w}")
check("rrf-rank-not-score", abs(w["a:z"] - 1 / 65) < 1e-12, f"{w}")

# Q10.2a + amended Q12.1(b): exact-only collapse ----------------------
pr = static_prune([("a", 0.9, "the cat sat"),
                   ("b", 0.8, "the cat sat"),   # exact dup -> collapse
                   ("c", 0.7, "the cat sat!")],  # near-dup -> KEEP
                  10)
ids = [p[0] for p in pr]
check("prune-exact-collapses", ids == ["a", "c"], f"{ids}")
pr = static_prune([(str(i), 1.0 - i / 10, f"text number {i}")
                   for i in range(10)], 4)
check("prune-cap-score-order", [p[0] for p in pr] == ["0", "1", "2", "3"],
      f"{[p[0] for p in pr]}")

# Q10.2a: exact vector MMR diversifies --------------------------------
vecs = {"a": [1.0, 0.0], "b": [0.99, 0.01], "c": [0.0, 1.0]}
ord1 = mmr_order([("a", 1.0), ("b", 0.99), ("c", 0.5)], vecs, 0.5, 3)
check("mmr-diversifies", ord1[0] == "a" and ord1[1] == "c",
      f"{ord1}")
ord2 = mmr_order([("a", 1.0), ("b", 0.99), ("c", 0.5)], vecs, 1.0, 3)
check("mmr-lambda1-score-order", ord2 == ["a", "b", "c"], f"{ord2}")
# matrix path == reference path (optimization equivalence) --------
import random as _r
_rng = _r.Random(7)
vbig = {f"v{i}": [_rng.uniform(-1, 1) for _ in range(24)]
        for i in range(30)}
cbig = [(f"v{i}", _rng.random()) for i in range(30)]
smat = {a: {b: _cos(va, vb) for b, vb in vbig.items()}
        for a, va in vbig.items()}
o_ref = mmr_order(cbig, vbig, 0.5, 30)
o_mat = mmr_order_matrix(cbig, lambda a, b: smat[a][b], 0.5, 30)
check("mmr-matrix-equivalence", o_ref == o_mat,
      f"{o_ref[:6]} vs {o_mat[:6]}")

# Q12.3 final: variable-K admission -----------------------------------
adm, dfn = admit([("a", 0.5), ("b", 0.02), ("c", 0.005)], [], 0.01, 10)
check("admit-tau", adm == ["a", "b"] and dfn == [("c", "below-tau")],
      f"{adm} {dfn}")
adm, dfn = admit([("a", 0.005)], [], 0.01, 10)
check("admit-zero-valid", adm == [] and dfn == [("a", "below-tau")],
      f"{adm} {dfn}")
adm, dfn = admit([("a", 0.5), ("b", 0.4), ("c", 0.3)], [], 0.01, 2)
check("admit-cap-no-backfill", adm == ["a", "b"]
      and dfn == [("c", "cap-reached")], f"{adm} {dfn}")
# counterpart rides below tau, status unmodified
adm, dfn = admit([("a", 0.5), ("b", 0.001)], [("a", "b")], 0.01, 10)
check("admit-counterpart-rides", adm == ["a", "b"] and dfn == [],
      f"{adm} {dfn}")
# binding cap defers BOTH, never one-sided
adm, dfn = admit([("x", 0.9), ("a", 0.5), ("b", 0.4)],
                 [("a", "b")], 0.01, 2)
check("admit-overflow-never-onesided",
      adm == ["x"] and sorted(dfn) == [("a", "pair-overflow-cap"),
                                       ("b", "pair-overflow-cap")],
      f"{adm} {dfn}")

# determinism: all-tied MMR follows cands order, stable across
# hash seeds (regression: set-iteration made 13% of campaign rows
# differ run-to-run, 2026-09-29) ----------------------------------
_tied = [(f"t{i}", 0.05) for i in range(12)]
_tie_sim = lambda a, b: 0.0  # noqa: E731 - uniform zero similarity
_o1 = mmr_order_matrix(_tied, _tie_sim, 0.5, 12)
check("mmr-ties-follow-cands-order",
      _o1 == [f"t{i}" for i in range(12)], f"{_o1}")
import subprocess as _sp
_probe = ("import sys; sys.path.insert(0, %r); "
          "from tlsys.fuse import mmr_order_matrix; "
          "c=[(f't{i}',0.05) for i in range(12)]; "
          "print(mmr_order_matrix(c, lambda a,b: 0.0, 0.5, 12))")
_here = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."))
_outs = set()
for _seed in ("0", "1", "42"):
    _env = dict(os.environ, PYTHONHASHSEED=_seed)
    _p = _sp.run([sys.executable, "-c", _probe % _here],
                 capture_output=True, text=True, env=_env)
    _outs.add((_p.returncode, _p.stdout.strip()))
check("mmr-cross-process-deterministic",
      len(_outs) == 1 and next(iter(_outs))[0] == 0,
      f"{_outs}")

print("RESULT:", "FAIL " + str(FAILS) if FAILS else "PASS")
sys.exit(1 if FAILS else 0)
