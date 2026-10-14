"""WP census for the 10M prefix (same method as scale-stage tok_wp_census.py).

Counts WordPiece tokens (all-MiniLM-L6-v2, add_special_tokens=False,
local cache only) over the exact 13,081 ingestion texts:
scifact-full + curated paras + delta lines 0..7797, BEIR text convention.
Writes ONLY to stdout.
"""
import json
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HOME", "/tmp/tl-bench-env-20260927/hf-cache")

from transformers import AutoTokenizer  # noqa: E402

SCIFACT = "/tmp/tl-bench-env-20260927/cache/scifact/corpus.jsonl"
CURATED = ("/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace-bench"
           "/src/trace_bench/datasets/trace_engineering_curated.json")
DELTA = ("/mnt/c/Users/anshu/AppData/Local/trace-scale-data/staged_1m"
         "/wikipedia_delta.jsonl")
N_DELTA = 7798


def main():
    tok = AutoTokenizer.from_pretrained(
        "sentence-transformers/all-MiniLM-L6-v2", local_files_only=True)
    assert type(tok).__name__ == "BertTokenizerFast", type(tok).__name__
    assert len(tok) == 30522, len(tok)
    parts = {}
    scifact = []
    with open(SCIFACT, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            scifact.append((r.get("title", "") + "\n" +
                            r.get("text", "")).strip())
    parts["scifact"] = scifact
    d = json.load(open(CURATED, encoding="utf-8"))
    paras = [p for p in d["corpus_text"].split("\n\n") if p.strip()]
    assert len(paras) == 100
    parts["curated"] = paras
    delta = []
    with open(DELTA, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= N_DELTA:
                break
            r = json.loads(line)
            delta.append((r.get("title", "") + "\n" +
                          r.get("text", "")).strip())
    assert len(delta) == N_DELTA
    parts["delta"] = delta
    out = {"tok_class": type(tok).__name__, "vocab": len(tok)}
    total = 0
    for name, texts in parts.items():
        mx = 0
        n = 0
        for i in range(0, len(texts), 256):
            ids = tok(texts[i:i + 256],
                      add_special_tokens=False)["input_ids"]
            n += sum(len(x) for x in ids)
            mx = max(mx, max(len(x) for x in ids))
        out[name] = {"docs": len(texts), "tok_wp": n, "max_doc_wp": mx}
        total += n
    out["prefix_docs"] = sum(v["docs"] for k, v in out.items()
                             if isinstance(v, dict) and "docs" in v)
    out["prefix_tok_wp"] = total
    out["_method"] = ("AutoTokenizer all-MiniLM-L6-v2 local-only, "
                      "add_special_tokens=False, BEIR ingestion texts.")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
