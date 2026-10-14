"""TRACE freeze-38 demo backend.

Runs the ACTUAL frozen HierQuery.guided/flat (fork/tl-sys/tlsys/query.py:1617/1764)
and product_pilot.tie_recall (tools/product_pilot.py:449) over a small sample
corpus built from the ACTUAL receipt probe vectors (data/probes.json, 120 x 384-d
cached encoder vectors from the 10M qualification). This is vector-probe mode:
there is no text encoder and no fake QA. The full 10M qualification record is
served separately at /api/evidence and is never recomputed here.

Freeze source: env TRACE_FREEZE_SRC, default ../freeze-src relative to this
folder (integrator: drop this folder in as demo-app/ beside freeze-src/).
Stdlib HTTP only; numpy is required because the frozen engine requires it.
"""
import hashlib
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
STATIC = HERE / "static"


def freeze_src():
    env = os.environ.get("TRACE_FREEZE_SRC")
    candidates = [Path(env)] if env else []
    candidates += [HERE.parent / "freeze-src" / "cand", HERE.parent / "freeze-src",
                   HERE.parent / "vm-recovery" / "cand" / "stack-fork" / "cand"]
    for c in candidates:
        if (c / "tools" / "product_pilot.py").exists():
            return c.resolve()
    raise RuntimeError("frozen source not found; set TRACE_FREEZE_SRC (tried: "
                       + ", ".join(str(c) for c in candidates) + ")")


SRC = freeze_src()
sys.path[:0] = [str(SRC / "tools"), str(SRC / "fork" / "tl-sys"), str(SRC)]
import numpy as np  # noqa: E402
import product_pilot  # noqa: E402  frozen tools/product_pilot.py
from tlsys.query import HierQuery  # noqa: E402  frozen fork/tl-sys/tlsys/query.py

EXPECTED_FREEZE_SHA = "38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54"
FREEZE_SHA = hashlib.sha256((SRC / "SOURCEFREEZE.json").read_bytes()).hexdigest()
if FREEZE_SHA != EXPECTED_FREEZE_SHA:
    raise RuntimeError(f"source-freeze identity mismatch: got {FREEZE_SHA}, expected {EXPECTED_FREEZE_SHA}; refusing to start")
PROBES = json.loads((DATA / "probes.json").read_text())
RESULT = json.loads((DATA / "result.json").read_text())
ORACLE = json.loads((DATA / "ORACLE.json").read_text())

VECS = np.asarray([p["vector"] for p in PROBES], dtype=np.float64)
VECS = VECS / np.linalg.norm(VECS, axis=1)[:, None]
AIDS = [f"a{i}" for i in range(len(PROBES))]
STORE = {}


class DemoArtifacts:
    """In-memory artifact store; read_artifact verifies sha256 like the frozen path expects."""

    def read_artifact(self, ref, expect_digest=None):
        body = STORE[ref]
        if expect_digest and hashlib.sha256(body).hexdigest() != expect_digest:
            raise ValueError("digest mismatch")
        return body


def build_index(exclude_sources=frozenset()):
    atoms, leaves, parents, holons = {}, {}, {}, {}
    keep = []
    for i, p in enumerate(PROBES):
        if exclude_sources and set(p["sources"]) & set(exclude_sources):
            continue
        keep.append(i)
        text = (f"Receipt probe #{p['id']} ({p['family']}) from "
                f"{', '.join(p['sources'])} - 384-d cached encoder vector; "
                "original chunk text is not in the recovered receipts.")
        digest = hashlib.sha256(text.encode()).hexdigest()
        STORE[digest] = text.encode()
        atoms[AIDS[i]] = {"descriptor": VECS[i], "doc_id": p["sources"][0],
                          "span": "receipt-probe", "text_art": digest,
                          "text_digest": digest}
    groups = [keep[i:i + 10] for i in range(0, len(keep), 10)]
    for li, grp in enumerate(groups):
        cen = VECS[grp].mean(axis=0)
        cen = cen / np.linalg.norm(cen)
        leaves[f"leaf{li}"] = {"descriptor": cen,
                               "members": [AIDS[j] for j in grp]}
        holons[f"leaf{li}"] = {"children": []}
    for pi in range(0, len(groups), 3):
        kids = [f"leaf{li}" for li in range(pi, min(pi + 3, len(groups)))]
        cen = np.mean([leaves[k]["descriptor"] for k in kids], axis=0)
        cen = cen / np.linalg.norm(cen)
        parents[f"par{pi // 3}"] = {"descriptor": cen, "children": kids}
        holons[f"par{pi // 3}"] = {"children": kids}
    return SimpleNamespace(atoms=atoms, seg_leaves=leaves, seg_parents=parents,
                           holons=holons, retired_aids=set(),
                           triple=("demo-sample", 0, len(atoms)))


def recorded_row(probe_id, lso):
    for q in RESULT["evaluation"]["queries"]:
        if q["probe"] == probe_id and q["leave_source_out"] == lso:
            return q
    return None


def run_query(probe_id, top_k=10, mode="both", lso=False):
    if not isinstance(probe_id, int) or not 0 <= probe_id < len(PROBES):
        raise ValueError(f"probe_id must be an integer 0..{len(PROBES) - 1}")
    if mode not in ("both", "guided", "flat"):
        raise ValueError("mode must be both, guided, or flat")
    top_k = max(1, min(int(top_k), 25))
    probe = PROBES[probe_id]
    qvec = VECS[probe_id]
    idx = build_index(set(probe["sources"]) if lso else frozenset())
    hq = HierQuery(DemoArtifacts(), idx, lambda x: x)
    aids = sorted(idx.atoms)
    mat = np.asarray([idx.atoms[a]["descriptor"] for a in aids])
    scores = mat @ qvec  # exact oracle, as evaluate_facade (product_pilot.py:500)
    oracle = [aids[i] for i in np.argsort(-scores, kind="stable")[:top_k]]
    out = {"probe": {"id": probe["id"], "family": probe["family"],
                     "sources": probe["sources"]},
           "mode": mode, "top_k": top_k, "leave_source_out": bool(lso),
           "sample_atoms": len(aids),
           "oracle_top": oracle,
           "scope": "sample corpus of 120 receipt probe vectors; not the 10M store",
           "frozen": {"source": str(SRC), "sourcefreeze_sha256": FREEZE_SHA,
                      "guided": "fork/tl-sys/tlsys/query.py:1617 HierQuery.guided",
                      "flat": "fork/tl-sys/tlsys/query.py:1764 HierQuery.flat",
                      "tie_recall": "tools/product_pilot.py:449 tie_recall"},
           "recorded_10m_row": recorded_row(probe_id, bool(lso))}
    if mode in ("both", "guided"):
        rows, report = hq.guided(qvec, top_parents=4, top_children=8,
                                 top_atoms=top_k)
        got = [r["aid"] for r in rows]
        out["guided"] = {"rows": rows, "report": report,
                         "recall_at_k_vs_sample_oracle":
                         product_pilot.tie_recall(scores, aids, got, k=top_k)}
    if mode in ("both", "flat"):
        budget = 40
        if "guided" in out:
            w = out["guided"]["report"]["work"]
            budget = w["parents_scored"] + w["children_scored"] + w["atoms_scored"]
        rows, report = hq.flat(qvec, total_budget=budget, top_atoms=top_k)
        got = [r["aid"] for r in rows]
        out["flat"] = {"rows": rows, "report": report, "budget": budget,
                       "recall_at_k_vs_sample_oracle":
                       product_pilot.tie_recall(scores, aids, got, k=top_k)}
    return out


def evidence():
    ev = RESULT["evaluation"]["summary"]
    inp = RESULT["input"]
    return {"freeze_sha256": FREEZE_SHA,
            "oracle_status": ORACLE["status"], "oracle_queries": ORACLE["queries"],
            "oracle_counts_match": ORACLE["counts_match"], "pin": ORACLE["pin"],
            "store_before_after_identical":
                ORACLE["store_before"] == ORACLE["store_after"],
            "input": {k: inp[k] for k in ("target_tokens", "actual_tokens",
                        "complete_documents", "atoms", "cache_misses",
                        "normalization")},
            "summary": ev,
            "scope": ("Separate full 10M qualification record (VM receipt). "
                      "Harness recall / oracle agreement, not semantic IR or nDCG. "
                      "The live demo above runs the same frozen query code on a "
                      "120-vector sample only.")}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(fmt % args + "\n")

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json({"ok": True, "freeze_sha256": FREEZE_SHA,
                                   "freeze_src": str(SRC),
                                   "sample_probes": len(PROBES)})
        if path == "/api/probes":
            return self.send_json({"probes": [
                {"id": p["id"], "family": p["family"], "sources": p["sources"]}
                for p in PROBES]})
        if path == "/api/evidence":
            return self.send_json(evidence())
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (STATIC / name).resolve()
        if STATIC.resolve() in f.parents and f.is_file():
            body = f.read_bytes()
            ctype = {"html": "text/html", "css": "text/css",
                     "js": "text/javascript"}.get(f.suffix[1:], "text/plain")
            self.send_response(200)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        return self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/query":
            return self.send_json({"error": "not found"}, 404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            result = run_query(req.get("probe_id"), req.get("top_k", 10),
                               req.get("mode", "both"),
                               bool(req.get("leave_source_out", False)))
            return self.send_json(result)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.send_json({"error": str(exc)}, 400)
        except Exception as exc:  # fail closed, no fake results
            return self.send_json({"error": f"engine error: {exc!r}"}, 500)


def main(port=8765):
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
