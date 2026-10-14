import copy
import json
import os
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fork', 'tl-sys'))
import numpy as np
from tlsys.local_repair import RepairConfig, RepairEngine, partition, canonical
from tlsys.repair_metrics import metrics

D = 384

def v(i, sign=1):
    a = np.zeros(D); a[i] = sign
    return a.tolist()


def fixture(n=6):
    vectors = {f'a{i}': v(0 if i < n//2 else 1) for i in range(n)}
    leaves = {f'xseg-l{i}': {'members': [f'a{i}'], 'descriptor': vectors[f'a{i}'], 'segments': []} for i in range(n)}
    mean = np.mean(list(vectors.values()), axis=0).tolist()
    parents = {'xpar-p': {'children': sorted(leaves), 'members': sorted(vectors), 'descriptor': mean}}
    return vectors, leaves, parents


def engine(n=6, **kw):
    vs, ls, ps = fixture(n)
    e = RepairEngine(vs, ls, ps, RepairConfig(enabled=True, **kw))
    return e


class RepairTests(unittest.TestCase):
    def assert_valid(self, e):
        m = metrics(e)
        self.assertEqual((m['orphan_children'], m['duplicate_edges'], m['dangling_edges'], m['parent_union_mismatches']), (0,0,0,0))
        self.assertLessEqual(m['parent_occupancy']['max'], 16)
        self.assertLessEqual(m['leaf_occupancy']['max'], 25)

    def test_default_off(self):
        vs, ls, ps = fixture()
        e = RepairEngine(vs, ls, ps)
        before = canonical(e.snapshot())
        e.touch(ls)
        self.assertEqual(e.repair_step(10**8)['spent'], 0)
        self.assertEqual(before, canonical(e.snapshot()))

    def test_queue_dedup_and_snapshot_resume(self):
        e = engine(); e.touch(['xseg-l2','xseg-l0']); e.touch(['xseg-l0'])
        self.assertEqual(list(e.queue), [('leaf','xseg-l0'), ('leaf','xseg-l2'), ('parent','xpar-p')])
        restored = RepairEngine.restore(json.loads(canonical(e.snapshot())), e.vectors)
        self.assertEqual(canonical(e.snapshot()), canonical(restored.snapshot()))

    def test_budget_no_partial(self):
        e = engine(); e.touch(parent_ids=['xpar-p'])
        before = canonical(e.snapshot())
        self.assertEqual(e.repair_step(e._estimate(('parent','xpar-p'))-1)['spent'], 0)
        self.assertEqual(before, canonical(e.snapshot()))

    def test_parent_split(self):
        e = engine(edge_threshold=.8); e.touch(parent_ids=['xpar-p'])
        e.repair_step(10**8)
        self.assertEqual(e.counts['parent_split'], 1)
        self.assert_valid(e)
        self.assertEqual(sorted(len(p['children']) for p in e.parents.values()), [3,3])

    def test_capacity_parent_split(self):
        e = engine(n=17); e.touch(parent_ids=['xpar-p']); e.repair_step(10**8)
        self.assert_valid(e)
        self.assertEqual(e.counts['parent_split'], 1)

    def test_leaf_split_full_parent(self):
        e = engine(16)
        aids = [f'new{i}' for i in range(26)]
        e.vectors.update({a:v(0) for a in aids})
        e.observe_leaf('xseg-l0', {'members':aids, 'descriptor':v(0), 'segments':[]})
        e.repair_step(10**8)
        self.assert_valid(e)
        self.assertEqual(e.counts['leaf_split'], 1)

    def test_leaf_incoherent_split(self):
        e = engine(2)
        e.observe_leaf('xseg-l0', {'members':['a0','a1'], 'descriptor':v(0), 'segments':[]})
        e2 = RepairEngine.restore(e.snapshot(), e.vectors)
        # .707 mean cohesion is below an explicit .8 drift threshold.
        from dataclasses import replace
        e2.config = replace(e2.config, leaf_threshold=.8)
        e2.repair_step(10**8)
        self.assert_valid(e2)
        self.assertGreater(e2.counts['leaf_split'], 0)

    def test_reassignment(self):
        e = engine(6, edge_threshold=.8)
        e.observe_parent('xpar-q', {'children':['xseg-l3'], 'members':['a3'], 'descriptor':v(1)})
        e.touch(parent_ids=['xpar-p']); e.repair_step(10**8)
        self.assertGreater(e.counts['reassigned'], 0)
        self.assert_valid(e)

    def test_retire(self):
        e = engine(); e.retire_atoms(['a0']); e.repair_step(10**8)
        self.assertNotIn('a0', e.leaves['xseg-l0']['members'])
        self.assertIn('a0', e.vectors)
        self.assert_valid(e)

    def test_failure_rollback(self):
        e = engine(edge_threshold=.8); e.touch(parent_ids=['xpar-p'])
        before = canonical(e.snapshot())
        def fail(record): raise RuntimeError('injected')
        e.commit = fail
        with self.assertRaises(RuntimeError): e.repair_step(10**8)
        self.assertEqual(before, canonical(e.snapshot()))

    def test_determinism_idempotence(self):
        e = engine(edge_threshold=.8); e.touch(parent_ids=['xpar-p'])
        twin = RepairEngine.restore(e.snapshot(), copy.deepcopy(e.vectors))
        e.repair_step(10**8); twin.repair_step(10**8)
        self.assertEqual(canonical(e.snapshot()), canonical(twin.snapshot()))
        before = canonical(e.snapshot()); e.repair_step(10**8)
        self.assertEqual(before, canonical(e.snapshot()))

    def test_degenerate_partition(self):
        cfg=RepairConfig(enabled=True)
        for vec in (v(0), [0.0]*D):
            ids=[str(i) for i in range(26)]
            parts=partition(ids,{i:vec for i in ids},25,cfg)
            self.assertTrue(parts[0] and parts[1])
            self.assertEqual(sorted(parts[0]+parts[1]), sorted(ids))
            self.assertLessEqual(max(map(len,parts)),25)
        self.assertIsNone(partition(['a'],{'a':v(0)},25,cfg))

    def test_infeasible_debt(self):
        e=engine(n=33); e.touch(parent_ids=['xpar-p'])
        before=canonical(e.snapshot())
        r=e.repair_step(10**8)
        self.assertEqual(r['blocked'],'infeasible-local-two-way-split')
        self.assertEqual(before,canonical(e.snapshot()))

    def test_observed_work_within_budget(self):
        e=engine(edge_threshold=.8)
        e.touch(parent_ids=['xpar-p'])
        receipt=e.repair_step(10**8)
        rows=e.counts['member_rows']+e.counts['cosine_rows']
        self.assertGreater(rows,0)
        self.assertLessEqual(rows*D,receipt['spent'])
        self.assertLessEqual(receipt['spent'],10**8)

    def test_latest_record_replay_idempotent(self):
        e=engine(edge_threshold=.8);records=[]
        e.commit=lambda record:records.append(copy.deepcopy(record))
        e.touch(parent_ids=['xpar-p']);e.repair_step(10**8)
        before=canonical(e.snapshot())
        e.apply(records[-1])
        self.assertEqual(before,canonical(e.snapshot()))
        restored=RepairEngine.restore(json.loads(before),e.vectors)
        restored.apply(records[-1])
        self.assertEqual(before,canonical(restored.snapshot()))

    def test_no_unrelated_vector_scan(self):
        vs,ls,ps=fixture()
        # A large unrelated catalog has deliberately unavailable vectors.
        # Candidate limit zero permits only the touched neighborhood.
        for i in range(1000):
            lid=f'xseg-unused-{i}';pid=f'xpar-unused-{i}'
            ls[lid]={'members':[f'absent-{i}'],'descriptor':v(2),'segments':[]}
            ps[pid]={'children':[lid],'members':[f'absent-{i}'],'descriptor':v(2)}
        e=RepairEngine(vs,ls,ps,RepairConfig(enabled=True,candidate_limit=0,edge_threshold=.8))
        e.touch(parent_ids=['xpar-p']);e.repair_step(10**8)
        self.assertEqual(e.counts['parent_split'],1)
        self.assertEqual(len(e.parents),1002)

    def test_provenance_alignment_after_split(self):
        e=engine(2,leaf_threshold=.8)
        e.observe_leaf('xseg-l0',{'members':['a0','a1'],'descriptor':v(0),'segments':[
            {'doc':'d','aids':['a0','a1'],'spans':[[0,3],[4,8]],'byte_spans':[[0,3],[4,8]]}]})
        e.repair_step(10**8)
        for leaf in e.leaves.values():
            for seg in leaf['segments']:
                self.assertEqual(len(seg['aids']),len(seg['spans']))
                self.assertEqual(len(seg['aids']),len(seg['byte_spans']))

    def test_capacity_ties_and_zero_partition_bound(self):
        calls=[0]
        def score(a,b):
            calls[0]+=1
            return 0.0
        cfg=RepairConfig(enabled=True)
        ids=[f'a{i:02}' for i in range(26)]
        parts=partition(ids,{a:v(0) for a in ids},25,cfg,score)
        self.assertLessEqual(calls[0],16**2)
        self.assertTrue(parts[0] and parts[1])
        self.assertEqual(sorted(parts[0]+parts[1]),ids)

    def test_budget_chunking_same_generation_records(self):
        e=engine(edge_threshold=.8);e.touch(parent_ids=['xpar-p'])
        twin=RepairEngine.restore(e.snapshot(),e.vectors)
        e.repair_step(10**8)
        while twin.queue:
            cost=twin._estimate(next(iter(twin.queue)))
            r=twin.repair_step(cost)
            self.assertGreater(r['checked'],0)
        self.assertEqual(canonical(e.snapshot()),canonical(twin.snapshot()))

    def test_core_publication_and_restart(self):
        from tlsys.store_if import TLStore, prepare_artifact
        from tlsys.place import leaf_op, parent_op, read_seg_hierarchy
        from tlsys.proj import Projections
        root=tempfile.mkdtemp(prefix='repair-core-')
        tl=TLStore(os.path.join(root,'store'), create=True, local_repair=True,
                   repair_config=RepairConfig(edge_threshold=.8))
        vs, ls, ps=fixture()
        # Committed atoms through ordinary source operations (no encoder).
        from tlsys.identity import ATOM_SCHEME
        from tlsys.store_if import uuidv7
        prep=lambda body,sid:prepare_artifact(tl.store,body,sid)
        for a,vec in vs.items():
            art=prep(canonical({'atom':a,'descriptor':vec,'doc_id':'d','atom_scheme':ATOM_SCHEME}).encode(),'test')
            r,_=tl.commit_batch([{'op_id':uuidv7(),'kind':'ACCEPT_ATOMS','payload':{'meta_artifact':art['artifact_id']},'disclosure':{},'approval_ref':None,'artifacts':(art,)}])
            self.assertEqual(r[0]['status'],'committed')
        ops=[leaf_op(lid,l['members'],l['descriptor'],'test',prep) for lid,l in ls.items()]
        ops += [parent_op('xpar-p',ps['xpar-p']['children'],ps['xpar-p']['members'],ps['xpar-p']['descriptor'],'test',prep)]
        tl.commit_batch(ops)
        oldpin=tl.pin(); old=read_seg_hierarchy(tl,oldpin)
        r=tl.local_repair.repair_step(10**8)
        self.assertGreater(r['checked'],0)
        self.assertEqual(read_seg_hierarchy(tl,oldpin),old)
        new=read_seg_hierarchy(tl,tl.pin())
        self.assertEqual(len(new['parents']),2)
        proj=Projections(); proj.update(tl)
        self.assertEqual(proj.hierarchy_view(),new)
        self.assertTrue(proj.validate_reverse_maps()['ok'])
        before=canonical(tl.local_repair.engine.snapshot())
        tl.close()
        tl=TLStore(os.path.join(root,'store'),local_repair=True,repair_config=RepairConfig(edge_threshold=.8))
        tl.local_repair.sync()
        self.assertEqual(before,canonical(tl.local_repair.engine.snapshot()))
        pin=tl.pin(); tl.local_repair.repair_step(10**8); self.assertEqual(pin,tl.pin())
        tl.close()

if __name__=='__main__': unittest.main(verbosity=2)
