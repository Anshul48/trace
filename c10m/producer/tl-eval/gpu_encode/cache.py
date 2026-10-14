"""Incremental file-backed embedding cache (stdlib-only).

Layout under cache_dir:
  meta.json     {format, key_config, config_id, dim, dtype, created, ...}
  index.jsonl   append-only; one JSON object per cached row:
                {key, shard, row, chunk_sha256, byte_len, model_tokens,
                 truncated, dim}
  shard_XXXXXX.f32  raw little-endian float32, row-major (dim per row)

Properties:
- Keyed by (chunk bytes, encoder/tokenizer/pooling/truncation/
  normalization/precision) via config.cache_key — never by atom ID.
- Incremental + resume-safe: open-for-write replays index.jsonl
  (a torn tail line is ignored and truncated), then validates
  every shard file against the replayed index: unindexed trailing
  bytes (orphan vectors from an interruption between the vector
  fsync and the index fsync) are truncated + fsynced; a shard
  holding FEWER bytes than the index addresses refuses the open.
  Appends remain row-atomic (vector bytes flushed + fsynced
  before the index line is appended and fsynced).
- Duplicate puts of the same key are deduplicated (first row wins;
  put returns the existing location).
- No numpy/torch dependency: readable anywhere with struct/array.

ADJACENT HAZARD (documented, not built here): there is NO
inter-process exclusive-writer lock. The open-for-write repair is
correct only under single-writer ownership: two concurrent
CacheWriters on one dir can interleave shard/index appends and
defeat the byte accounting. Owners must serialize writers
externally (one writer process per cache dir). A lock service is
explicitly out of scope for the M1 minimal repair.

Shard rotation: a new shard starts every `rows_per_shard` rows
(default 50k ~ 73MB at dim 384 fp32) so no single file grows without
bound and per-shard digests stay cheap.
"""

import array
import hashlib
import json
import os
import struct
import time

from . import config as _cfg

DTYPE = "float32-le"
ROWS_PER_SHARD = 50000


def _shard_name(ix):
    return "shard_%06d.f32" % ix


class CacheWriter:
    """Open-or-create a cache for incremental appends.

    Open-for-write heals interruptions (truncates unindexed shard
    bytes) or refuses the open (missing indexed bytes, config/
    geometry mismatch). Single-writer ownership is required (see
    module docstring: no inter-process lock)."""

    def __init__(self, cache_dir, dim, precision=_cfg.PRECISION_FIRST,
                 rows_per_shard=ROWS_PER_SHARD, produced_by=None):
        """produced_by: optional dict identifying the producing stack
        (torch/ST versions, device). When supplied AND the cache already
        records one, a mismatch refuses the append: legs built by
        different stacks must live in separate caches and be compared
        with compare_legs, never silently merged."""
        self.dir = os.path.abspath(cache_dir)
        self.dim = int(dim)
        self.precision = precision
        self.rows_per_shard = int(rows_per_shard)
        os.makedirs(self.dir, exist_ok=True)
        self._key_config_json = _cfg.canonical_config_json(precision)
        self._keys = {}      # key -> (shard, row)
        self._row_count = 0
        self._shard_max_row = {}  # shard -> max indexed row (replay)
        meta_path = os.path.join(self.dir, "meta.json")
        self._produced_by = produced_by
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("key_config_json") != self._key_config_json:
                raise ValueError(
                    "cache config mismatch: existing cache was built for "
                    "a different numeric configuration (refusing to mix "
                    "numeric variants in one cache)")
            if int(meta.get("dim", 0)) != self.dim:
                raise ValueError("cache dim mismatch: %r vs %d"
                                 % (meta.get("dim"), self.dim))
            if meta.get("rows_per_shard") != self.rows_per_shard:
                raise ValueError(
                    "cache rows_per_shard mismatch: existing cache "
                    "uses %r, open requested %d (refusing: shard "
                    "geometry selects the byte accounting; a wrong "
                    "geometry would mis-repair valid bytes)"
                    % (meta.get("rows_per_shard"), self.rows_per_shard))
            if self._produced_by is not None:
                prev = meta.get("produced_by")
                if prev is not None and prev != self._produced_by:
                    raise ValueError(
                        "cache producer mismatch: this cache was built by "
                        "%r, refusing appends from %r (different stacks "
                        "must use separate caches; compare with "
                        "compare_legs)" % (prev, self._produced_by))
                if prev is None:
                    meta["produced_by"] = self._produced_by
                    _atomic_write_json(meta_path, meta)
        else:
            meta = {
                "format": _cfg.FORMAT_TAG,
                "key_config_json": self._key_config_json,
                "config_id": _cfg.config_id(precision),
                "dim": self.dim,
                "dtype": DTYPE,
                "rows_per_shard": self.rows_per_shard,
                "produced_by": self._produced_by,
                "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime()),
            }
            _atomic_write_json(meta_path, meta)
        self._replay_index()
        self._validate_shards()
        self._shard_fh = None
        self._shard_ix = None

    # -- resume ------------------------------------------------------
    def _replay_index(self):
        idx_path = os.path.join(self.dir, "index.jsonl")
        if not os.path.exists(idx_path):
            return
        good_upto = 0
        with open(idx_path, "rb") as f:
            data = f.read()
        off = 0
        for line in data.split(b"\n"):
            if not line:
                off += 1
                continue
            try:
                rec = json.loads(line.decode("utf-8"))
                key = rec["key"]
            except Exception:
                break  # torn tail line: stop, truncate below
            if key not in self._keys:
                sh, rw = int(rec["shard"]), int(rec["row"])
                self._keys[key] = (sh, rw)
                self._row_count = max(self._row_count, rw + 1)
                prev = self._shard_max_row.get(sh)
                if prev is None or rw > prev:
                    self._shard_max_row[sh] = rw
            off += len(line) + 1
            good_upto = off
        if good_upto != len(data):
            # Truncate the torn tail so the index is clean going forward.
            with open(idx_path, "r+b") as f:
                f.truncate(good_upto)
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except OSError:
                    pass

    # -- crash recovery (F1 minimal repair) ------------------------------
    def _validate_shards(self):
        """Reconcile shard files with the replayed index.

        Per shard: expected = indexed rows in shard x dim x 4.
        actual > expected -> truncate + fsync (orphan vector bytes
        from an interruption between the vector fsync and the index
        fsync; without this the next put() appends at physical EOF
        while the index claims the logical row -- silent wrong-vector
        serving). actual < expected -> REFUSE the open (missing
        indexed bytes; fail closed, never serve shifted rows).
        A corrupt (shard,row) record also refuses the open.
        Requires single-writer ownership (see module docstring).
        """
        rps = self.rows_per_shard
        stride = self.dim * 4
        expected = {}
        for sh, max_row in self._shard_max_row.items():
            base = sh * rps
            if max_row < base or max_row >= base + rps:
                raise ValueError(
                    "cache index corrupt: row %d is not in shard %d "
                    "(rows_per_shard=%d); refusing open"
                    % (max_row, sh, rps))
            expected[sh] = (max_row - base + 1) * stride
        for name in os.listdir(self.dir):
            if name.startswith("shard_") and name.endswith(".f32"):
                try:
                    sh = int(name[len("shard_"):-len(".f32")])
                except ValueError:
                    continue
                expected.setdefault(sh, 0)
        for sh in sorted(expected):
            want = expected[sh]
            path = os.path.join(self.dir, _shard_name(sh))
            if not os.path.exists(path):
                if want == 0:
                    continue
                raise IOError(
                    "cache shard %d missing: index addresses %d "
                    "bytes; refusing open (restore or rebuild)"
                    % (sh, want))
            actual = os.path.getsize(path)
            if actual > want:
                with open(path, "r+b") as f:
                    f.truncate(want)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
            elif actual < want:
                raise IOError(
                    "cache shard %d short: index addresses %d bytes "
                    "but the file holds %d; refusing open (missing "
                    "indexed bytes; restore or rebuild)"
                    % (sh, want, actual))

    # -- append ------------------------------------------------------
    def _shard_for(self, row):
        return row // self.rows_per_shard, row % self.rows_per_shard

    def _fh(self, shard_ix):
        if self._shard_fh is not None and self._shard_ix == shard_ix:
            return self._shard_fh
        self.close_shard()
        path = os.path.join(self.dir, _shard_name(shard_ix))
        self._shard_fh = open(path, "ab")
        self._shard_ix = shard_ix
        return self._shard_fh

    def close_shard(self):
        if self._shard_fh is not None:
            try:
                self._shard_fh.flush()
                os.fsync(self._shard_fh.fileno())
            except OSError:
                pass
            self._shard_fh.close()
            self._shard_fh = None
            self._shard_ix = None

    def put(self, chunk_bytes, vector, model_tokens=None, truncated=None):
        """Append (chunk_bytes -> vector). Returns (key, shard, row, new)."""
        if not isinstance(chunk_bytes, (bytes, bytearray)):
            raise TypeError("chunk_bytes must be bytes")
        key = _cfg.cache_key(bytes(chunk_bytes), self.precision)
        if key in self._keys:
            shard, row = self._keys[key]
            return key, shard, row, False
        vec = [float(v) for v in vector]
        if len(vec) != self.dim:
            raise ValueError("vector dim %d != cache dim %d"
                             % (len(vec), self.dim))
        row = self._row_count
        shard_ix, _within = self._shard_for(row)
        blob = struct.pack("<%df" % self.dim, *vec)
        fh = self._fh(shard_ix)
        fh.write(blob)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
        rec = {"key": key, "shard": shard_ix, "row": row,
               "chunk_sha256": hashlib.sha256(bytes(chunk_bytes)).hexdigest(),
               "byte_len": len(chunk_bytes),
               "model_tokens": model_tokens, "truncated": truncated,
               "dim": self.dim}
        idx_path = os.path.join(self.dir, "index.jsonl")
        with open(idx_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        self._keys[key] = (shard_ix, row)
        self._row_count += 1
        return key, shard_ix, row, True

    def __contains__(self, key):
        return key in self._keys

    @property
    def row_count(self):
        return self._row_count

    def close(self):
        self.close_shard()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class CacheReader:
    """Read-only access to a cache built by CacheWriter."""

    def __init__(self, cache_dir, precision=_cfg.PRECISION_FIRST):
        self.dir = os.path.abspath(cache_dir)
        meta_path = os.path.join(self.dir, "meta.json")
        with open(meta_path, "r", encoding="utf-8") as f:
            self.meta = json.load(f)
        want = _cfg.canonical_config_json(precision)
        if self.meta.get("key_config_json") != want:
            raise ValueError(
                "cache/reader config mismatch: refusing to serve vectors "
                "built under a different numeric configuration")
        self.dim = int(self.meta["dim"])
        if self.meta.get("dtype") != DTYPE:
            raise ValueError("unsupported cache dtype %r" % self.meta.get("dtype"))
        self.precision = precision
        self._keys = {}
        idx_path = os.path.join(self.dir, "index.jsonl")
        if os.path.exists(idx_path):
            with open(idx_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    self._keys.setdefault(rec["key"],
                                          (int(rec["shard"]), int(rec["row"])))
        self._rows_per_shard = int(self.meta.get("rows_per_shard",
                                                 ROWS_PER_SHARD))
        self._fh_cache = {}

    @property
    def row_count(self):
        return len(self._keys)

    def __contains__(self, key):
        return key in self._keys

    def locate(self, chunk_bytes):
        key = _cfg.cache_key(bytes(chunk_bytes), self.precision)
        return key, self._keys.get(key)

    def _read_row(self, shard, row):
        within = row % self._rows_per_shard
        fh = self._fh_cache.get(shard)
        if fh is None:
            fh = open(os.path.join(self.dir, _shard_name(shard)), "rb")
            self._fh_cache[shard] = fh
        fh.seek(within * self.dim * 4)
        blob = fh.read(self.dim * 4)
        if len(blob) != self.dim * 4:
            raise IOError("short read at shard %d row %d" % (shard, row))
        return list(struct.unpack("<%df" % self.dim, blob))

    def get_by_key(self, key):
        loc = self._keys.get(key)
        if loc is None:
            raise KeyError(key)
        return self._read_row(*loc)

    def get(self, chunk_bytes):
        key, loc = self.locate(chunk_bytes)
        if loc is None:
            raise KeyError(key)
        return self._read_row(*loc)

    def close(self):
        for fh in self._fh_cache.values():
            try:
                fh.close()
            except OSError:
                pass
        self._fh_cache.clear()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def digests(cache_dir):
    """sha256 per cache file (meta/index/shards) for run records."""
    out = {}
    d = os.path.abspath(cache_dir)
    for name in sorted(os.listdir(d)):
        if name == "meta.json" or name == "index.jsonl" \
                or (name.startswith("shard_") and name.endswith(".f32")):
            h = hashlib.sha256()
            with open(os.path.join(d, name), "rb") as f:
                for blk in iter(lambda: f.read(1 << 20), b""):
                    h.update(blk)
            out[name] = h.hexdigest()
    return out


def _atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)
