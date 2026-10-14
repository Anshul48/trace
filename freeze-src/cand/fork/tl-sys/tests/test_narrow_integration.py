"""Maintained integration test: ingest -> index -> Narrow query on the
real candidate store with the real MiniLM encoder (offline weights).

Requires: tl-sys/.venv (ST+torch+blake3+numpy), HF_HOME=/tmp/hf_cache,
HF_HUB_OFFLINE=1. Run:
  HF_HOME=/tmp/hf_cache HF_HUB_OFFLINE=1 tl-sys/.venv/bin/python \\
    tl-sys/tests/test_narrow_integration.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore
from tlsys.ingest import ingest_docs
from tlsys.index import NarrowIndex
from tlsys.query import NarrowQuery

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DOCS = [
    ("d-cat", "The domestic cat is a small carnivorous mammal. Cats "
     "purr when content and hunt small rodents at night."),
    ("d-dog", "The domestic dog is a loyal companion animal. Dogs bark "
     "to alert their owners and enjoy long walks in the park."),
    ("d-fuse", "An electrical fuse protects circuits from overcurrent. "
     "When current exceeds the rating the fuse wire melts."),
]

tmp = tempfile.mkdtemp(prefix="tlsys-it-")
tl = TLStore(os.path.join(tmp, "store"), create=True,
             lease_owner="test-narrow-it")

from sentence_transformers import SentenceTransformer
enc = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
emb = lambda texts: [list(map(float, v)) for v in
                     enc.encode(texts, convert_to_numpy=True)]
emb1 = lambda q: list(map(float, enc.encode(
    q, convert_to_numpy=True)))

rep = ingest_docs(tl, DOCS, emb)
check("ingest-counts", rep["n_atoms"] == 3 and rep["n_holons"] == 3,
      f"{rep}")
pinned = tl.pin()
check("pin-triple", pinned[3].count(":") == 2, f"{pinned[3]}")

idx = NarrowIndex(tl, pinned)
check("index-atoms", len(idx.atoms) == 3, f"{len(idx.atoms)}")
check("index-holons",
      {"d-cat", "d-dog", "d-fuse"} <= set(idx.holons)
      and all(h in ("d-cat", "d-dog", "d-fuse")
              or h.startswith("xdoc-") for h in idx.holons),
      f"{sorted(idx.holons)}")
check("atom-doc-attribution",
      all(a["doc_id"] in ("d-cat", "d-dog", "d-fuse")
          for a in idx.atoms.values()), "Q3.1 attribution")

nq = NarrowQuery(tl, idx, emb1)
dos, rec = nq.run("which animal purrs when content")
ids = [e["doc_id"] for e in dos["entries"]]
check("query-finds-cat", "d-cat" in ids, f"{ids}")
check("receipt-3d",
      rec["execution"]["status"] == "complete"
      and "support_findings" in rec
      and "selection_outcomes" in rec, f"{rec['execution']}")
check("receipt-gen", rec["pinned_generation"] == pinned[3],
      rec["pinned_generation"])
check("receipt-flags", rec["flags"].get("narrow_Q9.2") is True
      and "disclosure_UQ1" in rec, f"{rec['flags']}")
check("entries-shape",
      all("atom_id" in e and "text" in e and "span" in e
          and e["issuing_generation"] != ""
          and e["resolving_generation"] == pinned[3]
          for e in dos["entries"]), f"{len(dos['entries'])} entries")
check("trace-calls", len(tl.trace.calls) > 10,
      f"{len(tl.trace.calls)} calls")

# determinism: same query twice -> same entry order
dos2, rec2 = nq.run("which animal purrs when content")
check("deterministic",
      [e["atom_id"] for e in dos["entries"]] ==
      [e["atom_id"] for e in dos2["entries"]], "order differs")

# unpruned reference mode runs
dosu, recu = nq.run("which animal purrs when content",
                    unpruned_reference=True)
check("unpruned-mode", recu["metrics"]["unpruned_reference"] is True
      and len(dosu["entries"]) >= 1, f"{recu['metrics']}")

# idempotent re-ingest via manifest: all skipped, pin unchanged
rep2 = ingest_docs(tl, DOCS, emb)
check("reingest-idempotent",
      rep2["n_atoms"] == 0 and rep2["n_holons"] == 0
      and sorted(rep2["skipped"]) == ["d-cat", "d-dog", "d-fuse"]
      and tl.pin()[3] == pinned[3],
      f"{rep2}")

# cfg overrides ([E] tuning; Q16.1d) --------------------------------
from tlsys.query import NarrowQuery as NQ2
nq_hi = NQ2(tl, idx, emb1, cfg={"TAU_SEL": 999.0})
dos_hi, rec_hi = nq_hi.run("which animal purrs when content")
check("cfg-tausel-blocks",
      len(dos_hi["entries"]) == 0
      and rec_hi["metrics"]["tau_sel"] == 999.0,
      f"{len(dos_hi['entries'])}")
try:
    NQ2(tl, idx, emb1, cfg={"RRF_K": 20})
    check("cfg-rrf-rejected", False, "RRF_K accepted!")
except ValueError:
    check("cfg-rrf-rejected", True)
try:
    NQ2(tl, idx, emb1, cfg={"NOPE": 1})
    check("cfg-unknown-rejected", False, "unknown key accepted!")
except ValueError:
    check("cfg-unknown-rejected", True)
# R1 repair pin: default MMR lambda is 0.8 through the same
# resolution path the product query path uses (query.py:405).
from tlsys import query as _qmod
_nq_def = NQ2(tl, idx, emb1)
check("default-mmr-lambda",
      _qmod.MMR_LAMBDA == 0.8
      and _nq_def._C("MMR_LAMBDA", _qmod.MMR_LAMBDA) == 0.8,
      f"{_qmod.MMR_LAMBDA}")

# Q3.2(c): emission is OWN fused support only -- region sums rank
# regions, never member scores (no free-riding). Own support is the
# lex/holon RRF plus the dense-atom RRF scaled by DENSE_WEIGHT (0.5),
# so each emitted score is a + 0.5*b with a, b in {1/(60+r)} | {0}.
_rrf1 = {1.0 / (60 + r) for r in range(100)} | {0.0}
_rrf = {a + 0.5 * b for a in _rrf1 for b in _rrf1}
_em = [e["emitted_score"] for e in dos["entries"]]
check("emission-own-support-only",
      len(_em) >= 1 and all(
          min(abs(s - w) for w in _rrf) < 1e-12 for s in _em),
      f"{_em}")

tl.trace.dump(os.path.join(tmp, "call-trace.json"))
tl.close()
print("store-root:", tmp)
print("RESULT:", "FAIL " + str(FAILS) if FAILS else "PASS")
sys.exit(1 if FAILS else 0)
