#!/usr/bin/env python3
"""Deterministic verify + extract for docs-10m.jsonl.gz (stdlib only).

Checks compressed bytes, gzip header mtime==0, and decompressed exact
C2-10M freeze-v2 input (sha/bytes/rows). Writes exact bytes only on success,
via a sibling temporary file atomically replacing --out after all raw
byte/hash/schema checks pass. Rejects asset/out aliases (identical resolved
paths, symlinks, hardlinks) before any write. Preserves existing output and
asset on every failure; cleans temporary files.

Usage:
  python3 verify_docs_10m.py --asset docs-10m.jsonl.gz --out /tmp/c10m-inputs/docs-10m.jsonl
  python3 verify_docs_10m.py --asset docs-10m.jsonl.gz   # verify without writing
  python3 verify_docs_10m.py --self-test                 # bounded alias/corruption checks
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import tempfile

GZ_SHA256 = "31002b8cdb871989fc40c1970e7485e4dcbd80d0cbd813956dedffa28dda760a"
GZ_BYTES = 21787645
RAW_SHA256 = "04bbbb3ea3425a49491559173b20280fb286edeeef49c8293aebc0b92bcce3fd"
RAW_BYTES = 64291035
RAW_ROWS = 3099


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


def _alias_rejected(asset, out):
    """Return failure message if out aliases asset, else None. No I/O writes."""
    if out is None:
        return None
    try:
        if os.path.realpath(asset) == os.path.realpath(out):
            return f"FAIL: asset and --out resolve to the same path: {asset!r} == {out!r}"
    except OSError:
        pass
    try:
        if os.path.exists(asset) and os.path.exists(out) and os.path.samefile(asset, out):
            return f"FAIL: asset and --out are the same file (hardlink/symlink alias): {asset!r} == {out!r}"
    except OSError:
        pass
    return None


def verify(asset, out):
    # Reject aliases BEFORE any read/write that could truncate.
    msg = _alias_rejected(asset, out)
    if msg:
        print(msg, file=sys.stderr)
        return 1

    if not os.path.isfile(asset):
        print(f"FAIL: asset not found: {asset}", file=sys.stderr)
        return 1
    gz_size = os.path.getsize(asset)
    if gz_size != GZ_BYTES:
        print(f"FAIL: gz bytes {gz_size} != pinned {GZ_BYTES}", file=sys.stderr)
        return 1
    with open(asset, "rb") as f:
        hdr = f.read(10)
    if len(hdr) < 10 or hdr[0:2] != b"\x1f\x8b" or int.from_bytes(hdr[4:8], "little") != 0:
        print("FAIL: not deterministic gzip (magic/mtime0 check failed)", file=sys.stderr)
        return 1
    gz_sha = sha256_file(asset)
    if gz_sha != GZ_SHA256:
        print(f"FAIL: gz sha256 {gz_sha} != pinned {GZ_SHA256}", file=sys.stderr)
        return 1
    print(f"gz OK: {GZ_BYTES} bytes, sha256 {GZ_SHA256}, mtime 0")

    tmp_path = None
    tmp_f = None
    out_dir = None
    if out:
        # Re-check aliases after resolving output dir (parent may contain symlinks).
        out_abs = os.path.abspath(out)
        out_dir = os.path.dirname(out_abs) or "."
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            print(f"FAIL: cannot create output dir {out_dir}: {e}", file=sys.stderr)
            return 1
        msg = _alias_rejected(asset, out)
        if msg:
            print(msg, file=sys.stderr)
            return 1
        if os.path.isdir(out) and os.path.exists(out):
            print(f"FAIL: --out is a directory: {out}", file=sys.stderr)
            return 1
        base = os.path.basename(out_abs) or "docs-10m.jsonl"
        try:
            fd, tmp_path = tempfile.mkstemp(dir=out_dir, prefix=base + ".tmp-")
            tmp_f = os.fdopen(fd, "wb")
        except OSError as e:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            print(f"FAIL: cannot create temp output: {e}", file=sys.stderr)
            return 1

    def _cleanup_tmp():
        nonlocal tmp_f, tmp_path
        if tmp_f is not None:
            try:
                tmp_f.close()
            except OSError:
                pass
            tmp_f = None
        if tmp_path is not None:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            tmp_path = None

    # Stream-decompress, hash, count rows, validate JSONL keys on the fly.
    h = hashlib.sha256()
    nbytes = 0
    nrows = 0
    try:
        with gzip.open(asset, "rb") as f:
            buf = b""
            while True:
                chunk = f.read(8 * 1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
                nbytes += len(chunk)
                if tmp_f is not None:
                    tmp_f.write(chunk)
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for ln in lines:
                    if not ln:
                        continue
                    nrows += 1
                    if nrows <= 3 or nrows == RAW_ROWS:  # spot-validate schema
                        o = json.loads(ln.decode("utf-8"))
                        assert set(o.keys()) == {"doc_id", "text"}, f"row {nrows} keys {sorted(o.keys())}"
            if buf.strip():
                nrows += 1
                o = json.loads(buf.decode("utf-8"))
                assert set(o.keys()) == {"doc_id", "text"}
    except Exception as e:
        _cleanup_tmp()
        print(f"FAIL: decompress/parse: {e}", file=sys.stderr)
        return 1

    raw_sha = h.hexdigest()
    if nbytes != RAW_BYTES or raw_sha != RAW_SHA256 or nrows != RAW_ROWS:
        _cleanup_tmp()
        print(f"FAIL: raw bytes={nbytes} (want {RAW_BYTES}) sha={raw_sha} (want {RAW_SHA256}) rows={nrows} (want {RAW_ROWS})", file=sys.stderr)
        return 1
    print(f"raw OK: {RAW_BYTES} bytes, sha256 {RAW_SHA256}, {RAW_ROWS} rows, keys {{doc_id,text}}")
    if out:
        try:
            tmp_f.close()
            tmp_f = None
            os.replace(tmp_path, out)
            tmp_path = None
        except OSError as e:
            _cleanup_tmp()
            print(f"FAIL: atomic replace: {e}", file=sys.stderr)
            return 1
        print(f"wrote {out}")
    print("VERIFY PASS")
    return 0


def _gz_mtime0(raw: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as g:
        g.write(raw)
    return buf.getvalue()


def _tmp_leftovers(out_dir, base):
    try:
        return [n for n in os.listdir(out_dir) if n.startswith(base + ".tmp-")]
    except OSError:
        return []


def run_self_test():
    """Bounded checks: same path, hardlink, malformed asset/schema/digest,
    preexisting-output preservation, normal exact extraction. Small fixtures
    in temp dirs only; never touches the real asset."""
    global GZ_SHA256, GZ_BYTES, RAW_SHA256, RAW_BYTES, RAW_ROWS
    saved = (GZ_SHA256, GZ_BYTES, RAW_SHA256, RAW_BYTES, RAW_ROWS)
    passed = []
    failed = []

    def check(name, fn):
        try:
            fn()
        except AssertionError as e:
            failed.append(name)
            print(f"SELF-TEST FAIL {name}: {e}", file=sys.stderr)
        except Exception as e:
            failed.append(name)
            print(f"SELF-TEST ERROR {name}: {e!r}", file=sys.stderr)
        else:
            passed.append(name)
            print(f"SELF-TEST PASS {name}")
        finally:
            GZ_SHA256, GZ_BYTES, RAW_SHA256, RAW_BYTES, RAW_ROWS = saved

    def t_same_path():
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.gz")
            data = b"disposable-bytes"
            with open(p, "wb") as f:
                f.write(data)
            rc = verify(p, p)
            assert rc == 1, f"exit {rc}"
            with open(p, "rb") as f:
                assert f.read() == data, "asset mutated"
            assert _tmp_leftovers(d, "a.gz") == [], "temp leftover"

    def t_same_resolved_symlink():
        with tempfile.TemporaryDirectory() as d:
            real = os.path.join(d, "real.gz")
            with open(real, "wb") as f:
                f.write(b"x")
            link = os.path.join(d, "link.gz")
            os.symlink(real, link)
            rc = verify(real, link)
            assert rc == 1, f"exit {rc}"
            with open(real, "rb") as f:
                assert f.read() == b"x", "asset mutated"
            assert _tmp_leftovers(d, "link.gz") == [], "temp leftover"

    def t_hardlink():
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.gz")
            b = os.path.join(d, "b.gz")
            with open(a, "wb") as f:
                f.write(b"hl")
            try:
                os.link(a, b)
            except OSError as e:
                raise AssertionError(f"hardlink setup failed: {e}")
            rc = verify(a, b)
            assert rc == 1, f"exit {rc}"
            with open(a, "rb") as f:
                assert f.read() == b"hl"
            with open(b, "rb") as f:
                assert f.read() == b"hl"
            assert _tmp_leftovers(d, "b.gz") == [], "temp leftover"

    def t_malformed_asset():
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.gz")
            with open(bad, "wb") as f:
                f.write(b"\x00" * 100)  # bad magic
            out = os.path.join(d, "out.jsonl")
            sentinel = b"PREEXISTING"
            with open(out, "wb") as f:
                f.write(sentinel)
            globals()["GZ_BYTES"] = 100  # reach header check, still fail
            rc = verify(bad, out)
            assert rc == 1, f"exit {rc}"
            with open(out, "rb") as f:
                assert f.read() == sentinel, "preexisting output not preserved"
            assert os.path.getsize(bad) == 100, "asset mutated"
            assert _tmp_leftovers(d, "out.jsonl") == [], "temp leftover"

    def t_malformed_schema():
        with tempfile.TemporaryDirectory() as d:
            raw = b'{"doc_id":"a","bad":"x"}\n'
            gz = _gz_mtime0(raw)
            asset = os.path.join(d, "a.gz")
            with open(asset, "wb") as f:
                f.write(gz)
            globals()["GZ_BYTES"] = len(gz)
            globals()["GZ_SHA256"] = hashlib.sha256(gz).hexdigest()
            globals()["RAW_BYTES"] = len(raw)
            globals()["RAW_SHA256"] = hashlib.sha256(raw).hexdigest()
            globals()["RAW_ROWS"] = 1
            out = os.path.join(d, "o.jsonl")
            sentinel = b"SENTINEL"
            with open(out, "wb") as f:
                f.write(sentinel)
            rc = verify(asset, out)
            assert rc == 1, f"exit {rc}"
            with open(out, "rb") as f:
                assert f.read() == sentinel, "preexisting output not preserved"
            assert _tmp_leftovers(d, "o.jsonl") == [], "temp leftover"

    def t_malformed_digest():
        with tempfile.TemporaryDirectory() as d:
            raw = b'{"doc_id":"a","text":"hi"}\n'
            gz = _gz_mtime0(raw)
            asset = os.path.join(d, "a.gz")
            with open(asset, "wb") as f:
                f.write(gz)
            globals()["GZ_BYTES"] = len(gz)
            globals()["GZ_SHA256"] = hashlib.sha256(gz).hexdigest()
            globals()["RAW_BYTES"] = len(raw)
            globals()["RAW_SHA256"] = "0" * 64  # wrong digest
            globals()["RAW_ROWS"] = 1
            out = os.path.join(d, "o.jsonl")
            sentinel = b"KEEPME"
            with open(out, "wb") as f:
                f.write(sentinel)
            rc = verify(asset, out)
            assert rc == 1, f"exit {rc}"
            with open(out, "rb") as f:
                assert f.read() == sentinel, "preexisting output not preserved"
            with open(asset, "rb") as f:
                assert f.read() == gz, "asset mutated"
            assert _tmp_leftovers(d, "o.jsonl") == [], "temp leftover"

    def t_normal_exact():
        with tempfile.TemporaryDirectory() as d:
            rows = [b'{"doc_id":"d1","text":"t1"}', b'{"doc_id":"d2","text":"t2"}',
                    b'{"doc_id":"d3","text":"t3"}']
            raw = b"\n".join(rows) + b"\n"
            gz = _gz_mtime0(raw)
            asset = os.path.join(d, "a.gz")
            with open(asset, "wb") as f:
                f.write(gz)
            globals()["GZ_BYTES"] = len(gz)
            globals()["GZ_SHA256"] = hashlib.sha256(gz).hexdigest()
            globals()["RAW_BYTES"] = len(raw)
            globals()["RAW_SHA256"] = hashlib.sha256(raw).hexdigest()
            globals()["RAW_ROWS"] = 3
            out = os.path.join(d, "o.jsonl")
            with open(out, "wb") as f:
                f.write(b"OLD")
            rc = verify(asset, out)
            assert rc == 0, f"exit {rc}"
            with open(out, "rb") as f:
                assert f.read() == raw, "output not exact"
            assert _tmp_leftovers(d, "o.jsonl") == [], "temp leftover"
            # verify-without-write path
            rc2 = verify(asset, None)
            assert rc2 == 0, f"no-out exit {rc2}"

    for name, fn in [
        ("same-path", t_same_path),
        ("same-resolved-symlink", t_same_resolved_symlink),
        ("hardlink-alias", t_hardlink),
        ("malformed-asset", t_malformed_asset),
        ("malformed-schema", t_malformed_schema),
        ("malformed-digest", t_malformed_digest),
        ("normal-exact-extraction", t_normal_exact),
    ]:
        check(name, fn)
    GZ_SHA256, GZ_BYTES, RAW_SHA256, RAW_BYTES, RAW_ROWS = saved
    print(f"SELF-TEST {len(passed)} passed, {len(failed)} failed")
    return 0 if not failed else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs-10m.jsonl.gz"))
    ap.add_argument("--out", default=None, help="write exact docs-10m.jsonl here on success")
    ap.add_argument("--self-test", action="store_true", help="run bounded alias/corruption checks")
    a = ap.parse_args()
    if a.self_test:
        return run_self_test()
    return verify(a.asset, a.out)


if __name__ == "__main__":
    sys.exit(main())
