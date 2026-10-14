"""Lane BUILD100M-C2: quarantined C2-profile store build driver (§5.5/§5.7).

Corrected §5.7 driver: builds a committed store with the keyed P
backend (keyed_state=True + one shared ProducerSession) with ONE
validated catalog-enabled profile bound through the session AND every
producer call (ingest/drain/organize). profile=None (reference
organization) is refused; see DERIVATION.md. Two modes:

  10m  — C1-shape replication from docs-10m.jsonl (per-prefix ingest +
         drain, anchor-v1 publication, ONE organize at end) for the
         keyed≡legacy slice-scale differential.
  100m — the quarantined C2 100M store build from docs-100m.jsonl
         (per-prefix ingest + drain + organize, snapshots, NO
         publication: no 100M relations input exists; recorded).

Every phase appends a checkpoint to checkpoints.jsonl (wall, rows,
bytes, pins, report digest). --resume reopens the store and skips
completed phases (ingest skips source-durable docs, drain/organize
are commit-free no-ops on completed work, publication is guarded by
its checkpoint + a pre-commit relations count).

Any failure writes FAILURE.json and exits 1: no retries without a
changed hypothesis (STOP-and-classify).

Usage on the VM (from the synced work dir):
  PYTHONHASHSEED=0 HF_HUB_OFFLINE=1 /srv/tl/venv/bin/python \\
    lane-RELAUNCH/b100m_build_c2.py --mode 10m \\
    --root /srv/tl/lane-relaunch/work \\
    --out /srv/tl/lane-relaunch/scratch/build-10m-c2 \\
    --profile /srv/tl/lane-relaunch/work/inputs/c2-profile-100m.json \\
    --cache-dir /srv/tl/stores/encode-5050/emb_cache

RELAUNCH repairs (§5.8 item 1): publication expects
n_relations + n_qual_signals (C1-correct 5, not the stale `!= 3`);
idempotent-publication re-entry verifies counts + rel_type multiset
and never duplicates; bind_candidate_store runs once after the
first commit; ONE explicit export_manifest_archive per completed
bulk prefix (+ one final boundary archive in 10m mode), each cost
recorded separately in its own checkpoint.
"""
import argparse
import json
import os
import shutil
import sys
import time
import traceback


GUARD = "lane-relaunch"
STORE_ID = "gate-full"

PIN_DOCS_10M = "04bbbb3ea3425a49491559173b20280fb286edeeef49c8293aebc0b92bcce3fd"
PIN_DOCS_100M = "c098fdace3a73efc83f3c71a9e024b3cd77114fd0d7f2348c7c813995e6b0e09"
PIN_ANCHORS_V1 = "9728129bd96b8a948bd60ace37d7c270af2779cc33154624a0653e4e5cf33754"

CFG_EXTRACTOR = {"extractor": "gate-runner-v1", "window": 1,
                 "model": "none", "rules": ["gate-confirmation"]}


def log(msg):
    print(f"[b100m {time.strftime('%H:%M:%S', time.gmtime())}Z] {msg}",
          flush=True)


def sha256_file(path, chunk=1 << 20):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def trim(rep, cap=12):
    """Small JSON-safe digest of a producer report (no big lists)."""
    out = {}
    for k, v in (rep or {}).items():
        if isinstance(v, list):
            out[k] = {"n": len(v), "sample": v[:3]} if len(v) > cap \
                else v
        elif isinstance(v, dict):
            out[k] = trim(v, cap=cap) if len(str(v)) > 2000 else v
        else:
            out[k] = v
    return out


def load_c2_profile(root, profile_path):
    """Load + Lane-G-validate the build profile (refuses, never degrades)."""
    import importlib.util
    lane_g = os.path.join(
        root, "coordination", "c2-work-20261006T1925Z", "lane-G",
        "profile.py")
    if not os.path.isfile(lane_g):
        raise RuntimeError(f"refusing: lane-G profile.py missing: {lane_g}")
    if not os.path.isfile(profile_path):
        raise RuntimeError(
            f"refusing: --profile missing: {profile_path}")
    spec = importlib.util.spec_from_file_location(
        "c2_lane_g_profile", lane_g)
    gprof = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gprof)
    prof = gprof.load_profile(profile_path)  # raises when malformed
    if not prof["flags"]["organization_catalog_routing"]:
        raise RuntimeError(
            "refusing: profile does not enable catalog routing "
            "(reference organization is not a C2 build)")
    return prof


def assert_catalog_engaged(rep, where, require_decisions):
    """§5.7 per-call binding proof: catalog receipt + gate + session.

    Raises RuntimeError (→ FAILURE.json, no retry) when the call did
    not run the bound catalog path: missing receipt, over-budget
    latch, any R_cat rejection, or an ephemeral (non-shared) session.
    """
    cat = (rep or {}).get("catalog")
    if not isinstance(cat, dict):
        raise RuntimeError(
            f"{where}: missing catalog receipt (profile not engaged?)")
    if cat.get("over_budget"):
        raise RuntimeError(
            f"{where}: over_budget latched (max_rows="
            f"{cat.get('max_rows_per_decision')})")
    rejected = cat.get("rejected") or []
    if isinstance(rejected, dict):  # trimmed form never occurs pre-trim
        raise RuntimeError(f"{where}: rejected present in dict form")
    if len(rejected):
        raise RuntimeError(
            f"{where}: {len(rejected)} R_cat rejections: "
            f"{str(rejected[:2])[:400]}")
    if require_decisions and not cat.get("decisions"):
        raise RuntimeError(
            f"{where}: catalog receipt has 0 decisions (not engaged)")
    keyed = (rep or {}).get("keyed") or {}
    if "session" not in keyed:
        raise RuntimeError(
            f"{where}: shared ProducerSession not engaged "
            f"(keyed keys: {sorted(keyed)[:8]})")
    return {"decisions": int(cat.get("decisions") or 0),
            "max_rows": int(cat.get("max_rows_per_decision") or 0),
            "ties": cat.get("ties") or [],
            "pops": sorted(k for k in cat
                           if k in ("xholon", "leaf", "parent")
                           and cat[k] is not None)}


def catalog_totals(checkpoints_done):
    """Aggregate engaged-catalog work over checkpointed producer reports."""
    tot = {"decisions": 0, "max_rows_per_decision": 0, "ties": 0,
           "rejected": 0, "over_budget_any": False, "pops": set(),
           "rows": {}, "bytes": {}, "calls": {}}
    for phase, rec in checkpoints_done.items():
        if not (phase.startswith("ingest-") or phase.startswith("drain-")
                or phase.startswith("organize-")):
            continue
        cat = ((rec.get("report") or {}).get("catalog")) or {}
        if not cat:
            continue
        tot["decisions"] += int(cat.get("decisions") or 0)
        tot["max_rows_per_decision"] = max(
            tot["max_rows_per_decision"],
            int(cat.get("max_rows_per_decision") or 0))
        ties = cat.get("ties") or []
        tot["ties"] += ties["n"] if isinstance(ties, dict) \
            else len(ties)
        rej = cat.get("rejected") or []
        tot["rejected"] += rej["n"] if isinstance(rej, dict) \
            else len(rej)
        tot["over_budget_any"] = bool(
            tot["over_budget_any"] or cat.get("over_budget"))
        for pop in ("xholon", "leaf", "parent"):
            blk = cat.get(pop)
            if isinstance(blk, dict):
                tot["pops"].add(pop)
                for key in ("rows", "bytes", "calls"):
                    if isinstance(blk.get(key), (int, float)):
                        tot[key][pop] = tot[key].get(pop, 0) + blk[key]
    tot["pops"] = sorted(tot["pops"])
    return tot


class Checkpoints:
    def __init__(self, path, resume):
        self.path = path
        self.done = {}
        if resume and os.path.isfile(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    self.done[rec["phase"]] = rec
        self.fh = open(path, "a")

    def has(self, phase):
        return phase in self.done

    def write(self, rec):
        rec = dict(rec)
        rec["utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                   time.gmtime())
        self.fh.write(json.dumps(rec) + "\n")
        self.fh.flush()
        self.done[rec["phase"]] = rec

    def close(self):
        self.fh.close()


def plan_prefixes_100m(docs_path, n_prefixes, chunk_text):
    """Greedy equal-chunk prefix split over file-order docs.

    Returns (prefixes, geometry): prefixes[i] = [doc_ids] cumulative
    (prefix i contains all docs of prefix i-1 plus new ones, C1
    campaign shape); geometry[i] = {docs, chunks, tok_v1} ADDED.
    One bounded streaming pass; texts are never retained.
    """
    import re
    tok_v1 = re.compile(r'[^\W_]+', re.UNICODE)
    counts = []  # (doc_id, n_chunks, tok_v1)
    with open(docs_path, "rb") as f:
        for raw in f:
            raw = raw.rstrip(b"\n")
            if not raw.strip():
                continue
            row = json.loads(raw.decode("utf-8"))
            text = row["text"]
            counts.append((row["doc_id"], len(chunk_text(text)),
                           len(tok_v1.findall(text))))
    total_chunks = sum(c for _d, c, _v in counts)
    target = total_chunks / n_prefixes
    prefixes, geometry = [], []
    cur, acc_c, acc_v = [], 0, 0
    start = 0
    for i, (doc_id, nc, nv) in enumerate(counts):
        cur.append(doc_id)
        acc_c += nc
        acc_v += nv
        last = (i == len(counts) - 1)
        if (acc_c >= target and len(prefixes) < n_prefixes - 1) or last:
            prefixes.append(list(cur))
            geometry.append({"docs": len(cur) - start,
                             "chunks": acc_c, "tok_v1": acc_v})
            start = len(cur)
            acc_c, acc_v = 0, 0
    return prefixes, geometry


def store_bytes(store_root):
    total, files = 0, 0
    for dirpath, _dirs, names in os.walk(store_root):
        for n in names:
            p = os.path.join(dirpath, n)
            try:
                total += os.path.getsize(p)
                files += 1
            except OSError:
                pass
    return {"bytes": total, "files": files}


def pin_triple(tl):
    b, e, mx, triple = tl.pin()
    return {"birth": b, "epoch": e, "max_seq": mx, "triple": triple}


def prove_snapshot_open(tl_cls, snap_dir, expect_triple):
    """Open a snapshot copy read-mostly and prove its live pin triple.

    Opens with create=False under its own lease, reads the pin, and
    closes. Raises on any mismatch.
    """
    tl = tl_cls(snap_dir, create=False,
                lease_owner=f"b100m-proof-{os.getpid()}")
    try:
        got = tl.pin()[3]
    finally:
        tl.close()
    if got != expect_triple:
        raise RuntimeError(
            f"snapshot {snap_dir}: pin {got} != live {expect_triple}")
    return got


def run_publication_10m(tl, anchors_path, store_id):
    """Replicate the C1 publication block (current-tree anchor path).

    NarrowIndex at the pre-publication pin, resolve endpoints/signals
    from the anchors-v1 specs, commit relations + qual signals.
    Idempotent re-entry: when relations are already committed, verify
    the committed count AND rel_type multiset against the anchors
    specs and return a resumed receipt WITHOUT committing again.
    Anything else already committed is refused (no duplicate
    publication, no silent adoption of foreign records).
    """
    from tlsys.index import NarrowIndex
    from tlsys import relations as _relations
    from tlsys import relquery as _relquery
    import run_integrated_gate as gate
    with open(anchors_path) as f:
        rf = json.load(f)
    rel_specs = rf["relations"]
    sig_specs = rf.get("qual_signals", [])
    expect_n = len(rel_specs) + len(sig_specs)
    expect_types = sorted([rs["rel_type"] for rs in rel_specs]
                          + [_relquery.QUAL_SIGNAL_TYPE] * len(sig_specs))
    pre_pin = tl.pin()
    pre_rels = _relations.read_relations(tl, pre_pin)
    pre_n = len(pre_rels)
    if pre_n:
        got_types = sorted(row["record"]["rel_type"]
                           for row in pre_rels.values())
        if pre_n == expect_n and got_types == expect_types:
            log(f"publication: already committed {pre_n} "
                f"(verified counts + types vs anchors; no re-commit)")
            return {"n_relations": len(rel_specs),
                    "n_qual_signals": len(sig_specs),
                    "committed_relations": pre_n,
                    "resumed": True,
                    "pin_before": pre_pin[3], "pin_after": pre_pin[3]}
        raise RuntimeError(
            f"publication refused: {pre_n} relations already committed "
            f"but expected {expect_n} with types {expect_types}; got "
            f"types {got_types} (not this publication; refusing)")
    idx_pre = NarrowIndex(tl, pre_pin)
    anchor_docs = ({rs["src"] for rs in rel_specs}
                   | {rs["dst"] for rs in rel_specs}
                   | {ss["doc"] for ss in sig_specs})
    anchor_texts = {}
    for aid, meta in idx_pre.atoms.items():
        if meta.get("doc_id") not in anchor_docs:
            continue
        anchor_texts[aid] = tl.read_artifact(
            meta["text_art"],
            expect_digest=meta["text_digest"]).decode("utf-8")
    endpoints = gate.resolve_relation_endpoints(
        rel_specs, idx_pre.atoms, anchor_texts)
    sig_aids = gate.resolve_signal_anchors(
        sig_specs, idx_pre.atoms, anchor_texts)
    recs = []
    for rs, (a, b) in zip(rel_specs, endpoints):
        recs.append(_relations.make_record(
            rs["rel_type"], [("src", a), ("dst", b)],
            rs.get("qualifiers") or {}, CFG_EXTRACTOR,
            _relations.PROPOSED, [a, b]))
    _relations.commit_relations(tl, recs, store_id=store_id)
    sigs = []
    for ss, aid in zip(sig_specs, sig_aids):
        sigs.append(_relquery.make_qual_signal(
            aid, ss["qualifiers"], CFG_EXTRACTOR))
    if sigs:
        _relquery.commit_qual_signals(tl, sigs, store_id=store_id)
    _relations.invalidate_rel_index(tl)
    post_pin = tl.pin()
    post_rels = _relations.read_relations(tl, post_pin)
    return {"n_relations": len(recs), "n_qual_signals": len(sigs),
            "committed_relations": len(post_rels),
            "resumed": False,
            "pin_before": pre_pin[3], "pin_after": post_pin[3]}


def build_parser():
    ap = argparse.ArgumentParser(
        description="Quarantined C2 keyed store build driver.")
    ap.add_argument("--mode", choices=["10m", "100m"], required=True)
    ap.add_argument("--root", required=True,
                    help="synced work root (tl-sys/, tl-eval/, inputs/)")
    ap.add_argument("--out", required=True,
                    help="quarantined build dir (under lane-relaunch)")
    ap.add_argument("--profile", required=True,
                    help="C2 producer profile JSON (required; "
                    "reference organization is refused)")
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--docs-100m", default=None,
                    help="100m mode: VM corpus path")
    ap.add_argument("--n-prefixes", type=int, default=10,
                    help="100m mode: prefix count")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--drain-budget", type=int, default=2)
    ap.add_argument("--min-free-gb", type=float, default=80.0,
                    help="thin old mid-growth snapshots below this")
    ap.add_argument("--lease-owner", default=None)
    return ap


def main():
    ns = build_parser().parse_args()
    if GUARD not in os.path.abspath(ns.out):
        print(f"refusing: --out is not under {GUARD}", flush=True)
        return 2
    if ns.mode == "100m" and not ns.docs_100m:
        print("refusing: 100m mode needs --docs-100m", flush=True)
        return 2
    sys.path.insert(0, os.path.join(ns.root, "tl-sys"))
    sys.path.insert(0, os.path.join(ns.root, "tl-eval"))
    sys.path.insert(0, os.path.join(ns.root, "tl-eval", "gate_runner"))

    from tlsys.store_if import TLStore
    from tlsys.ingest import ingest_docs, chunk_text
    from tlsys import maint as _maint
    from tlsys.prodstate import (ProducerSession, bind_candidate_store,
                                 export_manifest_archive)
    from gpu_encode import config as _cfg
    from gpu_encode.consume import make_file_backed_emb
    from gate_lib import snapshot_store
    import run_integrated_gate as gate

    os.makedirs(ns.out, exist_ok=True)
    store_root = os.path.join(ns.out, "store")
    snap_dir = os.path.join(ns.out, "snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    ck = Checkpoints(os.path.join(ns.out, "checkpoints.jsonl"),
                     ns.resume)
    fail_path = os.path.join(ns.out, "FAILURE.json")
    if os.path.isfile(fail_path) and not ns.resume:
        print(f"refusing: {fail_path} exists (use --resume or clear)",
              flush=True)
        return 2

    log(f"mode={ns.mode} out={ns.out} resume={ns.resume}")
    log(f"env PYTHONHASHSEED={os.environ.get('PYTHONHASHSEED')} "
        f"HF_HUB_OFFLINE={os.environ.get('HF_HUB_OFFLINE')}")
    profile = load_c2_profile(ns.root, ns.profile)
    profile_sha = sha256_file(ns.profile)
    profile_rcat = profile["derived_limits"]["R_cat"]
    log(f"profile id={profile['profile_id']} "
        f"sha={profile_sha[:16]}… R_cat={profile_rcat}")

    # ---- pins ------------------------------------------------------
    docs_path = (os.path.join(ns.root, "inputs", "docs-10m.jsonl")
                 if ns.mode == "10m" else ns.docs_100m)
    want_docs = PIN_DOCS_10M if ns.mode == "10m" else PIN_DOCS_100M
    got_docs = sha256_file(docs_path)
    if got_docs != want_docs:
        print(f"refusing: docs hash {got_docs} != pin {want_docs}",
              flush=True)
        return 2
    log(f"docs pin OK {got_docs[:16]}… ({os.path.getsize(docs_path)} B)")
    anchors_path = os.path.join(ns.root, "inputs",
                                "relations-10m.anchors-v1.json")
    if ns.mode == "10m":
        got_a = sha256_file(anchors_path)
        if got_a != PIN_ANCHORS_V1:
            print(f"refusing: anchors hash {got_a} != pin",
                  flush=True)
            return 2
        log(f"anchors pin OK {got_a[:16]}…")

    emb_texts, cache_handle = make_file_backed_emb(
        ns.cache_dir, strict=True, fallback=None)
    got_cfg = cache_handle["reader"].meta.get("config_id")
    want_cfg = _cfg.config_id(_cfg.PRECISION_FIRST)
    if got_cfg != want_cfg:
        print(f"refusing: cache config {got_cfg} != {want_cfg}",
              flush=True)
        return 2
    log(f"encoder pin OK model={_cfg.MODEL_ID} "
        f"rev={_cfg.MODEL_REVISION[:12]}… cfg={got_cfg}")
    cache0 = cache_handle["stats"]()

    # ---- prefix plan ------------------------------------------------
    if ns.mode == "10m":
        with open(os.path.join(ns.root, "inputs",
                               "prefix-doc-ranges.json")) as f:
            pr = json.load(f)
        prefixes = [list(r["docs"]) for r in pr["prefixes"]]
        geometry = [{"docs": r.get("added_docs"),
                     "chunks": r.get("added_chunks"),
                     "tok_v1": r.get("added_tokens_tok_v1")}
                    for r in pr["prefixes"]]
        organize_per_prefix = False
    else:
        log(f"planning {ns.n_prefixes} prefixes (streaming chunk pass)…")
        t0 = time.perf_counter()
        prefixes, geometry = plan_prefixes_100m(
            docs_path, ns.n_prefixes, chunk_text)
        log(f"prefix plan: {len(prefixes)} prefixes, "
            f"{sum(g['chunks'] for g in geometry)} chunks, "
            f"{time.perf_counter() - t0:.1f}s")
        for i, g in enumerate(geometry):
            log(f"  p{i}: docs={g['docs']} chunks={g['chunks']} "
                f"tok_v1={g['tok_v1']}")
        organize_per_prefix = True
    with open(os.path.join(ns.out, "prefix-plan.json"), "w") as f:
        json.dump({"mode": ns.mode, "prefixes": prefixes,
                   "geometry": geometry}, f)

    # ---- store ------------------------------------------------------
    if ns.resume and not os.path.isdir(store_root):
        print("refusing: --resume but no store present", flush=True)
        return 2
    if os.path.isdir(store_root) and not ns.resume:
        print("refusing: store exists (use --resume or clear)",
              flush=True)
        return 2
    lease = (ns.lease_owner or
             f"b100m-{ns.mode}-{time.strftime('%Y%m%dT%H%M%SZ')}")
    tl = TLStore(store_root, create=not ns.resume, lease_owner=lease)
    sess = ProducerSession(profile)
    pins = {}
    t_build0 = time.perf_counter()
    try:
        prev_ids = set()
        for pi, ids in enumerate(prefixes):
            new_ids = [d for d in ids if d not in prev_ids]
            prev_ids.update(new_ids)
            want = set(new_ids)
            order = {d: i for i, d in enumerate(new_ids)}
            new_docs = [(d, t) for d, t, _o, _h in
                        gate.stream_docs_file(docs_path) if d in want]
            new_docs.sort(key=lambda x: order[x[0]])
            if len(new_docs) != len(new_ids):
                raise RuntimeError(
                    f"p{pi}: resolved {len(new_docs)}/{len(new_ids)} docs")
            geo = geometry[pi] if pi < len(geometry) else {}
            # -- ingest --
            ph = f"ingest-p{pi}"
            if not ck.has(ph):
                b0, pin0 = store_bytes(store_root), pin_triple(tl)
                c0 = cache_handle["stats"]()
                t0 = time.perf_counter()
                rep = ingest_docs(tl, new_docs, emb_texts,
                                  store_id=STORE_ID, place_xdoc=True,
                                  place_budget=None, profile=profile,
                                  keyed_state=True, session=sess)
                wall = time.perf_counter() - t0
                eng = assert_catalog_engaged(rep, ph, True)
                c1 = cache_handle["stats"]()
                ck.write({"phase": ph, "prefix": pi,
                          "n_docs": len(new_docs),
                          "geometry": geo, "wall_s": round(wall, 3),
                          "pin_before": pin0["triple"],
                          "pin_after": pin_triple(tl)["triple"],
                          "bytes_before": b0, "bytes_after": store_bytes(
                              store_root),
                          "cache": {k: c1[k] - c0[k] for k in c1},
                          "report": trim(rep)})
                pins[ph] = pin_triple(tl)["triple"]
                log(f"{ph}: {len(new_docs)} docs +{geo.get('chunks')} "
                    f"chunks in {wall:.1f}s "
                    f"({wall / max(len(new_docs), 1):.2f}s/doc) "
                    f"pin={pins[ph][:16]}… n_atoms={rep.get('n_atoms')} "
                    f"cat={eng['pops']} decisions={eng['decisions']} "
                    f"max_rows={eng['max_rows']}")
            else:
                pins[ph] = ck.done[ph]["pin_after"]
                log(f"{ph}: SKIP (checkpointed)")
            # -- bind (once, after the first commit) --
            if pi == 0:
                ph = "bind"
                if not ck.has(ph):
                    t0 = time.perf_counter()
                    brec = bind_candidate_store(
                        tl, profile=profile,
                        profile_id=profile["profile_id"],
                        profile_sha256=profile_sha,
                        compact_bounds=None)
                    wall = time.perf_counter() - t0
                    ck.write({"phase": ph,
                              "wall_s": round(wall, 3),
                              "pin_after": pin_triple(tl)["triple"],
                              "binding": brec.get("binding"),
                              "existing": brec.get("existing")})
                    pins[ph] = pin_triple(tl)["triple"]
                    log(f"{ph}: version="
                        f"{(brec.get('binding') or {}).get('version')} "
                        f"existing={brec.get('existing')} "
                        f"in {wall:.1f}s")
                else:
                    pins[ph] = ck.done[ph]["pin_after"]
                    log(f"{ph}: SKIP (checkpointed)")
            # -- drain --
            ph = f"drain-p{pi}"
            if not ck.has(ph):
                b0 = store_bytes(store_root)
                t0 = time.perf_counter()
                drep = _maint.drain_placement_backlog(
                    tl, store_id=STORE_ID, budget=ns.drain_budget,
                    profile=profile, keyed_state=True, session=sess)
                wall = time.perf_counter() - t0
                deng = assert_catalog_engaged(drep, ph, False)
                ck.write({"phase": ph, "prefix": pi,
                          "wall_s": round(wall, 3),
                          "pin_after": pin_triple(tl)["triple"],
                          "bytes_before": b0, "bytes_after": store_bytes(
                              store_root),
                          "report": trim(drep)})
                pins[ph] = pin_triple(tl)["triple"]
                log(f"{ph}: drained={len(drep.get('drained', []))} "
                    f"failed={len(drep.get('failed', {}))} "
                    f"in {wall:.1f}s "
                    f"cat_decisions={deng['decisions']}")
            else:
                pins[ph] = ck.done[ph]["pin_after"]
                log(f"{ph}: SKIP (checkpointed)")
            # -- organize (100m per-prefix) --
            if organize_per_prefix:
                ph = f"organize-p{pi}"
                if not ck.has(ph):
                    b0 = store_bytes(store_root)
                    t0 = time.perf_counter()
                    orep = _maint.organize_segments(
                        tl, doc_ids=new_ids, budget=None,
                        store_id=STORE_ID, profile=profile,
                        keyed_state=True, session=sess)
                    wall = time.perf_counter() - t0
                    oeng = assert_catalog_engaged(orep, ph, True)
                    ck.write({"phase": ph, "prefix": pi,
                              "wall_s": round(wall, 3),
                              "pin_after": pin_triple(tl)["triple"],
                              "bytes_before": b0,
                              "bytes_after": store_bytes(store_root),
                              "report": trim(orep)})
                    pins[ph] = pin_triple(tl)["triple"]
                    log(f"{ph}: organized={orep.get('organized')} "
                        f"failed={orep.get('failed')} "
                        f"in {wall:.1f}s "
                        f"cat={oeng['pops']} "
                        f"decisions={oeng['decisions']} "
                        f"max_rows={oeng['max_rows']}")
                else:
                    pins[ph] = ck.done[ph]["pin_after"]
                    log(f"{ph}: SKIP (checkpointed)")
            # -- archive (ONE explicit manifest per bulk prefix) --
            ph = f"archive-p{pi}"
            if not ck.has(ph):
                b0 = store_bytes(store_root)
                t0 = time.perf_counter()
                arec = export_manifest_archive(
                    tl, reason=f"bulk-prefix-p{pi}")
                wall = time.perf_counter() - t0
                ck.write({"phase": ph, "prefix": pi,
                          "wall_s": round(wall, 3),
                          "pin_after": pin_triple(tl)["triple"],
                          "bytes_before": b0,
                          "bytes_after": store_bytes(store_root),
                          "report": trim(arec)})
                pins[ph] = pin_triple(tl)["triple"]
                log(f"{ph}: {arec.get('manifest_bytes')} B "
                    f"docs={arec.get('docs')} in {wall:.1f}s")
            else:
                pins[ph] = ck.done[ph]["pin_after"]
                log(f"{ph}: SKIP (checkpointed)")
            # -- snapshot (100m per-prefix) --
            if ns.mode == "100m":
                ph = f"snap-p{pi}"
                if not ck.has(ph):
                    thin_snapshots(snap_dir, ns.min_free_gb, keep={0})
                    live = store_bytes(store_root)
                    t0 = time.perf_counter()
                    sp = os.path.join(snap_dir, f"pin-p{pi}")
                    sr = snapshot_store(store_root, sp)
                    wall = time.perf_counter() - t0
                    if not sr.get("ok"):
                        raise RuntimeError(
                            f"snapshot p{pi} failed: {sr}")
                    ck.write({"phase": ph, "prefix": pi,
                              "wall_s": round(wall, 3),
                              "pin": pin_triple(tl)["triple"],
                              "live_store": live, "snapshot": sr,
                              "path": sp})
                    pins[ph] = pin_triple(tl)["triple"]
                    log(f"{ph}: {sr.get('bytes')} B in {wall:.1f}s")
                else:
                    pins[ph] = ck.done[ph]["pin"]
                    log(f"{ph}: SKIP (checkpointed)")
            # -- first ETA from measured units --
            if pi == 0:
                log_eta(ck, geometry, ns.mode)
        # -- publication (10m only) --
        if ns.mode == "10m":
            ph = "publication"
            if not ck.has(ph):
                b0 = store_bytes(store_root)
                t0 = time.perf_counter()
                pub = run_publication_10m(tl, anchors_path, STORE_ID)
                wall = time.perf_counter() - t0
                expect_pub = (pub["n_relations"]
                              + pub["n_qual_signals"])
                if pub["committed_relations"] != expect_pub:
                    raise RuntimeError(
                        f"publication committed "
                        f"{pub['committed_relations']} != "
                        f"{expect_pub} relations "
                        f"({pub['n_relations']} relations + "
                        f"{pub['n_qual_signals']} qual signals)")
                ck.write({"phase": ph, "wall_s": round(wall, 3),
                          "pin_after": pin_triple(tl)["triple"],
                          "bytes_before": b0,
                          "bytes_after": store_bytes(store_root),
                          "report": pub})
                pins[ph] = pin_triple(tl)["triple"]
                log(f"{ph}: rels={pub['n_relations']} "
                    f"sigs={pub['n_qual_signals']} in {wall:.1f}s")
            else:
                pins[ph] = ck.done[ph]["pin_after"]
                log(f"{ph}: SKIP (checkpointed)")
            # -- organize once (10m C1 shape) --
            ph = "organize-final"
            if not ck.has(ph):
                b0 = store_bytes(store_root)
                t0 = time.perf_counter()
                orep = _maint.organize_segments(
                    tl, doc_ids=None, budget=None, store_id=STORE_ID,
                    profile=profile, keyed_state=True, session=sess)
                wall = time.perf_counter() - t0
                feng = assert_catalog_engaged(orep, ph, True)
                ck.write({"phase": ph, "wall_s": round(wall, 3),
                          "pin_after": pin_triple(tl)["triple"],
                          "bytes_before": b0,
                          "bytes_after": store_bytes(store_root),
                          "report": trim(orep)})
                pins[ph] = pin_triple(tl)["triple"]
                log(f"{ph}: organized={orep.get('organized')} "
                    f"in {wall:.1f}s "
                    f"cat={feng['pops']} "
                    f"decisions={feng['decisions']} "
                    f"max_rows={feng['max_rows']}")
            else:
                pins[ph] = ck.done[ph]["pin_after"]
                log(f"{ph}: SKIP (checkpointed)")
            # -- archive-final (10m compatibility boundary) --
            ph = "archive-final"
            if not ck.has(ph):
                b0 = store_bytes(store_root)
                t0 = time.perf_counter()
                arec = export_manifest_archive(
                    tl, reason="organize-final-boundary")
                wall = time.perf_counter() - t0
                ck.write({"phase": ph, "wall_s": round(wall, 3),
                          "pin_after": pin_triple(tl)["triple"],
                          "bytes_before": b0,
                          "bytes_after": store_bytes(store_root),
                          "report": trim(arec)})
                pins[ph] = pin_triple(tl)["triple"]
                log(f"{ph}: {arec.get('manifest_bytes')} B "
                    f"docs={arec.get('docs')} in {wall:.1f}s")
            else:
                pins[ph] = ck.done[ph]["pin_after"]
                log(f"{ph}: SKIP (checkpointed)")
        # -- final snapshot + open proof --
        ph = "snap-final"
        if not ck.has(ph):
            live = store_bytes(store_root)
            t0 = time.perf_counter()
            sp = os.path.join(snap_dir, "pin-final")
            sr = snapshot_store(store_root, sp)
            wall = time.perf_counter() - t0
            if not sr.get("ok"):
                raise RuntimeError(f"final snapshot failed: {sr}")
            final_pin = pin_triple(tl)["triple"]
            prove_snapshot_open(TLStore, sp, final_pin)
            ck.write({"phase": ph, "wall_s": round(wall, 3),
                      "pin": final_pin, "live_store": live,
                      "snapshot": sr, "path": sp,
                      "open_proof": True})
            pins[ph] = final_pin
            log(f"{ph}: {sr.get('bytes')} B open-proved pin="
                f"{final_pin[:16]}…")
        else:
            pins[ph] = ck.done[ph]["pin"]
            log(f"{ph}: SKIP (checkpointed)")
    except Exception as e:  # noqa: BLE001 - preserved, not retried
        with open(fail_path, "w") as f:
            json.dump({"mode": ns.mode, "utc": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-6000:],
                "completed_phases": sorted(ck.done.keys()),
                "resume_hint": "inspect, fix cause, rerun with --resume"},
                f, indent=1)
        log(f"BUILD FAILED: {type(e).__name__}: {e} "
            f"(preserved in {fail_path}; no retry)")
        raise
    finally:
        try:
            tl.close()
        except Exception:  # noqa: BLE001 - close-best-effort
            pass
        try:
            cache_handle["close"]()
        except Exception:  # noqa: BLE001 - close-best-effort
            pass
        ck.close()
    cache1 = cache_handle["stats"]()
    loaded = {}
    for name, mod in sorted(sys.modules.items()):
        path = getattr(mod, "__file__", None)
        if path and os.path.abspath(path).startswith(
                os.path.abspath(ns.root)):
            loaded[name] = os.path.relpath(path, ns.root)
    cat_tot = catalog_totals(ck.done)
    if cat_tot["rejected"] or cat_tot["over_budget_any"]:
        with open(fail_path, "w") as f:
            json.dump({"mode": ns.mode, "utc": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "error": "catalog gate violated in checkpointed reports",
                "catalog": cat_tot}, f, indent=1)
        raise RuntimeError(
            f"refusing receipt: rejected={cat_tot['rejected']} "
            f"over_budget_any={cat_tot['over_budget_any']}")
    bind_rec = ck.done.get("bind", {})
    archives = [
        {"phase": ph, "wall_s": rec.get("wall_s"),
         "manifest_bytes": (rec.get("report") or {}).get(
             "manifest_bytes"),
         "docs": (rec.get("report") or {}).get("docs")}
        for ph, rec in sorted(ck.done.items())
        if ph.startswith("archive-")]
    receipt = {
        "mode": ns.mode, "verdict": "ok",
        "arm": "C2",
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "build_wall_s": round(time.perf_counter() - t_build0, 3),
        "store_id": STORE_ID, "lease_owner": lease,
        "keyed_state": True,
        "candidate_binding": (bind_rec.get("binding")
                              if isinstance(bind_rec, dict) else None),
        "archives": archives,
        "archive_wall_s_total": round(sum(
            a["wall_s"] for a in archives
            if isinstance(a.get("wall_s"), (int, float))), 3),
        "profile": {"profile_id": profile["profile_id"],
                    "sha256": profile_sha,
                    "R_cat": profile_rcat,
                    "calibration_manifest_id":
                        profile["calibration_manifest_id"],
                    "session_bound": True},
        "catalog": cat_tot,
        "place_xdoc": True, "place_budget": None,
        "drain_budget": ns.drain_budget,
        "docs_sha256": got_docs,
        "cache_stats_total": {k: cache1[k] - cache0[k]
                              for k in cache1},
        "final_store": store_bytes(store_root),
        "final_pin": pins.get("snap-final"),
        "pins": pins,
        "loaded_modules": loaded,
    }
    with open(os.path.join(ns.out, "BUILD-RECEIPT.json"), "w") as f:
        json.dump(receipt, f, indent=1, sort_keys=True)
    with open(os.path.join(ns.out, "pins.json"), "w") as f:
        json.dump(pins, f, indent=1, sort_keys=True)
    log(f"BUILD OK mode={ns.mode} wall={receipt['build_wall_s']:.1f}s "
        f"final_pin={receipt['final_pin'][:16]}… "
        f"store={receipt['final_store']}")
    return 0


def thin_snapshots(snap_dir, min_free_gb, keep):
    """Delete oldest mid-growth snapshots when disk runs low.

    Never deletes pin-final (created last, after all thinning) or
    prefixes in `keep`. Records nothing itself; the caller logs.
    """
    free_gb = shutil.disk_usage(snap_dir).free / (1 << 30)
    if free_gb >= min_free_gb:
        return
    cands = []
    for name in sorted(os.listdir(snap_dir)):
        if not name.startswith("pin-p"):
            continue
        try:
            ix = int(name[len("pin-p"):])
        except ValueError:
            continue
        if ix in keep:
            continue
        cands.append((ix, os.path.join(snap_dir, name)))
    for ix, path in sorted(cands)[:-1] if len(cands) > 1 else []:
        # keep the latest mid-growth snapshot always
        shutil.rmtree(path, ignore_errors=True)
        log(f"thinned snapshot pin-p{ix} (free {free_gb:.1f}GB "
            f"< {min_free_gb}GB)")
        free_gb = shutil.disk_usage(snap_dir).free / (1 << 30)
        if free_gb >= min_free_gb:
            break


def log_eta(ck, geometry, mode):
    try:
        ing = ck.done.get("ingest-p0", {})
        wall = ing.get("wall_s", 0)
        ch = (ing.get("geometry") or {}).get("chunks") or 1
        tot = sum(g.get("chunks", 0) for g in geometry)
        per_ch = wall / ch
        log(f"ETA(units): ingest {per_ch * 1000:.2f}ms/chunk; "
            f"all-prefix ingest forecast ~{per_ch * tot / 3600:.2f}h "
            f"(linear; organize/publication excluded)")
        if mode == "100m":
            org = ck.done.get("organize-p0", {})
            if org.get("wall_s"):
                log(f"ETA(units): organize-p0 {org['wall_s']:.1f}s for "
                    f"{ch} chunks (scaling unknown; re-fit per prefix)")
    except Exception as e:  # noqa: BLE001 - ETA-best-effort
        log(f"ETA skipped: {e}")


if __name__ == "__main__":
    sys.exit(main())

