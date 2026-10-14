"""Compare opt-in native pending queries with the original literal ordering."""
import numpy as np
from tlsys.org_publication import PreparedFacade, pending_order

def test_exact_selection_against_literal_full_sort():
    rng=np.random.default_rng(1901)
    for n in (1,2,17,1001):
        ids=tuple(str(x) for x in rng.permutation(n))
        for scores in (rng.normal(size=n),rng.integers(-2,3,size=n).astype(float),np.zeros(n)):
            for k in set((1,min(10,n),n)):
                expected=sorted(range(n),key=lambda i:(-scores[i],ids[i]))[:k]
                assert pending_order(scores,ids,k,True)==expected
    for scores in (np.array([float('nan'),1.,-1.]),np.array([float('inf'),0.,float('-inf')]),np.array([-0.,0.,np.nextafter(0.,1.)])):
        ids=('z','a','b')
        assert pending_order(scores,ids,2,True)==sorted(range(3),key=lambda i:(-scores[i],ids[i]))[:2]

def test_real_pending_method_same_rows_work_default_and_fast():
    from types import SimpleNamespace
    rng=np.random.default_rng(103)
    ids=tuple(str(x) for x in rng.permutation(301))
    mat=rng.normal(size=(301,8));mat[:30]=mat[0];mat[30]=0
    f=PreparedFacade.__new__(PreparedFacade)
    f._closed=False;f._pending_ids=ids;f._pending_mat=mat
    f._pending_norm=np.linalg.norm(mat,axis=1);f._pending_norm[f._pending_norm==0]=1
    f._index=SimpleNamespace(atoms={a:{'doc_id':'d'+a} for a in ids});f.triple='fixture'
    for q in (rng.normal(size=8),np.zeros(8)):
        for k in (-1,0,1,10,301,900):
            f._fast_pending_topk=False;old=f.pending_search(q,k)
            f._fast_pending_topk=True;new=f.pending_search(q,k)
            assert old==new
            assert new[1]['pending_atoms_scored']==(301 if k>0 else 0)
    del f._fast_pending_topk
    assert f.pending_search(np.ones(8),10)[1]['pending_atoms_scored']==301
