"""Track R6-B: ingest progress/recovery repro + repair checks.

Authority: TL-INGEST-NAVIGATION-ARCHITECTURE-2026-10-05 sections 3
(progress invariants), 6 checkpoint 1 (correct recovery), 7
(consequential risks). Pinned env: HF_HOME=<repo>/local-data/hf-cache
HF_HUB_OFFLINE=1 PYTHONHASHSEED=0 (this file needs no encoder: fake
embeddings only).

Risk tally convention: checks named *-CONFIRMED-DEFECT assert the
defective behavior EXISTS (PASS = reproduced). Checks named
*-repaired assert the corrected behavior (FAIL before the repair,
PASS after). Risks whose repair lies outside the ingest.py grant
(readers/committer in store_if.py, xholon cap semantics in
place.py/maint.py) are reproduced + confirmed here; the concrete
contract proposal lives in
tl-eval/evidence/round6-2026-10-05/trackB/REPRO-REPAIR.md.

Run: tl-sys/.venv/bin/python tl-sys/tests/test_recovery.py
"""
import hashlib
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore, TruncationError  # noqa: E402
from tlsys.ingest import chunk_text, ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.place import MAX_XHOLON_MEMBERS  # noqa: E402
from tlsys.maint import reconcile_manifest  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 8


def _vec(seed):
    return [float((seed >> (4 * d)) & 1) for d in range(DIM)]


def emb(texts):
    return [_vec(abs(hash(t)) % 256) for t in texts]


def emb1(q):
    return _vec(abs(hash(q)) % 256)


def words(n):
    return " ".join(f"w{i}" for i in range(n))


def sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def committed_metas(tl):
    """All committed ACCEPT_ATOMS metas: (atoms, holons).

    atoms: doc_id -> [(chunk_ix, byte_span, text_digest, revision_id,
    n_chunks, aid)]; holons: holon_id -> members.
    """
    birth, epoch, mx, _t = tl.pin()
    rows = tl.read_commits(birth, epoch, mx, kind="ACCEPT_ATOMS",
                           limit=1000000)
    refs = tl.pub_refs([r[0] for r in rows])
    atoms, holons = {}, {}
    for seq in [r[0] for r in rows]:
        for art_id in refs.get(seq, []):
            arow = tl.artifact_row(art_id)
            if arow is None:
                continue
            try:
                meta = json.loads(tl.read_artifact(
                    art_id, expect_digest=arow[4]).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            if "atom" in meta and "doc_id" in meta:
                atoms.setdefault(meta["doc_id"], []).append(
                    (meta.get("chunk_ix"), tuple(meta.get("byte_span", ())),
                     meta.get("text_digest"), meta.get("revision_id"),
                     meta.get("n_chunks"), meta.get("atom")))
            elif "holon" in meta and "members" in meta:
                holons[meta["holon"]] = list(meta.get("members", []))
    return atoms, holons


def load_manifest(tl):
    path = os.path.join(tl.store.root, "ingest_manifest.json")
    with open(path) as f:
        return json.load(f)


class Crasher:
    """commit_batch wrapper: fail the Nth call (before or after commit)."""

    def __init__(self, tl, fail_on=(), after_commit=False):
        self.real = tl.commit_batch
        self.calls = 0
        self.fail_on = set(fail_on)
        self.after_commit = after_commit
        tl.commit_batch = self

    def __call__(self, ops):
        self.calls += 1
        if self.calls in self.fail_on and not self.after_commit:
            raise RuntimeError("SIMCRASH-before-commit")
        out = self.real(ops)
        if self.calls in self.fail_on and self.after_commit:
            raise RuntimeError("SIMCRASH-after-commit")
        return out

    def disarm(self, tl):
        tl.commit_batch = self.real


def main():
    tmp = tempfile.mkdtemp(prefix="tlsys-r6b-")

    # -- sanity: chunk geometry used by the boundary tests ---------------
    t12, t10, t30 = words(1800), words(1500), words(4500)
    check("geom-12-chunks", len(chunk_text(t12)) == 12,
          f"{len(chunk_text(t12))}")
    check("geom-10-chunks", len(chunk_text(t10)) == 10,
          f"{len(chunk_text(t10))}")
    check("geom-30-chunks", len(chunk_text(t30)) == 30,
          f"{len(chunk_text(t30))}")

    # -- RISK A: partial-document manifest-key-then-skip -----------------
    # A1: crash between flushes (12-chunk doc, place off): first flush
    # commits 10 atoms + manifest key; crash before the final flush.
    sp = os.path.join(tmp, "store-a1")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-a1")
    crash = Crasher(tl, fail_on=(2,))
    try:
        ingest_docs(tl, [("docA", t12)], emb, store_id="r6b",
                    place_xdoc=False)
        check("A1-crash-injected", False, "no crash?")
    except RuntimeError as e:
        check("A1-crash-injected", "SIMCRASH" in str(e), f"{e}")
    crash.disarm(tl)
    man_mid = load_manifest(tl)
    check("A1-partial-key-persisted",
          "docA" in man_mid and len(man_mid["docA"]["atoms"]) == 10
          and man_mid["docA"]["holon"] is None, f"{man_mid.get('docA')}")
    rev_mid = man_mid["docA"]["revision_id"]
    rep = ingest_docs(tl, [("docA", t12)], emb, store_id="r6b",
                      place_xdoc=False)
    atoms, holons = committed_metas(tl)
    check("A1-resume-not-skip", rep["skipped"] == []
          and rep["n_atoms"] == 2 and rep["n_holons"] == 1, f"{rep}")
    check("A1-full-coverage", len(atoms.get("docA", [])) == 12
          and "docA" in holons and len(holons["docA"]) == 12,
          f"atoms={len(atoms.get('docA', []))} holons={sorted(holons)}")
    man_end = load_manifest(tl)
    check("A1-same-revision",
          man_end["docA"]["revision_id"] == rev_mid
          and len({m[3] for m in atoms["docA"]}) == 1
          and atoms["docA"][0][3] == rev_mid,
          f"{man_end['docA'].get('revision_id')} vs {rev_mid}")
    check("A1-status-source-complete",
          man_end["docA"].get("status") == "source-complete"
          and man_end["docA"].get("n_chunks_expected") == 12,
          f"{man_end['docA']}")
    tl.close()

    # A2: commit-then-crash on the FIRST flush (10 atoms durable, no
    # manifest trace in legacy): retry must resume the SAME revision,
    # never mint a duplicate revision.
    sp = os.path.join(tmp, "store-a2")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-a2")
    crash = Crasher(tl, fail_on=(1,), after_commit=True)
    try:
        ingest_docs(tl, [("docB", t12)], emb, store_id="r6b",
                    place_xdoc=False)
        check("A2-crash-injected", False, "no crash?")
    except RuntimeError as e:
        check("A2-crash-injected", "SIMCRASH" in str(e), f"{e}")
    crash.disarm(tl)
    rep = ingest_docs(tl, [("docB", t12)], emb, store_id="r6b",
                      place_xdoc=False)
    atoms, holons = committed_metas(tl)
    check("A2-no-duplicate-revision", len(atoms.get("docB", [])) == 12
          and len({m[3] for m in atoms["docB"]}) == 1
          and "docB" in holons, f"atoms={len(atoms.get('docB', []))} "
          f"revs={len({m[3] for m in atoms.get('docB', [])})}")
    check("A2-resume-not-restart", rep["skipped"] == []
          and rep["n_atoms"] == 2, f"{rep}")
    tl.close()

    # A3: changed bytes on a partial doc are refused, never resumed as
    # the same revision and never skipped.
    sp = os.path.join(tmp, "store-a3")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-a3")
    crash = Crasher(tl, fail_on=(2,))
    try:
        ingest_docs(tl, [("docC", t12)], emb, store_id="r6b",
                    place_xdoc=False)
    except RuntimeError:
        pass
    crash.disarm(tl)
    pin_mid = tl.pin()[3]
    try:
        ingest_docs(tl, [("docC", t12 + " altered")], emb,
                    store_id="r6b", place_xdoc=False)
        check("A3-changed-partial-refused", False, "no refusal")
    except RuntimeError as e:
        check("A3-changed-partial-refused", True, f"{e}")
    check("A3-refusal-pin-stable", tl.pin()[3] == pin_mid,
          f"{tl.pin()[3]} != {pin_mid}")
    tl.close()

    # A4: exact 10-chunk boundary (one full flush, holon outstanding).
    sp = os.path.join(tmp, "store-a4")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-a4")
    crash = Crasher(tl, fail_on=(2,))
    try:
        ingest_docs(tl, [("docD", t10)], emb, store_id="r6b",
                    place_xdoc=False)
    except RuntimeError:
        pass
    crash.disarm(tl)
    rep = ingest_docs(tl, [("docD", t10)], emb, store_id="r6b",
                      place_xdoc=False)
    atoms, holons = committed_metas(tl)
    check("A4-boundary-resumes", rep["skipped"] == []
          and len(atoms.get("docD", [])) == 10
          and "docD" in holons, f"{rep}")
    tl.close()

    # -- RISK B: recovered-manifest source-hash bypass -------------------
    # B1: reconcile a sourceless entry, then re-ingest CHANGED bytes:
    # must refuse, never skip.
    sp = os.path.join(tmp, "store-b1")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-b1")
    ingest_docs(tl, [("docE", "alpha one two three")], emb,
                store_id="r6b", place_xdoc=False)
    os.remove(os.path.join(sp, "ingest_manifest.json"))
    rrec = reconcile_manifest(tl, store_id="r6b")
    man_rec = load_manifest(tl)
    check("B1-recovered-sourceless", "docE" in rrec["recovered_docs"]
          and "source_sha256" not in man_rec["docE"],
          f"{rrec} {man_rec.get('docE')}")
    pin_rec = tl.pin()[3]
    try:
        rep_b1 = ingest_docs(tl, [("docE", "COMPLETELY different bytes "
                                        "here entirely")], emb,
                             store_id="r6b", place_xdoc=False)
        check("B1-changed-recovered-refused", False,
              f"skipped={rep_b1['skipped']}")
    except RuntimeError as e:
        check("B1-changed-recovered-refused", True, f"{e}")
    check("B1-refusal-pin-stable", tl.pin()[3] == pin_rec,
          f"{tl.pin()[3]} != {pin_rec}")
    tl.close()

    # B2: same bytes after reconcile still skip (existing contract),
    # and the entry adopts the verified source hash (no longer UNKNOWN).
    sp = os.path.join(tmp, "store-b2")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-b2")
    ingest_docs(tl, [("docF", "alpha one two three")], emb,
                store_id="r6b", place_xdoc=False)
    os.remove(os.path.join(sp, "ingest_manifest.json"))
    reconcile_manifest(tl, store_id="r6b")
    pin_rec = tl.pin()[3]
    rep_b2 = ingest_docs(tl, [("docF", "alpha one two three")], emb,
                         store_id="r6b", place_xdoc=False)
    man_b2 = load_manifest(tl)
    check("B2-same-recovered-skips", rep_b2["skipped"] == ["docF"]
          and tl.pin()[3] == pin_rec, f"{rep_b2}")
    check("B2-hash-adopted",
          man_b2["docF"].get("source_sha256")
          == sha("alpha one two three"), f"{man_b2['docF']}")
    tl.close()

    # B3: recovered PARTIAL (crash-partial + manifest loss): same bytes
    # R8-C REPAIRED (B3 flip): UNKNOWN-origin partials REFUSE
    # same-revision completion (raised RuntimeError, stable pin, no
    # adopted identity); a new revision is required. The R6-B
    # resume-to-full assertions below were replaced by
    # repaired-behavior assertions (same store shape).
    sp = os.path.join(tmp, "store-b3")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-b3")
    crash = Crasher(tl, fail_on=(2,))
    try:
        ingest_docs(tl, [("docG", t12)], emb, store_id="r6b",
                    place_xdoc=False)
    except RuntimeError:
        pass
    crash.disarm(tl)
    os.remove(os.path.join(sp, "ingest_manifest.json"))
    reconcile_manifest(tl, store_id="r6b")
    pin_b3 = tl.pin()[3]
    try:
        rep_b3 = ingest_docs(tl, [("docG", t12)], emb, store_id="r6b",
                             place_xdoc=False)
        check("B3-unknown-partial-refuses", False,
              f"completed same revision: {rep_b3}")
    except RuntimeError as e:
        check("B3-unknown-partial-refuses", True, f"{e}")
    check("B3-pin-stable", tl.pin()[3] == pin_b3,
          "refusal must commit nothing")
    tl.close()

    # -- RISK C: 1M-commit reader limits / SQLite IN limits --------------
    # R7-A REPAIRED (proposal C, store_if.py): chunked pub_refs
    # IN-lists, fail-loud read_commits, unbounded read_commits_all.
    # The R6-B CONFIRMED-DEFECT characterizations below were replaced
    # by repaired-behavior assertions (same store shape).
    sp = os.path.join(tmp, "store-c")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-c")
    ingest_docs(tl, [(f"c{i}", f"doc number {i}") for i in range(3)],
                emb, store_id="r6b", place_xdoc=False)
    birth, epoch, mx, _t = tl.pin()
    con = sqlite3.connect(":memory:")
    var_limit = con.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER)
    con.close()
    small = tl.pub_refs([r[0] for r in tl.read_commits(
        birth, epoch, mx, kind="ACCEPT_ATOMS")])
    big = tl.pub_refs(list(range(1, var_limit + 1001)))
    check("C1-IN-chunked-repaired", big == small,
          f"over-var-limit IN must serve the identical union "
          f"(var_limit={var_limit})")
    try:
        tl.read_commits(birth, epoch, mx, limit=2)
        check("C2-LIMIT-fail-loud-repaired", False,
              "limit=2 over 6 commits silently truncated")
    except TruncationError as e:
        check("C2-LIMIT-fail-loud-repaired", True, f"{e}")
    n_all = len(tl.read_commits_all(birth, epoch, mx))
    exact = tl.read_commits(birth, epoch, mx, limit=n_all)
    check("C2-paginated-full-prefix-repaired",
          n_all == 6 and len(exact) == 6
          and [r[0] for r in exact]
          == [r[0] for r in tl.read_commits_all(
              birth, epoch, mx, page=2)],
          f"n_all={n_all}")
    # Documented 10M scale: 95045 commits (round5 trackC COMPAT-DRAFT);
    # linear projection to 100M ~ 950k IN params per full-prefix read.
    # Chunking serves that param count directly (no var-limit failure).
    proj = tl.pub_refs(list(range(1, 950001)))
    check("C3-100M-projection-repaired", proj == small
          and var_limit < 950000,
          f"var_limit={var_limit}; 950k-param IN serves {len(proj)} "
          "seqs identically")
    tl.close()

    # -- RISK D: atom-list-vs-xholon-cap disagreement --------------------
    # CONFIRMED-DEFECT characterization: whole-doc new-group creation
    # mints groups the join path would refuse (members > cap); repair
    # needs place/maint units agreement -> contract proposal.
    sp = os.path.join(tmp, "store-d")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-d")
    ingest_docs(tl, [("docH", t30)], emb, store_id="r6b")
    _atoms, holons = committed_metas(tl)
    xh_members = holons.get("xdoc-docH", [])
    check("D1-overcap-group-CONFIRMED-DEFECT",
          len(xh_members) == len(chunk_text(t30))
          and len(xh_members) > MAX_XHOLON_MEMBERS,
          f"members={len(xh_members)} cap={MAX_XHOLON_MEMBERS}")
    from tlsys.place import decide  # noqa: E402
    joins = decide([0.0] * DIM,
                   {"xdoc-docH": {"members": xh_members,
                                  "descriptor": [0.0] * DIM}},
                   t_place=-2.0)
    check("D2-join-path-disagrees-CONFIRMED-DEFECT", joins == [],
          "a group the join path can never build exists")
    tl.close()

    # -- JOURNAL: incremental progress journal, flag-gated ---------------
    # J1: default path writes no journal file (additive, off by default).
    sp = os.path.join(tmp, "store-j1")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-j1")
    ingest_docs(tl, [("j1a", "hello world"), ("j1b", t12)], emb,
                store_id="r6b")
    check("J1-journal-off-by-default",
          not os.path.exists(os.path.join(sp, "ingest_progress.jsonl")),
          "default ingest must not write a journal")
    tl.close()

    # J2: journal mode commits the identical evidence stream (modulo
    # fresh ids) and honors the 10-op batch contract.
    docs_j = [("jA", "alpha one"), ("jB", t12), ("jC", "zzz outlier")]
    snaps = {}
    for mode, kw in (("legacy", {}), ("journal", {"progress_journal": True})):
        spm = os.path.join(tmp, f"store-j2-{mode}")
        tlm = TLStore(spm, create=True, lease_owner=f"test-r6b-j2-{mode}")
        sizes = []
        real_cb = tlm.commit_batch

        def counting_cb(ops, _real=real_cb, _sizes=sizes):
            _sizes.append(len(ops))
            return _real(ops)

        tlm.commit_batch = counting_cb
        try:
            repj = ingest_docs(tlm, docs_j, emb, store_id="r6b",
                               place_budget=1, **kw)
        except TypeError as e:
            check(f"J2-{mode}-ingest", False, f"{e}")
            tlm.close()
            continue
        tlm.commit_batch = real_cb
        jatoms, jholons = committed_metas(tlm)
        idx = NarrowIndex(tlm, tlm.pin())
        # Revision-independent evidence shape: per-doc chunk coverage
        # (ix, byte span, text digest) + holon sizes + descriptors.
        shape = {}
        for doc, metas in jatoms.items():
            shape[doc] = sorted((m[0], m[1], m[2]) for m in metas)
        desc = {}
        for aid, a in idx.atoms.items():
            desc[(a["doc_id"], a["span"][0], a["span"][1])] = [
                float(x) for x in a["descriptor"]]
        snaps[mode] = {"shape": shape,
                       "holons": {h: len(m) for h, m in jholons.items()},
                       "desc": desc, "sizes": sizes, "rep": repj,
                       "docs": sorted(idx.doc_atoms),
                       "n_atoms": len(idx.atoms)}
        tlm.close()
    if "legacy" in snaps and "journal" in snaps:
        leg, jou = snaps["legacy"], snaps["journal"]
        check("J2-identical-evidence",
              leg["shape"] == jou["shape"]
              and leg["holons"] == jou["holons"]
              and leg["desc"] == jou["desc"]
              and leg["n_atoms"] == jou["n_atoms"]
              and leg["rep"]["n_atoms"] == jou["rep"]["n_atoms"]
              and leg["rep"]["n_holons"] == jou["rep"]["n_holons"]
              and leg["rep"]["pending_placement"]
              == jou["rep"]["pending_placement"],
              f"{leg['rep']} vs {jou['rep']}")
        check("J2-10op-contract",
              all(s <= 10 for s in leg["sizes"])
              and all(s <= 10 for s in jou["sizes"])
              and leg["sizes"] == jou["sizes"],
              f"{leg['sizes']} vs {jou['sizes']}")
    else:
        check("J2-identical-evidence", False, "journal mode missing")
        check("J2-10op-contract", False, "journal mode missing")

    # J3: journal-mode crash resume (commit-then-crash, first flush).
    sp = os.path.join(tmp, "store-j3")
    tl = TLStore(sp, create=True, lease_owner="test-r6b-j3")
    try:
        crash = Crasher(tl, fail_on=(1,), after_commit=True)
        try:
            ingest_docs(tl, [("docJ", t12)], emb, store_id="r6b",
                        place_xdoc=False, progress_journal=True)
        except RuntimeError as e:
            check("J3-crash-injected", "SIMCRASH" in str(e), f"{e}")
        crash.disarm(tl)
        jpath = os.path.join(sp, "ingest_progress.jsonl")
        check("J3-journal-has-started",
              os.path.isfile(jpath)
              and any(json.loads(line).get("event") == "started"
                      and json.loads(line).get("doc_id") == "docJ"
                      for line in open(jpath) if line.strip()),
              "journal must durably declare the revision pre-commit")
        rep_j3 = ingest_docs(tl, [("docJ", t12)], emb, store_id="r6b",
                             place_xdoc=False, progress_journal=True)
        jatoms, jholons = committed_metas(tl)
        check("J3-journal-resume", rep_j3["skipped"] == []
              and len(jatoms.get("docJ", [])) == 12
              and len({m[3] for m in jatoms["docJ"]}) == 1
              and "docJ" in jholons, f"{rep_j3}")
    except TypeError as e:
        check("J3-crash-injected", False, f"no journal flag: {e}")
        check("J3-journal-has-started", False, f"no journal flag: {e}")
        check("J3-journal-resume", False, f"no journal flag: {e}")
    tl.close()

    # J4: journal mode collapses manifest writes (one end-save).
    import tlsys.ingest as _ingmod  # noqa: E402
    real_save = _ingmod._save_manifest
    counts = {}
    for mode, kw in (("legacy", {}), ("journal", {"progress_journal": True})):
        spm = os.path.join(tmp, f"store-j4-{mode}")
        tlm = TLStore(spm, create=True, lease_owner=f"test-r6b-j4-{mode}")
        counts[mode] = 0

        def counting_save(path, man, _real=real_save, _mode=mode):
            counts[_mode] += 1
            return _real(path, man)

        _ingmod._save_manifest = counting_save
        try:
            ingest_docs(tlm, docs_j, emb, store_id="r6b",
                        place_budget=1, **kw)
        except TypeError as e:
            check(f"J4-{mode}-ingest", False, f"{e}")
        finally:
            _ingmod._save_manifest = real_save
            tlm.close()
    if "journal" in counts and counts.get("journal") is not None:
        try:
            check("J4-manifest-writes-collapse",
                  counts["journal"] == 1
                  and counts["journal"] < counts["legacy"],
                  f"{counts}")
        except KeyError as e:
            check("J4-manifest-writes-collapse", False, f"missing: {e}")

    print("store-root:", tmp)
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
