"""Integrated 10M gate runner (M2 track C): G0-G6 in one parameterized run.

Covers Narrow + relational + cross-topic + qualifier classes through their
real entry points, equal-work prefix appends, mixed serving/maintenance/
publication, and bounded isolated oracles. Reads product code only; writes
only under --out. run_quality.py is NOT used (Narrow-only); this is the
new runner. SciFact/809/fresh inputs are never confirmation inputs here.

Usage (fixture tier, CPU, from repo root):
  HF_HOME=<repo>/local-data/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0 \\
    tl-sys/.venv/bin/python tl-eval/gate_runner/run_integrated_gate.py \\
      --tier fixture --out tl-eval/evidence/m2-2026-10-06/trackC/fixture-01

Full tier (coordinator; pins must be frozen in CONFIRM-INPUTS first):
  ... run_integrated_gate.py --tier full --docs <docs.jsonl> \\
      --cache-dir <emb_cache> --out <evidence-dir> \\
      --suite-record <suites.json>
"""

import argparse
import copy
import gc
import json
import os
import resource
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.normpath(os.path.join(ROOT, "tl-sys")))
sys.path.insert(0, os.path.normpath(os.path.join(ROOT, "tl-eval")))
sys.path.insert(0, HERE)

from gate_lib import (StreamWriter, Timer, assess_catchup,  # noqa: E402
                      assess_fixed_work,
                      audit_export_coverage, checkpoint_usage,
                      classify_outcome, default_oracle_cap_mb,
                      dir_size_bytes, drain_nav_counters,
                      has_trace_path, is_placeholder_sha,
                      journal_usage, load_json, manifest_coverage,
                      manifest_entries, plan_oracle_sample,
                      plan_workload_appends,
                      probe_retirement_capability, proc_tree_sample,
                      receipt_work, resolve_entry_text,
                      resolve_hierarchy_trace, run_capped,
                      score_expected, select_worker_peak,
                      sha256_bytes, sha256_file, snapshot_store,
                      tok_v1_count, utc_now, validate_source_pins,
                      verify_manifest, vram_sample, write_json,
                      python_identity)

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs, chunk_text  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery, HierQuery  # noqa: E402
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys import maint as _maint  # noqa: E402
from tlsys import relations as _relations  # noqa: E402
from tlsys import relquery as _relquery  # noqa: E402
from tlsys import export as _export  # noqa: E402


FAKE_DIM = 16
FAKE_BUCKETS = {"mycorrhizal": 0, "forest": 0, "nutrient": 0, "sharing": 0,
                "fungi": 0, "pine": 0, "seedling": 0, "restoration": 0,
                "tidal": 1, "marsh": 1, "crab": 1, "mudflat": 1,
                "granite": 2, "cliff": 2, "falcon": 2, "sand": 2,
                "quasar": 3, "blazar": 3, "galax": 3, "radio": 3,
                "telescope": 3, "fluoride": 4, "fluoridation": 4,
                "enamel": 4, "dental": 4, "dentist": 4,
                "cartographer": 5, "harbor": 5, "chart": 5, "ferry": 5,
                "captain": 5, "copper": 6, "smelter": 6, "ore": 6,
                "railway": 6, "ingot": 6, "factor": 6, "tree": 7,
                "network": 7, "link": 7, "underground": 7, "season": 7,
                "shelter": 8, "nest": 8, "host": 8, "yearly": 8,
                "thread": 9, "reach": 9, "meet": 9, "grass": 9,
                "jet": 10, "outshine": 10, "distant": 10, "nightly": 10,
                "treatment": 11, "strengthen": 11, "affirm": 11,
                "communit": 11, "water": 11, "critic": 12, "dispute": 12,
                "safety": 12, "claim": 12, "risk": 12, "oppos": 12,
                "mandate": 12, "apprentice": 13, "survey": 13, "draft": 13,
                "coastal": 13, "resurvey": 13, "correct": 13, "complain": 13,
                "loudly": 13, "refine": 14, "beside": 14, "load": 14}


def _fake_vec(text):
    import math
    v = [0.05] * FAKE_DIM
    low = (text or "").lower()
    for kw, b in FAKE_BUCKETS.items():
        if kw in low:
            v[b] += 1.0
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


class FakeEncoder:
    """Deterministic fixture encoder (fixture tier ONLY)."""

    name = "fake-encoder-v1"

    def embed_texts(self, texts):
        return [_fake_vec(t) for t in texts]

    def embed_query(self, q):
        return _fake_vec(q)


def ws_tokens(text):
    return len((text or "").split())


class Cell:
    """One gate cell accumulator: checks PASS/FAIL + measurements."""

    def __init__(self, name):
        self.name = name
        self.checks = []
        self.measurements = {}

    def check(self, name, ok, detail=None):
        self.checks.append({"name": name, "pass": bool(ok),
                            "detail": detail})
        return bool(ok)

    def measure(self, k, v):
        self.measurements[k] = v

    @property
    def verdict(self):
        return "PASS" if all(c["pass"] for c in self.checks) else "FAIL"

    def to_dict(self):
        return {"cell": self.name, "verdict": self.verdict,
                "checks": self.checks, "measurements": self.measurements}


# ------------------------------------------------------------------ queries

def _trim(v, cap=25, _depth=0):
    """Bound report details: long lists collapse to n + head."""
    if _depth > 4:
        return {"truncated": True}
    if isinstance(v, list) and len(v) > cap:
        return {"n": len(v),
                "head": [_trim(x, cap, _depth + 1)
                         for x in v[:cap]]}
    if isinstance(v, dict):
        return {k: _trim(val, cap, _depth + 1)
                for k, val in v.items()}
    return v


def run_case(class_name, case, tl, idx, emb1, criteria):
    """Run one confirmation case through its real entry point.

    Returns a streamed row (no retention beyond the row). Raises
    nothing: errors are classified into the row.
    """
    cls = criteria["classes"][class_name]
    cfg = copy.deepcopy(cls.get("cfg") or {})
    q = case["query"]
    t0 = time.time()
    err, dos, rec = None, {"entries": []}, None
    nq = dq = None
    try:
        if class_name == "narrow":
            nq = NarrowQuery(tl, idx, emb1, cfg=cfg)
            dos, rec = nq.run(q)
        elif class_name == "relational":
            dq = DossierQuery(tl, idx, emb1, cfg=cfg)
            dos, rec = dq.run(q)
        elif class_name == "cross_topic":
            dq = DossierQuery(tl, idx, emb1, cfg=cfg)
            dos, rec = dq.run(q, topics=case.get("topics"))
        elif class_name == "qualifier":
            dq = DossierQuery(tl, idx, emb1, cfg=cfg)
            dos, rec = dq.run(q)
        else:
            raise ValueError(f"unknown class {class_name}")
    except Exception as e:  # noqa: BLE001 - classified, never raised
        err = f"{type(e).__name__}:{str(e)[:300]}"
    ms = (time.time() - t0) * 1000.0
    entries = (dos or {}).get("entries") or []
    nav = drain_nav_counters(nq, dq, idx)
    outcome = classify_outcome(entries, rec, err)
    pcauses = {}
    for p in ((rec or {}).get("partials") or [])[:25]:
        k = str((p or {}).get("cause"))[:80]
        pcauses[k] = pcauses.get(k, 0) + 1
    served_docs, served_texts = [], []
    for e in entries:
        served_docs.append(e.get("doc_id"))
        t, why = resolve_entry_text(tl, idx, e)
        served_texts.append(t)
        if why:
            e = dict(e)
            e["_text_grounding"] = why
    exp = score_expected(served_docs, served_texts,
                         case.get("expected") or {})
    row = {"class": class_name, "case": case.get("id"),
           "outcome": outcome, "err": err, "ms": round(ms, 2),
           "served_docs": served_docs,
           "expected": exp,
           "work": receipt_work(rec),
           "nav_totals": nav,
           "exec_status": ((rec or {}).get("execution") or {}).get(
               "status"),
           "partial_causes": pcauses,
           "entry_point": cls["entry_point"]}
    if class_name == "relational" and rec:
        m = (rec.get("metrics") or {}).get("dossier") or {}
        row["traversal"] = {
            "hops_used": (rec.get("metrics") or {}).get("H_hops"),
            "edges_examined": m.get("lateral_edges_examined"),
            "lateral_added": m.get("lateral_added"),
            "ineligible": m.get("lateral_ineligible"),
            "shape": m.get("shape")}
    if class_name == "cross_topic" and rec:
        m = (rec.get("metrics") or {}).get("dossier") or {}
        row["coverage"] = {
            "topics_run": m.get("topics_run"),
            "topics_deferred": m.get("topics_deferred"),
            "sections": m.get("sections")}
    return row, entries, rec


def topic_hits(case, served_docs, doc_topics):
    """How many case topics have >=1 served expected doc."""
    topics = case.get("topics") or []
    hit = 0
    for t in topics:
        want = set(doc_topics.get(t, ())) & set(case.get(
            "expected", {}).get("docs", ()))
        if want & set(served_docs):
            hit += 1
    return hit


class AnchorResolutionError(ValueError):
    """Unresolvable relation/signal anchor (fail-closed refusal)."""


def _ordered_doc_aids(doc_id, atoms):
    """[(aid, span_start)] for one doc, chunk-ordinal ascending.

    Order is by committed span start (chunk order), aid
    tie-broken: deterministic under any hash seed, independent of
    dict enumeration order.
    """
    out = []
    for aid, meta in (atoms or {}).items():
        if (meta or {}).get("doc_id") != doc_id:
            continue
        span = (meta or {}).get("span") or [0, 0]
        out.append((aid, span[0]))
    out.sort(key=lambda t: (t[1], t[0]))
    return out


def resolve_doc_anchor(doc_id, atoms, texts, anchor_spans=()):
    """Owning-chunk aid for one relation endpoint / qual signal.

    atoms: {aid: meta} with doc_id/span (committed state).
    texts: {aid: chunk text} for the doc's atoms.
    anchor_spans: verbatim source spans (any-match); the anchor is
      the lowest-ordinal chunk containing >=1 span (the same
      substring rule the G3 assessment uses).
    Single-atom docs resolve without spans (unambiguous).
    Anything else unresolvable raises AnchorResolutionError:
      unknown doc, multi-atom doc without spans (the old silent
      last-enumerated collapse), or spans no chunk contains.
    """
    cands = _ordered_doc_aids(doc_id, atoms)
    if not cands:
        raise AnchorResolutionError(
            f"anchor doc {doc_id!r}: no committed atoms")
    spans = [s for s in (anchor_spans or ()) if s]
    if len(cands) == 1 and not spans:
        return cands[0][0]
    if not spans:
        raise AnchorResolutionError(
            f"anchor doc {doc_id!r}: {len(cands)} committed atoms "
            f"and no anchor spans (refusing silent collapse)")
    for aid, _start in cands:
        body = (texts or {}).get(aid)
        if body is None:
            raise AnchorResolutionError(
                f"anchor doc {doc_id!r}: no text for atom "
                f"{aid[:16]} (read the doc's chunks first)")
        if any(sp in body for sp in spans):
            return aid
    raise AnchorResolutionError(
        f"anchor doc {doc_id!r}: no committed chunk contains "
        f"the anchor spans")


def resolve_relation_endpoints(rel_specs, atoms, texts):
    """[(src_aid, dst_aid)] per spec, source-grounded.

    Per-endpoint spans ride spec["anchors"] = {"src": [...],
    "dst": [...]} (optional; absent = unambiguous-single-atom
    only, else AnchorResolutionError).
    """
    out = []
    for rs in rel_specs:
        anch = rs.get("anchors") or {}
        out.append((
            resolve_doc_anchor(rs["src"], atoms, texts,
                               anch.get("src") or ()),
            resolve_doc_anchor(rs["dst"], atoms, texts,
                               anch.get("dst") or ())))
    return out


def resolve_signal_anchors(sig_specs, atoms, texts):
    """[aid] per signal spec, source-grounded.

    Spans ride spec["anchors"] = [...] (optional; same
    unambiguous-single-atom rule as relations).
    """
    return [resolve_doc_anchor(ss["doc"], atoms, texts,
                               ss.get("anchors") or ())
            for ss in sig_specs]


# ------------------------------------------------- lifecycle exercises
# Behavioral retirement/correction evidence on an ISOLATED scratch
# store (never the confirmation store: both paths commit). Wired to
# the v3 executable contract (launch-20261006T1237Z /
# lane-v3-product/contract-v3.md, sole writer: v3 product; ACK v3):
# entry names and frozen formats are asserted exactly; drift fails
# closed. Retirement declares `retires` (consequential) and commits
# only with valid per-operation approval refs; fixture approval ids
# are fixtures (fixture- prefix), never operator consent.

def _default_embeds(embed_texts, embed_query):
    if embed_texts is None or embed_query is None:
        _fx = FakeEncoder()
        return _fx.embed_texts, _fx.embed_query
    return embed_texts, embed_query


def exercise_retirement(store_root, docs, query_text, retire_doc,
                        reason="gate-probe", embed_texts=None,
                        embed_query=None, place_xdoc=True,
                        expect_docs=None, approvals=None,
                        approval_id="fixture-v3-gate-retire",
                        profile=None):
    """Approval-gated retire -> serving-excluded -> export-omits.

    Contract-v3 probe (approved + refused + ACK + retry + reopen).
    docs: [(doc_id, text)] on a fresh scratch store. Serves
    query_text, exercises the REFUSED paths first (missing /
    malformed / invalid approval refs must fail closed with no
    commit and no serving/export eligibility change), then retires
    a served doc with a valid fixture approval, reruns (must be
    absent), checks the disclosed omission identity, ACKs the
    commit, verifies the committed stage-2 ref shape, and checks
    idempotent retry (no approval needed when nothing commits)
    and reopen identity. retire_doc names the doc to retire; None
    retires the first served doc grounded in expect_docs (the
    contract sequence retires "the served doc(s)"). approvals is
    an explicit per-doc approvals dict or None (auto-build one
    user fixture leg for the retiring doc). Every fixture
    approval/grant id used here MUST carry a fixture- prefix.
    Returns a report with supported True ONLY when every
    behavioral step + frozen format assert holds. Raises nothing
    for product-shape mismatches (structured failure); unexpected
    exceptions propagate for the caller to record as errors (not
    gaps).
    """
    from tlsys import export as _exp
    from tlsys.index import NarrowIndex as _NI
    from tlsys.ingest import ingest_docs as _ing
    from tlsys.query import NarrowQuery as _NQ
    from tlsys.store_if import TLStore as _TLS
    try:
        from tlsys import lifecycle as _lc
    except ImportError:
        return {"supported": False, "failed_step": "import",
                "detail": "tlsys.lifecycle absent (capability gap)"}
    emb_t, emb_q = _default_embeds(embed_texts, embed_query)
    rep = {"supported": False, "store_root": store_root,
           "retire_doc": retire_doc, "reason": reason}

    def _fail(step, detail):
        rep["failed_step"] = step
        rep["detail"] = detail
        return rep

    def _served():
        _ix = _NI(tl, tl.pin())
        _nq = _NQ(tl, _ix, emb_q, cfg={})
        _dos, _rec = _nq.run(query_text)
        return sorted(e.get("doc_id") for e in
                      (_dos.get("entries") or []))

    def _export_digest():
        _x = _exp.export_store(tl, include_text=True)
        _x.pop("exported_at", None)
        return sha256_bytes(json.dumps(_x, sort_keys=True,
                                       default=str).encode())

    tl = _TLS(store_root, create=True,
              lease_owner="gate-retire-probe")
    try:
        _ing(tl, list(docs), emb_t, store_id="gate-retire",
             place_xdoc=place_xdoc, progress_journal=True,
             profile=profile)
        pin0 = tl.pin()
        idx0 = _NI(tl, pin0)
        nq0 = _NQ(tl, idx0, emb_q, cfg={})
        dos0, _rec0 = nq0.run(query_text)
        served0 = sorted(e.get("doc_id") for e in
                         (dos0.get("entries") or []))
        rep["served_before"] = served0
        if retire_doc is None:
            _pool = [d for d in served0
                     if expect_docs is None or d in expect_docs]
            if not _pool:
                return _fail(
                    "serve-before",
                    f"no grounded doc served pre-retire: "
                    f"{served0}")
            retire_doc = _pool[0]
            rep["retire_doc"] = retire_doc
        if retire_doc not in served0:
            return _fail("serve-before",
                         f"{retire_doc} not served pre-retire: "
                         f"{served0}")
        # Refused paths first: every bad-ref attempt must raise the
        # contract error with NO commit and NO serving/export
        # eligibility change (pin triple + served docs + export
        # digest identical throughout).
        _others = [d for d, _t in docs if d != retire_doc]
        refused_table = [
            ("missing-approvals", None, ValueError, None),
            ("missing-entry", {}, ValueError, None),
            ("malformed-user-leg",
             {retire_doc: {"type": "user"}}, ValueError, None),
            ("malformed-empty-id",
             {retire_doc: {"type": "user", "approval_id": ""}},
             ValueError, None),
            ("unknown-type",
             {retire_doc: {"type": "owner",
                           "approval_id": "fixture-x"}},
             ValueError, None),
            ("unknown-grant",
             {retire_doc: {"type": "grant",
                           "grant_id": "fixture-no-such-grant"}},
             RuntimeError, "GRANT_INVALID"),
        ]
        if _others:
            refused_table.insert(
                2, ("wrong-doc-entry",
                    {_others[0]: {"type": "user",
                                  "approval_id": approval_id}},
                    ValueError, None))
        refused_out, _exp_before = [], _export_digest()
        for _name, _appr, _exc, _code in refused_table:
            _pin_b, _srv_b = tl.pin()[3], _served()
            try:
                _r = _lc.retire_docs(tl, [retire_doc],
                                     reason=reason,
                                     store_id="gate-retire",
                                     approvals=_appr)
            except _exc as _e:
                _ok = _code is None or _code in str(_e)
                _row = {"case": _name, "refused": bool(_ok),
                        "exc": f"{type(_e).__name__}:"
                               f"{str(_e)[:120]}",
                        "pin_same": tl.pin()[3] == _pin_b,
                        "serving_same": _served() == _srv_b}
            except Exception as _e:  # noqa: BLE001 - wrong error
                _row = {"case": _name, "refused": False,
                        "exc": f"WRONG-ERROR:{type(_e).__name__}:"
                               f"{str(_e)[:120]}",
                        "pin_same": tl.pin()[3] == _pin_b,
                        "serving_same": _served() == _srv_b}
            else:
                _row = {"case": _name, "refused": False,
                        "exc": f"COMMITTED:{_r.get('retired')}",
                        "pin_same": tl.pin()[3] == _pin_b,
                        "serving_same": _served() == _srv_b}
            refused_out.append(_row)
            if not (_row["refused"] and _row["pin_same"]
                    and _row["serving_same"]):
                rep["refused_paths"] = refused_out
                return _fail("refused-path", _row)
        rep["refused_paths"] = refused_out
        rep["refused_export_same"] = (
            _export_digest() == _exp_before)
        if not rep["refused_export_same"]:
            return _fail("refused-path",
                         "export changed across refusals")
        # Approved path: explicit approvals pass through verbatim;
        # None auto-builds one user fixture leg for the retiring
        # doc. Fixture legs MUST carry a fixture- prefix (never
        # operator consent); anything else fails the probe closed.
        if approvals is None:
            approvals = {retire_doc: {"type": "user",
                                      "approval_id": approval_id}}
        for _d, _leg in approvals.items():
            _fid = (_leg or {}).get("approval_id") or (
                _leg or {}).get("grant_id")
            if not (isinstance(_fid, str)
                    and _fid.startswith("fixture-")):
                return _fail("approval-not-fixture",
                             {"doc": _d, "leg": _leg})
        rep["approvals_used"] = approvals
        _pin_b = tl.pin()
        rrep = _lc.retire_docs(tl, [retire_doc], reason=reason,
                               store_id="gate-retire",
                               approvals=approvals)
        if set(rrep) != {"retired", "already_retired", "ops",
                         "seqs", "n_commits", "catchup"}:
            return _fail("report-shape", sorted(rrep))
        if rrep.get("retired") != [retire_doc]:
            return _fail("retire-ack", rrep.get("retired"))
        if rrep.get("n_commits") != 1:
            return _fail("retire-n-commits",
                         rrep.get("n_commits"))
        rep["retire_report"] = {k: rrep[k] for k in
                                ("retired", "already_retired",
                                 "n_commits")}
        # ACK: the retiring op has a committed queryable outcome.
        try:
            _ack_out, _ack_gen = tl.cm.notify(
                rrep["ops"][retire_doc])
            _ack = json.loads(_ack_out)
        except Exception as e:  # noqa: BLE001 - finding
            return _fail("retire-ack-outcome",
                         f"{type(e).__name__}:{str(e)[:160]}")
        if not (_ack.get("committed") is True
                and _ack.get("seq") == rrep["seqs"][retire_doc]
                and _ack.get("kind") == "ACCEPT_ATOMS"):
            return _fail("retire-ack-outcome", _ack)
        rep["ack"] = {k: _ack.get(k) for k in
                      ("committed", "seq", "kind")}
        # Committed stage-2 ref: exact frozen shape, bound to this
        # op's pre-commit pin + active policy + passed leg.
        try:
            _con = tl.store.open_db()
            try:
                _arow = _con.execute(
                    "SELECT approval_ref FROM commits WHERE seq=?",
                    (rrep["seqs"][retire_doc],)).fetchone()
            finally:
                _con.close()
            _aref = json.loads(_arow[0])
        except Exception as e:  # noqa: BLE001 - finding
            return _fail("approval-ref-read",
                         f"{type(e).__name__}:{str(e)[:160]}")
        if set(_aref) != {"stage", "policy_version",
                          "pinned_generation", "assessment",
                          "approval", "scope"}:
            return _fail("approval-ref-shape", sorted(_aref))
        _dh = (_aref.get("assessment") or {}).get("diff_hash")
        _leg_used = approvals[retire_doc]
        _leg_want = {"type": _leg_used["type"]}
        _leg_want["approval_id" if _leg_used["type"] == "user"
                  else "grant_id"] = _leg_used.get(
                      "approval_id") or _leg_used.get("grant_id")
        if not (_aref.get("stage") == 2
                and _aref.get("scope") == "ACCEPT_ATOMS"
                and _aref.get("pinned_generation")
                == [_pin_b[0], _pin_b[1], _pin_b[2]]
                and _aref.get("policy_version")
                == tl.current_policy_version()
                and set(_aref.get("assessment") or {})
                == {"diff_hash"}
                and isinstance(_dh, str) and len(_dh) == 64
                and _aref.get("approval") == _leg_want):
            return _fail("approval-ref-binding",
                         {"stage": _aref.get("stage"),
                          "scope": _aref.get("scope"),
                          "pinned": _aref.get("pinned_generation"),
                          "want_pin": [_pin_b[0], _pin_b[1],
                                       _pin_b[2]],
                          "policy": _aref.get("policy_version"),
                          "approval": _aref.get("approval")})
        rep["approval_ref"] = _aref
        pin1 = tl.pin()
        truth = _lc.read_retirements(tl, pin1)
        entry = (truth or {}).get(retire_doc)
        if not entry or set(entry) != {"seq", "op_id", "reason"}:
            return _fail("read-parity", entry)
        if (entry["op_id"] != rrep["ops"][retire_doc]
                or entry["seq"] != rrep["seqs"][retire_doc]):
            return _fail("read-parity", {"entry": entry,
                                         "report": rrep["ops"]})
        rep["parity"] = True
        idx1 = _NI(tl, pin1)
        _rdocs = list(getattr(idx1, "retired_docs", ()))
        if retire_doc not in _rdocs or _rdocs != sorted(_rdocs):
            return _fail("index-exclusion", _rdocs)
        rep["retired_docs"] = list(idx1.retired_docs)
        rep["retired_atoms"] = int(
            getattr(idx1, "retired_atoms", 0))
        nq1 = _NQ(tl, idx1, emb_q, cfg={})
        dos1, rec1 = nq1.run(query_text)
        served1 = sorted(e.get("doc_id") for e in
                         (dos1.get("entries") or []))
        rep["served_after"] = served1
        if retire_doc in served1:
            return _fail("serve-after",
                         f"{retire_doc} still served: {served1}")
        rmet = ((rec1 or {}).get("metrics") or {}).get("retired")
        if (not rmet or set(rmet) != {"docs", "atoms_excluded"}
                or list(rmet["docs"]) != sorted(rmet["docs"])):
            return _fail("receipt-shape", rmet)
        rep["receipt_retired"] = rmet
        exp = _exp.export_store(tl, include_text=True,
                                pinned=pin1)
        om = [o for o in (exp.get("omissions") or [])
              if isinstance(o, dict)
              and o.get("scope") == f"doc:{retire_doc}"]
        if len(om) != 1:
            return _fail("omission-present",
                         [o.get("scope") for o in
                          (exp.get("omissions") or [])])
        om = om[0]
        if set(om) != {"scope", "cause", "seq",
                       "atoms_withheld"}:
            return _fail("omission-shape", sorted(om))
        if om["cause"] != f"retired:{rrep['ops'][retire_doc]}":
            return _fail("omission-cause", om["cause"])
        if om["seq"] != rrep["seqs"][retire_doc]:
            return _fail("omission-seq", om["seq"])
        rep["omission"] = om
        rep["counts"] = exp.get("counts")
        # No-effect retry needs no approval (nothing is committed).
        rep2 = _lc.retire_docs(tl, [retire_doc], reason=reason,
                               store_id="gate-retire")
        rep["retry_idempotent"] = (
            rep2.get("already_retired") == [retire_doc]
            and rep2.get("n_commits") == 0)
        if not rep["retry_idempotent"]:
            return _fail("retry", {k: rep2.get(k) for k in
                                   ("already_retired",
                                    "n_commits")})
        triple_before = tl.pin()[3]
        tl.close()
        tl = None
        tl2 = _TLS(store_root, create=False,
                   lease_owner="gate-retire-reopen")
        try:
            pin2 = tl2.pin()
            idx2 = _NI(tl2, pin2)
            exp2 = _exp.export_store(tl2, include_text=True,
                                     pinned=pin2)
            om2 = [o for o in (exp2.get("omissions") or [])
                   if isinstance(o, dict)
                   and o.get("scope") == f"doc:{retire_doc}"]
            rep["reopen_identical"] = (
                pin2[3] == triple_before and len(om2) == 1
                and om2[0] == om
                and retire_doc in list(
                    getattr(idx2, "retired_docs", ())))
            if not rep["reopen_identical"]:
                return _fail("reopen",
                             {"pin_same":
                              pin2[3] == triple_before,
                              "omission_same":
                              bool(om2) and om2[0] == om})
        finally:
            tl2.close()
        rep["supported"] = True
        return rep
    finally:
        if tl is not None:
            tl.close()


def exercise_correction(store_root, doc, correction_suffix,
                        query_text, embed_texts=None,
                        embed_query=None, place_xdoc=True,
                        profile=None):
    """New-id correction mechanics on an isolated scratch store.

    doc: (doc_id, text). Ingests a correction under a NEW doc id
    (changed-bytes same-id stays refused per G1), verifies both
    revisions' bytes are preserved, serves the corrected doc for
    its grounded query, and checks organization covers it.
    """
    from tlsys import maint as _m
    from tlsys.index import NarrowIndex as _NI
    from tlsys.ingest import ingest_docs as _ing
    from tlsys.query import NarrowQuery as _NQ
    from tlsys.store_if import TLStore as _TLS
    emb_t, emb_q = _default_embeds(embed_texts, embed_query)
    did, text = doc
    corr_id = f"{did}-corr1"
    corr_text = f"{text} {correction_suffix}"
    rep = {"supported": False, "doc": did,
           "correction_id": corr_id}

    def _fail(step, detail):
        rep["failed_step"] = step
        rep["detail"] = detail
        return rep

    tl = _TLS(store_root, create=True,
              lease_owner="gate-correct-probe")
    try:
        _ing(tl, [(did, text)], emb_t, store_id="gate-correct",
             place_xdoc=place_xdoc, progress_journal=True,
             profile=profile)
        r2 = _ing(tl, [(corr_id, corr_text)], emb_t,
                  store_id="gate-correct", place_xdoc=place_xdoc,
                  progress_journal=True, profile=profile)
        if not r2.get("n_atoms"):
            return _fail("correction-accepted", r2)
        pin = tl.pin()
        idx = _NI(tl, pin)
        # Both revisions preserved: every owning-chunker chunk body
        # of each ingested text is present verbatim among that
        # revision's committed artifact bytes.
        from tlsys.ingest import chunk_text as _ct
        bodies = {}
        for want, wtext in ((did, text), (corr_id, corr_text)):
            aids = [a for a, m in idx.atoms.items()
                    if m.get("doc_id") == want]
            if not aids:
                return _fail("revision-indexed", want)
            got = set()
            for a in aids:
                try:
                    raw = tl.read_artifact(
                        idx.atoms[a]["text_art"],
                        expect_digest=idx.atoms[a][
                            "text_digest"])
                    got.add(raw.decode("utf-8"))
                except Exception as e:  # noqa: BLE001 - finding
                    return _fail(
                        "revision-bytes",
                        f"{want}:{type(e).__name__}")
            bodies[want] = got
            want_chunks = {c[2] for c in _ct(wtext)}
            if not want_chunks or not want_chunks <= got:
                return _fail("revision-bytes",
                             {"doc": want,
                              "want_chunks": len(want_chunks),
                              "got_bodies": len(got)})
        rep["both_revisions_preserved"] = True
        nq = _NQ(tl, idx, emb_q, cfg={})
        dos, _rec = nq.run(query_text)
        served = sorted(e.get("doc_id") for e in
                        (dos.get("entries") or []))
        rep["corrected_served"] = corr_id in served
        rep["served"] = served
        if not rep["corrected_served"]:
            return _fail("corrected-served", served)
        org = _m.organize_segments(tl, budget=None,
                                      profile=profile)
        idx2 = _NI(tl, tl.pin())
        covered = [a for leaves in
                   (idx2.seg_leaves or {}).values()
                   for a in (leaves.get("members") or [])
                   if (idx2.atoms.get(a) or {}).get("doc_id")
                   == corr_id]
        rep["organized"] = {"leaves": len(idx2.seg_leaves),
                            "parents": len(idx2.seg_parents),
                            "corrected_atoms_covered":
                            len(covered)}
        if not covered:
            return _fail("organized-covers", rep["organized"])
        rep["supported"] = True
        return rep
    finally:
        tl.close()


# ------------------------------------------------------------------ oracle

def oracle_worker_main(spec_path, result_path):
    """Isolated bounded oracle worker (G6). Fresh process, capped output.

    One worker per sampled pin: asserts its live pin triple equals
    the spec pin (pin-correctness proof — a snapshot of another
    generation fails here), then checks indexed read_relations vs
    fullscan oracle exact equality, RelView eligibility
    agreement, and reruns EVERY spec query through its campaign
    entry point against the recorded baseline. Writes ONE JSON
    result file (size-capped) and exits 0/2 (2 = oracle FAIL).
    """
    import resource as _res
    spec = load_json(spec_path)
    out = {"spec": {k: spec.get(k) for k in
                    ("pin_tag", "pin_triple", "query_ids")},
           "checks": [], "self_peak_kb": None,
           "peak_hwm_kb": None}
    ok_all = True

    def _ck(name, ok, detail=None):
        nonlocal ok_all
        ok_all = ok_all and bool(ok)
        out["checks"].append({"name": name, "pass": bool(ok),
                              "detail": detail})

    tl = TLStore(spec["store_root"], create=False,
                 lease_owner=spec.get("lease_owner",
                                      "gate-oracle-worker"))
    try:
        live = tl.pin()
        _ck("pin-correct", live[3] == spec.get("pin_triple"),
            {"live": live[3], "spec": spec.get("pin_triple")})
        if live[3] != spec.get("pin_triple"):
            raise ValueError("worker store is not the sampled "
                             "generation")
        pin = live
        idx = NarrowIndex(tl, pin)
        live_atoms = set(idx.atoms)
        indexed = _relations.read_relations(tl, pin)
        scanned = _relations.read_relations_fullscan(tl, pin)
        ci = json.dumps(indexed, sort_keys=True, default=str)
        cs = json.dumps(scanned, sort_keys=True, default=str)
        _ck("relations-indexed-vs-fullscan",
            ci == cs and set(indexed) == set(scanned),
            {"n_indexed": len(indexed), "n_scanned": len(scanned)})
        view = _relquery.load(tl, pin, live_atoms)
        elig_ids = sorted(getattr(view, "eligible", {}).keys())
        expect_elig = sorted(
            r for r, it in scanned.items()
            if _relations.eligible(it["record"], live_atoms))
        _ck("relview-eligibility-agreement",
            elig_ids == expect_elig,
            {"n_eligible": len(elig_ids)})
        queries = spec.get("queries") or []
        _ck("queries-present", len(queries) > 0,
            {"n_queries": len(queries)})
        emb1 = _fake_vec if spec.get(
            "encoder") == "fake-encoder-v1" else None
        if emb1 is None and spec.get("encoder_model"):
            from sentence_transformers import SentenceTransformer
            _st = SentenceTransformer(
                spec["encoder_model"],
                revision=spec.get("encoder_revision"))

            def emb1(qtext, _st=_st):
                import numpy as _np
                v = _st.encode(qtext, convert_to_numpy=True,
                               show_progress_bar=False)
                return [float(x) for x in _np.ravel(v)]

        if queries and emb1 is None:
            _ck("query-rerun", False, "oracle worker needs a "
                "fixture encoder or a bound full-tier encoder")
        for q in queries:
            if emb1 is None:
                break
            cls = q["class"]
            try:
                if cls == "narrow":
                    nq = NarrowQuery(tl, idx, emb1,
                                     cfg=q.get("cfg") or {})
                    dos, rec = nq.run(q["text"])
                    drain_nav_counters(nq, idx)
                else:
                    dq = DossierQuery(tl, idx, emb1,
                                      cfg=q.get("cfg") or {})
                    dos, rec = dq.run(q["text"],
                                      topics=q.get("topics"))
                    drain_nav_counters(dq, idx)
                served = sorted(e.get("doc_id") for e in
                                (dos.get("entries") or []))
                _ck(f"query-rerun:{q.get('qid')}",
                    served == sorted(q.get("expect_docs") or []),
                    {"served_docs": served,
                     "expect_docs": sorted(q.get("expect_docs")
                                           or []),
                     "status": ((rec or {}).get("execution") or {}
                                ).get("status")})
            except Exception as e:  # noqa: BLE001 - per-query
                _ck(f"query-rerun:{q.get('qid')}", False,
                    f"{type(e).__name__}:{str(e)[:200]}")
    except Exception as e:  # noqa: BLE001 - oracle finding, not crash
        _ck("worker-exception", False,
            f"{type(e).__name__}:{str(e)[:300]}")
    try:
        out["self_peak_kb"] = int(
            _res.getrusage(_res.RUSAGE_SELF).ru_maxrss)
    except (OSError, ValueError, AttributeError):
        pass
    try:
        out["peak_hwm_kb"] = proc_tree_sample()["hwm_kb"]
    except Exception:  # noqa: BLE001 - best effort
        pass
    out["ok"] = ok_all
    blob = json.dumps(out, sort_keys=True)
    out["result_bytes"] = len(blob)
    blob = json.dumps(out, sort_keys=True)
    if len(blob) > int(spec.get("result_cap_bytes", 1 << 20)):
        out = {"ok": False, "checks": [
            {"name": "result-cap", "pass": False,
             "detail": f"result {len(blob)} bytes over cap"}]}
        blob = json.dumps(out, sort_keys=True)
    with open(result_path, "w") as f:
        f.write(blob)
    return 0 if ok_all else 2


def run_oracle_subprocess(spec, timeout_s=300, as_mb=2048):
    """Run one pin's oracle checks in an isolated subprocess (G6).

    stdio streams to temp files with byte caps (never accumulated);
    the result file is size-verified; the per-worker peak is the
    worker's own self maxrss with the RUSAGE_CHILDREN delta kept
    as a labeled cross-check. Returns (rc, result_or_None, info):
    rc is the exit code or "timeout"; info carries peak, output
    bytes, and the applied rlimit/timeout.
    """
    import resource as _res
    tmpd = tempfile.mkdtemp(prefix="gate-oracle-")
    spec_path = os.path.join(tmpd, "spec.json")
    res_path = os.path.join(tmpd, "result.json")
    write_json(spec_path, spec)
    before = _res.getrusage(_res.RUSAGE_CHILDREN).ru_maxrss
    cmd = [sys.executable, os.path.abspath(__file__),
           "--oracle-only", spec_path, "--oracle-result", res_path]
    rc, cap = run_capped(cmd, timeout_s=timeout_s,
                         cap_bytes=1 << 20, as_mb=as_mb)
    after = _res.getrusage(_res.RUSAGE_CHILDREN).ru_maxrss
    delta = max(0, after - before)
    res_cap = int(spec.get("result_cap_bytes", 1 << 20))
    res_bytes = 0
    if os.path.isfile(res_path):
        try:
            res_bytes = os.path.getsize(res_path)
        except OSError:
            res_bytes = 0
    res = None
    if rc == "timeout":
        res = {"ok": False, "checks": [
            {"name": "worker-timeout", "pass": False,
             "detail": f"no result in {timeout_s}s"}]}
    elif res_bytes > res_cap:
        res = {"ok": False, "checks": [
            {"name": "result-cap", "pass": False,
             "detail": f"result {res_bytes} bytes over cap"}]}
        rc = 2
    elif os.path.isfile(res_path):
        try:
            res = load_json(res_path)
        except ValueError:
            res = {"ok": False, "checks": [
                {"name": "result-parse", "pass": False,
                 "detail": "unparseable result"}]}
    else:
        res = {"ok": False, "checks": [
            {"name": "result-missing", "pass": False,
             "detail": f"rc={rc} stderr={cap['stderr_head']}"}]}
    if not cap["capped"]:
        res = {"ok": False, "checks": [
            {"name": "stdio-cap", "pass": False,
             "detail": f"worker stdio over cap "
                       f"(out={cap['stdout_bytes']} "
                       f"err={cap['stderr_bytes']})"}]}
        rc = 2
    peak = select_worker_peak(res, delta)
    info = {"peak_kb": peak["peak_kb"],
            "peak_source": peak["source"],
            "cross_check_delta_kb": peak[
                "cross_check_delta_kb"],
            "stdout_bytes": cap["stdout_bytes"],
            "stderr_bytes": cap["stderr_bytes"],
            "result_bytes": res_bytes,
            "rlimit_as_mb": as_mb, "timeout_s": timeout_s}
    return rc, res, info


# ------------------------------------------------------------------ prefixes

def plan_prefixes(doc_stream, n_prefixes, label="plan"):
    """Find exact-equal chunk/token append boundaries (whole docs).

    doc_stream: [(doc_id, n_chunks, n_tokens)] in corpus order.
    Returns {"feasible": bool, "ranges": [...], "why": ...}. Chunks
    counted by the OWNING chunker (tlsys.ingest.chunk_text); tokens
    are whitespace tokens. Exact equality required; no tolerance.
    """
    tot_c = sum(c for _, c, _ in doc_stream)
    tot_t = sum(t for _, _, t in doc_stream)
    if tot_c % n_prefixes or tot_t % n_prefixes:
        return {"feasible": False, "label": label, "why":
                f"totals not divisible: chunks={tot_c} "
                f"tokens={tot_t} over {n_prefixes} appends"}
    pc, pt = tot_c // n_prefixes, tot_t // n_prefixes
    if not pc or not pt:
        return {"feasible": False, "label": label,
                "why": "empty append target"}
    ranges, start, ac, at, k = [], 0, 0, 0, 1
    for i, (did, c, t) in enumerate(doc_stream):
        ac += c
        at += t
        if ac == k * pc and at == k * pt:
            ranges.append({"append": k, "docs": [d for d, _, _
                                                in doc_stream[start:i + 1]],
                           "chunks": pc, "tokens": pt})
            start = i + 1
            k += 1
        elif ac > k * pc or at > k * pt:
            return {"feasible": False, "label": label, "why":
                    f"no exact boundary at append {k} "
                    f"(doc {did} overshoots)"}
    if k - 1 != n_prefixes:
        return {"feasible": False, "label": label,
                "why": "boundaries incomplete"}
    return {"feasible": True, "label": label, "ranges": ranges,
            "per_append": {"chunks": pc, "tokens": pt}}


def stream_docs_file(path, id_field="doc_id", text_field="text"):
    """Yield (doc_id, text, ordinal, line_sha256) streaming (no retain)."""
    with open(path, "rb") as f:
        ordinal = 0
        for raw in f:
            raw = raw.rstrip(b"\n")
            if not raw.strip():
                continue
            ordinal += 1
            row = json.loads(raw.decode("utf-8"))
            yield (row[id_field], row[text_field], ordinal,
                   sha256_bytes(raw))


# ------------------------------------------------------------------ gate

def build_arg_parser():
    ap = argparse.ArgumentParser(
        description="Integrated 10M gate runner (G0-G6).")
    ap.add_argument("--tier", choices=["fixture", "full"],
                    default="fixture")
    ap.add_argument("--criteria",
                    default=os.path.join(HERE, "CRITERIA.v1.json"))
    ap.add_argument("--inputs",
                    default=os.path.join(HERE, "CONFIRM-INPUTS.v1.json"))
    ap.add_argument("--out", required=False, default=None)
    ap.add_argument("--store-root", default=None)
    ap.add_argument("--candidate-label", default=None)
    ap.add_argument("--docs", default=None,
                    help="full tier: streamed docs jsonl")
    ap.add_argument("--cache-dir", default=None,
                    help="full tier: file-backed embedding cache")
    ap.add_argument("--queries", default=None,
                    help="full tier: sealed queries file")
    ap.add_argument("--relations-file", default=None,
                    help="full tier: typed analyst relations json")
    ap.add_argument("--suite-record", default=None,
                    help="full tier G0: tl-sys+tl-eval suite record")
    ap.add_argument("--encoder-model", default=None)
    ap.add_argument("--encoder-revision", default=None)
    ap.add_argument("--source-manifest",
                    default="tl-eval/evidence/m1-2026-10-06/"
                           "resume-20261006T042743Z/SOURCE-SHA256SUMS")
    ap.add_argument("--place-xdoc", dest="place_xdoc",
                    action="store_true", default=True)
    ap.add_argument("--no-place-xdoc", dest="place_xdoc",
                    action="store_false")
    ap.add_argument("--place-budget", type=int, default=None)
    ap.add_argument("--drain-budget", type=int, default=2)
    ap.add_argument("--profile", default=None, metavar="PATH",
                    help="Lane G profile JSON (schema 1.0.0) threading "
                    "C2 organization catalogs through the gate's "
                    "ingest/drain/organize calls. Default None = exact "
                    "C1 reference organization (today's behavior).")
    ap.add_argument("--seed", type=int, default=20261006)
    ap.add_argument("--oracle-as-mb", type=int, default=None,
                    help="worker RLIMIT_AS cap MiB (default: tier "
                         "default 2048 fixture / 8192 full; full "
                         "workers load the pinned query encoder)")
    ap.add_argument("--oracle-timeout-s", type=int, default=300)
    ap.add_argument("--plan-prefixes", default=None, metavar="DOCS_JSONL",
                    help="plan exact-equal prefix boundaries and exit")
    ap.add_argument("--n-prefixes", type=int, default=3)
    ap.add_argument("--plan-workload", default=None,
                    metavar="DOCS_JSONL",
                    help="plan fixed-work appends at seeded bases "
                         "and exit (fixed-work-v2 rule)")
    ap.add_argument("--workload-bases", default="",
                    help="comma doc-counts, e.g. 1000,10000,100000")
    ap.add_argument("--workload-target", default="",
                    help="chunks,tok_v1_tokens, e.g. 500,100000")
    ap.add_argument("--workload-tol", type=float, default=0.0,
                    help="plan-workload tolerance (default 0 = exact, "
                         "per the frozen v3 rule)")
    ap.add_argument("--skip-cells", default="",
                    help="comma list of cells to skip (recorded)")
    ap.add_argument("--oracle-only", default=None, metavar="SPEC")
    ap.add_argument("--oracle-result", default=None, metavar="PATH")
    ap.add_argument("--retirement-contract", default=None,
                    help="lane-2 executable contract note (its sha "
                         "is bound into the G1 retirement record; "
                         "frozen formats are asserted exactly)")
    # C2 Lane G-6: v4 F/D/FI qualification binding (closure C). Off
    # by default (exact v3 behavior). When on: version + adapter
    # binding refusal fires BEFORE any writable store opens, and the
    # executable F/D/FI adapters run on scratch forks after G0-G6.
    ap.add_argument("--qualify-v4", action="store_true", default=False,
                    help="bind + execute v4 F/D/FI qualification "
                         "(refuses pre-open when unbindable)")
    ap.add_argument("--requirements", default=None, metavar="PATH",
                    help="v4 requirements registry JSON (default: "
                         "lane-G5 requirements.v4.json)")
    ap.add_argument("--fd-scope", default="scouting",
                    choices=["scouting", "confirmation"],
                    help="declared qualification scope (v2 amendment: "
                         "scouting is not confirmation)")
    ap.add_argument("--fd-stage", default="10M-readiness",
                    choices=["10M-readiness", "100M-acceptance"],
                    help="v4 aggregation stage")
    ap.add_argument("--fd-inputs", default=None, metavar="PATH",
                    help="confirmation-scope inputs manifest (sizes + "
                         "frozen battery + endpoint plan)")
    return ap


def run_gate(args):
    if os.environ.get("TL_REL_ORACLE") == "1":
        raise SystemExit("refusing: TL_REL_ORACLE=1 is oracle-only "
                         "(G6 campaign rule); unset it for the campaign")
    # C2 Lane G-6: v4 qualification pre-open gate (before criteria
    # load, long before the first writable store opens). Deferred
    # import: default v3 runs never load the binding.
    fd_qual = None
    if getattr(args, "qualify_v4", False):
        from fd_binding import preopen_qualification_gate
        fd_qual = preopen_qualification_gate(args)
    criteria = load_json(args.criteria)
    inputs = load_json(args.inputs)
    criteria_sha = sha256_file(args.criteria)
    inputs_sha = sha256_file(args.inputs)
    # C2 organization profile (Lane G schema, read-only consume).
    # None (default) = exact C1 reference organization at every
    # ingest/drain/organize call below; a valid profile with
    # flags.organization_catalog_routing=true engages the catalogs.
    # Malformed input refuses here, never silently degrades.
    profile = None
    profile_sha = None
    if args.profile:
        profile = load_json(args.profile)
        profile_sha = sha256_file(args.profile)
        if not isinstance(profile, dict):
            raise SystemExit("refusing: --profile must be a JSON object")
        if profile.get("profile_schema_version") != "1.0.0":
            raise SystemExit(
                "refusing: --profile schema "
                f"{profile.get('profile_schema_version')!r} != '1.0.0' "
                "(Lane G is the sole writer of the profile schema)")
        flags = profile.get("flags")
        if not isinstance(flags, dict) or \
                flags.get("organization_catalog_routing") not in (True, False):
            raise SystemExit("refusing: --profile lacks "
                             "flags.organization_catalog_routing bool")
    if not args.out:
        raise SystemExit("--out is required for a gate run")
    os.makedirs(args.out, exist_ok=True)
    store_root = args.store_root or os.path.join(args.out, "store")
    run_id = f"{args.tier}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    rows_w = StreamWriter(os.path.join(args.out, "rows.jsonl"))
    res_w = StreamWriter(os.path.join(args.out, "resources.jsonl"))
    geo_w = StreamWriter(os.path.join(args.out, "prefix_geometry.jsonl"))
    maint_w = StreamWriter(os.path.join(args.out, "maintenance.jsonl"))
    cells = {}

    def _cell(name):
        c = Cell(name)
        cells[name] = c
        return c

    skipped = {s.strip() for s in args.skip_cells.split(",") if s.strip()}

    # ---------------------------------------------------------- G0
    g0 = _cell("G0")
    cand_label = args.candidate_label or criteria.get(
        "candidate_label", "candidate")
    sm_path = os.path.join(ROOT, args.source_manifest)
    sm = verify_manifest(sm_path, ROOT) if os.path.isfile(
        sm_path) else {"ok": False, "checked": 0,
                       "failures": [{"why": "manifest-missing",
                                     "path": sm_path}]}
    g0.check("source-manifest-verifies",
             sm["ok"] and sm["checked"] > 0, sm)
    g0.measure("source_manifest_checked", sm["checked"])
    if args.tier == "full" and not (sm["ok"] and sm["checked"] > 0):
        raise SystemExit("full tier refused: source manifest does "
                         "not verify (candidate mismatch; refreeze "
                         "before confirmation)")
    # Coverage: a verifying manifest that omits required files is not
    # acceptance. The required set is declared by the criteria
    # (v2: 18 files; v3: +lifecycle/proj/approval = 21); full tier
    # enforces it, fixture tier discloses it.
    required_src = (criteria.get("g0") or {}).get(
        "required_source_files") or []
    cov = manifest_coverage(
        manifest_entries(sm_path) if os.path.isfile(sm_path) else {},
        required_src)
    g0.measure("source_manifest_coverage", cov)
    tier_early = args.tier
    if tier_early == "full" and required_src:
        g0.check("source-manifest-covers-candidate", cov["ok"], cov)
        if not cov["ok"]:
            raise SystemExit("full tier refused: source manifest omits "
                             f"required files {cov['missing']}")
    elif tier_early == "full" and not required_src:
        g0.check("source-manifest-covers-candidate", False,
                 "criteria declares no required_source_files; "
                 "coverage unenforceable (refreeze criteria first)")
        raise SystemExit("full tier refused: no declared required "
                         "source set (refreeze criteria first)")
    g0.check("criteria-inputs-frozen-recorded",
             bool(criteria_sha and inputs_sha),
             {"criteria_sha256": criteria_sha,
              "inputs_sha256": inputs_sha,
              "criteria_id": criteria.get("criteria_id"),
              "inputs_id": inputs.get("inputs_id")})
    tier = args.tier
    if tier == "fixture":
        fx = inputs["fixture_tier"]
        docs_all = [(d["doc_id"], d["text"]) for d in fx["docs"]]
        doc_text = dict(docs_all)
        by_id = {d["doc_id"]: d["text"] for d in fx["docs"]}
        prefixes = [list(p) for p in fx["prefixes"]]
        cases = fx["cases"]
        encoder_pin = {"encoder": FakeEncoder.name,
                       "dim": FAKE_DIM, "scope": "fixture-only"}
        corpus_pin = {"kind": "fixture-inline",
                      "inputs_sha256": inputs_sha,
                      "n_docs": len(docs_all)}
        emb = FakeEncoder()
        emb_texts = emb.embed_texts
        emb1 = emb.embed_query
        cache_handle = None
    else:
        bind = inputs.get("full_tier_binding") or {}
        missing = [k for k in ("docs_file", "queries_file",
                               "relations_file", "corpus_manifest")
                   if not ((bind.get(k) or {}).get("path")
                           and (bind.get(k) or {}).get("sha256"))]
        if not bind.get("prefix_doc_ranges"):
            missing.append("prefix_doc_ranges")
        if not bind.get("source_pins", {}).get("pins"):
            missing.append("source_pins.pins")
        g0.check("full-tier-pins-bound", not missing,
                 {"missing": missing})
        if missing:
            raise SystemExit(f"full tier refused: unbound pins "
                             f"{missing} (freeze inputs first)")
        # Real identity: every bound file is hashed against its frozen
        # SHA BEFORE the store is opened or mutated. Placeholder hashes
        # (empty/all-zero/non-hex) refuse immediately.
        sha_bad = []
        for k in ("docs_file", "queries_file", "relations_file",
                  "corpus_manifest"):
            spec = bind[k] or {}
            p = spec.get("path")
            expect = spec.get("sha256")
            fpath = os.path.join(ROOT, p) if p else None
            present = bool(fpath and os.path.isfile(fpath))
            g0.check(f"pin-present-{k}", present, p)
            if not present:
                sha_bad.append(f"{k}-missing")
                continue
            if is_placeholder_sha(expect):
                g0.check(f"pin-sha-{k}", False,
                         {"refused": "placeholder-sha256",
                          "supplied": expect})
                sha_bad.append(f"{k}-placeholder-sha")
                continue
            got = sha256_file(fpath)
            ok = (got == expect)
            g0.check(f"pin-sha-{k}", ok,
                     {"expect": expect, "got": got, "path": p})
            if not ok:
                sha_bad.append(f"{k}-digest-mismatch")
        pinrep = validate_source_pins(
            (bind.get("source_pins") or {}).get("pins"))
        g0.check("source-pins-valid", pinrep["ok"], pinrep)
        if not pinrep["ok"]:
            sha_bad.append("source-pins-invalid")
        if sha_bad:
            raise SystemExit("full tier refused before ingest: "
                             f"identity failures {sha_bad}")
        docs_all, doc_text = None, None  # streamed, never retained
        fx = None
        cases = load_json(os.path.join(
            ROOT, bind["queries_file"]["path"]))
        if not args.cache_dir:
            raise SystemExit("full tier requires --cache-dir")
        from gpu_encode.consume import make_file_backed_emb
        from gpu_encode import config as _cfg
        emb_texts, cache_handle = make_file_backed_emb(
            args.cache_dir, strict=True, fallback=None)
        # Encoder binding: CLI pins must equal the authoritative
        # gpu_encode pins AND the cache's served numeric config.
        want_model, want_rev = _cfg.MODEL_ID, _cfg.MODEL_REVISION
        want_cfg = _cfg.config_id(_cfg.PRECISION_FIRST)
        got_cfg = (cache_handle["reader"].meta.get("config_id")
                   if cache_handle is not None else None)
        enc_ok = (args.encoder_model == want_model
                  and args.encoder_revision == want_rev
                  and got_cfg == want_cfg)
        g0.check("encoder-pinned-bound", enc_ok,
                 {"want_model": want_model, "want_revision": want_rev,
                  "got_model": args.encoder_model,
                  "got_revision": args.encoder_revision,
                  "want_config_id": want_cfg,
                  "cache_config_id": got_cfg,
                  "precision": _cfg.PRECISION_FIRST})
        if not enc_ok:
            raise SystemExit("full tier refused: query/corpus encoder "
                             "pins do not match the frozen numeric "
                             "profile (see encoder-pinned-bound)")
        from sentence_transformers import SentenceTransformer
        _st = SentenceTransformer(args.encoder_model,
                                  revision=args.encoder_revision)

        def emb1(q, _st=_st):
            import numpy as _np
            v = _st.encode(q, convert_to_numpy=True,
                           show_progress_bar=False)
            return [float(x) for x in _np.ravel(v)]

        encoder_pin = {"model": args.encoder_model,
                       "revision": args.encoder_revision,
                       "cache_dir": args.cache_dir,
                       "cache_config_id": got_cfg,
                       "consume": "make_file_backed_emb strict"}
        corpus_pin = {"kind": "sealed-corpus",
                      "docs_sha256": bind["docs_file"]["sha256"],
                      "manifest_sha256":
                          bind["corpus_manifest"]["sha256"]}
        by_id = None
        prefixes = [list(r["docs"]) for r in
                    bind["prefix_doc_ranges"]]
    g0.measure("candidate_label", cand_label)
    g0.measure("encoder_pin", encoder_pin)
    g0.measure("corpus_pin", corpus_pin)
    g0.measure("python", python_identity())
    if tier == "full":
        if not args.suite_record:
            g0.check("suite-record-present", False,
                     "missing --suite-record")
            raise SystemExit("full tier requires --suite-record (G0)")
        sr = load_json(args.suite_record)
        req = criteria.get("suite_record_contract", {})
        keys_ok = all(k in sr for k in req.get("required_keys", ()))
        exits_ok = sr.get("tlsys_exit") == 0 and sr.get(
            "tleval_exit") == 0
        g0.check("suite-record-green", keys_ok and exits_ok, sr)
        # Binding: the suite record must name THIS candidate (the
        # verified source manifest digest) and THIS frozen
        # criteria/inputs pair. An unrelated green record refuses.
        sm_sha = (sha256_file(sm_path)
                  if os.path.isfile(sm_path) else None)
        cand_ok = (sr.get("candidate_revision") == sm_sha
                   and not is_placeholder_sha(
                       sr.get("candidate_revision")))
        g0.check("suite-record-bound-candidate", cand_ok,
                 {"candidate_revision": sr.get("candidate_revision"),
                  "source_manifest_sha256": sm_sha})
        ci_ok, ci_detail = True, {}
        for key, got in (("criteria_sha256", criteria_sha),
                         ("inputs_sha256", inputs_sha)):
            if key in req.get("required_keys", ()):
                ok_k = (sr.get(key) == got)
                ci_detail[key] = {"record": sr.get(key),
                                  "run": got, "match": ok_k}
                ci_ok = ci_ok and ok_k
            else:
                ci_detail[key] = {"record": sr.get(key),
                                  "run": got, "match": "unbound-v1"}
        g0.check("suite-record-bound-inputs", ci_ok, ci_detail)
        # Conditional HNSW rule: only fires when HNSW is the serving
        # backend. This runner's serving arms attach no candidate
        # search (campaigns) or the CPU partition index (G2 ON arm
        # retired to HierQuery); backend determination recorded.
        backend = ((criteria.get("serving_backend")
                    or "cpu-partition-or-none"))
        hnsw_needed = "hnsw" in str(backend).lower()
        hnsw_ok = (not hnsw_needed) or bool(
            sr.get("hnsw_checks_rerun"))
        g0.check("suite-record-hnsw-conditional", hnsw_ok,
                 {"serving_backend": backend,
                  "hnsw_checks_rerun": sr.get("hnsw_checks_rerun")})
        if not (keys_ok and exits_ok and cand_ok and ci_ok
                and hnsw_ok):
            raise SystemExit("full tier refused: suite record not "
                             "green+bound for this candidate/inputs")
    else:
        g0.check("suite-record-fixture-tier", True,
                 "deferred: coordinator supplies the suite record "
                 "for the full-tier confirmation")
    g0.measure("prefixes", [len(p) for p in prefixes])
    g0.check("prefixes-nonempty-growing",
             len(prefixes) >= 3 and all(prefixes) and all(
                 len(prefixes[i]) > len(prefixes[i - 1])
                 for i in range(1, len(prefixes))),
             [len(p) for p in prefixes])
    if "G0" in skipped:
        g0.checks = [{"name": "skipped", "pass": True,
                      "detail": "operator-skipped"}]

    # ------------------------------------------------- ingest/prefixes
    store_id = f"gate-{tier}"
    tl = TLStore(store_root, create=True, lease_owner=f"gate-{run_id}")
    admission_log = []  # (doc_id, admitted_perf_counter)
    pins = []
    prefix_reports = []
    maint_rows = []  # small per-drain dicts for the G5 assessment
    pin_baselines = {}  # pin tag -> [qspecs actually served there]
    pin_triples = {}  # pin tag -> live triple when served there
    snap_records = []  # store snapshots for pin-correct oracles
    g4 = _cell("G4")
    g5 = _cell("G5")
    n_chunks_planned, n_toks_planned, n_tokv1_planned = [], [], []
    prev_ids = set()
    store_bytes_before = dir_size_bytes(store_root)["bytes"]
    # G6 sample plan (tags only; triples known when pins land).
    # Prefix pins serve narrow + cross_topic; publication/hier pins
    # serve all run_case classes. Full tier: seeded >=3 x >=5 per
    # the frozen rule; fixture: every pin x every servable query.
    _prefix_qids = [f"{cl}:{c.get('id')}"
                    for cl in ("narrow", "cross_topic")
                    for c in cases.get(cl, ())]
    _all_qids = [f"{cl}:{c.get('id')}"
                 for cl in ("narrow", "relational",
                            "cross_topic", "qualifier")
                 for c in cases.get(cl, ())]
    _tag_universe = ([(pi, None, list(_prefix_qids))
                      for pi in range(len(prefixes))]
                     + [("publication", None, list(_all_qids)),
                        ("hier", None, list(_all_qids))])
    if tier == "full":
        g6_plan = plan_oracle_sample(_tag_universe,
                                     seed=args.seed)
    else:
        g6_plan = {"feasible": True, "seed": args.seed,
                   "sampled": [(t, None, list(qs))
                               for t, _tr, qs in _tag_universe],
                   "rule": "every pin x every servable query"}
    g6_sample_tags = {t for t, _tr, _qs in
                      g6_plan.get("sampled", ())}
    g6_want_qids = {t: list(qs) for t, _tr, qs in
                    g6_plan.get("sampled", ())}
    snap_dir = os.path.join(args.out, "store-snapshots")
    if g6_sample_tags:
        os.makedirs(snap_dir, exist_ok=True)

    full_docs_path = os.path.join(
        ROOT, (inputs.get("full_tier_binding") or {}).get(
            "docs_file", {}).get("path") or "") if tier == "full" \
        else None

    def _geometry(ids):
        # (chunks, ws_tokens, tok_v1): fixture inline; full tier via
        # the streamed authoritative path (owning chunker over the
        # sealed docs file, one bounded pass per prefix).
        n_c = n_t = n_v = 0
        if tier == "fixture":
            for did in ids:
                t = by_id[did]
                n_c += len(chunk_text(t))
                n_t += ws_tokens(t)
                n_v += tok_v1_count(t)
            return n_c, n_t, n_v
        want = set(ids)
        for did, text, _o, _h in stream_docs_file(full_docs_path):
            if did in want:
                n_c += len(chunk_text(text))
                n_t += ws_tokens(text)
                n_v += tok_v1_count(text)
        return n_c, n_t, n_v

    corpus_order = []
    if tier == "full":
        for did, _t, _o, _h in stream_docs_file(os.path.join(
                ROOT, inputs["full_tier_binding"]["docs_file"]["path"])):
            corpus_order.append(did)
    else:
        corpus_order = [d for d, _ in docs_all]

    for pi, ids in enumerate(prefixes):
        new_ids = [d for d in ids if d not in prev_ids]
        if tier == "fixture":
            new_docs = [(d, by_id[d]) for d in new_ids]
        else:
            want = set(new_ids)
            path = os.path.join(
                ROOT, inputs["full_tier_binding"]["docs_file"]["path"])
            new_docs = [(d, t) for d, t, _o, _h in
                        stream_docs_file(path) if d in want]
            order = {d: i for i, d in enumerate(new_ids)}
            new_docs.sort(key=lambda x: order[x[0]])
        t_admit = time.perf_counter()
        for d, _t in new_docs:
            admission_log.append((d, t_admit))
        # Production intake: journal-enabled (declarations +
        # per-flush progress append; manifest saves once).
        with Timer() as tm:
            rep = ingest_docs(tl, new_docs, emb_texts,
                              store_id=store_id,
                              place_xdoc=args.place_xdoc,
                              place_budget=args.place_budget,
                              progress_journal=True,
                              profile=profile)
        drain_nav_counters(tl)
        pin = tl.pin()
        pins.append([list(pin[:3]) + [pin[3]], pi])
        nc, nt, nv = _geometry(new_ids)
        n_chunks_planned.append(nc)
        n_toks_planned.append(nt)
        n_tokv1_planned.append(nv)
        _ju = journal_usage(store_root)
        _cu = checkpoint_usage(store_root)
        prefix_reports.append({"prefix": pi, "n_docs": len(ids),
                               "added_docs": len(new_docs),
                               "added_chunks": nc,
                               "added_tokens": nt,
                               "added_tokens_tok_v1": nv,
                               "ingest_s": round(tm.s, 3),
                               "intake_journal": _ju,
                               "checkpoint": _cu,
                               "ingest": _trim(
                                   {k: (v if k !=
                                         "pending_placement"
                                         else len(v))
                                    for k, v in rep.items()}),
                               "pin_triple": pin[3]})
        geo_w.write(prefix_reports[-1])
        res_w.write({"phase": f"ingest-prefix-{pi}",
                     "proc_tree": proc_tree_sample(),
                     "vram": vram_sample(),
                     "store": dir_size_bytes(store_root)})
        # per-prefix campaign: narrow + cross-topic (every prefix)
        idx = NarrowIndex(tl, pin)
        _bl = []
        for cls in ("narrow", "cross_topic"):
            for case in cases.get(cls, ()):
                row, _e, _r = run_case(cls, case, tl, idx, emb1,
                                       criteria)
                row["prefix"] = pi
                row["pin_triple"] = pin[3]
                rows_w.write(row)
                _bl.append({"qid": f"{cls}:{case.get('id')}",
                            "class": cls, "text": case["query"],
                            "topics": case.get("topics"),
                            "cfg": criteria["classes"][cls][
                                "cfg"],
                            "expect_docs": row.get(
                                "served_docs")})
        pin_baselines[pi] = _bl
        pin_triples[pi] = pin[3]
        # Snapshot sampled pins while the generation is live (the
        # later drain commits; the worker proves the triple).
        if pi in g6_sample_tags:
            _sp = os.path.join(snap_dir, f"pin-{pi}")
            _sr = snapshot_store(store_root, _sp)
            _sr.update({"tag": pi, "pin_triple": pin[3]})
            snap_records.append(_sr)
        res_w.write({"phase": f"campaign-prefix-{pi}",
                     "proc_tree": proc_tree_sample(),
                     "vram": vram_sample(),
                     "store": dir_size_bytes(store_root)})
        # scheduled maintenance between prefixes (G5)
        from tlsys.ingest import _load_manifest
        man, _mp = _load_manifest(tl.store)
        pending_before = list(man.get("_pending_placement", []))
        now = time.perf_counter()
        ages = [now - a for d, a in admission_log
                if d in set(pending_before)]
        oldest = max(ages) if ages else 0.0
        # blocking probe: serving latency around the drain window
        probe = (cases.get("narrow") or [None])[0]
        lat_idle = []
        if probe:
            for _ in range(2):
                r, _e, _rr = run_case("narrow", probe, tl, idx,
                                      emb1, criteria)
                lat_idle.append(r["ms"])
        # A drain that errors FAILS the blocking rule (recorded,
        # never a silent crash or a skip).
        drain_error = None
        with Timer() as dtm:
            try:
                drep = _maint.drain_placement_backlog(
                    tl, store_id=store_id,
                    budget=args.drain_budget,
                    profile=profile)
            except Exception as e:  # noqa: BLE001 - G5 finding
                drep = {"drained": 0, "failed": 0}
                drain_error = (f"{type(e).__name__}:"
                               f"{str(e)[:200]}")
        drain_nav_counters(tl)
        lat_after = []
        if probe:
            idx2 = NarrowIndex(tl, tl.pin())
            for _ in range(2):
                r, _e, _rr = run_case("narrow", probe, tl, idx2,
                                      emb1, criteria)
                lat_after.append(r["ms"])
        man2, _mp2 = _load_manifest(tl.store)
        pending_after = list(man2.get("_pending_placement", []))
        _mrow = {"prefix": pi,
                 "pending_before": len(pending_before),
                 "pending_after": len(pending_after),
                 "oldest_pending_age_s": round(oldest, 3),
                 "drained": drep.get("drained"),
                 "failed": drep.get("failed"),
                 "n_commits": drep.get("n_commits"),
                 "drain_s": round(dtm.s, 3),
                 "drain_error": drain_error,
                 "catchup": _trim(drep.get("catchup")),
                 "commit_catchup": _trim(
                     drep.get("commit_catchup")),
                 "debt": _trim(drep.get("debt")),
                 "churn": _trim(drep.get("churn")),
                 "retained": _trim(drep.get("retained")),
                 "probe_ms_idle": lat_idle,
                 "probe_ms_after": lat_after}
        maint_w.write(_mrow)
        maint_rows.append(_mrow)
        prev_ids = set(ids)

    adds_docs = [prefix_reports[i]["added_docs"] for i in range(
        len(prefix_reports))]
    prefix_rule = (criteria.get("g4") or {}).get("prefix_rule") or {}
    rule_id = prefix_rule.get("rule_id", "exact-equal-v1")
    g4.measure("prefix_rule_id", rule_id)
    if rule_id == "fixed-work-v2":
        # Seeded-base fixed-work appends: each append lands within tol
        # of the frozen chunk/token workload. The workload target is
        # frozen per campaign in the INPUTS (full: binding.
        # append_workload; fixture: fixture_tier.append_workload);
        # tol lives in the criteria rule (v3: 0 = exact). Doc counts
        # are recorded geometry, never an equality bar (docs differ
        # in length). A missing/invalid tol fails closed (no silent
        # default tolerance).
        if tier == "full":
            wl = ((inputs.get("full_tier_binding") or {}).get(
                "append_workload") or {})
        else:
            wl = ((inputs.get("fixture_tier") or {}).get(
                "append_workload") or {})
        tc, tt = wl.get("target_chunks"), wl.get(
            "target_tokens_tok_v1")
        tol = prefix_rule.get("tol", None)
        fw = assess_fixed_work(
            [(n_chunks_planned[i], n_tokv1_planned[i])
             for i in range(len(prefix_reports))],
            tc, tt, tol)
        for _a, _d in zip(fw["appends"], adds_docs):
            _a["docs"] = _d
        g4.check("appends-tol-declared", fw["tol_ok"],
                 {"tol": tol, "why": fw["why"]})
        g4.check("appends-fixed-work", fw["ok"],
                 {"target": wl, "appends": fw["appends"],
                  "tol": tol, "why": fw["why"]})
        g4.measure("per_append", {"target": wl,
                                  "actual": fw["appends"],
                                  "docs_recorded": adds_docs})
    else:
        g4.check("prefixes-exact-equal-docs",
                 len(set(adds_docs)) == 1, adds_docs)
        g4.check("prefixes-exact-equal-chunks",
                 len(set(n_chunks_planned)) == 1, n_chunks_planned)
        g4.check("prefixes-exact-equal-tokens",
                 len(set(n_toks_planned)) == 1, n_toks_planned)
        g4.measure("per_append",
                   {"docs": adds_docs[0] if adds_docs else 0,
                    "chunks": n_chunks_planned[0]
                    if n_chunks_planned else 0,
                    "tokens": n_toks_planned[0]
                    if n_toks_planned else 0,
                    "tokens_tok_v1": n_tokv1_planned[0]
                    if n_tokv1_planned else 0})

    # Journal-enabled intake (production profile): every append
    # must show journal records applied (durable manifest
    # counter), not legacy per-flush manifest rewrites.
    _jseqs = [p.get("intake_journal", {}).get("journal_seq")
              for p in prefix_reports]
    g4.check("intake-journal-enabled",
             bool(_jseqs) and all(isinstance(s, int) and s > 0
                                  for s in _jseqs),
             {"journal_seq_per_append": _jseqs})

    # ------------------------------------------------- publication
    with Timer() as ptm:
        final_pin_pre = tl.pin()
        idx_pre = NarrowIndex(tl, final_pin_pre)
        CFG = {"extractor": "gate-runner-v1", "window": 1,
               "model": "none", "rules": ["gate-confirmation"]}
        if tier == "fixture":
            rel_specs = inputs["fixture_tier"]["relations"]
            sig_specs = inputs["fixture_tier"]["qual_signals"]
        else:
            # The frozen binding is authoritative; the CLI flag only
            # overrides it explicitly (documented full invocation
            # omits --relations-file).
            rf_path = (args.relations_file
                       or (bind.get("relations_file") or {}).get(
                           "path"))
            if not rf_path:
                raise SystemExit("full tier: no relations file bound")
            rf = load_json(os.path.join(ROOT, rf_path))
            rel_specs = rf["relations"]
            sig_specs = rf.get("qual_signals", [])
        # Source-grounded anchor resolution (G3R): each endpoint /
        # signal resolves to its owning chunk by verbatim source
        # span. No silent doc->last-atom collapse: ambiguous
        # bindings refuse fail-closed. Chunk texts are read for
        # endpoint / signal docs only (bounded by the spec, never
        # corpus-wide).
        _anchor_docs = ({rs["src"] for rs in rel_specs}
                        | {rs["dst"] for rs in rel_specs}
                        | {ss["doc"] for ss in sig_specs})
        _anchor_texts = {}
        for _aid, _meta in idx_pre.atoms.items():
            if _meta.get("doc_id") not in _anchor_docs:
                continue
            _anchor_texts[_aid] = tl.read_artifact(
                _meta["text_art"],
                expect_digest=_meta["text_digest"]).decode("utf-8")
        try:
            _endpoints = resolve_relation_endpoints(
                rel_specs, idx_pre.atoms, _anchor_texts)
            _sig_aids = resolve_signal_anchors(
                sig_specs, idx_pre.atoms, _anchor_texts)
        except AnchorResolutionError as e:
            raise SystemExit(f"publication refused: {e}")
        recs = []
        for rs, (a, b) in zip(rel_specs, _endpoints):
            recs.append(_relations.make_record(
                rs["rel_type"], [("src", a), ("dst", b)],
                rs.get("qualifiers") or {}, CFG,
                _relations.PROPOSED, [a, b]))
        _relations.commit_relations(tl, recs, store_id=store_id)
        sigs = []
        for ss, _aid in zip(sig_specs, _sig_aids):
            sigs.append(_relquery.make_qual_signal(
                _aid, ss["qualifiers"], CFG))
        if sigs:
            _relquery.commit_qual_signals(tl, sigs,
                                          store_id=store_id)
        _relations.invalidate_rel_index(tl)
        final_pin = tl.pin()
    drain_nav_counters(tl)
    pins.append([list(final_pin[:3]) + [final_pin[3]], "final"])
    pin_triples["publication"] = final_pin[3]
    if "publication" in g6_sample_tags:
        _sp = os.path.join(snap_dir, "pin-publication")
        _sr = snapshot_store(store_root, _sp)
        _sr.update({"tag": "publication",
                    "pin_triple": final_pin[3]})
        snap_records.append(_sr)
    pub = {"phase": "publication", "n_relations": len(recs),
           "n_qual_signals": len(sigs),
           "publication_s": round(ptm.s, 3),
           "pin_triple": final_pin[3]}
    geo_w.write(pub)
    res_w.write({"phase": "publication",
                 "proc_tree": proc_tree_sample(),
                 "vram": vram_sample(),
                 "store": dir_size_bytes(store_root)})
    g4.check("publication-executed", True, pub)

    # --------------------------------- final-prefix campaigns (G3)
    g3 = _cell("G3")
    idxf = NarrowIndex(tl, final_pin)
    # Compact retention: the streamed row + the qualifier evidence
    # it needs (served atom ids + receipt disclosure bit). Full
    # entries/receipts are dropped after each case (bounded by the
    # frozen case count, never by corpus/result scale).
    final_rows = {}  # (class, case_id) -> (row, atom_ids, rel_disc)
    _publ = []
    for cls in ("narrow", "relational", "cross_topic", "qualifier"):
        for case in cases.get(cls, ()):
            row, entries, rec = run_case(cls, case, tl, idxf,
                                         emb1, criteria)
            row["prefix"] = "final"
            row["pin_triple"] = final_pin[3]
            rows_w.write(row)
            _aids = [e.get("atom_id") for e in entries
                     if e.get("atom_id")]
            _reld = "rel_consumption" in (rec or {})
            final_rows[(cls, case.get("id"))] = (row, _aids,
                                                 _reld)
            _publ.append({"qid": f"{cls}:{case.get('id')}",
                          "class": cls, "text": case["query"],
                          "topics": case.get("topics"),
                          "cfg": criteria["classes"][cls]["cfg"],
                          "expect_docs": row.get("served_docs")})
            del entries, rec
    pin_baselines["publication"] = _publ
    res_w.write({"phase": "campaign-final",
                 "proc_tree": proc_tree_sample(),
                 "vram": vram_sample(),
                 "store": dir_size_bytes(store_root)})
    # class assessment (frozen per-class rules)
    for cls in ("narrow", "relational", "cross_topic", "qualifier"):
        spec = cases.get(cls, ())
        outs = [final_rows[(cls, c.get("id"))][0]["outcome"]
                for c in spec]
        errs = [o for o in outs if o == "error"]
        g3.check(f"{cls}-zero-errors", not errs,
                 {"outcomes": outs})
        g3.check(f"{cls}-all-classified",
                 all(o in ("ok", "partial", "refused", "empty",
                           "error") for o in outs), outs)
        scored = [c for c in spec if not c.get("outcome_only")]
        hits = [c for c in scored if final_rows[(
            cls, c.get("id"))][0]["expected"]["hit_docs"]]
        g3.check(f"{cls}-nonvacuous", bool(hits),
                 {"hit_cases": [c.get("id") for c in hits],
                  "n_cases": len(scored)})
        # Outcome treatment (v2): scored cases may be ok or partial
        # (bounded-incomplete is designed behavior with disclosed
        # causes); error/refused/empty on a scored case FAILS.
        unres = [(c.get("id"), final_rows[(
            cls, c.get("id"))][0]["outcome"]) for c in scored
            if final_rows[(cls, c.get("id"))][0]["outcome"]
            in ("error", "refused", "empty")]
        g3.check(f"{cls}-no-unresolved-outcomes", not unres,
                 {"unresolved": unres,
                  "outcomes": [(c.get("id"), final_rows[(
                      cls, c.get("id"))][0]["outcome"])
                      for c in scored]})
        # Passage grounding (v2): every scored case that declares
        # expected spans must serve every span verbatim.
        ungrounded = [c.get("id") for c in scored
                      if (c.get("expected") or {}).get("spans")
                      and not final_rows[(
                          cls, c.get("id"))][0][
                          "expected"]["all_spans_hit"]]
        g3.check(f"{cls}-passages-grounded", not ungrounded,
                 {"ungrounded": ungrounded,
                  "n_scored": len(scored)})
        g3.measure(f"{cls}_outcomes", {o: outs.count(o)
                                       for o in set(outs)})
    # relational reachability: the bridge must arrive THROUGH the
    # declared traversal (lateral edge contribution), not by direct
    # retrieval alone.
    for c in cases.get("relational", ()):
        if c.get("bridge_doc"):
            row = final_rows[("relational", c.get("id"))][0]
            trav = row.get("traversal") or {}
            ok = (c["bridge_doc"] in (row.get("served_docs")
                                      or []) and (trav.get(
                                          "hops_used") or 0)
                  >= int(c.get("min_hops_used", 1)) and (
                                      trav.get("edges_examined")
                                      or 0) > 0 and (trav.get(
                                          "lateral_added") or 0)
                  > 0)
            g3.check("relational-bridge-reachability", ok,
                     {"case": c.get("id"), "traversal": trav,
                      "served": row.get("served_docs")})
    # qualifier joint preservation: every pair counterpart served
    for c in cases.get("qualifier", ()):
        pair = c.get("pair_docs") or []
        if pair:
            row, uni, disclosed = final_rows[("qualifier",
                                              c.get("id"))]
            served = set(row.get("served_docs") or [])
            g3.check("qualifier-joint-preservation",
                     all(d in served for d in pair),
                     {"case": c.get("id"), "pair": pair,
                      "served": sorted(served)})
            try:
                live = set(idxf.atoms)
                view = _relquery.load(tl, final_pin, live)
                pairs = _relquery.identify_pairs(view, uni)
            except Exception as e:  # noqa: BLE001 - recorded
                pairs = f"identify-failed:{type(e).__name__}"
            g3.measure(f"qualifier-pairs-{c.get('id')}", pairs)
            # Counterpart scope/conditions must be identified over the
            # served universe AND disclosed on the receipt (v2).
            g3.check("qualifier-pairs-identified",
                     isinstance(pairs, list) and len(pairs) > 0,
                     {"case": c.get("id"), "pairs": pairs})
            g3.check("qualifier-receipt-discloses",
                     disclosed is True,
                     {"case": c.get("id"),
                      "rel_consumption_present": disclosed})
            g3.measure(f"qualifier-receipt-has-rel-consumption",
                       disclosed)
    # cross-topic coverage: enforce the frozen min_topics_hit bar.
    # doc_topics derives from case-grounded facts: each case maps its
    # expected docs to its declared topics.
    doc_topics = {}
    for c in cases.get("cross_topic", ()):
        for t in c.get("topics") or ():
            doc_topics.setdefault(t, set()).update(
                (c.get("expected") or {}).get("docs") or ())
    min_hit = int((criteria.get("classes") or {}).get(
        "cross_topic", {}).get("min_topics_hit", 1))
    for c in cases.get("cross_topic", ()):
        row = final_rows[("cross_topic", c.get("id"))][0]
        cov = row.get("coverage") or {}
        g3.measure(f"cross-topic-coverage-{c.get('id')}", cov)
        nhit = topic_hits(c, row.get("served_docs") or [],
                          doc_topics)
        g3.check("cross-topic-min-topics-hit",
                 nhit >= min_hit,
                 {"case": c.get("id"), "topics_hit": nhit,
                  "min_topics_hit": min_hit,
                  "topics": c.get("topics")})
    g3.measure("entry_points",
               {k: v["entry_point"] for k, v in
                criteria["classes"].items()})

    # ------------------------------------------------ G2 + ablation
    # Hierarchy access (ON: HierQuery.guided over committed segment
    # organization) vs an isolated hierarchy-disabled arm (OFF:
    # HierQuery.flat, same scoring math, no parent routing) at
    # matched measured work. Every claimed trace resolves against
    # committed parent/child/member relations; flat [leaf, atom]
    # paths can never satisfy the bar.
    g2 = _cell("G2")
    trace_paths = criteria["g2"]["trace_key_paths"]
    with Timer() as orgtm:
        orgrep = _maint.organize_segments(tl, budget=None,
                                             profile=profile)
    drain_nav_counters(tl)
    hier_pin = tl.pin()
    idxh = NarrowIndex(tl, hier_pin)
    n_leaves = len(idxh.seg_leaves)
    n_parents = len(idxh.seg_parents)
    g2.check("hierarchy-organized",
             n_leaves > 0 and n_parents > 0,
             {"organize": _trim(orgrep), "leaves": n_leaves,
              "parents": n_parents,
              "organize_s": round(orgtm.s, 3),
              "hier_pin_triple": hier_pin[3]})
    # Organization debt classes (G5): the report's catch-up, debt,
    # churn, and retained views are first-class evidence, recorded
    # here and assessed at close-out.
    g5.measure("organize_debt",
               {"catchup": _trim(orgrep.get("catchup")),
                "debt": _trim(orgrep.get("debt")),
                "churn": _trim(orgrep.get("churn")),
                "retained": _trim(orgrep.get("retained")),
                "n_commits": orgrep.get("n_commits")})
    hq = HierQuery(tl, idxh, emb1)
    tol = float(criteria["g2"]["ablation"]["work_match_tol"])
    traced_evidence = 0
    ablation_rows = []
    for probe in cases.get("g2_probes", ()):
        want = set((probe.get("expected") or {}).get("docs", ()))
        # ON arm: hierarchy-routed descent (product path).
        try:
            rows_on, rep_on = hq.guided(probe["query"])
            err_on = None
        except Exception as e:  # noqa: BLE001
            rows_on, rep_on = [], {"status": "error",
                                   "work": {}}
            err_on = f"{type(e).__name__}:{str(e)[:200]}"
        w_on = rep_on.get("work") or {}
        work_on = (w_on.get("parents_scored", 0)
                   + w_on.get("children_scored", 0)
                   + w_on.get("atoms_scored", 0))
        # OFF arm: isolated hierarchy-disabled control at the SAME
        # measured scoring budget (flat spends exactly total_budget
        # scoring ops when the population allows).
        try:
            rows_off, rep_off = hq.flat(probe["query"],
                                        total_budget=work_on)
            err_off = None
        except Exception as e:  # noqa: BLE001
            rows_off, rep_off = [], {"status": "error",
                                     "work": {}}
            err_off = f"{type(e).__name__}:{str(e)[:200]}"
        w_off = rep_off.get("work") or {}
        work_off = (w_off.get("leaves_scored", 0)
                    + w_off.get("atoms_scored", 0))
        denom = max(work_on, work_off, 1)
        matched = abs(work_on - work_off) / denom <= tol
        # Resolve every claimed ON-arm trace against the committed
        # hierarchy at the serving pin; count only expected evidence
        # reached through a verified [parent, leaf, atom] route.
        traced = 0
        resolutions = []
        for r in rows_on:
            if r.get("integrity") != "intact-verified":
                continue
            rr = resolve_hierarchy_trace(r.get("path"), idxh,
                                         want_docs=want)
            resolutions.append(
                {"doc": r.get("doc_id"),
                 "resolved": rr["resolved"], "why": rr["why"]})
            if rr["resolved"]:
                traced += 1
        traced_evidence += min(traced, 1)
        served_on = sorted({r.get("doc_id") for r in rows_on}
                           & want)
        served_off = sorted({r.get("doc_id") for r in rows_off}
                            & want)
        # Retired-predicate disclosure: what the old presence-only
        # trace check would have claimed on these rows.
        legacy_hits = sum(
            1 for r in rows_on
            if r.get("doc_id") in want and has_trace_path(
                r, {"guided_report": rep_on}, trace_paths))
        arow = {"probe": probe.get("id"),
                "kind": probe.get("kind"),
                "work_on": work_on, "work_off": work_off,
                "match_tol": tol, "matched": matched,
                "guided_status": rep_on.get("status"),
                "flat_status": rep_off.get("status"),
                "guided_work": w_on, "flat_work": w_off,
                "guided_hits": served_on,
                "flat_hits": served_off,
                "want_docs": sorted(want),
                "traced_hits": traced,
                "legacy_presence_hits": legacy_hits,
                "resolutions": resolutions[:25],
                "err_on": err_on, "err_off": err_off}
        ablation_rows.append(arow)
        rows_w.write({"class": "g2-ablation", "case": arow["probe"],
                      "prefix": "final",
                      "pin_triple": hier_pin[3],
                      "ablation": arow})
    drain_nav_counters(hq)
    # Organization legitimately advances the live generation: the
    # serving/export/oracle final pin is the post-organization pin.
    # (G3 rows keep their pre-organization pin: historical evidence.)
    pins[-1][1] = "publication"
    pins.append([list(hier_pin[:3]) + [hier_pin[3]], "final"])
    g2.measure("final_pin_advanced",
               {"publication": pins[-2][0][3],
                "final": hier_pin[3]})
    final_pin = hier_pin
    del idxf
    idxf = NarrowIndex(tl, final_pin)
    pin_triples["hier"] = hier_pin[3]
    # Post-organization serving leg: every run_case class is served
    # again at the post-organization pin (the serving/export/oracle
    # pin). Rows are historical evidence; baselines feed the G6
    # reruns at this pin.
    _hier = []
    for cls in ("narrow", "relational", "cross_topic",
                "qualifier"):
        for case in cases.get(cls, ()):
            row, _e, _r = run_case(cls, case, tl, idxf, emb1,
                                   criteria)
            row["prefix"] = "post-org"
            row["pin_triple"] = hier_pin[3]
            rows_w.write(row)
            _hier.append({"qid": f"{cls}:{case.get('id')}",
                          "class": cls, "text": case["query"],
                          "topics": case.get("topics"),
                          "cfg": criteria["classes"][cls]["cfg"],
                          "expect_docs": row.get("served_docs")})
    pin_baselines["hier"] = _hier
    res_w.write({"phase": "campaign-post-org",
                 "proc_tree": proc_tree_sample(),
                 "vram": vram_sample(),
                 "store": dir_size_bytes(store_root)})
    # Bounded production-profile leg (G4): the same narrow cases
    # through the exact integrated bounded serving profile —
    # attached candidate searches on both dense legs + bounded
    # hierarchy sidecar — with attachment, fallback, work, and
    # agreement evidence. Additional to (never replacing) the
    # frozen-cfg G3 campaign above.
    _prof_cfg = {"USE_CANDIDATE_HOLONS": True,
                 "USE_CANDIDATE_ATOMS": True,
                 "CANDIDATE_K": 200,
                 "HIER_GUIDED": True,
                 "HIER_PARENT_BUDGET": 200}
    g4.measure("production_profile",
               {"intake": {"progress_journal": True,
                           "place_xdoc": args.place_xdoc,
                           "place_budget": args.place_budget,
                           "drain_budget": args.drain_budget},
                "serving": dict(_prof_cfg),
                "encoder": encoder_pin})
    from tlsys.place import PartitionCandidateIndex
    _prof_rows = []
    _prof_ok = True
    try:
        _idxp = NarrowIndex(tl, hier_pin)
        _sh = PartitionCandidateIndex().build(
            {h: {"descriptor": m.get("descriptor"),
                 "seq": m.get("seq")}
             for h, m in _idxp.holons.items()},
            hier_pin[3])
        _sa = PartitionCandidateIndex().build(
            {a: {"descriptor": m.get("descriptor"),
                 "seq": m.get("seq")}
             for a, m in _idxp.atoms.items()},
            hier_pin[3])
        _idxp.attach_candidate_search(_sh)
        _idxp.attach_atom_search(_sa)
        _prof_attach = {
            "holons": {"backend": _sh.BACKEND,
                       "generation": _sh.generation,
                       "n": _sh.n},
            "atoms": {"backend": _sa.BACKEND,
                      "generation": _sa.generation,
                      "n": _sa.n}}
    except Exception as e:  # noqa: BLE001 - profile finding
        _prof_attach = {"error": f"{type(e).__name__}:"
                        f"{str(e)[:200]}"}
        _prof_ok = False
    if _prof_ok:
        _base = {q["qid"]: q.get("expect_docs") or []
                 for q in _hier}
        for case in cases.get("narrow", ()):
            _qid = f"narrow:{case.get('id')}"
            try:
                _nq = NarrowQuery(tl, _idxp, emb1,
                                  cfg=dict(_prof_cfg))
                _dos, _rec = _nq.run(case["query"])
                _nav = drain_nav_counters(_nq, _idxp)
                _err = None
            except Exception as e:  # noqa: BLE001 - recorded
                _dos, _rec, _nav = {"entries": []}, None, {}
                _err = (f"{type(e).__name__}:"
                        f"{str(e)[:200]}")
            _served = sorted(e.get("doc_id") for e in
                             (_dos.get("entries") or []))
            _prow = {"qid": _qid, "err": _err,
                     "served_docs": _served,
                     "agrees_with_exact": (
                         _served == sorted(_base.get(_qid, ()))
                         if _err is None else False),
                     "candidate_nav": (((_rec or {}).get(
                         "metrics") or {}).get("candidate_nav")),
                     "nav_counters": _nav,
                     "work": receipt_work(_rec)}
            _prof_rows.append(_prow)
            rows_w.write({"class": "profile-narrow",
                          "case": case.get("id"),
                          "prefix": "post-org",
                          "pin_triple": hier_pin[3],
                          "profile": _prow})
            if _err is not None:
                _prof_ok = False
        del _idxp
    g4.measure("production_profile_attach", _prof_attach)
    g4.measure("production_profile_rows", _prof_rows)
    g4.check("production-profile-executed",
             _prof_ok and bool(_prof_rows)
             and "error" not in _prof_attach,
             {"n_cases": len(_prof_rows),
              "agree": sum(1 for r in _prof_rows
                           if r["agrees_with_exact"]),
              "attach": _prof_attach})
    n_probes = len(cases.get("g2_probes", ()))
    g2.check("hierarchy-traced-evidence",
             traced_evidence >= 1,
             {"probes_with_traced_hits": traced_evidence,
              "n_probes": n_probes,
              "rule": "expected evidence via a resolved "
                      "[parent, leaf, atom] route at the serving pin"})
    g2.check("ablation-work-matched",
             bool(ablation_rows) and all(
                 a["matched"] for a in ablation_rows),
             [{"probe": a["probe"], "matched": a["matched"],
               "work_on": a["work_on"],
               "work_off": a["work_off"]}
              for a in ablation_rows])
    # Guided-vs-flat comparison at matched work (recorded; a flat
    # rescue cannot satisfy hierarchy-traced-evidence above).
    g2.measure("guided_vs_flat",
               [{"probe": a["probe"], "kind": a["kind"],
                 "guided_hits": a["guided_hits"],
                 "flat_hits": a["flat_hits"],
                 "traced_hits": a["traced_hits"]}
                for a in ablation_rows])
    g2.measure("ablation", ablation_rows)
    # append/correction behavior (G2 rule)
    g1 = _cell("G1")
    try:
        rep_corr = ingest_docs(
            tl, [("gatefx-app1" if tier == "fixture" else
                  corpus_order[0],
                  "CHANGED BYTES " * 10)], emb_texts,
            store_id=store_id, place_xdoc=args.place_xdoc,
            progress_journal=True, profile=profile)
        corr_outcome = {"refused": False, "report": _trim({
            k: v for k, v in rep_corr.items()
            if k != "pending_placement"})}
    except Exception as e:  # noqa: BLE001 - probe expects refusal
        corr_outcome = {"refused": True,
                        "via": f"{type(e).__name__}:{str(e)[:200]}"}
    g1.measure("changed-bytes-same-id", corr_outcome)
    g1.check("changed-bytes-refused",
             bool(corr_outcome.get("refused")), corr_outcome)
    if tier == "fixture":
        prow = [r for r in ablation_rows
                if r.get("kind") == "append-correction"]
        g2.check("append-correction-served",
                 bool(prow and prow[0]["guided_hits"]), prow)
    # Correction mechanics on an isolated scratch store (G2 rule,
    # all tiers): new-id correction accepted, both revisions'
    # bytes preserved, corrected doc served for the sealed
    # correction probe's query, organization covers it. The
    # correction text is new bytes: fixture embeds via the
    # fixture encoder; full tier embeds via the pinned query
    # encoder (same model/revision as the cache — production
    # must re-encode new revisions; no cache row can exist).
    corr_probes = [c for c in cases.get("g2_probes", ())
                   if c.get("kind") == "append-correction"]
    if corr_probes:
        _cp = corr_probes[0]
        if tier == "fixture":
            _cdoc = (docs_all[0][0], docs_all[0][1])
            _cemb_t, _cemb_q = None, None
        else:
            _cpath = os.path.join(
                ROOT,
                inputs["full_tier_binding"]["docs_file"]["path"])
            _cdoc = [(d, t) for d, t, _o, _h in
                     stream_docs_file(_cpath)][0]

            def _cemb_t(texts, _e1=emb1):
                return [_e1(t) for t in texts]

            _cemb_q = emb1
        try:
            corr_rep = exercise_correction(
                os.path.join(args.out, "scratch-correction"),
                doc=_cdoc, correction_suffix=_cp["query"],
                query_text=_cp["query"],
                embed_texts=_cemb_t, embed_query=_cemb_q,
                place_xdoc=args.place_xdoc, profile=profile)
        except Exception as e:  # noqa: BLE001 - recorded
            corr_rep = {"supported": False, "error": (
                f"{type(e).__name__}:{str(e)[:200]}")}
        g2.measure("correction_exercise", _trim(corr_rep))
        g2.check("correction-exercised",
                 corr_rep.get("supported") is True, _trim(
                     {k: corr_rep.get(k) for k in
                      ("supported", "failed_step", "detail",
                       "both_revisions_preserved",
                       "corrected_served", "organized",
                       "error")}))
    else:
        g2.measure("correction_exercise",
                   {"skipped": "no append-correction probe in "
                               "inputs (rule ungrounded)"})

    # ------------------------------------------------------- G1
    # idempotent re-ingest
    if tier == "fixture":
        re_docs = docs_all
    else:
        path = os.path.join(
            ROOT, inputs["full_tier_binding"]["docs_file"]["path"])
        re_docs = [(d, t) for d, t, _o, _h in
                   stream_docs_file(path)]
    with Timer() as _rtm:
        rep2 = ingest_docs(tl, re_docs, emb_texts,
                           store_id=store_id,
                           place_xdoc=args.place_xdoc,
                           progress_journal=True,
                           profile=profile)
    drain_nav_counters(tl)
    g1.check("reingest-idempotent",
             rep2.get("n_atoms") == 0 and len(
                 rep2.get("skipped") or []) == len(re_docs),
             {"n_atoms": rep2.get("n_atoms"),
              "skipped": len(rep2.get("skipped") or []),
              "n_docs": len(re_docs)})
    # export byte-exactness vs committed artifacts + source spans
    exp = _export.export_store(tl, include_text=True,
                               pinned=final_pin)
    records_out = exp.get("records") or []
    g1.check("export-has-identity",
             bool(exp.get("retry_identity", {}).get("export_id")),
             {"export_id": (exp.get("retry_identity") or {}).get(
                 "export_id")})
    # Span-slice source texts: fixture holds all inline; full tier
    # collects a BOUNDED deterministic sample in one streaming pass
    # (never retains the corpus). Artifact equality is checked for
    # every record in both tiers.
    SAMPLE_N = 2000
    if tier == "fixture":
        span_texts = doc_text or {}
        span_ids = None  # all records
    else:
        step = max(1, len(records_out) // SAMPLE_N)
        sample = records_out[::step][:SAMPLE_N]
        span_ids = {it.get("doc_id") for it in sample
                    if it.get("doc_id")}
        span_texts = {}
        dpath = os.path.join(
            ROOT, inputs["full_tier_binding"]["docs_file"]["path"])
        for did, text, _o, _h in stream_docs_file(dpath):
            if did in span_ids and did not in span_texts:
                span_texts[did] = text
                if len(span_texts) >= len(span_ids):
                    break
    # Streamed comparison: per-record verdicts, bounded mismatch
    # retention (cap + overflow count, never the full list).
    MISM_CAP = 25
    mism, n_checked, n_span, n_mism = [], 0, 0, 0
    for item in records_out:
        aid = item.get("atom_id")
        txt = (item.get("payload") or {}).get("text")
        occ = item.get("occurrence") or {}
        meta = idxf.atoms.get(aid) if aid else None
        if meta is None or not isinstance(txt, str):
            n_mism += 1
            if len(mism) < MISM_CAP:
                mism.append({"atom": aid, "why": "unresolvable"})
            continue
        n_checked += 1
        try:
            raw = tl.read_artifact(
                meta["text_art"],
                expect_digest=meta["text_digest"])
            same_artifact = (raw.decode("utf-8") == txt)
        except Exception:  # noqa: BLE001 - finding
            same_artifact = False
        span_ok = None
        if span_ids is None or meta.get("doc_id") in span_ids:
            src = span_texts.get(meta.get("doc_id"), "")
            n_span += 1
            try:
                b0, b1 = (occ.get("byte_span") or [None, None])
                span_ok = (b0 is not None and b1 is not None
                           and bool(txt) and src.encode(
                               "utf-8")[b0:b1].decode("utf-8")
                           == txt)
            except (ValueError, UnicodeDecodeError, TypeError):
                span_ok = False
        if not same_artifact or span_ok is False:
            n_mism += 1
            if len(mism) < MISM_CAP:
                mism.append({"atom": aid,
                             "same_artifact": same_artifact,
                             "span_slice_ok": span_ok})
    g1.check("export-byte-exact", n_mism == 0 and n_checked > 0,
             {"checked": n_checked, "span_checked": n_span,
              "mismatches": n_mism, "mismatch_head": mism})
    # Occurrence coverage: every live atom/holon at the pin is
    # exported exactly once; omissions carry disclosed causes and
    # counted identities. The confirmation store retires nothing
    # (retirement is exercised on scratch), so any omission here
    # must still account exactly.
    _live_atoms = {a: (m.get("doc_id") or "")
                   for a, m in idxf.atoms.items()}
    _live_holons = set(idxf.holons)
    covrep = audit_export_coverage(_live_atoms, _live_holons, exp,
                                   retired_docs=set())
    g1.check("export-occurrence-coverage", covrep["ok"], _trim(
        covrep))
    g1.measure("export-qualification-disclosure",
               {"qualifiers": _trim(
                   ((records_out[0].get("qualifications")
                     if records_out else {}) or {})),
                "counts": exp.get("counts"),
                "coverage_frontier": exp.get("coverage_frontier"),
                "retry_identity": exp.get("retry_identity"),
                "omissions": _trim(exp.get("omissions") or [])})
    del records_out, span_texts
    # retirement/exclusion: interface candidates are never
    # sufficient; the bar needs the behaviorally exercised
    # approval-gated retire -> serving-excluded -> export-omits
    # path on an isolated scratch store, grounded in a sealed
    # narrow case (its query + expected docs). Contract-v3
    # refused + approved + ACK + frozen formats are asserted
    # exactly inside the exercise.
    import tlsys.ingest as _ing
    retrep = probe_retirement_capability(_maint, _ing)
    try:
        from tlsys import lifecycle as _lcmod
        retrep["lifecycle_sha256"] = sha256_file(
            _lcmod.__file__)
    except (ImportError, OSError, TypeError):
        retrep["lifecycle_sha256"] = None
    if args.retirement_contract:
        _cp = os.path.join(ROOT, args.retirement_contract) \
            if not os.path.isabs(args.retirement_contract) \
            else args.retirement_contract
        retrep["contract"] = args.retirement_contract
        retrep["contract_sha256"] = sha256_file(_cp) \
            if os.path.isfile(_cp) else None
    _ncases = [c for c in cases.get("narrow", ())
               if (c.get("expected") or {}).get("docs")]
    if _ncases:
        _nc = _ncases[0]
        _want = list(_nc["expected"]["docs"])
        if tier == "fixture":
            _rdocs = [(d, by_id[d]) for d in _want
                      if d in by_id]
            _remb_t, _remb_q = None, None
        else:
            _rpath = os.path.join(
                ROOT,
                inputs["full_tier_binding"]["docs_file"]["path"])
            _rtexts = {d: t for d, t, _o, _h in
                       stream_docs_file(_rpath) if d in set(_want)}
            _rdocs = [(d, _rtexts[d]) for d in _want
                      if d in _rtexts]
            _remb_t, _remb_q = emb_texts, emb1
        if len(_rdocs) == len(_want):
            try:
                rex = exercise_retirement(
                    os.path.join(args.out, "scratch-retirement"),
                    docs=_rdocs, query_text=_nc["query"],
                    retire_doc=None, expect_docs=_want,
                    reason="gate-confirmation-probe",
                    embed_texts=_remb_t, embed_query=_remb_q,
                    place_xdoc=args.place_xdoc, profile=profile)
            except Exception as e:  # noqa: BLE001 - recorded
                rex = {"supported": False, "error": (
                    f"{type(e).__name__}:{str(e)[:200]}")}
        else:
            rex = {"supported": False,
                   "failed_step": "grounding",
                   "detail": f"expected docs missing from corpus: "
                             f"{sorted(set(_want) - {d for d, _ in _rdocs})}"}  # noqa: E501
        retrep["exercise"] = _trim(rex)
    else:
        retrep["exercise"] = {"supported": False,
                              "failed_step": "grounding",
                              "detail": "no narrow case with "
                                        "expected docs"}
    retrep["changed_bytes_refusal"] = corr_outcome
    g1.measure("retirement_probe", _trim(retrep))
    if tier == "full":
        g1.check("retirement-supported",
                 (retrep.get("exercise") or {}).get(
                     "supported") is True,
                 _trim({k: (retrep.get("exercise") or {}).get(k)
                        for k in ("supported", "failed_step",
                                  "detail", "error", "retire_doc",
                                  "served_before", "served_after",
                                  "approvals_used",
                                  "refused_paths",
                                  "refused_export_same", "ack",
                                  "approval_ref", "omission",
                                  "retry_idempotent",
                                  "reopen_identical")}))
    else:
        g1.check("retirement-disclosed-fixture", True, _trim(
            retrep))
    # recovery: close + reopen identity (fence: one live handle).
    # Same-generation comparison at final_pin: G2 organization commits
    # (ACCEPT_ATOMS kind) legitimately advance the live pin after
    # publication; comparing latest-vs-final would conflate them.
    # Streaming reopen comparison: digest the pre-close export
    # incrementally (same key coverage as a full canonical
    # compare, minus the volatile wall-clock stamp), release it,
    # then digest the post-reopen export the same way. Peak is one
    # export + two digests, never two exports + two strings.
    def _export_digest(x):
        import hashlib as _hl
        h = _hl.sha256()
        for k in sorted(x):
            if k == "exported_at":
                continue
            v = x[k]
            if isinstance(v, list):
                h.update(f"{k}[{len(v)}]".encode())
                for it in v:
                    h.update(json.dumps(it, sort_keys=True,
                                        default=str).encode())
            else:
                h.update(k.encode())
                h.update(json.dumps(v, sort_keys=True,
                                    default=str).encode())
        return h.hexdigest()

    exp_digest = _export_digest(exp)
    del exp
    gc.collect()
    triple_before = tl.pin()[3]
    del idxf, idx_pre, idxh
    tl.close()
    del tl
    gc.collect()
    tl2 = TLStore(store_root, create=False,
                  lease_owner=f"gate-{run_id}-reopen")
    triple_after = tl2.pin()[3]
    exp2 = _export.export_store(tl2, include_text=True,
                                pinned=final_pin)
    g1.measure("post_final_organization",
               {"final_pin_triple": final_pin[3],
                "hier_pin_triple": hier_pin[3],
                "live_pin_triple": triple_after})
    same_export = (exp_digest == _export_digest(exp2))
    g1.check("reopen-identity",
             triple_before == triple_after and same_export,
             {"pin_same": triple_before == triple_after,
              "export_same": same_export,
              "export_digest": exp_digest})
    del exp2
    tl2.close()
    del tl2
    gc.collect()

    # --------------------------------- cold attach (G4) + G5 close
    with Timer() as ctm:
        tlc = TLStore(store_root, create=False,
                      lease_owner=f"gate-{run_id}-cold")
        pcold = tlc.pin()
        idxc = NarrowIndex(tlc, pcold)
        n_atoms_cold = len(idxc.atoms)
    tlc.close()
    g4.check("cold-attach-separated", True,
             {"cold_attach_s": round(ctm.s, 3),
              "n_atoms": n_atoms_cold,
              "pin_triple": pcold[3],
              "note": "fresh handle; no queries served before "
                      "timing ended"})
    res_w.write({"phase": "cold-attach",
                 "proc_tree": proc_tree_sample(),
                 "vram": vram_sample(),
                 "store": dir_size_bytes(store_root)})
    del tlc, idxc
    gc.collect()
    store_bytes_after = dir_size_bytes(store_root)["bytes"]
    g4.measure("store_bytes_before", store_bytes_before)
    g4.measure("store_bytes_after", store_bytes_after)
    g4.measure("retained_pins", [p[1] for p in pins])
    g4.check("cold-pin-matches-final", pcold[3] == final_pin[3],
             {"cold": pcold[3], "final": final_pin[3]})
    # G5 close-out: every debt class accounted, catch-up assessed
    from tlsys.ingest import _load_manifest as _lm
    _tl5 = TLStore(store_root, create=False,
                   lease_owner=f"gate-{run_id}-g5")
    manf, _mpf = _lm(_tl5.store)
    _tl5.close()
    del _tl5
    final_pending = list(manf.get("_pending_placement", []))
    # Organization debt at close: acknowledged docs missing
    # segment organization (the review's R6 gap class).
    _seg_org = manf.get("_seg_organized")
    _unorg = None
    try:
        _admitted = {d for d, _a in admission_log}
        _orgd = set(_seg_org) if isinstance(_seg_org, dict) \
            else (set(_seg_org) if isinstance(_seg_org, list)
                  else set())
        _unorg = sorted(_admitted - _orgd) if _orgd else None
    except Exception:  # noqa: BLE001 - disclosure best-effort
        _unorg = None
    g5.measure("seg_organized_debt",
               {"unorganized_admitted_docs": _unorg,
                "manifest_has_seg_organized":
                manf.get("_seg_organized") is not None})
    g5.check("backlog-bounded", len(final_pending) == 0,
             {"final_pending": final_pending})
    _initial_pending = (maint_rows[0].get("pending_before", 0)
                        if maint_rows else 0)
    catchrep = assess_catchup(maint_rows, _initial_pending,
                              len(final_pending))
    g5.measure("catchup", catchrep)
    g5.check("keeps-pace", catchrep["keeps_pace"], catchrep)
    g5.check("backpressure-bounded",
             catchrep["backpressure_ok"], catchrep)
    g5.check("drain-blocking", catchrep["blocking_ok"],
             catchrep)
    g5.measure("retained_generations", len({p[0][3] for p in pins
                                            if p[0]}))
    g5.measure("admission_log_docs", len(admission_log))
    # Nonvacuity: a keeps-pace verdict over zero corrective work
    # proves nothing. Full tier enforces; fixture discloses.
    _corrective = (catchrep["drained_total"]
                   + int(((orgrep.get("churn") or {}).get(
                       "leaf_minted") or 0))
                   + int(((orgrep.get("churn") or {}).get(
                       "parent_minted") or 0)))
    g5.measure("corrective_work_total", _corrective)
    if tier == "full":
        g5.check("maintenance-nonvacuous", _corrective > 0,
                 {"drained": catchrep["drained_total"],
                  "churn": _trim(orgrep.get("churn"))})
    g5.check("maintenance-scheduled",
             len(maint_rows) == len(prefixes),
             {"n_drains": len(maint_rows),
              "n_prefixes": len(prefixes),
              "note": "explicit per-prefix drains with budgets; "
                      "see maintenance.jsonl"})

    # ------------------------------------------------------- G6
    g6 = _cell("G6")
    g6.check("campaign-indexed-only",
             os.environ.get("TL_REL_ORACLE") != "1",
             "TL_REL_ORACLE unset for the campaign")
    # Frozen selection rule: full = seeded >=3 pins x >=5
    # queries (plan_oracle_sample, seed = args.seed, default the
    # rule's 20261006); fixture = every pin x every servable
    # query. Each pin's worker opens the store snapshot taken
    # while that generation was live (hier = the live store) and
    # PROVES pin-correctness by asserting its live triple; then
    # it reruns every sampled query through its campaign entry
    # point. No cross-generation serving, no vacuous reruns.
    _snap_by_tag = {s.get("tag"): s for s in snap_records
                    if s.get("ok")}
    _size_ok = True
    _size_detail = {"plan": _trim(g6_plan)}
    if tier == "full":
        _size_ok = bool(g6_plan.get("feasible"))
        for _t, _tr, _qs in g6_plan.get("sampled", ()):
            _have = [q for q in pin_baselines.get(_t, ())
                     if q["qid"] in set(_qs)]
            if len(_have) < 5 or _t not in pin_triples:
                _size_ok = False
            if _t != "hier" and _t not in _snap_by_tag:
                _size_ok = False
        _size_detail["baselines"] = {
            str(t): len(pin_baselines.get(t, ()))
            for t, _tr, _qs in g6_plan.get("sampled", ())}
        _size_detail["snapshots"] = sorted(
            str(s.get("tag")) for s in snap_records)
    g6.check("oracle-sample-size", _size_ok, _size_detail)
    oracle_rows = []
    # Tier default address-space cap (frozen rule: 8192 full /
    # 2048 fixture); the cap still bounds every worker.
    as_mb = args.oracle_as_mb
    if as_mb is None:
        as_mb = default_oracle_cap_mb(tier)
    for (tag, _tr, want_qids) in g6_plan.get("sampled", ()):
        triple = pin_triples.get(tag)
        bl = [q for q in pin_baselines.get(tag, ())
              if q["qid"] in set(want_qids or ())]
        if tag == "hier":
            wroot = os.path.abspath(store_root)
            snap_ok = True
        else:
            snap = _snap_by_tag.get(tag) or {}
            wroot = os.path.abspath(snap.get("dst") or "")
            snap_ok = bool(snap.get("ok") and os.path.isdir(
                wroot))
        spec = {"store_root": wroot,
                "lease_owner": f"gate-{run_id}-oracle",
                "pin_tag": str(tag),
                "pin": None,
                "pin_triple": triple,
                "query_ids": [q["qid"] for q in bl],
                "queries": bl,
                "encoder": ("fake-encoder-v1" if tier == "fixture"
                            else "pinned-full"),
                "encoder_model": (args.encoder_model
                                  if tier == "full" else None),
                "encoder_revision": (args.encoder_revision
                                     if tier == "full" else None),
                "result_cap_bytes": 1 << 20}
        if not snap_ok or triple is None or not bl:
            oracle_rows.append(
                {"pin_tag": str(tag), "pin_triple": triple,
                 "rc": "unsampled",
                 "ok": False, "worker": None,
                 "checks": [{"name": "sample-grounding",
                             "pass": False,
                             "detail": {"snapshot_ok": snap_ok,
                                        "n_queries": len(bl)}}]})
            continue
        rc, res, info = run_oracle_subprocess(
            spec, timeout_s=args.oracle_timeout_s, as_mb=as_mb)
        oracle_rows.append(
            {"pin_tag": str(tag), "pin_triple": triple,
             "rc": rc, "ok": bool(res and res.get("ok")),
             "worker": info,
             "checks": (res or {}).get("checks")})
    g6.check("oracle-sample-all-pass",
             bool(oracle_rows) and all(o["ok"]
                                       for o in oracle_rows),
             _trim(oracle_rows))
    g6.measure("oracle_selection",
               {"rule": criteria["g6"]["selection_rule"],
                "seed": args.seed,
                "sampled": [(o["pin_tag"], o["pin_triple"],
                             [c.get("name") for c in
                              (o.get("checks") or [])
                              if str(c.get("name")).startswith(
                                  "query-rerun:")])
                            for o in oracle_rows]})
    g6.measure("oracle_child_peak_kb",
               {str(o["pin_tag"]): (o.get("worker") or {}).get(
                   "peak_kb") for o in oracle_rows})
    g6.measure("oracle_child_bounds",
               {str(o["pin_tag"]): o.get("worker")
                for o in oracle_rows})
    write_json(os.path.join(args.out, "snapshots.json"),
               {"snapshots": snap_records,
                "plan": _trim(g6_plan)})
    g6.check("streaming-enforced", True,
             {"rows_streamed": rows_w.rows_written,
              "row_buffer_cap": rows_w.buffer_cap,
              "note": "rows flushed incrementally; nav records "
                      "drained+cleared per op (asserted empty)"})
    if cache_handle is not None:
        try:
            g0.measure("cache_stats", cache_handle["stats"]())
            cache_handle["close"]()
        except Exception as e:  # noqa: BLE001 - recorded
            g0.measure("cache_close", f"{type(e).__name__}")

    # C2 Lane G-6: v4 F/D/FI execution on scratch forks (after v3
    # G0-G6, which are preserved fully above). Never mutates the
    # campaign store.
    fd_summary = None
    if fd_qual is not None:
        from fd_binding import execute_qualification
        fd_summary = execute_qualification(
            fd_qual, args, store_root, profile=profile)

    for name in ("G0", "G1", "G2", "G3", "G4", "G5", "G6"):
        if name in skipped and cells[name].checks and \
                cells[name].checks[0]["name"] != "skipped":
            cells[name].checks = [{"name": "skipped", "pass": True,
                                   "detail": "operator-skipped"}]

    rows_w.close()
    res_w.close()
    geo_w.close()
    maint_w.close()
    verdict = {n: cells[n].verdict for n in
               ("G0", "G1", "G2", "G3", "G4", "G5", "G6")}
    all_pass = all(v == "PASS" for v in verdict.values())
    summary = {
        "run_id": run_id, "utc": utc_now(), "tier": tier,
        "candidate_label": cand_label,
        "criteria_sha256": criteria_sha,
        "inputs_sha256": inputs_sha,
        "cells": verdict,
        "all_cells_pass": all_pass,
        "coordinator_note": "GO/NO-GO is a single coordinator "
                            "statement citing G0-G6; this file "
                            "records per-cell evidence only.",
        "failing_cells": [n for n, v in verdict.items()
                          if v != "PASS"]}
    write_json(os.path.join(args.out, "cells.json"),
               {n: cells[n].to_dict() for n in cells})
    write_json(os.path.join(args.out, "verdict.json"), summary)
    write_json(os.path.join(args.out, "config.json"),
               {"tier": tier, "candidate_label": cand_label,
                "criteria": args.criteria,
                "inputs": args.inputs,
                "criteria_sha256": criteria_sha,
                "inputs_sha256": inputs_sha,
                "encoder_pin": encoder_pin,
                "corpus_pin": corpus_pin,
                "place_xdoc": args.place_xdoc,
                "place_budget": args.place_budget,
                "drain_budget": args.drain_budget,
                "profile": args.profile,
                "profile_sha256": profile_sha,
                "profile_id": (profile.get("profile_id")
                               if profile else None),
                "organization_catalog_routing": (
                    bool(profile["flags"]
                         ["organization_catalog_routing"])
                    if profile else False),
                "serving_reference_index": (
                    os.environ.get("TL_C2_REFERENCE_INDEX") == "1"),
                "retirement_contract": args.retirement_contract,
                "qualify_v4": bool(getattr(args, "qualify_v4",
                                           False)),
                "fd_scope": getattr(args, "fd_scope", None),
                "fd_stage": getattr(args, "fd_stage", None),
                "fd_verdict": (fd_summary or {}).get("verdict")
                if fd_summary is not None else None,
                "requirements": getattr(args, "requirements", None),
                "seed": args.seed,
                "oracle_as_mb": (args.oracle_as_mb
                                 if args.oracle_as_mb is not None
                                 else default_oracle_cap_mb(tier)),
                "python": python_identity()})
    lines = [f"# Gate cells — {run_id} ({tier})", "",
             f"all_cells_pass: {all_pass}", ""]
    for n in ("G0", "G1", "G2", "G3", "G4", "G5", "G6"):
        c = cells[n]
        lines.append(f"## {n}: {c.verdict}")
        for ch in c.checks:
            mark = "PASS" if ch["pass"] else "FAIL"
            lines.append(f"- [{mark}] {ch['name']}")
        lines.append("")
    with open(os.path.join(args.out, "CELLS.md"), "w") as f:
        f.write("\n".join(lines))
    # evidence hashes (of this run's own files)
    sums = []
    for fn in ("config.json", "rows.jsonl", "resources.jsonl",
               "prefix_geometry.jsonl", "maintenance.jsonl",
               "snapshots.json", "cells.json", "verdict.json",
               "CELLS.md", "cells_fd.json", "verdict_fd.json"):
        p = os.path.join(args.out, fn)
        if os.path.isfile(p):
            sums.append(f"{sha256_file(p)}  {fn}")
    with open(os.path.join(args.out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0 if all_pass else 1


def main(argv=None):
    ap = build_arg_parser()
    args = ap.parse_args(argv)
    if args.oracle_only:
        if not args.oracle_result:
            raise SystemExit("--oracle-only needs --oracle-result")
        raise SystemExit(oracle_worker_main(args.oracle_only,
                                            args.oracle_result))
    if args.plan_prefixes:
        docs = []
        for did, text, _o, _h in stream_docs_file(args.plan_prefixes):
            docs.append((did, len(chunk_text(text)),
                         ws_tokens(text)))
        plan = plan_prefixes(docs, args.n_prefixes,
                             label=args.plan_prefixes)
        print(json.dumps(plan, indent=1, sort_keys=True))
        raise SystemExit(0 if plan["feasible"] else 1)
    if args.plan_workload:
        if not args.workload_bases or not args.workload_target:
            raise SystemExit("--plan-workload needs "
                             "--workload-bases + --workload-target")
        bases = [int(x) for x in
                 args.workload_bases.split(",") if x.strip()]
        tparts = [int(x) for x in
                  args.workload_target.split(",") if x.strip()]
        if len(tparts) != 2:
            raise SystemExit("--workload-target is "
                             "chunks,tok_v1_tokens")
        docs = []
        for did, text, _o, _h in stream_docs_file(
                args.plan_workload):
            docs.append((did, len(chunk_text(text)),
                         ws_tokens(text), tok_v1_count(text)))
        plan = plan_workload_appends(
            docs, bases, tparts[0], tparts[1],
            tol=args.workload_tol, label=args.plan_workload)
        print(json.dumps(plan, indent=1, sort_keys=True))
        raise SystemExit(0 if plan["feasible"] else 1)
    raise SystemExit(run_gate(args))


if __name__ == "__main__":
    main()
