"""S-02 section 1b relation records (foundation; Narrow-orthogonal).

Status: first dependency-path item for the relations gap
(TL-FULL-COMPLETION-MAP 2026-10-05 item 3; SPEC-MAP named gap 1).
This module is additive: Narrow retrieval never imports it, and
relation commits are invisible to every existing reader (index,
maint, export key on "atom"/"holon" metas; relation metas carry
only "relation" + "rel_scheme"). No cfg flag needed: nothing in
the Narrow path changes whether or not relations are committed.

Contract (sessions/S-02-CLOSURE.md sections 1-2a):
  - Explicit relation records only (source-attributed claims and
    proposed semantic relationships). Organizational connections
    are separately versioned, rebuildable projections -- never
    presented as relation records.
  - Origin is immutable provenance; verification never rewrites
    origin, and support establishment never promotes proposed to
    source-attributed. Status is stable under pinned generations.
  - Flat AND availability: a relation is eligible at the pinned
    generation iff the record version is visible there AND its
    endpoints resolve AND its grounding atoms are live there.
    Eligibility never upgrades status.
  - Negation, conditions, and their scope are preserved in
    qualifiers ("A does not cause B" differs from "A causes
    not-B"). Unrepresentable conditions retain the source
    evidence with the interpretation marked unresolved -- never
    a silently weakened edge.
  - No relation-on-relation grounding; corroboration at the
    assertion level. (Endpoints MAY be relations; grounding
    atoms must be atoms.)
  - Identity: tlsys.identity.relation_id (S-02 section 2a).

Persistence mirrors the holon-marker precedent: relation
records ride as non-consequential ACCEPT_ATOMS ops (no
`retires` key, so approval.classify stays non-consequential)
with payload {"relation": rid, "meta_artifact": ...} and the
full record in the digest-verified meta artifact. Pinned reads
predicate seq<=pinned seq within (birth,epoch); resolution
always evaluates at the resolving query's pinned generation.
"""

import json
import os

from tlsys.identity import (canonical_json_bytes,
                            extractor_config_id, relation_id)
from tlsys.store_if import uuidv7

KIND = "ACCEPT_ATOMS"

# Disclosure-leg read contract (round 8 track A; RELREAD-PROFILE
# section 4.3 rule 5): relation_op stamps disclosure leg "relations"
# on every relation commit, and the indexed read path finds relation
# commits by that marker instead of decoding every artifact. A
# relation meta committed WITHOUT the leg is missed by the fast path
# (no silent third outcome: TL_REL_AUDIT=1 asserts fast == fullscan).
LEG = "relations"

# Env-gated full-scan audit: when "1", read_relations runs the
# fullscan oracle after the fast path and raises on any divergence.
# Default off; conformance tooling only (never a Narrow behavior).
AUDIT_ENV = "TL_REL_AUDIT"

# Env-gated oracle mode: when "1", read_relations IS the fullscan
# oracle (relquery.load skips index material, dossier._lateral takes
# the pre-index loop): exact pre-index behavior for differential
# conformance. Default off; identical output either way (proven by
# the conformance suites, not asserted here).
ORACLE_ENV = "TL_REL_ORACLE"

# Module index cache: (db_path, birth, epoch) -> RelIndex. Bounded
# (FIFO eviction); every serve re-validates against the query pin, so
# a stale entry can only cause a rebuild, never a stale read.
_CACHE_MAX = 8
_INDEX_CACHE = {}

# Relation-record scheme stamp. Committed relation metas carry it;
# readers refuse to mix schemes (rebuild scratch stores; no
# migration). Deliberately distinct from ATOM_SCHEME so existing
# readers (which key on "atom"/"holon" + atom_scheme) skip
# relation metas untouched.
REL_SCHEME = "tlsys-rel-v1"

SOURCE_ATTRIBUTED = "source-attributed"
PROPOSED = "proposed"
STATUSES = (SOURCE_ATTRIBUTED, PROPOSED)


def _check_id32(eid, what):
    try:
        raw = bytes.fromhex(str(eid))
    except ValueError:
        raise ValueError(f"{what} not 64-hex-char: {eid!r}")
    if len(raw) != 32:
        raise ValueError(f"{what} not 32 bytes: {eid!r}")
    return str(eid)


def make_record(rel_type, endpoints, qualifiers, extractor_config,
                status, grounding, claim_text=None,
                interchangeable=False, version=1):
    """Build (but do not commit) one relation record dict.

    endpoints: [(role, id-hex)] ordered, or [id-hex] with
      interchangeable=True (declared by the extractor config).
    qualifiers: canonical-JSON-profile dict; must explicitly
      encode negation/condition/scope where present. Use
      {"unresolved": "<reason>"} (alongside retained evidence
      refs) when a condition is unrepresentable.
    extractor_config: 64-hex config id or effective-behavior
      spec dict (hashed per S-02 section 2a).
    status: "source-attributed" | "proposed" (immutable origin;
      never rewritten by verification or eligibility).
    grounding: [atom-id-hex] flat grounding atoms (relation ids
      rejected here: no relation-on-relation grounding).
    claim_text: optional verbatim source slice the record
      attributes (display only; never an identity input).
    """
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if not isinstance(qualifiers, dict):
        raise ValueError("qualifiers must be a dict")
    if not isinstance(grounding, (list, tuple)) or not grounding:
        raise ValueError("grounding needs >=1 atom id")
    ground = [_check_id32(g, "grounding atom") for g in grounding]
    if isinstance(extractor_config, dict):
        cfg_hex = extractor_config_id(extractor_config)
    else:
        cfg_hex = _check_id32(extractor_config, "extractor_config_id")
    if interchangeable:
        eps = [_check_id32(e, "endpoint") for e in endpoints]
        if not eps:
            raise ValueError("relation needs >=1 endpoint")
    else:
        eps = []
        for item in endpoints:
            role, eid = item
            if not role or not isinstance(role, str):
                raise ValueError("ordered endpoints need role labels")
            eps.append([role, _check_id32(eid, "endpoint")])
        if not eps:
            raise ValueError("relation needs >=1 endpoint")
    rid = relation_id(rel_type, endpoints, qualifiers, cfg_hex,
                      interchangeable=interchangeable)
    rec = {"relation": rid, "rel_scheme": REL_SCHEME,
           "rel_type": rel_type, "endpoints": eps,
           "interchangeable": bool(interchangeable),
           "qualifiers": qualifiers,
           "extractor_config_id": cfg_hex, "status": status,
           "grounding": ground, "version": int(version)}
    if claim_text is not None:
        rec["claim_text"] = str(claim_text)
    return rec


def relation_op(record, store_id, prepare_artifact):
    """One ACCEPT_ATOMS op carrying a relation record (holon-marker
    pattern). Payload carries IDs only; the full record rides in
    the digest-verified meta artifact. The disclosure leg ("relations")
    is read-contract: indexed readers find relation commits by it
    (LEG above); every relation commit must carry it."""
    if record.get("rel_scheme") != REL_SCHEME:
        raise ValueError("relation_op: foreign rel_scheme refused")
    mart = prepare_artifact(json.dumps(record, sort_keys=True).encode(),
                            store_id)
    return {"op_id": uuidv7(),
            "kind": KIND,
            "payload": {"relation": record["relation"],
                        "meta_artifact": mart["artifact_id"]},
            "disclosure": {"leg": "relations",
                           "rel_type": record["rel_type"]},
            "approval_ref": None,
            "artifacts": (mart,)}


def commit_relations(tlstore, records, store_id="tl-sys-docs"):
    """Commit relation records; returns [op_id]. Default-off: only
    runs when the caller explicitly passes records. Raises on any
    non-committed op outcome."""
    from tlsys.store_if import prepare_artifact as _prep
    store = tlstore.store
    prep = lambda bb, sid, _s=store: _prep(_s, bb, sid)  # noqa: E731
    ops = [relation_op(r, store_id, prep) for r in records]
    if not ops:
        return []
    results, _info = tlstore.commit_batch(ops)
    out = []
    for r in results:
        if r.get("status") != "committed":
            raise RuntimeError(f"relation op {r.get('op_id')} "
                               f"{r.get('status')}:{r.get('code')}")
        out.append(r["op_id"])
    return out


def _admit_meta(seq, op_id, body, out):
    """Decode one artifact body; admit it into `out` iff it is a
    relation meta. Shared by the fullscan oracle and the indexed
    path so the guards cannot drift: text/non-meta artifacts skip,
    foreign rel_scheme and id mismatch raise, latest wins."""
    try:
        meta = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return  # text artifact, not meta
    if not isinstance(meta, dict) or "relation" not in meta:
        return  # atoms / holons / xholons: not ours
    if meta.get("rel_scheme") != REL_SCHEME:
        raise ValueError(
            f"op seq {seq}: relation meta scheme "
            f"{meta.get('rel_scheme')!r} != "
            f"{REL_SCHEME!r}: rebuild the scratch store "
            "(no migration)")
    if meta["relation"] != relation_id(
            meta["rel_type"], meta["endpoints"],
            meta["qualifiers"], meta["extractor_config_id"],
            interchangeable=meta.get("interchangeable",
                                     False)):
        raise ValueError(
            f"op seq {seq}: relation id mismatch: stored "
            "id does not recompute from record fields")
    out[meta["relation"]] = {"seq": seq, "op_id": op_id,
                             "record": meta}


def read_relations_fullscan(tlstore, pinned, min_seq=0):
    """Pinned relation records via full O(commits) scan: {rid: {seq,
    op_id, record}}. The byte-source-of-truth oracle for the indexed
    path (RELREAD-PROFILE section 6): fullscan-vs-indexed differential
    conformance keeps this implementation as the reference.

    pinned: (birth, epoch, max_seq, triple) from TLStore.pin().
    Only REL_SCHEME metas decode; foreign schemes raise (no
    silent mixing). Latest version wins on repeat ids.
    """
    birth, epoch, max_seq = pinned[0], pinned[1], pinned[2]
    rows = tlstore.read_commits(birth, epoch, max_seq,
                               kind=KIND, limit=1000000,
                               min_seq=min_seq)
    seqs = [r[0] for r in rows]
    refs = tlstore.pub_refs(seqs)
    by_seq = {r[0]: r for r in rows}
    out = {}
    for seq in seqs:
        op_id = by_seq[seq][1]
        for art_id in refs.get(seq, []):
            arow = tlstore.artifact_row(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id,
                                        expect_digest=arow[4])
            _admit_meta(seq, op_id, body, out)
    return out


def _is_relation_row(row):
    """QW0 prefilter: True iff a read_commits row may carry relation
    metas. Exact-match on the parsed disclosure leg (LEG); a row whose
    disclosure is unparseable or not a dict is KEPT (fail-open: the
    content guards in _admit_meta still decide, so corrupt disclosures
    behave exactly as the fullscan oracle)."""
    try:
        dis = json.loads(row[5])
    except (ValueError, TypeError):
        return True
    if not isinstance(dis, dict):
        return True
    return dis.get("leg") == LEG


def _scan_relation_window(tlstore, birth, epoch, max_seq, min_seq):
    """One window read: {rid: {seq, op_id, record}} for relation-leg
    commits in (min_seq, max_seq]. QW0 (disclosure prefilter) + QW1
    (batched artifact_rows over one connection): reads O(relations)
    artifacts instead of O(artifacts). Same commit-window call as the
    oracle (identical TruncationError behavior); same ascending-seq /
    pub_refs order (identical latest-wins)."""
    rows = tlstore.read_commits(birth, epoch, max_seq,
                               kind=KIND, limit=1000000,
                               min_seq=min_seq)
    kept = [r for r in rows if _is_relation_row(r)]
    seqs = [r[0] for r in kept]
    refs = tlstore.pub_refs(seqs)
    art_ids = []
    for seq in seqs:
        art_ids.extend(refs.get(seq, []))
    arows = tlstore.artifact_rows(art_ids)
    by_seq = {r[0]: r for r in kept}
    out = {}
    for seq in seqs:
        op_id = by_seq[seq][1]
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id,
                                        expect_digest=arow[4])
            _admit_meta(seq, op_id, body, out)
    return out


def _record_endpoints(record):
    """[(endpoint-id, role)] in record order (role None when
    interchangeable)."""
    eps = record.get("endpoints", [])
    if record.get("interchangeable"):
        return [(e, None) for e in eps]
    return [(e[1], e[0]) for e in eps]


class RelIndex:
    """Per-generation indexed relation reads (round 8 track A).

    Built from relation-leg commits only (QW0/QW1 window reads),
    served from memory at the pinned generation:

    - records: {rid: {seq, op_id, record}} (read_relations shape)
    - by_type: {rel_type: sorted [rid]}
    - endpoint_adj: {endpoint-id: sorted [(rid, role)]}
    - qualifiers: {rid: qualifiers} sidecar view
    - opp: {rid: (rel_type, frozenset(endpoints), quals-minus-negated
      canonical bytes, negated)} opposition material for identify_pairs

    Frontier discipline (RELREAD-PROFILE section 4.2/4.3): the index
    covers (birth, epoch) through `frontier` (max consumed seq).
    Same-(birth, epoch) pin advance extends incrementally via min_seq;
    any birth/epoch change (or a backward pin) rebuilds from scratch --
    generations never mix. All orderings are sorted: PYTHONHASHSEED-
    independent (section 6 rule 6).
    """

    def __init__(self, db_path, birth, epoch, frontier, records):
        self.db_path = db_path
        self.birth = birth
        self.epoch = epoch
        self.frontier = frontier
        self.records = records
        self.by_type = {}
        self.endpoint_adj = {}
        self.qualifiers = {}
        self.opp = {}
        for rid in sorted(records):
            self._admit_views(rid, records[rid]["record"])

    def _admit_views(self, rid, rec):
        self.by_type.setdefault(rec.get("rel_type"), [])
        if rid not in self.by_type[rec.get("rel_type")]:
            self.by_type[rec.get("rel_type")].append(rid)
            self.by_type[rec.get("rel_type")].sort()
        for eid, role in _record_endpoints(rec):
            lst = self.endpoint_adj.setdefault(eid, [])
            if (rid, role) not in lst:
                lst.append((rid, role))
                lst.sort()
        quals = rec.get("qualifiers", {}) or {}
        self.qualifiers[rid] = quals
        rest = canonical_json_bytes(
            {k: v for k, v in quals.items() if k != "negated"})
        self.opp[rid] = (rec.get("rel_type"),
                         frozenset(e for e, _r
                                   in _record_endpoints(rec)),
                         rest, bool(quals.get("negated", False)))

    def _extend_views(self, won):
        for rid in sorted(won):
            rec = self.records[rid]["record"]
            self._admit_views(rid, rec)

    def covers(self, pinned):
        """True iff this index serves `pinned` exactly (same store
        generation line, frontier == pinned max_seq)."""
        return (pinned[0] == self.birth and pinned[1] == self.epoch
                and pinned[2] == self.frontier)

    def records_copy(self, min_seq=0):
        """{rid: {seq, op_id, record}} copies for records whose
        winning seq exceeds min_seq. Copies: callers may not mutate
        the cached index through the returned dicts."""
        return {rid: {"seq": item["seq"], "op_id": item["op_id"],
                      "record": json.loads(json.dumps(item["record"]))}
                for rid, item in self.records.items()
                if item["seq"] > min_seq}

    def extend(self, tlstore, pinned):
        """Advance this index to `pinned` (same birth/epoch, larger
        max_seq) by reading only (frontier, max_seq]. Mutates and
        returns self. Raises ValueError if the pin is not a forward
        advance of this index (caller rebuilds instead)."""
        birth, epoch, max_seq = pinned[0], pinned[1], pinned[2]
        if (birth, epoch) != (self.birth, self.epoch):
            raise ValueError("RelIndex.extend: generation change "
                             f"{self.birth}:{self.epoch} -> "
                             f"{birth}:{epoch}: rebuild, never mix")
        if max_seq < self.frontier:
            raise ValueError("RelIndex.extend: backward pin "
                             f"{max_seq} < frontier {self.frontier}: "
                             "rebuild for older prefixes")
        if max_seq == self.frontier:
            return self
        won = _scan_relation_window(tlstore, birth, epoch, max_seq,
                                    self.frontier)
        for rid, item in won.items():
            self.records[rid] = item  # ascending seqs: latest wins
        self._extend_views(won)
        self.frontier = max_seq
        return self

    @classmethod
    def build(cls, tlstore, pinned):
        """Fresh index for `pinned` (full-prefix relation-leg scan)."""
        birth, epoch, max_seq = pinned[0], pinned[1], pinned[2]
        db_path = os.path.abspath(tlstore.store.db_path)
        records = _scan_relation_window(tlstore, birth, epoch,
                                        max_seq, 0)
        return cls(db_path, birth, epoch, max_seq, records)


def _cache_key(tlstore, pinned):
    return (os.path.abspath(tlstore.store.db_path),
            pinned[0], pinned[1])


def get_index(tlstore, pinned):
    """Serve the RelIndex for `pinned` (module cache, NarrowIndex
    discipline): cache hit at the same frontier serves from memory
    (zero store reads); same-(birth, epoch) pin advance extends
    incrementally; anything else rebuilds. Never serves a foreign
    generation or a newer frontier than the pin."""
    key = _cache_key(tlstore, pinned)
    idx = _INDEX_CACHE.get(key)
    if idx is not None:
        if idx.covers(pinned):
            return idx
        try:
            return idx.extend(tlstore, pinned)
        except ValueError:
            pass  # not a forward advance: rebuild below
    idx = RelIndex.build(tlstore, pinned)
    if len(_INDEX_CACHE) >= _CACHE_MAX:
        _INDEX_CACHE.pop(next(iter(_INDEX_CACHE)))
    _INDEX_CACHE[key] = idx
    return idx


def invalidate_rel_index(tlstore=None):
    """Explicit invalidation: drop cached RelIndex entries (all, or
    just `tlstore`'s). Pin discipline already prevents stale serves;
    this is lifecycle control for tests and cache-bounded operation."""
    if tlstore is None:
        _INDEX_CACHE.clear()
        return
    prefix = os.path.abspath(tlstore.store.db_path)
    for key in [k for k in _INDEX_CACHE if k[0] == prefix]:
        del _INDEX_CACHE[key]


def _canonical_records(items):
    return json.dumps(items, sort_keys=True, default=str)


def read_relations(tlstore, pinned, min_seq=0):
    """Pinned relation records: {rid: {seq, op_id, record}}.

    Indexed fast path (round 8 track A): QW0 disclosure-leg prefilter
    + QW1 batched artifact rows + per-generation RelIndex with
    min_seq/frontier incremental extend. Output is byte-identical to
    read_relations_fullscan (the kept oracle); TL_REL_AUDIT=1 asserts
    that per call. min_seq>0 filters the served prefix to records
    whose winning seq is above min_seq (same result as a min_seq
    oracle scan: a record's winner exceeds min_seq iff its latest
    overall op does). Returned dicts are copies: callers may not
    mutate the cached index through them.

    pinned: (birth, epoch, max_seq, triple) from TLStore.pin().
    Only REL_SCHEME metas decode; foreign schemes raise (no
    silent mixing). Latest version wins on repeat ids.
    TL_REL_ORACLE=1 serves the fullscan oracle instead (exact
    pre-index behavior for differential conformance).
    """
    if os.environ.get(ORACLE_ENV) == "1":
        return read_relations_fullscan(tlstore, pinned,
                                       min_seq=min_seq)
    idx = get_index(tlstore, pinned)
    out = idx.records_copy(min_seq=min_seq)
    if os.environ.get(AUDIT_ENV) == "1":
        oracle = read_relations_fullscan(tlstore, pinned,
                                         min_seq=min_seq)
        if _canonical_records(out) != _canonical_records(oracle):
            raise AssertionError(
                "TL_REL_AUDIT: indexed read diverges from fullscan "
                f"at {pinned[3]} min_seq={min_seq}")
    return out


def eligible(record, live_atoms, visible_relations=frozenset()):
    """Flat-AND-availability eligibility at the pinned generation.

    live_atoms: set of atom ids live at the pin (e.g. from
      NarrowIndex.atoms keys; Narrow has no retirement, so
      committed-at-pin == live).
    visible_relations: set of relation ids visible at the pin
      (endpoints may be relations; grounding may not).
    Returns {"eligible": bool, "status": <unchanged>,
             "reasons": [...], "unresolved": <mark or None>}.
    Status is reported verbatim: eligibility never upgrades
    proposed to source-attributed (or anything else).
    """
    reasons = []
    eps = record.get("endpoints", [])
    if record.get("interchangeable"):
        ep_ids = list(eps)
    else:
        ep_ids = [e[1] for e in eps]
    for eid in ep_ids:
        if eid not in live_atoms and eid not in visible_relations:
            reasons.append(f"endpoint-unresolved:{eid[:16]}")
    for g in record.get("grounding", []):
        if g in visible_relations:
            reasons.append(f"grounding-not-atom:{g[:16]}")
        elif g not in live_atoms:
            reasons.append(f"grounding-not-live:{g[:16]}")
    return {"eligible": not reasons, "status": record.get("status"),
            "reasons": reasons,
            "unresolved": record.get("qualifiers", {}).get(
                "unresolved")}


def endpoint_degrees(records):
    """Pure helper: {endpoint-id: degree} over relation records.

    Future input to Q10.1 hub suppression (still GAP: no query
    path consumes degrees yet). Counts each endpoint once per
    record; records may be raw record dicts or read_relations
    values ({..., "record": rec}).
    """
    deg = {}
    for item in records:
        rec = item.get("record", item)
        eps = rec.get("endpoints", [])
        ids = list(eps) if rec.get("interchangeable") \
            else [e[1] for e in eps]
        for eid in set(ids):
            deg[eid] = deg.get(eid, 0) + 1
    return deg
