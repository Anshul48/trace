"""Ingest: docs -> chunks (atoms) -> ACCEPT_ATOMS commits -> per-doc holons.

Contract:
  ACCEPT_ATOMS is a non-consequential kind (approval.classify): no
  approval_ref required unless payload carries `retires` (never here).
  op_id is a FRESH uuidv7 per op (replay P5 requires parseable uuidv7
  within the horizon window -- content-derived IDs would expire).
  Re-ingest idempotency therefore lives in an ingest-side manifest
  (doc_id -> committed op_ids), not in op_id determinism: committed
  docs are skipped, never re-minted.
  Atom bytes ride as artifacts (P2: durable before the referencing
  commit); payload carries IDs/spans only -- never bare-span-hash
  verification (Q15.1(c) refusal).
  Holon membership + centroid descriptor are THEMSELVES committed
  (ACCEPT_ATOMS, holon marker) so the index reads committed data only.

Chunking (frozen default; protocol may pin otherwise):
  whitespace tokens, 200/chunk, 50-token overlap.

Progress (R6-B repair): every manifest doc entry carries status
(started | partial | source-complete | placement-pending),
source_sha256 + revision_id + n_chunks_expected. Completion is
NEVER bare manifest-key presence: skip requires a source-durable
status with matching declared coverage. Interrupted docs resume
the SAME revision (missing chunks only, reconciled against
committed truth); changed bytes are refused; recovered
(sourceless) entries must reproduce the committed chunk evidence
before they are trusted (adopt) or skipped, else refused.

Journal (R6-B, flag-gated): progress_journal=True appends
per-flush progress to ingest_progress.jsonl (fsync per record)
and saves the manifest once at call end. Same committed op
stream, same batching (10-op contract), same Narrow behavior.

Recovery edges (R8-C): UNKNOWN-origin PARTIAL revisions REFUSE
same-revision completion (re-ingest under a new doc_id) -- a
same-count suffix substitution is indistinguishable from the
original bytes, so only full pre-existing coverage may skip;
and a torn journal tail is truncated to the last validated
boundary (torn bytes preserved aside) BEFORE the first append
of a call, so append never builds on a torn fragment.
"""

import json
import os

from tlsys.identity import ATOM_SCHEME, atom_id, holon_ref
from tlsys.store_if import uuidv7

KIND = "ACCEPT_ATOMS"
CHUNK_TOKENS = 200
CHUNK_OVERLAP = 50
BATCH_OPS = 10


def chunk_text(text):
    """[(char_start, char_end, chunk_text, byte_start, byte_end)].

    Whitespace-token windows. Byte offsets address the immutable
    source revision bytes (S-02: nonempty half-open UTF-8 byte spans,
    0 <= start < end <= revision_byte_length). Chunk text is the
    EXACT source slice (verbatim, never rewritten or normalized).
    Boundaries fall on token edges (whitespace-adjacent), which are
    always UTF-8 code-point boundaries; verified by construction
    below (a boundary inside a code point raises instead of silently
    splitting bytes).
    """
    toks = []
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        j = i
        while j < n and not text[j].isspace():
            j += 1
        toks.append((i, j))
        i = j
    if not toks:
        return []
    raw = text.encode("utf-8")
    # char offset -> byte offset map (ASCII whitespace edges keep this
    # exact; map is linear and built once per doc).
    byte_at = [0] * (n + 1)
    b = 0
    for ix, ch in enumerate(text):
        byte_at[ix] = b
        b += len(ch.encode("utf-8"))
    byte_at[n] = b
    out = []
    step = CHUNK_TOKENS - CHUNK_OVERLAP
    for s in range(0, len(toks), step):
        e = min(s + CHUNK_TOKENS, len(toks))
        c0, _ = toks[s]
        _, c1 = toks[e - 1]
        b0, b1 = byte_at[c0], byte_at[c1]
        ctext = text[c0:c1]
        if not (0 <= b0 < b1 <= len(raw)):
            raise ValueError(
                f"chunk byte span [{b0},{b1}) outside revision "
                f"length {len(raw)}")
        if raw[b0:b1].decode("utf-8") != ctext:
            raise ValueError(
                "chunk boundary splits a UTF-8 code point: "
                f"chars [{c0},{c1}) -> bytes [{b0},{b1})")
        out.append((c0, c1, ctext, b0, b1))
        if e >= len(toks):
            break
    return out


def atom_op(doc_id, ix, n_chunks, span, text_bytes, descriptor,
            store_id, prepare_artifact, revision_id,
            atomizer_config=None):
    """span: (char_start, char_end, byte_start, byte_end). revision_id:
    source-revision UUID (S-02: identifies a revision of a source, not
    a text hash). Both join the v2 preimage with the atomizer config.
    """
    from tlsys.identity import ATOMIZER_CONFIG as _ACFG
    cfg = _ACFG if atomizer_config is None else atomizer_config
    c0, c1, b0, b1 = span
    aid = atom_id(text_bytes, doc_id, (b0, b1), revision_id, cfg)
    tart = prepare_artifact(text_bytes, store_id)
    meta = {"atom": aid, "atom_scheme": ATOM_SCHEME,
            "doc_id": doc_id, "chunk_ix": ix,
            "n_chunks": n_chunks, "span": [c0, c1],
            "byte_span": [b0, b1],
            "revision_id": str(revision_id),
            "atomizer_config": cfg,
            "text_len": len(text_bytes),
            "text_artifact": tart["artifact_id"],
            "text_digest": tart["digest"],
            "descriptor": descriptor}
    mart = prepare_artifact(json.dumps(meta, sort_keys=True).encode(),
                            store_id)
    return {"op_id": uuidv7(),
            "kind": KIND,
            "payload": {"atom": aid, "doc_id": doc_id,
                        "meta_artifact": mart["artifact_id"]},
            "disclosure": {"leg": "ingest", "doc_id": doc_id,
                           "chunk_ix": ix},
            "approval_ref": None,
            "artifacts": (tart, mart)}


def holon_op(doc_id, member_aids, descriptor, store_id,
             prepare_artifact):
    meta = {"holon": doc_id, "atom_scheme": ATOM_SCHEME,
            "members": member_aids, "descriptor": descriptor}
    mart = prepare_artifact(json.dumps(meta, sort_keys=True).encode(),
                            store_id)
    return {"op_id": uuidv7(),
            "kind": KIND,
            "payload": {"holon": doc_id,
                        "meta_artifact": mart["artifact_id"]},
            "disclosure": {"leg": "ingest-holon", "doc_id": doc_id},
            "approval_ref": None,
            "artifacts": (mart,)}


MANIFEST_NAME = "ingest_manifest.json"


def _save_manifest(manifest_path, manifest):
    """Atomic manifest persist (tmp + fsync + os.replace).

    A crash leaves the previous complete manifest or the new one,
    never a torn file. The remaining commit-then-crash window (ops
    committed, manifest stale) is closed by
    tlsys.maint.reconcile_manifest, which rebuilds the manifest from
    committed data.

    O-7: compact JSON (no indent). Same parsed content, ~2-3x faster
    dumps and a smaller file (which also speeds every future load);
    the per-flush cadence and journal default are untouched (pinned
    by test_recovery J4 and test_r7a_perf journal-off-by-default).

    P-2: a manifest write means the file is current again, so any
    P-2 stale marker beside it is cleared (missing-ok, OSError-safe;
    legacy flows never create markers and cannot observe this).
    """
    tmp_path = manifest_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(manifest, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, manifest_path)
    from tlsys.prodstate import clear_stale_marker as _clear_stale
    _clear_stale(manifest_path)


def _load_manifest(store):
    path = os.path.join(store.root, MANIFEST_NAME)
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f), path
    return {}, path


# Progress states (R6-B). Persisted per doc entry for crash
# visibility, but ALWAYS re-derived fresh on read: a stale on-disk
# value (e.g. after tlsys.maint.drain_placement_backlog, which does
# not update it) can never certify completion.
P_STARTED = "started"  # revision declared, nothing committed
P_PARTIAL = "partial"  # some ops committed, coverage incomplete
P_SOURCE_COMPLETE = "source-complete"  # all atoms + holon durable
P_PLACEMENT_PENDING = "placement-pending"  # source-complete + backlog
P_SOURCE_DURABLE = (P_SOURCE_COMPLETE, P_PLACEMENT_PENDING)

JOURNAL_NAME = "ingest_progress.jsonl"
TORN_NAME = "ingest_progress.torn"
_JOURNAL_SEQ_KEY = "_journal_seq"


def _backfill_entry(entry):
    entry.setdefault("atoms", [])
    entry.setdefault("xdoc", [])
    entry.setdefault("holon", None)
    return entry


def _derive_status(entry, in_backlog):
    """Structural progress from entry fields (never bare key presence).

    Legacy/recovered entries without n_chunks_expected grandfather:
    holon + atoms counts as source-complete (existing stores keep
    their skip behavior); anything less is partial/started and must
    resume, never skip.
    """
    atoms = entry.get("atoms") or []
    holon = entry.get("holon")
    exp = entry.get("n_chunks_expected")
    if exp is None:
        complete = bool(holon) and len(atoms) > 0
    else:
        complete = bool(holon) and len(atoms) >= exp
    if not complete:
        return P_PARTIAL if (atoms or holon) else P_STARTED
    return P_PLACEMENT_PENDING if in_backlog else P_SOURCE_COMPLETE


def _supplied_chunks(text):
    chunks = chunk_text(text)
    if not chunks:
        # Empty-source marker (same normalization as the commit path).
        chunks = [(0, 0, "", 0, 0)]
    return chunks


def _committed_doc_state(tlstore, doc_id):
    """Committed truth for one doc: atom metas by chunk_ix, the
    per-doc holon meta, and xdoc versions touching the doc.

    R7-A (proposal C(b)): unbounded read via min_seq frontiers
    (read_commits_all) + single-connection batched artifact rows,
    so resume/verify covers the store at any scale with no 1M
    window to fail closed at. Fails closed on any read failure, so
    a resume/verify can never run blind. Identical results to the
    pre-R7-A loop at every scale the old window covered.
    """
    birth, epoch, mx, _triple = tlstore.pin()
    try:
        rows = tlstore.read_commits_all(birth, epoch, mx, kind=KIND)
    except Exception as e:
        raise RuntimeError(
            f"resume/verify for doc {doc_id!r} refused: commit scan "
            f"failed ({e}); coverage cannot be proven") from e
    seqs = [r[0] for r in rows]
    op_of_seq = {r[0]: r[1] for r in rows}
    try:
        refs = tlstore.pub_refs(seqs)
    except Exception as e:
        raise RuntimeError(
            f"resume/verify for doc {doc_id!r} refused: pub_refs "
            f"failed ({e}); coverage cannot be proven") from e
    try:
        arows = tlstore.artifact_rows(
            [a for seq in seqs for a in refs.get(seq, [])])
    except Exception as e:
        raise RuntimeError(
            f"resume/verify for doc {doc_id!r} refused: artifact scan "
            f"failed ({e}); coverage cannot be proven") from e
    by_ix = {}
    holon = None  # (op_id, members)
    xdoc = []  # [(op_id, members)]
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
            if meta.get("atom_scheme") != ATOM_SCHEME:
                continue  # foreign/legacy scheme: refused by readers
            if meta.get("doc_id") == doc_id and "atom" in meta:
                by_ix[meta.get("chunk_ix")] = {
                    "byte_span": tuple(meta.get("byte_span", ())),
                    "text_digest": meta.get("text_digest"),
                    "revision_id": meta.get("revision_id"),
                    "n_chunks": meta.get("n_chunks"),
                    "aid": meta.get("atom"),
                    "op_id": op_of_seq[seq]}
            elif meta.get("holon") == doc_id and "members" in meta:
                holon = (op_of_seq[seq], list(meta.get("members", [])))
            elif isinstance(meta.get("holon"), str) \
                    and meta["holon"].startswith("xdoc-") \
                    and "members" in meta:
                xdoc.append((op_of_seq[seq],
                             list(meta.get("members", []))))
    return {"by_ix": by_ix, "holon": holon, "xdoc": xdoc}


def _verify_chunks_against_committed(chunks, by_ix):
    """True iff the supplied bytes reproduce the committed chunk
    evidence. Committed coverage must be a nonempty ix-prefix
    (ingest commits in chunk order, so anything else is tamper),
    every committed chunk must match its supplied chunk (byte span
    + text digest), and every committed meta must declare the
    supplied chunk count (closes prefix-extension/truncation: the
    committed geometry must equal the supplied geometry, so a
    resume can only fill an uncommitted tail, never rewrite
    history). Used to certify recovered (sourceless) entries.
    """
    import hashlib as _hl
    if not by_ix or set(by_ix) != set(range(len(by_ix))):
        return False
    if len(by_ix) > len(chunks):
        return False
    for ix in range(len(by_ix)):
        (_c0, _c1, ctext, b0, b1) = chunks[ix]
        c = by_ix[ix]
        if c["byte_span"] != (b0, b1):
            return False
        want = "sha256:" + _hl.sha256(
            ctext.encode("utf-8")).hexdigest()
        if c["text_digest"] != want:
            return False
        if c["n_chunks"] != len(chunks):
            return False
    return True


def _journal_path(store):
    return os.path.join(store.root, JOURNAL_NAME)


def _journal_append(jf, record):
    jf.write(json.dumps(record, sort_keys=True) + "\n")
    jf.flush()
    os.fsync(jf.fileno())


def _journal_records(journal_path):
    """Parsed records; tolerates a torn tail (crash mid-append) but
    refuses mid-file corruption."""
    with open(journal_path) as f:
        content = f.read()
    if not content.strip():
        return []
    lines = content.split("\n")
    recs = []
    for lineno, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            recs.append(json.loads(line))
        except ValueError:
            rest = "".join(lines[lineno + 1:]).strip()
            if rest:
                raise RuntimeError(
                    f"progress journal {journal_path}: corrupt record "
                    f"at line {lineno + 1} (mid-file; refusing replay)")
            break  # torn tail only: ignore
    return recs


def _restore_journal_boundary(journal_path):
    """Restore a validated journal boundary before the first append.

    R8-C (b): a torn tail (crash mid-append) is truncated to the
    last complete record BEFORE a call appends -- otherwise the
    first post-restart record is silently swallowed into the torn
    line and the second converts the fragment into fatal mid-file
    corruption refusing all replay. The exact torn bytes are
    preserved aside (TORN_NAME, appended) for forensics; the
    journal itself keeps only validated records. No-op on a clean
    or missing journal (a complete-but-unterminated tail record is
    normalized with its missing newline). Mid-file corruption
    still fails closed.
    """
    if not os.path.isfile(journal_path):
        return None
    with open(journal_path, "rb") as f:
        raw = f.read()
    if not raw.strip():
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise RuntimeError(
            f"progress journal {journal_path}: corrupt record "
            "(non-UTF8 bytes; refusing replay)")
    lines = text.split("\n")
    bad = None
    for lineno, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except ValueError:
            rest = "".join(lines[lineno + 1:]).strip()
            if rest:
                raise RuntimeError(
                    f"progress journal {journal_path}: corrupt record "
                    f"at line {lineno + 1} (mid-file; refusing replay)")
            bad = lineno
            break
    if bad is None:
        if text.endswith("\n"):
            return None
        with open(journal_path, "ab") as f:
            f.write(b"\n")
            f.flush()
            os.fsync(f.fileno())
        return None
    keep_text = "\n".join(lines[:bad])
    if bad > 0:
        keep_text += "\n"
    cut = len(keep_text.encode("utf-8"))
    torn = raw[cut:]
    aside = os.path.join(os.path.dirname(journal_path), TORN_NAME)
    with open(aside, "ab") as f:
        f.write(torn)
        if not torn.endswith(b"\n"):
            f.write(b"\n")
        f.flush()
        os.fsync(f.fileno())
    _fsync_dir(os.path.dirname(journal_path) or ".")
    with open(journal_path, "r+b") as f:
        f.truncate(cut)
        f.flush()
        os.fsync(f.fileno())
    return aside


def _fsync_dir(dir_path):
    """Best-effort directory fsync (R7-A journal hardening: the
    directory entry of a newly created journal must survive a crash
    for the per-record file fsyncs to mean anything). Failures are
    ignored (exotic filesystems may refuse dir fsync); the file
    fsyncs still hold whatever durability the platform offers."""
    try:
        fd = os.open(dir_path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _journal_replay(manifest, journal_path):
    """Fold unapplied journal records into the in-memory manifest
    (idempotent). Always runs at ingest start -- in BOTH modes -- so
    a legacy call after a journal call can never see stale progress.
    Returns the max journal seq seen (None when no journal).

    R7-A hardening: every record must be an object with an integer
    seq, and unapplied seqs must arrive strictly increasing (the
    writer always appends increasing seqs; anything else is
    operator damage or a torn splice and fails closed). The torn
    tail was already dropped by _journal_records.
    """
    if not os.path.isfile(journal_path):
        return None
    recs = _journal_records(journal_path)
    if not recs:
        return None
    applied_from = manifest.get(_JOURNAL_SEQ_KEY, 0)
    max_seq = applied_from
    last_new = None
    for lineno, rec in enumerate(recs):
        if not isinstance(rec, dict):
            raise RuntimeError(
                f"progress journal {journal_path}: corrupt record "
                f"at line {lineno + 1} (not an object; refusing replay)")
        seq = rec.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) \
                or seq < 0:
            raise RuntimeError(
                f"progress journal {journal_path}: corrupt record "
                f"at line {lineno + 1} (bad seq {seq!r}; "
                "refusing replay)")
        max_seq = max(max_seq, seq)
        if seq <= applied_from:
            continue
        if last_new is not None and seq <= last_new:
            raise RuntimeError(
                f"progress journal {journal_path}: seqs not strictly "
                f"increasing at line {lineno + 1} "
                f"({last_new} -> {seq}; refusing replay)")
        last_new = seq
        ev = rec.get("event")
        if ev == "started":
            doc = rec["doc_id"]
            if doc not in manifest:
                manifest[doc] = {
                    "atoms": [], "holon": None, "xdoc": [],
                    "revision_id": rec["revision_id"],
                    "source_sha256": rec["source_sha256"],
                    "revision_len": rec["revision_len"],
                    "n_chunks_expected": rec["n_chunks_expected"],
                    "source_verified": True, "status": P_STARTED}
            elif manifest[doc].get("revision_id") \
                    != rec["revision_id"]:
                raise RuntimeError(
                    "progress journal conflicts with manifest for doc "
                    f"{doc!r} (mixed revisions; operator must resolve)")
        elif ev == "flushed":
            for op in rec.get("ops", []):
                m = _backfill_entry(manifest.setdefault(
                    op["doc"], {"atoms": [], "holon": None,
                               "xdoc": []}))
                if op["kind"] == "atom":
                    if op["op_id"] not in m["atoms"]:
                        m["atoms"].append(op["op_id"])
                elif op["kind"] == "xholon":
                    if op["op_id"] not in m["xdoc"]:
                        m["xdoc"].append(op["op_id"])
                else:
                    m["holon"] = op["op_id"]
            for doc, st in rec.get("statuses", {}).items():
                if doc in manifest and isinstance(manifest[doc], dict):
                    manifest[doc]["status"] = st
        elif ev == "backlog_add":
            pending = manifest.setdefault("_pending_placement", [])
            if rec["doc_id"] not in pending:
                pending.append(rec["doc_id"])
        elif ev == "backlog_del":
            pending = manifest.setdefault("_pending_placement", [])
            if rec["doc_id"] in pending:
                pending.remove(rec["doc_id"])
        elif ev == "adopted":
            m = manifest.get(rec["doc_id"])
            if m is not None and isinstance(m, dict):
                have = m.get("source_sha256")
                if have in (None, "", "UNKNOWN"):
                    m["source_sha256"] = rec["source_sha256"]
                    m["revision_len"] = rec["revision_len"]
                    m["source_verified"] = True
                elif have != rec["source_sha256"]:
                    raise RuntimeError(
                        "progress journal conflicts with manifest for "
                        f"doc {rec['doc_id']!r} (mixed source hashes; "
                        "operator must resolve)")
        # Unknown events: ignore (forward compatibility).
    manifest[_JOURNAL_SEQ_KEY] = max(
        manifest.get(_JOURNAL_SEQ_KEY, 0), max_seq)
    return max(rec.get("seq", 0) for rec in recs)


def ingest_docs(tlstore, docs, embed_texts, store_id="tl-sys-docs",
                place_xdoc=True, place_t=None, place_budget=None,
                progress_journal=False, profile=None, counters=None,
                keyed_state=False, session=None,
                archive_manifest=False):
    """docs: [(doc_id, text)]. embed_texts: [str]->[[float]] (real ST).
    Skips source-durable docs (idempotent re-ingest); resumes
    interrupted docs under their SAME revision (missing chunks only).
    Returns {"n_atoms": new, "n_holons": new, "skipped": [...],
    "resumed": [...], "pinned": triple, "catchup": {...} or None}.
    Raises on any non-committed op outcome.

    place_xdoc: cross-doc placement baseline (tlsys.place). Per doc,
    decided against PRE-doc committed state and committed in the SAME
    batch as the doc's own ops: no new crash window beyond the
    documented manifest/commit one. Doc ids starting with "xdoc-" are
    refused (cross-doc namespace reservation). Placement reads are
    frontier-bounded (M2-C): the xholon window seeds from the
    persisted keyed projection (tlsys.proj; cold call scans once,
    warm calls consume only new commits) and only same-call
    flushed versions arrive through the per-doc min_seq window;
    the "catchup" receipt records the consumption (None when
    place_xdoc=False, which performs no placement reads).

    place_budget: S-03 section 1b foreground budget (max placement
    decisions per call; default PLACE_FOREGROUND_BUDGET). Overflow
    docs are still ingested (acknowledged + retrievable) but their
    placement defers to the manifest backlog
    (manifest["_pending_placement"]), drained explicitly via
    tlsys.maint.drain_placement_backlog. No autonomous worker.

    Progress (R6-B): completion is NEVER bare manifest-key
    presence. Skip requires a source-durable status
    (source-complete | placement-pending) with matching declared
    coverage; anything less resumes the same revision. Recovered
    (sourceless) entries must reproduce the committed chunk
    evidence before they are trusted or skipped, else refused.

    progress_journal: additive flag-gated path (default False =
    legacy persistence). When True, declarations and per-flush
    progress append to ingest_progress.jsonl (fsync per record)
    and the manifest saves once at call end. Identical committed
    op stream, batching, and Narrow behavior.

    profile/counters (C2 Lane O): profile is a Lane G profile dict
    (None = the exact C1 reference path, bit-identical to before).
    When profile["flags"]["organization_catalog_routing"] is true,
    cross-doc decisions route through a row-budgeted exact catalog
    (D2 parity): the committed xholon cache is mirrored
    incrementally into a caller-owned Catalog (O(new versions) per
    doc), the same-batch pending overlay is upserted per decision
    and rolled back (no per-doc whole-population dict copy), and
    the return gains a "catalog" section (rows/bytes, per-decision
    maxima, budget and tie diagnostics). counters (Lane G
    Counters, optional) receives the per-call catalog
    rows/bytes/scoring evals. Catalog routing does not compose
    with an attached sync navigator: that combination fails
    closed.

    keyed_state (C2 Closure P §5.2): additive persistence backend.
    When True, foreground progress uses the indexed TL-owned SQLite
    sidecar (tlsys.prodstate) with keyed reads/writes (no
    whole-manifest load/save, no per-doc prefix scan). The committed
    op stream, batching (10-op contract), Narrow behavior,
    resume/refusal rules and report shapes match the legacy path
    (plus additive "keyed"/"rejected" receipts). Exclusive with
    progress_journal. session: optional tlsys.prodstate.ProducerSession
    for routing reuse (else an ephemeral per-call session
    restores/persists routing snapshots).

    archive_manifest (P-2, Sec 5.7): explicit archive/compatibility
    export on this keyed call (the legacy JSON materializes exactly
    once and the sidecar records the export). Ordinary calls leave
    it False: NO JSON is written, and progress past the last export
    is flagged with the O(1) stale marker (see tlsys.prodstate;
    manifest_currency reports the verdict). Requires keyed_state.
    """
    if archive_manifest and not keyed_state:
        raise ValueError("ingest: archive_manifest needs "
                         "keyed_state=True (legacy cadence is pinned)")
    if keyed_state and progress_journal:
        raise ValueError("ingest: keyed_state and progress_journal "
                         "are exclusive persistence paths")
    if keyed_state:
        return _ingest_docs_keyed(
            tlstore, docs, embed_texts, store_id=store_id,
            place_xdoc=place_xdoc, place_t=place_t,
            place_budget=place_budget, profile=profile,
            counters=counters, session=session,
            archive_manifest=archive_manifest)
    from tlsys.prodstate import refuse_legacy_writer as _refuse
    _refuse(tlstore.store)
    from tlsys.store_if import prepare_artifact as _prep
    store = tlstore.store
    manifest, manifest_path = _load_manifest(store)
    if any(not k.startswith("_") for k in manifest):
        found = manifest.get("_scheme")
        if found != ATOM_SCHEME:
            raise RuntimeError(
                f"ingest manifest scheme {found!r} != {ATOM_SCHEME!r}: "
                "store was organized under a different atom-identity "
                "scheme; rebuild the scratch store (no migration; see "
                "tl-sys/ORGANIZATION-CONFORMANCE.md section 4)")
    journal_path = _journal_path(store)
    # Always replay (both modes): a legacy call after a journal call
    # must never see stale progress.
    _journal_replay(manifest, journal_path)
    jf = None
    journal_seq = manifest.get(_JOURNAL_SEQ_KEY, 0)
    if progress_journal:
        # R8-C (b): never append onto a torn tail -- truncate to
        # the last validated boundary (torn bytes preserved aside)
        # BEFORE the first append of this call.
        _restore_journal_boundary(journal_path)
        # R7-A hardening: dir-fsync on create (journal-only; the
        # legacy path is untouched). The file must be linked before
        # its first fsynced record means anything.
        _journal_new = not os.path.isfile(journal_path)
        jf = open(journal_path, "a")
        if _journal_new:
            _fsync_dir(os.path.dirname(journal_path) or ".")

    def journal_record(rec):
        nonlocal journal_seq
        journal_seq += 1
        rec = dict(rec)
        rec["seq"] = journal_seq
        _journal_append(jf, rec)
        manifest[_JOURNAL_SEQ_KEY] = journal_seq

    def refresh_statuses(doc_ids):
        pending = manifest.get("_pending_placement", [])
        statuses = {}
        for d in doc_ids:
            if d in manifest and isinstance(manifest[d], dict):
                st = _derive_status(manifest[d], d in pending)
                manifest[d]["status"] = st
                statuses[d] = st
        return statuses

    def persist_statuses(statuses):
        # Status-only persist for docs whose batch is empty (no flush
        # will follow to carry them).
        if not statuses:
            return
        if jf is None:
            _save_manifest(manifest_path, manifest)
        else:
            journal_record({"event": "flushed", "ops": [],
                            "statuses": statuses})

    n_atoms = n_holons = n_x = 0
    skipped = []
    resumed = []
    batch = []
    pending_doc = []  # (doc_id, kind) per batched op, for manifest
    pending_x = {}  # xholon_id -> {members, descriptor}: versions built
    # in the current unflushed batch (placement sees committed + pending,
    # so same-batch xholons are joinable; flush resets to committed truth)

    def flush():
        if not batch:
            return
        results, _info = tlstore.commit_batch(batch)
        ops_log = []
        for r, (doc_id, kind) in zip(results, pending_doc):
            if r.get("status") != "committed":
                raise RuntimeError(f"ingest op {r.get('op_id')} "
                                   f"{r.get('status')}:{r.get('code')}")
            m = _backfill_entry(manifest.setdefault(
                doc_id, {"atoms": [], "holon": None, "xdoc": []}))
            if kind == "atom":
                m["atoms"].append(r["op_id"])
            elif kind == "xholon":
                m["xdoc"].append(r["op_id"])
            else:
                m["holon"] = r["op_id"]
            ops_log.append({"doc": doc_id, "kind": kind,
                            "op_id": r["op_id"]})
        manifest["_scheme"] = ATOM_SCHEME
        statuses = refresh_statuses({d for d, _k in pending_doc})
        if jf is None:
            _save_manifest(manifest_path, manifest)
        else:
            journal_record({"event": "flushed", "ops": ops_log,
                            "statuses": statuses})
        del batch[:]
        del pending_doc[:]
        pending_x.clear()

    from tlsys.place import PLACE_FOREGROUND_BUDGET as _PFB
    budget = _PFB if place_budget is None else place_budget
    n_placed = 0  # placement decisions this call (S-03 §1b budget)
    n_deferred = 0
    manifest.setdefault("_pending_placement", [])

    xh_cache = {}  # committed xholon versions (incremental; latest wins)
    xh_seen = 0  # max commit seq folded into xh_cache
    # M2-C: seed the xholon window from the persisted keyed
    # projection (tlsys.proj) instead of re-scanning from seq 0 on
    # every call. A cold store scans once; a warm call consumes
    # only new commits. Same-call flushed versions still arrive
    # through the per-doc min_seq window in place_doc below.
    ingest_proj = None
    ingest_catchup = None
    if place_xdoc:
        from tlsys.proj import Projections as _Projections
        ingest_proj = _Projections.cached(tlstore)
        ingest_catchup = ingest_proj.update(tlstore)
        for _hid, _h in ingest_proj.xholons_view().items():
            xh_cache[_hid] = {"members": list(_h["members"]),
                              "descriptor": list(_h["descriptor"]),
                              "seq": _h.get("seq")}
        xh_seen = ingest_proj.frontier
    # C2 Lane O working state (flag-gated; flag-off leaves every
    # line below on the reference path, bit-identical to before).
    from tlsys.catalog import (Catalog as _Catalog,
                               OverlayView as _OverlayView,
                               catalog_row_budget as _rcat,
                               catalog_routing_enabled as _flag_on)
    use_catalog = bool(_flag_on(profile) and place_xdoc)
    xcat = None
    if use_catalog:
        for _v in xh_cache.values():
            xcat = _Catalog("xholon", len(_v["descriptor"]),
                            _rcat(profile))
            break
        if xcat is not None:
            xcat.build(
                (hid, e["descriptor"], len(e["members"]))
                for hid, e in xh_cache.items())
    catch = {"decisions": 0, "max_rows": 0, "ties": [],
             "over_budget": False, "max_exec_rows": 0, "_exec_seen": 0}

    def place_doc(doc_id, aids, vecs, centroid):
        """Cross-doc placement ops for one doc; appends to batch.

        Decided against committed (incrementally cached) +
        same-batch-pending xholon versions. Joins: new versioned meta
        (members + exact incremental mean descriptor). Miss: one new
        xholon `xdoc-{doc_id}`. Returns ops.
        """
        nonlocal xh_seen, xcat
        from tlsys.place import (T_PLACE, decide, read_xholons,
                                 xholon_op)
        from tlsys.place import decide_catalog as _decide_catalog
        t_place = T_PLACE if place_t is None else place_t
        pinned = tlstore.pin()
        fresh = read_xholons(tlstore, pinned, min_seq=xh_seen)
        for hid, h in fresh.items():
            xh_cache[hid] = h
        xh_seen = pinned[2]  # window fully scanned; ascending seqs
        if use_catalog:
            if xcat is None:
                # Lazily created at the first decision (dim from the
                # query side; the committed mirror starts empty or
                # from the folded cache -- same key order either way).
                dim = len(centroid)
                xcat = _Catalog("xholon", dim, _rcat(profile))
                xcat.build(
                    (hid, e["descriptor"], len(e["members"]))
                    for hid, e in xh_cache.items())
            else:
                for hid, h in fresh.items():
                    xcat.upsert(hid, h["descriptor"],
                                len(h["members"]))
            # Per-decision union, exactly mirroring `dict(xh_cache)
            # + update(pending_x)` order and values (in-place for
            # shadowed ids, appended for pending-only ids), rolled
            # back so the catalog stays the committed mirror.
            xcat.begin_doc()
            try:
                for hid, h in pending_x.items():
                    xcat.upsert(hid, h["descriptor"],
                                len(h["members"]))
                xstats = {}
                joins = _decide_catalog(
                    centroid, xcat, t_place=t_place,
                    stats=xstats, counters=counters)
            finally:
                xcat.rollback()
            catch["decisions"] += 1
            rows = xstats.get("catalog_rows", 0)
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
            if xstats.get("catalog_ties") \
                    and len(catch["ties"]) < 16:
                catch["ties"].append(xstats["catalog_ties"])
            if xstats.get("catalog_budget_exceeded"):
                catch["over_budget"] = True
            xh = _OverlayView(xh_cache, pending_x)
        else:
            xh = dict(xh_cache)
            xh.update(pending_x)
            joins = decide(centroid, xh, t_place=t_place)
        n = 0
        prep = lambda bb, sid, _s=store: _prep(_s, bb, sid)  # noqa: E731
        from tlsys.place import MAX_XHOLON_MEMBERS as _MXH
        applied = []
        for hid in joins:
            old = xh[hid]
            fresh_aids = [a for a in aids if a not in old["members"]]
            fresh_set = set(fresh_aids)
            if not fresh_aids:
                continue
            if len(old["members"]) + len(fresh_aids) > _MXH:
                continue  # exact cap: multi-atom docs must not push
                # a holon past MAX (decide() pre-filters on current
                # size only, so this check closes the overshoot).
            members = old["members"] + fresh_aids
            n_old = len(old["members"])
            fresh_vecs = [vecs[ix] for ix, a in enumerate(aids)
                          if a in fresh_set]
            from tlsys.place import join_descriptor as _join_desc
            desc = _join_desc(old["descriptor"], n_old, fresh_vecs)
            batch.append(xholon_op(hid, members, desc, store_id, prep))
            pending_doc.append((doc_id, "xholon"))
            pending_x[hid] = {"members": members, "descriptor": desc}
            applied.append(hid)
            n += 1
        if not applied:
            hid = f"xdoc-{doc_id}"
            batch.append(xholon_op(hid, list(aids), list(centroid),
                                   store_id, prep))
            pending_doc.append((doc_id, "xholon"))
            pending_x[hid] = {"members": list(aids),
                              "descriptor": list(centroid)}
            n += 1
        return n

    import hashlib as _hl
    try:
        for doc_id, text in docs:
            chunks = _supplied_chunks(text)
            want = "sha256:" + _hl.sha256(
                text.encode("utf-8")).hexdigest()
            want_len = len(text.encode("utf-8"))
            entry = manifest.get(doc_id)
            if entry is not None and not isinstance(entry, dict):
                raise RuntimeError(
                    f"manifest entry for {doc_id!r} is corrupt "
                    "(not an object; refusing to proceed)")
            if entry is None:
                if place_xdoc and doc_id.startswith("xdoc-"):
                    raise ValueError(
                        f"doc_id {doc_id!r}: 'xdoc-' prefix is "
                        "reserved for cross-doc holons")
                # New source revision: uuidv7 minted at
                # acknowledgment, carried in the manifest + every
                # atom meta + the v2 preimage. The declaration is
                # persisted BEFORE any op commits, so a retry resumes
                # this same revision instead of minting a duplicate.
                revision_id = uuidv7()
                entry = {
                    "atoms": [], "holon": None, "xdoc": [],
                    "revision_id": revision_id,
                    "source_sha256": want, "revision_len": want_len,
                    "n_chunks_expected": len(chunks),
                    "source_verified": True, "status": P_STARTED}
                manifest[doc_id] = entry
                manifest["_scheme"] = ATOM_SCHEME
                if jf is None:
                    _save_manifest(manifest_path, manifest)
                else:
                    journal_record({
                        "event": "started", "doc_id": doc_id,
                        "revision_id": revision_id,
                        "source_sha256": want,
                        "revision_len": want_len,
                        "n_chunks_expected": len(chunks)})
                committed_ix = {}
                committed_holon = None
                committed_xdoc = []
                fresh = True
            else:
                _backfill_entry(entry)
                have_hash = entry.get("source_sha256")
                if have_hash not in (None, "", "UNKNOWN"):
                    # Idempotent re-ingest ONLY for identical bytes
                    # (S-02: changed source bytes mean a new
                    # revision, never a silent keep-or-overwrite;
                    # revision chains are future, so a changed
                    # re-ingest fails closed here).
                    if have_hash != want:
                        raise RuntimeError(
                            f"doc {doc_id!r}: source bytes changed "
                            "since acknowledgment (new revision under "
                            "an existing doc_id refused; re-ingest "
                            "under a new doc_id)")
                else:
                    # Recovered (sourceless) entry: trust nothing.
                    # The supplied bytes must reproduce the committed
                    # chunk evidence exactly before the entry is
                    # trusted (hash adopted) -- otherwise refuse.
                    # Replay never certifies an unknown source.
                    _comm = _committed_doc_state(tlstore, doc_id)
                    if not _verify_chunks_against_committed(
                            chunks, _comm["by_ix"]):
                        raise RuntimeError(
                            f"doc {doc_id!r}: recovered manifest "
                            "entry has unknown source identity and "
                            "the supplied bytes do not reproduce the "
                            "committed chunk evidence (refusing to "
                            "certify; re-ingest corrected bytes under "
                            "a new doc_id)")
                    # R8-C (a): UNKNOWN-origin PARTIAL revisions
                    # REFUSE same-revision completion. A same-count
                    # suffix substitution past the committed prefix
                    # is indistinguishable from the original bytes
                    # (the verifier above passes for both), so only
                    # full pre-existing coverage -- skip with no new
                    # bytes certified -- may proceed. Refused BEFORE
                    # adoption (no hash fill, no journal write) so a
                    # refused call leaves no adopted identity behind
                    # and commits nothing.
                    if not (len(_comm["by_ix"]) == len(chunks)
                            and _comm["holon"] is not None):
                        raise RuntimeError(
                            f"doc {doc_id!r}: recovered manifest "
                            "entry has unknown source identity and "
                            "committed coverage is partial "
                            f"({len(_comm['by_ix'])}/{len(chunks)} "
                            "chunks"
                            f"{', no holon' if _comm['holon'] is None else ''}); "  # noqa: E501
                            "same-revision completion refused "
                            "(re-ingest under a new doc_id)")
                    entry["source_sha256"] = want
                    entry["revision_len"] = want_len
                    entry["source_verified"] = True
                    if jf is not None:
                        journal_record({
                            "event": "adopted", "doc_id": doc_id,
                            "source_sha256": want,
                            "revision_len": want_len})
                exp = entry.get("n_chunks_expected")
                if exp is None:
                    # Legacy/recovered entry: adopt the (verified)
                    # chunking as the declared coverage.
                    entry["n_chunks_expected"] = len(chunks)
                elif exp != len(chunks):
                    raise RuntimeError(
                        f"doc {doc_id!r}: supplied bytes chunk to "
                        f"{len(chunks)} chunks but the declared "
                        f"revision expects {exp} (atomizer drift; "
                        "refusing resume)")
                status = _derive_status(
                    entry,
                    doc_id in manifest.get("_pending_placement", []))
                entry["status"] = status
                if status in P_SOURCE_DURABLE:
                    skipped.append(doc_id)
                    continue
                # RESUME the same revision: reconcile the manifest
                # against committed truth, commit only what is
                # missing, adopt (never re-mint) committed op ids.
                revision_id = entry.get("revision_id")
                _comm = _committed_doc_state(tlstore, doc_id)
                by_ix = _comm["by_ix"]
                revs = {c["revision_id"] for c in by_ix.values()}
                revs.discard(None)
                if revision_id is None:
                    if len(revs) != 1:
                        raise RuntimeError(
                            f"doc {doc_id!r}: manifest lacks a "
                            "revision and committed data shows "
                            f"{len(revs)} revisions (ambiguous; "
                            "re-ingest under a new doc_id)")
                    revision_id = revs.pop()
                    entry["revision_id"] = revision_id
                elif revs and revs != {revision_id}:
                    raise RuntimeError(
                        f"doc {doc_id!r}: committed chunks span "
                        "multiple revisions under one doc_id "
                        "(ambiguous; re-ingest under a new doc_id)")
                committed_ix = by_ix
                committed_holon = _comm["holon"]
                committed_xdoc = _comm["xdoc"]
                fresh = False
                resumed.append(doc_id)
            # Atom ids are deterministic in (bytes, doc, span,
            # revision): recompute for ALL chunks so resume reuses
            # the identical ids the fresh path would mint.
            aids = [atom_id(ct.encode("utf-8"), doc_id, (b0, b1),
                             revision_id)
                    for (_c0, _c1, ct, b0, b1) in chunks]
            if not fresh:
                for ix, c in committed_ix.items():
                    if not isinstance(ix, int) \
                            or not (0 <= ix < len(chunks)) \
                            or aids[ix] != c["aid"]:
                        raise RuntimeError(
                            f"doc {doc_id!r}: committed chunk {ix} "
                            "disagrees with the declared revision "
                            "(ambiguous; re-ingest under a new doc_id)")
                if committed_holon is not None:
                    hop_id, hmembers = committed_holon
                    if set(hmembers) != set(aids):
                        raise RuntimeError(
                            f"doc {doc_id!r}: committed holon "
                            "membership disagrees with the declared "
                            "revision coverage (ambiguous; re-ingest "
                            "under a new doc_id)")
                    if entry.get("holon") is None:
                        entry["holon"] = hop_id
                have_ops = set(entry["atoms"])
                for ix in sorted(committed_ix):
                    op_id = committed_ix[ix]["op_id"]
                    if op_id not in have_ops:
                        entry["atoms"].append(op_id)
                        have_ops.add(op_id)
                aid_set = set(aids)
                for op_id, members in committed_xdoc:
                    if (aid_set & set(members)) \
                            and op_id not in entry["xdoc"]:
                        entry["xdoc"].append(op_id)
            holon_needed = entry.get("holon") is None
            texts = [c[2] for c in chunks]
            vecs = embed_texts(texts)
            for ix, (c0, c1, ctext, b0, b1) in enumerate(chunks):
                if ix in committed_ix:
                    continue
                b = ctext.encode("utf-8")
                op = atom_op(doc_id, ix, len(chunks),
                             (c0, c1, b0, b1), b,
                             [float(x) for x in vecs[ix]], store_id,
                             lambda bb, sid, _s=store: _prep(_s, bb, sid),
                             revision_id)
                batch.append(op)
                pending_doc.append((doc_id, "atom"))
                n_atoms += 1
                if len(batch) >= BATCH_OPS:
                    flush()
            dim = len(vecs[0])
            centroid = [sum(v[d] for v in vecs) / len(vecs)
                        for d in range(dim)]
            if holon_needed:
                batch.append(holon_op(
                    doc_id, aids, centroid, store_id,
                    lambda bb, sid, _s=store: _prep(_s, bb, sid)))
                pending_doc.append((doc_id, "holon"))
                n_holons += 1
            if place_xdoc and not entry["xdoc"]:
                if n_placed >= budget:
                    # Budget-bound: atoms + per-doc holon still commit
                    # (acknowledged + retrievable); placement defers.
                    if doc_id not in manifest["_pending_placement"]:
                        manifest["_pending_placement"].append(doc_id)
                        if jf is not None:
                            journal_record({"event": "backlog_add",
                                            "doc_id": doc_id})
                    n_deferred += 1
                else:
                    # Placement appends up to MAX_XMEMBERSHIPS ops;
                    # pre-flush so the batch never exceeds the
                    # committer's 10-op cap.
                    from tlsys.place import MAX_XMEMBERSHIPS as _MXM
                    if len(batch) > BATCH_OPS - _MXM:
                        flush()
                    n_x += place_doc(doc_id, aids, vecs, centroid)
                    n_placed += 1
                    if doc_id in manifest["_pending_placement"]:
                        # Resumed a backlogged doc within budget:
                        # placed now, leaves the backlog.
                        manifest["_pending_placement"].remove(doc_id)
                        if jf is not None:
                            journal_record({"event": "backlog_del",
                                            "doc_id": doc_id})
            if batch:
                if len(batch) >= BATCH_OPS:
                    flush()
            else:
                # Nothing outstanding (catch-up resume): persist the
                # refreshed status; no flush will carry it.
                persist_statuses(refresh_statuses([doc_id]))
        flush()
    finally:
        if jf is not None:
            jf.close()
    _b, _e, _s, triple = tlstore.pin()
    # End-save (both modes): manifest carries every declaration,
    # adoption, backlog edit, and status refresh; journal mode saves
    # here exactly once. Skipped docs also refresh their (derived)
    # status in this save.
    manifest["_scheme"] = ATOM_SCHEME
    refresh_statuses([d for d in manifest
                      if not d.startswith("_")])
    if manifest.get("_pending_placement") is None:
        manifest["_pending_placement"] = []
    _save_manifest(manifest_path, manifest)
    # Drain the journal when the manifest now covers it (both modes,
    # so a legacy call also retires journal debt). Best-effort
    # unlink: on a read-only store the records simply replay
    # idempotently next time.
    try:
        if os.path.isfile(journal_path):
            recs = _journal_records(journal_path)
            if not recs or manifest.get(_JOURNAL_SEQ_KEY, 0) >= max(
                    r.get("seq", 0) for r in recs):
                os.remove(journal_path)
    except OSError:
        pass
    if ingest_proj is not None:
        # Consume this call's own commits so the checkpoint covers
        # the end pin (bounded: only this call's versions), then
        # persist. A cache write must never fail the ingest: on
        # OSError the next call cold-rebuilds (recorded, never
        # silent).
        try:
            ingest_catchup["commit_catchup"] = ingest_proj.update(
                tlstore)
            ingest_proj.save(tlstore)
            ingest_catchup["checkpoint_saved"] = True
        except OSError as e:
            ingest_catchup["checkpoint_saved"] = False
            ingest_catchup["checkpoint_error"] = (
                f"{type(e).__name__}: {e}")
    out = {"n_atoms": n_atoms, "n_holons": n_holons,
           "n_xholon_ops": n_x, "skipped": skipped,
           "resumed": resumed,
           "n_deferred": n_deferred,
           "pending_placement": list(
               manifest.get("_pending_placement", [])),
           "pinned": triple,
           "catchup": ingest_catchup}
    if use_catalog:
        # Opt-in only (flag-gated): catalog work receipt for F5/D2.
        # O-7: executed + logical bytes ride alongside the eligible
        # rows/bytes (eligible keys unchanged).
        out["catalog"] = {
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
    return out


def _check_session_profile(session, profile, where):
    """Fail loud when a session's bound profile disagrees with a call.

    The R_cat budget pins catalog construction; a session serves one
    budget per process (same rule as the frozen profile).
    """
    from tlsys.catalog import catalog_row_budget as _rcat
    from tlsys.prodstate import SidecarError as _SCE
    if session._profile is None:  # same-package bound-profile read
        raise _SCE(
            f"{where}: session needs the call profile for catalog "
            "routing (pass ProducerSession(profile))")
    if _rcat(profile) != _rcat(session._profile):
        raise _SCE(
            f"{where}: session R_cat {_rcat(session._profile)} != "
            f"call R_cat {_rcat(profile)} (one budget per session)")


def _keyed_totals_snapshot(xcat):
    if xcat is None:
        return None
    return (xcat.total_rows, xcat.total_bytes, xcat.total_calls,
            xcat.total_executed_rows, xcat.total_descriptor_read_B,
            xcat.total_copy_B, xcat.total_logical_read_B,
            xcat.total_logical_written_B)


def _keyed_totals_delta(xcat, snap):
    if xcat is None:
        return None
    cur = _keyed_totals_snapshot(xcat)
    base = snap or (0, 0, 0, 0, 0, 0, 0, 0)
    return {"rows": cur[0] - base[0], "bytes": cur[1] - base[1],
            "calls": cur[2] - base[2], "n": xcat.n,
            "executed_rows": cur[3] - base[3],
            "descriptor_read_B": cur[4] - base[4],
            "copy_B": cur[5] - base[5],
            "logical_read_B": cur[6] - base[6],
            "logical_written_B": cur[7] - base[7]}


def _ingest_docs_keyed(tlstore, docs, embed_texts, store_id="tl-sys-docs",
                       place_xdoc=True, place_t=None, place_budget=None,
                       profile=None, counters=None, session=None,
                       archive_manifest=False):
    """Keyed-backend ingest (Closure P §5.2; see ingest_docs).

    Same committed op stream, batching, Narrow behavior, resume and
    refusal rules as the legacy path; foreground progress is keyed
    SQLite (no whole-manifest load/save, no per-doc prefix scan).
    P-2: the legacy manifest materializes ONLY on an explicit
    archive_manifest request; ordinary calls write no JSON (the O(1)
    stale marker flags progress past the last export).
    """
    from tlsys.store_if import prepare_artifact as _prep
    from tlsys.prodstate import (
        ProducerState, ProducerSession, consume_suffix, gate_decision,
        OverBudgetRejected, REMAINING_SAMPLE, close_out_keyed_call)
    from tlsys.catalog import (
        OverlayView as _OverlayView, catalog_row_budget as _rcat,
        catalog_routing_enabled as _flag_on)
    store = tlstore.store
    manifest = {}
    mpath = os.path.join(store.root, MANIFEST_NAME)
    if os.path.isfile(mpath):
        with open(mpath) as f:
            manifest = json.load(f)
    state, migrec = ProducerState.create_or_migrate(tlstore, manifest)
    keyed_rec = {"migrated": migrec, "suffix": None, "adopted_ops": 0,
                 "rcat_estimates": [], "rcat_estimate_count": 0}
    try:
        # Crash-window adoption up front (bounded suffix; clean calls
        # read nothing): every resume below is pure keyed.
        sufrec = consume_suffix(tlstore, state)
        keyed_rec["suffix"] = sufrec
        keyed_rec["adopted_ops"] = sufrec["adopted_ops"]
        n_atoms = n_holons = n_x = 0
        skipped = []
        resumed = []
        batch = []
        pending_doc = []  # (doc_id, kind) per batched op
        pending_meta = []  # sidecar record detail per batched op
        pending_x = {}
        touched = []
        touched_set = set()
        touched_xids = set()
        rejected = []

        def note_touched(doc_id):
            if doc_id not in touched_set:
                touched_set.add(doc_id)
                touched.append(doc_id)

        def refresh_statuses(doc_ids):
            statuses = {}
            for d in doc_ids:
                e = state.get_doc(d)
                if e is None:
                    continue
                statuses[d] = _derive_status(e, state.is_pending(d))
            return statuses

        def flush():
            if not batch:
                return
            results, _info = tlstore.commit_batch(batch)
            ops_log = []
            for r, (doc_id, kind), meta in zip(results, pending_doc,
                                               pending_meta):
                if r.get("status") != "committed":
                    raise RuntimeError(
                        f"ingest op {r.get('op_id')} "
                        f"{r.get('status')}:{r.get('code')}")
                rec = {"doc": doc_id, "kind": kind,
                       "op_id": r["op_id"], "seq": None}
                rec.update(meta)
                ops_log.append(rec)
                note_touched(doc_id)
            _b, _e, _mx, _triple = tlstore.pin()
            statuses = refresh_statuses({d for d, _k in pending_doc})
            state.record_flush(ops_log, statuses,
                               frontier=(_b, _e, _mx, _triple))
            del batch[:]
            del pending_doc[:]
            del pending_meta[:]
            pending_x.clear()

        from tlsys.place import PLACE_FOREGROUND_BUDGET as _PFB
        budget = _PFB if place_budget is None else place_budget
        n_placed = 0
        n_deferred = 0
        ingest_proj = None
        ingest_catchup = None
        xh_cache = {}
        xh_seen = 0
        if place_xdoc:
            from tlsys.proj import Projections as _Projections
            ingest_proj = _Projections.cached(tlstore)
            ingest_catchup = ingest_proj.update(tlstore)
        use_catalog = bool(_flag_on(profile) and place_xdoc)
        if session is not None and use_catalog:
            _check_session_profile(session, profile, "ingest")
        sess = None
        xcat = None
        if place_xdoc:
            if use_catalog:
                sess = session if session is not None \
                    else ProducerSession(profile)
                sess.begin_call()
                sess.attach(tlstore, state)
                xh_cache, _aidx = sess.ensure_xdoc(
                    ingest_proj.xholons_view(), ingest_proj.frontier)
                if xh_cache:
                    first = next(iter(xh_cache.values()))
                    xcat = sess.xdoc_catalog(len(first["descriptor"]))
            else:
                for _hid, _h in ingest_proj.xholons_view().items():
                    xh_cache[_hid] = {
                        "members": list(_h["members"]),
                        "descriptor": list(_h["descriptor"]),
                        "seq": _h.get("seq")}
            xh_seen = ingest_proj.frontier
        tot0 = _keyed_totals_snapshot(xcat)
        catch = {"decisions": 0, "max_rows": 0, "ties": [],
                 "over_budget": False, "max_exec_rows": 0,
                 "_exec_seen": None}

        def place_doc(doc_id, aids, vecs, centroid):
            nonlocal xh_seen, xcat
            from tlsys.place import (T_PLACE, decide, read_xholons,
                                     xholon_op)
            from tlsys.place import decide_catalog as _decide_catalog
            from tlsys.place import (MAX_XHOLON_MEMBERS as _MXH,
                                     MAX_XMEMBERSHIPS as _MXM)
            t_place = T_PLACE if place_t is None else place_t
            pinned = tlstore.pin()
            fresh = read_xholons(tlstore, pinned, min_seq=xh_seen)
            for hid, h in fresh.items():
                xh_cache[hid] = h
            if use_catalog and fresh and xcat is not None:
                for hid, h in fresh.items():
                    xcat.upsert(hid, h["descriptor"],
                                len(h["members"]))
                sess.note_dirty("xdoc")
            xh_seen = pinned[2]
            if use_catalog:
                if xcat is None:
                    xcat = sess.xdoc_catalog(len(centroid))
                if catch["_exec_seen"] is None:
                    # Session catalogs carry prior totals; the
                    # watermark seeds at first use (fresh cats: 0).
                    catch["_exec_seen"] = xcat.total_executed_rows
                # Same-batch pending overlay, exactly mirroring
                # dict(xh_cache) + update(pending_x) order/values.
                xcat.begin_doc()
                try:
                    for hid, h in pending_x.items():
                        xcat.upsert(hid, h["descriptor"],
                                    len(h["members"]))
                    # R_cat pre-execution gate over the exact decision
                    # population (BEFORE any scan; the masks below are
                    # the gate's copy -- decide() recomputes its own,
                    # both counted in mask_bytes).
                    rows_e = int(xcat.mask_lt(_MXH).sum())
                    try:
                        est = gate_decision(
                            "xholon", xcat.n, xcat.dim, [rows_e],
                            [_MXM], _rcat(profile),
                            f"ingest-place:{doc_id}")
                    except OverBudgetRejected as e:
                        rejected.append(
                            {"doc": doc_id, "leg": "place_xdoc",
                             "reason": str(e), "estimate": e.estimate})
                        raise
                    keyed_rec["rcat_estimate_count"] += 1
                    if len(keyed_rec["rcat_estimates"]) < 64:
                        keyed_rec["rcat_estimates"].append(
                            {"doc": doc_id, "leg": "place_xdoc",
                             "estimate": est})
                    xstats = {}
                    joins = _decide_catalog(
                        centroid, xcat, t_place=t_place,
                        stats=xstats, counters=counters)
                finally:
                    xcat.rollback()
                catch["decisions"] += 1
                rows = xstats.get("catalog_rows", 0)
                if rows > catch["max_rows"]:
                    catch["max_rows"] = rows
                exec_now = xcat.total_executed_rows
                exec_rows = exec_now - catch["_exec_seen"]
                catch["_exec_seen"] = exec_now
                if exec_rows > catch["max_exec_rows"]:
                    catch["max_exec_rows"] = exec_rows
                if xstats.get("catalog_ties") \
                        and len(catch["ties"]) < 16:
                    catch["ties"].append(xstats["catalog_ties"])
                if xstats.get("catalog_budget_exceeded"):
                    catch["over_budget"] = True
                xh = _OverlayView(xh_cache, pending_x)
            else:
                xh = dict(xh_cache)
                xh.update(pending_x)
                joins = decide(centroid, xh, t_place=t_place)
            n = 0
            prep = lambda bb, sid, _s=store: _prep(_s, bb, sid)
            from tlsys.place import MAX_XHOLON_MEMBERS as _MXH2
            applied = []
            for hid in joins:
                old = xh[hid]
                fresh_aids = [a for a in aids
                              if a not in old["members"]]
                fresh_set = set(fresh_aids)
                if not fresh_aids:
                    continue
                if len(old["members"]) + len(fresh_aids) > _MXH2:
                    continue
                members = old["members"] + fresh_aids
                n_old = len(old["members"])
                fresh_vecs = [vecs[ix] for ix, a in enumerate(aids)
                              if a in fresh_set]
                from tlsys.place import join_descriptor as _join_desc
                desc = _join_desc(old["descriptor"], n_old, fresh_vecs)
                batch.append(xholon_op(hid, members, desc, store_id,
                                       prep))
                pending_doc.append((doc_id, "xholon"))
                pending_meta.append({"xdoc_id": hid})
                pending_x[hid] = {"members": members,
                                  "descriptor": desc}
                touched_xids.add(hid)
                applied.append(hid)
                n += 1
            if not applied:
                hid = f"xdoc-{doc_id}"
                batch.append(xholon_op(hid, list(aids),
                                       list(centroid), store_id, prep))
                pending_doc.append((doc_id, "xholon"))
                pending_meta.append({"xdoc_id": hid})
                pending_x[hid] = {"members": list(aids),
                                  "descriptor": list(centroid)}
                touched_xids.add(hid)
                n += 1
            return n

        import hashlib as _hl
        for doc_id, text in docs:
            chunks = _supplied_chunks(text)
            want = "sha256:" + _hl.sha256(
                text.encode("utf-8")).hexdigest()
            want_len = len(text.encode("utf-8"))
            entry = state.get_doc(doc_id)
            if entry is None:
                if place_xdoc and doc_id.startswith("xdoc-"):
                    raise ValueError(
                        f"doc_id {doc_id!r}: 'xdoc-' prefix is "
                        "reserved for cross-doc holons")
                # New source revision, declared durably BEFORE any
                # op commits (a retry resumes this same revision).
                from tlsys.store_if import uuidv7 as _uuidv7
                revision_id = _uuidv7()
                state.declare_revision(
                    doc_id, revision_id, want, want_len, len(chunks))
                note_touched(doc_id)
                committed_ix = {}
                committed_holon_op = None
                committed_holon_members = None
                fresh = True
            else:
                note_touched(doc_id)
                have_hash = entry.get("source_sha256")
                if have_hash not in (None, "", "UNKNOWN"):
                    if have_hash != want:
                        raise RuntimeError(
                            f"doc {doc_id!r}: source bytes changed "
                            "since acknowledgment (new revision under "
                            "an existing doc_id refused; re-ingest "
                            "under a new doc_id)")
                else:
                    # Recovered (sourceless) entry: the supplied bytes
                    # must reproduce the recorded chunk evidence
                    # before adoption (R8-C: partials refuse
                    # same-revision completion).
                    det = state.doc_detail(doc_id)
                    if not _verify_chunks_against_committed(
                            chunks, det["by_ix"]):
                        raise RuntimeError(
                            f"doc {doc_id!r}: recovered manifest "
                            "entry has unknown source identity and "
                            "the supplied bytes do not reproduce the "
                            "committed chunk evidence (refusing to "
                            "certify; re-ingest corrected bytes under "
                            "a new doc_id)")
                    if not (len(det["by_ix"]) == len(chunks)
                            and det["holon_op"] is not None):
                        raise RuntimeError(
                            f"doc {doc_id!r}: recovered manifest "
                            "entry has unknown source identity and "
                            "committed coverage is partial "
                            f"({len(det['by_ix'])}/{len(chunks)} "
                            "chunks"
                            f"{', no holon' if det['holon_op'] is None else ''}; "  # noqa: E501
                            "same-revision completion refused "
                            "(re-ingest under a new doc_id)")
                    state.adopt_declaration(
                        doc_id, source_sha256=want,
                        revision_len=want_len)
                    entry["source_sha256"] = want
                    entry["revision_len"] = want_len
                    entry["source_verified"] = True
                exp = entry.get("n_chunks_expected")
                if exp is None:
                    state.adopt_declaration(
                        doc_id, n_chunks_expected=len(chunks))
                    entry["n_chunks_expected"] = len(chunks)
                elif exp != len(chunks):
                    raise RuntimeError(
                        f"doc {doc_id!r}: supplied bytes chunk to "
                        f"{len(chunks)} chunks but the declared "
                        f"revision expects {exp} (atomizer drift; "
                        "refusing resume)")
                status = _derive_status(
                    entry, state.is_pending(doc_id))
                if status in P_SOURCE_DURABLE:
                    skipped.append(doc_id)
                    continue
                # RESUME the same revision: the start-of-call suffix
                # adoption already reconciled recorded truth; adopt
                # (never re-mint) recorded op ids.
                revision_id = entry.get("revision_id")
                det = state.doc_detail(doc_id)
                by_ix = det["by_ix"]
                revs = {c["revision_id"] for c in by_ix.values()}
                revs.discard(None)
                if revision_id is None:
                    if len(revs) != 1:
                        raise RuntimeError(
                            f"doc {doc_id!r}: manifest lacks a "
                            "revision and committed data shows "
                            f"{len(revs)} revisions (ambiguous; "
                            "re-ingest under a new doc_id)")
                    revision_id = revs.pop()
                    state.adopt_declaration(
                        doc_id, revision_id=revision_id)
                elif revs and revs != {revision_id}:
                    raise RuntimeError(
                        f"doc {doc_id!r}: committed chunks span "
                        "multiple revisions under one doc_id "
                        "(ambiguous; re-ingest under a new doc_id)")
                committed_ix = by_ix
                committed_holon_op = det["holon_op"]
                committed_holon_members = det["holon_members"]
                fresh = False
                resumed.append(doc_id)
            aids = [atom_id(ct.encode("utf-8"), doc_id, (b0, b1),
                             revision_id)
                    for (_c0, _c1, ct, b0, b1) in chunks]
            if not fresh:
                for ix, c in committed_ix.items():
                    if not isinstance(ix, int) \
                            or not (0 <= ix < len(chunks)) \
                            or aids[ix] != c["aid"]:
                        raise RuntimeError(
                            f"doc {doc_id!r}: committed chunk {ix} "
                            "disagrees with the declared revision "
                            "(ambiguous; re-ingest under a new doc_id)")
                if committed_holon_op is not None \
                        and committed_holon_members is not None:
                    if set(committed_holon_members) != set(aids):
                        raise RuntimeError(
                            f"doc {doc_id!r}: committed holon "
                            "membership disagrees with the declared "
                            "revision coverage (ambiguous; re-ingest "
                            "under a new doc_id)")
            entry = state.get_doc(doc_id)
            holon_needed = entry["holon"] is None
            texts = [c[2] for c in chunks]
            vecs = embed_texts(texts)
            for ix, (c0, c1, ctext, b0, b1) in enumerate(chunks):
                if ix in committed_ix:
                    continue
                b = ctext.encode("utf-8")
                op = atom_op(doc_id, ix, len(chunks),
                             (c0, c1, b0, b1), b,
                             [float(x) for x in vecs[ix]], store_id,
                             lambda bb, sid, _s=store: _prep(_s, bb,
                                                             sid),
                             revision_id)
                batch.append(op)
                pending_doc.append((doc_id, "atom"))
                pending_meta.append(
                    {"chunk_ix": ix, "aid": aids[ix],
                     "byte_span": (b0, b1),
                     "text_digest": "sha256:" + _hl.sha256(b)
                     .hexdigest(),
                     "revision_id": revision_id,
                     "n_chunks": len(chunks)})
                n_atoms += 1
                if len(batch) >= BATCH_OPS:
                    flush()
            dim = len(vecs[0])
            centroid = [sum(v[d] for v in vecs) / len(vecs)
                        for d in range(dim)]
            if holon_needed:
                batch.append(holon_op(
                    doc_id, aids, centroid, store_id,
                    lambda bb, sid, _s=store: _prep(_s, bb, sid)))
                pending_doc.append((doc_id, "holon"))
                pending_meta.append({"members": list(aids)})
                n_holons += 1
            if place_xdoc and not entry["xdoc"]:
                if n_placed >= budget:
                    if not state.is_pending(doc_id):
                        state.backlog_add(doc_id)
                    n_deferred += 1
                else:
                    from tlsys.place import MAX_XMEMBERSHIPS as _MXM
                    if len(batch) > BATCH_OPS - _MXM:
                        flush()
                    try:
                        n_x += place_doc(doc_id, aids, vecs, centroid)
                    except OverBudgetRejected:
                        # No decision executed: the doc defers with a
                        # named reason (budget unconsumed).
                        if not state.is_pending(doc_id):
                            state.backlog_add(doc_id)
                        n_deferred += 1
                    else:
                        n_placed += 1
                        if state.is_pending(doc_id):
                            state.backlog_del(doc_id)
            if batch:
                if len(batch) >= BATCH_OPS:
                    flush()
            else:
                statuses = refresh_statuses([doc_id])
                if statuses:
                    state.record_flush([], statuses)
        flush()
        _b, _e, _s, triple = tlstore.pin()
        # Boundary close-out: touched-only status refresh (bounded;
        # untouched docs cannot have changed state), routing sync +
        # persist, then the single legacy-manifest materialization.
        statuses = {}
        for d in touched:
            e = state.get_doc(d)
            if e is not None:
                statuses[d] = _derive_status(e, state.is_pending(d))
        if statuses:
            state.record_flush([], statuses)
        if use_catalog and sess is not None:
            if touched_xids:
                sess.note_dirty("xdoc")
                final_views = ingest_proj.update(tlstore)
                sess.leg_sync("xdoc", ingest_proj.xholons_view(),
                              touched_xids, ingest_proj.frontier)
                if xcat is not None:
                    for hid in touched_xids:
                        h = ingest_proj.xholons_view().get(hid)
                        if h is not None:
                            xcat.upsert(hid, h["descriptor"],
                                        len(h["members"]))
                ingest_catchup["commit_catchup"] = final_views
            sess.persist(state)
        _man, arch_rec = close_out_keyed_call(
            state, mpath, archive_manifest=archive_manifest,
            reason="ingest")
        pending_count = state.pending_count()
        pending_ids = state.pending_sample()
        keyed_rec["archive"] = arch_rec
        keyed_rec["candidate_version"] = arch_rec[
            "candidate_version"]
    finally:
        state.close()
    if ingest_proj is not None and "commit_catchup" not in (
            ingest_catchup or {}):
        try:
            ingest_catchup["commit_catchup"] = ingest_proj.update(
                tlstore)
            ingest_proj.save(tlstore)
            ingest_catchup["checkpoint_saved"] = True
        except OSError as e:
            ingest_catchup["checkpoint_saved"] = False
            ingest_catchup["checkpoint_error"] = (
                f"{type(e).__name__}: {e}")
    elif ingest_proj is not None:
        try:
            ingest_proj.save(tlstore)
            ingest_catchup["checkpoint_saved"] = True
        except OSError as e:
            ingest_catchup["checkpoint_saved"] = False
            ingest_catchup["checkpoint_error"] = (
                f"{type(e).__name__}: {e}")
    if use_catalog and rejected:
        catch["over_budget"] = True
    out = {"n_atoms": n_atoms, "n_holons": n_holons,
           "n_xholon_ops": n_x, "skipped": skipped,
           "resumed": resumed,
           "n_deferred": n_deferred,
           "pending_placement": pending_ids,
           "pinned": triple,
           "catchup": ingest_catchup}
    out["pending_truncated"] = pending_count > REMAINING_SAMPLE
    out["pending_count"] = pending_count
    if use_catalog:
        out["catalog"] = {
            "decisions": catch["decisions"],
            "max_rows_per_decision": catch["max_rows"],
            "max_executed_rows_per_decision": catch["max_exec_rows"],
            "over_budget": catch["over_budget"],
            "ties": list(catch["ties"]),
            "rejected": rejected,
            "xholon": _keyed_totals_delta(xcat, tot0)}
    keyed_rec["suffix_commits"] = (keyed_rec["suffix"] or {}).get(
        "suffix_commits", 0)
    if use_catalog and sess is not None:
        keyed_rec["session" if session is not None else "routing"] = \
            sess.call_receipt()
    out["keyed"] = keyed_rec
    return out
