#!/usr/bin/env python3
"""Deterministic verify + extract for docs-10m.jsonl.gz (stdlib only).

Checks compressed bytes, gzip header mtime==0, and decompressed exact
C2-10M freeze-v2 input (sha/bytes/rows). Writes exact bytes only on success.

Usage:
  python3 verify_docs_10m.py --asset docs-10m.jsonl.gz --out /tmp/c10m-inputs/docs-10m.jsonl
  python3 verify_docs_10m.py --asset docs-10m.jsonl.gz   # verify without writing
"""
import argparse, gzip, hashlib, json, os, sys

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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs-10m.jsonl.gz"))
    ap.add_argument("--out", default=None, help="write exact docs-10m.jsonl here on success")
    a = ap.parse_args()

    if not os.path.isfile(a.asset):
        print(f"FAIL: asset not found: {a.asset}", file=sys.stderr)
        return 1
    gz_size = os.path.getsize(a.asset)
    if gz_size != GZ_BYTES:
        print(f"FAIL: gz bytes {gz_size} != pinned {GZ_BYTES}", file=sys.stderr)
        return 1
    with open(a.asset, "rb") as f:
        hdr = f.read(10)
    if len(hdr) < 10 or hdr[0:2] != b"\x1f\x8b" or int.from_bytes(hdr[4:8], "little") != 0:
        print("FAIL: not deterministic gzip (magic/mtime0 check failed)", file=sys.stderr)
        return 1
    gz_sha = sha256_file(a.asset)
    if gz_sha != GZ_SHA256:
        print(f"FAIL: gz sha256 {gz_sha} != pinned {GZ_SHA256}", file=sys.stderr)
        return 1
    print(f"gz OK: {GZ_BYTES} bytes, sha256 {GZ_SHA256}, mtime 0")

    # Stream-decompress, hash, count rows, validate JSONL keys on the fly.
    h = hashlib.sha256()
    nbytes = 0
    nrows = 0
    out_f = None
    try:
        if a.out:
            os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
            out_f = open(a.out, "wb")
        with gzip.open(a.asset, "rb") as f:
            buf = b""
            while True:
                chunk = f.read(8 * 1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
                nbytes += len(chunk)
                if out_f:
                    out_f.write(chunk)
                buf += chunk
                # count complete lines incrementally
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
        if out_f:
            out_f.close()
            try:
                os.remove(a.out)
            except OSError:
                pass
        print(f"FAIL: decompress/parse: {e}", file=sys.stderr)
        return 1
    finally:
        if out_f:
            out_f.close()

    raw_sha = h.hexdigest()
    if nbytes != RAW_BYTES or raw_sha != RAW_SHA256 or nrows != RAW_ROWS:
        if out_f:
            try:
                os.remove(a.out)
            except OSError:
                pass
        print(f"FAIL: raw bytes={nbytes} (want {RAW_BYTES}) sha={raw_sha} (want {RAW_SHA256}) rows={nrows} (want {RAW_ROWS})", file=sys.stderr)
        return 1
    print(f"raw OK: {RAW_BYTES} bytes, sha256 {RAW_SHA256}, {RAW_ROWS} rows, keys {{doc_id,text}}")
    if a.out:
        print(f"wrote {a.out}")
    print("VERIFY PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
