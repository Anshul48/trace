"""C2 Closure P-2 (Sec 5.7 P residuals): keyed operational reads.

Pins explicit-archive-only manifest export (no mandatory JSON on
ordinary add/correct/retire/maintenance calls), stale-snapshot
identification, the keyed operational read API + recorded candidate
version for Q's trial threading, and projection compaction wired to
bounded lifecycle/debt hooks. All pins are structural/deterministic
(file bytes, markers, receipts, row counts, view equality) -- no
wall-clock assertions.

Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_p2_keyed_ops.py
"""
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.maint import (drain_placement_backlog, organize_segments,  # noqa: E402
                         reconcile_manifest)
from tlsys.lifecycle import retire_docs, read_retirements  # noqa: E402
from tlsys.proj import Projections  # noqa: E402
from tlsys import proj as PROJ  # noqa: E402
from tlsys import prodstate as PS  # noqa: E402
from tlsys.prodstate import (  # noqa: E402 (P-2 keyed-ops seam)
    CANDIDATE_VERSION, KEYED_BACKEND_ID, ARCHIVE_POLICY_EXPLICIT,
    CandidateMissingError, CandidateMismatchError,
    StaleProducerError, SidecarMissingError, SidecarConflictError,
    bind_candidate_store, export_manifest_archive, read_progress,
    read_doc, read_eligibility, read_candidate, manifest_currency,
    require_candidate, read_checkpoint_debt)
from tlsys.proj import (PROJ_COMPACT_DEFAULTS,  # noqa: E402 (P-2 hooks)
                        validate_compact_bounds)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def emb8(texts):
    out = []
    for t in texts:
        w = t.split()[0] if t.split() else ""
        v = [0.0] * 8
        if w.startswith("sport"):
            v[0], v[1] = 1.0, 0.1
        elif w.startswith("medic"):
            v[0], v[1] = 0.1, 1.0
        else:
            v[2] = 1.0
        out.append(v)
    return out


def run_of(word, n, start=0):
    return " ".join(f"{word}{start + i}" for i in range(n))


FROZEN_DOCS = [
    ("p-a", run_of("sport", 12, 0)),
    ("p-b", run_of("sport", 12, 5000)),
    ("p-c", run_of("medic", 12, 9000)),
    ("p-d", run_of("sport", 400, 20000)),
    ("p-e", run_of("other", 12, 30000)),
    ("p-f", run_of("medic", 400, 40000)),
]


def fresh_store(prefix="tlsys-p2-"):
    tmp = tempfile.mkdtemp(prefix=prefix)
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="test-c2-p2")
    return tmp, tl


def man_path(root):
    return os.path.join(root, "ingest_manifest.json")


def read_json(path):
    with open(path) as f:
        return json.load(f)


def file_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def main():
    _tmp = tempfile.mkdtemp(prefix="tlsys-p2-main-")
    # -- A. explicit-archive-only export ---------------------------
    spa = os.path.join(_tmp, "store-a")
    tla = TLStore(spa, create=True, lease_owner="test-c2-p2-a")
    mpa = man_path(tla.store.root)
    repa = ingest_docs(tla, FROZEN_DOCS, emb8, store_id="p",
                       place_budget=2, keyed_state=True)
    check("p2-a-no-manifest-ordinary",
          not os.path.isfile(mpa)
          and repa["keyed"]["archive"]["exported"] is False, f"{repa}")
    marker_a = mpa + ".stale.json"
    check("p2-a-stale-marker",
          os.path.isfile(marker_a)
          and read_json(marker_a).get("stale") is True
          and read_json(marker_a).get("exported_seq") is None
          and read_json(marker_a)["progress_seq"] >= 1, f"{marker_a}")
    repd = drain_placement_backlog(tla, store_id="p", keyed_state=True)
    repo = organize_segments(tla, keyed_state=True)
    repr_ = retire_docs(
        tla, ["p-e"], reason="p2-a",
        approvals={"p-e": {"type": "user",
                           "approval_id": "p2-a-u1"}},
        keyed_state=True)
    check("p2-a-no-export-maintenance",
          not os.path.isfile(mpa)
          and repd["keyed"]["archive"]["exported"] is False
          and repo["keyed"]["archive"]["exported"] is False
          and repr_["keyed"]["archive"]["exported"] is False
          and repr_["retired"] == ["p-e"], f"{repd} {repo} {repr_}")
    cur_a = manifest_currency(tla.store.root)
    check("p2-a-currency-stale",
          cur_a["current"] is False
          and cur_a["manifest_present"] is False
          and cur_a["stale_marker"] is True, f"{cur_a}")
    # Explicit once-per-prefix compatibility snapshot (counted).
    arec = export_manifest_archive(tla, reason="bulk-prefix")
    check("p2-a-archive-receipt",
          arec["exported"] is True
          and arec["exported_seq"] == arec["progress_seq"]
          and arec["reason"] == "bulk-prefix"
          and arec["manifest_bytes"] > 0
          and arec["docs"] == 6
          and not os.path.isfile(marker_a), f"{arec}")
    mana = read_json(mpa)
    check("p2-a-archive-content",
          mana["_sidecar_seq"] == arec["exported_seq"]
          and mana["_scheme"] == "tlsys-v2-revision"
          and "_journal_seq" not in mana
          and mana["_pending_placement"] == []
          and mana["_retired"] == ["p-e"], f"{sorted(mana)}")
    check("p2-a-currency-current",
          manifest_currency(tla.store.root)["current"] is True)
    before = file_bytes(mpa)
    rep_small = ingest_docs(tla, [("p-g", run_of("sport", 12, 0))],
                            emb8, store_id="p", keyed_state=True)
    check("p2-a-small-edit-no-rewrite",
          file_bytes(mpa) == before
          and rep_small["keyed"]["archive"]["exported"] is False
          and manifest_currency(tla.store.root)["current"] is False
          and os.path.isfile(marker_a), "small edit rewrote JSON")
    mark_small = read_json(marker_a)
    check("p2-a-marker-shape",
          mark_small["exported_seq"] == arec["exported_seq"]
          and mark_small["progress_seq"]
          > mark_small["exported_seq"], f"{mark_small}")
    rep_arc = ingest_docs(tla, [("p-h", run_of("medic", 12, 0))],
                          emb8, store_id="p", keyed_state=True,
                          archive_manifest=True)
    check("p2-a-archive-flag",
          file_bytes(mpa) != before
          and rep_arc["keyed"]["archive"]["exported"] is True
          and manifest_currency(tla.store.root)["current"] is True
          and not os.path.isfile(marker_a), f"{rep_arc['keyed']}")
    # archive_manifest without keyed_state fails closed (all five).
    n_closed = 0
    for label, fn in (
            ("ingest", lambda: ingest_docs(
                tla, [("zz", "sport one")], emb8,
                archive_manifest=True)),
            ("drain", lambda: drain_placement_backlog(
                tla, archive_manifest=True)),
            ("organize", lambda: organize_segments(
                tla, archive_manifest=True)),
            ("retire", lambda: retire_docs(
                tla, ["p-a"], approvals={"p-a": {"type": "user",
                                                 "approval_id": "u"}},
                archive_manifest=True)),
            ("reconcile", lambda: reconcile_manifest(
                tla, archive_manifest=True))):
        try:
            fn()
        except ValueError:
            n_closed += 1
    check("p2-a-archive-needs-keyed", n_closed == 5, f"{n_closed}/5")
    tla.close()
    # Sidecar loss with NO manifest: the stale marker alone witnesses
    # the loss (named refusal; only the named rebuild recovers).
    spw = os.path.join(_tmp, "store-wit")
    tlw = TLStore(spw, create=True, lease_owner="test-c2-p2-wit")
    ingest_docs(tlw, [("wm", "sport one two three")], emb8,
                store_id="p", place_xdoc=False, keyed_state=True)
    wit_mark = man_path(tlw.store.root) + ".stale.json"
    os.remove(os.path.join(tlw.store.root, PS.SIDECAR_NAME))
    try:
        ingest_docs(tlw, [("wm", "sport one two three")], emb8,
                    store_id="p", place_xdoc=False, keyed_state=True)
        check("p2-a-marker-witness", False, "lost sidecar trusted")
    except PS.SidecarMissingError:
        check("p2-a-marker-witness",
              os.path.isfile(wit_mark)
              and not os.path.isfile(man_path(tlw.store.root)))
    wrec = reconcile_manifest(tlw, store_id="p", keyed_state=True)
    check("p2-a-witness-rebuild",
          wrec["cold_rebuild"] is True
          and "wm" in wrec["recovered_docs"], f"{wrec}")
    tlw.close()
    # -- B. keyed reads + recorded candidate version --------------
    spb = os.path.join(_tmp, "store-b")
    tlb = TLStore(spb, create=True, lease_owner="test-c2-p2-b")
    check("p2-b-unbound-reads",
          read_candidate(tlb.store.root) is None, "bound too early")
    try:
        require_candidate(tlb.store.root)
        check("p2-b-require-missing", False, "unbound store passed")
    except CandidateMissingError:
        check("p2-b-require-missing", True)
    try:
        read_progress(tlb.store.root)
        check("p2-b-progress-missing", False, "no-sidecar read served")
    except SidecarMissingError:
        check("p2-b-progress-missing", True)
    repb = ingest_docs(tlb, [("q-a", run_of("sport", 12, 0)),
                             ("q-b", run_of("medic", 12, 0))],
                       emb8, store_id="p", place_budget=1,
                       keyed_state=True)
    check("p2-b-keyed-prebind",
          repb["n_atoms"] == 2
          and repb["keyed"]["candidate_version"] is None,
          f"{repb['keyed']}")
    brec = bind_candidate_store(tlb)
    check("p2-b-bind-default",
          brec["existing"] is False
          and brec["binding"]["version"] == CANDIDATE_VERSION
          and brec["binding"]["backend"] == KEYED_BACKEND_ID
          and brec["binding"]["archive_policy"]
          == ARCHIVE_POLICY_EXPLICIT
          and brec["binding"]["profile"]["catalog_routing"] is False
          and brec["binding"]["profile"]["rcat"] is None
          and brec["binding"]["compact"]
          == PROJ_COMPACT_DEFAULTS, f"{brec}")
    check("p2-b-read-candidate",
          read_candidate(tlb.store.root) == brec["binding"])
    brec2 = bind_candidate_store(tlb)
    check("p2-b-rebind-idempotent",
          brec2["existing"] is True
          and brec2["binding"] == brec["binding"], f"{brec2}")
    try:
        bind_candidate_store(
            tlb, profile={"flags": {"organization_catalog_routing": True},  # noqa: E501
                          "derived_limits": {"R_cat": 65536}})
        check("p2-b-rebind-conflict", False, "profile swap bound")
    except SidecarConflictError:
        check("p2-b-rebind-conflict", True)
    try:
        bind_candidate_store(tlb, profile="not-a-dict")
        check("p2-b-bind-bad-profile", False, "bad profile bound")
    except ValueError:
        check("p2-b-bind-bad-profile", True)
    check("p2-b-require-ok",
          require_candidate(tlb.store.root)["version"]
          == CANDIDATE_VERSION)
    try:
        require_candidate(tlb.store.root, version="nope-0")
        check("p2-b-require-version", False, "wrong version passed")
    except CandidateMismatchError:
        check("p2-b-require-version", True)
    spb2 = os.path.join(_tmp, "store-b2")
    tlb2 = TLStore(spb2, create=True, lease_owner="test-c2-p2-b2")
    ingest_docs(tlb2, [("zz", "sport one two")], emb8, store_id="p",
                place_xdoc=False)
    gen_diff = tlb.pin()[:2] != tlb2.pin()[:2]
    try:
        require_candidate(tlb.store.root, pin=tlb2.pin())
        check("p2-b-require-generation", False, "foreign pin passed")
    except CandidateMismatchError:
        check("p2-b-require-generation", gen_diff, "same generation?")
    tlb2.close()
    # Bound store: legacy writers refuse, keyed writers proceed.
    n_bref = 0
    for label, fn in (
            ("ingest", lambda: ingest_docs(
                tlb, [("s2", "fresh bytes here")], emb8, store_id="p",
                place_xdoc=False)),
            ("drain", lambda: drain_placement_backlog(tlb)),
            ("organize", lambda: organize_segments(tlb)),
            ("retire", lambda: retire_docs(
                tlb, ["q-a"], approvals={"q-a": {"type": "user",
                                                "approval_id": "u"}})),
            ("reconcile", lambda: reconcile_manifest(tlb))):
        try:
            fn()
        except StaleProducerError:
            n_bref += 1
    check("p2-b-bound-refuses-legacy", n_bref == 5, f"{n_bref}/5")
    elig_a = read_eligibility(tlb.store.root, "q-b")
    check("p2-b-eligibility-pending",
          elig_a["acknowledged"] is True
          and elig_a["pending"] is True
          and elig_a["organized"] is False
          and elig_a["retired"] is False
          and read_eligibility(tlb.store.root, "q-a")["pending"]
          is False, f"{elig_a}")
    repb2 = drain_placement_backlog(tlb, store_id="p",
                                    keyed_state=True)
    check("p2-b-keyed-proceeds",
          repb2["drained"] == ["q-b"]
          and repb2["keyed"]["candidate_version"]
          == CANDIDATE_VERSION, f"{repb2['keyed']}")
    organize_segments(tlb, keyed_state=True)
    elig_b = read_eligibility(tlb.store.root, "q-a")
    check("p2-b-eligibility-organized",
          elig_b["pending"] is False
          and elig_b["organized"] is True
          and elig_b["retired"] is False, f"{elig_b}")
    retire_docs(tlb, ["q-a"], reason="p2-b",
                approvals={"q-a": {"type": "user",
                                   "approval_id": "p2-b-u1"}},
                keyed_state=True)
    elig_c = read_eligibility(tlb.store.root, "q-a")
    check("p2-b-eligibility-retired",
          elig_c["retired"] is True
          and elig_c["acknowledged"] is True, f"{elig_c}")
    check("p2-b-eligibility-unknown",
          read_eligibility(tlb.store.root, "nope")["acknowledged"]
          is False)
    # Read-only proof: every ro read leaves the sidecar bytes alone.
    scpath = os.path.join(tlb.store.root, PS.SIDECAR_NAME)
    sc_before = file_bytes(scpath)
    prog = read_progress(tlb.store.root)
    _d = read_doc(tlb.store.root, "q-a")
    _e = read_eligibility(tlb.store.root, "q-b")
    _c = read_candidate(tlb.store.root)
    _m = manifest_currency(tlb.store.root)
    _k = read_checkpoint_debt(tlb.store.root)
    check("p2-b-readonly",
          file_bytes(scpath) == sc_before
          and not os.path.isfile(scpath + "-journal")
          and not os.path.isfile(scpath + "-wal"), "ro read mutated")
    check("p2-b-read-doc",
          _d is not None and len(_d["atoms"]) == 1
          and _d["holon"] is not None
          and read_doc(tlb.store.root, "nope") is None, f"{_d}")
    check("p2-b-progress-shape",
          prog["backend"] == KEYED_BACKEND_ID
          and prog["progress_seq"] >= 1
          and prog["counters"]["docs_with_atoms"] == 2
          and prog["pending_count"] == 0
          and prog["unorganized_count"] == 0
          and prog["export"]["current"] is False
          and prog["candidate"]["version"] == CANDIDATE_VERSION
          and isinstance(prog["frontier"]["seq"], int), f"{prog}")
    tlb.close()
    # -- C. projection compaction on bounded debt hooks ------------
    spc = os.path.join(_tmp, "store-c")
    tlc = TLStore(spc, create=True, lease_owner="test-c2-p2-c")
    debt0 = Projections.journal_debt(tlc)
    check("p2-c-debt-empty",
          debt0["journal_bytes"] == 0
          and debt0["journal_lines"] == 0
          and debt0["snapshot_bytes"] == 0, f"{debt0}")
    ingest_docs(tlc, [("k-a", run_of("sport", 12, 0))], emb8,
                store_id="p", keyed_state=True)
    ingest_docs(tlc, [("k-b", run_of("medic", 12, 0))], emb8,
                store_id="p", keyed_state=True)
    debt1 = Projections.journal_debt(tlc)
    check("p2-c-journal-grows",
          debt1["journal_bytes"] > 0
          and debt1["snapshot_bytes"] > 0, f"{debt1}")
    noop = Projections.maybe_compact(tlc)
    check("p2-c-under-bound-noop",
          noop["checked"] is True
          and noop["compacted"] is False
          and Projections.journal_debt(tlc)["journal_bytes"]
          == debt1["journal_bytes"], f"{noop}")
    pre = Projections.cached(tlc)
    pre.update(tlc)
    retained_pre = pre.retained()
    tiny = {"max_journal_bytes": 1, "max_journal_ratio": 0.0,
            "max_journal_lines": 1}
    did = Projections.maybe_compact(tlc, bounds=tiny,
                                    reason="p2-c-force")
    post = Projections.journal_debt(tlc)
    check("p2-c-compact-engages",
          did["compacted"] is True
          and did["work"]["journal_bytes_retired"]
          == debt1["journal_bytes"]
          and post["journal_bytes"] == 0
          and post["snapshot_bytes"] > 0, f"{did}")
    check("p2-c-compact-exact",
          Projections.cached(tlc).retained() == retained_pre,
          "compaction changed views")
    # Second explicit compact is a clean no-op (idempotent).
    again = Projections.compact_now(tlc, reason="p2-c-rerun")
    check("p2-c-compact-idempotent",
          again["compacted"] is False, f"{again}")
    # Drain hook honors the recorded binding bounds (tiny -> trips).
    bind_candidate_store(tlc, compact_bounds=tiny)
    ingest_docs(tlc, [("k-c", run_of("sport", 12, 9000))], emb8,
                store_id="p", place_budget=0, keyed_state=True)
    rep_hook = drain_placement_backlog(tlc, store_id="p",
                                       keyed_state=True)
    check("p2-c-drain-hook",
          rep_hook["drained"] == ["k-c"]
          and rep_hook["keyed"]["compact"]["compacted"] is True
          and rep_hook["keyed"]["compact"]["bounds"]
          == validate_compact_bounds(tiny)
          and "journal" in rep_hook["retained"], f"{rep_hook['keyed']}")
    # Ingest (foreground small-edit path) never compacts.
    ingest_docs(tlc, [("k-d", run_of("medic", 12, 9000))], emb8,
                store_id="p", place_budget=0, keyed_state=True)
    over_now = Projections.journal_debt(
        tlc, line_cap=tiny["max_journal_lines"] + 1)
    rep_nf = ingest_docs(tlc, [("k-e", run_of("sport", 12, 9500))],
                         emb8, store_id="p", place_budget=0,
                         keyed_state=True)
    check("p2-c-ingest-no-compact",
          "compact" not in rep_nf["keyed"]
          and Projections.journal_debt(tlc)["journal_bytes"]
          >= over_now["journal_bytes"] > 0, "ingest compacted")
    # Organize hook trips on the same bound; restart replays + trips.
    rep_org = organize_segments(tlc, keyed_state=True)
    check("p2-c-organize-hook",
          rep_org["keyed"]["compact"]["compacted"] is True,
          f"{rep_org['keyed']}")
    root_c = tlc.store.root
    pin_c = tlc.pin()[3]
    tlc.close()
    PROJ._WARM.pop(root_c, None)
    tlr = TLStore(root_c, lease_owner="test-c2-p2-restart")
    check("p2-c-restart-pin", tlr.pin()[3] == pin_c, "pin moved")
    rprog = read_progress(root_c)
    check("p2-c-restart-keyed",
          rprog["counters"]["docs_with_atoms"] == 5
          and read_eligibility(root_c, "k-a")["organized"] is True,
          f"{rprog['counters']}")
    debt_r = Projections.journal_debt(tlr)
    rep_rd = drain_placement_backlog(tlr, store_id="p",
                                     keyed_state=True)
    check("p2-c-restart-hook",
          rep_rd["keyed"]["compact"]["checked"] is True
          and (Projections.journal_debt(tlr)["journal_bytes"]
               <= max(tiny["max_journal_bytes"],
                      tiny["max_journal_ratio"]
                      * debt_r["snapshot_bytes"])), f"{debt_r}")
    # Post-compact parity vs the committed-truth oracle.
    retire_docs(tlr, ["k-a"], reason="p2-c",
                approvals={"k-a": {"type": "user",
                                   "approval_id": "p2-c-u1"}},
                keyed_state=True)
    Projections.compact_now(tlr, reason="p2-c-final")
    oracle = read_retirements(tlr, tlr.pin())
    view = Projections.cached(tlr).retained()
    check("p2-c-oracle-parity",
          set(oracle) == {"k-a"}
          and view["retired"] == 1, f"{oracle} {view}")
    # Long-run boundedness: journal stays within the hook limit.
    floor_b = {"max_journal_bytes": 2048, "max_journal_ratio": 0.0,
               "max_journal_lines": 100000}
    spb3 = os.path.join(_tmp, "store-c2")
    tlb3 = TLStore(spb3, create=True, lease_owner="test-c2-p2-c2")
    bind_candidate_store(tlb3, compact_bounds=floor_b)
    lim = validate_compact_bounds(floor_b)["max_journal_bytes"]
    ok_bound, n_checked = True, 0
    for i in range(6):
        ingest_docs(tlb3, [(f"w-{i}", run_of("sport", 12, i))],
                    emb8, store_id="p", place_budget=0,
                    keyed_state=True)
        rd = drain_placement_backlog(tlb3, store_id="p",
                                     keyed_state=True)
        ok_bound = ok_bound and rd["keyed"]["compact"]["checked"]
        n_checked += 1
    end_debt = Projections.journal_debt(tlb3)
    check("p2-c-long-run-bounded",
          ok_bound and n_checked == 6
          and end_debt["journal_bytes"] <= lim, f"{end_debt}")
    tlb3.close()
    tlr.close()
    # Legacy compact() still just rewrites + returns the path.
    spl = os.path.join(_tmp, "store-leg")
    tll = TLStore(spl, create=True, lease_owner="test-c2-p2-leg")
    ingest_docs(tll, [("g-a", run_of("sport", 12, 0))], emb8,
                store_id="p")
    pleg = Projections.cached(tll)
    pleg.update(tll)
    cpath = pleg.compact(tll)
    check("p2-c-legacy-compact-pin",
          cpath == Projections.checkpoint_path(tll)
          and os.path.isfile(cpath), f"{cpath}")
    tll.close()
    # Keyed no-export state == archived manifest == legacy shape.
    spk = os.path.join(_tmp, "store-eq")
    tlk = TLStore(spk, create=True, lease_owner="test-c2-p2-eq")
    ingest_docs(tlk, FROZEN_DOCS, emb8, store_id="p",
                place_budget=2, keyed_state=True)
    drain_placement_backlog(tlk, store_id="p", keyed_state=True)
    organize_segments(tlk, keyed_state=True)
    sigs_before = {d: (len(read_doc(tlk.store.root, d)["atoms"]),
                        read_doc(tlk.store.root, d)["holon"]
                        is not None,
                        len(read_doc(tlk.store.root, d)["xdoc"]))
                   for d, _t in FROZEN_DOCS}
    export_manifest_archive(tlk, reason="p2-eq")
    meq = read_json(man_path(tlk.store.root))
    sigs_after = {d: (len(meq[d]["atoms"]),
                       meq[d]["holon"] is not None,
                       len(meq[d]["xdoc"]))
                  for d, _t in FROZEN_DOCS}
    spl2 = os.path.join(_tmp, "store-eq-leg")
    tll2 = TLStore(spl2, create=True, lease_owner="test-c2-p2-eq-leg")
    ingest_docs(tll2, FROZEN_DOCS, emb8, store_id="p",
                place_budget=2)
    drain_placement_backlog(tll2, store_id="p")
    organize_segments(tll2)
    mleg = read_json(man_path(tll2.store.root))
    sigs_leg = {d: (len(mleg[d]["atoms"]),
                     mleg[d]["holon"] is not None,
                     len(mleg[d]["xdoc"]))
                for d, _t in FROZEN_DOCS}
    check("p2-a-noexport-equals-archive",
          sigs_before == sigs_after, "export changed keyed state")
    check("p2-a-keyed-equals-legacy",
          sigs_before == sigs_leg, "keyed diverged from legacy")
    tlk.close()
    tll2.close()

    print(f"p2-suite done: {len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
