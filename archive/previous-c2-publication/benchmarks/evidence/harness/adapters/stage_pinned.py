"""lane-BENCH10M S1: stage pinned 10M corpora into TB cache layouts (on VM).

Pulls ONLY the TB-consumable 10M-tier files (bright-pony, beir-scifact,
beir-nfcorpus: 8 files, ~9 MB) DIRECTLY on this machine from the pinned
manifest URLs, verifies bytes+sha256 per file, and places them where
trace-bench consumes them WITHOUT network (TB short-circuits on
existing verified caches; no harness edits):

- BRIGHT pony parquets -> <cache>/bright/raw/{documents,examples}/
  pony-00000-of-00001.parquet (verbatim bytes).
- BEIR scifact/nfcorpus corpus+queries parquets -> converted to the
  legacy BEIR-jsonl layout <cache>/{dataset}/corpus.jsonl +
  queries.jsonl (native _id/title/text preserved row-for-row);
  pinned test.tsv -> <cache>/{dataset}/qrels/test.tsv (verbatim).

Every conversion is self-verified (row counts + id-set equality
parquet<->jsonl) and checked against TB catalog counts. An optional
--cross-check-ukp downloads the small legacy UKP zips and diffs
parsed content against the pinned-derived files (recorded; the
pinned bytes remain authoritative either way).

Writes <cache>/c2-bench10m-source-record.json (pins, hashes, counts,
verification outcomes). Refuses to fetch anything outside the three
listed sources. Stdlib + pyarrow (for the BEIR conversion) only.

Usage (on VM):

    python stage_pinned.py --manifest upstream-links.json \\
        --cache benchmarks/cache [--cross-check-ukp]
"""

import argparse
import csv
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

SOURCES = {
    "bright-pony": {"tb_task": "pony"},
    "beir-scifact": {"tb_dataset": "scifact", "expect_docs": 5183,
                     "expect_test_queries": 300},
    "beir-nfcorpus": {"tb_dataset": "nfcorpus", "expect_docs": 3633,
                      "expect_test_queries": 323},
}
UKP_ZIP = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/{dataset}.zip"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url, dest, expect_bytes, expect_sha256):
    """Download url to dest (resume verified caches); verify bytes+sha256."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size == expect_bytes \
            and sha256_file(dest) == expect_sha256:
        return "reused-verified"
    tmp = dest.with_suffix(dest.suffix + ".part")
    last = None
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "c2-bench10m/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            break
        except Exception as exc:  # noqa: BLE001 - retry once, then fail closed
            last = exc
            if attempt == 2:
                raise RuntimeError(f"fetch failed for {url}: {exc}") from exc
    size = tmp.stat().st_size
    digest = sha256_file(tmp)
    if size != expect_bytes or digest != expect_sha256:
        tmp.unlink(missing_ok=True)
        raise ValueError(
            f"identity mismatch for {dest.name}: got {size} bytes / sha256 "
            f"{digest[:16]}..., expected {expect_bytes} / {expect_sha256[:16]}...")
    tmp.replace(dest)
    return "fetched-verified"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--cross-check-ukp", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    cache = Path(args.cache)
    raw = cache / "_pinned_raw"
    by_id = {f["id"]: f for f in manifest["files"]}
    sources = {s["id"]: s for s in manifest["sources"]}
    record = {"manifest_files": args.manifest, "sources": {}, "files": {}}

    for sid, spec in SOURCES.items():
        entry = {"repository": sources[sid]["repository"],
                 "revision": sources[sid]["revision"], "roles": {}}
        for fid in sources[sid]["file_ids"]:
            f = by_id[fid]
            # Mirror the upstream repo layout (role dirs differ even
            # when basenames collide, e.g. pony documents/ vs
            # examples/ both named pony-00000-of-00001.parquet).
            # 162-fix: bare basename collided and the second fetch
            # overwrote the first (see evidence/pony-collision-162.log).
            dest = raw / sid / f["path"]
            status = fetch(f["url"], dest, f["bytes"], f["sha256"])
            record["files"][fid] = {"bytes": f["bytes"], "sha256": f["sha256"],
                                    "url": f["url"], "status": status,
                                    "local": str(dest)}
            entry["roles"][f["role"]] = str(dest)
        record["sources"][sid] = entry

    # --- BRIGHT pony: verbatim placement into TB raw layout ---
    import shutil
    pony = record["sources"]["bright-pony"]["roles"]
    for group, src in (("documents", pony["corpus"]),
                       ("examples", pony["queries_and_gold"])):
        dest = cache / "bright" / "raw" / group / f"pony-00000-of-00001.parquet"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not (dest.is_file() and sha256_file(dest) == sha256_file(Path(src))):
            shutil.copyfile(src, dest)
    record["sources"]["bright-pony"]["tb_layout"] = "bright/raw/{documents,examples}/pony-00000-of-00001.parquet"

    # --- BEIR: pinned parquet -> legacy jsonl layout (verified conversion) ---
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("BEIR conversion needs pyarrow (trace-bench[datasets])") from exc

    for sid in ("beir-scifact", "beir-nfcorpus"):
        spec = SOURCES[sid]
        roles = record["sources"][sid]["roles"]
        dset = spec["tb_dataset"]
        ddir = cache / dset
        ddir.mkdir(parents=True, exist_ok=True)

        corpus_rows = pq.read_table(roles["corpus"]).to_pylist()
        queries_rows = pq.read_table(roles["queries_and_gold"]).to_pylist()

        def doc_id(r):
            return str(r.get("_id", r.get("id", "")))

        if any(not doc_id(r) for r in corpus_rows) or \
                any(not doc_id(r) for r in queries_rows):
            raise ValueError(f"{sid}: parquet rows missing native ids")

        with open(ddir / "corpus.jsonl", "w", encoding="utf-8") as f:
            for r in corpus_rows:
                f.write(json.dumps({"_id": doc_id(r),
                                    "title": r.get("title") or "",
                                    "text": r.get("text") or ""},
                                   ensure_ascii=False) + "\n")
        with open(ddir / "queries.jsonl", "w", encoding="utf-8") as f:
            for r in queries_rows:
                f.write(json.dumps({"_id": doc_id(r),
                                    "text": r.get("text") or ""},
                                   ensure_ascii=False) + "\n")
        qdir = ddir / "qrels"
        qdir.mkdir(exist_ok=True)
        shutil.copyfile(roles["qrels"], qdir / "test.tsv")

        # Self-verification: id-set equality parquet <-> jsonl.
        back_docs, back_q = {}, {}
        with open(ddir / "corpus.jsonl", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                back_docs[item["_id"]] = (item["title"], item["text"])
        with open(ddir / "queries.jsonl", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                back_q[item["_id"]] = item["text"]
        src_docs = {doc_id(r): ((r.get("title") or ""), (r.get("text") or ""))
                    for r in corpus_rows}
        src_q = {doc_id(r): (r.get("text") or "") for r in queries_rows}
        if back_docs != src_docs or back_q != src_q:
            raise ValueError(f"{sid}: parquet->jsonl round-trip mismatch")

        # Qrels header (TB requires it) + test-query coverage.
        with open(qdir / "test.tsv", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            header = next(reader, None)
            if header != ["query-id", "corpus-id", "score"]:
                raise ValueError(f"{sid}: unexpected qrels header {header}")
            qrel_q, qrel_rows, missing_docs = set(), 0, set()
            for row in reader:
                qrel_rows += 1
                qrel_q.add(row[0])
                if row[1] not in back_docs:
                    missing_docs.add(row[1])
        if missing_docs:
            raise ValueError(f"{sid}: {len(missing_docs)} qrel docs missing from corpus")
        uncovered = [q for q in qrel_q if q not in back_q]
        if uncovered:
            raise ValueError(f"{sid}: {len(uncovered)} qrel queries missing texts")

        # Catalog-count check (TB's own expected population).
        if len(back_docs) != spec["expect_docs"]:
            raise ValueError(f"{sid}: docs {len(back_docs)} != catalog {spec['expect_docs']}")
        if len(qrel_q) != spec["expect_test_queries"]:
            raise ValueError(f"{sid}: test queries {len(qrel_q)} != catalog "
                             f"{spec['expect_test_queries']}")
        record["sources"][sid]["verified"] = {
            "docs": len(back_docs), "query_rows": len(back_q),
            "qrel_rows": qrel_rows, "test_queries": len(qrel_q),
            "round_trip": "parquet<->jsonl id+text identical",
            "cross_check_ukp": None,
        }

        if args.cross_check_ukp:
            record["sources"][sid]["verified"]["cross_check_ukp"] = \
                ukp_cross_check(dset, back_docs, back_q, qdir / "test.tsv", cache)

    (cache / "c2-bench10m-source-record.json").write_text(
        json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({s: record["sources"][s].get("verified", "staged")
                      for s in SOURCES}, indent=1))
    print("STAGE-PINNED: DONE", cache)


def ukp_cross_check(dset, pin_docs, pin_q, pin_qrels, cache):
    """Diff pinned-derived content vs the legacy UKP zip (parsed comparison)."""
    import tempfile
    import zipfile
    tmp = Path(tempfile.mkdtemp(prefix="ukp-xcheck-"))
    try:
        zip_path = tmp / f"{dset}.zip"
        req = urllib.request.Request(UKP_ZIP.format(dataset=dset),
                                     headers={"User-Agent": "c2-bench10m/1.0"})
        with urllib.request.urlopen(req, timeout=180) as resp, open(zip_path, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            corpus_name = next(n for n in names if n.endswith("corpus.jsonl"))
            queries_name = next(n for n in names if n.endswith("queries.jsonl"))
            qrels_name = next(n for n in names if n.endswith("qrels/test.tsv"))
            ukp_docs = {}
            for line in zf.read(corpus_name).decode("utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    ukp_docs[str(item.get("_id", item.get("id", "")))] = (
                        item.get("title", ""), item.get("text", ""))
            ukp_q = {}
            for line in zf.read(queries_name).decode("utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    ukp_q[str(item.get("_id", item.get("id", "")))] = item.get("text", "")
            ukp_qrels = zf.read(qrels_name).decode("utf-8")
        pin_qrels_text = Path(pin_qrels).read_text(encoding="utf-8")
        diffs = {}
        if ukp_docs != pin_docs:
            only_ukp = set(ukp_docs) - set(pin_docs)
            only_pin = set(pin_docs) - set(ukp_docs)
            text_diff = sum(1 for k in set(ukp_docs) & set(pin_docs)
                            if ukp_docs[k] != pin_docs[k])
            diffs["docs"] = {"only_ukp": len(only_ukp), "only_pin": len(only_pin),
                             "text_diff": text_diff}
        if ukp_q != pin_q:
            diffs["queries"] = {"ukp": len(ukp_q), "pinned": len(pin_q)}
        if ukp_qrels != pin_qrels_text:
            diffs["qrels_bytes_differ"] = True
        return {"compared": True, "diffs": diffs or "none — identical"}
    except Exception as exc:  # noqa: BLE001 - cross-check is advisory
        return {"compared": False, "reason": str(exc)[:200]}
    finally:
        import shutil as _shutil
        _shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
