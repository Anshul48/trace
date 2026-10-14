#!/usr/bin/env python3
"""T6 gate differential: old-vs-new gate identity.

Import baseline approval.py AND new approval.py in one process (importlib,
distinct module names; each tree's `common` stubbed per tree -- approval
imports only Reject from common + stdlib). Matrix: kinds {EDIT,
ACCEPT_ATOMS, ACCEPT_DELTA, RETRACT, SUPERSEDE_ATOMS, FOLD_PHYSICAL,
ORPHAN_COLLECT, DESCRIPTOR_REFRESH, BOGUS_KIND} x payloads {{},
{"retires": ["x"]}} x refs {None, {"stage": 1}, {"stage": 99},
{"nope": 1}, "not-a-dict"} x policy present/absent (fresh store con per
tree via each tree's Store.create on scratch dirs; grants table empty;
policy-absent leg does DELETE FROM policy). For each cell: old gate()
and new gate() (fresh conns, same inputs incl. fixed now=1700000000.0)
must MATCH exactly (ok-string or Reject code+detail). Any divergence
-> FAIL with the cell.
(g) Out-of-contract payload=None (Finding G): table kinds must Reject
cleanly under the new head (fail-safe); EDIT+None must show old/new
parity (shared-classify crash, no new divergence).

If --sut approval.py IS the baseline file (new SUT not present), the
differential is vacuous -> BLOCKED, not a pass.

Usage: python3 test_gate_differential.py --sut <newdir> --store-root <dir>
       [--baseline <dir, default ./tl-candidate-v4/candidate>]
Exit 0 PASS, 1 FAIL, 2 BLOCKED. Stdlib only. Zero harness imports.
"""
import argparse
import copy
import importlib.util
import os
import sys
import time

sys.dont_write_bytecode = True

NOW = 1700000000.0
KINDS = ("EDIT", "ACCEPT_ATOMS", "ACCEPT_DELTA", "RETRACT",
         "SUPERSEDE_ATOMS", "FOLD_PHYSICAL", "ORPHAN_COLLECT",
         "DESCRIPTOR_REFRESH", "BOGUS_KIND")
PAYLOADS = ({}, {"retires": ["x"]})
REFS = (None, {"stage": 1}, {"stage": 99}, {"nope": 1}, "not-a-dict")


def load_tree(tag, treedir):
    """Load (common, approval, store) from one tree under distinct names."""
    def _load(modname, filename):
        path = os.path.join(treedir, filename)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{tag}: missing {filename} in {treedir}")
        spec = importlib.util.spec_from_file_location(modname, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[modname] = mod
        spec.loader.exec_module(mod)
        return mod
    common_mod = _load(f"t6_{tag}_common", "common.py")
    sys.modules["common"] = common_mod  # satisfy `from common import ...`
    try:
        approval_mod = _load(f"t6_{tag}_approval", "approval.py")
        store_mod = _load(f"t6_{tag}_store", "store.py")
    finally:
        sys.modules.pop("common", None)
    return common_mod, approval_mod, store_mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sut", required=True)
    ap.add_argument("--store-root", required=True)
    ap.add_argument("--baseline", default=None)
    args = ap.parse_args()
    new_tree = os.path.abspath(args.sut)
    here = os.path.dirname(os.path.abspath(__file__))
    base_tree = os.path.abspath(args.baseline) if args.baseline else os.path.join(
        here, "..", "..", "tl-candidate-v4", "candidate")

    fails, blocked = [], []

    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {detail}"))
        if not cond:
            fails.append(name)

    def block(name, detail=""):
        print("BLOCKED " + name + ("" if not detail else f" :: {detail}"))
        blocked.append(name)

    for label, tree in (("baseline", base_tree), ("new", new_tree)):
        for m in ("approval.py", "common.py", "store.py"):
            if not os.path.isfile(os.path.join(tree, m)):
                block(f"sut-missing-{label}", f"{tree} lacks {m}")
    if blocked:
        print("RESULT: BLOCKED", blocked)
        return 2
    try:
        if os.path.samefile(os.path.join(base_tree, "approval.py"),
                            os.path.join(new_tree, "approval.py")):
            block("differential-vacuous",
                  f"--sut approval.py is the baseline file ({new_tree}); new SUT not present")
            print("RESULT: BLOCKED", blocked)
            return 2
    except OSError as e:
        block("samefile-check", f"{e}")
        print("RESULT: BLOCKED", blocked)
        return 2

    try:
        old_common, old_approval, old_store_mod = load_tree("old", base_tree)
    except Exception as e:
        block("baseline-import", f"{type(e).__name__}: {e}")
        print("RESULT: BLOCKED", blocked)
        return 2
    try:
        new_common, new_approval, new_store_mod = load_tree("new", new_tree)
    except Exception as e:
        block("new-import", f"{type(e).__name__}: {e}")
        print("RESULT: BLOCKED", blocked)
        return 2

    import random as _r
    root = os.path.join(os.path.abspath(args.store_root),
                        "t6-gatediff-%d-%d-%04x" % (os.getpid(), int(time.time()), _r.randrange(65536)))
    os.makedirs(root, exist_ok=False)

    def run_gate(approval_mod, common_mod, store, kind, payload, ref):
        con = store.open_db()
        try:
            sys.modules["common"] = common_mod  # call-time `from common import sha256`
            try:
                ret = approval_mod.gate(con, kind, copy.deepcopy(payload),
                                        copy.deepcopy(ref), {"leg": "t6"}, NOW)
            finally:
                sys.modules.pop("common", None)
            return ("ok", ret)
        except Exception as e:
            if hasattr(e, "code"):
                return ("reject", getattr(e, "code"), getattr(e, "detail", ""))
            return ("error", type(e).__name__, str(e)[:200])
        finally:
            con.close()

    divergences = []
    ncells = 0
    for leg, wipe_policy in (("present", False), ("absent", True)):
        old_store = old_store_mod.Store.create(os.path.join(root, f"old-{leg}"))
        new_store = new_store_mod.Store.create(os.path.join(root, f"new-{leg}"))
        if wipe_policy:
            for st in (old_store, new_store):
                con = st.open_db()
                try:
                    con.execute("BEGIN IMMEDIATE;")
                    con.execute("DELETE FROM policy;")
                    con.execute("COMMIT;")
                finally:
                    con.close()
        for kind in KINDS:
            for pi, pay in enumerate(PAYLOADS):
                for ri, ref in enumerate(REFS):
                    ncells += 1
                    o = run_gate(old_approval, old_common, old_store, kind, pay, ref)
                    n = run_gate(new_approval, new_common, new_store, kind, pay, ref)
                    if o != n:
                        divergences.append((leg, kind, f"pay{pi}", f"ref{ri}", o, n))
    check("cells-run", ncells == 180, f"ncells={ncells}")
    # sanity: the matrix must actually exercise both ok and reject outcomes
    # (else a single-path stub could pass vacuously)
    probe = run_gate(old_approval, old_common,
                     old_store_mod.Store.create(os.path.join(root, "probe")),
                     "EDIT", {}, None)
    check("matrix-nontrivial", probe[0] == "ok", f"EDIT/{{}}/None -> {probe}")
    probe2 = run_gate(old_approval, old_common,
                      old_store_mod.Store.create(os.path.join(root, "probe2")),
                      "RETRACT", {}, None)
    check("matrix-nontrivial-reject", probe2[0] == "reject", f"RETRACT/{{}}/None -> {probe2}")
    if divergences:
        for d in divergences[:10]:
            print(f"DIVERGE policy={d[0]} kind={d[1]} {d[2]} {d[3]} old={d[4]} new={d[5]}")
        check("gates-identical", False,
              f"{len(divergences)}/{ncells} cells diverge (first shown above)")
    else:
        check("gates-identical", True)
        print(f"INFO: all {ncells} cells match exactly")

    # ---- (g) out-of-contract payload (Finding G; parity measured) ----
    # Non-dict payload is outside gate()'s contract (classify() needs
    # .get). MEASURED: old and new behave identically here (table kinds
    # clean-Reject in both; EDIT+None AttributeErrors in both via shared
    # classify()) -- the alleged old/new divergence does not exist. These
    # cells pin that parity (new-behavior asserts + old INFO record).
    oc_store = new_store_mod.Store.create(os.path.join(root, "oc-new"))
    oc_old_store = old_store_mod.Store.create(os.path.join(root, "oc-old"))
    for kind, want_code in (("FOLD_PHYSICAL", "ENTRY1_MISSING_PA"),
                            ("ORPHAN_COLLECT", "POLICY_NOT_ACTIVE"),
                            ("DESCRIPTOR_REFRESH", "POLICY_NOT_ACTIVE")):
        n = run_gate(new_approval, new_common, oc_store, kind, None, None)
        o = run_gate(old_approval, old_common, oc_old_store, kind, None, None)
        print(f"INFO oc: kind={kind} old={o} new={n}")
        check(f"oc-new-rejects-{kind}", n[0] == "reject" and n[1] == want_code,
              f"new={n}")
    # Non-table kind + non-dict payload crashes in shared classify() in
    # both revs: pin PARITY (not the crash name), i.e. no new divergence.
    o_edit = run_gate(old_approval, old_common, oc_old_store, "EDIT", None, None)
    n_edit = run_gate(new_approval, new_common, oc_store, "EDIT", None, None)
    print(f"INFO oc: EDIT/None old={o_edit} new={n_edit}")
    check("oc-edit-none-parity", (o_edit[0], n_edit[0]) == ("error", "error")
          and o_edit[1] == n_edit[1], f"old={o_edit} new={n_edit}")

    if fails:
        print("RESULT:", f"FAIL {fails}")
        return 1
    if blocked:
        print("RESULT:", f"BLOCKED {blocked}")
        return 2
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
