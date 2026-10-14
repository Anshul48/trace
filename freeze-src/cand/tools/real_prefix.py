"""Read-only complete-document prefixes and strict cached vectors; NumPy only.

Portable: data dir via RealPrefix(target_tokens, data_dir=None),
env PILOT_DATA_DIR, else <this-file>/../data (file-parent default).
Corpus identity (TOK_V1 complete documents, tl-gpu-embcache-v1 FP32 cache)
is unchanged; only path resolution is parameterized.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time

import numpy as np

TOK = re.compile(r'[^\W_]+', re.UNICODE)
TOOL_DIR = Path(__file__).resolve().parent


def default_data_dir():
    return Path(os.environ.get('PILOT_DATA_DIR', TOOL_DIR.parent / 'data'))


class RealPrefix:
    def __init__(self, target_tokens, data_dir=None):
        from tlsys.ingest import chunk_text
        DATA = Path(data_dir) if data_dir is not None else default_data_dir()
        started = time.perf_counter()
        self.data_dir = str(DATA)
        self.docs, self.vectors = [], {}
        self.token_count = self.chunk_count = self.whitespace_tokens = 0
        self.cache = DATA/'emb_cache'
        meta_body = (self.cache/'meta.json').read_bytes()
        meta = json.loads(meta_body)
        assert meta['format'] == 'tl-gpu-embcache-v1'
        assert meta['dim'] == 384 and meta['dtype'] == 'float32-le'
        assert json.loads(meta['key_config_json'])['normalize_embeddings'] is False
        rows_per_shard = int(meta['rows_per_shard'])
        if rows_per_shard <= 0:
            raise RuntimeError('invalid cache rows_per_shard')
        self.config = meta['key_config_json'].encode('ascii')
        assert hashlib.sha256(self.config).hexdigest()[:16] == meta['config_id']
        wanted = {}
        doc_hash = hashlib.sha256()
        with open(DATA/'docs-100m.jsonl','rb') as source:
            for line in source:
                if not line.strip():
                    continue
                row = json.loads(line)
                doc, text = row['doc_id'], row['text']
                self.docs.append((doc,text))
                doc_hash.update(line)
                self.token_count += len(TOK.findall(text))
                self.whitespace_tokens += len(text.split())
                chunks = chunk_text(text) or [(0,0,'',0,0)]
                self.chunk_count += len(chunks)
                for chunk in chunks:
                    body = chunk[2].encode('utf-8')
                    key = self.key(body)
                    wanted[key] = hashlib.sha256(body).hexdigest(),len(body)
                if self.token_count >= target_tokens:
                    break
        assert len({d for d,_ in self.docs}) == len(self.docs)
        self.locations = {}
        index_hash = hashlib.sha256()
        with open(self.cache/'index.jsonl','rb') as source:
            for line in source:
                index_hash.update(line)
                row = json.loads(line)
                key = row['key']
                if key in wanted:
                    assert (row['chunk_sha256'],row['byte_len']) == wanted[key]
                    assert row['dim'] == 384
                    shard, global_row = int(row['shard']), int(row['row'])
                    if shard < 0 or global_row < 0 or global_row // rows_per_shard != shard:
                        raise RuntimeError('invalid cache row/shard')
                    # Cache index row is global; shard memmaps require local row.
                    loc = shard, global_row % rows_per_shard
                    if key in self.locations:
                        assert self.locations[key] == loc
                    self.locations[key] = loc
        if set(wanted) != set(self.locations):
            raise RuntimeError('real prefix cache miss: '+str(len(set(wanted)-set(self.locations))))
        shards = {}
        vector_hash = hashlib.sha256()
        for key in sorted(self.locations):
            shard, row = self.locations[key]
            if shard not in shards:
                shards[shard] = np.memmap(self.cache/f'shard_{shard:06d}.f32',mode='r',dtype='<f4').reshape(-1,384)
            if row >= len(shards[shard]):
                raise RuntimeError('cache row beyond shard end')
            v = np.array(shards[shard][row],copy=True)
            if not np.isfinite(v).all():
                raise RuntimeError('nonfinite cached vector')
            self.vectors[key] = v
            vector_hash.update(key.encode()); vector_hash.update(v.tobytes())
        self.receipt = {'target_tokens':target_tokens,'actual_tokens':self.token_count,
                        'tokenizer':'regex [^\\W_]+ (staged TOK_V1)',
                        'whitespace_tokens':self.whitespace_tokens,'complete_documents':len(self.docs),
                        'atoms':self.chunk_count,'distinct_chunks':len(wanted),'cache_misses':0,
                        'documents_source':str(DATA/'docs-100m.jsonl'),
                        'prefix_raw_sha256':doc_hash.hexdigest(),
                        'cache_meta_sha256':hashlib.sha256(meta_body).hexdigest(),
                        'cache_index_sha256':index_hash.hexdigest(),
                        'used_vector_sha256':vector_hash.hexdigest(),
                        'normalization':'cached FP32, unnormalized; cosine normalizes at scoring',
                        'input_wall_s':time.perf_counter()-started}

    def key(self, body):
        return hashlib.sha256(b'tl-gpu-embcache-v1\0'+self.config+b'\0'+body).hexdigest()

    def embed(self, texts):
        return [self.vectors[self.key(t.encode('utf-8'))].tolist() for t in texts]

    def probe(self):
        return next(iter(self.vectors.values())).astype(np.float64)
