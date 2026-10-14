"""Track R8-C: recovery edge repairs (arch section 10.4 checks a + b).

Authority: handoffs/TL-INGEST-NAVIGATION-ARCHITECTURE-2026-10-05.md
section 10.4 (last table row + checks (a)/(b)) and
tl-eval/evidence/round8prep-2026-10-05/RECOVERY-EDGES.md (both
hypotheses CONFIRMED as defects on ingest.py 2aacd546...;
scenarios F-A1/F-A2/F-A3/F-B1/F-B2 defined there in sections
1.4 and 2.4). Pinned env: HF_HOME=<repo>/local-data/hf-cache
HF_HUB_OFFLINE=1 PYTHONHASHSEED=0 (this file needs no encoder:
fake embeddings only).

Repaired behavior asserted here (FAIL before the repair, PASS
after). Controls that already hold keep passing throughout:

  F-A1 (check a): UNKNOWN-origin partial retry with a
    same-chunk-count substituted suffix MUST REFUSE same-revision
    completion (re-ingest under a new doc_id). The byte-identical
    retry is indistinguishable (same verified prefix + same
    count) so it MUST REFUSE too -- this is the B3 flip
    (test_recovery.py B3 encodes the vulnerable behavior).
  F-A2 (B2 control): UNKNOWN-origin FULL-coverage retry with
    identical bytes MUST ALLOW skip + hash adoption (no new bytes
    are certified).
  F-A3 (count gate): UNKNOWN-origin partial retry that changes
    the chunk count MUST REFUSE (committed-n_chunks gate).
  F-B1 (check b): torn journal tail + restart appending two
    durable flushed records + crash before snapshot retirement +
    restart MUST leave both records recoverable (repair =
    truncate/rotate to the last validated boundary BEFORE the
    first append of a call).
  F-B2 (masking control): torn tail + ONE post-restart append +
    successful call end succeeds today (the end-save masks the
    swallowed record). Control MUST PASS; the forensic assertion
    (torn fragment preserved aside; no record silently swallowed)
    FAILS until the repair.

Repair contract pinned by the forensic assertions (any mechanism
satisfying the observables is acceptable):
  R1. A call MUST NOT append onto an unvalidated (torn) journal
      tail; it restores a validated boundary first.
  R2. The exact torn bytes MUST be preserved aside for forensics
      in some file under the store root OTHER than the journal
      itself (name/mechanism free; content pinned: the torn byte
      sequence must appear verbatim in the sibling file).

Run: tl-sys/.venv/bin/python tl-sys/tests/test_recovery_edges.py
"""
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import (chunk_text, ingest_docs, _journal_records,  # noqa: E402
                          JOURNAL_NAME)
from tlsys.maint import reconcile_manifest  # noqa: E402
import tlsys.ingest as _ingmod  # noqa: E402

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


def words(n):
    return " ".join(f"w{i}" for i in range(n))


def sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def committed_atoms(tl, doc_id):
    """Committed atom metas for one doc: [(chunk_ix, aid, revision)]."""
    birth, epoch, mx, _t = tl.pin()
    rows = tl.read_commits(birth, epoch, mx, kind="ACCEPT_ATOMS",
                           limit=1000000)
    refs = tl.pub_refs([r[0] for r in rows])
    out, holons = [], {}
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
            if meta.get("doc_id") == doc_id and "atom" in meta:
                out.append((meta.get("chunk_ix"), meta.get("atom"),
                            meta.get("revision_id")))
            elif meta.get("holon") == doc_id and "members" in meta:
                holons[meta["holon"]] = list(meta.get("members", []))
    return out, holons


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


class EndSaveCrasher:
    """Fail _save_manifest (journal mode: the single end-save only)."""

    def __init__(self):
        self.real = _ingmod._save_manifest
        self.calls = 0
        _ingmod._save_manifest = self

    def __call__(self, path, man):
        self.calls += 1
        raise RuntimeError("SIMCRASH-pre-snapshot")

    def disarm(self):
        _ingmod._save_manifest = self.real


def make_unknown_partial(tmp, tag, text):
    """Crash-partial (10 atoms, no holon) + manifest loss + reconcile.

    Returns (tl, store_path). The doc id is f"doc-{tag}".
    """
    doc = f"doc-{tag}"
    sp = os.path.join(tmp, f"store-{tag}")
    tl = TLStore(sp, create=True, lease_owner=f"test-r8c-{tag}")
    crash = Crasher(tl, fail_on=(2,))
    try:
        ingest_docs(tl, [(doc, text)], emb, store_id="r8c",
                    place_xdoc=False)
    except RuntimeError:
        pass
    crash.disarm(tl)
    os.remove(os.path.join(sp, "ingest_manifest.json"))
    reconcile_manifest(tl, store_id="r8c")
    return tl, sp, doc


def main():
    tmp = tempfile.mkdtemp(prefix="tlsys-r8c-")
    t12 = words(1800)
    check("geom-12-chunks", len(chunk_text(t12)) == 12,
          f"{len(chunk_text(t12))}")

    # -- F-A1 (check a): same-count suffix substitution must refuse --
    # Substitution past token 1549 (end of committed chunk 9):
    # same token count -> still 12 chunks; committed prefix
    # byte-identical -> verifier passes on current code (defect).
    toks = t12.split(" ")
    sub = " ".join(toks[:1550] + [f"zzz{i}" for i in range(1550, 1800)])
    check("FA1-construction-12-chunks", len(chunk_text(sub)) == 12,
          f"{len(chunk_text(sub))}")
    check("FA1-construction-prefix-identical",
          chunk_text(sub)[:10] == chunk_text(t12)[:10],
          "committed prefix must be byte-identical")

    tl, _sp, doc = make_unknown_partial(tmp, "fa1-sub", t12)
    man = load_manifest(tl)
    check("FA1-setup-sourceless-partial",
          "source_sha256" not in man[doc]
          and len(man[doc]["atoms"]) == 10
          and man[doc]["holon"] is None, f"{man.get(doc)}")
    pin_pre = tl.pin()[3]
    try:
        rep = ingest_docs(tl, [(doc, sub)], emb, store_id="r8c",
                          place_xdoc=False)
        check("FA1-substituted-refused", False,
              f"completed same revision: {rep}")
    except RuntimeError as e:
        check("FA1-substituted-refused", True, f"{e}")
    check("FA1-substituted-pin-stable", tl.pin()[3] == pin_pre,
          "refusal must commit nothing")
    tl.close()

    # F-A1 control (B3 flip): byte-identical retry is
    # indistinguishable -> must refuse completion too.
    tl, _sp, doc = make_unknown_partial(tmp, "fa1-ident", t12)
    pin_pre = tl.pin()[3]
    try:
        rep = ingest_docs(tl, [(doc, t12)], emb, store_id="r8c",
                          place_xdoc=False)
        check("FA1-identical-refused-B3flip", False,
              f"completed same revision: {rep}")
    except RuntimeError as e:
        check("FA1-identical-refused-B3flip", True, f"{e}")
    check("FA1-identical-pin-stable", tl.pin()[3] == pin_pre,
          "refusal must commit nothing")
    tl.close()

    # -- F-A2 (B2 control): full-coverage identical retry allows ----
    sp = os.path.join(tmp, "store-fa2")
    tl = TLStore(sp, create=True, lease_owner="test-r8c-fa2")
    ingest_docs(tl, [("doc-fa2", "alpha one two three")], emb,
                store_id="r8c", place_xdoc=False)
    os.remove(os.path.join(sp, "ingest_manifest.json"))
    reconcile_manifest(tl, store_id="r8c")
    pin_pre = tl.pin()[3]
    rep = ingest_docs(tl, [("doc-fa2", "alpha one two three")], emb,
                      store_id="r8c", place_xdoc=False)
    man = load_manifest(tl)
    check("FA2-skip-allowed", rep["skipped"] == ["doc-fa2"]
          and tl.pin()[3] == pin_pre, f"{rep}")
    check("FA2-hash-adopted",
          man["doc-fa2"].get("source_sha256")
          == sha("alpha one two three"), f"{man['doc-fa2']}")
    tl.close()

    # -- F-A3 (count gate): changed chunk count must refuse ---------
    tl, _sp, doc = make_unknown_partial(tmp, "fa3", t12)
    # 1860 tokens -> 13 chunks != 12 (window s=1650 no longer covers
    # the end, so s=1800 opens a 13th chunk; 1801 tokens still yields
    # 12 because the s=1650 window covers through token 1800).
    more = t12 + " " + words(60)
    check("FA3-construction-13-chunks", len(chunk_text(more)) == 13,
          f"{len(chunk_text(more))}")
    pin_pre = tl.pin()[3]
    try:
        rep = ingest_docs(tl, [(doc, more)], emb, store_id="r8c",
                          place_xdoc=False)
        check("FA3-count-change-refused", False,
              f"completed same revision: {rep}")
    except RuntimeError as e:
        check("FA3-count-change-refused", True, f"{e}")
    check("FA3-pin-stable", tl.pin()[3] == pin_pre,
          "refusal must commit nothing")
    tl.close()

    # -- F-B1 (check b): torn tail + 2 appends + pre-snapshot crash --
    sp = os.path.join(tmp, "store-fb1")
    tl = TLStore(sp, create=True, lease_owner="test-r8c-fb1")
    jp = os.path.join(sp, JOURNAL_NAME)
    # Phase 1: journal-mode ingest, crash before the end-save ->
    # complete journal records on disk, stale/missing manifest.
    crash1 = EndSaveCrasher()
    try:
        ingest_docs(tl, [("docP", "seed bytes one two three")], emb,
                    store_id="r8c", place_xdoc=False,
                    progress_journal=True)
        check("FB1-phase1-crash-injected", False, "no crash?")
    except RuntimeError as e:
        check("FB1-phase1-crash-injected", "SIMCRASH" in str(e),
              f"{e}")
    finally:
        crash1.disarm()
    with open(jp) as f:
        phase1_lines = [ln for ln in f.read().split("\n") if ln.strip()]
    check("FB1-phase1-journal-complete", len(phase1_lines) == 2
          and all(json.loads(ln).get("seq") for ln in phase1_lines),
          f"{len(phase1_lines)} lines")
    # Simulate the torn tail: a mid-record prefix with no newline.
    torn = '{"event": "flushed", "ops": [{"doc": "docP", "kind": "atom"'
    with open(jp, "a") as f:
        f.write(torn)
    # Phase 2 (restart 1): new 12-chunk doc -> started + TWO flushed
    # appends; crash again before snapshot retirement.
    crash2 = EndSaveCrasher()
    try:
        ingest_docs(tl, [("docQ", t12)], emb, store_id="r8c",
                    place_xdoc=False, progress_journal=True)
        check("FB1-phase2-crash-injected", False, "no crash?")
    except RuntimeError as e:
        check("FB1-phase2-crash-injected", "SIMCRASH" in str(e),
              f"{e}")
    finally:
        crash2.disarm()
    # Phase 3 (restart 2): replay must recover BOTH flushed records.
    pin_pre = tl.pin()[3]
    try:
        recs = _journal_records(jp)
        n_flushed_q = sum(1 for r in recs
                          if r.get("event") == "flushed"
                          and any(o.get("doc") == "docQ"
                                  for o in r.get("ops", [])))
        check("FB1-journal-parses-both-flushed", n_flushed_q == 2,
              f"{n_flushed_q}/2 flushed records for docQ parse")
    except RuntimeError as e:
        check("FB1-journal-parses-both-flushed", False, f"{e}")
        n_flushed_q = 0
    try:
        rep = ingest_docs(tl, [("docP", "seed bytes one two three"),
                               ("docQ", t12)], emb, store_id="r8c",
                          place_xdoc=False, progress_journal=True)
        atoms_q, holons_q = committed_atoms(tl, "docQ")
        atoms_p, holons_p = committed_atoms(tl, "docP")
        check("FB1-both-recoverable",
              "docP" in rep["skipped"] and "docQ" in rep["skipped"]
              and tl.pin()[3] == pin_pre
              and len(atoms_q) == 12 and "docQ" in holons_q
              and len({m[2] for m in atoms_q}) == 1
              and len(atoms_p) == 1 and "docP" in holons_p,
              f"{rep}")
    except RuntimeError as e:
        check("FB1-both-recoverable", False, f"{e}")
    tl.close()

    # -- F-B2 (masking control + forensic assertion) ----------------
    sp = os.path.join(tmp, "store-fb2")
    tl = TLStore(sp, create=True, lease_owner="test-r8c-fb2")
    jp = os.path.join(sp, JOURNAL_NAME)
    # Setup: journal-mode declaration persisted, commit crashed ->
    # journal holds exactly one complete (started) record.
    crash = Crasher(tl, fail_on=(1,))
    try:
        ingest_docs(tl, [("docS", "solo chunk bytes here")], emb,
                    store_id="r8c", place_xdoc=False,
                    progress_journal=True)
    except RuntimeError:
        pass
    crash.disarm(tl)
    with open(jp) as f:
        setup_lines = [ln for ln in f.read().split("\n") if ln.strip()]
    check("FB2-setup-one-started-record", len(setup_lines) == 1
          and json.loads(setup_lines[0]).get("event") == "started",
          f"{len(setup_lines)} lines")
    torn2 = '{"event": "flushed", "ops": [{"doc": "docS"'
    with open(jp, "a") as f:
        f.write(torn2)
    # Restart: resume needs exactly ONE flush -> ONE post-restart
    # append; the call ends successfully (masking on current code).
    try:
        rep = ingest_docs(tl, [("docS", "solo chunk bytes here")], emb,
                          store_id="r8c", place_xdoc=False,
                          progress_journal=True)
        atoms_s, holons_s = committed_atoms(tl, "docS")
        check("FB2-masking-control",
              len(atoms_s) == 1 and "docS" in holons_s
              and len({m[2] for m in atoms_s}) == 1, f"{rep}")
    except RuntimeError as e:
        check("FB2-masking-control", False, f"{e}")
    # Forensic assertion (repair R1+R2): the torn bytes must be
    # preserved aside (any sibling file under the store root other
    # than the journal itself carrying the exact torn sequence),
    # and no record may be silently swallowed.
    tb = torn2.encode("utf-8")
    preserved = False
    for name in os.listdir(sp):
        if name == JOURNAL_NAME:
            continue
        p = os.path.join(sp, name)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, "rb") as f:
                if tb in f.read():
                    preserved = True
                    break
        except OSError:
            continue
    check("FB2-torn-fragment-preserved", preserved,
          "no sibling file carries the exact torn bytes")
    tl.close()

    print("store-root:", tmp)
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
