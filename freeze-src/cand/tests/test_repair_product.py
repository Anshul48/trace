import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fork/tl-sys'))
import numpy as np
from tlsys.store_if import TLStore
from tlsys.ingest import ingest_docs
from tlsys.maint import organize_segments
from tlsys.local_repair import RepairConfig,canonical
from tlsys.index import NarrowIndex
from tlsys.query import HierQuery
from tlsys.lifecycle import retire_docs
from tlsys.proj import Projections


def emb(texts):
    vs=[]
    for t in texts:
        v=np.zeros(384);v[0 if 'sport' in t else 1]=1;vs.append(v.tolist())
    return vs


class ProductTests(unittest.TestCase):
    def build(self):
        root=tempfile.mkdtemp(prefix='repair-product-')
        tl=TLStore(os.path.join(root,'store'),create=True,local_repair=True,
                   repair_config=RepairConfig(edge_threshold=.8))
        docs=[('sport-a','sport one two'),('sport-b','sport three four'),('med-a','medicine four five')]
        ingest_docs(tl,docs,emb,place_xdoc=False)
        # Deliberate source-compatible pressure: mixed children in one parent
        # must split at the independent repair threshold .8.
        organize_segments(tl,t_parent=-1)
        return tl,docs

    def test_joins_revisions_retirements_enqueue(self):
        tl,docs=self.build()
        try:
            self.assertGreater(len(tl.local_repair.engine.queue),0)
            tl.local_repair.repair_step(10**8)
            ingest_docs(tl,[('sport-c','sport late append')],emb,place_xdoc=False);organize_segments(tl)
            self.assertTrue(tl.local_repair.engine.queue)
            tl.local_repair.repair_step(10**8)
            retire_docs(tl,['sport-a'],approvals={'sport-a':{'type':'user','approval_id':'TEST-FIXTURE-repair'}})
            self.assertTrue(tl.local_repair.engine.queue)
            tl.local_repair.repair_step(10**8)
            self.assertFalse(tl.local_repair.engine.queue)
        finally:tl.close()

    def test_pinned_reference_segmented_parity(self):
        tl,docs=self.build()
        try:
            oldpin=tl.pin();refold=NarrowIndex(tl,oldpin,use_reference=True)
            segold=NarrowIndex(tl,oldpin,use_reference=False)
            before=canonical({k:list(v['children']) for k,v in segold.seg_parents.items()})
            tl.local_repair.repair_step(10**8)
            pin=tl.pin();ref=NarrowIndex(tl,pin,use_reference=True);seg=NarrowIndex(tl,pin,use_reference=False)
            self.assertEqual(len(refold.seg_parents),1)
            self.assertEqual(len(ref.seg_parents),2)
            for attr in ('seg_leaves','seg_parents'):
                ra=getattr(ref,attr);sa=getattr(seg,attr)
                self.assertEqual(set(ra),set(sa))
                for hid in ra:
                    self.assertEqual(ra[hid]['members'],sa[hid]['members'])
                    self.assertEqual(ra[hid].get('children'),sa[hid].get('children'))
                    np.testing.assert_array_equal(ra[hid]['descriptor'],sa[hid]['descriptor'])
            self.assertEqual(before,canonical({k:list(v['children']) for k,v in segold.seg_parents.items()}))
            for idx in (refold,segold,ref,seg):
                rows,r=HierQuery(tl,idx,lambda q:emb([q])[0]).guided('sport')
                self.assertTrue(rows)
            for idx in (refold,segold,ref,seg):
                if hasattr(idx,'release'):idx.release()
        finally:tl.close()

    def test_independent_old_pinned_reader_during_split(self):
        import threading
        tl,docs=self.build()
        try:
            index=NarrowIndex(tl,tl.pin(),use_reference=False)
            query=HierQuery(tl,index,lambda q:emb([q])[0])
            expected=canonical(query.guided('sport'))
            started=threading.Event();done=threading.Event();errors=[];reads=[]
            def reader():
                started.set()
                try:
                    for _ in range(30):reads.append(canonical(query.guided('sport')))
                except BaseException as exc:errors.append(str(exc))
                finally:done.set()
            thread=threading.Thread(target=reader);thread.start();started.wait(10)
            tl.repair_step(10**8)
            thread.join(10)
            self.assertTrue(done.is_set());self.assertFalse(errors)
            self.assertEqual(reads,[expected]*30)
            self.assertGreater(tl.local_repair.engine.counts['parent_split'],0)
            if hasattr(index,'release'):index.release()
        finally:tl.close()

    def test_commit_failure_no_membership_or_queue_change(self):
        tl,docs=self.build()
        try:
            e=tl.local_repair.engine;before=canonical(e.snapshot());pin=tl.pin()
            original=tl.cm.commit_batch
            tl.cm.commit_batch=lambda ops:([{'status':'raised','code':'INJECTED'}],{})
            with self.assertRaises(RuntimeError):tl.local_repair.repair_step(10**8)
            self.assertEqual(before,canonical(e.snapshot()));self.assertEqual(pin,tl.pin())
            tl.cm.commit_batch=original;tl.local_repair.repair_step(10**8)
        finally:tl.close()

    def test_commit_before_apply_recovery(self):
        tl,docs=self.build()
        try:
            e=tl.local_repair.engine;original=e.apply;calls=[0]
            def fail_once(record):
                calls[0]+=1
                if calls[0]==1:raise RuntimeError('injected commit-before-apply')
                original(record)
            e.apply=fail_once
            with self.assertRaises(RuntimeError):tl.local_repair.repair_step(10**8)
            self.assertEqual(e.generation,1) # finally sync adopted committed record
            e.apply=original;tl.local_repair.repair_step(10**8)
            before=canonical(e.snapshot());tl.local_repair.sync()
            self.assertEqual(before,canonical(e.snapshot()))
        finally:tl.close()

    def test_serialized_queue_replay(self):
        tl,docs=self.build();root=tl.store.root
        before=canonical(tl.local_repair.snapshot())
        tl.close();tl=TLStore(root,local_repair=True,repair_config=RepairConfig(edge_threshold=.8))
        try:self.assertEqual(before,canonical(tl.local_repair.snapshot()))
        finally:tl.close()

    def test_real_core_capacity_refusal_rollback(self):
        tl,docs=self.build()
        try:
            e=tl.local_repair.engine;before=canonical(e.snapshot());pin=tl.pin()
            # Real owning core admission refusal, rather than a mocked writer.
            tl.cm.caps['max_delta_entries']=0
            with self.assertRaises(RuntimeError):tl.repair_step(10**8)
            self.assertEqual(pin,tl.pin())
            self.assertEqual(before,canonical(e.snapshot()))
        finally:tl.close()

    def test_prepared_retry_payload_identity(self):
        tl,docs=self.build()
        try:
            captured=[];original=tl.cm.commit_batch
            def reject(ops):
                captured.append(ops[0])
                return [{'status':'retryable','message':'INJECTED'}],{}
            tl.cm.commit_batch=reject
            for _ in range(2):
                with self.assertRaises(RuntimeError):tl.repair_step(10**8)
            self.assertEqual(captured[0]['op_id'],captured[1]['op_id'])
            self.assertEqual(captured[0]['payload'],captured[1]['payload'])
            self.assertEqual(captured[0]['artifacts'],captured[1]['artifacts'])
            tl.cm.commit_batch=original;tl.repair_step(10**8)
        finally:tl.close()

    def test_complete_bytes_fsync_failure_then_retry(self):
        from unittest.mock import patch
        tl,docs=self.build()
        try:
            e=tl.local_repair.engine;before=canonical(e.snapshot());pin=tl.pin()
            with patch('tlsys.local_repair.os.fsync',side_effect=OSError('injected fsync failure')):
                with self.assertRaises(OSError):tl.repair_step(10**8)
            self.assertEqual(before,canonical(e.snapshot()));self.assertEqual(pin,tl.pin())
            original=tl.cm.commit_batch;real_fsync=os.fsync;calls=[]
            def seal(fd):calls.append(fd);return real_fsync(fd)
            tl.cm.commit_batch=lambda ops:([{'status':'retryable','message':'INJECTED'}],{})
            with patch('tlsys.local_repair.os.fsync',side_effect=seal):
                with self.assertRaises(RuntimeError):tl.repair_step(10**8)
            self.assertEqual(len(calls),2) # reused artifact and parent directory
            self.assertEqual(before,canonical(e.snapshot()));self.assertEqual(pin,tl.pin())
            tl.cm.commit_batch=original;tl.repair_step(10**8)
        finally:tl.close()

if __name__=='__main__':unittest.main(verbosity=2)
