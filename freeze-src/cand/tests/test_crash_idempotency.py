"""Crash-idempotency regressions for the batched organize seam (own fork).

Strong case: a doc that JOINED a foreign leaf is SIGKILLed after its
organization commits but before its service ACK persists. On retry the
already-organized doc must be skipped commit-free (ENTIRE pin tuple
unchanged) while still running per-doc callbacks, attempt increment,
and persisted service ACK. A following doc under max_documents=1 must
stay untouched.

Direct case: replaying an organized doc through organize_segments with
a service checkpoint skips run_doc (no commits, callbacks still fire,
reported organized); the default None path keeps recompute semantics.

Runnable standalone: `python -B test_crash_idempotency.py` from this dir.
Constraints: <=10 synthetic docs, single-threaded env, nice 19.
"""
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
try:
    os.nice(19)
except OSError:
    pass

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "fork" / "tl-sys"))
sys.path.insert(0, str(HERE / "fork" / "tl-candidate-batch" / "candidate"))
TMP = HERE / "tmp"
TMP.mkdir(exist_ok=True)

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.org_service import OrganizationService, ServiceConfig  # noqa: E402
from tlsys.ingest import ingest_docs, _committed_doc_state  # noqa: E402
from tlsys.maint import organize_segments  # noqa: E402

PY = sys.executable

ALPHA = [1., 0., 0., 0.]
BETA = [0., 1., 0., 0.]


def embed(texts):
    return [list(ALPHA) if t.split()[0] == "alpha" else list(BETA)
            for t in texts]


def docs3():
    return [("F", "alpha foreign leaf doc"),
            ("B", "alpha victim doc same topic"),
            ("C", "beta following doc other topic")]


def make_service(tl, directory, **kw):
    cfg = ServiceConfig(enabled=True, drain_budget_seconds=600,
                        max_documents_per_drain=64, batched_drain=True)
    return OrganizationService(tl, config=cfg, directory=str(directory),
                               keyed_state=True, **kw)


def geometry_hash(tl):
    from tlsys.proj import Projections
    proj = Projections.cached(tl)
    proj.update(tl)
    view = proj.hierarchy_view()
    leaves = {}
    for lid, v in view["leaves"].items():
        docset = sorted(s.get("doc") for s in v.get("segments", []))
        leaves[lid] = (docset,
                       [round(float(x), 9) for x in v["descriptor"]])
    parents = {}
    for pid, v in view["parents"].items():
        pdocs = sorted({d for c in v.get("children", [])
                        for d in leaves.get(c, ([], []))[0]})
        parents[pid] = (pdocs, sorted(v.get("children", [])),
                        [round(float(x), 9) for x in v["descriptor"]])
    canon = json.dumps({"leaves": leaves, "parents": parents},
                       sort_keys=True, default=str)
    return hashlib.sha256(canon.encode()).hexdigest()


def doc_op_ids(tl, doc):
    comm = _committed_doc_state(tl, doc)
    return (sorted(c["op_id"] for c in comm["by_ix"].values()),
            comm["holon"][0] if comm["holon"] else None)


def organized_docset(tl):
    from tlsys.proj import Projections
    proj = Projections.cached(tl)
    proj.update(tl)
    view = proj.hierarchy_view()
    return {s.get("doc") for v in view["leaves"].values()
            for s in v.get("segments", [])}


def backlog_maps(svc):
    rows = svc.backlog()
    return ({b["doc_id"]: b["state"] for b in rows},
            {b["doc_id"]: b["attempts"] for b in rows},
            {b["doc_id"]: b["last_error"] for b in rows})


class SigkillPinInvariantTests(unittest.TestCase):
    def test_sigkill_retry_leaves_entire_pin_unchanged(self):
        work = Path(tempfile.mkdtemp(prefix="crash-", dir=str(TMP)))
        store, svcdir = str(work / "store"), str(work / "svc")
        pid_file, ready_file = str(work / "child.pid"), str(work / "ready")
        child_log = str(work / "child.log")

        tl = TLStore(store, create=True)
        svc = make_service(tl, svcdir)
        try:
            svc.ingest(docs3(), embed)
            rep_f = svc.drain(max_documents=1)
            self.assertEqual(rep_f["completed"], ["F"], rep_f)
        finally:
            svc.close()
            tl.close()

        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                   OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                   MKL_NUM_THREADS="1", TMPDIR=str(TMP))
        child_out = open(str(work / "child.out"), "w")
        child = subprocess.Popen(
            [PY, "-B", str(HERE / "tools" / "child_crash_drain.py"),
             store, svcdir, pid_file, ready_file, child_log],
            env=env, stdout=child_out,
            stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 120
            while not os.path.exists(ready_file):
                self.assertLess(time.monotonic(), deadline,
                                "child never reached after_organize_before_ack")
                self.assertIsNone(child.poll(), "child exited before fault")
                time.sleep(0.05)
            tracked = int(Path(pid_file).read_text().strip())
            self.assertEqual(tracked, child.pid)  # tracked child PID
            os.kill(tracked, signal.SIGKILL)  # observed: real SIGKILL
            rc = child.wait(timeout=60)
            self.assertEqual(rc, -signal.SIGKILL)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            child_out.close()

        # Post-kill, pre-retry observed state on the same store.
        tl = TLStore(store)
        try:
            # B joined F's foreign leaf: committed but unacknowledged.
            self.assertIn("B", organized_docset(tl))
            src_pre = doc_op_ids(tl, "B")
            pin_pre = tl.pin()
        finally:
            tl.close()
        probe = TLStore(store)
        svc_probe = make_service(probe, svcdir)
        try:
            states, attempts, errors = backlog_maps(svc_probe)
            self.assertEqual(states["B"], "pending")
            self.assertEqual(attempts["B"], 1)
            self.assertEqual(states["C"], "pending")
            self.assertEqual(attempts["C"], 0,
                             "following doc untouched before kill")
            self.assertIsNone(errors["C"])
        finally:
            svc_probe.close()
            probe.close()

        # Retry with max_documents=1: B must complete with zero new ops.
        tl2 = TLStore(store)
        svc2 = make_service(tl2, svcdir)
        try:
            rep2 = svc2.drain(max_documents=1)
            self.assertEqual(rep2["completed"], ["B"], rep2)
            self.assertEqual(rep2["failed"], {}, rep2)
            self.assertEqual(tl2.pin(), pin_pre,
                             "ENTIRE pin must be unchanged on retry")
            self.assertEqual(doc_op_ids(tl2, "B"), src_pre,
                             "no duplicate source commits on retry")
            states, attempts, _ = backlog_maps(svc2)
            self.assertEqual(states["B"], "done",
                             "service ACK persisted on retry")
            self.assertEqual(attempts["B"], 2,
                             "retry ran callbacks (attempt increment)")
            self.assertEqual(states["C"], "pending")
            self.assertEqual(attempts["C"], 0,
                             "following doc untouched on max1 retry")
            rep3 = svc2.drain()
            self.assertEqual(rep3["completed"], ["C"], rep3)
            geo_restart = geometry_hash(tl2)
        finally:
            svc2.close()
            tl2.close()

        # Clean run with the identical drain sequence (observed).
        work2 = Path(tempfile.mkdtemp(prefix="crash-clean-", dir=str(TMP)))
        tl3 = TLStore(str(work2 / "store"), create=True)
        svc3 = make_service(tl3, str(work2 / "svc"))
        try:
            svc3.ingest(docs3(), embed)
            svc3.drain(max_documents=1)
            svc3.drain(max_documents=1)
            svc3.drain()
            self.assertEqual(geometry_hash(tl3), geo_restart,
                             "retry geometry matches clean run")
        finally:
            svc3.close()
            tl3.close()


class AlreadyOrganizedReplayTests(unittest.TestCase):
    def _joined_store(self):
        work = Path(tempfile.mkdtemp(prefix="replay-", dir=str(TMP)))
        tl = TLStore(str(work / "store"), create=True)
        ingest_docs(tl, [("F", "alpha foreign leaf doc"),
                         ("B", "alpha victim doc same topic")], embed,
                    keyed_state=True)
        organize_segments(tl, doc_ids=["F"], keyed_state=True)
        organize_segments(tl, doc_ids=["B"], keyed_state=True)
        return tl, work

    def test_checkpoint_replay_skips_commit_free(self):
        tl, _work = self._joined_store()
        try:
            pin_pre = tl.pin()
            calls = []

            def ck(stage, doc, err=None):
                calls.append((stage, doc, err))
                return True

            rep = organize_segments(tl, doc_ids=["B"], keyed_state=True,
                                    doc_checkpoint=ck)
            self.assertEqual(rep["organized"], ["B"], rep)
            self.assertEqual(rep["failed"], {}, rep)
            self.assertEqual(rep["n_commits"], 0, rep)
            self.assertEqual(rep["n_leaf_ops"] + rep["n_parent_ops"], 0,
                             rep)
            self.assertEqual(tl.pin(), pin_pre,
                             "ENTIRE pin unchanged on checkpoint replay")
            self.assertEqual([(c[0], c[1]) for c in calls],
                             [("before", "B"), ("after", "B")],
                             "before/after callbacks maintained")
            self.assertIsNone(calls[1][2], "no error on skip path")
        finally:
            tl.close()

    def test_default_none_keeps_recompute_semantics(self):
        tl, _work = self._joined_store()
        try:
            pin_pre = tl.pin()
            rep = organize_segments(tl, doc_ids=["B"], keyed_state=True)
            self.assertEqual(rep["organized"], ["B"], rep)
            # Explicit recompute without a callback still recomputes:
            # B re-joins then mints its singleton, committing new ops.
            self.assertGreater(rep["n_commits"], 0, rep)
            self.assertNotEqual(tl.pin(), pin_pre)
        finally:
            tl.close()

    def test_checkpoint_budget_stop_leaves_rest_untouched(self):
        tl, _work = self._joined_store()
        try:
            calls = []

            def ck(stage, doc, err=None):
                calls.append((stage, doc))
                if stage == "before" and doc == "F":
                    return False  # exhausted budget: stop
                return True

            rep = organize_segments(tl, doc_ids=["B", "F"],
                                    keyed_state=True, doc_checkpoint=ck)
            self.assertEqual(rep["organized"], ["B"], rep)
            self.assertNotIn("F", rep["failed"], rep)
            self.assertIn("F", rep["remaining"], rep)
            self.assertEqual([c for c in calls],
                             [("before", "B"), ("after", "B"),
                              ("before", "F")])
        finally:
            tl.close()

    def test_checkpoint_error_propagates(self):
        tl, _work = self._joined_store()
        try:
            def ck(stage, doc, err=None):
                if stage == "after":
                    raise RuntimeError("boom-after-ack")
                return True

            with self.assertRaises(RuntimeError):
                organize_segments(tl, doc_ids=["B"], keyed_state=True,
                                  doc_checkpoint=ck)
        finally:
            tl.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
