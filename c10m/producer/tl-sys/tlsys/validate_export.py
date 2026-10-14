"""Reference consumer-side validator for tl-evidence-export/0.2 and /0.3.

Implements the TL-consumer acceptance gates B1/B12
(handoffs/TL-CONSUMER-ACCEPTANCE-CHECKLIST.md): schema label +
per-version atom-scheme pins, pin/frontier/counts consistency,
retry-identity recomputation per tl-sys/EXPORT-SCHEMA.md section
3.3, and refusal of present record qualifiers (contract: record
qualifiers stay absent until RV1).

TL-owned conformance reference only: it judges artifact shape
against the versioned contract. It makes no claim about TRACE
consumption (external-prereq gate stays open).

Deliberately standalone: stdlib + blake3 only, no tlsys imports
and no store access, so a consumer can vendor this file. The
scheme pins are literals from the contract, not the live
producer constants, so the validator judges the artifact even
after the producer revs.

No prints in library code.
"""

import json

try:
    import blake3 as _blake3
except ImportError:  # pragma: no cover
    _blake3 = None

# Per-version atom-scheme pins (checklist section A). Literals on
# purpose: the validator pins the contract, not current code.
SCHEME_PINS = {
    "tl-evidence-export/0.2": "tlsys-v1-occurrence",
    "tl-evidence-export/0.3": "tlsys-v2-revision",
}

# Envelope absent keys required in both versions (0.2 carries extra
# A1/A2/A3 keys; the block is variable-keyed per section 10).
REQUIRED_ABSENT_KEYS = (
    "retirement", "qualifiers", "relations", "valid_time", "archive")

IMPORTABLE = "IMPORTABLE"
REFUSED = "REFUSED"


def is_absent(node):
    """True iff node is a well-formed absent marker."""
    return (isinstance(node, dict) and node.get("status") == "absent"
            and isinstance(node.get("reason"), str)
            and len(node["reason"]) > 0)


def _is_int(x):
    return type(x) is int


def _is_hex64(s):
    if not isinstance(s, str) or len(s) != 64:
        return False
    try:
        int(s, 16)
    except ValueError:
        return False
    return True


def canonical_preimage_bytes(export_schema, producer, pinned_triple,
                             counts, n_omissions, n_errors):
    """Byte-exact section-3.3 preimage (independent mirror).

    Arguments are plain values, not an export dict, so callers (and
    tests) can recompute the id without trusting the artifact.
    """
    obj = {
        "export_schema": export_schema,
        "producer": {"spec_session": producer["spec_session"],
                     "candidate_rev": producer["candidate_rev"],
                     "candidate_approval":
                         producer["candidate_approval"],
                     "atom_scheme": producer["atom_scheme"]},
        "pinned_triple": pinned_triple,
        "counts": dict(counts),
        "omissions": n_omissions,
        "errors": n_errors,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def recompute_export_id(export_schema, producer, pinned_triple,
                        counts, n_omissions, n_errors):
    """Deterministic export_id per section 3.3 (no silent hash swap)."""
    if _blake3 is None:
        raise RuntimeError(
            "blake3 required; refusing silent hash swap")
    return "blake3:" + _blake3.blake3(
        canonical_preimage_bytes(export_schema, producer,
                                 pinned_triple, counts,
                                 n_omissions, n_errors)).hexdigest()


def validate_export(exp):
    """Judge one parsed export dict.

    Returns {"verdict": IMPORTABLE|REFUSED, "problems": [...],
    "identity": {...}}. Every refusal carries at least one
    "scope: detail" problem; identity is best-effort (None where
    the artifact does not supply the field).
    """
    problems = []

    def bad(scope, detail):
        problems.append(f"{scope}: {detail}")

    if not isinstance(exp, dict):
        return {"verdict": REFUSED,
                "problems": ["envelope: not an object"],
                "identity": _identity(None)}
    schema = exp.get("export_schema")
    pin = SCHEME_PINS.get(schema)
    if pin is None:
        bad("schema", f"unsupported {schema!r}; want one of "
                      f"{sorted(SCHEME_PINS)}")

    producer = exp.get("producer")
    if not isinstance(producer, dict):
        bad("producer", "missing or not an object")
        producer = {}
    else:
        for key in ("spec_session", "candidate_rev",
                    "candidate_approval", "atom_scheme"):
            if not isinstance(producer.get(key), str):
                bad("producer", f"{key} missing or not a string")
        if pin is not None and producer.get("atom_scheme") != pin:
            bad("producer", f"atom_scheme "
                            f"{producer.get('atom_scheme')!r} != {pin!r} "
                            f"pinned for {schema}")

    pg = exp.get("pinned_generation")
    triple = None
    if not isinstance(pg, dict):
        bad("pin", "pinned_generation missing or not an object")
    else:
        birth, epoch, seq = (pg.get("birth"), pg.get("epoch"),
                             pg.get("seq"))
        triple = pg.get("triple")
        if not isinstance(birth, str) or not _is_int(epoch) \
                or not _is_int(seq) or not isinstance(triple, str):
            bad("pin", "birth/epoch/seq/triple ill-typed "
                       f"{pg!r}")
        elif triple != f"{birth}:{epoch}:{seq}":
            bad("pin", f"triple {triple!r} != "
                       f"{birth}:{epoch}:{seq}")

    counts = exp.get("counts")
    if not isinstance(counts, dict):
        bad("counts", "missing or not an object")
        counts = {}
    else:
        for key in ("atoms", "holons", "entries", "omitted"):
            if not _is_int(counts.get(key)) or counts[key] < 0:
                bad("counts", f"{key} missing or not a "
                              f"non-negative int")

    records = exp.get("records")
    if not isinstance(records, list):
        bad("records", "missing or not a list")
        records = None
    holons = exp.get("holons")
    if not isinstance(holons, list):
        bad("holons", "missing or not a list")
        holons = None
    if records is not None and counts.get("atoms") != len(records):
        bad("counts", f"atoms {counts.get('atoms')} != "
                      f"len(records) {len(records)}")
    if holons is not None and counts.get("holons") != len(holons):
        bad("counts", f"holons {counts.get('holons')} != "
                      f"len(holons) {len(holons)}")
    if records is not None and counts.get("entries") != len(records):
        bad("counts", f"entries {counts.get('entries')} != "
                      f"len(records) {len(records)}")

    fr = exp.get("coverage_frontier")
    if not isinstance(fr, dict):
        bad("frontier", "coverage_frontier missing or not an object")
    else:
        if triple is not None and fr.get("pinned_triple") != triple:
            bad("frontier", f"pinned_triple "
                            f"{fr.get('pinned_triple')!r} != {triple!r}")
        if isinstance(pg, dict):
            for key, pg_key in (("birth", "birth"), ("epoch", "epoch"),
                                ("max_seq", "seq")):
                if fr.get(key) != pg.get(pg_key):
                    bad("frontier", f"{key} {fr.get(key)!r} != "
                                    f"pinned {pg.get(pg_key)!r}")
        if fr.get("kinds_covered") != ["ACCEPT_ATOMS"]:
            bad("frontier", f"kinds_covered "
                            f"{fr.get('kinds_covered')!r} != "
                            f"['ACCEPT_ATOMS']")
        if fr.get("counts_ref") != counts:
            bad("frontier", f"counts_ref {fr.get('counts_ref')!r} "
                            f"!= counts {counts!r}")

    omissions = exp.get("omissions")
    if not isinstance(omissions, list):
        bad("omissions", "missing or not a list")
        omissions = None
    else:
        for i, entry in enumerate(omissions):
            if not isinstance(entry, dict) \
                    or not isinstance(entry.get("scope"), str) \
                    or not isinstance(entry.get("cause"), str):
                bad("omissions", f"entry {i} lacks scope/cause "
                                 f"strings")
    errors = exp.get("errors")
    if not isinstance(errors, list):
        bad("errors", "missing or not a list")
        errors = None
    else:
        for i, entry in enumerate(errors):
            if not isinstance(entry, dict) \
                    or not isinstance(entry.get("scope"), str) \
                    or not isinstance(entry.get("cause"), str):
                bad("errors", f"entry {i} lacks scope/cause strings")

    for key in ("dossier", "receipt", "call_trace_summary"):
        if key in exp and not isinstance(exp[key], dict):
            bad("attachments", f"{key} present but not an object")
    receipt = exp.get("receipt") if isinstance(
        exp.get("receipt"), dict) else None
    partials = []
    if receipt is not None:
        partials = receipt.get("partials", [])
        if not isinstance(partials, list):
            bad("receipt", "partials present but not a list")
            partials = []
    if omissions is not None and errors is not None \
            and _is_int(counts.get("omitted")):
        seal_omissions = len(omissions) - len(partials)
        if seal_omissions < 0:
            bad("omissions", f"receipt carries {len(partials)} "
                             f"partials but envelope lists "
                             f"{len(omissions)} omissions")
        elif counts["omitted"] != seal_omissions + len(errors):
            bad("counts", f"omitted {counts['omitted']} != seal "
                          f"omissions {seal_omissions} + errors "
                          f"{len(errors)}")
        for p in partials:
            if p not in omissions:
                bad("omissions", f"receipt partial {p!r} not "
                                 f"carried verbatim in omissions")
                break

    rty = exp.get("retry_identity")
    if not isinstance(rty, dict):
        bad("retry_identity", "missing or not an object")
    else:
        if rty.get("producer_attempt") != 1:
            bad("retry_identity", f"producer_attempt "
                                  f"{rty.get('producer_attempt')!r} "
                                  f"!= 1")
        export_id = rty.get("export_id")
        if not isinstance(export_id, str) \
                or not export_id.startswith("blake3:") \
                or not _is_hex64(export_id[len("blake3:"):]):
            bad("retry_identity", f"export_id {export_id!r} not "
                                  f"'blake3:' + 64 hex")
        elif pin is not None and triple is not None \
                and omissions is not None and errors is not None \
                and isinstance(counts, dict) \
                and all(_is_int(counts.get(k))
                        for k in ("atoms", "holons", "entries",
                                  "omitted")) \
                and all(isinstance(producer.get(k), str)
                        for k in ("spec_session", "candidate_rev",
                                  "candidate_approval",
                                  "atom_scheme")):
            try:
                want = recompute_export_id(
                    schema, producer, triple, counts,
                    len(omissions) - len(partials), len(errors))
            except (KeyError, TypeError) as exc:
                bad("retry_identity", f"preimage unbuildable: {exc}")
            else:
                if export_id != want:
                    bad("retry_identity", f"export_id {export_id} != "
                                          f"recomputed {want}")

    absent = exp.get("absent")
    if not isinstance(absent, dict):
        bad("absent", "envelope absent block missing or not an "
                      "object")
    else:
        for key in REQUIRED_ABSENT_KEYS:
            if not is_absent(absent.get(key)):
                bad("absent", f"{key} missing or not an absent "
                              f"marker")

    if records is not None:
        for i, rec in enumerate(records):
            _check_record(rec, i, pin, triple, schema, bad)
    if holons is not None:
        for i, hol in enumerate(holons):
            _check_holon(hol, i, pin, triple, bad)

    completeness = exp.get("completeness")
    status = None
    if receipt is not None:
        execution = receipt.get("execution")
        if isinstance(execution, dict):
            status = execution.get("status")
    if status == "bounded-incomplete":
        if completeness != "bounded-incomplete":
            bad("completeness", "receipt execution is "
                                "bounded-incomplete but envelope "
                                f"completeness is {completeness!r}")
    elif completeness != "complete":
        bad("completeness", f"{completeness!r} without a "
                            f"bounded-incomplete receipt")

    verdict = IMPORTABLE if not problems else REFUSED
    return {"verdict": verdict, "problems": problems,
            "identity": _identity(exp)}


def _identity(exp):
    if not isinstance(exp, dict):
        return {"export_schema": None, "atom_scheme": None,
                "pinned_triple": None, "export_id": None,
                "counts": None}
    producer = exp.get("producer")
    pg = exp.get("pinned_generation")
    rty = exp.get("retry_identity")
    return {
        "export_schema": exp.get("export_schema"),
        "atom_scheme": producer.get("atom_scheme")
        if isinstance(producer, dict) else None,
        "pinned_triple": pg.get("triple")
        if isinstance(pg, dict) else None,
        "export_id": rty.get("export_id")
        if isinstance(rty, dict) else None,
        "counts": dict(exp["counts"])
        if isinstance(exp.get("counts"), dict) else None,
    }


def _check_record(rec, i, pin, triple, schema, bad):
    scope = f"record[{i}]"
    if not isinstance(rec, dict):
        bad(scope, "not an object")
        return
    if pin is not None and rec.get("atom_scheme") != pin:
        bad(scope, f"atom_scheme {rec.get('atom_scheme')!r} != "
                   f"{pin!r}")
    if not _is_hex64(rec.get("atom_id", "")):
        bad(scope, f"atom_id {rec.get('atom_id')!r} not 64 hex")
    if not isinstance(rec.get("doc_id"), str):
        bad(scope, "doc_id missing or not a string")
    occ = rec.get("occurrence")
    if not isinstance(occ, dict):
        bad(scope, "occurrence missing or not an object")
    else:
        span = occ.get("span")
        if not isinstance(span, list) or len(span) != 2 \
                or not all(_is_int(v) for v in span):
            bad(scope, f"span {span!r} not [int, int]")
        if occ.get("span_unit") != "char":
            bad(scope, f"span_unit {occ.get('span_unit')!r} != "
                       f"'char'")
        for key in ("chunk_ix", "n_chunks"):
            if not _is_int(occ.get(key)):
                bad(scope, f"{key} missing or not an int")
        if schema == "tl-evidence-export/0.3":
            bspan = occ.get("byte_span")
            if not isinstance(bspan, list) or len(bspan) != 2 \
                    or not all(_is_int(v) for v in bspan):
                bad(scope, f"byte_span {bspan!r} not [int, int]")
            src = occ.get("source_revision")
            if not isinstance(src, dict) \
                    or not isinstance(src.get("revision_id"), str):
                bad(scope, "source_revision lacks revision_id "
                           "string")
            acfg = occ.get("atomizer_config")
            if not isinstance(acfg, dict) \
                    or not isinstance(acfg.get("atomizer_config"),
                                      str):
                bad(scope, "atomizer_config lacks atomizer_config "
                           "string")
        elif schema == "tl-evidence-export/0.2":
            for key in ("byte_span", "source_revision",
                        "atomizer_config"):
                if not is_absent(occ.get(key)):
                    bad(scope, f"0.2 path {key} must stay an "
                               f"absent marker, got "
                               f"{occ.get(key)!r}")
    rev = rec.get("revision")
    if not isinstance(rev, dict):
        bad(scope, "revision missing or not an object")
    else:
        for key, typ in (("issuing_generation", str),
                         ("issuing_seq", int),
                         ("issuing_op_id", str),
                         ("resolving_generation", str)):
            val = rev.get(key)
            ok = _is_int(val) if typ is int else isinstance(val, typ)
            if not ok:
                bad(scope, f"revision.{key} missing or ill-typed")
        # Commit-row decided_at verbatim: epoch seconds as a number
        # (bool excluded), matching the producer + test_export.py.
        if isinstance(rev.get("decided_at"), bool) or not isinstance(
                rev.get("decided_at"), (int, float)):
            bad(scope, "revision.decided_at missing or not epoch "
                       "seconds")
        if triple is not None \
                and rev.get("resolving_generation") != triple:
            bad(scope, f"resolving_generation "
                       f"{rev.get('resolving_generation')!r} != "
                       f"{triple!r}")
        if not is_absent(rev.get("retires")):
            bad(scope, "revision.retires must stay absent (A4)")
    pay = rec.get("payload")
    if not isinstance(pay, dict):
        bad(scope, "payload missing or not an object")
    else:
        for key, typ in (("text_artifact", str),
                         ("text_digest", str),
                         ("text_len_bytes", int),
                         ("text_included", bool),
                         ("meta_artifact", str),
                         ("descriptor_included", bool)):
            val = pay.get(key)
            ok = type(val) is typ if typ is bool else (
                _is_int(val) if typ is int else isinstance(val, typ))
            if not ok:
                bad(scope, f"payload.{key} missing or ill-typed")
        if pay.get("text_included") is True \
                and not isinstance(pay.get("text"), str):
            bad(scope, "payload.text_included but text missing")
        if pay.get("text_included") is not True \
                and "text" in pay:
            bad(scope, "payload.text present while "
                       "text_included is not true")
    qual = rec.get("qualifications")
    if not isinstance(qual, dict):
        bad(scope, "qualifications missing or not an object")
    else:
        if not is_absent(qual.get("qualifiers")):
            bad(scope, "present record qualifiers refused per "
                       "contract until RV1")
        if qual.get("integrity") != "intact-verified":
            bad(scope, f"integrity {qual.get('integrity')!r} != "
                       f"'intact-verified'")
        if qual.get("selection") != "selected":
            bad(scope, f"selection {qual.get('selection')!r} != "
                       f"'selected'")
        marks = qual.get("marks")
        if not isinstance(marks, dict) \
                or marks.get("routing_uncertain") is not False \
                or marks.get("outlier") is not False \
                or marks.get("resolution") != "live":
            bad(scope, f"marks {marks!r} != v1 constants")


def _check_holon(hol, i, pin, triple, bad):
    scope = f"holon[{i}]"
    if not isinstance(hol, dict):
        bad(scope, "not an object")
        return
    doc = hol.get("holon")
    if not isinstance(doc, str):
        bad(scope, "holon id missing or not a string")
    if triple is not None and isinstance(doc, str) \
            and hol.get("holon_ref") != f"holon:{doc}:{triple}":
        bad(scope, f"holon_ref {hol.get('holon_ref')!r} != "
                   f"'holon:{doc}:{triple}'")
    if pin is not None and hol.get("atom_scheme") != pin:
        bad(scope, f"atom_scheme {hol.get('atom_scheme')!r} != "
                   f"{pin!r}")
    members = hol.get("members")
    if not isinstance(members, list) \
            or not all(isinstance(m, str) for m in members):
        bad(scope, "members missing or not a string list")
    if not _is_int(hol.get("issuing_seq")):
        bad(scope, "issuing_seq missing or not an int")
    if not isinstance(hol.get("issuing_op_id"), str):
        bad(scope, "issuing_op_id missing or not a string")
    if type(hol.get("descriptor_included")) is not bool:
        bad(scope, "descriptor_included missing or not a bool")
    if not is_absent(hol.get("relations")):
        bad(scope, "relations must stay absent (A6)")
