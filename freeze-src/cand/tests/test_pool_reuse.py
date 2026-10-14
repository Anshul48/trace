"""Native pin/lifecycle parity tests for isolated opt-in ViewPool reuse."""
import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tlsys.org_publication import GenerationPublisher, PreparedFacade
from tlsys.org_service import OrganizationService, ServiceConfig
from tlsys.index import NarrowIndex
from tlsys.serving.view import ViewPool
from tlsys.store_if import TLStore
from test_publication import embed, FakeMembershipRepair, PublicationTests

class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='reuse-native-'))
        self.tl = TLStore(str(self.root/'store'), create=True)
        self.services=[]; self.publishers=[]
    def tearDown(self):
        for s in self.services: s.close()
        for p in self.publishers: p.close()
        self.tl.close()
    def service(self):
        s=OrganizationService(self.tl,config=ServiceConfig(enabled=True,
            drain_budget_seconds=30,reuse_view_pool=True))
        self.services.append(s);return s
    def assert_cold_parity(self,reader):
        g=reader.generation
        cold=PreparedFacade(self.tl,g.pin,g.pending_documents)
        try:
            self.assertEqual(reader.facade.membership_revisions,cold.membership_revisions)
            self.assertEqual(reader.facade.leaves,cold.leaves)
            self.assertEqual(reader.facade.parents,cold.parents)
            for v in ([1.,0.,0.,0.],[0.,1.,0.,0.],[1.,1.,0.,0.]):
                for method in ('guided','search'):
                    a=getattr(reader.facade,method)('alpha',v)[0]
                    b=getattr(cold,method)('alpha',v)[0]
                    self.assertEqual(a,b)
                self.assertEqual(reader.facade.pending_search(v),cold.pending_search(v))
        finally: cold.close()
    def test_retained_old_pins_advances_repair_and_cold_parity(self):
        s=self.service();s.ingest([('d1','alpha one'),('d2','beta two')],embed);s.last_future.result()
        old=s.publisher.acquire(); pool=old.facade._index._pool; oldview=old.facade._index._view
        try:
            self.assert_cold_parity(old)
            for i in range(2):
                s.drain(max_documents=1,budget_seconds=30);s.last_future.result()
                with s.publisher.acquire() as current:
                    self.assertIs(current.facade._index._pool,pool)
                    self.assertIsNot(current.facade._index._view,oldview)
                    self.assert_cold_parity(current)
                self.assert_cold_parity(old)
            s.ingest([('d3','alpha three')],embed);s.last_future.result()
            s.drain(max_documents=1,budget_seconds=30);s.last_future.result()
            FakeMembershipRepair(self.tl).repair_step(1)
            s.publish().result()
            with s.publisher.acquire() as current: self.assert_cold_parity(current)
            self.assert_cold_parity(old);self.assertEqual(old.facade.atom_count,2)
            # Retire acknowledged pending source (no hierarchy rewrite needed).
            s.ingest([('d4','beta four')],embed);s.last_future.result()
            before_retire=s.publisher.acquire()
            from tlsys.lifecycle import retire_docs
            retire_docs(self.tl,['d4'],approvals={'d4':{'type':'user','approval_id':'reuse-test'}})
            s.publish().result()
            try:
                self.assert_cold_parity(before_retire)
                with s.publisher.acquire() as current: self.assert_cold_parity(current)
                self.assert_cold_parity(old)
            finally:before_retire.release()
        finally:old.release()
    def test_same_head_pending_and_dedup(self):
        s=self.service();s.ingest([('d1','alpha one')],embed);g=s.last_future.result()
        old=s.publisher.acquire();pool=old.facade._index._pool;view=old.facade._index._view
        try:
            g1=s.publisher.submit(g.pin,()).result()
            self.assertNotEqual(g1.generation_id,g.generation_id)
            with s.publisher.acquire() as current:
                self.assertIs(current.facade._index._view,view)
                self.assertEqual(current.facade.pending_search([1,0,0,0])[0],[])
                self.assert_cold_parity(current)
            self.assertEqual(len(old.facade.pending_search([1,0,0,0])[0]),1)
            with patch.object(s.publisher,'_prepare',side_effect=AssertionError('must dedup')):
                self.assertEqual(s.publisher.submit(g.pin,()).result(),g1)
            self.assertIs(s.publisher._view_pool,pool)
        finally:old.release()
    def test_prepare_failure_and_source_binding_tamper_pointer_unchanged(self):
        s=self.service();s.ingest([('d1','alpha one')],embed);s.last_future.result()
        pointer=(s.publisher.directory/'current.json').read_bytes();old=s.publisher.acquire()
        try:
            def fail(stage):
                if stage=='after_prepare': raise RuntimeError('prepare fault')
            s.publisher._fault=fail
            s.ingest([('d2','beta two')],embed)
            with self.assertRaisesRegex(RuntimeError,'prepare fault'):s.last_future.result()
            self.assertEqual((s.publisher.directory/'current.json').read_bytes(),pointer)
            self.assert_cold_parity(old);s.publisher._fault=None
            s.drain(max_documents=2,budget_seconds=30);s.last_future.result()
            pointer=(s.publisher.directory/'current.json').read_bytes()
            original=s.publisher._prepare
            def tamper(tl,pin,pending):
                facade=original(tl,pin,pending)
                # Self-consistent ghost source snapshot must still fail actual source binding.
                lid=next(iter(facade.leaves));leaf=dict(facade.leaves[lid]);leaf['descriptor']=(0.,0.,1.,0.)
                facade.leaves={**facade.leaves,lid:leaf}
                import hashlib
                from tlsys.org_publication import MembershipRevision,canonical
                digest=hashlib.sha256(canonical({'members':list(leaf['members']),
                    'children':list(leaf.get('children',[])),'descriptor':list(leaf['descriptor'])})).hexdigest()
                facade.membership_revisions=tuple(MembershipRevision(r.holon_id,r.commit_seq,digest)
                    if r.holon_id==lid else r for r in facade.membership_revisions)
                return facade
            s.publisher._prepare=tamper
            with self.assertRaisesRegex(RuntimeError,'differ from pinned source'):
                s.publisher.submit(self.tl.pin(),('changed-pending',)).result()
            self.assertEqual((s.publisher.directory/'current.json').read_bytes(),pointer)
            s.publisher._prepare=original
        finally:old.release()
    def test_detach_restart_anchor_release_and_outliving_close(self):
        s=self.service();s.ingest([('d1','alpha one')],embed);s.last_future.result()
        old=s.publisher.acquire();pool=old.facade._index._pool;view=old.facade._index._view
        detached=s.detach_readers();self.publishers.append(detached)
        self.assertIsNone(detached._pool_anchor);self.assertIsNone(detached._view_pool)
        self.assertEqual(view._refs,1)
        replacement=self.service()
        with replacement.publisher.acquire() as current:
            self.assertIsNot(current.facade._index._pool,pool)
            self.assertEqual(current.generation,old.generation);self.assert_cold_parity(current)
        replacement.ingest([('d2','beta two')],embed);replacement.last_future.result()
        detached.close();self.assert_cold_parity(old)
        old.release();self.assertEqual(view._refs,0)
    def test_shared_samepin_mapping_mutators_and_advance_refused(self):
        s=self.service();s.ingest([('d1','alpha one')],embed);g=s.last_future.result()
        old=s.publisher.acquire()
        try:
            s.publisher.submit(g.pin,()).result()
            with s.publisher.acquire() as current:
                a=old.facade._index;b=current.facade._index
                self.assertIs(a._view,b._view)
                aid=next(iter(a.atoms));before=dict(b.atoms[aid])
                import numpy as _np2
                def _same_row(r1,r2):
                    if set(r1)!=set(r2):return False
                    for k in r1:
                        v1,v2=r1[k],r2[k]
                        if isinstance(v1,_np2.ndarray) or isinstance(v2,_np2.ndarray):
                            if not _np2.array_equal(_np2.asarray(v1),_np2.asarray(v2)):return False
                        elif isinstance(v1,float) and isinstance(v2,float):
                            if v1!=v2:return False
                        else:
                            try:
                                if v1!=v2:return False
                            except ValueError:
                                if not _np2.array_equal(_np2.asarray(v1),_np2.asarray(v2)):return False
                    return True
                for operation in (lambda:a.atoms.__setitem__(aid,{}),
                    lambda:a.atoms.__delitem__(aid),lambda:a.atoms.pop(aid),
                    lambda:a.atoms.popitem(),lambda:a.atoms.clear(),
                    lambda:a.atoms.update({aid:{}}),lambda:a.atoms.setdefault('ghost',{})):
                    with self.assertRaisesRegex(TypeError,'read-only'):operation()
                    # Value comparison: rows are now independent copies, so
                    # plain assertEqual would compare array identities.
                    self.assertTrue(_same_row(dict(b.atoms[aid]),before))
                with self.assertRaisesRegex(RuntimeError,'fixed'):a.advance_to(g.pin)
                self.assert_cold_parity(old);self.assert_cold_parity(current)
        finally:old.release()

    def test_foreign_rewind_and_custom_factory_compatibility(self):
        s=self.service();s.ingest([('d1','alpha one')],embed);g=s.last_future.result()
        s.drain(max_documents=1,budget_seconds=30);s.last_future.result()
        for pin in (g.pin,('foreign',*g.pin[1:])):
            with self.assertRaisesRegex(RuntimeError,'foreign incarnation or rewound'):
                s.publisher.submit(pin).result()
        calls=[]
        def custom(tl,pin,pending):calls.append((tl,pin,pending));return PreparedFacade(tl,pin,pending)
        p=GenerationPublisher(self.tl,self.root/'custom',prepare=custom,reuse_view_pool=True)
        self.publishers.append(p);p.submit(self.tl.pin()).result();self.assertEqual(len(calls),1)
        self.assertFalse(p.reuse_view_pool);self.assertIsNone(p._view_pool)
        wrong=ViewPool(self.tl,'foreign',0)
        with self.assertRaisesRegex(ValueError,'different source incarnation'):
            NarrowIndex(self.tl,self.tl.pin(),view_pool=wrong,use_reference=False)
    def test_shared_nested_row_mutation_isolated(self):
        """Same-pin shared rows are copies: caller mutation must not leak."""
        s=self.service();s.ingest([('d1','alpha one'),('d2','beta two')],embed)
        g=s.last_future.result();s.publisher.submit(g.pin,()).result()
        old=s.publisher.acquire()
        try:
            with s.publisher.acquire() as cur:
                self.assertIs(old.facade._index._view,cur.facade._index._view)
                aid=next(iter(old.facade._index.atoms))
                row=old.facade._index.atoms[aid]
                row['descriptor']=(9.,9.,9.,9.)
                nested=row.get('span')
                if isinstance(nested,list): nested.append(99999)
                # Sibling facade sharing the pin must be unaffected.
                import numpy as _np
                sib=dict(cur.facade._index.atoms[aid])
                self.assertFalse(_np.array_equal(
                    _np.asarray(sib.get('descriptor'),dtype=float),
                    _np.asarray((9.,9.,9.,9.),dtype=float)))
                if isinstance(nested,list):
                    self.assertNotIn(99999,sib.get('span',()))
                self.assert_cold_parity(old);self.assert_cold_parity(cur)
        finally:old.release()
    def test_retained_reader_correct_during_blocked_prepare(self):
        """Mechanism test (manufactured delay, NOT a latency measurement):
        prepare advance holds the shared pool lock, so an old retained
        reader's query waits; its results must still be pin-correct."""
        import threading,time
        from tlsys.serving import view as view_mod
        s=self.service();s.ingest([('d1','alpha one'),('d2','beta two')],embed)
        s.last_future.result()
        old=s.publisher.acquire()
        try:
            before=old.facade.guided('alpha',[1.,0.,0.,0.])[0]
            started=threading.Event()
            orig_adv=view_mod.ViewPool._advance_locked
            orig_gen=view_mod.ViewPool._advance_gen_locked
            orig_pre=view_mod.ViewPool._advance_prefetched_locked
            def slow_adv(self2,base,pin):
                started.set();time.sleep(3.0);return orig_adv(self2,base,pin)
            def slow_gen(self2,base,pin):
                started.set();time.sleep(3.0);return orig_gen(self2,base,pin)
            def slow_pre(self2,base,pin,lo,prefetched):
                started.set();time.sleep(3.0);return orig_pre(self2,base,pin,lo,prefetched)
            with patch.object(view_mod.ViewPool,'_advance_locked',slow_adv),\
                 patch.object(view_mod.ViewPool,'_advance_gen_locked',slow_gen),\
                 patch.object(view_mod.ViewPool,'_advance_prefetched_locked',slow_pre):
                s.ingest([('d3','alpha three')],embed)
                self.assertTrue(started.wait(timeout=60))
                t0=time.monotonic()
                during=old.facade.guided('alpha',[1.,0.,0.,0.])[0]
                elapsed=time.monotonic()-t0
                s.last_future.result()
            # Reader serialized behind the lock-holding advance (mechanism),
            # but still served its own pin correctly.
            self.assertGreaterEqual(elapsed,2.5)
            self.assertEqual(during,before)
            self.assert_cold_parity(old)
            with s.publisher.acquire() as cur:
                self.assert_cold_parity(cur)
        finally:old.release()
    def test_off_default_and_custom_publisher_factory(self):
        self.assertFalse(ServiceConfig().reuse_view_pool)
        calls=[]
        def factory(tl,directory):calls.append(directory);return GenerationPublisher(tl,directory)
        s=OrganizationService(self.tl,config=ServiceConfig(enabled=True,reuse_view_pool=True),
                              publisher_factory=factory)
        self.services.append(s);s.ingest([('d1','alpha one')],embed);s.last_future.result()
        self.assertEqual(len(calls),1);self.assertFalse(s.publisher.reuse_view_pool)

class ExistingPublicationReuseTests(PublicationTests):
    """All inherited native publication fixtures using explicit opt-in services."""
    def make(self,**kwargs):
        s=OrganizationService(self.tl,config=ServiceConfig(enabled=True,
            drain_budget_seconds=30,reuse_view_pool=True),**kwargs)
        self.services.append(s);return s

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
                self.assertIs(c.facade._index._pool, a.facade._index._pool)
                self.assertIsNot(c.facade._index._view, a.facade._index._view)
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


del PublicationTests  # Avoid discovering the imported baseline class twice.

if __name__=='__main__':unittest.main(verbosity=2)
