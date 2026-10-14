"""Shared helpers for the integrated 10M gate runner (M2 track C).

Read-only w.r.t. product code: imports tlsys/gpu_encode modules but never
modifies them. All writers stream (no unbounded retention).
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time


# ---------------------------------------------------------------- hashing

def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def verify_manifest(manifest_path, root):
    """Verify a `sha256sum -c`-style manifest. Returns dict.

    Pure-python equivalent of `sha256sum -c` (no shell needed).
    """
    checked, failures = 0, []
    with open(manifest_path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                expect, rel = line.split(None, 1)
            except ValueError:
                failures.append({"line": line, "why": "unparseable"})
                continue
            rel = rel.strip()
            if rel.startswith("*"):
                rel = rel[1:]
            p = os.path.join(root, rel)
            if not os.path.isfile(p):
                failures.append({"file": rel, "why": "missing"})
                continue
            got = sha256_file(p)
            checked += 1
            if got != expect:
                failures.append({"file": rel, "why": "digest-mismatch",
                                 "expect": expect, "got": got})
    return {"manifest": manifest_path, "checked": checked,
            "failures": failures, "ok": not failures}


def manifest_entries(manifest_path):
    """Parse a `sha256sum`-style manifest into {rel_path: hex_digest}."""
    entries = {}
    with open(manifest_path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                expect, rel = line.split(None, 1)
            except ValueError:
                continue
            rel = rel.strip()
            if rel.startswith("*"):
                rel = rel[1:]
            entries[rel] = expect
    return entries


def manifest_coverage(entries, required):
    """Coverage of a declared required file set by manifest entries.

    Returns {"missing": [...], "covered": [...], "ok": bool}.
    A manifest that verifies but omits required files is NOT
    sufficient acceptance: coverage must be exact-complete.
    """
    missing = sorted(set(required or ()) - set(entries or ()))
    covered = sorted(set(required or ()) & set(entries or ()))
    return {"missing": missing, "covered": covered,
            "n_entries": len(entries or ()),
            "ok": not missing}


def is_placeholder_sha(s):
    """True for empty/all-zero/non-hex-64 placeholder digests."""
    if not isinstance(s, str) or len(s) != 64:
        return True
    if set(s) == {"0"}:
        return True
    try:
        int(s, 16)
    except ValueError:
        return True
    return False


def validate_source_pins(pins):
    """Structural validity of full-tier source_pins (no silent swap).

    Each pin must be a dict carrying a non-placeholder `sha256`
    plus a `path` (or `doc_id`/`file`) identity. Returns
    {"ok": bool, "problems": [...], "n_pins": int}.
    """
    problems = []
    if not isinstance(pins, list) or not pins:
        return {"ok": False, "problems": ["pins-not-a-nonempty-list"],
                "n_pins": 0}
    for i, p in enumerate(pins):
        if not isinstance(p, dict):
            problems.append(f"pin[{i}]-not-a-dict")
            continue
        if is_placeholder_sha(p.get("sha256")):
            problems.append(f"pin[{i}]-bad-sha256")
        if not (p.get("path") or p.get("doc_id") or p.get("file")):
            problems.append(f"pin[{i}]-no-identity")
    return {"ok": not problems, "problems": problems,
            "n_pins": len(pins)}


def load_json(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------- streaming

class StreamWriter:
    """Append-only JSONL writer: every row flushed, nothing retained.

    `buffer_cap` bounds the in-memory pre-flush queue (default 1 row:
    flush-on-write). `rows_written` is the only aggregate kept.
    """

    def __init__(self, path, buffer_cap=1):
        self.path = path
        self.buffer_cap = max(1, int(buffer_cap))
        self._buf = []
        self.rows_written = 0
        self._f = open(path, "w")

    def write(self, row):
        self._buf.append(row)
        assert len(self._buf) <= self.buffer_cap, \
            f"row buffer exceeded cap {self.buffer_cap}"
        if len(self._buf) >= self.buffer_cap:
            self.flush()

    def flush(self):
        for row in self._buf:
            self._f.write(json.dumps(row, sort_keys=True) + "\n")
        self.rows_written += len(self._buf)
        self._buf = []
        self._f.flush()

    def close(self):
        self.flush()
        self._f.close()
        self._f = None


# ---------------------------------------------------------------- resources

def _proc_status(pid):
    out = {}
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith(("VmRSS:", "VmHWM:", "VmSwap:")):
                    k, rest = line.split(":", 1)
                    out[k] = int(rest.strip().split()[0])  # KiB
    except (OSError, ValueError):
        pass
    return out


def _child_pids(pid):
    kids = []
    try:
        with open(f"/proc/{pid}/task/{pid}/children") as f:
            kids = [int(x) for x in f.read().split()]
    except (OSError, ValueError):
        pass
    return kids


def proc_tree_sample(pid=None):
    """Whole-process-tree RSS/HWM/swap (KiB), self + descendants.

    /proc only, no third-party deps. `unknown` fields stay explicit.
    """
    pid = pid or os.getpid()
    seen, stack, tot = set(), [pid], {"rss_kb": 0, "hwm_kb": 0,
                                      "swap_kb": 0, "n_procs": 0,
                                      "unknown_procs": 0}
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        st = _proc_status(p)
        if not st:
            tot["unknown_procs"] += 1
            continue
        tot["rss_kb"] += st.get("VmRSS", 0)
        tot["hwm_kb"] += st.get("VmHWM", 0)
        tot["swap_kb"] += st.get("VmSwap", 0)
        tot["n_procs"] += 1
        stack.extend(_child_pids(p))
    return tot


def vram_sample():
    """NVML-free VRAM probe via nvidia-smi; explicit unknown otherwise."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"], capture_output=True,
            text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return {"vram": "unknown", "why": "nvidia-smi-unavailable"}
    if r.returncode != 0:
        return {"vram": "unknown", "why": "nvidia-smi-failed",
                "stderr": (r.stderr or "")[:200]}
    used, total, n = 0, 0, 0
    for line in r.stdout.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) == 2:
            try:
                used += int(float(parts[0]))
                total += int(float(parts[1]))
                n += 1
            except ValueError:
                pass
    if not n:
        return {"vram": "unknown", "why": "unparsed-smi-output"}
    return {"vram_used_mib": used, "vram_total_mib": total,
            "vram_n_gpus": n}


def dir_size_bytes(path):
    total, n_files = 0, 0
    for dp, _dn, fn in os.walk(path):
        for f in fn:
            try:
                total += os.path.getsize(os.path.join(dp, f))
                n_files += 1
            except OSError:
                pass
    return {"bytes": total, "files": n_files}


# ---------------------------------------------------------------- outcomes

def classify_outcome(entries, receipt, err):
    """Outcome taxonomy (frozen): error|partial|refused|empty|ok.

    error: the call raised. partial: bounded-incomplete status or a
    nonempty partials inventory. refused: empty emission explicitly
    marked as a refusal. empty: complete but nothing served. ok:
    complete with >=1 entry.
    """
    if err is not None:
        return "error"
    rec = receipt or {}
    status = (rec.get("execution") or {}).get("status")
    partials = rec.get("partials") or []
    if status == "bounded-incomplete" or partials:
        return "partial"
    if not entries:
        hay = json.dumps({"s": rec.get("selection_outcomes"),
                          "f": rec.get("support_findings"),
                          "fl": rec.get("flags")}).lower()
        if "refus" in hay:
            return "refused"
        return "empty"
    return "ok"


def receipt_work(receipt):
    """Scalar work evidence from a query receipt (missing -> 0/None)."""
    m = (receipt or {}).get("metrics") or {}
    ops = m.get("op_class_counts") or {}
    return {
        "work_used": m.get("work_used", 0),
        "work_budget": m.get("work_budget"),
        "op_classes": dict(ops),
        "op_total": sum(v for v in ops.values()
                        if isinstance(v, (int, float))),
        "R_regions": m.get("R_regions"),
        "C_candidates": m.get("C_candidates"),
        "E_edges": m.get("E_edges"),
        "H_hops": m.get("H_hops"),
        "prune_survivors": m.get("prune_survivors"),
        "entries": m.get("entries"),
        "T_ms": m.get("T_ms"),
    }


def drain_nav_counters(*objs):
    """Stream NavCounters evidence then clear (no unbounded retention).

    Walks each object's attributes (one level + `records` lists of
    NavCounters-like holders). Returns merged {path: {counter: sum}}
    and empties every `records` list found. Unknown holders are
    reported, never retained.
    """
    totals = {}

    def _merge(t):
        for path, counters in (t or {}).items():
            slot = totals.setdefault(path, {})
            for k, v in (counters or {}).items():
                if isinstance(v, (int, float)):
                    slot[k] = slot.get(k, 0) + v

    def _drain_holder(h):
        # NavCounters-shape ONLY (records list + totals method):
        # never clear an arbitrary product list.
        recs = getattr(h, "records", None)
        if not isinstance(recs, list) or not callable(
                getattr(h, "totals", None)):
            return False
        try:
            _merge(h.totals())
        except Exception:  # noqa: BLE001 - evidence best-effort
            pass
        n = len(recs)
        del recs[:]
        assert len(recs) == 0
        return True

    seen = set()

    def _walk(o, depth):
        if o is None or depth < 0 or id(o) in seen:
            return
        seen.add(id(o))
        if _drain_holder(o):
            return
        kids = []
        try:
            kids.extend(vars(o).values())
        except TypeError:
            pass
        if isinstance(o, dict):
            kids.extend(o.values())
        elif isinstance(o, (list, tuple)):
            kids.extend(o)
        for k in kids:
            _walk(k, depth - 1)

    for obj in objs:
        _walk(obj, 4)
    return totals


# ---------------------------------------------------------------- evidence

def resolve_entry_text(tlstore, index, entry):
    """Ground one served entry in committed bytes (or None + reason)."""
    aid = (entry or {}).get("atom_id")
    if not aid:
        return None, "no-atom-id"
    meta = (getattr(index, "atoms", None) or {}).get(aid)
    if meta is None:
        return None, "atom-not-in-index"
    try:
        raw = tlstore.read_artifact(meta["text_art"],
                                    expect_digest=meta["text_digest"])
    except Exception as e:  # noqa: BLE001 - classified, never raised
        return None, f"artifact-read-failed:{type(e).__name__}"
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "non-utf8-text"


def score_expected(served_docs, served_texts, expected):
    """Expected-evidence accounting for one case.

    expected: {docs:[...], spans:[...]}. Spans are required
    substrings of served entry texts (source grounding).
    """
    want_docs = list((expected or {}).get("docs") or [])
    want_spans = list((expected or {}).get("spans") or [])
    hit_docs = sorted(set(served_docs) & set(want_docs))
    span_hits = {}
    for sp in want_spans:
        span_hits[sp] = any(sp in (t or "") for t in served_texts)
    return {
        "want_docs": want_docs,
        "hit_docs": hit_docs,
        "doc_recall": (len(hit_docs) / len(want_docs)
                       if want_docs else None),
        "span_hits": span_hits,
        "all_spans_hit": (all(span_hits.values()) if want_spans
                          else None),
    }


def has_trace_path(entry, receipt, key_paths):
    """True iff any frozen trace key path is present and non-empty.

    Paths use dotted notation; a leading `entry.` addresses the
    served entry, `receipt.` addresses the receipt. Lists/dicts
    count only when non-empty.

    RETIRED as a G2 pass predicate (v2): presence alone accepts a
    document-container field or an unrelated receipt-global trace.
    Kept for disclosure measurements only; G2 now requires
    resolve_hierarchy_trace().
    """
    hits = []
    for kp in key_paths or []:
        if kp.startswith("entry."):
            cur, parts = entry, kp.split(".")[1:]
        elif kp.startswith("receipt."):
            cur, parts = receipt or {}, kp.split(".")[1:]
        else:
            continue
        ok = True
        for part in parts:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, "", [], {}):
            hits.append(kp)
    return hits


def resolve_hierarchy_trace(path, index, want_docs=None):
    """Verify a claimed higher->child->evidence path against committed state.

    path: [parent_id, leaf_id, atom_id] (exactly 3 legs).
    index: NarrowIndex at the serving pin (same-pin identity is the
      caller's contract: build the index at the pin being served).
    want_docs: optional set of expected doc ids the evidence must
      support; when given, the resolved atom's doc must be a member.

    Checks: parent in seg_parents, leaf in seg_leaves, leaf listed
    in the parent's committed children, atom listed in the leaf's
    committed members, atom present with a doc id (in want_docs
    when given). Returns {"resolved": bool, "why": str, ...}.
    A flat/direct-atom [leaf, atom] path can never resolve here.
    """
    if not isinstance(path, (list, tuple)) or len(path) != 3:
        return {"resolved": False, "why": "path-must-be-3-legs"}
    parent, leaf, aid = path
    try:
        parents = index.seg_parents
        leaves = index.seg_leaves
        holons = index.holons
        atoms = index.atoms
    except AttributeError as e:
        return {"resolved": False, "why": f"index-shape:{e}"}
    if parent not in parents:
        return {"resolved": False, "why": "parent-not-committed"}
    if leaf not in leaves:
        return {"resolved": False, "why": "leaf-not-committed"}
    kids = (holons.get(parent) or {}).get("children") or []
    if leaf not in kids:
        return {"resolved": False, "why": "leaf-not-parent-child"}
    members = (leaves.get(leaf) or {}).get("members") or []
    if aid not in members:
        return {"resolved": False, "why": "atom-not-leaf-member"}
    meta = atoms.get(aid)
    if meta is None:
        return {"resolved": False, "why": "atom-not-in-index"}
    doc = meta.get("doc_id")
    if want_docs is not None and doc not in set(want_docs):
        return {"resolved": False, "why": "evidence-not-expected",
                "doc_id": doc}
    return {"resolved": True, "why": "ok", "doc_id": doc,
            "parent": parent, "leaf": leaf, "atom": aid}


TOK_V1_RE = re.compile(r"[^\W_]+")


def tok_v1_count(text):
    """TOK-v1 token count: [^\\W_]+ runs (encoder/verifier denominator)."""
    return len(TOK_V1_RE.findall(text or ""))


def plan_workload_appends(doc_stream, bases, target_chunks,
                          target_tokens, tol=0, label="plan"):
    """Fixed-work append sets at distinct seeded base populations.

    doc_stream: [(doc_id, n_chunks, n_ws_tokens, n_tok_v1)] in corpus
      order. bases: [base_doc_counts...] (nonempty, strictly growing
      seeded populations). target_chunks/target_tokens: the fixed
      append workload; tol: relative tolerance per append (default
      0 = exact, per the frozen v3 rule; pass explicitly for
      banded exploration).

    Each base Bi takes the first Bi corpus docs; its append adds
    whole docs until BOTH chunk and token targets are met, and must
    land within tol of both. Returns {"feasible": bool, ...} with
    per-append actual docs/chunks/tokens recorded. Unlike
    plan_prefixes (exact-equal thirds of one corpus), bases may
    overlap and appends need not partition the corpus.
    """
    if sorted(bases) != list(bases) or any(
            b <= 0 for b in bases) or len(set(bases)) != len(bases):
        return {"feasible": False, "label": label,
                "why": "bases must be distinct positive growing counts"}
    if not target_chunks or not target_tokens:
        return {"feasible": False, "label": label,
                "why": "empty append target"}
    if not (0 <= tol < 1):
        return {"feasible": False, "label": label,
                "why": "tol must be in [0,1)"}
    n = len(doc_stream)
    if max(bases) >= n:
        return {"feasible": False, "label": label,
                "why": "largest base leaves no append docs"}
    appends = []
    for bi, base in enumerate(bases):
        ac, at, docs = 0, 0, []
        for j in range(base, n):
            did, c, _w, v = doc_stream[j]
            docs.append(did)
            ac += c
            at += v
            if ac >= target_chunks and at >= target_tokens:
                break
        if ac < target_chunks or at < target_tokens:
            return {"feasible": False, "label": label,
                    "why": f"base {base}: corpus exhausted before "
                           f"targets (chunks={ac} tokens={at})"}
        dc = abs(ac - target_chunks) / target_chunks
        dt = abs(at - target_tokens) / target_tokens
        if dc > tol or dt > tol:
            return {"feasible": False, "label": label,
                    "why": f"base {base}: append outside tol "
                           f"(chunks={ac} d={dc:.3f} tokens={at} "
                           f"d={dt:.3f} tol={tol})"}
        appends.append({"base": bi, "base_docs": base,
                        "append_docs": docs,
                        "chunks": ac, "tokens_tok_v1": at,
                        "d_chunks": round(dc, 4),
                        "d_tokens": round(dt, 4)})
    return {"feasible": True, "label": label, "appends": appends,
            "target": {"chunks": target_chunks,
                       "tokens_tok_v1": target_tokens},
            "tol": tol}


def assess_fixed_work(actual, target_chunks, target_tokens, tol):
    """Fixed-work append assessment (G4 fixed-work-v2 rule).

    actual: [(chunks, tokens_tok_v1)] per append in campaign order.
    target_chunks/target_tokens: the frozen workload from the
      inputs file. tol: relative tolerance from the criteria rule;
      v3 freezes tol=0 (exact equal work).

    A missing/invalid tol FAILS CLOSED (no silent default): the
    gate must never grade a fixed-work campaign against a
    tolerance the frozen criteria did not declare. Returns {"ok",
    "tol_ok", "target_ok", "why", "appends", "tol"}.
    """
    ok_num = (isinstance(tol, (int, float))
              and not isinstance(tol, bool)
              and 0 <= tol < 1)
    target_ok = bool(target_chunks and target_tokens)
    per = []
    ok_all = True
    for i, (c, v) in enumerate(actual or ()):
        dc = (abs(c - target_chunks) / target_chunks
              if target_chunks else None)
        dt = (abs(v - target_tokens) / target_tokens
              if target_tokens else None)
        within = (target_ok and ok_num and dc <= tol and dt <= tol)
        ok_all = ok_all and bool(within)
        per.append({"append": i, "chunks": c,
                    "tokens_tok_v1": v, "d_chunks": dc,
                    "d_tokens": dt, "within_tol": bool(within)})
    why = None
    if not ok_num:
        why = f"tol not declared as a number in [0,1): {tol!r}"
    elif not target_ok:
        why = "append_workload target missing/empty in inputs"
    elif not ok_all:
        why = "append(s) outside tol"
    return {"ok": bool(ok_num and target_ok and ok_all),
            "tol_ok": bool(ok_num), "target_ok": bool(target_ok),
            "why": why, "appends": per, "tol": tol}


RETIREMENT_KEYWORDS = ("retir", "exclud", "withdraw", "supersed",
                       "tombstone")


def probe_retirement_capability(*modules):
    """Behavioral retirement/exclusion capability probe (harness-side).

    Stage 1 (interface): enumerate candidate owning callables whose
    names carry retirement/exclusion semantics. Stage 2
    (behavioral): only when a candidate exists, exercise it on a
    caller-supplied scratch store (the caller runs the behavior;
    this helper reports the interface verdict).

    A substring/presence match alone NEVER closes the bar: with no
    candidate owning interface the result is an explicit capability
    gap plus the required interface shape. Returns a report dict.
    """
    candidates = []
    for mod in modules:
        if mod is None:
            continue
        for name in dir(mod):
            if any(k in name.lower()
                   for k in RETIREMENT_KEYWORDS):
                try:
                    obj = getattr(mod, name)
                except Exception:  # noqa: BLE001 - intake best-effort
                    continue
                # place.discover(exclude=...) style parameters and doc
                # prose are not retirement interfaces: only module-level
                # callables count as candidates.
                if callable(obj):
                    candidates.append(
                        f"{getattr(mod, '__name__', '?')}.{name}")
    if candidates:
        return {"supported": "unknown",
                "candidates": sorted(set(candidates)),
                "note": "candidate interface(s) found; caller must "
                        "exercise retire->verify-excluded->export-omits "
                        "behaviorally before claiming support"}
    return {"supported": False,
            "candidates": [],
            "capability_gap": True,
            "note": "no owning retirement/exclusion interface found",
            "required_interfaces": [
                "tlsys: retire/withdraw(doc_id|atom_id, reason) -> "
                "committed tombstone/supersede record",
                "tlsys: serving exclusion (retired evidence never "
                "emitted; exclusion verifiable per query)",
                "tlsys: export omits retired payloads with a disclosed "
                "omission identity (retry/export frontier accounts)",
            ]}


# ------------------------------------------------------- oracle sampling

def plan_oracle_sample(universe, seed, min_pins=3, min_queries=5):
    """Seeded G6 (pin x query) sample over pins with servable queries.

    universe: [(pin_tag, pin_triple, [query_ids])] in campaign order.
      A pin is eligible only when it carries >= min_queries
      servable queries (queries actually served at that pin through
      their campaign entry points; no cross-generation reruns).
    Returns {"feasible": bool, "sampled": [(tag, triple, [qids])],
    "seed": seed, ...}. Infeasible (too few pins or too few
    queries at a pin) is a caller FAIL, never a silent smaller
    sample: the frozen rule is >= min_pins x >= min_queries.
    """
    import random
    eligible = [(t, tr, list(qs)) for t, tr, qs in (universe or [])
                if len(qs or ()) >= min_queries]
    if len(eligible) < min_pins:
        return {"feasible": False,
                "why": f"only {len(eligible)} pins carry "
                       f">={min_queries} servable queries "
                       f"(need {min_pins})",
                "seed": seed, "min_pins": min_pins,
                "min_queries": min_queries,
                "per_pin_counts": [(t, len(qs or ()))
                                   for t, _tr, qs in (universe
                                                     or ())]}
    rng = random.Random(seed)
    picked = rng.sample(eligible, min_pins)
    sampled = [(t, tr, rng.sample(list(qs), min_queries))
               for t, tr, qs in picked]
    return {"feasible": True, "seed": seed, "min_pins": min_pins,
            "min_queries": min_queries, "sampled": sampled,
            "rule": f">={min_pins} pins x >={min_queries} queries"}


def select_worker_peak(worker_report, rusage_delta_kb):
    """Honest per-worker peak: the worker's own self maxrss first.

    RUSAGE_CHILDREN ru_maxrss is a cumulative high-water mark; a
    delta of successive maxima is NOT a per-worker peak. The worker
    reports resource.getrusage(RUSAGE_SELF).ru_maxrss (its true
    peak); the parent delta is kept as a labeled cross-check only.
    """
    rep = worker_report or {}
    self_peak = rep.get("self_peak_kb")
    try:
        delta = int(rusage_delta_kb or 0)
    except (TypeError, ValueError):
        delta = 0
    if isinstance(self_peak, int) and self_peak > 0:
        return {"peak_kb": self_peak, "source": "worker-self",
                "cross_check_delta_kb": max(0, delta)}
    if delta > 0:
        return {"peak_kb": delta,
                "source": "rusage-children-delta-fallback",
                "cross_check_delta_kb": delta}
    return {"peak_kb": None, "source": "unknown",
            "cross_check_delta_kb": max(0, delta)}


def default_oracle_cap_mb(tier):
    """Tier-default G6 worker RLIMIT_AS cap (MiB).

    Full-tier query workers map libtorch for the pinned query
    encoder (2048 MiB cannot map it; 8192 approved per the frozen
    rule); fixture workers stay at 2048. The cap bounds every
    worker in both tiers.
    """
    return 8192 if tier == "full" else 2048


def run_capped(cmd, timeout_s=300, cap_bytes=1 << 20, as_mb=None):
    """Run cmd with file-backed stdio + byte caps + optional RLIMIT_AS.

    stdout/stderr stream to temp files (never accumulated in
    memory); sizes are enforced AFTER the run and always recorded.
    Returns (rc, info): rc is the exit code or "timeout"; info
    carries stdout/stderr bytes, capped bool, a bounded stderr
    head, and the applied rlimit/timeout. Temp files removed.
    """
    import resource as _res
    import shutil
    import subprocess
    import tempfile
    tmpd = tempfile.mkdtemp(prefix="gate-capped-")
    out_p = os.path.join(tmpd, "stdout.bin")
    err_p = os.path.join(tmpd, "stderr.bin")
    cap = int(as_mb) * 1024 * 1024 if as_mb else None

    def _limit():
        if cap is None:
            return
        try:
            _res.setrlimit(_res.RLIMIT_AS, (cap, cap))
        except (ValueError, OSError):
            pass

    rc = None
    try:
        with open(out_p, "wb") as fo, open(err_p, "wb") as fe:
            try:
                p = subprocess.run(cmd, stdout=fo, stderr=fe,
                                   timeout=timeout_s,
                                   preexec_fn=_limit if cap
                                   else None)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                rc = "timeout"
    finally:
        try:
            so = os.path.getsize(out_p)
        except OSError:
            so = 0
        try:
            se = os.path.getsize(err_p)
        except OSError:
            se = 0
        head = ""
        try:
            with open(err_p, "rb") as fe:
                head = fe.read(300).decode("utf-8", "replace")
        except OSError:
            pass
        shutil.rmtree(tmpd, ignore_errors=True)
    return rc, {"stdout_bytes": so, "stderr_bytes": se,
                "capped": so <= cap_bytes and se <= cap_bytes,
                "cap_bytes": cap_bytes, "stderr_head": head,
                "rlimit_as_mb": as_mb, "timeout_s": timeout_s}


SNAPSHOT_EXCLUDE = ("committer.lock", "commit.db-shm")


def snapshot_store(src, dst, exclude=SNAPSHOT_EXCLUDE):
    """Filesystem copy of a quiescent store directory for pin travel.

    The caller snapshots synchronously while the generation is
    live (no concurrent writers); the worker proves exactness by
    asserting its live pin triple. The fence lock is NOT copied
    (a copied lock trips the lock-path identity fail-closed):
    the copy gets a FRESH lock file and its OWN meta
    lock_dev/lock_ino record is re-keyed to it — the live store
    is never written. The copied WAL-index (-shm) is excluded;
    SQLite rebuilds it from the copied WAL on open. Returns
    {ok, files, bytes, excluded, rekeyed}.
    """
    import shutil
    import sqlite3
    skip = set(exclude or ())

    def _ignore(_d, names):
        return [n for n in names if n in skip]

    try:
        shutil.copytree(src, dst, ignore=_ignore)
    except Exception as e:  # noqa: BLE001 - reported, not raised
        return {"ok": False, "error": f"{type(e).__name__}:"
                f"{str(e)[:200]}"}
    rekeyed, rekey_detail = False, "no-db"
    lock_p = os.path.join(dst, "committer.lock")
    db_p = os.path.join(dst, "commit.db")
    try:
        fd = os.open(lock_p, os.O_RDWR | os.O_CREAT | os.O_TRUNC,
                     0o644)
        try:
            s = os.fstat(fd)
            dev, ino = s.st_dev, s.st_ino
        finally:
            os.close(fd)
        if os.path.isfile(db_p):
            con = sqlite3.connect(db_p, timeout=30)
            try:
                rows = {r[0]: r[1] for r in con.execute(
                    "SELECT k, v FROM meta WHERE k IN "
                    "('lock_dev','lock_ino')")}
                if "lock_dev" in rows and "lock_ino" in rows:
                    con.execute(
                        "UPDATE meta SET v=? WHERE k='lock_dev'",
                        (str(dev),))
                    con.execute(
                        "UPDATE meta SET v=? WHERE k='lock_ino'",
                        (str(ino),))
                    con.commit()
                    rekeyed = True
                    rekey_detail = {"dev": dev, "ino": ino}
                else:
                    rekey_detail = "lock-identity-record-missing"
            finally:
                con.close()
        else:
            rekey_detail = "no-db"
    except Exception as e:  # noqa: BLE001 - reported, not raised
        rekey_detail = (f"{type(e).__name__}:"
                        f"{str(e)[:200]}")
    counts = dir_size_bytes(dst)
    return {"ok": True, "dst": dst, "files": counts["files"],
            "bytes": counts["bytes"],
            "excluded": sorted(skip), "rekeyed": rekeyed,
            "rekey_detail": rekey_detail}


def journal_usage(store_root):
    """Bounded intake-journal stats (streamed, no full retention).

    present/records/bytes describe the journal FILE (absent after
    a clean call: applied records are consumed at call end, so
    absence + journal_seq > 0 is the clean-journal state).
    journal_seq is the durable manifest counter (bounded regex
    scan, never a full manifest parse): > 0 proves declarations
    and per-flush progress went through the journal path.
    manifest_bytes is the intake manifest size (journal mode
    saves it once per call instead of per flush).
    """
    jp = os.path.join(store_root or "", "ingest_progress.jsonl")
    mp = os.path.join(store_root or "", "ingest_manifest.json")
    try:
        mb = os.path.getsize(mp)
    except OSError:
        mb = 0
    seq = None
    if os.path.isfile(mp):
        try:
            pat = re.compile(rb'"_journal_seq"\s*:\s*(\d+)')
            tail = b""
            with open(mp, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        break
                    m = pat.search(tail + chunk)
                    if m:
                        seq = int(m.group(1))
                        break
                    tail = (tail + chunk)[-32:]
        except OSError:
            pass
    base = {"manifest_bytes": mb, "journal_seq": seq}
    if not os.path.isfile(jp):
        base.update({"present": False, "records": 0, "bytes": 0})
        return base
    n, b = 0, 0
    try:
        with open(jp, "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                b += len(chunk)
                n += chunk.count(b"\n")
    except OSError:
        base.update({"present": False, "records": 0, "bytes": 0})
        return base
    base.update({"present": True, "records": n, "bytes": b})
    return base


def checkpoint_usage(store_root):
    """Projection checkpoint footprint: snapshot + journal bytes."""
    sp = os.path.join(store_root or "", "tl_projections.json")
    jp = os.path.join(store_root or "",
                      "tl_projections.journal.jsonl")
    try:
        sb = os.path.getsize(sp)
    except OSError:
        sb = 0
    try:
        jb = os.path.getsize(jp)
    except OSError:
        jb = 0
    return {"snapshot_bytes": sb, "journal_bytes": jb,
            "total_bytes": sb + jb}


# ------------------------------------------------------- export auditing

def audit_export_coverage(live_atoms, live_holons, export,
                          retired_docs=None):
    """Every live occurrence exported exactly once, omissions accounted.

    live_atoms: {atom_id: doc_id} (or iterable of atom ids);
    live_holons: {doc_id}. export: export_store-shaped dict.
    A live atom/holon missing from the export FAILS unless a
    doc-scoped omission entry with cause "retired:<op>" covers its
    doc AND the doc is in retired_docs AND atoms_withheld equals
    the missing atom count for that doc. Exported-but-not-live
    (ghost) records FAIL. counts.* must agree with the lists.
    """
    retired = set(retired_docs or ())
    if isinstance(live_atoms, dict):
        atom_doc = dict(live_atoms)
    else:
        atom_doc = {a: None for a in (live_atoms or ())}
    live_h = set(live_holons or ())
    exp = export or {}
    recs = exp.get("records") or []
    hols = exp.get("holons") or []
    omis = exp.get("omissions") or []
    counts = exp.get("counts") or {}
    got_atoms = [r.get("atom_id") for r in recs]
    got_holons = [h.get("holon") for h in hols]
    missing_atoms = sorted(set(atom_doc) - set(got_atoms))
    extra_atoms = sorted(set(got_atoms) - set(atom_doc))
    missing_holons = sorted(live_h - set(got_holons))
    extra_holons = sorted(set(got_holons) - live_h)
    accounted = []
    problems = []
    by_doc_missing = {}
    for a in missing_atoms:
        by_doc_missing.setdefault(atom_doc.get(a), []).append(a)
    for o in omis:
        if not isinstance(o, dict):
            continue
        scope, cause = o.get("scope"), o.get("cause")
        if not (isinstance(scope, str)
                and scope.startswith("doc:")
                and isinstance(cause, str)
                and cause.startswith("retired:")):
            continue
        doc = scope[len("doc:"):]
        if doc not in retired:
            problems.append(f"omission-for-undeclared-{doc}")
            continue
        miss = by_doc_missing.get(doc, [])
        if o.get("atoms_withheld") != len(miss):
            problems.append(f"withheld-mismatch-{doc}:"
                            f"{o.get('atoms_withheld')}"
                            f"!={len(miss)}")
            continue
        accounted.append(doc)
        for a in miss:
            if a in missing_atoms:
                missing_atoms.remove(a)
        if doc in missing_holons:
            missing_holons.remove(doc)
    if sorted(set(counts)) and (
            counts.get("atoms") != len(recs)
            or counts.get("holons") != len(hols)):
        problems.append("counts disagree with record lists")
    withheld_total = sum(o.get("atoms_withheld", 0) for o in omis
                         if isinstance(o, dict)
                         and isinstance(o.get("atoms_withheld"),
                                        int))
    if "omitted" in counts and counts.get("omitted") != withheld_total:
        problems.append("counts.omitted disagrees with omissions")
    ok = (not missing_atoms and not extra_atoms
          and not missing_holons and not extra_holons
          and not problems)
    return {"ok": ok, "missing_atoms": missing_atoms,
            "extra_atoms": extra_atoms,
            "missing_holons": missing_holons,
            "extra_holons": extra_holons,
            "omissions_accounted": sorted(accounted),
            "problems": problems}


# ------------------------------------------------------- debt auditing

def assess_catchup(maint_rows, initial_pending, final_pending):
    """Catch-up rate + keeps-pace + backpressure + blocking verdicts.

    maint_rows: per-drain {drained, failed, drain_s, drain_error?}.
    keeps_pace holds iff pending reaches zero within the declared
    schedule OR bounded backpressure holds (criteria g5); a drain
    that errors FAILS blocking. Pure: no store access.
    """
    drained = sum(int(r.get("drained") or 0)
                  for r in (maint_rows or []))
    failed = sum(int(r.get("failed") or 0)
                 for r in (maint_rows or []))
    secs = sum(float(r.get("drain_s") or 0.0)
               for r in (maint_rows or []))
    rate = (drained / secs) if secs > 0 else None
    errors = [r.get("drain_error") for r in (maint_rows or [])
              if r.get("drain_error")]
    backpressure_ok = (final_pending or 0) <= (initial_pending or 0)
    keeps_pace = ((final_pending or 0) == 0 and not errors) or (
        backpressure_ok and not errors)
    return {"catchup_rate": rate, "drained_total": drained,
            "failed_total": failed, "drain_s_total": round(secs, 3),
            "keeps_pace": bool(keeps_pace),
            "backpressure_ok": bool(backpressure_ok),
            "blocking_ok": not errors, "drain_errors": errors}


# ---------------------------------------------------------------- misc

class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *a):
        self.s = time.perf_counter() - self.t0
        return False


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def python_identity():
    return {"executable": sys.executable, "version": sys.version,
            "hash_seed": os.environ.get("PYTHONHASHSEED"),
            "hf_home": os.environ.get("HF_HOME"),
            "hf_offline": os.environ.get("HF_HUB_OFFLINE")}
