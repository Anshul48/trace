"""C2 Closure P-3 (§5.7 follow-up): session-vs-store-birth product fix.

Failing-first pin for the C2-10M drain-p0 product bug: on a fresh
store, ingest attaches the shared profile-bound session while the
store is still empty (session binds the pre-birth incarnation
``None:None:...``); after ingest mints the first generation, maint's
unconditional sess.attach raises SidecarConflictError (pre-birth !=
live). The §5.7-mandated flow (one shared session across
ingest→drain→organize on a fresh store) can never run.

Fix contract (tlsys.prodstate): a stored PRE-BIRTH incarnation is
unbound — attach re-binds it to the live born incarnation (receipted);
persist() stamps the born incarnation after a minting call. The
one-session-one-generation guard still refuses every REAL generation
change (born→born', born→pre-birth, cross-store use after a mint).

Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_p3_birth.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "coordination", "c2-work-20261006T1925Z", "lane-G")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.maint import (drain_placement_backlog,  # noqa: E402
                         organize_segments)
from tlsys.prodstate import (ProducerSession,  # noqa: E402
                             SidecarConflictError,
                             incarnation_of)
from profile import default_profile  # noqa: E402  (Lane G, read-only)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def prof_on(pid):
    p = default_profile(profile_id=pid,
                        calibration_manifest_id="seed-host-20261006")
    p["flags"]["organization_catalog_routing"] = True
    return p


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


DOCS = [("b-a", run_of("sport", 12, 0)),
        ("b-b", run_of("sport", 12, 5000)),
        ("b-c", run_of("medic", 12, 9000))]


def fresh_store(prefix="tlsys-p3-"):
    tmp = tempfile.mkdtemp(prefix=prefix)
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="test-c2-p3")
    return tmp, tl


def hier_sig(tl):
    """Hierarchy signature from committed seg metas (D2 compare).

    Occurrence-signature convention (O-series): atom ids bind the
    store's random revision_id, so membership compares by (doc_id,
    span); member ORDER and descriptors compare exactly.
    """
    import json as _j
    birth, epoch, mx, _t = tl.pin()
    rows = tl.read_commits(birth, epoch, mx, kind="ACCEPT_ATOMS",
                           limit=1000000)
    refs = tl.pub_refs([r[0] for r in rows])
    metas = []
    for seq in [r[0] for r in rows]:
        for art_id in refs.get(seq, []):
            arow = tl.artifact_row(art_id)
            if arow is None:
                continue
            try:
                meta = _j.loads(tl.read_artifact(
                    art_id, expect_digest=arow[4]).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(meta, dict):
                metas.append(meta)
    aidmap = {}
    for meta in metas:
        if "atom" in meta and "doc_id" in meta:
            aidmap[meta["atom"]] = (meta["doc_id"],
                                    tuple(meta.get("span", ())))
    sig = {}
    for meta in metas:
        if meta.get("kind") in ("seg-leaf", "seg-parent"):
            sig[meta["holon"]] = (
                tuple(aidmap.get(a, ("?", ())) for a in
                meta.get("members", ())),
                tuple(meta.get("children", ())),
                tuple(round(float(x), 12)
                      for x in meta.get("descriptor", [])))
    return sig


def main():
    # -- B. shared-session empty→born→drain→organize (the C2-10M flow)
    _tmpb, tlb = fresh_store(prefix="tlsys-p3-birth-")
    prof = prof_on("p3-birth")
    sess = ProducerSession(profile=prof)
    rep = ingest_docs(tlb, DOCS, emb8, store_id="p", profile=prof,
                      keyed_state=True, session=sess, place_budget=1)
    birth_live = tlb.pin()[0]
    check("p3-birth-ingest-mints",
          rep["n_atoms"] == 3 and birth_live is not None
          and rep["n_deferred"] == 2, f"{rep}")
    try:
        drep = drain_placement_backlog(tlb, profile=prof,
                                       keyed_state=True, session=sess)
        derr = None
    except SidecarConflictError as e:
        drep, derr = None, e
    check("p3-birth-shared-drain-ok", derr is None,
          f"SidecarConflictError: {derr}" if derr is not None
          else f"drained={drep['drained']}")
    if derr is None:
        check("p3-birth-drain-does-work",
              sorted(drep["drained"]) == ["b-b", "b-c"], f"{drep}")
        try:
            orep = organize_segments(tlb, profile=prof,
                                     keyed_state=True, session=sess)
            oerr = None
        except SidecarConflictError as e:
            orep, oerr = None, e
        check("p3-birth-shared-organize-ok", oerr is None,
              f"SidecarConflictError: {oerr}" if oerr is not None
              else f"organized={orep['organized']}")
        if oerr is None:
            check("p3-birth-organize-all",
                  sorted(orep["organized"]) == ["b-a", "b-b", "b-c"],
                  f"{orep}")
    else:
        check("p3-birth-drain-does-work", False,
              "drain raised; organize skipped")
        check("p3-birth-shared-organize-ok", False,
              "drain raised; organize skipped")
        check("p3-birth-organize-all", False,
              "drain raised; organize skipped")
    sig_shared = hier_sig(tlb) if derr is None else None
    tlb.close()

    # -- B2. rebind is receipted + D2 parity vs sessionless reference --
    _tmpd, tld = fresh_store(prefix="tlsys-p3-rebind-")
    sess_d = ProducerSession(profile=prof)
    arec0 = sess_d.attach(tld)
    check("p3-birth-prebirth-binds",
          arec0["attached"] is True
          and arec0["incarnation"].startswith("None:None:"),
          f"{arec0}")
    ingest_docs(tld, DOCS, emb8, store_id="p", profile=prof,
                keyed_state=True, place_budget=1)
    try:
        arec1 = sess_d.attach(tld)
        aerr = None
    except SidecarConflictError as e:
        arec1, aerr = None, e
    check("p3-birth-rebind-receipted",
          aerr is None and arec1.get("rebound_prebirth") is True
          and not arec1["incarnation"].startswith("None:None:"),
          f"SidecarConflictError: {aerr}" if aerr is not None
          else f"{arec1}")
    tld.close()
    # Reference flow without a shared session: identical commits.
    _tmpr, tlr = fresh_store(prefix="tlsys-p3-ref-")
    ingest_docs(tlr, DOCS, emb8, store_id="p", profile=prof,
                keyed_state=True, place_budget=1)
    drain_placement_backlog(tlr, profile=prof, keyed_state=True)
    organize_segments(tlr, profile=prof, keyed_state=True)
    check("p3-birth-d2-parity",
          sig_shared is not None and hier_sig(tlr) == sig_shared,
          "shared-session commits differ from reference")
    tlr.close()

    # -- R. guard pins: REAL generation changes still refuse ---------
    _tmpa, tla = fresh_store(prefix="tlsys-p3-guard-a-")
    ingest_docs(tla, DOCS[:1], emb8, store_id="p", profile=prof,
                keyed_state=True)
    _tmpc, tlc = fresh_store(prefix="tlsys-p3-guard-c-")
    ingest_docs(tlc, DOCS[:1], emb8, store_id="p", profile=prof,
                keyed_state=True)
    _tmpe, tle = fresh_store(prefix="tlsys-p3-guard-e-")
    sess_g = ProducerSession(profile=prof)
    sess_g.attach(tla)
    try:
        sess_g.attach(tlc)
        gerr = None
    except SidecarConflictError as e:
        gerr = e
    check("p3-guard-born-born-refuses",
          gerr is not None
          and "one session serves one store generation" in str(gerr),
          f"no refusal: {sess_g._incarnation}")
    try:
        sess_g.attach(tle)
        eerr = None
    except SidecarConflictError as e:
        eerr = e
    check("p3-guard-born-prebirth-refuses",
          eerr is not None
          and "one session serves one store generation" in str(eerr),
          "born→empty attach did not refuse")
    # A minting call stamps the born incarnation: cross-store use
    # after the mint refuses (no silent leg mixing).
    sess_m = ProducerSession(profile=prof)
    _tmpm, tlm = fresh_store(prefix="tlsys-p3-guard-m-")
    ingest_docs(tlm, DOCS[:1], emb8, store_id="p", profile=prof,
                keyed_state=True, session=sess_m)
    live_m = incarnation_of(tlm.pin())
    check("p3-guard-stamp-binds-born",
          sess_m._incarnation == live_m
          and not live_m.startswith("None:None:"),  # same-package read
          f"session={sess_m._incarnation} live={live_m}")
    try:
        sess_m.attach(tlc)
        merr = None
    except SidecarConflictError as e:
        merr = e
    check("p3-guard-minted-cross-store-refuses",
          merr is not None
          and "one session serves one store generation" in str(merr),
          "post-mint cross-store attach did not refuse")
    tla.close()
    tlc.close()
    tle.close()
    tlm.close()

    # -- N. REF profile=None path unchanged ---------------------------
    _tmpn, tln = fresh_store(prefix="tlsys-p3-refnone-")
    sess_n = ProducerSession(profile=None)
    repn = ingest_docs(tln, DOCS, emb8, store_id="p",
                       keyed_state=True)
    check("p3-refnone-ingest-no-attach",
          sess_n._incarnation is None and repn["n_atoms"] == 3,
          f"incarnation={sess_n._incarnation}")
    drepn = drain_placement_backlog(tln, keyed_state=True,
                                    session=sess_n)
    check("p3-refnone-shared-drain-ok",
          drepn["drained"] == [] and sess_n._incarnation
          == incarnation_of(tln.pin()), f"{drepn}")
    orepn = organize_segments(tln, keyed_state=True, session=sess_n)
    check("p3-refnone-shared-organize-ok",
          sorted(orepn["organized"]) == ["b-a", "b-b", "b-c"],
          f"{orepn}")
    tln.close()

    print(f"p3-birth-suite done: {len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
