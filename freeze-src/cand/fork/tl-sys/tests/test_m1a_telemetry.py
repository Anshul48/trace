"""Track M1-A: bounded telemetry + paged reads.

Authority: tl-eval/evidence/m1-2026-10-06/FAILURE-ANALYSIS.md (F2) +
handoffs/TL-100M-DELIVERY-PLAN-2026-10-06.md section 2 (Durable
intake, Current metadata rows). Pinned env: HF_HOME=<repo>/
local-data/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0 (this file
needs no encoder: fake embeddings only). Scratch stores under
/tmp/tl-m1a-*/ only.

Contracts under test:
* CallTrace.summary() output IDENTICAL to the pre-M1 loop-over-
  calls formula for the same event stream (aggregate-on-log).
* Bounded recent-event deque (TRACE_RECENT_MAX=1000); .calls
  keeps its audited read contract (len/slice/eq/iterate of
  oldest->newest dicts); n_total/dropped_detail disclose.
* dump() writes aggregates + bounded recent + scope note.
* Optional streamed sink: False = declined/backpressure,
  raised = caught+counted; telemetry never breaks product.
* read_commits_iter yields the byte-identical row sequence as
  read_commits_all with bounded working memory; the concat
  form keeps its single-trace-record shape.

Run: tl-sys/.venv/bin/python tl-sys/tests/test_m1a_telemetry.py
"""
import inspect
import json
import os
import sys
import tempfile
import tracemalloc

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import (TRACE_RECENT_MAX, CallTrace,  # noqa: E402
                            TLStore)
from tlsys.ingest import ingest_docs  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 8


def _vec(seed):
    return [float((seed >> (4 * d)) & 1) for d in range(DIM)]


def emb(texts):
    return [_vec(abs(hash(t)) % 256) for t in texts]


def old_summary(events):
    """Pre-M1 summary formula (loop over every retained call)."""
    out = {}
    for c in events:
        k = (c["op"], c["outcome"])
        n, tot = out.get(k, (0, 0.0))
        out[k] = (n + 1, tot + c["ms"])
    return {f"{op}/{oc}": {"n": n, "ms_total": round(tot, 2)}
            for (op, oc), (n, tot) in sorted(out.items())}


def deep_size(obj, _seen=None):
    import collections  # noqa: E402
    _seen = _seen if _seen is not None else set()
    if id(obj) in _seen:
        return 0
    _seen.add(id(obj))
    n = sys.getsizeof(obj, 0)
    if isinstance(obj, dict):
        for k, v in obj.items():
            n += deep_size(k, _seen) + deep_size(v, _seen)
    elif isinstance(obj, (list, tuple, set, frozenset,
                          collections.deque)):
        for v in obj:
            n += deep_size(v, _seen)
    elif hasattr(obj, "__dict__"):
        n += deep_size(vars(obj), _seen)
    return n


OPS = [("commit_batch", "ok"), ("pin", "ok"),
       ("read_commits", "ok"), ("read_commits", "TRUNCATED"),
       ("read_artifact", "ok"), ("read_artifact", "INTEGRITY_FAILED"),
       ("pub_refs", "ok"), ("fence.acquire", "ok"),
       ("fence.release", "ok")]


def main():
    tmp = tempfile.mkdtemp(prefix="tl-m1a-")

    # -- (1) summary() IDENTICAL to the old loop formula -----------
    tr = CallTrace()
    events = []
    for i in range(2500):
        op, oc = OPS[i % len(OPS)]
        ms = (i % 7) * 0.1 + (i % 13) * 0.01 + 0.001
        detail = {"id": f"ev-{i}", "len": 100 + i, "digest_ok": True}
        tr.log(op, detail, ms, oc)
        events.append({"op": op, "detail": detail, "ms": ms,
                       "outcome": oc})
    check("summary-identical", tr.summary() == old_summary(events),
          "aggregate-on-log must match the loop formula exactly")
    check("summary-keys-sorted",
          list(tr.summary()) == sorted(tr.summary()))
    check("recent-max-default",
          TRACE_RECENT_MAX == 1000 and tr.recent_max == 1000,
          f"{TRACE_RECENT_MAX}/{tr.recent_max}")

    # -- (2) bounded recent window ---------------------------------
    check("recent-bounded", len(tr.calls) == 1000, len(tr.calls))
    check("recent-is-newest",
          [c["detail"]["id"] for c in tr.calls]
          == [f"ev-{i}" for i in range(1500, 2500)])
    check("recent-oldest-first",
          tr.calls[0]["detail"]["id"] == "ev-1500"
          and tr.calls[-1]["detail"]["id"] == "ev-2499")
    check("ntotal-disclosed", tr.n_total == 2500, tr.n_total)
    check("dropped-disclosed", tr.dropped_detail == 1500,
          tr.dropped_detail)
    small = CallTrace()
    for i in range(10):
        small.log("pin", {"triple": f"t{i}"}, 0.5, "ok")
    check("small-identical-to-old",
          len(small.calls) == 10 and small.n_total == 10
          and small.dropped_detail == 0
          and [c["detail"]["triple"] for c in small.calls]
          == [f"t{i}" for i in range(10)])
    zero = CallTrace(recent_max=0)
    zero.log("pin", {}, 1.0, "ok")
    check("recent-zero-aggregates-only",
          zero.calls == [] and zero.n_total == 1
          and zero.dropped_detail == 1
          and zero.summary() == {"pin/ok": {"n": 1,
                                            "ms_total": 1.0}},
          f"{zero.calls} {zero.summary()}")

    # -- (3) audited .calls read contract --------------------------
    # Under capacity the mark+slice idiom (test_relindex) is exact.
    trm = CallTrace()
    for i in range(5):
        trm.log("pin", {"triple": f"pre-{i}"}, 0.1, "ok")
    mark = len(trm.calls)
    trm.log("pin", {"triple": "mark-a"}, 0.25, "ok")
    trm.log("pin", {"triple": "mark-b"}, 0.25, "ok")
    check("calls-mark-slice",
          [c["detail"].get("triple") for c in trm.calls[mark:]]
          == ["mark-a", "mark-b"], trm.calls[mark:])
    check("calls-empty-slice-eq",
          trm.calls[len(trm.calls):] == [], "must equal []")
    check("calls-iter-ops",
          all(set(c) == {"t", "op", "detail", "ms", "outcome"}
              for c in trm.calls),
          "event dict shape preserved")
    # Past capacity .calls is the newest-1000 window: the 3 just
    # logged land at the tail, evicting the 3 oldest.
    tr.log("pin", {"triple": "mark-a"}, 0.25, "ok")
    tr.log("pin", {"triple": "mark-b"}, 0.25, "ok")
    tr.log("pin", {"triple": "mark-c"}, 0.25, "ok")
    check("calls-full-window-tail",
          len(tr.calls) == 1000
          and [c["detail"].get("triple") for c in tr.calls[-3:]]
          == ["mark-a", "mark-b", "mark-c"]
          and tr.calls[0]["detail"]["id"] == "ev-1503"
          and tr.dropped_detail == 1503,
          f"{len(tr.calls)} {tr.dropped_detail}")

    # -- (4) dump(): aggregates + bounded recent + scope note ------
    dp = os.path.join(tmp, "trace-dump.json")
    tr.dump(dp)
    with open(dp) as f:
        dumped = json.load(f)
    check("dump-keys",
          set(dumped) == {"candidate_rev", "scope_note", "n_total",
                          "recent_max", "dropped_detail", "summary",
                          "sink", "recent"}, sorted(dumped))
    check("dump-aggregates",
          dumped["n_total"] == tr.n_total == 2503
          and dumped["dropped_detail"] == tr.dropped_detail == 1503
          and dumped["recent_max"] == 1000
          and dumped["summary"] == tr.summary(),
          f"{dumped['n_total']}/{dumped['dropped_detail']}")
    check("dump-recent-bounded",
          len(dumped["recent"]) == 1000
          and dumped["recent"] == tr.calls, len(dumped["recent"]))
    check("dump-scope-note",
          isinstance(dumped["scope_note"], str)
          and "recent" in dumped["scope_note"]
          and "sink" in dumped["scope_note"],
          dumped["scope_note"][:80])
    old_shape = json.dumps(
        {"calls": [dict(e, t=0.0) for e in events]}, indent=1)
    new_bytes = os.path.getsize(dp)
    print(f"measure dump-bytes: old-shape={len(old_shape)} "
          f"new={new_bytes} "
          f"(2500 similar events; recent window 1000)")
    check("dump-bytes-bounded", new_bytes < len(old_shape) * 0.6,
          f"{new_bytes} vs {len(old_shape)}")
    old_retained = deep_size(events)
    new_retained = deep_size(tr._recent) + deep_size(tr._agg)
    print(f"measure trace-retained-bytes: old-list={old_retained} "
          f"new-deque+agg={new_retained}")
    check("trace-retained-bounded", new_retained < old_retained,
          f"{new_retained} vs {old_retained}")

    # -- (5) streamed sink -----------------------------------------
    got = []
    trs = CallTrace(sink=got.append)
    for i in range(100):
        trs.log("read_artifact", {"id": f"s{i}"}, 0.3, "ok")
    check("sink-accepts-all",
          len(got) == 100 and trs.sink_accepted == 100
          and trs.sink_dropped == 0 and trs.sink_errors == 0
          and [e["detail"]["id"] for e in got]
          == [f"s{i}" for i in range(100)],
          f"{len(got)}/{trs.sink_accepted}/{trs.sink_dropped}")
    state = {"n": 0}

    def declining(ev, _st=state):
        _st["n"] += 1
        return _st["n"] <= 5 or False

    trd = CallTrace(sink=declining)
    for i in range(20):
        trd.log("pin", {"i": i}, 0.1, "ok")
    check("sink-backpressure-disclosed",
          trd.sink_accepted == 5 and trd.sink_dropped == 15
          and trd.sink_errors == 0
          and trd.n_total == 20 and trd.summary()["pin/ok"]["n"]
          == 20,
          f"{trd.sink_accepted}/{trd.sink_dropped}/"
          f"{trd.sink_errors}")

    def raising(_ev):
        raise ValueError("sink boom")

    trr = CallTrace(sink=raising)
    try:
        for i in range(7):
            trr.log("pin", {"i": i}, 0.1, "ok")
        raised = False
    except ValueError:
        raised = True
    check("sink-raise-never-breaks",
          not raised and trr.sink_errors == 7
          and trr.sink_dropped == 7
          and trr.sink_first_error == "ValueError: sink boom"
          and trr.summary()["pin/ok"]["n"] == 7,
          f"{raised} {trr.sink_first_error}")
    trr.dump(os.path.join(tmp, "trace-sink.json"))
    with open(os.path.join(tmp, "trace-sink.json")) as f:
        sd = json.load(f)
    check("sink-disclosed-in-dump",
          sd["sink"] == {"accepted": 0, "dropped": 7, "errors": 7,
                         "first_error": "ValueError: sink boom"},
          sd["sink"])

    # -- (6) read_commits_iter == read_commits_all, byte-identical --
    sp = os.path.join(tmp, "store-it")
    tl = TLStore(sp, create=True, lease_owner="test-m1a")
    docs = [(f"m{i}", f"alpha doc number {i} beta gamma")
            for i in range(600)]
    ingest_docs(tl, docs, emb, store_id="m1a", place_xdoc=False)
    birth, epoch, mx, _t = tl.pin()
    full = tl.read_commits_all(birth, epoch, mx)
    check("shape-n-commits", len(full) == 1200, len(full))
    import types  # noqa: E402
    check("iter-is-generator",
          isinstance(tl.read_commits_iter(birth, epoch, mx),
                     types.GeneratorType))
    for pg in (1, 2, 7, 100, 50000):
        got = [tuple(r) for r in tl.read_commits_iter(
            birth, epoch, mx, page=pg)]
        if got != [tuple(r) for r in full]:
            check(f"iter-eq-concat-{pg}", False,
                  f"{len(got)} vs {len(full)} rows")
            break
    else:
        check("iter-eq-concat-all-pages", True)
    kf_c = [tuple(r) for r in tl.read_commits_all(
        birth, epoch, mx, kind="ACCEPT_ATOMS", page=7)]
    kf_i = [tuple(r) for r in tl.read_commits_iter(
        birth, epoch, mx, kind="ACCEPT_ATOMS", page=7)]
    check("iter-kind-filter", kf_i == kf_c and len(kf_i) == 1200,
          f"{len(kf_i)}/{len(kf_c)}")
    check("iter-kind-empty",
          list(tl.read_commits_iter(birth, epoch, mx, kind="NOPE"))
          == [] and tl.read_commits_all(birth, epoch, mx, kind="NOPE")
          == [])
    seqs = [r[0] for r in full]
    win_i = [tuple(r) for r in tl.read_commits_iter(
        birth, epoch, mx, min_seq=seqs[9], page=3)]
    check("iter-minseq-window", win_i == [tuple(r) for r in full][10:],
          "exclusive lower bound preserved")
    check("iter-empty-window",
          list(tl.read_commits_iter(birth, epoch, mx, min_seq=mx))
          == [])
    # early termination: first page only, then abandoned
    it = tl.read_commits_iter(birth, epoch, mx, page=50000)
    head = [tuple(next(it)) for _ in range(5)]
    it.close()
    check("iter-early-head",
          head == [tuple(r) for r in full][:5], head)
    # per-page trace events on the iterator (bounded by design)
    n_before = tl.trace.summary().get(
        "read_commits_iter/ok", {}).get("n", 0)
    n_rows = sum(1 for _ in tl.read_commits_iter(
        birth, epoch, mx, page=7))
    n_after = tl.trace.summary()["read_commits_iter/ok"]["n"]
    check("iter-page-trace",
          n_rows == 1200 and n_after - n_before == 172,
          f"rows={n_rows} pages={n_after - n_before}")
    # concat keeps its single-trace-record compat shape
    c0 = tl.trace.summary().get("read_commits_all/ok", {}).get("n", 0)
    tl.read_commits_all(birth, epoch, mx, page=7)
    c1 = tl.trace.summary()["read_commits_all/ok"]["n"]
    last = tl.trace.calls[-1]
    check("concat-single-trace-record",
          c1 - c0 == 1 and last["op"] == "read_commits_all"
          and set(last["detail"]) == {"gen", "kind", "n", "pages"}
          and last["detail"]["n"] == 1200
          and last["detail"]["pages"] == 172,
          f"{last}")
    check("concat-page-signature",
          str(inspect.signature(tl.read_commits_all))
          == str(inspect.signature(tl.read_commits_iter)),
          "same call shape for drop-in migration")

    # -- (7) iterator working memory << concat ---------------------
    tracemalloc.start()
    tracemalloc.reset_peak()
    n = 0
    h = 0
    for r in tl.read_commits_iter(birth, epoch, mx, page=100):
        n += 1
        h = (h + r[0]) % 1000003
    _cur_i, peak_i = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    rows = tl.read_commits_all(birth, epoch, mx)
    total = sum(r[0] for r in rows) % 1000003
    _cur_c, peak_c = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"measure iter-vs-concat: rows={n} hash={h}/{total} "
          f"iter-peak={peak_i} concat-peak={peak_c}")
    check("iter-same-content", n == len(rows) == 1200
          and h == total, f"{n}/{len(rows)}")
    check("iter-peak-bounded", peak_i < peak_c,
          f"iter={peak_i} concat={peak_c}")
    tl.close()

    print("store-root:", tmp)
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
