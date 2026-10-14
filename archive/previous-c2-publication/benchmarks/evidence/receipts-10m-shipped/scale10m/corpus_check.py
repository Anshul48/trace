"""10M-rung corpus check (stdlib only, no model load).

Reproduces the exact TOK-10M validated vector and verifies it doc-by-doc:
  frozen order = [scifact file order][curated file order][wikipedia_delta file order]
  prefix = smallest whole-doc prefix with cumsum TOK-v1 >= 10M.

Verifies against /tmp/tl-tok-10m-s2-2026-09-29/tok-10m-s/records/doc_manifest.json:
  1. source file sha256 pins (scifact, curated, delta)
  2. per-doc counted_sha256 + tok_count for all 13,081 prefix docs
  3. prefix minimality cumsum[n-1] < 10M <= cumsum[n]
  4. doc_id uniqueness across the prefix
  5. gold coverage: all 809 S1/tuning scifact qrels gold docs in the prefix

Writes ONLY to stdout (caller redirects into the owned evidence dir).
"""
import csv
import hashlib
import json
import re

TOK = re.compile(r"[^\W_]+", re.UNICODE)
TARGET = 10_000_000

SCIFACT = "/tmp/tl-bench-env-20260927/cache/scifact/corpus.jsonl"
SCIFACT_QRELS_TRAIN = "/tmp/tl-bench-env-20260927/cache/scifact/qrels/train.tsv"
CURATED = ("/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace-bench"
           "/src/trace_bench/datasets/trace_engineering_curated.json")
DELTA = ("/mnt/c/Users/anshu/AppData/Local/trace-scale-data/staged_1m"
         "/wikipedia_delta.jsonl")
MANIFEST = ("/tmp/tl-tok-10m-s2-2026-09-29/tok-10m-s/records/doc_manifest.json")


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main():
    man = json.load(open(MANIFEST, encoding="utf-8"))
    rows = man["rows"]
    out = {"target": TARGET, "manifest_doc_count": len(rows),
           "manifest_prefix_tokens": man["prefix_actual_tokens"]}

    # 1. source file pins
    pins = man["corpus_file_sha256"]
    file_sha = {
        "scifact_corpus.jsonl": sha_file(SCIFACT),
        "trace_engineering_curated.json": sha_file(CURATED),
        "wikipedia_delta.jsonl": sha_file(DELTA),
    }
    out["file_sha_match"] = {k: file_sha[k] == pins[k] for k in pins}
    out["file_sha_actual"] = file_sha

    # 2. rebuild prefix texts in frozen order
    docs = []  # (doc_id, counted_text)
    with open(SCIFACT, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            docs.append((r["_id"], (r.get("title", "") + "\n" +
                                    r.get("text", "")).strip()))
    n_scifact = len(docs)
    d = json.load(open(CURATED, encoding="utf-8"))
    paras = [p for p in d["corpus_text"].split("\n\n") if p.strip()]
    for i, p in enumerate(paras):
        docs.append((f"cur-{i:03d}", p))
    n_curated = len(paras)

    # delta counted-text convention: resolve empirically against the
    # manifest's first delta row, then verify all rows.
    delta_lines = []
    with open(DELTA, encoding="utf-8") as f:
        for line in f:
            delta_lines.append(json.loads(line))
    out["delta_file_lines"] = len(delta_lines)
    m_first = [r for r in rows if r["corpus"] == "delta"][0]
    r0 = delta_lines[0]
    cands = {
        "beir_strip(title\\ntext)": (r0.get("title", "") + "\n" +
                                     r0.get("text", "")).strip(),
        "text_verbatim": r0.get("text", ""),
        "text_strip": r0.get("text", "").strip(),
        "title_nn_text_strip": (r0.get("title", "") + "\n\n" +
                                r0.get("text", "")).strip(),
    }
    convention = None
    for name, t in cands.items():
        if sha_text(t) == m_first["counted_sha256"]:
            convention = name
            break
    out["delta_convention_candidates"] = {
        n: sha_text(t) == m_first["counted_sha256"] for n, t in cands.items()}
    assert convention is not None, "no delta counted-text convention matched"
    out["delta_convention"] = convention
    assert r0["doc_id"] == m_first["doc_id"], (r0["doc_id"], m_first["doc_id"])

    def delta_text(r):
        if convention == "text_verbatim":
            return r.get("text", "")
        if convention == "text_strip":
            return r.get("text", "").strip()
        if convention == "title_nn_text_strip":
            return (r.get("title", "") + "\n\n" +
                    r.get("text", "")).strip()
        return (r.get("title", "") + "\n" + r.get("text", "")).strip()

    n_delta_need = sum(1 for r in rows if r["corpus"] == "delta")
    for r in delta_lines[:n_delta_need]:
        docs.append((r["doc_id"], delta_text(r)))
    assert len(docs) == len(rows), (len(docs), len(rows))

    # per-doc verify: id, sha, tok, cumsum
    mism = {"id": 0, "sha": 0, "tok": 0, "cumsum": 0}
    first_mism = {}
    cumsum = 0
    toks = []
    for got, m in zip(docs, rows):
        gid, gtext = got
        c = len(TOK.findall(gtext))
        toks.append(c)
        cumsum += c
        for key, ok in (("id", gid == m["doc_id"]),
                        ("sha", sha_text(gtext) == m["counted_sha256"]),
                        ("tok", c == m["tok_count"]),
                        ("cumsum", cumsum == m["cumsum"])):
            if not ok:
                mism[key] += 1
                first_mism.setdefault(key, {"rank": m["rank"],
                                            "manifest": m["doc_id"],
                                            "got": gid})
    out["n_scifact"] = n_scifact
    out["n_curated"] = n_curated
    out["n_delta"] = n_delta_need
    out["prefix_docs"] = len(docs)
    out["prefix_tok_v1"] = cumsum
    out["per_doc_mismatches"] = mism
    out["first_mismatches"] = first_mism

    # 3. minimality
    out["minimality"] = {"prev_cumsum": cumsum - toks[-1],
                         "prev_lt_target": (cumsum - toks[-1]) < TARGET,
                         "prefix_gte_target": cumsum >= TARGET,
                         "terminal_doc_id": docs[-1][0],
                         "terminal_line_ix": n_delta_need - 1}
    out["matches_manifest_total"] = (
        cumsum == man["prefix_actual_tokens"])

    # 4. uniqueness
    ids = [d[0] for d in docs]
    out["doc_ids_unique"] = len(set(ids)) == len(ids)

    # 5. gold coverage: tuning qrels gold docs in prefix
    idset = set(ids)
    gold = set()
    n_q = 0
    with open(SCIFACT_QRELS_TRAIN, encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        for row in rd:
            if int(row["score"]) >= 1:
                gold.add(row["corpus-id"])
    # tuning qids per run_quality task mapping: qids with any train qrel
    tq = set()
    with open(SCIFACT_QRELS_TRAIN, encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        for row in rd:
            tq.add(row["query-id"])
    out["tuning_qids"] = len(tq)
    out["tuning_gold_docs"] = len(gold)
    out["gold_in_prefix"] = len(gold & idset)
    out["gold_missing"] = sorted(gold - idset)[:10]
    out["gold_coverage_ok"] = gold <= idset

    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
