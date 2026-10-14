"""Deferred placement drain (S-03 section 1b maintenance).

Ingest places synchronously within its foreground budget
(PLACE_FOREGROUND_BUDGET); overflow docs land in the manifest backlog
(manifest["_pending_placement"]) — acknowledged, committed, and
retrievable through the S-01 per-doc paths while unplaced. This module
drains that backlog on EXPLICIT caller invocation. There is no
autonomous worker, no new op kind, and no in-place mutation: drain
commits versioned xdoc metas through the same ingest-path authority
(ACCEPT_ATOMS, non-consequential) as synchronous placement, so D-23
(descriptor refresh struck, orphan collect deferred) is preserved.

Refresh rule (incremental, additive): every published xdoc version
carries members + descriptor computed together in one op via
tlsys.place.join_descriptor (shared with the sync path, so both paths
publish identical math). Readers resolve latest-wins. Pending docs are
absent from membership — never stale members — so partial placement
cannot publish incompatible membership/descriptor state.

Retirement (lane-2 closure): tlsys.lifecycle commits doc-level
retirement markers; drain/organize consume them from the keyed
projections and skip retired docs (reported as retired_skipped).
Pending docs stay query-eligible throughout; retired docs are
excluded at serving/export with disclosed identities.

Caller-serialized: ingest and drain both read/write the manifest;
callers must not run them concurrently on one store (same lease-owner
pattern as ingest).
"""

from tlsys.ingest import _load_manifest, _save_manifest
from tlsys.store_if import format_commit_failure
from tlsys.place import (MAX_XHOLON_MEMBERS, MAX_XMEMBERSHIPS, T_PLACE,
                         decide, decide_with_navigator,
                         join_descriptor, member_centroid,
                         xholon_op)

# Codex gate C (C2 100M recovery): fail-fast on store-wide capacity
# exhaustion. The 100M p0 leg burned one 5.0 s reserve deadline per
# doc for 9,444 consecutive REJECT_CAPACITY failures (~13 h) because
# the organize loop records failed[doc] and continues. Under the
# single-writer monotonic ledger, consecutive identical capacity
# rejections can only be the store-wide wall (no drain path exists,
# so no later doc can succeed): after TRIP consecutive capacity
# failures the loop raises with the cause preserved instead of
# burning another deadline. A success or a non-capacity failure
# resets the streak. Wired into the keyed path (the C2 build path);
# the legacy path is refused on new state (refuse_legacy_writer)
# and keeps its record-and-continue contract.
ORGANIZE_WALL_TRIP_CONSECUTIVE = 3


def is_capacity_failure(err):
    """True when a per-doc organize error names admission-capacity rejection."""
    return isinstance(err, str) and "REJECT_CAPACITY" in err


class CapacityTripwire:
    """Consecutive-capacity-failure tripwire for the organize loop.

    note(doc_id, err) records one doc outcome (err None on success);
    on ORGANIZE_WALL_TRIP_CONSECUTIVE consecutive capacity failures
    it raises RuntimeError naming the wall, the streak docs, and the
    last cause, so the phase fails fast with evidence instead of
    burning one reserve deadline per remaining doc.
    """

    def __init__(self, limit=ORGANIZE_WALL_TRIP_CONSECUTIVE):
        self.limit = limit
        self.streak = 0
        self._streak_ids = []

    def note(self, doc_id, err):
        if is_capacity_failure(err):
            self.streak += 1
            self._streak_ids.append(doc_id)
            if self.streak >= self.limit:
                raise RuntimeError(
                    "organize: store-wide capacity wall: "
                    f"{self.streak} consecutive REJECT_CAPACITY doc "
                    f"failures (docs {self._streak_ids[-self.limit:]}; "
                    f"last: {err}); failing the phase fast instead of "
                    "burning one reserve deadline per remaining doc")
        else:
            self.streak = 0
            self._streak_ids = []


def _doc_vecs(tlstore, doc_id):
    """[(aid, vec)] for one doc from COMMITTED atom metas (seq order).

    No embedder needed: drain reuses stored descriptors. Fails closed
    (RuntimeError) when the doc has no committed atoms.
    """
    birth, epoch, mx, _triple = tlstore.pin()
    # R8-B (R7-A proposal C adoption): unbounded read via min_seq
    # frontiers (read_commits_all) + single-connection batched
    # artifact rows (same call shape as
    # ingest._committed_doc_state). Identical results to the pre-R8-B
    # loop at every scale the old 1M window covered.
    rows = tlstore.read_commits_all(birth, epoch, mx,
                                    kind="ACCEPT_ATOMS")
    seqs = [r[0] for r in rows]
    refs = tlstore.pub_refs(seqs)
    arows = tlstore.artifact_rows(
        [a for seq in seqs for a in refs.get(seq, [])])
    import json as _json
    out = []
    for seq in seqs:
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id,
                                         expect_digest=arow[4])
            try:
                meta = _json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            if meta.get("doc_id") == doc_id and "atom" in meta \
                    and "descriptor" in meta:
                out.append((meta["atom"],
                            [float(x) for x in meta["descriptor"]]))
    if not out:
        raise RuntimeError(
            f"drain: doc {doc_id!r} has no committed atoms; "
            "stays pending (never half-placed)")
    return out


def drain_placement_backlog(tlstore, store_id="tl-sys-docs", budget=None,
                            t_place=None, doc_ids=None,
                            navigator=None, projections=None,
                            profile=None, counters=None,
                            keyed_state=False, session=None,
                            archive_manifest=False):
    """Place up to `budget` backlogged docs; return a costed report.

    budget: max placement decisions this call (None = all pending).
    doc_ids: explicit docs to place (must be acknowledged in the
    manifest); None = the manifest backlog in order. Each doc commits
    its xdoc ops in one batch; on success it leaves the backlog and
    its manifest xdoc list grows. A doc whose atoms are missing fails
    closed and stays pending (reported, not raised past the batch).
    navigator: M1-C opt-in tlsys.place.CandidateNavigator (default
    None = exact decide() per doc, behavior unchanged). When given,
    each placement discovers through the navigator with exact
    local rescore (same threshold/cap/full-holon policy; the exact
    post-decide cap check below still applies) and the report
    gains per-doc "nav" work entries plus "nav_totals".

    Reads (M2-C): doc atoms and the xdoc view come from keyed
    projections (tlsys.proj) consumed once per call through a
    frontier -- a cold call scans once, a warm call decodes only
    new commits, and no per-doc step re-decodes unrelated state.
    projections: caller-owned Projections (the caller owns save());
    None loads (or cold builds) the store checkpoint and saves it.

    Returns {"drained": [...], "already_placed": [...],
    "failed": {doc: reason}, "remaining": [...],
    "n_xholon_ops": n, "n_commits": c, "catchup": {...},
    "debt": {...}, "churn": {...}, "retained": {...}}.
    n_commits bounds the maintenance write cost (one batch per doc).
    Re-draining a placed doc is a commit-free no-op (already_placed).

    profile/counters (C2 Lane O): profile is a Lane G profile dict
    (None = the exact C1 reference path, bit-identical to before).
    When profile["flags"]["organization_catalog_routing"] is true,
    xdoc decisions route through a row-budgeted exact catalog (D2
    parity), the per-doc placed-aids union scan becomes a keyed
    AtomIndex lookup, and the report gains a "catalog" section.
    counters (Lane G Counters, optional) receives the per-call
    catalog rows/bytes/scoring evals. Catalog routing does not
    compose with the navigator leg: passing both fails closed.

    keyed_state (C2 Closure P §5.2): additive keyed backend (see
    tlsys.ingest.ingest_docs): ordered windowed backlog reads, no
    whole-manifest load/save, bounded remaining + exact counts,
    R_cat pre-execution gate on catalog decisions. session:
    optional ProducerSession (else ephemeral). archive_manifest
    (P-2, Sec 5.7): explicit archive/compatibility export on this
    keyed call; ordinary calls write no JSON (stale marker instead).
    Requires keyed_state.
    """
    if archive_manifest and not keyed_state:
        raise ValueError("drain: archive_manifest needs "
                         "keyed_state=True (legacy cadence is pinned)")
    if keyed_state:
        return _drain_placement_backlog_keyed(
            tlstore, store_id=store_id, budget=budget,
            t_place=t_place, doc_ids=doc_ids, navigator=navigator,
            projections=projections, profile=profile,
            counters=counters, session=session,
            archive_manifest=archive_manifest)
    from tlsys.prodstate import refuse_legacy_writer as _refuse
    _refuse(tlstore.store)
    from tlsys.store_if import prepare_artifact as _prep
    from tlsys.proj import Projections as _Projections
    from tlsys.place import decide_catalog as _decide_catalog
    from tlsys.catalog import (AtomIndex as _AtomIndex,
                               Catalog as _Catalog,
                               catalog_row_budget as _rcat,
                               catalog_routing_enabled as _flag_on)
    manifest, manifest_path = _load_manifest(tlstore.store)
    pending = list(manifest.get("_pending_placement", []))
    if doc_ids is None:
        # Copy: the loop removes from `pending` as docs drain.
        targets = list(pending) if budget is None else pending[:budget]
    else:
        for d in doc_ids:
            if d not in manifest:
                raise ValueError(
                    f"drain: doc {d!r} not acknowledged in manifest")
            if d.startswith("xdoc-"):
                raise ValueError(
                    f"drain: doc {d!r}: 'xdoc-' prefix reserved")
        targets = list(doc_ids) if budget is None else list(doc_ids)[:budget]
    t = T_PLACE if t_place is None else t_place
    store = tlstore.store
    prep = lambda bb, sid: _prep(store, bb, sid)  # noqa: E731
    # Keyed projections, consumed once per call (M2-C). The xdoc
    # overlay starts as a copy of the consumed view and carries
    # versions committed earlier in this call (callers are
    # serialized, so it equals the per-doc fresh reads).
    own_proj = projections is None
    proj = _Projections.cached(tlstore) if own_proj else projections
    catchup = proj.update(tlstore)
    retired = set(proj.retired_view())
    retired_skipped = [d for d in targets if d in retired]
    targets = [d for d in targets if d not in retired]
    xh = {k: {"members": list(v["members"]),
              "descriptor": list(v["descriptor"]),
              "seq": v.get("seq")}
          for k, v in proj.xholons_view().items()}
    # C2 Lane O working state (flag-gated; flag-off leaves every line
    # below on the reference path, bit-identical to before).
    use_catalog = _flag_on(profile)
    if use_catalog and navigator is not None:
        raise ValueError(
            "drain: catalog routing does not compose with "
            "the navigator leg")
    xcat = atom_idx = None
    drain_dim = None
    if use_catalog:
        for _v in xh.values():
            drain_dim = len(_v["descriptor"])
            break
        if drain_dim is not None:
            xcat = _Catalog("xholon", drain_dim, _rcat(profile))
            xcat.build(
                (hid, e["descriptor"], len(e["members"]))
                for hid, e in xh.items())
        atom_idx = _AtomIndex().build(xh)
    catch = {"decisions": 0, "max_rows": 0, "ties": [],
             "over_budget": False, "max_exec_rows": 0, "_exec_seen": 0}
    backlog_before = len(pending)
    drained, failed = [], {}
    already = []
    nav_entries = []
    churn = {"xdoc_superseded": 0, "xdoc_minted": 0}
    n_ops = n_commits = 0
    for doc_id in targets:
        try:
            pairs = proj.doc_vecs(doc_id)
        except RuntimeError:
            failed[doc_id] = (
                f"drain: doc {doc_id!r} has no committed atoms; "
                "stays pending (never half-placed)")
            continue
        aids = [a for a, _v in pairs]
        vecs = [v for _a, v in pairs]
        centroid = member_centroid(vecs)
        if use_catalog:
            if xcat is None and vecs:
                drain_dim = len(vecs[0])
                xcat = _Catalog("xholon", drain_dim,
                                _rcat(profile))
                xcat.build(
                    (hid, e["descriptor"], len(e["members"]))
                    for hid, e in xh.items())
            placed = all(a in atom_idx for a in aids)
        else:
            placed_aids = set()
            for _h, _v in xh.items():
                placed_aids.update(_v["members"])
            placed = all(a in placed_aids for a in aids)
        if placed:
            # Idempotent re-drain: atoms already members somewhere.
            # No new version (a singleton re-mint would be noise).
            if doc_id in pending:
                pending.remove(doc_id)
            manifest["_pending_placement"] = pending
            _save_manifest(manifest_path, manifest)
            already.append(doc_id)
            continue
        if use_catalog:
            dstats = {}
            joins = _decide_catalog(centroid, xcat, t_place=t,
                                    stats=dstats,
                                    counters=counters)
            catch["decisions"] += 1
            rows = dstats.get("catalog_rows", 0)
            if rows > catch["max_rows"]:
                catch["max_rows"] = rows
            # O-7: per-decision executed rows via totals delta (the
            # xcat is call-local and only this decide call advances
            # it, so the delta is exactly this decision's executed
            # work; place.py stats stay in eligible units).
            exec_now = xcat.total_executed_rows
            exec_rows = exec_now - catch["_exec_seen"]
            catch["_exec_seen"] = exec_now
            if exec_rows > catch["max_exec_rows"]:
                catch["max_exec_rows"] = exec_rows
            if dstats.get("catalog_ties") \
                    and len(catch["ties"]) < 16:
                catch["ties"].append(dstats["catalog_ties"])
            if dstats.get("catalog_budget_exceeded"):
                catch["over_budget"] = True
        elif navigator is None:
            joins = decide(centroid, xh, t_place=t)
        else:
            nstats = {}
            joins = decide_with_navigator(
                centroid, xh, navigator, t_place=t,
                stats=nstats, path="deferred-place")
            nav_entries.append({
                "doc": doc_id, "joins": list(joins),
                "discovered": nstats["nav_discovered"],
                "visited": nstats["visited"],
                "rescored": nstats["scored"],
                "rounds": nstats["nav_rounds"],
                "replenished": nstats["nav_replenished"],
                "changed_ids": nstats["nav_changed_ids"]})
        ops = []
        versions = []  # (hid, members, desc) in op order
        applied = []
        for hid in joins:
            old = xh[hid]
            ixs = [ix for ix, a in enumerate(aids)
                   if a not in old["members"]]
            if not ixs:
                continue
            if len(old["members"]) + len(ixs) > MAX_XHOLON_MEMBERS:
                continue  # exact cap (same rule as the sync path)
            members = old["members"] + [aids[ix] for ix in ixs]
            desc = join_descriptor(old["descriptor"],
                                   len(old["members"]),
                                   [vecs[ix] for ix in ixs])
            ops.append(xholon_op(hid, members, desc, store_id, prep))
            versions.append((hid, members, desc))
            applied.append(hid)
        if not applied:
            hid = f"xdoc-{doc_id}"
            ops.append(xholon_op(hid, list(aids), list(centroid),
                                 store_id, prep))
            versions.append((hid, list(aids), list(centroid)))
        if len(ops) > MAX_XMEMBERSHIPS + 1:
            ops = ops[:MAX_XMEMBERSHIPS + 1]
            versions = versions[:MAX_XMEMBERSHIPS + 1]
        results, _info = tlstore.commit_batch(ops)
        for r in results:
            if r.get("status") != "committed":
                raise RuntimeError(
                    f"drain {format_commit_failure(r)}")
        for hid, members, desc in versions:
            if hid in xh:
                churn["xdoc_superseded"] += 1
            else:
                churn["xdoc_minted"] += 1
            xh[hid] = {"members": list(members),
                       "descriptor": list(desc), "seq": None}
            if use_catalog:
                xcat.upsert(hid, desc, len(members))
                atom_idx.add(hid, members)
        m = manifest.setdefault(doc_id, {"atoms": [], "holon": None,
                                         "xdoc": []})
        m["xdoc"].extend(r["op_id"] for r in results)
        if doc_id in pending:
            pending.remove(doc_id)
        manifest["_pending_placement"] = pending
        _save_manifest(manifest_path, manifest)
        drained.append(doc_id)
        n_ops += len(results)
        n_commits += 1
    if doc_ids is None:
        remaining = list(manifest.get("_pending_placement", []))
    else:
        remaining = [d for d in doc_ids
                     if d not in drained and d not in failed
                     and d not in already
                     and d not in retired_skipped]
    if own_proj:
        # Consume this call's own commits so the checkpoint covers
        # the end pin; the next loader starts warm with nothing
        # stale (bounded: only this call's versions).
        commit_catchup = proj.update(tlstore)
        proj.save(tlstore)
    else:
        commit_catchup = None
    ckpt_bytes = _Projections.checkpoint_bytes(tlstore)
    retained = proj.retained()
    retained["checkpoint_bytes"] = ckpt_bytes
    report = {"drained": drained, "already_placed": already,
              "failed": failed, "remaining": remaining,
              "retired_skipped": retired_skipped,
              "n_xholon_ops": n_ops, "n_commits": n_commits,
              "catchup": catchup,
              "commit_catchup": commit_catchup,
              "debt": {"backlog_before": backlog_before,
                       "drained": len(drained),
                       "already_placed": len(already),
                       "failed": len(failed),
                       "remaining": len(remaining),
                       "backpressured": max(
                           0, backlog_before - len(targets))
                       if doc_ids is None else 0,
                       "budget": budget},
              "churn": dict(churn,
                            minted=churn["xdoc_minted"],
                            superseded=churn["xdoc_superseded"]),
              "retained": retained}
    if use_catalog:
        # Opt-in only (flag-gated): catalog work receipt for F5/D2.
        # O-7: executed + logical bytes ride alongside the eligible
        # rows/bytes (eligible keys unchanged).
        report["catalog"] = {
            "decisions": catch["decisions"],
            "max_rows_per_decision": catch["max_rows"],
            "max_executed_rows_per_decision": catch["max_exec_rows"],
            "over_budget": catch["over_budget"],
            "ties": list(catch["ties"]),
            "xholon": {"rows": xcat.total_rows,
                       "bytes": xcat.total_bytes,
                       "calls": xcat.total_calls,
                       "n": xcat.n,
                       "executed_rows": xcat.total_executed_rows,
                       "descriptor_read_B":
                           xcat.total_descriptor_read_B,
                       "copy_B": xcat.total_copy_B,
                       "logical_read_B": xcat.total_logical_read_B,
                       "logical_written_B":
                           xcat.total_logical_written_B}
            if xcat is not None else None}
    if navigator is not None:
        # Opt-in only: default reports keep exactly the keys above.
        totals = {"placements": len(nav_entries),
                  "discovered": sum(e["discovered"]
                                    for e in nav_entries),
                  "visited": sum(e["visited"]
                                 for e in nav_entries),
                  "rescored": sum(e["rescored"]
                                  for e in nav_entries),
                  "rounds": sum(e["rounds"] for e in nav_entries),
                  "replenished": sum(e["replenished"]
                                     for e in nav_entries)}
        report["nav"] = nav_entries
        report["nav_totals"] = totals
    return report


def reconcile_manifest(tlstore, store_id="tl-sys-docs",
                       keyed_state=False, archive_manifest=False):
    """Rebuild the ingest manifest from COMMITTED data (crash recovery).

    Closes the commit-then-crash window: ops committed but never
    recorded (manifest torn — impossible after atomic writes — or
    stale) are re-registered by scanning ACCEPT_ATOMS commits and
    joining metas to op_ids. Recovered docs keep their committed
    revision_id (read from atom metas); source_sha256 is UNKNOWN for
    recovered docs (full source bytes are not stored), so the
    changed-bytes guard is skipped for them until a fresh ingest
    re-records it — documented, never silent.

    Docs already in the manifest are completed, never overwritten:
    missing op_ids append, present entries keep their fields.
    Pending placement is recomputed: acknowledged docs with no xdoc
    ops and no prior placement record re-enter the backlog.

    Returns {"recovered_docs": [...], "repaired_ops": n,
    "pending_placement": [...]}. Idempotent.

    keyed_state (C2 Closure P §5.2): additive keyed backend. Warm
    sidecars adopt the pinned suffix only (bounded); a missing sidecar
    takes the named cold rebuild (cold_rebuild receipt); legacy
    writers on sidecar stores refuse before committing.
    archive_manifest (P-2, Sec 5.7): explicit archive/compatibility
    export on this keyed call; ordinary calls write no JSON (stale
    marker instead). Requires keyed_state.
    """
    if archive_manifest and not keyed_state:
        raise ValueError("reconcile: archive_manifest needs "
                         "keyed_state=True (legacy cadence is pinned)")
    if keyed_state:
        return _reconcile_manifest_keyed(
            tlstore, store_id=store_id,
            archive_manifest=archive_manifest)
    from tlsys.prodstate import refuse_legacy_writer as _refuse
    _refuse(tlstore.store)
    from tlsys.identity import ATOM_SCHEME
    manifest, manifest_path = _load_manifest(tlstore.store)
    birth, epoch, mx, _triple = tlstore.pin()
    # R8-B (R7-A proposal C adoption): one unbounded read via min_seq
    # frontiers (read_commits_all) + one single-connection batched
    # artifact-row fetch shared by all three attribution passes below
    # (same call shape as ingest._committed_doc_state). Identical
    # results to the pre-R8-B loops at every scale the old 1M window
    # covered.
    rows = tlstore.read_commits_all(birth, epoch, mx,
                                    kind="ACCEPT_ATOMS")
    seqs = [r[0] for r in rows]
    op_of_seq = {r[0]: r[1] for r in rows}
    refs = tlstore.pub_refs(seqs)
    arows = tlstore.artifact_rows(
        [a for seq in seqs for a in refs.get(seq, [])])
    import json as _json
    # committed truth: doc -> {atoms, holon, xdoc, revision_id}
    truth = {}
    retired_truth = set()
    for seq in seqs:
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id,
                                         expect_digest=arow[4])
            try:
                meta = _json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            if meta.get("atom_scheme") != ATOM_SCHEME:
                continue  # foreign scheme: refused elsewhere, not here
            ret = meta.get("retirement")
            if isinstance(ret, dict) \
                    and isinstance(ret.get("doc"), str):
                retired_truth.add(ret["doc"])
                continue
            op_id = op_of_seq[seq]
            if "atom" in meta and "doc_id" in meta:
                t = truth.setdefault(
                    meta["doc_id"],
                    {"atoms": [], "holon": None, "xdoc": [],
                     "revision_id": meta.get("revision_id")})
                if op_id not in t["atoms"]:
                    t["atoms"].append(op_id)
                if t["revision_id"] is None:
                    t["revision_id"] = meta.get("revision_id")
            elif "holon" in meta:
                hid = meta["holon"]
                if hid.startswith("xdoc-"):
                    continue  # xdoc versions attributed below
                t = truth.setdefault(
                    hid, {"atoms": [], "holon": None, "xdoc": [],
                          "revision_id": None})
                t["holon"] = op_id  # latest wins (ascending seqs)
    # xdoc op attribution: disclosure leg carries no doc; attribute
    # via members -> atom metas -> doc (first member's doc wins; the
    # manifest xdoc list is advisory placement history, not identity).
    aid_doc = {}
    for seq in seqs:
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id,
                                         expect_digest=arow[4])
            try:
                meta = _json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(meta, dict) and "atom" in meta \
                    and "doc_id" in meta:
                aid_doc.setdefault(meta["atom"], meta["doc_id"])
    # A doc counts as placed when ANY of its aids appears in ANY
    # xdoc version's members (join versions span docs; first-member
    # attribution would miss joiners).
    placed_docs = set()
    for seq in seqs:
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id,
                                         expect_digest=arow[4])
            try:
                meta = _json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            hid = meta.get("holon")
            if not isinstance(hid, str) or not hid.startswith("xdoc-"):
                continue
            op_id = op_of_seq[seq]
            for aid in meta.get("members", []):
                doc = aid_doc.get(aid)
                if doc is None or doc not in truth:
                    continue
                placed_docs.add(doc)
                if op_id not in truth[doc]["xdoc"]:
                    truth[doc]["xdoc"].append(op_id)
    recovered, repaired = [], 0
    for doc, t in truth.items():
        if doc.startswith("xdoc-"):
            continue
        m = manifest.get(doc)
        if m is None:
            manifest[doc] = {"atoms": t["atoms"], "holon": t["holon"],
                             "xdoc": t["xdoc"],
                             "revision_id": t["revision_id"]}
            recovered.append(doc)
            repaired += len(t["atoms"]) + (1 if t["holon"] else 0) \
                + len(t["xdoc"])
        else:
            for op_id in t["atoms"]:
                if op_id not in m.setdefault("atoms", []):
                    m["atoms"].append(op_id)
                    repaired += 1
            if t["holon"] is not None and not m.get("holon"):
                m["holon"] = t["holon"]
                repaired += 1
            for op_id in t["xdoc"]:
                if op_id not in m.setdefault("xdoc", []):
                    m["xdoc"].append(op_id)
                    repaired += 1
            if not m.get("revision_id") and t["revision_id"]:
                m["revision_id"] = t["revision_id"]
    # backlog recompute: acknowledged + committed, but never placed
    # and not already pending -> pending (placement state unknown).
    pending = manifest.setdefault("_pending_placement", [])
    for doc, t in truth.items():
        if doc.startswith("xdoc-"):
            continue
        m = manifest.get(doc, {})
        if doc not in placed_docs and not m.get("xdoc") \
                and doc not in pending:
            # No xdoc evidence anywhere: placement never ran for this
            # doc (or ran with place_xdoc=False). Re-entering is
            # safe: drain commits only for memberless atoms and
            # reports the rest as already_placed without writes.
            pending.append(doc)
    manifest["_scheme"] = ATOM_SCHEME
    # Advisory retirement list converges to committed truth (closes
    # the retire commit-then-crash window; union, never removal).
    ret_pending = manifest.setdefault("_retired", [])
    for doc in sorted(retired_truth):
        if doc not in ret_pending:
            ret_pending.append(doc)
    _save_manifest(manifest_path, manifest)
    return {"recovered_docs": sorted(recovered),
            "repaired_ops": repaired,
            "pending_placement": list(pending)}


# ---- M2-A segment organization --------------------------------------
# Explicit caller-invoked organization (same contract shape as
# drain_placement_backlog: no autonomous worker, no new op kind, no
# in-place mutation). Reads committed atoms per doc, segments them by
# topic coherence (place.segment_atoms), and places segments into
# cross-source leaves with parent holons (place.decide_leaf /
# decide_parent + versioned leaf_op/parent_op metas). Per-doc holons
# and atoms are never rewritten: provenance containers stay
# byte-stable; hierarchy versions supersede additively (latest-wins).
SEG_ORGANIZED_KEY = "_seg_organized"
SEG_BATCH_OPS = 10  # ten-op durability: every commit carries <= 10 ops


def _doc_atom_rows(tlstore, doc_id):
    """[(aid, vec, chunk_ix, span, byte_span)] in chunk order.

    Same committed read shape as _doc_vecs plus span provenance for
    segment records. Fails closed (RuntimeError) with no committed
    atoms.
    """
    birth, epoch, mx, _triple = tlstore.pin()
    rows = tlstore.read_commits_all(birth, epoch, mx,
                                    kind="ACCEPT_ATOMS")
    seqs = [r[0] for r in rows]
    refs = tlstore.pub_refs(seqs)
    arows = tlstore.artifact_rows(
        [a for seq in seqs for a in refs.get(seq, [])])
    import json as _json
    out = []
    for seq in seqs:
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id,
                                         expect_digest=arow[4])
            try:
                meta = _json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            if meta.get("doc_id") == doc_id and "atom" in meta \
                    and "descriptor" in meta:
                out.append((meta["atom"],
                            [float(x) for x in meta["descriptor"]],
                            meta.get("chunk_ix"),
                            list(meta.get("span", [])),
                            list(meta.get("byte_span", []))))
    if not out:
        raise RuntimeError(
            f"organize: doc {doc_id!r} has no committed atoms; "
            "stays unorganized (never half-placed)")
    out.sort(key=lambda t: (t[2] is None, t[2]))
    return out


def organize_segments(tlstore, doc_ids=None, budget=None,
                      store_id="tl-sys-docs", t_seg=None,
                      t_leaf=None, t_parent=None,
                      max_leaf_members=None,
                      max_seg_memberships=None, navigator=None,
                      parent_navigator=None, projections=None,
                      profile=None, counters=None,
                      keyed_state=False, session=None,
                      archive_manifest=False, defer_manifest_save=False,
                      doc_checkpoint=None):
    """Organize docs into segment leaves + parents; costed report.

    doc_ids: explicit docs (must be acknowledged); None = every
    acknowledged doc not yet organized, in manifest order. budget caps
    the decisions this call (None = all targets). Threshold/cap
    overrides default to the place.py M2-A constants. Commits carry
    <= SEG_BATCH_OPS (10) ops each; a doc's leaf ops precede its
    parent ops within the batch order so latest-wins reads see the
    consistent pair.

    Locality: a join republishes only the joined leaves plus the
    parents that reference them; overflow mints one sibling leaf and
    attaches it to the full leaf's parents (or decided parents); a
    no-fit segment mints one singleton leaf (+ parent), never forced.
    Corrected revisions (new doc_id, S-02 changed-bytes rule) join as
    ordinary appends: old versions stay committed, only the affected
    path gains versions.

    Reads (M2-C): doc atoms and the hierarchy come from keyed
    projections (tlsys.proj) consumed once per call through a
    frontier -- a cold call scans once, a warm call decodes only
    new commits, and no per-doc step re-decodes unrelated state.
    projections: caller-owned Projections (reused across calls for
    warm frontiers; the caller owns save()); None loads (or cold
    builds) the store checkpoint and saves it before returning.

    navigator: M2-C opt-in tlsys.place.CandidateNavigator for
    the leaf leg (default None = exact decide_leaf per segment,
    behavior unchanged). parent_navigator: same for the parent
    leg (None = exact decide_parent). The legs need separate
    navigators (one discovery population each). When given, joins
    discover through the navigator with exact local rescore (same
    threshold/cap policy; the exact cap checks below still apply)
    and the report gains "nav" per-decision work entries plus
    "nav_totals" (same shape as drain_placement_backlog).

    profile/counters (C2 Lane O): profile is a Lane G profile dict
    (None = the exact C1 reference path, bit-identical to before).
    When profile["flags"]["organization_catalog_routing"] is true,
    leaf/parent decisions route through row-budgeted exact catalogs
    (D2 parity), per-doc snapshots become copy-on-write overlays of
    touched ids, parent scans become keyed reverse-map lookups,
    overflow numbering uses per-base counters, and the report gains
    a "catalog" section (rows/bytes, per-decision maxima, budget
    and tie diagnostics). counters (Lane G Counters, optional)
    receives the per-call catalog rows/bytes/scoring evals.
    Catalog routing does not compose with navigator legs: passing
    both fails closed.

    keyed_state (C2 Closure P §5.2): additive keyed backend (see
    tlsys.ingest.ingest_docs). session: optional ProducerSession.
    archive_manifest (P-2, Sec 5.7): explicit archive/compatibility
    export on this keyed call; ordinary calls write no JSON (stale
    marker instead). Requires keyed_state.

    defer_manifest_save (profiling/opt-in, default False): skip the
    per-doc full-manifest dump and write the manifest exactly once
    at call end. Committed ops and final manifest bytes are
    unchanged. Requires the legacy path (fails closed with
    keyed_state=True).

    doc_checkpoint (service-opt-in, default None): per-doc callback
    for the keyed explicit-doc path only, called as
    doc_checkpoint("before", doc_id) before each actual run_doc
    (return False to stop before starting the next doc) and
    doc_checkpoint("after", doc_id, failed.get(doc_id)) after
    run_doc returns. Requires keyed_state=True and explicit
    doc_ids (fails closed otherwise). Default None preserves
    exact caller behavior.

    Returns {"organized", "failed", "remaining", "n_leaf_ops",
    "n_parent_ops", "n_commits", "max_batch_ops", "catchup",
    "debt", "churn", "retained"}. Re-running over organized docs
    is commit-free (already organized => skipped). The last four
    keys are additive maintenance accounting (item 4): catch-up
    consumed this call, organization debt before/after with
    budget backpressure, hierarchy churn (superseded vs minted
    versions), and retained projection views.
    """
    if archive_manifest and not keyed_state:
        raise ValueError("organize: archive_manifest needs "
                         "keyed_state=True (legacy cadence is pinned)")
    if defer_manifest_save and keyed_state:
        raise ValueError("organize: defer_manifest_save needs "
                         "keyed_state=False (legacy cadence is pinned)")
    if doc_checkpoint is not None:
        if not keyed_state:
            raise ValueError("organize: doc_checkpoint needs "
                             "keyed_state=True (legacy cadence is pinned)")
        if doc_ids is None:
            raise ValueError("organize: doc_checkpoint needs explicit "
                             "doc_ids (no windowed-cursor support)")
        if not callable(doc_checkpoint):
            raise ValueError("organize: doc_checkpoint must be callable")
    from tlsys.place import (MAX_LEAF_MEMBERS, MAX_LEAF_PARENTS,
                             MAX_PARENT_CHILDREN, MAX_SEG_MEMBERSHIPS,
                             PARENT_PREFIX, SEG_PREFIX, T_LEAF,
                             T_PARENT, T_SEG_JOIN, decide_leaf,
                             decide_leaf_catalog,
                             decide_leaf_with_navigator,
                             decide_parent,
                             decide_parent_catalog,
                             decide_parent_with_navigator,
                             join_descriptor,
                             leaf_op, member_centroid, overflow_leaf_id,
                             parent_op, seg_leaf_id, seg_parent_id,
                             segment_atoms)
    if keyed_state:
        return _organize_segments_keyed(
            tlstore, doc_ids=doc_ids, budget=budget,
            store_id=store_id, t_seg=t_seg, t_leaf=t_leaf,
            t_parent=t_parent, max_leaf_members=max_leaf_members,
            max_seg_memberships=max_seg_memberships,
            navigator=navigator, parent_navigator=parent_navigator,
            projections=projections, profile=profile,
            counters=counters, session=session,
            archive_manifest=archive_manifest,
            doc_checkpoint=doc_checkpoint)
    from tlsys.prodstate import refuse_legacy_writer as _refuse
    _refuse(tlstore.store)
    from tlsys.catalog import (Catalog, LeafParentIndex,
                               MemberIndex, OverflowCounters,
                               TouchMap, catalog_row_budget,
                               catalog_routing_enabled)
    from tlsys.proj import Projections as _Projections
    from tlsys.store_if import prepare_artifact as _prep
    manifest, manifest_path = _load_manifest(tlstore.store)
    organized_key = manifest.setdefault(SEG_ORGANIZED_KEY, [])
    if doc_ids is None:
        targets = [d for d in manifest
                   if not d.startswith("_")
                   and isinstance(manifest[d], dict)
                   and manifest[d].get("atoms")
                   and d not in organized_key]
        if budget is not None:
            targets = targets[:budget]
    else:
        for d in doc_ids:
            if d not in manifest:
                raise ValueError(
                    f"organize: doc {d!r} not acknowledged in manifest")
            if d.startswith(SEG_PREFIX) or d.startswith(PARENT_PREFIX):
                raise ValueError(
                    f"organize: doc {d!r}: hierarchy prefixes reserved")
        targets = list(doc_ids) if budget is None \
            else list(doc_ids)[:budget]
    t_s = T_SEG_JOIN if t_seg is None else t_seg
    t_l = T_LEAF if t_leaf is None else t_leaf
    t_p = T_PARENT if t_parent is None else t_parent
    cap_leaf = MAX_LEAF_MEMBERS if max_leaf_members is None \
        else max_leaf_members
    cap_mem = MAX_SEG_MEMBERSHIPS if max_seg_memberships is None \
        else max_seg_memberships
    store = tlstore.store
    prep = lambda bb, sid: _prep(store, bb, sid)  # noqa: E731
    # Keyed projections, consumed once per call (M2-C): no per-doc
    # re-decode of unrelated state. The live overlay starts as a
    # deep copy of the consumed view and carries versions committed
    # earlier in this call (callers are serialized, so the overlay
    # equals the per-doc fresh reads it replaces); a failed doc
    # rolls its overlay entries back, like the old fresh re-read.
    own_proj = projections is None
    proj = _Projections.cached(tlstore) if own_proj else projections
    catchup = proj.update(tlstore)
    retired = set(proj.retired_view())
    retired_skipped = [d for d in targets if d in retired]
    targets = [d for d in targets if d not in retired]
    start_view = proj.hierarchy_view()
    start_lids = set(start_view["leaves"])
    start_pids = set(start_view["parents"])
    live_l = {k: {"members": list(v["members"]),
                  "descriptor": list(v["descriptor"]),
                  "segments": list(v.get("segments", [])),
                  "seq": v.get("seq")}
              for k, v in start_view["leaves"].items()}
    live_p = {k: {"members": list(v["members"]),
                  "children": list(v.get("children", [])),
                  "descriptor": list(v["descriptor"]),
                  "seq": v.get("seq")}
              for k, v in start_view["parents"].items()}
    # C2 Lane O working state (flag-gated; flag-off leaves every line
    # below this block on the reference path, bit-identical to before).
    use_catalog = catalog_routing_enabled(profile)
    if use_catalog and (navigator is not None
                        or parent_navigator is not None):
        raise ValueError(
            "organize: catalog routing does not compose with "
            "navigator legs")
    rcat = catalog_row_budget(profile) if use_catalog else None
    edge = memidx = ovc = None
    leaf_cat = parent_cat = None
    org_dim = None
    catch = {"decisions": 0, "max_rows": 0, "ties": [],
             "over_budget": False, "max_exec_rows": 0, "_exec_seen": 0}
    if use_catalog:
        live_l = TouchMap(live_l)
        live_p = TouchMap(live_p)
        edge = LeafParentIndex().build(live_p)
        memidx = MemberIndex().build(live_p, live_l)
        ovc = OverflowCounters()
        ovc.seed(live_l)
        for _v in live_l.values():
            org_dim = len(_v["descriptor"])
            break
        if org_dim is None:
            for _v in live_p.values():
                org_dim = len(_v["descriptor"])
                break
        if org_dim is not None:
            leaf_cat = Catalog("leaf", org_dim, rcat)
            leaf_cat.build(
                (lid, e["descriptor"], len(e["members"]))
                for lid, e in live_l.items())
            parent_cat = Catalog("parent", org_dim, rcat)
            parent_cat.build(
                (pid, e["descriptor"], len(e["children"]))
                for pid, e in live_p.items())

    def _harvest_cstats(stats):
        catch["decisions"] += 1
        rows = stats.get("catalog_rows", 0)
        if rows > catch["max_rows"]:
            catch["max_rows"] = rows
        # O-7: per-decision executed rows via totals delta (both
        # catalogs are call-local and only the harvested decide call
        # advances them, so the delta is exactly this decision's
        # executed work; a failure-path _rebuild_indexes swap
        # self-heals here via a non-positive delta).
        exec_now = ((leaf_cat.total_executed_rows
                     if leaf_cat is not None else 0)
                    + (parent_cat.total_executed_rows
                       if parent_cat is not None else 0))
        exec_rows = exec_now - catch["_exec_seen"]
        catch["_exec_seen"] = exec_now
        if exec_rows > catch["max_exec_rows"]:
            catch["max_exec_rows"] = exec_rows
        if stats.get("catalog_ties") and len(catch["ties"]) < 16:
            catch["ties"].append(stats["catalog_ties"])
        if stats.get("catalog_budget_exceeded"):
            catch["over_budget"] = True

    def _ensure_cats(dim):
        nonlocal leaf_cat, parent_cat, org_dim
        if leaf_cat is not None:
            return
        org_dim = dim
        leaf_cat = Catalog("leaf", dim, rcat)
        leaf_cat.build(
            (lid, e["descriptor"], len(e["members"]))
            for lid, e in live_l.items())
        parent_cat = Catalog("parent", dim, rcat)
        parent_cat.build(
            (pid, e["descriptor"], len(e["children"]))
            for pid, e in live_p.items())
        leaf_cat.begin_doc()
        parent_cat.begin_doc()

    def _rebuild_indexes():
        # Failure-path-only O(N) resync after mid-doc committed batches
        # merged into the live overlay (exceptional: commit failures).
        nonlocal leaf_cat, parent_cat, edge, memidx, ovc
        leaf_cat = Catalog("leaf", org_dim, rcat)
        leaf_cat.build(
            (lid, e["descriptor"], len(e["members"]))
            for lid, e in live_l.items())
        parent_cat = Catalog("parent", org_dim, rcat)
        parent_cat.build(
            (pid, e["descriptor"], len(e["children"]))
            for pid, e in live_p.items())
        edge = LeafParentIndex().build(live_p)
        memidx = MemberIndex().build(live_p, live_l)
        ovc = OverflowCounters()
        ovc.seed(live_l)

    unorganized_before = len(
        [d for d in manifest
         if not d.startswith("_")
         and isinstance(manifest[d], dict)
         and manifest[d].get("atoms")
         and d not in organized_key])
    organized, failed = [], {}
    nav_entries = []
    n_leaf_ops = n_parent_ops = n_commits = 0
    max_batch = 0
    churn = {"leaf_superseded": 0, "leaf_minted": 0,
             "parent_superseded": 0, "parent_minted": 0}
    emitted_ids = set()
    for doc_id in targets:
        if doc_id.startswith(SEG_PREFIX) \
                or doc_id.startswith(PARENT_PREFIX):
            failed[doc_id] = "hierarchy prefixes reserved"
            continue
        if use_catalog:
            live_l.begin_doc()
            live_p.begin_doc()
            edge.begin_doc()
            memidx.begin_doc()
            ovc.begin_doc()
            if leaf_cat is not None:
                leaf_cat.begin_doc()
                parent_cat.begin_doc()
        else:
            snap_l, snap_p = dict(live_l), dict(live_p)
        try:
            rows = proj.doc_rows(doc_id)
        except RuntimeError as e:
            failed[doc_id] = str(e)
            continue
        aids = [r[0] for r in rows]
        vecs = [r[1] for r in rows]
        vec_of = dict(zip(aids, vecs))
        if use_catalog and vecs:
            _ensure_cats(len(vecs[0]))
        ops = []
        n_leaf = 0

        def _churn(hid, is_leaf):
            if hid in emitted_ids:
                key = "leaf_superseded" if is_leaf \
                    else "parent_superseded"
            elif hid in (start_lids if is_leaf else start_pids):
                key = "leaf_superseded" if is_leaf \
                    else "parent_superseded"
            else:
                key = "leaf_minted" if is_leaf else "parent_minted"
            churn[key] += 1
            emitted_ids.add(hid)

        def _emit_leaf(lid, members, desc, segrecs):
            ops.append(leaf_op(lid, members, desc, store_id, prep,
                               segments=segrecs))
            live_l[lid] = {"members": list(members),
                           "descriptor": list(desc),
                           "segments": list(segrecs), "seq": None}
            if use_catalog:
                leaf_cat.upsert(lid, desc, len(members))
            _churn(lid, True)

        def _republish_parents(child_lid, fresh_aids):
            # Every live parent referencing the grown child gains one
            # version with the fresh atoms (dedupe by set difference);
            # unchanged parents gain no version (local correction).
            if use_catalog:
                pids = edge.parents_of(child_lid)
            else:
                pids = sorted(live_p)
            for pid in pids:
                par = live_p[pid]
                if child_lid not in par["children"]:
                    continue
                if use_catalog:
                    have = memidx.union_of(pid)
                else:
                    have = set(par["members"])
                add = [a for a in fresh_aids if a not in have]
                if not add:
                    continue
                try:
                    avecs = [vec_of[a] for a in add]
                except KeyError:
                    raise RuntimeError(
                        f"organize: doc {doc_id!r}: parent {pid!r} "
                        "needs vectors outside this doc (foreign leaf "
                        "version; refusing half-update)")
                members = par["members"] + add
                desc = join_descriptor(par["descriptor"],
                                       len(par["members"]), avecs)
                ops.append(parent_op(pid, par["children"], members,
                                       desc, store_id, prep))
                live_p[pid] = {"members": members,
                               "children": list(par["children"]),
                               "descriptor": desc, "seq": None}
                if use_catalog:
                    parent_cat.upsert(pid, desc,
                                      len(par["children"]))
                    for _a in add:
                        memidx.add(pid, _a)
                _churn(pid, False)

        def _attach_leaf(new_lid, new_desc, new_aids, preferred):
            # Attach a fresh leaf to parents: preferred first (the
            # overflow base's parents), then decided joins, else mint
            # one deterministic parent. Returns parent ids attached.
            attached = []
            cands = [p for p in preferred if p in live_p]
            if use_catalog:
                pstats = {}
                decided = decide_parent_catalog(
                    new_desc, parent_cat, t_parent=t_p,
                    stats=pstats, counters=counters)
                _harvest_cstats(pstats)
            elif parent_navigator is None:
                decided = decide_parent(new_desc, live_p,
                                        t_parent=t_p)
            else:
                pstats = {}
                decided = decide_parent_with_navigator(
                    new_desc, live_p, parent_navigator,
                    t_parent=t_p, stats=pstats,
                    path="organize-parent")
                nav_entries.append({
                    "doc": doc_id, "leaf": new_lid, "leg": "parent",
                    "joins": list(decided),
                    "discovered": pstats["nav_discovered"],
                    "visited": pstats["scored"]
                    + pstats["full_skipped"],
                    "rescored": pstats["scored"],
                    "rounds": pstats["nav_rounds"],
                    "replenished": pstats["nav_replenished"],
                    "changed_ids": pstats["nav_changed_ids"]})
            for pid in decided:
                if pid not in cands:
                    cands.append(pid)
            for pid in cands:
                if len(attached) >= MAX_LEAF_PARENTS:
                    break
                par = live_p[pid]
                if new_lid in par["children"]:
                    continue
                if len(par["children"]) >= MAX_PARENT_CHILDREN:
                    continue
                if use_catalog:
                    have = memidx.union_of(pid)
                else:
                    have = set(par["members"])
                add = [a for a in new_aids if a not in have]
                members = par["members"] + add
                if add:
                    desc = join_descriptor(
                        par["descriptor"], len(par["members"]),
                        [vec_of[a] for a in add])
                else:
                    desc = list(par["descriptor"])
                ops.append(parent_op(pid, par["children"] + [new_lid],
                                       members, desc, store_id, prep))
                live_p[pid] = {"members": members,
                               "children": par["children"] + [new_lid],
                               "descriptor": desc, "seq": None}
                if use_catalog:
                    parent_cat.upsert(
                        pid, desc, len(par["children"]) + 1)
                    edge.add_edge(pid, new_lid)
                    memidx.ensure(pid)
                    for _a in new_aids:
                        memidx.add(pid, _a)
                _churn(pid, False)
                attached.append(pid)
            if not attached:
                pid = seg_parent_id(new_lid)
                if pid in live_p and new_lid in live_p[pid]["children"]:
                    return [pid]  # re-run stability: already attached
                children = ([new_lid] if pid not in live_p
                            else live_p[pid]["children"] + [new_lid])
                if use_catalog:
                    have = memidx.union_of(pid) if pid in live_p \
                        else set()
                else:
                    have = set(live_p[pid]["members"]) \
                        if pid in live_p else set()
                add = [a for a in new_aids if a not in have]
                base = live_p[pid] if pid in live_p else None
                members = (list(base["members"]) if base else []) + add
                if base is not None and add:
                    desc = join_descriptor(
                        base["descriptor"], len(base["members"]),
                        [vec_of[a] for a in add])
                elif base is not None:
                    desc = list(base["descriptor"])
                else:
                    desc = list(new_desc)
                ops.append(parent_op(pid, children, members, desc,
                                       store_id, prep))
                live_p[pid] = {"members": members, "children": children,
                               "descriptor": desc, "seq": None}
                if use_catalog:
                    parent_cat.upsert(pid, desc, len(children))
                    edge.add_edge(pid, new_lid)
                    memidx.ensure(pid)
                    for _a in new_aids:
                        memidx.add(pid, _a)
                _churn(pid, False)
                attached.append(pid)
            return attached

        snap_churn = dict(churn)
        snap_emitted = set(emitted_ids)
        committed_any = False
        try:
            for six, seg in enumerate(
                    segment_atoms(aids, vecs, t_join=t_s)):
                seg_aids = [aids[ix] for ix in seg]
                seg_vecs = [vecs[ix] for ix in seg]
                centroid = member_centroid(seg_vecs)
                segrec = {"doc": doc_id, "aids": list(seg_aids),
                          "spans": [rows[ix][3] for ix in seg],
                          "byte_spans": [rows[ix][4] for ix in seg]}
                stats = {}
                if use_catalog:
                    joins = decide_leaf_catalog(
                        centroid, leaf_cat, t_leaf=t_l,
                        max_m=cap_mem, max_members=cap_leaf,
                        stats=stats, counters=counters)
                    _harvest_cstats(stats)
                elif navigator is None:
                    joins = decide_leaf(
                        centroid, live_l, t_leaf=t_l,
                        max_m=cap_mem, max_members=cap_leaf,
                        stats=stats)
                else:
                    joins = decide_leaf_with_navigator(
                        centroid, live_l, navigator, t_leaf=t_l,
                        max_m=cap_mem, max_members=cap_leaf,
                        stats=stats, path="organize-leaf")
                    nav_entries.append({
                        "doc": doc_id, "seg": six, "leg": "leaf",
                        "joins": list(joins),
                        "discovered": stats["nav_discovered"],
                        "visited": stats["scored"],
                        "rescored": stats["scored"],
                        "rounds": stats["nav_rounds"],
                        "replenished": stats["nav_replenished"],
                        "changed_ids": stats["nav_changed_ids"]})
                applied = []
                for lid in joins:
                    cur = live_l[lid]
                    fresh = [a for a in seg_aids
                             if a not in set(cur["members"])]
                    if not fresh:
                        continue
                    if len(cur["members"]) + len(fresh) > cap_leaf:
                        continue  # exact cap (same rule as sync path)
                    members = cur["members"] + fresh
                    fvecs = [vec_of[a] for a in fresh]
                    desc = join_descriptor(cur["descriptor"],
                                           len(cur["members"]), fvecs)
                    _emit_leaf(lid, members, desc,
                               cur.get("segments", []) + [segrec])
                    applied.append(lid)
                    n_leaf += 1
                    _republish_parents(lid, fresh)
                if not applied:
                    if stats.get("full_qualifying"):
                        # Local overflow: one sibling leaf + attach to
                        # the full leaf's parents (preferred).
                        base = stats["full_qualifying"][0]
                        if use_catalog:
                            n = ovc.next_n(base, live_l)
                        else:
                            stem = base + "-ov"
                            n = 1 + sum(1 for k in live_l
                                        if k.startswith(stem))
                        sib = overflow_leaf_id(base, n)
                        _emit_leaf(sib, list(seg_aids),
                                   list(centroid), [segrec])
                        n_leaf += 1
                        if use_catalog:
                            preferred = edge.parents_of(base)
                        else:
                            preferred = sorted(
                                p for p, v in live_p.items()
                                if base in v["children"])
                        _attach_leaf(sib, centroid, seg_aids,
                                     preferred)
                    else:
                        # No fit anywhere: singleton leaf (+ parent),
                        # never forced into an unrelated group.
                        lid = seg_leaf_id(doc_id, six)
                        if lid in live_l:
                            cur = live_l[lid]
                            fresh = [a for a in seg_aids
                                     if a not in set(cur["members"])]
                            if fresh and len(cur["members"]) \
                                    + len(fresh) <= cap_leaf:
                                members = cur["members"] + fresh
                                desc = join_descriptor(
                                    cur["descriptor"],
                                    len(cur["members"]),
                                    [vec_of[a] for a in fresh])
                                _emit_leaf(
                                    lid, members, desc,
                                    cur.get("segments", []) + [segrec])
                                n_leaf += 1
                                _republish_parents(lid, fresh)
                            # else: already present (re-run) -> no op
                        else:
                            _emit_leaf(lid, list(seg_aids),
                                       list(centroid), [segrec])
                            n_leaf += 1
                            _attach_leaf(lid, centroid, seg_aids, [])
            # Commit this doc's ops in <= 10-op batches (ten-op
            # durability); leaf ops precede parent ops by emission.
            op_ids = []
            for lo in range(0, len(ops), SEG_BATCH_OPS):
                chunk = ops[lo:lo + SEG_BATCH_OPS]
                max_batch = max(max_batch, len(chunk))
                results, _info = tlstore.commit_batch(chunk)
                for r in results:
                    if r.get("status") != "committed":
                        raise RuntimeError(
                            f"organize {format_commit_failure(r)}")
                    op_ids.append(r["op_id"])
                committed_any = True
                n_commits += 1
        except RuntimeError as e:
            # Roll the failed doc's uncommitted overlay back (the old
            # per-doc fresh re-read never saw it); committed partial
            # batches are consumed into the projection and merged so
            # later docs see exactly committed state, as before.
            failed[doc_id] = str(e)
            touched = emitted_ids - snap_emitted
            if use_catalog:
                live_l.rollback()
                live_p.rollback()
                edge.rollback()
                memidx.rollback()
                ovc.rollback()
                if leaf_cat is not None:
                    leaf_cat.rollback()
                    parent_cat.rollback()
            else:
                live_l.clear()
                live_l.update(snap_l)
                live_p.clear()
                live_p.update(snap_p)
            churn.clear()
            churn.update(snap_churn)
            emitted_ids.intersection_update(snap_emitted)
            if committed_any:
                proj.update(tlstore)
                fresh = proj.hierarchy_view()
                for hid in touched:
                    if hid in fresh["leaves"]:
                        v = fresh["leaves"][hid]
                        live_l[hid] = {
                            "members": list(v["members"]),
                            "descriptor": list(v["descriptor"]),
                            "segments": list(v.get("segments", [])),
                            "seq": v.get("seq")}
                    elif hid in fresh["parents"]:
                        v = fresh["parents"][hid]
                        live_p[hid] = {
                            "members": list(v["members"]),
                            "children": list(v.get("children", [])),
                            "descriptor": list(v["descriptor"]),
                            "seq": v.get("seq")}
                if use_catalog:
                    _rebuild_indexes()
            continue
        n_leaf_ops += n_leaf
        # Parent ops this doc = emitted ops minus leaf ops. Leaf ops
        # are counted at emission; parent ops ride the same batches.
        n_parent_ops += len(ops) - n_leaf
        m = manifest.setdefault(doc_id, {"atoms": [], "holon": None,
                                         "xdoc": []})
        m.setdefault("seg", []).extend(op_ids)
        if doc_id not in organized_key:
            organized_key.append(doc_id)
        manifest[SEG_ORGANIZED_KEY] = organized_key
        if not defer_manifest_save:
            _save_manifest(manifest_path, manifest)
        organized.append(doc_id)
    if defer_manifest_save:
        # One end-save covers the call: the same in-memory content
        # the per-doc saves would have written last (flag OFF path
        # is untouched).
        _save_manifest(manifest_path, manifest)
    if doc_ids is None:
        remaining = [d for d in manifest
                     if not d.startswith("_")
                     and isinstance(manifest[d], dict)
                     and manifest[d].get("atoms")
                     and d not in organized_key
                     and d not in retired]
    else:
        remaining = [d for d in targets
                     if d not in organized and d not in failed]
    if own_proj:
        # Consume this call's own commits so the checkpoint covers
        # the end pin; the next loader starts warm with nothing
        # stale (bounded: only this call's versions).
        commit_catchup = proj.update(tlstore)
        proj.save(tlstore)
    else:
        commit_catchup = None
    ckpt_bytes = _Projections.checkpoint_bytes(tlstore)
    retained = proj.retained()
    retained["checkpoint_bytes"] = ckpt_bytes
    report = {"organized": organized, "failed": failed,
              "remaining": remaining,
              "retired_skipped": retired_skipped,
              "n_leaf_ops": n_leaf_ops,
              "n_parent_ops": n_parent_ops, "n_commits": n_commits,
              "max_batch_ops": max_batch,
              "catchup": catchup,
              "commit_catchup": commit_catchup,
              "debt": {"unorganized_before": unorganized_before,
                       "organized": len(organized),
                       "failed": len(failed),
                       "remaining": len(remaining),
                       "backpressured": max(
                           0, unorganized_before - len(targets))
                       if doc_ids is None else 0,
                       "budget": budget},
              "churn": dict(churn,
                            minted=churn["leaf_minted"]
                            + churn["parent_minted"],
                            superseded=churn["leaf_superseded"]
                            + churn["parent_superseded"]),
              "retained": retained}
    if use_catalog:
        # Opt-in only (flag-gated): catalog work receipt for F5/D2.
        # O-7: executed + logical bytes ride alongside the eligible
        # rows/bytes (eligible keys unchanged).
        def _exec_tot(cat):
            return {"rows": cat.total_rows,
                    "bytes": cat.total_bytes,
                    "calls": cat.total_calls,
                    "n": cat.n,
                    "executed_rows": cat.total_executed_rows,
                    "descriptor_read_B":
                        cat.total_descriptor_read_B,
                    "copy_B": cat.total_copy_B,
                    "logical_read_B": cat.total_logical_read_B,
                    "logical_written_B":
                        cat.total_logical_written_B}
        leaf_tot = _exec_tot(leaf_cat) \
            if leaf_cat is not None else None
        parent_tot = _exec_tot(parent_cat) \
            if parent_cat is not None else None
        report["catalog"] = {
            "decisions": catch["decisions"],
            "max_rows_per_decision": catch["max_rows"],
            "max_executed_rows_per_decision": catch["max_exec_rows"],
            "over_budget": catch["over_budget"],
            "ties": list(catch["ties"]),
            "leaf": leaf_tot, "parent": parent_tot}
    if navigator is not None or parent_navigator is not None:
        # Opt-in only (same shape as drain_placement_backlog).
        totals = {"placements": len(nav_entries),
                  "discovered": sum(e["discovered"]
                                    for e in nav_entries),
                  "visited": sum(e["visited"]
                                 for e in nav_entries),
                  "rescored": sum(e["rescored"]
                                  for e in nav_entries),
                  "rounds": sum(e["rounds"] for e in nav_entries),
                  "replenished": sum(e["replenished"]
                                     for e in nav_entries)}
        report["nav"] = nav_entries
        report["nav_totals"] = totals
    return report


def _keyed_compact_bounds(state):
    """Compaction bounds for the debt hook: binding, else defaults.

    Reads the recorded candidate binding's compact block when the
    store carries one (None = use PROJ_COMPACT_DEFAULTS). Never
    raises: an unreadable block falls back to defaults (the hook
    receipts which bounds applied).
    """
    import json as _json
    try:
        raw = state.meta("candidate_json")
    except Exception:  # noqa: BLE001 -- bounds fallback, not state
        return None
    if not raw:
        return None
    try:
        rec = _json.loads(raw)
    except ValueError:
        return None
    bounds = rec.get("compact") if isinstance(rec, dict) else None
    return dict(bounds) if isinstance(bounds, dict) else None


def _keyed_retained(state, tlstore, hier_live=None):
    """Bounded retained report: O(1) counters + resident maps only.

    Never forces a checkpoint parse or a population recount. hier_live
    = (live_l, live_p) when the hierarchy leg ran this call (leaf/
    parent counts are O(1) lens); else hierarchy counts ride as None
    with hierarchy_loaded False. The journal block is the bounded
    debt census (stats + capped line count; P-2).
    """
    from tlsys.proj import Projections as _Projections
    c = state.counters()
    f = state.frontier()
    ckpt = _Projections.checkpoint_bytes(tlstore)
    ret = {"docs": c.get("docs_with_atoms", 0),
           "atoms": c.get("atoms_committed", 0),
           "xdoc": c.get("xdoc_versions", 0),
           "retired": c.get("retired_count", 0),
           "frontier": f.get("seq", 0),
           "checkpoint_bytes": ckpt,
           "journal": _Projections.journal_debt(tlstore)}
    if hier_live is not None:
        live_l, live_p = hier_live
        ret["leaves"] = len(live_l)
        ret["parents"] = len(live_p)
        ret["hierarchy_loaded"] = True
    else:
        ret["leaves"] = None
        ret["parents"] = None
        ret["hierarchy_loaded"] = False
    return ret


def _drain_placement_backlog_keyed(tlstore, store_id="tl-sys-docs",
                                   budget=None, t_place=None,
                                   doc_ids=None, navigator=None,
                                   projections=None, profile=None,
                                   counters=None, session=None,
                                   archive_manifest=False):
    """Keyed-backend drain (Closure P §5.2; see drain_placement_backlog).

    Ordered windowed backlog reads (cursor, bounded memory), keyed
    placed checks (no per-doc union scans), one atomic txn per doc,
    R_cat pre-execution gate on catalog decisions (rejected docs stay
    pending with a named reason). P-2: explicit-archive-only export
    plus the bounded projection-compaction debt hook (binding
    bounds, else defaults; receipted; never on the ingest path).
    """
    from tlsys.store_if import prepare_artifact as _prep
    from tlsys.proj import Projections as _Projections
    from tlsys.place import decide_catalog as _decide_catalog
    from tlsys.catalog import (catalog_row_budget as _rcat,
                               catalog_routing_enabled as _flag_on)
    from tlsys.prodstate import (
        ProducerState, ProducerSession, consume_suffix, gate_decision,
        OverBudgetRejected, REMAINING_SAMPLE, TARGET_WINDOW,
        close_out_keyed_call)
    from tlsys.ingest import MANIFEST_NAME as _MAN
    import json as _json
    import os as _os
    store = tlstore.store
    manifest = {}
    mpath = _os.path.join(store.root, _MAN)
    if _os.path.isfile(mpath):
        with open(mpath) as f:
            manifest = _json.load(f)
    state, migrec = ProducerState.create_or_migrate(tlstore, manifest)
    keyed_rec = {"migrated": migrec, "suffix": None, "adopted_ops": 0,
                 "rcat_estimates": [], "rcat_estimate_count": 0}
    try:
        sufrec = consume_suffix(tlstore, state)
        keyed_rec["suffix"] = sufrec
        keyed_rec["adopted_ops"] = sufrec["adopted_ops"]
        use_catalog = _flag_on(profile)
        if use_catalog and navigator is not None:
            raise ValueError(
                "drain: catalog routing does not compose with "
                "the navigator leg")
        if session is not None and use_catalog:
            from tlsys.ingest import \
                _check_session_profile as _check_sess
            _check_sess(session, profile, "drain")
        # Targets: explicit (caller-bounded) or windowed queue cursor
        # (bounded memory; deletions of earlier seqs cannot shift the
        # cursor, and drain never enqueues, so chunked == snapshot).
        explicit = doc_ids is not None
        if explicit:
            for d in doc_ids:
                if state.get_doc(d) is None:
                    raise ValueError(
                        f"drain: doc {d!r} not acknowledged in manifest")
                if d.startswith("xdoc-"):
                    raise ValueError(
                        f"drain: doc {d!r}: 'xdoc-' prefix reserved")
            exp_targets = list(doc_ids) if budget is None \
                else list(doc_ids)[:budget]
        t = T_PLACE if t_place is None else t_place
        prep = lambda bb, sid: _prep(store, bb, sid)  # noqa: E731
        own_proj = projections is None
        proj = _Projections.cached(tlstore) if own_proj else projections
        catchup = proj.update(tlstore)
        retired = proj.retired_view()
        sess = session if session is not None \
            else ProducerSession(profile)
        sess.begin_call()
        sess.attach(tlstore, state)
        xh, atom_idx = sess.ensure_xdoc(
            proj.xholons_view(), proj.frontier, with_atom_index=True)
        xcat = None
        drain_dim = None
        if use_catalog and xh:
            first = next(iter(xh.values()))
            drain_dim = len(first["descriptor"])
            xcat = sess.xdoc_catalog(drain_dim)
        tot0 = None
        if xcat is not None:
            from tlsys.ingest import _keyed_totals_snapshot as _snap
            tot0 = _snap(xcat)
        catch = {"decisions": 0, "max_rows": 0, "ties": [],
                 "over_budget": False, "max_exec_rows": 0,
                 "_exec_seen": None}
        rejected = []
        backlog_before = state.pending_count()
        drained, failed = [], {}
        already = []
        retired_skipped = []
        nav_entries = []
        churn = {"xdoc_superseded": 0, "xdoc_minted": 0}
        touched_xids = set()
        n_ops = n_commits = attempted = 0

        def run_doc(doc_id):
            nonlocal xcat, drain_dim, n_ops, n_commits, attempted
            if doc_id in retired:
                retired_skipped.append(doc_id)
                return
            attempted += 1
            try:
                pairs = proj.doc_vecs(doc_id)
            except RuntimeError:
                failed[doc_id] = (
                    f"drain: doc {doc_id!r} has no committed atoms; "
                    "stays pending (never half-placed)")
                return
            aids = [a for a, _v in pairs]
            vecs = [v for _a, v in pairs]
            centroid = member_centroid(vecs)
            placed = all(a in atom_idx for a in aids)
            if placed:
                if state.is_pending(doc_id):
                    state.backlog_del(doc_id)
                already.append(doc_id)
                return
            if use_catalog:
                if xcat is None and vecs:
                    drain_dim = len(vecs[0])
                    xcat = sess.xdoc_catalog(drain_dim)
                if catch["_exec_seen"] is None:
                    catch["_exec_seen"] = xcat.total_executed_rows
                rows_e = int(xcat.mask_lt(MAX_XHOLON_MEMBERS).sum())
                try:
                    est = gate_decision(
                        "xholon", xcat.n, xcat.dim, [rows_e],
                        [MAX_XMEMBERSHIPS], _rcat(profile),
                        f"drain:{doc_id}")
                except OverBudgetRejected as e:
                    # Nothing executed: stays pending with a named
                    # reason (resource boundary, not a defect).
                    rejected.append(
                        {"doc": doc_id, "leg": "drain-place",
                         "reason": str(e), "estimate": e.estimate})
                    return
                keyed_rec["rcat_estimate_count"] += 1
                if len(keyed_rec["rcat_estimates"]) < 64:
                    keyed_rec["rcat_estimates"].append(
                        {"doc": doc_id, "leg": "drain-place",
                         "estimate": est})
                dstats = {}
                joins = _decide_catalog(centroid, xcat, t_place=t,
                                        stats=dstats,
                                        counters=counters)
                catch["decisions"] += 1
                rows = dstats.get("catalog_rows", 0)
                if rows > catch["max_rows"]:
                    catch["max_rows"] = rows
                exec_now = xcat.total_executed_rows
                exec_rows = exec_now - catch["_exec_seen"]
                catch["_exec_seen"] = exec_now
                if exec_rows > catch["max_exec_rows"]:
                    catch["max_exec_rows"] = exec_rows
                if dstats.get("catalog_ties") \
                        and len(catch["ties"]) < 16:
                    catch["ties"].append(dstats["catalog_ties"])
                if dstats.get("catalog_budget_exceeded"):
                    catch["over_budget"] = True
            elif navigator is None:
                joins = decide(centroid, xh, t_place=t)
            else:
                nstats = {}
                joins = decide_with_navigator(
                    centroid, xh, navigator, t_place=t,
                    stats=nstats, path="deferred-place")
                nav_entries.append({
                    "doc": doc_id, "joins": list(joins),
                    "discovered": nstats["nav_discovered"],
                    "visited": nstats["visited"],
                    "rescored": nstats["scored"],
                    "rounds": nstats["nav_rounds"],
                    "replenished": nstats["nav_replenished"],
                    "changed_ids": nstats["nav_changed_ids"]})
            ops = []
            versions = []
            applied = []
            for hid in joins:
                old = xh[hid]
                ixs = [ix for ix, a in enumerate(aids)
                       if a not in old["members"]]
                if not ixs:
                    continue
                if len(old["members"]) + len(ixs) > MAX_XHOLON_MEMBERS:
                    continue
                members = old["members"] + [aids[ix] for ix in ixs]
                desc = join_descriptor(old["descriptor"],
                                       len(old["members"]),
                                       [vecs[ix] for ix in ixs])
                ops.append(xholon_op(hid, members, desc, store_id,
                                     prep))
                versions.append((hid, members, desc))
                applied.append(hid)
            if not applied:
                hid = f"xdoc-{doc_id}"
                ops.append(xholon_op(hid, list(aids), list(centroid),
                                     store_id, prep))
                versions.append((hid, list(aids), list(centroid)))
            if len(ops) > MAX_XMEMBERSHIPS + 1:
                ops = ops[:MAX_XMEMBERSHIPS + 1]
                versions = versions[:MAX_XMEMBERSHIPS + 1]
            results, _info = tlstore.commit_batch(ops)
            for r in results:
                if r.get("status") != "committed":
                    raise RuntimeError(
                        f"drain {format_commit_failure(r)}")
            op_recs = []
            for (hid, members, desc), r in zip(versions, results):
                if hid in xh:
                    churn["xdoc_superseded"] += 1
                else:
                    churn["xdoc_minted"] += 1
                xh[hid] = {"members": list(members),
                           "descriptor": list(desc), "seq": None}
                touched_xids.add(hid)
                if use_catalog:
                    xcat.upsert(hid, desc, len(members))
                    atom_idx.add(hid, members)
                else:
                    atom_idx.add(hid, members)
                op_recs.append({"doc": doc_id, "kind": "xholon",
                                "op_id": r["op_id"], "seq": None,
                                "xdoc_id": hid})
            sess.note_dirty("xdoc")
            _b, _e, _mx, _triple = tlstore.pin()
            state.record_flush(op_recs, {},
                               frontier=(_b, _e, _mx, _triple),
                               backlog_del=[doc_id])
            drained.append(doc_id)
            n_ops += len(results)
            n_commits += 1

        if explicit:
            for doc_id in exp_targets:
                run_doc(doc_id)
            remaining_ids = [d for d in exp_targets
                             if d not in drained and d not in failed
                             and d not in already
                             and d not in retired_skipped]
            remaining_count = len(remaining_ids)
        else:
            cursor, budget_left = 0, budget
            while True:
                window = state.pending_window(
                    TARGET_WINDOW if budget_left is None
                    else min(TARGET_WINDOW, budget_left), cursor)
                if not window:
                    break
                for doc_id, qseq in window:
                    cursor = qseq
                    run_doc(doc_id)
                    if budget_left is not None:
                        budget_left -= 1
                        if budget_left <= 0:
                            break
                if budget_left is not None and budget_left <= 0:
                    break
            remaining_count = state.pending_count()
            remaining_ids = state.pending_sample()
        if own_proj:
            commit_catchup = proj.update(tlstore)
            proj.save(tlstore)
        else:
            commit_catchup = None
        if touched_xids and own_proj:
            sess.leg_sync("xdoc", proj.xholons_view(), touched_xids,
                          proj.frontier)
        sess.persist(state)
        compact_rec = {"checked": False, "compacted": False}
        if own_proj:
            try:
                compact_rec = _Projections.maybe_compact(
                    tlstore, bounds=_keyed_compact_bounds(state),
                    reason="maintenance-debt-hook")
            except ValueError:
                compact_rec = _Projections.maybe_compact(
                    tlstore, bounds=None,
                    reason="maintenance-debt-hook")
                compact_rec["bounds_fallback"] = True
        keyed_rec["compact"] = compact_rec
        retained = _keyed_retained(state, tlstore)
        _man, arch_rec = close_out_keyed_call(
            state, mpath, archive_manifest=archive_manifest,
            reason="drain")
        keyed_rec["archive"] = arch_rec
        keyed_rec["candidate_version"] = arch_rec[
            "candidate_version"]
    finally:
        state.close()
    if use_catalog and rejected:
        catch["over_budget"] = True
    from tlsys.ingest import _keyed_totals_delta as _delta
    report = {"drained": drained, "already_placed": already,
              "failed": failed,
              "remaining": remaining_ids[:REMAINING_SAMPLE],
              "remaining_count": remaining_count,
              "remaining_truncated": (len(remaining_ids)
                                      > REMAINING_SAMPLE
                                      if explicit else remaining_count
                                      > REMAINING_SAMPLE),
              "retired_skipped": retired_skipped,
              "n_xholon_ops": n_ops, "n_commits": n_commits,
              "catchup": catchup,
              "commit_catchup": commit_catchup,
              "debt": {"backlog_before": backlog_before,
                       "drained": len(drained),
                       "already_placed": len(already),
                       "failed": len(failed),
                       "remaining": remaining_count,
                       "rejected_over_budget": len(rejected),
                       "backpressured": max(
                           0, backlog_before - attempted)
                       if not explicit else 0,
                       "budget": budget},
              "churn": dict(churn,
                            minted=churn["xdoc_minted"],
                            superseded=churn["xdoc_superseded"]),
              "retained": retained}
    if use_catalog:
        report["catalog"] = {
            "decisions": catch["decisions"],
            "max_rows_per_decision": catch["max_rows"],
            "max_executed_rows_per_decision": catch["max_exec_rows"],
            "over_budget": catch["over_budget"],
            "ties": list(catch["ties"]),
            "rejected": rejected,
            "xholon": _delta(xcat, tot0)}
    if navigator is not None:
        totals = {"placements": len(nav_entries),
                  "discovered": sum(e["discovered"]
                                    for e in nav_entries),
                  "visited": sum(e["visited"]
                                 for e in nav_entries),
                  "rescored": sum(e["rescored"]
                                  for e in nav_entries),
                  "rounds": sum(e["rounds"] for e in nav_entries),
                  "replenished": sum(e["replenished"]
                                     for e in nav_entries)}
        report["nav"] = nav_entries
        report["nav_totals"] = totals
    keyed_rec["suffix_commits"] = (keyed_rec["suffix"] or {}).get(
        "suffix_commits", 0)
    keyed_rec["session" if session is not None else "routing"] = \
        sess.call_receipt()
    report["keyed"] = keyed_rec
    return report


def _organize_segments_keyed(tlstore, doc_ids=None, budget=None,
                             store_id="tl-sys-docs", t_seg=None,
                             t_leaf=None, t_parent=None,
                             max_leaf_members=None,
                             max_seg_memberships=None, navigator=None,
                             parent_navigator=None, projections=None,
                             profile=None, counters=None, session=None,
                             archive_manifest=False,
                             doc_checkpoint=None):
    """Keyed-backend organize (Closure P §5.2; see organize_segments).

    Ordered windowed target reads, one atomic txn per organized doc,
    R_cat pre-execution gates on leaf (2-call: eligible + full masks)
    and parent legs (rejected docs fail named, committing nothing),
    session routing reuse with committed deltas. P-2:
    explicit-archive-only export plus the bounded
    projection-compaction debt hook (binding bounds, else defaults;
    receipted; never on the ingest path). Reference (non-catalog)
    decisions mirror legacy exactly; catalog decisions match legacy
    under budget. Codex gate C: ORGANIZE_WALL_TRIP_CONSECUTIVE
    consecutive REJECT_CAPACITY doc failures raise RuntimeError
    (store-wide wall; fail the phase fast with cause preserved)
    instead of recording another failed[doc].

    doc_checkpoint (default None): optional per-doc callback for
    the explicit-doc path only -- doc_checkpoint("before", doc)
    before each actual run_doc (False stops before starting the
    next doc), doc_checkpoint("after", doc, failed.get(doc))
    after run_doc returns, outside its exception handler. In
    callback mode an already-organized doc skips run_doc
    commit-free (crash-retry idempotency) while still firing
    both callbacks and reporting organized; in callback mode
    the tripwire is reset before each doc (per-doc-call
    equivalent, so no cross-doc global wall), and a callback
    exception propagates with committed work retained.
    Default None preserves exact caller behavior.
    """
    from tlsys.place import (MAX_LEAF_MEMBERS, MAX_LEAF_PARENTS,
                             MAX_PARENT_CHILDREN, MAX_SEG_MEMBERSHIPS,
                             T_LEAF, T_PARENT, T_SEG_JOIN, decide_leaf,
                             decide_leaf_catalog,
                             decide_leaf_with_navigator,
                             decide_parent,
                             decide_parent_catalog,
                             decide_parent_with_navigator,
                             join_descriptor,
                             leaf_op, member_centroid, overflow_leaf_id,
                             parent_op, seg_leaf_id, seg_parent_id,
                             segment_atoms)
    from tlsys.catalog import (catalog_row_budget,
                               catalog_routing_enabled)
    from tlsys.proj import Projections as _Projections
    from tlsys.store_if import prepare_artifact as _prep
    from tlsys.prodstate import (
        ProducerState, ProducerSession, consume_suffix, gate_decision,
        OverBudgetRejected, REMAINING_SAMPLE, TARGET_WINDOW,
        close_out_keyed_call)
    from tlsys.ingest import (MANIFEST_NAME as _MAN,
                             _keyed_totals_snapshot as _snap,
                             _keyed_totals_delta as _delta)
    import json as _json
    import os as _os
    store = tlstore.store
    manifest = {}
    mpath = _os.path.join(store.root, _MAN)
    if _os.path.isfile(mpath):
        with open(mpath) as f:
            manifest = _json.load(f)
    state, migrec = ProducerState.create_or_migrate(tlstore, manifest)
    keyed_rec = {"migrated": migrec, "suffix": None, "adopted_ops": 0,
                 "rcat_estimates": [], "rcat_estimate_count": 0}
    try:
        sufrec = consume_suffix(tlstore, state)
        keyed_rec["suffix"] = sufrec
        keyed_rec["adopted_ops"] = sufrec["adopted_ops"]
        use_catalog = catalog_routing_enabled(profile)
        if use_catalog and (navigator is not None
                            or parent_navigator is not None):
            raise ValueError(
                "organize: catalog routing does not compose with "
                "navigator legs")
        if session is not None and use_catalog:
            from tlsys.ingest import \
                _check_session_profile as _check_sess
            _check_sess(session, profile, "organize")
        explicit = doc_ids is not None
        if doc_checkpoint is not None and not explicit:
            raise ValueError("organize: doc_checkpoint needs explicit "
                             "doc_ids (no windowed-cursor support)")
        if explicit:
            for d in doc_ids:
                if state.get_doc(d) is None:
                    raise ValueError(
                        f"organize: doc {d!r} not acknowledged in "
                        "manifest")
            exp_targets = list(doc_ids) if budget is None \
                else list(doc_ids)[:budget]
        t_s = T_SEG_JOIN if t_seg is None else t_seg
        t_l = T_LEAF if t_leaf is None else t_leaf
        t_p = T_PARENT if t_parent is None else t_parent
        cap_leaf = MAX_LEAF_MEMBERS if max_leaf_members is None \
            else max_leaf_members
        cap_mem = MAX_SEG_MEMBERSHIPS if max_seg_memberships is None \
            else max_seg_memberships
        prep = lambda bb, sid: _prep(store, bb, sid)  # noqa: E731
        own_proj = projections is None
        proj = _Projections.cached(tlstore) if own_proj \
            else projections
        catchup = proj.update(tlstore)
        retired = set(proj.retired_view())
        sess = None
        if use_catalog:
            sess = session if session is not None \
                else ProducerSession(profile)
            sess.begin_call()
            sess.attach(tlstore, state)
            live_l, live_p, edge, memidx, ovc = sess.ensure_hier(
                proj.hierarchy_view(), proj.frontier)
            leaf_cat = parent_cat = None
            org_dim = None
        else:
            start_view = proj.hierarchy_view()
            live_l = {k: {"members": list(v["members"]),
                          "descriptor": list(v["descriptor"]),
                          "segments": list(v.get("segments", [])),
                          "seq": v.get("seq")}
                      for k, v in start_view["leaves"].items()}
            live_p = {k: {"members": list(v["members"]),
                          "children": list(v.get("children", [])),
                          "descriptor": list(v["descriptor"]),
                          "seq": v.get("seq")}
                      for k, v in start_view["parents"].items()}
            edge = memidx = ovc = None
            leaf_cat = parent_cat = None
            org_dim = None
        start_lids = set(live_l)
        start_pids = set(live_p)
        rcat = catalog_row_budget(profile) if use_catalog else None
        rejected = []
        catch = {"decisions": 0, "max_rows": 0, "ties": [],
                 "over_budget": False, "max_exec_rows": 0,
                 "_exec_seen": None}

        def _note_estimate(doc_id, leg, est):
            keyed_rec["rcat_estimate_count"] += 1
            if len(keyed_rec["rcat_estimates"]) < 64:
                keyed_rec["rcat_estimates"].append(
                    {"doc": doc_id, "leg": leg, "estimate": est})

        def _harvest_cstats(stats):
            catch["decisions"] += 1
            rows = stats.get("catalog_rows", 0)
            if rows > catch["max_rows"]:
                catch["max_rows"] = rows
            exec_now = ((leaf_cat.total_executed_rows
                         if leaf_cat is not None else 0)
                        + (parent_cat.total_executed_rows
                           if parent_cat is not None else 0))
            exec_rows = exec_now - catch["_exec_seen"]
            catch["_exec_seen"] = exec_now
            if exec_rows > catch["max_exec_rows"]:
                catch["max_exec_rows"] = exec_rows
            if stats.get("catalog_ties") and len(catch["ties"]) < 16:
                catch["ties"].append(stats["catalog_ties"])
            if stats.get("catalog_budget_exceeded"):
                catch["over_budget"] = True

        tots0 = {}

        def _ensure_cats(dim):
            nonlocal leaf_cat, parent_cat, org_dim
            if leaf_cat is not None:
                return
            org_dim = dim
            leaf_cat, parent_cat = sess.hier_catalogs(dim)
            # Seed per-call totals + watermark at first catalog use
            # (fresh/restored cats start at 0; warm session cats carry
            # prior totals, so the seed is the call baseline).
            tots0["leaf"] = _snap(leaf_cat)
            tots0["parent"] = _snap(parent_cat)
            if catch["_exec_seen"] is None:
                catch["_exec_seen"] = leaf_cat.total_executed_rows \
                    + parent_cat.total_executed_rows

        def _gate_leaf(doc_id, six):
            rows_e = int(leaf_cat.mask_lt(cap_leaf).sum())
            rows_f = int(leaf_cat.mask_ge(cap_leaf).sum())
            return gate_decision(
                "leaf", leaf_cat.n, leaf_cat.dim,
                [rows_e, rows_f], [cap_mem, leaf_cat.n], rcat,
                f"organize-leaf:{doc_id}:{six}")

        def _gate_parent(new_lid):
            rows_p = int(parent_cat.mask_lt(
                MAX_PARENT_CHILDREN).sum())
            return gate_decision(
                "parent", parent_cat.n, parent_cat.dim, [rows_p],
                [MAX_LEAF_PARENTS], rcat,
                f"organize-parent:{new_lid}")

        def _rebuild_indexes():
            nonlocal leaf_cat, parent_cat, edge, memidx, ovc, live_l
            nonlocal live_p
            # Failure-path-only resync after mid-doc committed batches
            # (exceptional: commit failures): drop the leg and rebuild
            # from current views (receipted full pass).
            proj.update(tlstore)
            sess.drop_leg("hier")
            live_l, live_p, edge, memidx, ovc = sess.ensure_hier(
                proj.hierarchy_view(), proj.frontier)
            leaf_cat, parent_cat = sess.hier_catalogs(org_dim)
            if "leaf" not in tots0:
                tots0["leaf"] = _snap(leaf_cat)
                tots0["parent"] = _snap(parent_cat)

        unorganized_before = state.unorganized_count()
        organized, failed = [], {}
        wall_trip = CapacityTripwire()
        retired_skipped = []
        nav_entries = []
        n_leaf_ops = n_parent_ops = n_commits = 0
        max_batch = 0
        attempted = 0
        churn = {"leaf_superseded": 0, "leaf_minted": 0,
                 "parent_superseded": 0, "parent_minted": 0}
        emitted_ids = set()

        def run_doc(doc_id):
            nonlocal n_leaf_ops, n_parent_ops, n_commits, max_batch
            nonlocal attempted, live_l, live_p, edge, memidx, ovc
            nonlocal leaf_cat, parent_cat, org_dim
            if doc_id in retired:
                retired_skipped.append(doc_id)
                return
            attempted += 1
            cats_armed = False
            if use_catalog:
                live_l.begin_doc()
                live_p.begin_doc()
                edge.begin_doc()
                memidx.begin_doc()
                ovc.begin_doc()
                if leaf_cat is not None:
                    leaf_cat.begin_doc()
                    parent_cat.begin_doc()
                    cats_armed = True
            else:
                snap_l, snap_p = dict(live_l), dict(live_p)
            try:
                rows = proj.doc_rows(doc_id)
            except RuntimeError as e:
                failed[doc_id] = str(e)
                return
            aids = [r[0] for r in rows]
            vecs = [r[1] for r in rows]
            vec_of = dict(zip(aids, vecs))
            if use_catalog and vecs:
                _ensure_cats(len(vecs[0]))
                if not cats_armed:
                    # Freshly created mid-doc: arm so the failure
                    # paths below can roll back (legacy leaves fresh
                    # cats unarmed -- a latent rollback crash -- so
                    # the keyed path arms explicitly).
                    leaf_cat.begin_doc()
                    parent_cat.begin_doc()
                    cats_armed = True
            ops = []
            n_leaf = 0

            def _churn(hid, is_leaf):
                if hid in emitted_ids:
                    key = "leaf_superseded" if is_leaf \
                        else "parent_superseded"
                elif hid in (start_lids if is_leaf else start_pids):
                    key = "leaf_superseded" if is_leaf \
                        else "parent_superseded"
                else:
                    key = "leaf_minted" if is_leaf else "parent_minted"
                churn[key] += 1
                emitted_ids.add(hid)

            def _emit_leaf(lid, members, desc, segrecs):
                ops.append(leaf_op(lid, members, desc, store_id, prep,
                                   segments=segrecs))
                live_l[lid] = {"members": list(members),
                               "descriptor": list(desc),
                               "segments": list(segrecs), "seq": None}
                if use_catalog:
                    leaf_cat.upsert(lid, desc, len(members))
                    sess.note_dirty("hier")
                _churn(lid, True)

            def _republish_parents(child_lid, fresh_aids):
                if use_catalog:
                    pids = edge.parents_of(child_lid)
                else:
                    pids = sorted(live_p)
                for pid in pids:
                    par = live_p[pid]
                    if child_lid not in par["children"]:
                        continue
                    if use_catalog:
                        have = memidx.union_of(pid)
                    else:
                        have = set(par["members"])
                    add = [a for a in fresh_aids if a not in have]
                    if not add:
                        continue
                    try:
                        avecs = [vec_of[a] for a in add]
                    except KeyError:
                        raise RuntimeError(
                            f"organize: doc {doc_id!r}: parent {pid!r} "
                            "needs vectors outside this doc (foreign "
                            "leaf version; refusing half-update)")
                    members = par["members"] + add
                    desc = join_descriptor(par["descriptor"],
                                           len(par["members"]), avecs)
                    ops.append(parent_op(pid, par["children"], members,
                                           desc, store_id, prep))
                    live_p[pid] = {"members": members,
                                   "children": list(par["children"]),
                                   "descriptor": desc, "seq": None}
                    if use_catalog:
                        parent_cat.upsert(pid, desc,
                                          len(par["children"]))
                        for _a in add:
                            memidx.add(pid, _a)
                        sess.note_dirty("hier")
                    _churn(pid, False)

            def _attach_leaf(new_lid, new_desc, new_aids, preferred):
                attached = []
                cands = [p for p in preferred if p in live_p]
                if use_catalog:
                    est = _gate_parent(new_lid)
                    _note_estimate(doc_id, "parent", est)
                    pstats = {}
                    decided = decide_parent_catalog(
                        new_desc, parent_cat, t_parent=t_p,
                        stats=pstats, counters=counters)
                    _harvest_cstats(pstats)
                elif parent_navigator is None:
                    decided = decide_parent(new_desc, live_p,
                                            t_parent=t_p)
                else:
                    pstats = {}
                    decided = decide_parent_with_navigator(
                        new_desc, live_p, parent_navigator,
                        t_parent=t_p, stats=pstats,
                        path="organize-parent")
                    nav_entries.append({
                        "doc": doc_id, "leaf": new_lid,
                        "leg": "parent",
                        "joins": list(decided),
                        "discovered": pstats["nav_discovered"],
                        "visited": pstats["scored"]
                        + pstats["full_skipped"],
                        "rescored": pstats["scored"],
                        "rounds": pstats["nav_rounds"],
                        "replenished": pstats["nav_replenished"],
                        "changed_ids": pstats["nav_changed_ids"]})
                for pid in decided:
                    if pid not in cands:
                        cands.append(pid)
                for pid in cands:
                    if len(attached) >= MAX_LEAF_PARENTS:
                        break
                    par = live_p[pid]
                    if new_lid in par["children"]:
                        continue
                    if len(par["children"]) >= MAX_PARENT_CHILDREN:
                        continue
                    if use_catalog:
                        have = memidx.union_of(pid)
                    else:
                        have = set(par["members"])
                    add = [a for a in new_aids if a not in have]
                    members = par["members"] + add
                    if add:
                        desc = join_descriptor(
                            par["descriptor"], len(par["members"]),
                            [vec_of[a] for a in add])
                    else:
                        desc = list(par["descriptor"])
                    ops.append(parent_op(pid, par["children"] + [new_lid],
                                           members, desc, store_id,
                                           prep))
                    live_p[pid] = {"members": members,
                                   "children": par["children"] + [new_lid],
                                   "descriptor": desc, "seq": None}
                    if use_catalog:
                        parent_cat.upsert(
                            pid, desc, len(par["children"]) + 1)
                        edge.add_edge(pid, new_lid)
                        memidx.ensure(pid)
                        for _a in new_aids:
                            memidx.add(pid, _a)
                        sess.note_dirty("hier")
                    _churn(pid, False)
                    attached.append(pid)
                if not attached:
                    pid = seg_parent_id(new_lid)
                    if pid in live_p and new_lid in live_p[pid][
                            "children"]:
                        return [pid]
                    children = ([new_lid] if pid not in live_p
                                else live_p[pid]["children"] + [new_lid])
                    if use_catalog:
                        have = memidx.union_of(pid) if pid in live_p \
                            else set()
                    else:
                        have = set(live_p[pid]["members"]) \
                            if pid in live_p else set()
                    add = [a for a in new_aids if a not in have]
                    base = live_p[pid] if pid in live_p else None
                    members = (list(base["members"]) if base else []) \
                        + add
                    if base is not None and add:
                        desc = join_descriptor(
                            base["descriptor"], len(base["members"]),
                            [vec_of[a] for a in add])
                    elif base is not None:
                        desc = list(base["descriptor"])
                    else:
                        desc = list(new_desc)
                    ops.append(parent_op(pid, children, members, desc,
                                           store_id, prep))
                    live_p[pid] = {"members": members,
                                   "children": children,
                                   "descriptor": desc, "seq": None}
                    if use_catalog:
                        parent_cat.upsert(pid, desc, len(children))
                        edge.add_edge(pid, new_lid)
                        memidx.ensure(pid)
                        for _a in new_aids:
                            memidx.add(pid, _a)
                        sess.note_dirty("hier")
                    _churn(pid, False)
                    attached.append(pid)
                return attached

            snap_churn = dict(churn)
            snap_emitted = set(emitted_ids)
            committed_any = False
            try:
                for six, seg in enumerate(
                        segment_atoms(aids, vecs, t_join=t_s)):
                    seg_aids = [aids[ix] for ix in seg]
                    seg_vecs = [vecs[ix] for ix in seg]
                    centroid = member_centroid(seg_vecs)
                    segrec = {"doc": doc_id, "aids": list(seg_aids),
                              "spans": [rows[ix][3] for ix in seg],
                              "byte_spans": [rows[ix][4] for ix in seg]}
                    stats = {}
                    if use_catalog:
                        est = _gate_leaf(doc_id, six)
                        _note_estimate(doc_id, "leaf", est)
                        joins = decide_leaf_catalog(
                            centroid, leaf_cat, t_leaf=t_l,
                            max_m=cap_mem, max_members=cap_leaf,
                            stats=stats, counters=counters)
                        _harvest_cstats(stats)
                    elif navigator is None:
                        joins = decide_leaf(
                            centroid, live_l, t_leaf=t_l,
                            max_m=cap_mem, max_members=cap_leaf,
                            stats=stats)
                    else:
                        joins = decide_leaf_with_navigator(
                            centroid, live_l, navigator, t_leaf=t_l,
                            max_m=cap_mem, max_members=cap_leaf,
                            stats=stats, path="organize-leaf")
                        nav_entries.append({
                            "doc": doc_id, "seg": six, "leg": "leaf",
                            "joins": list(joins),
                            "discovered": stats["nav_discovered"],
                            "visited": stats["scored"],
                            "rescored": stats["scored"],
                            "rounds": stats["nav_rounds"],
                            "replenished": stats["nav_replenished"],
                            "changed_ids": stats["nav_changed_ids"]})
                    applied = []
                    for lid in joins:
                        cur = live_l[lid]
                        fresh = [a for a in seg_aids
                                 if a not in set(cur["members"])]
                        if not fresh:
                            continue
                        if len(cur["members"]) + len(fresh) > cap_leaf:
                            continue
                        members = cur["members"] + fresh
                        fvecs = [vec_of[a] for a in fresh]
                        desc = join_descriptor(cur["descriptor"],
                                               len(cur["members"]),
                                               fvecs)
                        _emit_leaf(lid, members, desc,
                                   cur.get("segments", []) + [segrec])
                        applied.append(lid)
                        n_leaf += 1
                        _republish_parents(lid, fresh)
                    if not applied:
                        if stats.get("full_qualifying"):
                            base = stats["full_qualifying"][0]
                            if use_catalog:
                                n = ovc.next_n(base, live_l)
                            else:
                                stem = base + "-ov"
                                n = 1 + sum(1 for k in live_l
                                            if k.startswith(stem))
                            sib = overflow_leaf_id(base, n)
                            _emit_leaf(sib, list(seg_aids),
                                       list(centroid), [segrec])
                            n_leaf += 1
                            if use_catalog:
                                preferred = edge.parents_of(base)
                            else:
                                preferred = sorted(
                                    p for p, v in live_p.items()
                                    if base in v["children"])
                            _attach_leaf(sib, centroid, seg_aids,
                                         preferred)
                        else:
                            lid = seg_leaf_id(doc_id, six)
                            if lid in live_l:
                                cur = live_l[lid]
                                fresh = [a for a in seg_aids
                                         if a not in
                                         set(cur["members"])]
                                if fresh and len(cur["members"]) \
                                        + len(fresh) <= cap_leaf:
                                    members = cur["members"] + fresh
                                    desc = join_descriptor(
                                        cur["descriptor"],
                                        len(cur["members"]),
                                        [vec_of[a] for a in fresh])
                                    _emit_leaf(
                                        lid, members, desc,
                                        cur.get("segments", [])
                                        + [segrec])
                                    n_leaf += 1
                                    _republish_parents(lid, fresh)
                            else:
                                _emit_leaf(lid, list(seg_aids),
                                           list(centroid), [segrec])
                                n_leaf += 1
                                _attach_leaf(lid, centroid, seg_aids,
                                             [])
                op_ids = []
                for lo in range(0, len(ops), SEG_BATCH_OPS):
                    chunk = ops[lo:lo + SEG_BATCH_OPS]
                    max_batch = max(max_batch, len(chunk))
                    results, _info = tlstore.commit_batch(chunk)
                    for r in results:
                        if r.get("status") != "committed":
                            raise RuntimeError(
                                f"organize {format_commit_failure(r)}")
                        op_ids.append(r["op_id"])
                    committed_any = True
                    n_commits += 1
            except OverBudgetRejected as e:
                # The gate fires before any scan and all commits land
                # after the segment loop, so a rejection implies no
                # scan ran and nothing committed: light rollback, no
                # exceptional index resync.
                failed[doc_id] = str(e)
                rejected.append(
                    {"doc": doc_id, "leg": "organize",
                     "reason": str(e), "estimate": e.estimate})
                if use_catalog:
                    live_l.rollback()
                    live_p.rollback()
                    edge.rollback()
                    memidx.rollback()
                    ovc.rollback()
                    if cats_armed:
                        leaf_cat.rollback()
                        parent_cat.rollback()
                churn.clear()
                churn.update(snap_churn)
                emitted_ids.intersection_update(snap_emitted)
                return
            except RuntimeError as e:
                failed[doc_id] = str(e)
                touched = emitted_ids - snap_emitted
                if use_catalog:
                    live_l.rollback()
                    live_p.rollback()
                    edge.rollback()
                    memidx.rollback()
                    ovc.rollback()
                    if cats_armed:
                        leaf_cat.rollback()
                        parent_cat.rollback()
                else:
                    live_l.clear()
                    live_l.update(snap_l)
                    live_p.clear()
                    live_p.update(snap_p)
                churn.clear()
                churn.update(snap_churn)
                emitted_ids.intersection_update(snap_emitted)
                if committed_any:
                    proj.update(tlstore)
                    fresh = proj.hierarchy_view()
                    for hid in touched:
                        if hid in fresh["leaves"]:
                            v = fresh["leaves"][hid]
                            live_l[hid] = {
                                "members": list(v["members"]),
                                "descriptor": list(v["descriptor"]),
                                "segments": list(v.get("segments",
                                                       [])),
                                "seq": v.get("seq")}
                        elif hid in fresh["parents"]:
                            v = fresh["parents"][hid]
                            live_p[hid] = {
                                "members": list(v["members"]),
                                "children": list(
                                    v.get("children", [])),
                                "descriptor": list(v["descriptor"]),
                                "seq": v.get("seq")}
                    if use_catalog:
                        _rebuild_indexes()
                return
            except BaseException:
                # Unexpected (non-RuntimeError) failure may leave
                # uncommitted overlay in session maps with no valid
                # rollback scope: drop the leg so the next use
                # rebuilds from committed truth (receipted). The
                # exception itself propagates unchanged.
                if use_catalog:
                    sess.drop_leg("hier")
                raise
            n_leaf_ops += n_leaf
            n_parent_ops += len(ops) - n_leaf
            op_recs = [{"doc": doc_id, "kind": "seg", "op_id": op,
                        "seq": None} for op in op_ids]
            _b, _e, _mx, _triple = tlstore.pin()
            state.record_flush(op_recs, {},
                               frontier=(_b, _e, _mx, _triple),
                               organized=[doc_id])
            organized.append(doc_id)

        if explicit:
            for doc_id in exp_targets:
                if doc_checkpoint is not None:
                    # Service-callback mode: per-doc-call-equivalent
                    # tripwire (fresh per doc, so no new cross-doc
                    # global wall), then the caller hook before the
                    # actual run_doc. False stops before starting
                    # the next doc; unstarted docs keep no attempts
                    # and no failure entries.
                    wall_trip = CapacityTripwire()
                    if doc_checkpoint("before", doc_id) is False:
                        break
                    if state.is_organized(doc_id):
                        # Crash-retry idempotency (callback path
                        # only): organization already committed
                        # (e.g. SIGKILL after run_doc but before
                        # the service ACK persisted). Skip the
                        # recompute -- re-running would mint
                        # duplicate hierarchy versions -- but keep
                        # the per-doc callbacks, the success note,
                        # and the organized report so the caller
                        # still persists its ACK. Default None
                        # explicit calls still recompute.
                        attempted += 1
                        organized.append(doc_id)
                        wall_trip.note(doc_id, None)
                        doc_checkpoint("after", doc_id,
                                       failed.get(doc_id))
                        continue
                run_doc(doc_id)
                wall_trip.note(doc_id, failed.get(doc_id))
                if doc_checkpoint is not None:
                    doc_checkpoint("after", doc_id,
                                   failed.get(doc_id))
            remaining_ids = [d for d in exp_targets
                             if d not in organized and d not in failed
                             and d not in retired_skipped]
            remaining_count = len(remaining_ids)
        else:
            cursor, budget_left = 0, budget
            while True:
                window = state.unorganized_window(
                    TARGET_WINDOW if budget_left is None
                    else min(TARGET_WINDOW, budget_left), cursor)
                if not window:
                    break
                for doc_id, dseq in window:
                    cursor = dseq
                    run_doc(doc_id)
                    wall_trip.note(doc_id, failed.get(doc_id))
                    if budget_left is not None:
                        budget_left -= 1
                        if budget_left <= 0:
                            break
                if budget_left is not None and budget_left <= 0:
                    break
            # Legacy parity: remaining excludes retired docs (they
            # report via retired_skipped); the count stays exact via
            # the incremental retired-unorganized counter.
            remaining_count = state.unorganized_count() - state.counters().get(
                "retired_unorganized", 0)
            remaining_ids = [d for d, _s in
                             state.unorganized_window(REMAINING_SAMPLE)
                             if not state.is_retired(d)]
        if own_proj:
            commit_catchup = proj.update(tlstore)
            proj.save(tlstore)
        else:
            commit_catchup = None
        if use_catalog:
            if emitted_ids and own_proj:
                sess.leg_sync("hier", proj.hierarchy_view(),
                              emitted_ids, proj.frontier)
            sess.persist(state)
        compact_rec = {"checked": False, "compacted": False}
        if own_proj:
            try:
                compact_rec = _Projections.maybe_compact(
                    tlstore, bounds=_keyed_compact_bounds(state),
                    reason="maintenance-debt-hook")
            except ValueError:
                compact_rec = _Projections.maybe_compact(
                    tlstore, bounds=None,
                    reason="maintenance-debt-hook")
                compact_rec["bounds_fallback"] = True
        keyed_rec["compact"] = compact_rec
        retained = _keyed_retained(state, tlstore, (live_l, live_p))
        _man, arch_rec = close_out_keyed_call(
            state, mpath, archive_manifest=archive_manifest,
            reason="organize")
        keyed_rec["archive"] = arch_rec
        keyed_rec["candidate_version"] = arch_rec[
            "candidate_version"]
    finally:
        state.close()
    if use_catalog and rejected:
        catch["over_budget"] = True
    report = {"organized": organized, "failed": failed,
              "remaining": remaining_ids[:REMAINING_SAMPLE],
              "remaining_count": remaining_count,
              "remaining_truncated": (len(remaining_ids)
                                      > REMAINING_SAMPLE
                                      if explicit else remaining_count
                                      > REMAINING_SAMPLE),
              "retired_skipped": retired_skipped,
              "n_leaf_ops": n_leaf_ops,
              "n_parent_ops": n_parent_ops, "n_commits": n_commits,
              "max_batch_ops": max_batch,
              "catchup": catchup,
              "commit_catchup": commit_catchup,
              "debt": {"unorganized_before": unorganized_before,
                       "organized": len(organized),
                       "failed": len(failed),
                       "remaining": remaining_count,
                       "rejected_over_budget": len(rejected),
                       "backpressured": max(
                           0, unorganized_before - attempted)
                       if not explicit else 0,
                       "budget": budget},
              "churn": dict(churn,
                            minted=churn["leaf_minted"]
                            + churn["parent_minted"],
                            superseded=churn["leaf_superseded"]
                            + churn["parent_superseded"]),
              "retained": retained}
    if use_catalog:
        leaf_tot = _delta(leaf_cat, tots0.get("leaf"))
        parent_tot = _delta(parent_cat, tots0.get("parent"))
        report["catalog"] = {
            "decisions": catch["decisions"],
            "max_rows_per_decision": catch["max_rows"],
            "max_executed_rows_per_decision": catch["max_exec_rows"],
            "over_budget": catch["over_budget"],
            "ties": list(catch["ties"]),
            "rejected": rejected,
            "leaf": leaf_tot, "parent": parent_tot}
    if navigator is not None or parent_navigator is not None:
        totals = {"placements": len(nav_entries),
                  "discovered": sum(e["discovered"]
                                    for e in nav_entries),
                  "visited": sum(e["visited"]
                                 for e in nav_entries),
                  "rescored": sum(e["rescored"]
                                  for e in nav_entries),
                  "rounds": sum(e["rounds"] for e in nav_entries),
                  "replenished": sum(e["replenished"]
                                     for e in nav_entries)}
        report["nav"] = nav_entries
        report["nav_totals"] = totals
    keyed_rec["suffix_commits"] = (keyed_rec["suffix"] or {}).get(
        "suffix_commits", 0)
    if use_catalog:
        keyed_rec["session" if session is not None else "routing"] = \
            sess.call_receipt()
    report["keyed"] = keyed_rec
    return report


def _reconcile_manifest_keyed(tlstore, store_id="tl-sys-docs",
                              archive_manifest=False):
    """Keyed-backend reconcile (Closure P §5.2; see reconcile_manifest).

    Warm sidecar: adopt the pinned suffix only (bounded by new
    commits), recompute backlog placement for suffix-touched docs
    (bounded by touched docs). Missing sidecar: the NAMED cold
    rebuild (create_or_migrate joins committed truth once;
    cold_rebuild receipt). P-2: explicit-archive-only export.
    Idempotent.
    """
    from tlsys.prodstate import (ProducerState, consume_suffix,
                                 sidecar_exists, REMAINING_SAMPLE,
                                 close_out_keyed_call)
    from tlsys.ingest import MANIFEST_NAME as _MAN
    import json as _json
    import os as _os
    store = tlstore.store
    cold = not sidecar_exists(store)
    manifest = {}
    mpath = _os.path.join(store.root, _MAN)
    if _os.path.isfile(mpath):
        with open(mpath) as f:
            manifest = _json.load(f)
    state, migrec = ProducerState.create_or_migrate(
        tlstore, manifest, missing_ok=True)
    try:
        if cold:
            # Named cold rebuild: the migration join already adopted
            # every committed op + recomputed the backlog + stamped
            # the frontier. Recovered = migrated + adopted-touched.
            mig_docs = []
            for doc in manifest:
                if not doc.startswith("_") \
                        and isinstance(manifest[doc], dict):
                    mig_docs.append(doc)
            mig_docs.extend(migrec.get("sourceless", []))
            recovered = sorted(set(mig_docs))
            repaired = migrec.get("adopted_ops", 0)
            sufrec = {"suffix_commits": migrec.get(
                "meta_join_commits", 0), "suffix_artifacts": 0,
                "suffix_bytes": 0, "adopted_ops": repaired,
                "frontier": migrec.get("frontier", 0)}
        else:
            touched = []
            sufrec = consume_suffix(tlstore, state, touched)
            # Backlog recompute (reconcile rule, bounded by touched):
            # acknowledged + committed but never placed and not
            # pending -> pending.
            for doc in sorted(set(touched)):
                e = state.get_doc(doc)
                if e is None or e["xdoc"] or state.is_pending(doc):
                    continue
                if e["atoms"]:
                    state.backlog_add(doc)
            recovered = sorted(set(touched))
            repaired = sufrec["adopted_ops"]
        pending_count = state.pending_count()
        pending_ids = state.pending_sample()
        _man, arch_rec = close_out_keyed_call(
            state, mpath, archive_manifest=archive_manifest,
            reason="reconcile")
    finally:
        state.close()
    return {"recovered_docs": recovered, "repaired_ops": repaired,
            "pending_placement": pending_ids,
            "pending_count": pending_count,
            "pending_truncated": pending_count > REMAINING_SAMPLE,
            "cold_rebuild": cold,
            "keyed": {"migrated": migrec, "suffix": sufrec,
                      "archive": arch_rec,
                      "candidate_version": arch_rec[
                          "candidate_version"]}}
