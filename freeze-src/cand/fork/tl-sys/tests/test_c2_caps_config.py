"""C2 100M recovery (lane-R100M): per-run admission caps + cause-preserving
commit-failure format.

Root cause (CLASSIFICATION.md): max_delta_entries=100000 (D-12 default)
is a hard lifetime commit ceiling (delta_entries=COUNT(commits),
monotonic: P5 prune never deletes commits). The 100M p0 leg hit
exactly 100,000 commits; every further reserve burned the 5.0 s
deadline and raised REJECT_CAPACITY(deadline) -> organize-p0 took
47,784.7 s (9,444 x ~5 s) and ingest-p1 died fail-stop. The old
f"{status}:{code}" format printed "retryable:None", discarding the
REJECT_CAPACITY cause that retryable/not_attempted carry under
message/reason.

Covers: TLStore caps plumbing (defaults untouched when caps=None),
admission honored in both directions, sized caps admitting past the
default ceiling at a 100k+ ledger, and cause preservation (unit +
ingest + organize end-to-end).

Deterministic; scratch stores under /tmp; one ~5 s deadline burn only
in the default-deadline path (ingest end-to-end).
Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_caps_config.py
"""
import os
import sqlite3
import sys
import tempfile
import time
import uuid

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore, format_commit_failure  # noqa: E402
from tlsys.store_if import uuidv7 as _uuidv7  # noqa: E402
import intake  # noqa: E402  (candidate dir auto-added by store_if)
from tlsys.ingest import chunk_text, ingest_docs  # noqa: E402
from tlsys.maint import organize_segments  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 8


def _emb(texts):
    return [[1.0] + [0.0] * (DIM - 1) for _ in texts]


def _mkstore(caps=None):
    tmp = tempfile.mkdtemp(prefix="caps-config-")
    kw = {"lease_owner": "test-caps"}
    if caps is not None:
        kw["caps"] = caps
    tl = TLStore(tmp, create=True, **kw)
    return tl, tmp


def _op(i):
    # ACCEPT_ATOMS is non-consequential: no approval_ref required;
    # no artifacts listed, so no artifact durability to arrange.
    return {"op_id": _uuidv7(), "kind": "ACCEPT_ATOMS",
            "payload": {"atom": "a%d" % i, "doc_id": "d",
                        "meta_artifact": "none"},
            "disclosure": {"leg": "ingest", "doc_id": "d", "chunk_ix": i},
            "approval_ref": None, "artifacts": ()}


def _set_ledger(tmp, delta):
    con = sqlite3.connect(os.path.join(tmp, "commit.db"))
    try:
        con.execute("UPDATE counters SET v=? WHERE k='delta_entries'",
                    (delta,))
        con.commit()
    finally:
        con.close()


def main():
    # -- T1: defaults untouched when caps=None --
    tl, tmp = _mkstore()
    try:
        check("defaults-values", tl.cm.caps == intake.CAPS,
              f"{tl.cm.caps}")
        check("defaults-copy", tl.cm.caps is not intake.CAPS)
    finally:
        tl.close()

    # -- T2: sized caps plumbed + copied --
    sized = dict(intake.CAPS, max_delta_entries=2000000,
                 max_dedup_rows=2000000)
    tl, tmp = _mkstore(caps=sized)
    try:
        check("plumbing-sized",
              tl.cm.caps.get("max_delta_entries") == 2000000
              and tl.cm.caps.get("max_dedup_rows") == 2000000
              and tl.cm.caps.get("reserve_deadline_s")
              == intake.CAPS["reserve_deadline_s"],
              f"{tl.cm.caps}")
        sized["max_delta_entries"] = 7
        check("plumbing-copy", tl.cm.caps["max_delta_entries"] == 2000000,
              f"{tl.cm.caps}")
        check("defaults-unpolluted",
              intake.CAPS["max_delta_entries"] == 100000, f"{intake.CAPS}")
    finally:
        tl.close()

    # -- T3: tiny caps enforced (fast deadline), cause carried --
    tiny = dict(intake.CAPS, max_delta_entries=2, reserve_deadline_s=0.05)
    tl, tmp = _mkstore(caps=tiny)
    try:
        res, info = tl.commit_batch([_op(1), _op(2)])
        check("tiny-admit",
              [r.get("status") for r in res] == ["committed", "committed"],
              f"{res}")
        t0 = time.time()
        res2, info2 = tl.commit_batch([_op(3)])
        dt = time.time() - t0
        check("tiny-reject-status",
              [r.get("status") for r in res2] == ["retryable"], f"{res2}")
        check("tiny-reject-cause",
              "REJECT_CAPACITY" in (res2[0].get("message") or ""),
              f"{res2}")
        check("tiny-reject-fast", dt < 4.0, f"{dt:.2f}s")
        check("tiny-abort-info",
              (info2.get("abort") or {}).get("error_type") == "Retryable",
              f"{info2}")
    finally:
        tl.close()

    # -- T4: sized caps admit past the default ceiling at 100k+ ledger --
    tl, tmp = _mkstore(caps=dict(
        intake.CAPS, max_delta_entries=2000000,
        max_dedup_rows=2000000))
    try:
        _set_ledger(tmp, 150000)
        res, _info = tl.commit_batch([_op(4)])
        check("sized-admits-past-default",
              [r.get("status") for r in res] == ["committed"], f"{res}")
    finally:
        tl.close()
    # ... while the default limit still rejects that ledger (same
    # max_delta_entries value, shortened deadline only for speed).
    tl, tmp = _mkstore()
    try:
        _set_ledger(tmp, 150000)
        con = tl.store.open_db()
        try:
            t0 = time.time()
            try:
                intake.reserve(
                    con, 10,
                    dict(intake.CAPS, reserve_deadline_s=0.05),
                    t0, "UPSERT_ATOMS")
                granted = True
            except Exception as e:  # noqa: BLE001 -- asserting the shape
                granted = False
                etype, emsg = type(e).__name__, str(e)
        finally:
            con.close()
        check("default-limit-rejects-150k",
              not granted and etype == "Retryable"
              and "REJECT_CAPACITY" in emsg,
              f"granted={granted} {etype}: {emsg}")
    finally:
        tl.close()

    # -- T5: helper preserves every result shape's cause --
    shapes = [
        ({"op_id": "a", "status": "retryable",
          "message": "Retryable: REJECT_CAPACITY(deadline): x"},
         ["op a", "retryable", "REJECT_CAPACITY"]),
        ({"op_id": "b", "status": "not_attempted",
          "reason": "batch pre-commit abort: Retryable: "
                    "REJECT_CAPACITY(staged): y"},
         ["op b", "not_attempted", "REJECT_CAPACITY"]),
        ({"op_id": "c", "status": "terminal", "code": "APPROVAL_MISSING",
          "detail": "no grant"}, ["op c", "terminal", "APPROVAL_MISSING"]),
        ({"op_id": "d", "status": "raised", "code": "TERMINAL_REPLAY",
          "detail": "replay says no"},
         ["op d", "raised", "TERMINAL_REPLAY"]),
    ]
    for r, wants in shapes:
        got = format_commit_failure(r)
        check(f"helper-{r['status']}",
              all(w in got for w in wants), got)

    # -- T6: ingest end-to-end preserves the REJECT_CAPACITY cause --
    # (default caps + faked 100k ledger: old code raises with
    # "retryable:None"; new code names REJECT_CAPACITY.)
    tl, tmp = _mkstore()
    try:
        _set_ledger(tmp, 100000)
        docs = [("capdoc", "alpha beta gamma delta epsilon")]
        try:
            ingest_docs(tl, docs, _emb, store_id="caps-e2e")
            raised = None
        except RuntimeError as e:
            raised = str(e)
        check("ingest-names-cause",
              raised is not None and "REJECT_CAPACITY" in raised,
              f"{raised}")
    finally:
        tl.close()

    # -- T7: organize end-to-end records the cause in failed[doc] --
    tl, tmp = _mkstore()
    try:
        docs = [("orgdoc", "alpha beta gamma delta epsilon zeta eta")]
        rep = ingest_docs(tl, docs, _emb, store_id="caps-e2e",
                          place_xdoc=True, keyed_state=True)
        check("organize-setup-committed",
              rep.get("n_atoms", 0) > 0, f"{rep}")
        _set_ledger(tmp, 100000)
        orep = organize_segments(tl, doc_ids=["orgdoc"], budget=None,
                                 store_id="caps-e2e", keyed_state=True)
        check("organize-names-cause",
              "orgdoc" in orep.get("failed", {})
              and "REJECT_CAPACITY" in orep["failed"]["orgdoc"],
              f"{orep.get('failed')}")
    finally:
        tl.close()

    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
