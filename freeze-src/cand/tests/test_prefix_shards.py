"""Real cache-index global-row regression with tiny multi-shard vectors."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from real_prefix import RealPrefix

def cache_fixture(tmp_path,shard,row,short=False):
 data=tmp_path/'data';cache=data/'emb_cache';cache.mkdir(parents=True)
 config=json.dumps({'normalize_embeddings':False},separators=(',',':'))
 meta={'format':'tl-gpu-embcache-v1','dim':384,'dtype':'float32-le','key_config_json':config,'config_id':hashlib.sha256(config.encode()).hexdigest()[:16],'rows_per_shard':2}
 (cache/'meta.json').write_text(json.dumps(meta));text='public tiny boundary document';body=text.encode();key=hashlib.sha256(b'tl-gpu-embcache-v1\0'+config.encode()+b'\0'+body).hexdigest()
 (data/'docs-100m.jsonl').write_text(json.dumps({'doc_id':'synthetic-doc','text':text})+'\n')
 (cache/'index.jsonl').write_text(json.dumps({'key':key,'chunk_sha256':hashlib.sha256(body).hexdigest(),'byte_len':len(body),'dim':384,'shard':shard,'row':row})+'\n')
 mats={0:np.arange(768,dtype=np.float32).reshape(2,384),1:(1000+np.arange(768,dtype=np.float32)).reshape(2,384)}
 if short:mats[1]=mats[1][:1]
 for sh,mat in mats.items():mat.astype('<f4').tofile(cache/f'shard_{sh:06d}.f32')
 return data,key,mats

def test_global_row_in_second_shard(tmp_path):
 data,key,mats=cache_fixture(tmp_path,1,3);r=RealPrefix(1,data);np.testing.assert_array_equal(r.vectors[key],mats[1][1]);assert r.receipt['cache_misses']==0 and r.receipt['atoms']==1
def test_exact_shard_boundary(tmp_path):
 data,key,mats=cache_fixture(tmp_path,1,2);r=RealPrefix(1,data);np.testing.assert_array_equal(r.vectors[key],mats[1][0])
def test_shard_zero_vectors_unchanged(tmp_path):
 data,key,mats=cache_fixture(tmp_path,0,1);r=RealPrefix(1,data);np.testing.assert_array_equal(r.vectors[key],mats[0][1])
def test_short_last_shard_fails_closed(tmp_path):
 data,_,_=cache_fixture(tmp_path,1,3,short=True)
 with pytest.raises(RuntimeError,match='cache row beyond shard end'):RealPrefix(1,data)
def test_negative_global_row_fails_closed(tmp_path):
 data,_,_=cache_fixture(tmp_path,0,-1)
 with pytest.raises(RuntimeError,match='invalid cache row/shard'):RealPrefix(1,data)
def test_inconsistent_global_row_shard_fails_closed(tmp_path):
 data,_,_=cache_fixture(tmp_path,1,1)
 with pytest.raises(RuntimeError,match='invalid cache row/shard'):RealPrefix(1,data)
