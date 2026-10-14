"""Faithful TL evidence exporter: pinned generation -> tl-evidence-export/0.3.

Implements tl-sys/EXPORT-SCHEMA.md EXACTLY, honoring the absent facts
named there: every emitted field traces to a TL store read
(pin, read_commits, pub_refs, artifact_row, read_artifact), a
committed meta artifact, an attached query receipt / call trace, or a
documented deterministic derivation (coverage frontier, retry
identity). Anything else is marked with a uniform {"status":
"absent", "reason": ...} marker -- never synthesized, interpolated,
or default-filled.

Reads only; the exporter never writes to the store and treats export
ids as snapshot evidence, not live handles (consumer read-only rule).
No archive promise: scratch stores follow rebuild-no-migration, so an
export is a point-in-time claim at the pinned triple.

Relation commits (M2-B disclosure): S-02 relation records ride as
ACCEPT_ATOMS ops, so a relation-carrying store reaches this scanner.
Relation metas are recognized and DISCLOSED ONLY -- they emit no
records[]/holons[] entries (0.3 carries no edge shape), raise no
spurious meta-missing errors, and flip the absent.relations marker
from the zero-relation text to a truthful committed count. Stores
without relation commits export byte-identically to before (no
counts key added, legacy absent text kept). A relation op whose own
artifacts fail integrity still withholds fail-closed.

Stdlib + tlsys + blake3 (venv) only. No prints in library code.
"""

import copy
import json
from datetime import datetime, timezone

from tlsys import CANDIDATE_APPROVAL, CANDIDATE_REV, SPEC_SESSION
from tlsys.identity import ATOM_SCHEME, holon_ref

try:
    import blake3 as _blake3
except ImportError:  # pragma: no cover
    _blake3 = None

EXPORT_SCHEMA = "tl-evidence-export/0.3"

KIND = "ACCEPT_ATOMS"


def absent(reason):
    """Uniform absent-fact marker (SEAM.md A1-A10)."""
    return {"status": "absent", "reason": reason}


# Envelope absent block. A1/A2/A3 went present in 0.3 (v2 identity:
# revision_id + atomizer_config + byte_span committed per atom);
# the remaining entries keep their SEAM.md A-number suffixes.
_ABSENT_REASONS = {
    "retirement": (
        "retire effects ride approval-gated commits (payload declares "
        "retires; rows persist the hash only); no tombstone kind [A4]"),
    "qualifiers": (
        "atoms carry no qualifier signals "
        "(receipt flags_not_produced.qualifier_Q12.1) [A5]"),
    "relations": (
        "no S-02 relation records committed; relational shapes are a "
        "named future gap [A6]"),
    "valid_time": (
        "no per-record valid intervals; commits carry decided_at only "
        "[A9]"),
    "archive": (
        "no retention guarantee; scratch store, rebuild-no-migration "
        "policy [A10]"),
}


def envelope_absent_block():
    """Fresh copy of the 5-key envelope absent block (0.3)."""
    return {k: absent(v) for k, v in _ABSENT_REASONS.items()}


class SchemeMismatchError(ValueError):
    """Raised when committed data predates tlsys occurrence identity.

    Carries the partial export in `.export` (with the store /
    scheme-mismatch error entry) and the offending stamp in `.found`.
    """

    def __init__(self, message, export=None, found=None):
        super().__init__(message)
        self.export = export
        self.found = found


def _now_rfc3339():
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _new_export(pinned_triple, birth, epoch, seq):
    return {
        "export_schema": EXPORT_SCHEMA,
        "producer": {"system": "tlsys",
                     "spec_session": SPEC_SESSION,
                     "candidate_rev": CANDIDATE_REV,
                     "candidate_approval": CANDIDATE_APPROVAL,
                     "atom_scheme": ATOM_SCHEME},
        "pinned_generation": {"birth": birth, "epoch": epoch,
                              "seq": seq, "triple": pinned_triple},
        "exported_at": _now_rfc3339(),
        "completeness": "complete",
        "counts": {"atoms": 0, "holons": 0, "entries": 0,
                   "omitted": 0},
        "omissions": [],
        "errors": [],
        "absent": envelope_absent_block(),
        "records": [],
        "holons": [],
    }


def _check_scheme(meta, seq, export):
    """Abort the export if a committed meta mixes identity schemes."""
    if ("atom" in meta or "holon" in meta
            or "retirement" in meta) \
            and meta.get("atom_scheme") != ATOM_SCHEME:
        found = meta.get("atom_scheme")
        export["errors"].append(
            {"scope": "store",
             "cause": f"scheme-mismatch:{found}"})
        raise SchemeMismatchError(
            f"op seq {seq}: meta scheme {found!r} != "
            f"{ATOM_SCHEME!r}: committed data predates tlsys "
            "occurrence identity; rebuild the scratch store (no "
            "migration; see tl-sys/ORGANIZATION-CONFORMANCE.md "
            "section 4)",
            export=export, found=found)


def _canonical_preimage_bytes(export, triple):
    """Canonical bytes hashed into retry_identity.export_id.

    Recipe (byte-exact; mirrored in EXPORT-SCHEMA.md section 3):
      obj = {"export_schema": ..., "producer": {...},
             "pinned_triple": ..., "counts": {...},
             "omissions": <len>, "errors": <len>}
      canonical_bytes = json.dumps(obj, sort_keys=True,
          separators=(",", ":"), ensure_ascii=True).encode("ascii")
    """
    obj = {
        "export_schema": EXPORT_SCHEMA,
        "producer": {"spec_session": SPEC_SESSION,
                     "candidate_rev": CANDIDATE_REV,
                     "candidate_approval": CANDIDATE_APPROVAL,
                     "atom_scheme": ATOM_SCHEME},
        "pinned_triple": triple,
        "counts": dict(export["counts"]),
        "omissions": len(export["omissions"]),
        "errors": len(export["errors"]),
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def _export_id(export, triple):
    if _blake3 is None:
        raise RuntimeError(
            "blake3 required (tl-sys venv); refusing silent hash swap")
    return "blake3:" + _blake3.blake3(
        _canonical_preimage_bytes(export, triple)).hexdigest()


def _seal(export, birth, epoch, mx, triple):
    """Attach coverage_frontier + retry_identity to a finished claim.

    Called once per export, after counts are final and BEFORE caller
    attachments: the frontier/identity cover the store-derived claim
    only, so the same store state yields the same export_id whatever
    dossier/receipt the caller attaches (receipt partials describe
    the backing query, not withheld export records).
    """
    export["coverage_frontier"] = {
        "pinned_triple": triple,
        "birth": birth,
        "epoch": epoch,
        "max_seq": mx,
        "kinds_covered": [KIND],
        "atom_scheme": ATOM_SCHEME,
        "counts_ref": copy.deepcopy(export["counts"]),
    }
    export["retry_identity"] = {
        "export_id": _export_id(export, triple),
        "producer_attempt": 1,
    }


def export_store(tlstore, *, include_text=True,
                 include_descriptors=False, dossier=None,
                 receipt=None, call_trace=None, pinned=None):
    """Export the pinned generation as a tl-evidence-export/0.2 dict.

    Reads via the TLStore seam only (pin, read_commits, pub_refs,
    artifact_row, read_artifact) plus committed meta artifacts.
    `pinned` may be a prior pin() tuple; otherwise the store is
    pinned now. Optional `dossier`, `receipt` (query.py shapes), and
    `call_trace` (a store_if.CallTrace or a plain summary dict) are
    attached verbatim as self-contained deep copies after the
    coverage_frontier / retry_identity seal.
    """
    if pinned is None:
        pinned = tlstore.pin()
    birth, epoch, mx, triple = pinned
    if not birth:
        birth, epoch, mx, triple = "empty", 0, 0, "empty:0:0"
        export = _new_export(triple, birth, epoch, mx)
        _seal(export, birth, epoch, mx, triple)
        _attach(export, dossier, receipt, call_trace)
        return export
    export = _new_export(triple, birth, epoch, mx)

    rows = tlstore.read_commits(birth, epoch, mx, kind=KIND,
                                limit=1000000)
    seqs = [r[0] for r in rows]
    refs = tlstore.pub_refs(seqs)
    by_seq = {r[0]: r for r in rows}

    # Per-seq meta resolution: pub_refs -> digest-verified artifact
    # bytes -> JSON meta (A8: read_commits alone is insufficient).
    # Relation metas disclose only (M2-B): counted, never emitted.
    # Retirement markers (lane-2) resolve in the same scan (no extra
    # reads): emission runs second, so markers retiring earlier
    # records still omit them.
    rel_metas = 0
    rel_ops = 0
    ret_ops = 0
    retired = {}  # doc -> {"op_id", "seq"} latest-wins
    resolved = []  # (seq, op_id, decided_at, meta, meta_art)
    for seq in seqs:
        row = by_seq[seq]
        op_id = row[1]
        decided_at = row[6]
        meta = None
        meta_art = None
        saw_digest_failure = False
        saw_meta_candidate = False
        saw_relation = False
        saw_retirement = False
        for art_id in refs.get(seq, []):
            arow = tlstore.artifact_row(art_id)
            if arow is None:
                continue
            try:
                body = tlstore.read_artifact(
                    art_id, expect_digest=arow[4])
            except (ValueError, OSError):
                # Digest failure on an UNIDENTIFIED artifact: it may be
                # the text artifact (whose corruption surfaces honestly
                # at the candidate-scoped text re-read below) or the
                # meta itself. Remember and keep scanning; aborting
                # here would mis-scope text corruption and depend on
                # artifact order. Never trust failed bytes.
                saw_digest_failure = True
                continue
            try:
                cand = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue  # text artifact, not meta
            if not isinstance(cand, dict):
                continue
            if "atom" in cand and "text_artifact" in cand:
                meta, meta_art = cand, art_id
                break
            if "holon" in cand and "descriptor" in cand:
                meta, meta_art = cand, art_id
                break
            if "relation" in cand:
                # S-02 relation record: disclose, never emit (0.3
                # carries no edge shape). No break: a later
                # atom/holon meta in the same op still wins
                # resolution; every decoded relation meta counts.
                saw_relation = True
                rel_metas += 1
                continue
            ret = cand.get("retirement")
            if isinstance(ret, dict) \
                    and isinstance(ret.get("doc"), str):
                # TL-owned retirement marker: scheme-guarded,
                # recorded (latest-wins), never emitted as a record.
                # No break (same reason as relations).
                _check_scheme(cand, seq, export)
                saw_retirement = True
                retired[ret["doc"]] = {"op_id": op_id, "seq": seq}
                continue
            if "atom" in cand or "holon" in cand:
                # Shape-adjacent but unrecognized: still scheme-guard
                # it (legacy/foreign metas must abort, not slip by).
                _check_scheme(cand, seq, export)
                saw_meta_candidate = True
        if meta is None and (saw_relation or saw_retirement) \
                and not saw_digest_failure \
                and not saw_meta_candidate:
            # Healthy disclosure-only op: disclosed in counts/absent
            # below, not an error, not a withholding.
            if saw_relation and not saw_retirement:
                rel_ops += 1
            elif saw_retirement and not saw_relation:
                ret_ops += 1
            continue
        if meta is None:
            if saw_digest_failure and not saw_meta_candidate:
                # No meta resolvable and some artifact failed
                # integrity: the claim cannot be resolved. Withhold.
                export["omissions"].append(
                    {"scope": f"seq:{seq}",
                     "cause": "integrity-failed:withheld"})
                export["counts"]["omitted"] += 1
                continue
            if saw_meta_candidate:
                # Same-scheme but shape-unrecognized meta: never skip
                # silently; record and withhold.
                export["errors"].append(
                    {"scope": f"seq:{seq}",
                     "cause": "meta-unparseable"})
                export["counts"]["omitted"] += 1
                continue
            export["errors"].append(
                {"scope": f"seq:{seq}", "cause": "meta-missing"})
            export["counts"]["omitted"] += 1
            continue
        _check_scheme(meta, seq, export)
        resolved.append((seq, op_id, decided_at, meta, meta_art))

    withheld_by_doc = {}
    for seq, op_id, decided_at, meta, meta_art in resolved:
        if "atom" in meta:
            if meta.get("doc_id") in retired:
                doc = meta["doc_id"]
                withheld_by_doc[doc] = \
                    withheld_by_doc.get(doc, 0) + 1
                continue
            _emit_atom(export, tlstore, meta, meta_art, seq, op_id,
                       decided_at, birth, epoch, triple,
                       include_text, include_descriptors)
        else:
            hid = meta.get("holon")
            if hid in retired and meta.get("kind") is None:
                # Per-doc holon of a retired doc: excluded (covered
                # by the doc omission entry below; kind-tagged
                # hierarchy entries are never removed).
                continue
            _emit_holon(export, meta, seq, op_id, triple,
                        include_descriptors)

    export["counts"]["atoms"] = len(export["records"])
    export["counts"]["holons"] = len(export["holons"])
    export["counts"]["entries"] = len(export["records"])
    if rel_ops:
        # Conditional keys (dossier trav_on precedent): present
        # only when relation commits exist, so relation-free
        # exports stay byte-identical to the legacy shape.
        export["counts"]["relations"] = rel_metas
        export["absent"]["relations"] = absent(
            f"{rel_metas} S-02 relation records committed in "
            f"{rel_ops} ops; edge records not emitted in 0.3 [A6]")
    if retired:
        # One disclosed omission identity per retired doc, in
        # retiring-seq order (deterministic across reopen/retry).
        for doc in sorted(retired, key=lambda d: retired[d]["seq"]):
            info = retired[doc]
            n_with = withheld_by_doc.get(doc, 0)
            export["omissions"].append(
                {"scope": f"doc:{doc}",
                 "cause": f"retired:{info['op_id']}",
                 "seq": info["seq"], "atoms_withheld": n_with})
            export["counts"]["omitted"] += n_with
        export["counts"]["retired_docs"] = len(retired)
        export["absent"]["retirement"] = absent(
            f"{len(retired)} doc(s) retired in {ret_ops} op(s) via "
            "TL-owned marker metas; per-record retires links not "
            "emitted (A4)")
    _seal(export, birth, epoch, mx, triple)
    _attach(export, dossier, receipt, call_trace)
    return export


def _emit_atom(export, tlstore, meta, meta_art, seq, op_id,
               decided_at, birth, epoch, triple,
               include_text, include_descriptors):
    aid = meta["atom"]
    # Late materialization (Q15.1a): display bytes re-read at export
    # and digest-checked against the committed meta claim.
    try:
        text_bytes = tlstore.read_artifact(
            meta["text_artifact"],
            expect_digest=meta["text_digest"])
    except (ValueError, OSError, KeyError):
        export["omissions"].append(
            {"scope": f"candidate:{aid[:16]}",
             "cause": "integrity-failed:withheld"})
        export["counts"]["omitted"] += 1
        return
    if meta.get("text_len") != len(text_bytes):
        export["omissions"].append(
            {"scope": f"candidate:{aid[:16]}",
             "cause": "integrity-failed:withheld"})
        export["counts"]["omitted"] += 1
        return
    payload = {"text_artifact": meta["text_artifact"],
               "text_digest": meta["text_digest"],
               "text_len_bytes": meta["text_len"],
               "text_included": bool(include_text),
               "meta_artifact": meta_art,
               "descriptor_included": bool(include_descriptors)}
    if include_text:
        payload["text"] = text_bytes.decode("utf-8")
    if include_descriptors:
        payload["descriptor"] = list(meta.get("descriptor", []))
    try:
        byte_span = [meta["byte_span"][0], meta["byte_span"][1]]
        revision_id = meta["revision_id"]
        atomizer_config = meta["atomizer_config"]
    except (KeyError, TypeError, IndexError):
        export["omissions"].append(
            {"scope": f"candidate:{aid[:16]}",
             "cause": "meta-incomplete:withheld"})
        export["counts"]["omitted"] += 1
        return
    export["records"].append({
        "atom_id": aid,
        "atom_scheme": ATOM_SCHEME,
        "doc_id": meta["doc_id"],
        "occurrence": {
            "span": [meta["span"][0], meta["span"][1]],
            "span_unit": "char",
            "byte_span": byte_span,
            "chunk_ix": meta["chunk_ix"],
            "n_chunks": meta["n_chunks"],
            "source_revision": {"revision_id": revision_id},
            "atomizer_config": {"atomizer_config": atomizer_config},
        },
        "revision": {
            "issuing_generation": f"{birth}:{epoch}:{seq}",
            "issuing_seq": seq,
            "issuing_op_id": op_id,
            "resolving_generation": triple,
            "decided_at": decided_at,
            "retires": absent("A4"),
        },
        "payload": payload,
        "qualifications": {
            "qualifiers": absent("A5"),
            "integrity": "intact-verified",
            "selection": "selected",
            "marks": {"routing_uncertain": False,
                      "outlier": False,
                      "resolution": "live"},
        },
    })


def _emit_holon(export, meta, seq, op_id, triple,
                include_descriptors):
    doc = meta["holon"]
    hol = {"holon": doc,
           "holon_ref": holon_ref(doc, triple),
           "atom_scheme": ATOM_SCHEME,
           "members": list(meta["members"]),
           "issuing_seq": seq,
           "issuing_op_id": op_id,
           "descriptor_included": bool(include_descriptors),
           "relations": absent(
               "A6: membership list only; no edge records")}
    if include_descriptors:
        hol["descriptor"] = list(meta.get("descriptor", []))
    export["holons"].append(hol)


def _attach(export, dossier, receipt, call_trace):
    if dossier is not None:
        export["dossier"] = copy.deepcopy(dossier)
    if receipt is not None:
        export["receipt"] = copy.deepcopy(receipt)
        partials = receipt.get("partials", []) or []
        # omissions[] carries receipt partials verbatim; they
        # describe the backing query, not withheld export records,
        # so counts.omitted (exporter withholdings) is untouched.
        export["omissions"].extend(copy.deepcopy(partials))
        if receipt.get("execution", {}).get("status") \
                == "bounded-incomplete":
            export["completeness"] = "bounded-incomplete"
    if call_trace is not None:
        if hasattr(call_trace, "summary") \
                and callable(call_trace.summary):
            summary = call_trace.summary()
        else:
            summary = dict(call_trace)
        export["call_trace_summary"] = {
            "candidate_rev": CANDIDATE_REV,
            "summary": copy.deepcopy(summary),
        }
