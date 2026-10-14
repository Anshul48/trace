"""Owning doc retirement (v3 repair): declared effect + approval-gated.

A retirement is ONE ACCEPT_ATOMS op per doc carrying a committed meta
artifact {"retirement": {"doc", "reason"}, "atom_scheme"}. The payload
DECLARES its effect via `retires` (the retired doc id), so the owning
approval.classify treats it as consequential; every retiring op carries
a per-operation stage-2 approval_ref bound to payload (diff_hash), pin
(pinned_generation), policy version, and scope. The owning candidate
core is untouched: the existing gate enforces the binding
(APPROVAL_MISSING / REF_MALFORMED / STALE_ASSESSMENT / POLICY_STALE on
violation). Missing or malformed approvals fail closed in retire_docs
(ValueError before any commit; no eligibility change).

Committed truth is authoritative: serving (NarrowIndex build),
projections (tlsys.proj), and export (tlsys.export) consume the markers
from their ordinary scans. The manifest "_retired" list is advisory
(idempotency + crash-window bookkeeping); reconcile_manifest rebuilds
it from committed truth, so a commit-then-crash retry converges.

Retirement is doc-level and permanent (latest-wins; no un-retire op in
this minimum path). Retired docs keep their committed atoms (evidence
is never deleted); readers exclude/omit them with disclosed identities.
Pre-repair committed markers (unapproved, no `retires` in payload) stay
valid history: readers consume the meta artifact, which is unchanged.
"""

import json
import os

from tlsys.identity import ATOM_SCHEME
from tlsys.ingest import (_load_manifest, _save_manifest,
                          MANIFEST_NAME as ING_MANIFEST_NAME)
from tlsys.store_if import sha256, uuidv7

KIND = "ACCEPT_ATOMS"
RETIRED_KEY = "_retired"
APPROVAL_STAGE = 2


def validate_approval(approval, doc_id):
    """Normalized approval leg for one retiring op, or ValueError.

    Accepted legs (existing core stage-2 shapes): {"type": "user",
    "approval_id": <nonempty str>} or {"type": "grant", "grant_id":
    <nonempty str>}. The core gate re-validates at commit (grant
    existence/scope/lifetime, user approval_id presence); this
    pre-check fails fast before any commit. Only the known keys are
    kept, so callers cannot smuggle extra fields into the committed
    approval_ref.
    """
    if not isinstance(approval, dict):
        raise ValueError(
            f"retire: doc {doc_id!r} approval must be a dict, got "
            f"{type(approval).__name__}")
    atype = approval.get("type")
    if atype == "user":
        aid = approval.get("approval_id")
        if not isinstance(aid, str) or not aid:
            raise ValueError(
                f"retire: doc {doc_id!r} user approval needs a "
                "nonempty approval_id")
        return {"type": "user", "approval_id": aid}
    if atype == "grant":
        gid = approval.get("grant_id")
        if not isinstance(gid, str) or not gid:
            raise ValueError(
                f"retire: doc {doc_id!r} grant approval needs a "
                "nonempty grant_id")
        return {"type": "grant", "grant_id": gid}
    raise ValueError(
        f"retire: doc {doc_id!r} approval type {atype!r} unknown "
        "(want 'user' or 'grant')")


def build_approval_ref(tlstore, payload, approval, doc_id,
                       pinned=None, scope=KIND):
    """Per-operation stage-2 approval_ref bound to payload+pin+scope.

    pinned defaults to a fresh tlstore.pin() (call immediately before
    the op's commit: TOCTOU scope is the kind, so any sibling commit
    between pin and gate reads as a material change). diff_hash covers
    the exact payload bytes per the core gate's serialization
    (json.dumps sort_keys). Raises ValueError on a malformed leg.
    """
    leg = validate_approval(approval, doc_id)
    if pinned is None:
        pinned = tlstore.pin()
    birth, epoch, mx, _triple = pinned
    policy_version = tlstore.current_policy_version()
    diff_hash = sha256(json.dumps(payload, sort_keys=True).encode())
    return {"stage": APPROVAL_STAGE,
            "policy_version": policy_version,
            "pinned_generation": [birth, epoch, mx],
            "assessment": {"diff_hash": diff_hash},
            "approval": leg,
            "scope": scope}


def retirement_op(doc_id, reason, store_id, prepare_artifact,
                  approval_ref=None):
    """One ACCEPT_ATOMS op retiring doc_id (consequential).

    The payload declares `retires` (the retired doc id). An op with
    approval_ref None is unsubmittable: the core gate refuses it with
    APPROVAL_MISSING. Attach a ref from build_approval_ref (bound to
    this op's exact payload) before commit_batch.
    """
    meta = {"retirement": {"doc": doc_id, "reason": str(reason)},
            "atom_scheme": ATOM_SCHEME}
    mart = prepare_artifact(json.dumps(meta, sort_keys=True).encode(),
                            store_id)
    return {"op_id": uuidv7(),
            "kind": KIND,
            "payload": {"retirement": doc_id,
                        "meta_artifact": mart["artifact_id"],
                        "retires": doc_id},
            "disclosure": {"leg": "retire", "doc_id": doc_id},
            "approval_ref": approval_ref,
            "artifacts": (mart,)}


def read_retirements(tlstore, pinned, min_seq=0):
    """{doc_id: {"seq", "op_id", "reason"}} from COMMITTED metas.

    Latest-wins per doc within the scanned window (same call shape as
    place.read_xholons: read_commits_all + pub_refs + artifact_rows).
    Parity oracle for Projections.retired_view().
    """
    birth, epoch, mx, _triple = pinned
    rows = tlstore.read_commits_all(birth, epoch, mx, kind=KIND,
                                    min_seq=min_seq)
    seqs = [r[0] for r in rows]
    op_of_seq = {r[0]: r[1] for r in rows}
    refs = tlstore.pub_refs(seqs)
    arows = tlstore.artifact_rows(
        [a for seq in seqs for a in refs.get(seq, [])])
    out = {}
    for seq in seqs:
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id,
                                         expect_digest=arow[4])
            try:
                meta = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            ret = meta.get("retirement")
            if not isinstance(ret, dict):
                continue
            doc = ret.get("doc")
            if not isinstance(doc, str):
                continue
            if meta.get("atom_scheme") != ATOM_SCHEME:
                raise ValueError(
                    f"op seq {seq}: retirement meta scheme "
                    f"{meta.get('atom_scheme')!r} != {ATOM_SCHEME!r}")
            out[doc] = {"seq": seq, "op_id": op_of_seq[seq],
                        "reason": str(ret.get("reason", ""))}
    return out


def retire_docs(tlstore, doc_ids, reason="", store_id="tl-sys-docs",
                approvals=None, keyed_state=False,
                archive_manifest=False):
    """Retire acknowledged docs; idempotent retry, costed report.

    Already-retired docs (per COMMITTED truth, not the manifest) are
    reported under already_retired with no new commit (no approval
    needed when nothing is committed); unknown (unacknowledged) doc
    ids raise ValueError. Each newly retired doc needs one entry in
    `approvals` ({doc_id: {"type": "user", "approval_id": ...} or
    {"type": "grant", "grant_id": ...}}); a missing or malformed entry
    raises ValueError BEFORE any commit (fail closed: no commit, no
    eligibility change). Each op is committed in its own single-op
    batch with a fresh pin (TOCTOU scope is the kind, so a shared
    batch would self-conflict; still within the 10-op cap). A core
    refusal surfaces as RuntimeError with the gate code. Returns
    {"retired", "already_retired", "ops", "seqs", "n_commits",
    "catchup"}.

    keyed_state (C2 Closure P §5.2): additive keyed backend (see
    tlsys.ingest.ingest_docs). archive_manifest (P-2, Sec 5.7):
    explicit archive/compatibility export on this keyed call;
    ordinary calls write no JSON (stale marker instead). Requires
    keyed_state.
    """
    if archive_manifest and not keyed_state:
        raise ValueError("retire: archive_manifest needs "
                         "keyed_state=True (legacy cadence is pinned)")
    if keyed_state:
        return _retire_docs_keyed(tlstore, doc_ids, reason=reason,
                                  store_id=store_id,
                                  approvals=approvals,
                                  archive_manifest=archive_manifest)
    from tlsys.prodstate import refuse_legacy_writer as _refuse
    _refuse(tlstore.store)
    from tlsys.store_if import prepare_artifact as _prep
    from tlsys.proj import Projections as _Projections
    manifest, manifest_path = _load_manifest(tlstore.store)
    for d in doc_ids:
        if d not in manifest or not isinstance(manifest[d], dict):
            raise ValueError(
                f"retire: doc {d!r} not acknowledged in manifest")
    proj = _Projections.cached(tlstore)
    catchup = proj.update(tlstore)
    committed = proj.retired_view()
    targets = [d for d in doc_ids if d not in committed]
    already = [d for d in doc_ids if d in committed]
    legs = {}
    if targets:
        if not isinstance(approvals, dict):
            raise ValueError(
                "retire: approvals dict required for "
                f"{len(targets)} newly retiring doc(s)")
        for d in targets:
            if d not in approvals:
                raise ValueError(
                    f"retire: doc {d!r} missing approval "
                    "(fail closed: no commit)")
            legs[d] = validate_approval(approvals[d], d)
    store = tlstore.store
    prep = lambda bb, sid: _prep(store, bb, sid)  # noqa: E731
    ops = {}
    seqs = {}
    n_commits = 0
    for d in targets:
        op = retirement_op(d, reason, store_id, prep)
        op["approval_ref"] = build_approval_ref(
            tlstore, op["payload"], legs[d], d)
        results, _info = tlstore.commit_batch([op])
        r = results[0]
        if r.get("status") != "committed":
            raise RuntimeError(
                f"retire op {r.get('op_id')} "
                f"{r.get('status')}:{r.get('code')}")
        ops[d] = r["op_id"]
        n_commits += 1
    if targets:
        # Resolve issuing seqs + fold the markers into the warm
        # projection (bounded: only this call's commits).
        proj.update(tlstore)
        view = proj.retired_view()
        for d in targets:
            seqs[d] = view[d]["seq"]
        proj.save(tlstore)
        pending = manifest.setdefault(RETIRED_KEY, [])
        for d in targets:
            if d not in pending:
                pending.append(d)
        _save_manifest(manifest_path, manifest)
    return {"retired": list(targets), "already_retired": list(already),
            "ops": ops, "seqs": seqs, "n_commits": n_commits,
            "catchup": catchup}


def _retire_docs_keyed(tlstore, doc_ids, reason="", store_id="tl-sys-docs",
                       approvals=None, archive_manifest=False):
    """Keyed-backend retire (Closure P §5.2; see retire_docs).

    Keyed ack checks (no whole-manifest load), per-doc single-op
    commits, advisory retired marks in one txn each. P-2:
    explicit-archive-only export (no compaction hook: retire rides
    the foreground correction path). Same refusal/commit semantics
    as legacy.
    """
    from tlsys.prodstate import (ProducerState, consume_suffix,
                                 close_out_keyed_call)
    store = tlstore.store
    manifest = {}
    mpath = os.path.join(store.root, ING_MANIFEST_NAME)
    if os.path.isfile(mpath):
        with open(mpath) as f:
            manifest = json.load(f)
    state, migrec = ProducerState.create_or_migrate(tlstore, manifest)
    keyed_rec = {"migrated": migrec, "suffix": None}
    try:
        sufrec = consume_suffix(tlstore, state)
        keyed_rec["suffix"] = sufrec
        for d in doc_ids:
            if state.get_doc(d) is None:
                raise ValueError(
                    f"retire: doc {d!r} not acknowledged in manifest")
        from tlsys.proj import Projections as _Projections
        proj = _Projections.cached(tlstore)
        catchup = proj.update(tlstore)
        committed = proj.retired_view()
        targets = [d for d in doc_ids if d not in committed]
        already = [d for d in doc_ids if d in committed]
        legs = {}
        if targets:
            if not isinstance(approvals, dict):
                raise ValueError(
                    "retire: approvals dict required for "
                    f"{len(targets)} newly retiring doc(s)")
            for d in targets:
                if d not in approvals:
                    raise ValueError(
                        f"retire: doc {d!r} missing approval "
                        "(fail closed: no commit)")
                legs[d] = validate_approval(approvals[d], d)
        from tlsys.store_if import prepare_artifact as _prep
        prep = lambda bb, sid: _prep(store, bb, sid)  # noqa: E731
        ops = {}
        seqs = {}
        n_commits = 0
        for d in targets:
            op = retirement_op(d, reason, store_id, prep)
            op["approval_ref"] = build_approval_ref(
                tlstore, op["payload"], legs[d], d)
            results, _info = tlstore.commit_batch([op])
            r = results[0]
            if r.get("status") != "committed":
                raise RuntimeError(
                    f"retire op {r.get('op_id')} "
                    f"{r.get('status')}:{r.get('code')}")
            ops[d] = r["op_id"]
            n_commits += 1
            _b, _e, _mx, _triple = tlstore.pin()
            state.record_flush([], {}, frontier=(_b, _e, _mx, _triple),
                               retired=[d])
        if targets:
            proj.update(tlstore)
            view = proj.retired_view()
            for d in targets:
                seqs[d] = view[d]["seq"]
            proj.save(tlstore)
        _man, arch_rec = close_out_keyed_call(
            state, mpath, archive_manifest=archive_manifest,
            reason="retire")
        keyed_rec["archive"] = arch_rec
        keyed_rec["candidate_version"] = arch_rec[
            "candidate_version"]
    finally:
        state.close()
    out = {"retired": list(targets), "already_retired": list(already),
           "ops": ops, "seqs": seqs, "n_commits": n_commits,
           "catchup": catchup, "keyed": keyed_rec}
    return out
