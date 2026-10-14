"""C2 Closure P (§5.2): keyed producer state + recovery pins.

Pins the indexed TL-owned SQLite sidecar (tlsys.prodstate) behind the
existing single-writer fence, the keyed ingest/drain/organize/retire/
reconcile backends (keyed_state=True), keyed≡legacy differential
semantics on the frozen slice, restart/partial-batch/correction
recovery, stale-writer refusals, and bounded progress I/O with no
mandatory prefix scan. All pins are structural/deterministic (row
counts, trace events, save counts, view equality) — no wall-clock
assertions.

Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_p_sidecar.py
"""
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys import ingest as ING  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.maint import (drain_placement_backlog, organize_segments,  # noqa: E402
                         reconcile_manifest)
from tlsys.lifecycle import retire_docs  # noqa: E402
from tlsys.proj import Projections  # noqa: E402
from tlsys import prodstate as PS  # noqa: E402  (Closure P sidecar)
from tlsys.prodstate import (ProducerState, StaleProducerError,  # noqa: E402
                             SidecarMissingError, SidecarCorruptError,
                             SidecarConflictError)

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


# Frozen slice (§5.2 P exit: keyed/legacy semantics + actual commit
# effects match here). Fixed ids + fixed bytes; multi-chunk docs
# included (400 tokens -> 3 chunks at 200/50 geometry).
FROZEN_DOCS = [
    ("p-a", run_of("sport", 12, 0)),
    ("p-b", run_of("sport", 12, 5000)),
    ("p-c", run_of("medic", 12, 9000)),
    ("p-d", run_of("sport", 400, 20000)),
    ("p-e", run_of("other", 12, 30000)),
    ("p-f", run_of("medic", 400, 40000)),
]
T12 = run_of("w", 12)


def fresh_store(prefix="tlsys-p-"):
    tmp = tempfile.mkdtemp(prefix=prefix)
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="test-c2-p")
    return tmp, tl


def sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def committed_shape(tl):
    """Revision-independent committed evidence shape (J2 convention).

    Per-doc sorted (chunk_ix, byte_span, text_digest) + holon member
    counts + descriptor map keyed by (doc_id, span). Fresh op/revision
    ids never compared.
    """
    birth, epoch, mx, _t = tl.pin()
    rows = tl.read_commits(birth, epoch, mx, kind="ACCEPT_ATOMS",
                           limit=1000000)
    refs = tl.pub_refs([r[0] for r in rows])
    atoms, holons, desc = {}, {}, {}
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
                    (meta.get("chunk_ix"),
                     tuple(meta.get("byte_span", ())),
                     meta.get("text_digest")))
                desc[(meta["doc_id"], meta.get("chunk_ix"))] = [
                    float(x) for x in meta["descriptor"]]
            elif "holon" in meta and "members" in meta:
                holons[meta["holon"]] = list(meta.get("members", []))
    shape = {d: sorted(v) for d, v in atoms.items()}
    hsizes = {h: len(m) for h, m in holons.items()}
    return {"shape": shape, "holons": hsizes, "desc": desc,
            "n_atoms": sum(len(v) for v in atoms.values())}


def committed_revisions(tl, doc_id):
    """Distinct committed revision_ids for one doc's atom metas."""
    birth, epoch, mx, _t = tl.pin()
    rows = tl.read_commits(birth, epoch, mx, kind="ACCEPT_ATOMS",
                           limit=1000000)
    refs = tl.pub_refs([r[0] for r in rows])
    revs = set()
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
            if isinstance(meta, dict) and meta.get("doc_id") == doc_id \
                    and "atom" in meta:
                revs.add(meta.get("revision_id"))
    return revs


def load_manifest(root):
    with open(os.path.join(root, "ingest_manifest.json")) as f:
        return json.load(f)


def main():
    # -- A. sidecar engine -------------------------------------------
    _tmpa, tla = fresh_store(prefix="tlsys-p-eng-")
    sroot = tla.store.root
    check("p-eng-absent-initially", not PS.sidecar_exists(tla.store))
    try:
        ProducerState.open(tla)
        check("p-eng-missing-named", False, "no refusal on absent DB")
    except SidecarMissingError:
        check("p-eng-missing-named", True)
    st, mrec = ProducerState.create_or_migrate(tla, {})
    check("p-eng-create", PS.sidecar_exists(tla.store)
          and mrec.get("migrated_docs") == 0, f"{mrec}")
    check("p-eng-format", st.meta("format") == str(PS.SIDECAR_FORMAT)
          and st.meta("scheme") == "tlsys-v2-revision",
          "format/scheme stamp")
    st.declare_revision("d1", "rev-1", sha("hello"), 5, 1)
    st.close()
    st2 = ProducerState.open(tla)
    d1 = st2.get_doc("d1")
    check("p-eng-declare-durable",
          d1 is not None and d1["revision_id"] == "rev-1"
          and d1["source_sha256"] == sha("hello")
          and d1["revision_len"] == 5
          and d1["n_chunks_expected"] == 1
          and d1["status"] == "started", f"{d1}")
    check("p-eng-unknown-none", st2.get_doc("nope") is None)
    try:
        st2.declare_revision("d1", "rev-2", sha("other"), 5, 1)
        check("p-eng-declare-conflict-refused", False, "mixed revisions")
    except SidecarConflictError:
        check("p-eng-declare-conflict-refused", True)
    st2.record_flush(
        [{"doc": "d1", "kind": "atom", "op_id": "op-a0",
          "seq": 11, "chunk_ix": 0, "aid": "aid0",
          "byte_span": (0, 5), "text_digest": sha("hello"),
          "revision_id": "rev-1", "n_chunks": 1},
         {"doc": "d1", "kind": "holon", "op_id": "op-h",
          "seq": 12}],
        {"d1": "source-complete"})
    d1b = st2.get_doc("d1")
    check("p-eng-flush-atomic",
          d1b["atoms"] == ["op-a0"] and d1b["holon"] == "op-h"
          and d1b["status"] == "source-complete", f"{d1b}")
    c = st2.counters()
    check("p-eng-counts-exact",
          c["docs_declared"] == 1 and c["atoms_committed"] == 1
          and c["holons_committed"] == 1, f"{c}")
    st2.backlog_add("d1")
    st2.backlog_add("d2")
    check("p-eng-backlog-order",
          [d for d, _s in st2.pending_window(10)] == ["d1", "d2"]
          and st2.pending_count() == 2)
    check("p-eng-backlog-limit",
          [d for d, _s in st2.pending_window(1)] == ["d1"])
    st2.backlog_del("d1")
    check("p-eng-backlog-del",
          [d for d, _s in st2.pending_window(10)] == ["d2"]
          and st2.pending_count() == 1)
    man = st2.materialize_manifest()
    check("p-eng-materialize-shape",
          man["_scheme"] == "tlsys-v2-revision"
          and man["d1"]["atoms"] == ["op-a0"]
          and man["d1"]["holon"] == "op-h"
          and man["_pending_placement"] == ["d2"]
          and "_sidecar_seq" in man, f"{sorted(man)}")
    st2.close()
    # Corrupt bytes: named refusal, never invented identity.
    with open(os.path.join(sroot, PS.SIDECAR_NAME), "wb") as f:
        f.write(b"\x00not-a-sqlite-db" * 64)
    try:
        ProducerState.open(tla)
        check("p-eng-corrupt-named", False, "corrupt DB trusted")
    except SidecarCorruptError:
        check("p-eng-corrupt-named", True)
    tla.close()
    # -- B. keyed = legacy differential on the frozen slice --------
    reps, shapes, sizes, mans = {}, {}, {}, {}
    for mode, kw in (("legacy", {}), ("keyed", {"keyed_state": True,
                                                "archive_manifest": True})):
        spm = os.path.join(_tmpa, f"store-dif-{mode}")
        tlm = TLStore(spm, create=True,
                      lease_owner=f"test-c2-p-dif-{mode}")
        sizes[mode] = []
        real_cb = tlm.commit_batch

        def counting_cb(ops, _real=real_cb, _mode=mode):
            sizes[_mode].append(len(ops))
            return _real(ops)

        tlm.commit_batch = counting_cb
        repi = ingest_docs(tlm, FROZEN_DOCS, emb8, store_id="p",
                           place_budget=2, **kw)
        tlm.commit_batch = real_cb
        repd = drain_placement_backlog(tlm, store_id="p", **kw)
        repo = organize_segments(tlm, **kw)
        # Retire one doc on both arms (grant approval shape is
        # validated pre-commit; the core gate decides at commit).
        try:
            repr_ = retire_docs(
                tlm, ["p-e"], reason="p-dif",
                approvals={"p-e": {"type": "user",
                                   "approval_id": "p-dif-u1"}}, **kw)
        except (ValueError, RuntimeError) as e:
            repr_ = {"retire_refused": f"{type(e).__name__}: {e}"}
        reps[mode] = {"ingest": repi, "drain": repd, "organize": repo,
                      "retire": repr_}
        shapes[mode] = committed_shape(tlm)
        mans[mode] = load_manifest(tlm.store.root)
        tlm.close()
    leg, key = reps["legacy"], reps["keyed"]
    check("p-dif-evidence",
          shapes["legacy"] == shapes["keyed"],
          "committed evidence differs")
    check("p-dif-batches", sizes["legacy"] == sizes["keyed"]
          and all(s <= 10 for s in sizes["keyed"]),
          f"{sizes['legacy']} vs {sizes['keyed']}")
    check("p-dif-ingest-rep",
          leg["ingest"]["n_atoms"] == key["ingest"]["n_atoms"]
          and leg["ingest"]["n_holons"] == key["ingest"]["n_holons"]
          and leg["ingest"]["pending_placement"]
          == key["ingest"]["pending_placement"]
          and leg["ingest"]["n_deferred"]
          == key["ingest"]["n_deferred"], f"{leg['ingest']}")
    check("p-dif-drain-rep",
          leg["drain"]["drained"] == key["drain"]["drained"]
          and leg["drain"]["n_commits"] == key["drain"]["n_commits"]
          and len(leg["drain"]["remaining"])
          == key["drain"]["remaining_count"], f"{leg['drain']}")
    check("p-dif-organize-rep",
          leg["organize"]["organized"] == key["organize"]["organized"]
          and leg["organize"]["n_commits"]
          == key["organize"]["n_commits"]
          and len(leg["organize"]["remaining"])
          == key["organize"]["remaining_count"],
          f"{leg['organize']}")
    check("p-dif-retire-rep",
          leg["retire"].get("retired")
          == key["retire"].get("retired")
          and leg["retire"].get("already_retired")
          == key["retire"].get("already_retired")
          and ("retire_refused" in leg["retire"])
          == ("retire_refused" in key["retire"]),
          f"{leg['retire']} vs {key['retire']}")
    # Manifest equivalence modulo fresh ids + mode stamps: same doc
    # set, same per-doc atom/holon/xdoc/seg COUNTS + statuses +
    # coverage, same queue orders, same scheme.
    mleg, mkey = mans["legacy"], mans["keyed"]
    docs_leg = sorted(d for d in mleg if not d.startswith("_"))
    docs_key = sorted(d for d in mkey if not d.startswith("_"))

    def entry_sig(m, d):
        e = m[d]
        return (len(e.get("atoms", [])), bool(e.get("holon")),
                len(e.get("xdoc", [])), len(e.get("seg", [])),
                e.get("source_sha256"), e.get("revision_len"),
                e.get("n_chunks_expected"), e.get("status"))

    check("p-dif-manifest",
          docs_leg == docs_key
          and all(entry_sig(mleg, d) == entry_sig(mkey, d)
                  for d in docs_leg)
          and mleg.get("_pending_placement")
          == mkey.get("_pending_placement")
          and mleg.get("_seg_organized") == mkey.get("_seg_organized")
          and mleg.get("_retired") == mkey.get("_retired")
          and mleg.get("_scheme") == mkey.get("_scheme"),
          "materialized manifest differs from legacy")
    check("p-dif-sidecar-stamp",
          "_sidecar_seq" in mkey and "_journal_seq" not in mkey,
          "keyed manifest stamp")

    # -- C. keyed recovery -----------------------------------------
    # C1: crash AFTER commit -> restart adopts the committed ops (no
    # new revision, no duplicate effects, nothing re-committed).
    # Single-flush doc: adoption completes it -> durable skip.
    spc = os.path.join(_tmpa, "store-c1")
    tlc = TLStore(spc, create=True, lease_owner="test-c2-p-c1")
    crash = Crasher(tlc, fail_on=(1,), after_commit=True)
    try:
        ingest_docs(tlc, [("docJ", run_of("sport", 400, 0))], emb8,
                    store_id="p", place_xdoc=False, keyed_state=True)
        check("p-rec-crash-injected", False, "no crash")
    except RuntimeError as e:
        check("p-rec-crash-injected", "SIMCRASH" in str(e), f"{e}")
    crash.disarm(tlc)
    rep_c1 = ingest_docs(tlc, [("docJ", run_of("sport", 400, 0))], emb8,
                         store_id="p", place_xdoc=False,
                         keyed_state=True)
    atoms_c1 = committed_shape(tlc)["shape"]
    revs_c1 = committed_revisions(tlc, "docJ")
    check("p-rec-crash-after-commit-adopts",
          rep_c1["skipped"] == ["docJ"]
          and rep_c1["n_atoms"] == 0 and rep_c1["n_holons"] == 0
          and len(atoms_c1.get("docJ", [])) == 3
          and len(revs_c1) == 1, f"{rep_c1} revs={revs_c1}")
    # Multi-flush doc: adoption resumes the same revision tail.
    bigj = run_of("sport", 2000, 100000)
    crash1b = Crasher(tlc, fail_on=(1,), after_commit=True)
    try:
        ingest_docs(tlc, [("docJ2", bigj)], emb8,
                    store_id="p", place_xdoc=False, keyed_state=True)
        check("p-rec-crash1b-injected", False, "no crash")
    except RuntimeError as e:
        check("p-rec-crash1b-injected", "SIMCRASH" in str(e), f"{e}")
    crash1b.disarm(tlc)
    rep_c1b = ingest_docs(tlc, [("docJ2", bigj)], emb8,
                          store_id="p", place_xdoc=False,
                          keyed_state=True)
    n_j2 = len(committed_shape(tlc)["shape"].get("docJ2", []))
    revs_j2 = committed_revisions(tlc, "docJ2")
    check("p-rec-crash-after-commit-resumes",
          rep_c1b["resumed"] == ["docJ2"]
          and len(revs_j2) == 1 and n_j2 == 13,
          f"{rep_c1b} revs={revs_j2} n={n_j2}")
    # C2: crash BEFORE commit on flush 2 of a multi-flush doc ->
    # same-revision completion of the missing tail only.
    bigk = run_of("medic", 2000, 0)
    crash2 = Crasher(tlc, fail_on=(2,), after_commit=False)
    try:
        ingest_docs(tlc, [("docK", bigk)], emb8,
                    store_id="p", place_xdoc=False, keyed_state=True)
        check("p-rec-c2-crash-injected", False, "no crash")
    except RuntimeError as e:
        check("p-rec-c2-crash-injected", "SIMCRASH" in str(e), f"{e}")
    crash2.disarm(tlc)
    rep_c2 = ingest_docs(tlc, [("docK", bigk)], emb8,
                         store_id="p", place_xdoc=False,
                         keyed_state=True)
    revs_c2 = committed_revisions(tlc, "docK")
    n_k = len(committed_shape(tlc)["shape"].get("docK", []))
    check("p-rec-before-commit-resumes",
          "docK" in rep_c2.get("resumed", [])
          and len(revs_c2) == 1 and n_k == 13,
          f"{rep_c2} revs={revs_c2} n={n_k}")
    # C3: warm restart (close + reopen under a new fence holder) skips
    # durable docs with zero commit-scan reads.
    tlc.close()
    tlc2 = TLStore(spc, create=False, lease_owner="test-c2-p-c1b")
    rep_c3 = ingest_docs(
        tlc2, [("docJ", run_of("sport", 400, 0)),
               ("docK", bigk)], emb8,
        store_id="p", place_xdoc=False, keyed_state=True)
    scan_ev = [e for e in tlc2.trace.calls
               if e["op"] in ("read_commits", "read_commits_all",
                              "read_commits_iter")]
    check("p-rec-warm-restart-skips",
          sorted(rep_c3["skipped"]) == ["docJ", "docK"], f"{rep_c3}")
    check("p-rec-warm-restart-no-scan", scan_ev == [],
          f"{[(e['op'], e['detail']) for e in scan_ev]}")
    tlc2.close()
    # C4: correction lifecycle on the keyed path (retire + corrected
    # new doc_id + organize joins as ordinary appends).
    spcc = os.path.join(_tmpa, "store-c4")
    tlcc = TLStore(spcc, create=True, lease_owner="test-c2-p-c4")
    ingest_docs(tlcc, [("corr-1", run_of("sport", 12, 0))], emb8,
                store_id="p", keyed_state=True)
    organize_segments(tlcc, keyed_state=True)
    repr_c4 = retire_docs(
        tlcc, ["corr-1"], reason="superseded",
        approvals={"corr-1": {"type": "user",
                              "approval_id": "p-c4-u1"}},
        keyed_state=True)
    ingest_docs(tlcc, [("corr-2", run_of("sport", 12, 0))], emb8,
                store_id="p", keyed_state=True)
    org_c4 = organize_segments(tlcc, keyed_state=True,
                               archive_manifest=True)
    man_c4 = load_manifest(tlcc.store.root)
    check("p-rec-correction",
          repr_c4["retired"] == ["corr-1"]
          and org_c4["organized"] == ["corr-2"]
          and org_c4["retired_skipped"] == []
          and man_c4.get("_retired") == ["corr-1"],
          f"{repr_c4} {org_c4}")
    tlcc.close()
    # C5: sidecar loss after keyed commits -> named refusal; the named
    # rebuild path restores keyed operation without invented identity.
    spc5 = os.path.join(_tmpa, "store-c5")
    tlc5 = TLStore(spc5, create=True, lease_owner="test-c2-p-c5")
    ingest_docs(tlc5, [("docM", "alpha one two three")], emb8,
                store_id="p", place_xdoc=False, keyed_state=True)
    pin_c5 = tlc5.pin()[3]
    os.remove(os.path.join(spc5, PS.SIDECAR_NAME))
    try:
        ingest_docs(tlc5, [("docM", "alpha one two three")], emb8,
                    store_id="p", place_xdoc=False, keyed_state=True)
        check("p-rec-missing-named", False, "missing sidecar trusted")
    except SidecarMissingError:
        check("p-rec-missing-named", True)
    check("p-rec-missing-pin-stable", tlc5.pin()[3] == pin_c5,
          "refusal must commit nothing")
    rrec = reconcile_manifest(tlc5, store_id="p", keyed_state=True)
    check("p-rec-rebuild-named",
          "docM" in rrec.get("recovered_docs", [])
          and rrec.get("cold_rebuild") is True, f"{rrec}")
    rep_c5 = ingest_docs(tlc5, [("docM", "alpha one two three")], emb8,
                         store_id="p", place_xdoc=False,
                         keyed_state=True)
    check("p-rec-rebuild-skips", rep_c5["skipped"] == ["docM"],
          f"{rep_c5}")
    try:
        ingest_docs(tlc5, [("docM", "COMPLETELY different bytes "
                                    "here entirely")], emb8,
                    store_id="p", place_xdoc=False, keyed_state=True)
        check("p-rec-rebuild-changed-refused", False, "changed accepted")
    except RuntimeError:
        check("p-rec-rebuild-changed-refused", True)
    tlc5.close()

    # -- D. stale-writer refusal -----------------------------------
    spd = os.path.join(_tmpa, "store-stale")
    tld = TLStore(spd, create=True, lease_owner="test-c2-p-stale")
    ingest_docs(tld, [("s1", "sport one two")], emb8, store_id="p",
                place_xdoc=False, keyed_state=True,
                archive_manifest=True)
    pin_d = tld.pin()[3]
    n_refused = 0
    for label, fn in (
            ("ingest", lambda: ingest_docs(
                tld, [("s2", "fresh bytes here")], emb8, store_id="p",
                place_xdoc=False)),
            ("journal", lambda: ingest_docs(
                tld, [("s2", "fresh bytes here")], emb8, store_id="p",
                place_xdoc=False, progress_journal=True)),
            ("drain", lambda: drain_placement_backlog(tld)),
            ("organize", lambda: organize_segments(tld)),
            ("retire", lambda: retire_docs(
                tld, ["s1"], approvals={"s1": {"type": "user",
                                               "approval_id": "u"}})),
            ("reconcile", lambda: reconcile_manifest(tld))):
        try:
            fn()
        except StaleProducerError:
            n_refused += 1
        except SidecarMissingError:
            check(f"p-stale-{label}-named", False, "wrong error")
    check("p-stale-writers-refuse", n_refused == 6, f"{n_refused}/6")
    check("p-stale-pin-stable", tld.pin()[3] == pin_d,
          "refusal must commit nothing")
    # Legacy READS still work on a sidecar store (boundary artifact).
    man_d = load_manifest(tld.store.root)
    check("p-stale-legacy-reads",
          man_d.get("s1", {}).get("status") == "source-complete"
          and man_d.get("_scheme") == "tlsys-v2-revision", f"{man_d}")
    tld.close()

    # -- E. legacy -> sidecar migration -------------------------------
    # A legacy store (manifest + crash-window committed ops) adopts the
    # sidecar on its first keyed call: declarations/coverage/queues
    # migrate, committed-but-unrecorded ops adopt, and the materialized
    # manifest matches a pure-legacy run entry-for-entry (modulo the
    # mode stamp).
    spf = os.path.join(_tmpa, "store-mig")
    tlf = TLStore(spf, create=True, lease_owner="test-c2-p-mig")
    crashf = Crasher(tlf, fail_on=(2,), after_commit=True)
    try:
        ingest_docs(tlf, [("migA", run_of("sport", 2000, 0)),
                           ("migB", run_of("medic", 12, 0))], emb8,
                    store_id="p", place_xdoc=False)
    except RuntimeError:
        pass
    crashf.disarm(tlf)
    pin_f = tlf.pin()[3]
    rep_f = ingest_docs(tlf, [("migA", run_of("sport", 2000, 0)),
                              ("migB", run_of("medic", 12, 0))], emb8,
                        store_id="p", place_xdoc=False,
                        keyed_state=True, archive_manifest=True)
    keyed_f = rep_f.get("keyed", {})
    # The legacy crash left migA partial (10/13 recorded) + migB
    # declared-but-empty with 6 committed ops (flush 2). Migration
    # adopts the 4 atom ops (+2 holons) and completes both without a
    # single new commit; reconcile-rule backlog recompute re-queues
    # the never-placed docs (legacy reconcile parity).
    check("p-mig-adopted",
          keyed_f.get("migrated", {}).get("migrated_docs") == 2
          and keyed_f.get("migrated", {}).get("adopted_ops") == 4
          and sorted(rep_f["skipped"]) == ["migA", "migB"]
          and rep_f["n_atoms"] == 0, f"{rep_f}")
    check("p-mig-no-new-revision",
          len(committed_revisions(tlf, "migA")) == 1, "dup revision")
    man_f = load_manifest(tlf.store.root)
    check("p-mig-manifest-complete",
          man_f["migA"]["status"] == "placement-pending"
          and len(man_f["migA"]["atoms"]) == 13
          and man_f["migA"]["holon"] is not None
          and man_f["migB"]["status"] == "placement-pending"
          and len(man_f["migB"]["atoms"]) == 1
          and man_f["migB"]["holon"] is not None
          and man_f["_pending_placement"] == ["migA", "migB"],
          f"{man_f}")
    check("p-mig-pin-stable", tlf.pin()[3] == pin_f,
          "adoption must commit nothing new")
    tlf.close()

    # -- F. bounded progress I/O --------------------------------------
    # P-2 contract (Sec 5.7, supersedes the old per-call export):
    # ordinary keyed calls perform NO legacy-manifest materialization
    # (zero saves); exactly one save happens on an explicit archive
    # request. (The retired p-io-one-save-per-call pinned the old
    # per-call boundary.)
    spe = os.path.join(_tmpa, "store-io")
    tle = TLStore(spe, create=True, lease_owner="test-c2-p-io")
    real_save = ING._save_manifest
    counts = {}
    for label in ("ingest", "drain", "organize", "retire", "archive"):
        counts[label] = 0

        def counting_save(path, man, _real=real_save, _label=label):
            counts[_label] += 1
            return _real(path, man)

        ING._save_manifest = counting_save
        try:
            if label == "ingest":
                ingest_docs(tle, FROZEN_DOCS, emb8, store_id="p",
                            place_budget=1, keyed_state=True)
            elif label == "drain":
                drain_placement_backlog(tle, store_id="p",
                                        keyed_state=True)
            elif label == "organize":
                organize_segments(tle, keyed_state=True)
            elif label == "retire":
                retire_docs(
                    tle, ["p-e"], reason="p-io",
                    approvals={"p-e": {"type": "user",
                                       "approval_id": "p-io-u1"}},
                    keyed_state=True)
            elif label == "archive":
                PS.export_manifest_archive(tle, reason="p-io")
        finally:
            ING._save_manifest = real_save
    check("p-io-no-save-ordinary",
          all(counts[k] == 0 for k in
              ("ingest", "drain", "organize", "retire")),
          f"{counts}")
    check("p-io-one-save-archive",
          counts["archive"] == 1, f"{counts}")
    # E2: resume of one doc among many touches keyed rows only (no
    # whole-backlog/state scan); windowed pending fetch honors LIMIT.
    st_e = ProducerState.open(tle)
    io0 = st_e.io_snapshot()
    got = st_e.get_doc("p-a")
    win1 = st_e.pending_window(1)
    cnt = st_e.pending_count()
    unorg1 = st_e.unorganized_window(1)
    ucnt = st_e.unorganized_count()
    io1 = st_e.io_snapshot()
    st_e.close()
    d_io = {k: io1[k] - io0[k] for k in io0}
    check("p-io-keyed-touch",
          got is not None and cnt == 0 and ucnt == 0
          and d_io["rows"] <= 40, f"{d_io}")
    check("p-io-window-limit",
          len(win1) <= 1 and len(unorg1) <= 1, "LIMIT honored")
    tle.close()

    print(f"sidecar-suite done: {len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
