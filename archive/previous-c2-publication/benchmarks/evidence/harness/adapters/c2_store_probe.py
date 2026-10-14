"""lane-BENCH10M A3: deployment-condition probe on the shipped 10M store.

Opens a GCS-fetched COPY of the shipped store read-only at the
pristine pin, loads the MiniLM encoder once (resident), then serves
K sequential NarrowQuery requests at the adopted M80-P100-A40
budgets in one persistent process. Records walls + conditions.
Not a TB backend (the store corpus has no public qrels, so there
is no scored quality here); a conditions datapoint only.

Mirrors lane-S5S s5s_serve_demo.py mechanics (fresh NarrowIndex
attach per request + one dossier answer, no digest/audit on the
request clock) with the shipped query budgets applied.

Usage (on VM, store copy + staged checkout already in place):

    HF_HOME=/srv/tl/weights python c2_store_probe.py \\
        ROOT STORE BIRTH EPOCH SEQ OUT [--requests K] [--query Q]

Read-only wrt the store. Never point STORE at a live build dir.
"""

import json
import os
import sys
import time

ROOT, STORE, BIRTH, EPOCH, SEQ, OUT = sys.argv[1:7]
EPOCH = int(EPOCH)
SEQ = int(SEQ)
args = sys.argv[7:]

BUDGETS = {"M_REGIONS": 80, "PRUNE_CAP": 100, "MAX_ENTRIES": 40}
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args) and not args[i + 1].startswith("--"):
            return args[i + 1]
        return True
    return default


K = int(opt("--requests", "5"))
Q = opt("--query", "take")

sys.path.insert(0, os.path.join(ROOT, "tl-sys"))
sys.dont_write_bytecode = True  # never write into the staged checkout
os.environ.setdefault("HF_HOME", "/srv/tl/weights")
os.environ["HF_HUB_OFFLINE"] = "1"

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402

t0 = time.monotonic()
tl = TLStore(STORE, create=False, lease_owner="c2-bench10m-probe")
pin = tl.pin()
assert (pin[0], pin[1], pin[2]) == (BIRTH, EPOCH, SEQ), pin
t_open = time.monotonic()

from sentence_transformers import SentenceTransformer  # noqa: E402
st = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION)
t_enc = time.monotonic()


def emb(q):
    import numpy as _np
    v = st.encode(q, convert_to_numpy=True, show_progress_bar=False)
    return [float(x) for x in _np.ravel(v)]


reqs = []
for i in range(K):
    r0 = time.monotonic()
    t_a0 = time.monotonic()
    idx = NarrowIndex(tl, pin)
    t_a1 = time.monotonic()
    nq = NarrowQuery(tl, idx, emb, cfg=dict(BUDGETS))
    dos, rec = nq.run(Q)
    t_q1 = time.monotonic()
    assert rec["execution"]["status"] == "complete", rec["execution"]
    reqs.append({
        "attach_ms": round((t_a1 - t_a0) * 1000.0, 2),
        "query_ms": round((t_q1 - t_a1) * 1000.0, 2),
        "request_ms": round((t_q1 - r0) * 1000.0, 2),
        "n_entries": len(dos["entries"]),
        "serving_view": type(getattr(idx, "serving_view",
                                     getattr(idx, "_view", None))).__name__,
    })
    print(f"request {i} attach={reqs[-1]['attach_ms']} "
          f"query={reqs[-1]['query_ms']} "
          f"request={reqs[-1]['request_ms']} entries={reqs[-1]['n_entries']}",
          flush=True)

out = {
    "kind": "c2-bench10m-store-probe",
    "pin": [pin[0], pin[1], pin[2]],
    "budgets": BUDGETS,
    "model": {"id": MODEL_ID, "revision": MODEL_REVISION},
    "condition": "persistent process + resident encoder; read-only store copy",
    "store_open_ms": round((t_open - t0) * 1000.0, 2),
    "encoder_load_ms": round((t_enc - t_open) * 1000.0, 2),
    "query": Q,
    "requests": reqs,
    "process_wall_s": round(time.monotonic() - t0, 2),
}
with open(OUT, "w") as f:
    json.dump(out, f, sort_keys=True)
print("C2-STORE-PROBE: DONE", OUT)
