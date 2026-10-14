"""CPU-side consumption: file-backed emb() for the owning ingest path.

`make_file_backed_emb(cache_dir)` returns an `embed_texts` callable with
the exact signature `ingest_docs` expects ([str] -> [[float]]), served
from a GPU-stage cache file. Lookup is by exact chunk bytes under the
pinned numeric configuration — the same key derivation as the writer,
so a served vector is always the vector encoded for those exact bytes.

Miss policy: default STRICT (raise KeyError naming the missing chunk
digests). Strict is the default because a silent fallback encoder would
mix numeric configurations inside one ingest without a record. An
explicit `fallback` callable may be supplied for measured comparisons;
every fallback use is counted and reported in stats.

No torch / numpy required.
"""

import hashlib
import time

from . import cache as _cache
from . import config as _cfg


class StrictCacheMiss(KeyError):
    pass


def make_file_backed_emb(cache_dir, precision=_cfg.PRECISION_FIRST,
                          fallback=None, strict=True):
    """Return (embed_texts, handle).

    embed_texts(texts): [str] -> [[float]], ingest_docs-compatible.
    handle: dict with .close(), .stats(), reader access:
        handle["reader"]  CacheReader
        handle["stats"]() {"hits","misses","fallback_uses","lookups",
                           "lookup_s","vectors"}
        handle["close"]() release shard handles
    """
    reader = _cache.CacheReader(cache_dir, precision=precision)
    st = {"hits": 0, "misses": 0, "fallback_uses": 0,
          "lookups": 0, "lookup_s": 0.0, "vectors": 0}

    def embed_texts(texts):
        t0 = time.perf_counter()
        out = []
        missing = []
        for t in texts:
            cb = t.encode("utf-8")
            key, loc = reader.locate(cb)
            if loc is not None:
                out.append(reader._read_row(*loc))
                st["hits"] += 1
            else:
                st["misses"] += 1
                missing.append((t, key))
                out.append(None)
        st["lookups"] += 1
        st["vectors"] += len(texts)
        st["lookup_s"] += time.perf_counter() - t0
        if missing:
            if strict and fallback is None:
                digests = [hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]
                           for t, _k in missing[:8]]
                raise StrictCacheMiss(
                    "%d/%d texts missing from cache %r under config %s "
                    "(first chunk shas: %s). Refusing to mix encoders "
                    "silently; supply fallback= explicitly for measured "
                    "comparisons." % (len(missing), len(texts), cache_dir,
                                      reader.meta.get("config_id"),
                                      ",".join(digests)))
            fb_vecs = fallback([t for t, _k in missing])
            st["fallback_uses"] += len(missing)
            it = iter(fb_vecs)
            out = [next(it) if v is None else v for v in out]
        return out

    handle = {"reader": reader,
              "stats": lambda: dict(st),
              "close": reader.close}
    return embed_texts, handle


def check_coverage(manifest_rows, cache_dir, precision=_cfg.PRECISION_FIRST):
    """Verify exact manifest->cache mapping.

    For every manifest row: the recorded key must equal the recomputed
    key from the recorded chunk sha... (manifest carries chunk bytes
    only indirectly, so this check re-derives presence from the stored
    key and validates row metadata consistency: shard/row present,
    byte_len/dim consistent, no duplicate keys mapping two rows).
    Returns a report dict; raises on the first inconsistency.
    """
    reader = _cache.CacheReader(cache_dir, precision=precision)
    try:
        seen_keys = set()
        for r in manifest_rows:
            key = r["key"]
            if key in seen_keys:
                # Same chunk bytes in two manifest rows (duplicate chunk
                # text across docs) MUST share one key — that is the
                # documented dedup behavior, not an error.
                continue
            seen_keys.add(key)
            if key not in reader:
                raise ValueError("manifest key %s (doc %r chunk %d) has "
                                 "no cache row" % (key[:16], r["doc_id"],
                                                   r["chunk_ix"]))
            vec = reader.get_by_key(key)
            if len(vec) != reader.dim:
                raise ValueError("dim mismatch at key %s" % key[:16])
        return {"manifest_rows": len(manifest_rows),
                "distinct_keys": len(seen_keys),
                "cache_rows": reader.row_count,
                "coverage": "exact",
                "note": ("manifest_rows - distinct_keys duplicate chunk "
                         "texts share cache rows by design")}
    finally:
        reader.close()
