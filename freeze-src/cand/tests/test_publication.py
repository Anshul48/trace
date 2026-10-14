"""Standard-library unittest fixtures; scratch evidence is preserved, never deleted."""
import dataclasses
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from tlsys.ingest import ingest_docs
from tlsys.maint import organize_segments
from tlsys.org_publication import GenerationPublisher, PreparedFacade
from tlsys.org_service import OrganizationService, ServiceConfig
from tlsys.place import read_seg_hierarchy, leaf_op, parent_op
from tlsys.store_if import TLStore, prepare_artifact


def embed(texts):
    return [[1., 0., 0., 0.] if t.startswith('alpha') else [0., 1., 0., 0.] for t in texts]


def service(tl, **kwargs):
    return OrganizationService(tl, config=ServiceConfig(enabled=True,
                               drain_budget_seconds=30), **kwargs)


def kill_writer(root, marker, stage, organize_kwargs=None):
    tl = TLStore(root)
    def fault(where):
        if where == stage:
            Path(marker).write_text(where)
            while True:
                time.sleep(.02)
    if stage == 'after_source_batch_before_progress':
        original = tl.commit_batch
        def interrupted(ops):
            result = original(ops)
            fault(stage)
            return result
        tl.commit_batch = interrupted
    s = service(tl, fault=fault, organize_kwargs=organize_kwargs)
    s.drain(max_documents=1, budget_seconds=30)


def kill_publisher(root, marker):
    tl = TLStore(root)
    def publication_fault(where):
        if where == 'after_durable_pointer':
            Path(marker).write_text(where)
            while True:
                time.sleep(.02)
    def factory(tl, directory):
        return GenerationPublisher(tl, directory, fault=publication_fault)
    s = service(tl, publisher_factory=factory)
    s.drain(max_documents=1,budget_seconds=30)
    s.last_future.result()


class FakeMembershipRepair:
    """Versioned fake reassignment, exactly once per fake instance (no policy claim)."""
    def __init__(self, tl):
        self.tl, self.calls, self.done = tl, [], False

    def repair_step(self, budget):
        self.calls.append(budget)
        if not budget or self.done:
            return {"processed": 0}
        hierarchy = read_seg_hierarchy(self.tl, self.tl.pin())
        leaves = hierarchy['leaves']
        first, second = sorted(leaves)[:2]
        old_first, old_second = list(leaves[first]['members']), list(leaves[second]['members'])
        leaves[first]['members'], leaves[second]['members'] = old_second, old_first
        facade = PreparedFacade(self.tl, self.tl.pin(), ())
        atoms = facade._index.atoms
        def mean(ids):
            return np.asarray([atoms[a]['descriptor'] for a in ids], dtype=np.float64).mean(axis=0).tolist()
        prep = lambda body, sid: prepare_artifact(self.tl.store, body, sid)
        ops = [leaf_op(lid, leaves[lid]['members'], mean(leaves[lid]['members']),
                       'publish-fake', prep) for lid in (first, second)]
        for pid, p in hierarchy['parents'].items():
            if not set(p['children']) & {first, second}:
                continue
            members = list(dict.fromkeys(a for c in p['children'] for a in leaves[c]['members']))
            ops.append(parent_op(pid, p['children'], members, mean(members), 'publish-fake', prep))
        try:
            for lo in range(0, len(ops), 10):
                result, _ = self.tl.commit_batch(ops[lo:lo+10])
                assert all(r['status'] == 'committed' for r in result), result
        finally:
            facade.close()
        self.done = True
        return {"processed": 1, "rewritten_leaves": [first, second]}


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='publish-unit-'))
        self.tl = TLStore(str(self.root / 'store'), create=True)
        self.services = []

    def tearDown(self):
        for s in self.services:
            s.close()
        if self.tl is not None:
            self.tl.close()

    def make(self, **kwargs):
        s = service(self.tl, **kwargs)
        self.services.append(s)
        return s

    def test_two_old_pins_and_immutable_complete_frontier(self):
        s = self.make()
        s.ingest([('d1', 'alpha one'), ('d2', 'beta two')], embed)
        g0 = s.last_future.result()
        a, b = s.publisher.acquire(), s.publisher.acquire()
        try:
            rows, work = a.facade.pending_search([1., 0., 0., 0.], k=100)
            self.assertEqual(len(rows), 2)  # oversized k clamps
            self.assertEqual(work['pending_atoms_scored'], 2)
            with self.assertRaises(dataclasses.FrozenInstanceError):
                g0.generation_id = 'bad'
            self.assertEqual(s.drain(max_documents=1)['attempted'], 1)
            g1 = s.last_future.result()
            self.assertEqual(g1.parent_generation, g0.generation_id)
            self.assertEqual(g1.pending_documents, ('d2',))
            self.assertEqual(a.generation, g0)
            self.assertEqual(b.generation, g0)
            self.assertEqual(a.facade.atom_count, 2)
            self.assertEqual(s.publisher.retained()[g0.generation_id], 2)
            s.ingest([('d3', 'alpha three')], embed)
            g2 = s.last_future.result()
            self.assertEqual(a.facade.atom_count, 2)
            with s.publisher.acquire() as c:
                self.assertEqual(c.facade.atom_count, 3)
                self.assertEqual(c.generation, g2)
                self.assertNotEqual(c.facade._index._pool, a.facade._index._pool)
                with self.assertRaises(TypeError):
                    c.facade.leaves['mutation'] = {}
        finally:
            a.release()
            self.assertIn(g0.generation_id, s.publisher.retained())
            b.release()
        self.assertNotIn(g0.generation_id, s.publisher.retained())
        with self.assertRaises(RuntimeError):
            a.release()
        with self.assertRaises(RuntimeError):
            _ = a.facade

    def test_prepare_failures_never_visible(self):
        s = self.make()
        s.ingest([('d', 'alpha')], embed)
        old = s.last_future.result()
        pointer = (s.publisher.directory / 'current.json').read_bytes()
        for i, stage in enumerate(('before_prepare', 'after_prepare', 'before_pointer')):
            # Fault rides on the ingest's own submit: an identical-frontier
            # publish() is idempotent (no preparation runs), so the fresh
            # frontier from ingest must hit the injected stage directly.
            current = s.last_future.result()
            pointer = (s.publisher.directory / 'current.json').read_bytes()
            def fail(where, selected=stage):
                if where == selected:
                    raise RuntimeError('injected ' + selected)
            s.publisher._fault = fail
            s.ingest([(f'df-{i}', f'alpha fault {i}')], embed)
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                s.last_future.result()
            s.publisher._fault = None
            with s.publisher.acquire() as reader:
                self.assertEqual(reader.generation, current)
            self.assertEqual((s.publisher.directory / 'current.json').read_bytes(), pointer)
            # Reset last_future to a completed identical-frontier future.
            current = s.publish().result()
        s.publisher._fault = None
        completed = s.drain()['completed']
        self.assertIn('d', completed)
        self.assertTrue(s.last_future.result().membership_revisions)

    def test_blocked_preparer_does_not_hold_reader_lock(self):
        s = self.make()
        s.ingest([('d', 'alpha')], embed)
        s.last_future.result()
        entered, unblock = threading.Event(), threading.Event()
        original = s.publisher._prepare
        def blocked(*args):
            entered.set()
            self.assertTrue(unblock.wait(5))
            return original(*args)
        s.publisher._prepare = blocked
        # Identical-frontier publishes dedup BEFORE preparation (no _prepare
        # call), so force a fresh frontier to exercise the blocked preparer.
        s.ingest([('d2', 'alpha two')], embed)
        future = s.last_future
        self.assertTrue(entered.wait(5))
        try:
            for _ in range(100):
                with s.publisher.acquire() as pin:
                    self.assertEqual(pin.facade.atom_count, 1)
                    self.assertEqual(len(pin.facade.pending_search([1.,0.,0.,0.])[0]), 1)
        finally:
            unblock.set()
        future.result()

    def test_repair_hook_rewrites_only_new_generation(self):
        fake = FakeMembershipRepair(self.tl)
        s = self.make(repair=fake)
        s.ingest([('a', 'alpha'), ('b', 'beta')], embed)
        s.last_future.result()
        s.drain()
        old = s.last_future.result()
        a, b = s.publisher.acquire(), s.publisher.acquire()
        try:
            report = s.drain(max_documents=0, repair_budget=1)
            new = s.last_future.result()
            self.assertEqual(report['repair']['processed'], 1)
            self.assertNotEqual(new.membership_revisions, old.membership_revisions)
            self.assertEqual(a.generation, old)
            self.assertEqual(b.generation, old)
            first = sorted(a.facade.leaves)[0]
            with s.publisher.acquire() as pin:
                self.assertNotEqual(a.facade.leaves[first]['members'], pin.facade.leaves[first]['members'])
            head = self.tl.pin()
            s.drain(max_documents=0, repair_budget=1)
            s.last_future.result()
            self.assertEqual(self.tl.pin(), head)  # fake re-run commit-free
            self.assertEqual(fake.calls, [1, 1])
        finally:
            a.release(); b.release()

    def test_incomplete_parent_union_rejected(self):
        s = self.make()
        s.ingest([('a', 'alpha'), ('b', 'beta')], embed)
        s.last_future.result(); s.drain(); old = s.last_future.result()
        h = read_seg_hierarchy(self.tl, self.tl.pin())
        pid, p = next(iter(h['parents'].items()))
        op = parent_op(pid, p['children'], [], p['descriptor'], 'bad-fixture',
                       lambda body,sid: prepare_artifact(self.tl.store, body, sid))
        self.tl.commit_batch([op])
        with self.assertRaisesRegex(RuntimeError, 'member union'):
            s.publish().result()
        with s.publisher.acquire() as pin:
            self.assertEqual(pin.generation, old)

    def test_restart_restores_published_frontier_and_drain_idempotence(self):
        s = self.make()
        s.ingest([('d', 'alpha')], embed); published = s.last_future.result()
        s.drain(); s.last_future.result()
        head = self.tl.pin()
        s.drain(); s.last_future.result()
        self.assertEqual(self.tl.pin(), head)
        latest = s.publisher.load_record()
        s.close(); self.services.remove(s)
        restarted = self.make()
        with restarted.publisher.acquire() as pin:
            self.assertEqual(pin.generation, latest)
        self.assertEqual(restarted.pending(), ())
        self.assertEqual(published.pin[2] + 2, latest.pin[2])

    def test_killed_writer_after_source_before_ack_resumes_once(self):
        s = self.make()
        s.ingest([('d', 'alpha')], embed); old = s.last_future.result()
        a, b = s.publisher.acquire(), s.publisher.acquire()
        s.close(); self.services.remove(s)
        self.tl.close(); self.tl = None
        marker = self.root / 'kill-marker'
        p = mp.get_context('spawn').Process(target=kill_writer,
                    args=(str(self.root/'store'),str(marker),'after_organize_before_ack'))
        p.start()
        try:
            deadline = time.monotonic() + 15
            while not marker.exists() and p.is_alive() and time.monotonic() < deadline:
                self.assertEqual(a.generation, old)
                self.assertEqual(len(b.facade.pending_search([1.,0.,0.,0.])[0]), 1)
                time.sleep(.005)
            self.assertTrue(marker.exists(), 'writer did not reach kill boundary')
            p.kill(); p.join(5)
            self.assertEqual(p.exitcode, -9)
            self.tl = TLStore(str(self.root/'store'))
            head = self.tl.pin()
            restarted = self.make()
            self.assertEqual(restarted.pending(), ('d',))
            self.assertEqual(restarted.drain()['completed'], ['d'])
            restarted.last_future.result()
            self.assertEqual(self.tl.pin(), head)  # no duplicate source commits
            self.assertEqual(restarted.pending(), ())
            self.assertEqual(a.generation, old)
            self.assertEqual(b.generation, old)
        finally:
            if p.is_alive():
                p.kill(); p.join(5)
            a.release(); b.release()

    def test_ingest_commit_enqueue_crash_window_reconciles(self):
        def fail(stage):
            if stage == 'after_ingest_before_enqueue':
                raise RuntimeError('ingest interruption')
        s = self.make(fault=fail)
        with self.assertRaisesRegex(RuntimeError, 'interruption'):
            s.ingest([('d', 'alpha')], embed)
        self.assertEqual(s.backlog()[0]['state'], 'waiting')
        s.close(); self.services.remove(s)
        restarted = self.make()
        self.assertEqual(restarted.pending(), ('d',))
        restarted.publish().result()
        with restarted.publisher.acquire() as pin:
            self.assertEqual(len(pin.facade.pending_search([1.,0.,0.,0.])[0]), 1)

    def _kill_at_marker(self, target, args, marker, anchors):
        child = mp.get_context('spawn').Process(target=target,args=args)
        child.start()
        try:
            deadline = time.monotonic()+15
            while not marker.exists() and child.is_alive() and time.monotonic()<deadline:
                for pin in anchors:
                    self.assertTrue(pin.facade.pending_search([1.,0.,0.,0.])[0])
                time.sleep(.005)
            self.assertTrue(marker.exists(),f'kill boundary missed ({child.exitcode})')
            child.kill(); child.join(5)
            self.assertEqual(child.exitcode,-9)
        finally:
            if child.is_alive():
                child.kill(); child.join(5)

    def test_kill_inside_organizer_after_committed_batch(self):
        s = self.make()
        s.ingest([('d',' '.join('alpha'+str(i) for i in range(450)))],embed)
        old = s.last_future.result()
        detached = s.detach_readers()
        a,b = detached.acquire(),detached.acquire()
        s.close(); self.services.remove(s)
        self.tl.close(); self.tl = None
        marker = self.root/'mid-batch-marker'
        try:
            self._kill_at_marker(kill_writer,(str(self.root/'store'),str(marker),
                                'after_source_batch_before_progress'),marker,(a,b))
            self.tl = TLStore(str(self.root/'store'))
            resumed = self.make()
            with resumed.publisher.acquire() as pin:
                self.assertEqual(pin.generation,old)  # incomplete source never became visible
            self.assertEqual(resumed.drain()['completed'],['d'])
            resumed.last_future.result()
            with resumed.publisher.acquire() as pin:
                for leaf in pin.facade.leaves.values():
                    self.assertEqual(len(leaf['members']),len(set(leaf['members'])))
                self.assertEqual(pin.facade.atom_count,3)
                self.assertTrue(pin.facade.guided('alpha',[1.,0.,0.,0.])[0])
            head = self.tl.pin()
            resumed.drain();resumed.last_future.result()
            self.assertEqual(self.tl.pin(),head)
        finally:
            a.release();b.release();detached.close()

    def test_kill_after_durable_pointer_restores_complete_new_generation(self):
        s = self.make()
        s.ingest([('d','alpha')],embed);old = s.last_future.result()
        detached = s.detach_readers()
        a,b = detached.acquire(),detached.acquire()
        s.close();self.services.remove(s)
        self.tl.close();self.tl=None
        marker=self.root/'pointer-marker'
        try:
            self._kill_at_marker(kill_publisher,(str(self.root/'store'),str(marker)),marker,(a,b))
            self.tl=TLStore(str(self.root/'store'))
            restarted=self.make()
            with restarted.publisher.acquire() as pin:
                self.assertEqual(pin.generation.parent_generation,old.generation_id)
                self.assertTrue(pin.generation.membership_revisions)
                self.assertEqual(pin.generation.pending_documents,())
                self.assertTrue(pin.facade.guided('alpha',[1.,0.,0.,0.])[0])
            self.assertEqual(a.generation,old)
            self.assertEqual(b.generation,old)
        finally:
            a.release();b.release();detached.close()

    def test_kill_with_unfinished_multibatch_document(self):
        # Forced no-join thresholds produce one leaf+parent per atom: enough
        # ops to cross the inherited ten-op source durability boundary.
        knobs = {'t_seg':2.0,'t_leaf':2.0,'t_parent':2.0}
        s=self.make(organize_kwargs=knobs)
        s.ingest([('long',' '.join('alpha'+str(i) for i in range(4500)))],embed)
        old=s.last_future.result()
        detached=s.detach_readers();a,b=detached.acquire(),detached.acquire()
        s.close();self.services.remove(s)
        self.tl.close();self.tl=None
        marker=self.root/'multibatch-marker'
        try:
            self._kill_at_marker(kill_writer,(str(self.root/'store'),str(marker),
                                'after_source_batch_before_progress',knobs),marker,(a,b))
            self.tl=TLStore(str(self.root/'store'))
            prefix=read_seg_hierarchy(self.tl,self.tl.pin())
            self.assertEqual(len(prefix['leaves'])+len(prefix['parents']),10)
            self.assertGreater(len(prefix['leaves']),0)
            self.assertLess(len(prefix['leaves']),a.facade.atom_count)
            resumed=self.make(organize_kwargs=knobs)
            with resumed.publisher.acquire() as pin:
                self.assertEqual(pin.generation,old)
                self.assertEqual(len(pin.facade.leaves),0)
            resumed.drain();resumed.last_future.result()
            with resumed.publisher.acquire() as pin:
                self.assertEqual(len(pin.facade.leaves),pin.facade.atom_count)
                self.assertEqual(len(pin.facade.parents),pin.facade.atom_count)
                children={c for p in pin.facade.parents.values() for c in p['children']}
                self.assertEqual(children,set(pin.facade.leaves))
            head=self.tl.pin()
            resumed.drain();resumed.last_future.result()
            self.assertEqual(self.tl.pin(),head)
        finally:
            a.release();b.release();detached.close()

    def test_background_writer_and_zero_budget(self):
        s = self.make()
        s.ingest([('d', 'alpha')], embed); s.last_future.result()
        head = self.tl.pin()
        self.assertEqual(s.drain(budget_seconds=0)['attempted'], 0)
        s.last_future.result(); self.assertEqual(self.tl.pin(), head)
        s.start()
        deadline = time.monotonic() + 10
        while s.pending() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertEqual(s.pending(), ())
        self.assertIsNone(s.last_error)

    def test_publisher_ownership_and_rewind_fail_closed(self):
        s = self.make()
        s.ingest([('d', 'alpha')], embed); old = s.last_future.result()
        with self.assertRaisesRegex(RuntimeError, 'already has'):
            GenerationPublisher(self.tl, s.publisher.directory)
        s.drain(); latest = s.last_future.result()
        with self.assertRaisesRegex(RuntimeError, 'rewound'):
            s.publisher.submit(old.pin).result()
        foreign = ('other-birth', latest.pin[1], latest.pin[2], 'other-birth:0:1')
        with self.assertRaises(Exception):
            s.publisher.submit(foreign).result()
        with s.publisher.acquire() as pin:
            self.assertEqual(pin.generation, latest)


class FlagOffIdentity(unittest.TestCase):
    def test_original_source_bytes_unchanged(self):
        # Combined-fork adaptation: repair seam touches 7 files and both
        # seams add new modules; everything else must stay byte-identical
        # to the selected upstream source.
        # Stack-fork adaptation (fix-1+2+3+5+6): generation.py joins the
        # changed set (fix-2 suffix verify + fix-5 GC hook; view.py was
        # already in it for the fix-2 lock split) and gen_gc.py joins the
        # added set (fix-5 module). Guard logic below is untouched: any
        # file outside these sets must still match upstream byte-for-byte.
        source = Path('/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace-architecture')
        local = Path(__file__).resolve().parents[1]/'fork'
        changed = {'tl-sys/tlsys/index.py', 'tl-sys/tlsys/place.py',
                   'tl-sys/tlsys/proj.py', 'tl-sys/tlsys/serving/segments.py',
                   'tl-sys/tlsys/serving/view.py',
                   'tl-sys/tlsys/store_if.py', 'tl-sys/tlsys/ingest.py', 'tl-sys/tlsys/maint.py',
                   'tl-sys/tlsys/serving/generation.py'}
        added = {'tl-sys/tlsys/local_repair.py', 'tl-sys/tlsys/repair_metrics.py',
                 'tl-sys/tlsys/org_publication.py', 'tl-sys/tlsys/org_service.py',
                 'tl-sys/tlsys/repair_hook.py', 'tl-sys/tlsys/serving/gen_gc.py'}
        frozen = json.loads((Path(__file__).resolve().parents[1]/'SOURCEFREEZE.json').read_text())['files']
        import hashlib
        for rel in sorted(changed | added):
            key = 'fork/'+rel
            self.assertEqual(hashlib.sha256((local/rel).read_bytes()).hexdigest(), frozen[key], key)
        count = 0
        for old, new in ((source/'tl-sys/tlsys',local/'tl-sys/tlsys'),
                         (source/'tl-candidate-batch/candidate',local/'tl-candidate-batch/candidate')):
            for file in old.rglob('*.py'):
                rel = 'tl-sys/tlsys/'+str(file.relative_to(old)) if 'tlsys' in str(old) else \
                    'tl-candidate-batch/candidate/'+str(file.relative_to(old))
                if rel in changed:
                    continue
                self.assertEqual(file.read_bytes(), (new/file.relative_to(old)).read_bytes(), str(file))
                count += 1
        self.assertGreater(count, 50)
        for rel in added:
            self.assertTrue((local/rel).exists(), rel)

    def test_disabled_wrapper_byte_identity(self):
        base = Path(tempfile.mkdtemp(prefix='publish-off-diff-'))
        root = base/'store'
        tl = TLStore(str(root), create=True)
        lockname = Path(tl.store.lock_path).name
        tl.close()
        shutil.copytree(root,base/'seed')
        stamp = time.time()
        def run(wrapper):
            code = '''
import random,sys,uuid
from unittest.mock import patch
from tlsys.store_if import TLStore
from tlsys.org_service import OrganizationService
from tlsys.ingest import ingest_docs
from tlsys.maint import organize_segments
random.seed(20261011)
embed=lambda ts:[[1.,0.,0.,0.] for _ in ts]
with patch('time.time',return_value=float(sys.argv[2])), patch('uuid.uuid4',side_effect=lambda:uuid.UUID(int=random.getrandbits(128))):
    tl=TLStore(sys.argv[1],lease_owner='publish-off-diff')
    if sys.argv[3]=='True':
        off=OrganizationService(tl)
        assert not off.directory.exists()
        off.ingest([('d','alpha text')],embed)
        assert off.drain()=={'enabled':False,'attempted':0}
        off.close()
    else:
        ingest_docs(tl,[('d','alpha text')],embed)
    organize_segments(tl)
    tl.close()
'''
            subprocess.run([sys.executable,'-B','-c',code,str(root),str(stamp),str(wrapper)], check=True)
            return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
        direct = run(False)
        root.rename(base/'direct-result')
        shutil.copytree(base/'seed',root)
        # Fence binds the original inode; preserve it through a hard link.
        (root/lockname).rename(base/'copied-lock-preserved')
        os.link(base/'direct-result'/lockname, root/lockname)
        disabled = run(True)
        self.assertEqual(direct.keys(), disabled.keys())
        for path in direct:
            self.assertEqual(direct[path],disabled[path], path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
