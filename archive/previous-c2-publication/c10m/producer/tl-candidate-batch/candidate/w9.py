"""W9 folding + multi-store publication + drain (Stage-C scratch, Linux reference).

Settled contracts implemented (no redesign):
- I3.4: a physical fold publishes replacement coverage WITHOUT changing the
  logical generation; publication is a reference swing inside ONE commit
  transaction per store — never a second commit kind. Folds mint no
  generation, write no commits/dedup rows, publish no pointer.
- I3.6: ONE publication format; multiple physical publications may coexist
  for pinned readers and incremental folding (old layouts persist as
  RETIRED until drain reclaims them after pins release).
- I9.4: folds proceed incrementally in bounded transactions; replacement
  coverage is durably published before old coverage is released; in-flight
  snapshots retain the state they require (pin-protected layouts are never
  reclaimed while their gen is live).
- I9.7: publishing a fold does not necessarily free space; accounting
  reports pin-retained bytes separately from reclaimable bytes.
- PR-FOLD/PR-DRAIN shape: reclamation waits on pins; reads resolve exactly
  one layout per read (atomic publication => no torn reads); duplicates
  suppressed by single-layout resolution + digest verification.

Model: integer key space [0, K). A layout partitions it into contiguous
segments with deterministic content digests. Content function key_value()
is the shared oracle: readers recompute digests independently of the fold
path, so a torn read (mixed layouts), gap (incomplete coverage), or
corrupt segment is DETECTED, not assumed away.

Lock domains: fold/drain take the store fence + commit.db write txn
(the fold domain). Attach/claim take only PinTable shm byte-range locks
(Q1.4: disjoint by construction). Fold never blocks on readers (no pin
table access at all); drain reads the live-pin SET (shared-memory reads
via the caller's live_pins_fn) but takes no pin lock.

Drain worker seam: drain() is bounded + resumable (budget + cursor +
more flag); the worker is any driver loop calling drain() to completion.
Scratch scope embeds the driver in the probes (no background daemon).

B-01 neutrality: no C1 integration, no C2/C3 removal/repair, no
eligibility materialization, no checkpoint executor, no policy beyond
Entry-1 (folds require the store fence only).
"""
import hashlib
import time
import uuid as _uuid

from common import FailClosed, Reject

W9_SCHEMA = """
CREATE TABLE IF NOT EXISTS w9_layouts(layout_id TEXT PRIMARY KEY,
  fold_seq INTEGER NOT NULL, gen TEXT NOT NULL,
  covers_lo INTEGER NOT NULL, covers_hi INTEGER NOT NULL,
  state TEXT NOT NULL, protected_gen TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS w9_segments(layout_id TEXT NOT NULL,
  seg_lo INTEGER NOT NULL, seg_hi INTEGER NOT NULL, digest TEXT NOT NULL,
  PRIMARY KEY(layout_id, seg_lo));
CREATE TABLE IF NOT EXISTS w9_pub(gen TEXT PRIMARY KEY, layout_id TEXT NOT NULL,
  fold_seq INTEGER NOT NULL, published_at REAL NOT NULL);
"""

PREPARED, PUBLISHED, RETIRED, RECLAIMED = (
    "PREPARED", "PUBLISHED", "RETIRED", "RECLAIMED")

# Experimental bounds (D-12), recorded per run, enforced once configured.
W9_CAPS = {"max_layouts": 10000, "max_segments_per_layout": 1024,
           "max_keys": 1000000}


class TornRead(FailClosed):
    """A read observed mixed-layout or digest-mismatched coverage."""


class CoverageGap(FailClosed):
    """A read observed incomplete coverage for its pinned key range."""


def ensure_schema(con):
    con.executescript(W9_SCHEMA)


# ---- deterministic content oracle (shared by fold path and read path) ----

def key_value(gen, k):
    """Deterministic logical content of key k under logical generation gen."""
    return hashlib.sha256(f"{gen}:{k}".encode()).hexdigest()


def seg_digest(gen, lo, hi):
    h = hashlib.sha256()
    for k in range(lo, hi + 1):
        h.update(key_value(gen, k).encode())
    return h.hexdigest()


def partition(lo, hi, nsegs):
    """Split [lo, hi] into n contiguous non-empty segments."""
    total = hi - lo + 1
    if nsegs < 1 or nsegs > total:
        raise Reject("BAD_SEGMENTS", f"nsegs={nsegs} for {total} keys")
    out, start = [], lo
    for i in range(nsegs):
        ln = total // nsegs + (1 if i < total % nsegs else 0)
        out.append((start, start + ln - 1))
        start += ln
    return out


# ---- layout lifecycle ----

def current_pub(con, gen):
    row = con.execute("SELECT layout_id,fold_seq FROM w9_pub WHERE gen=?",
                      (gen,)).fetchone()
    return (row[0], int(row[1])) if row else (None, -1)


def seed_layout(con, fence, gen, K, nsegs=8):
    """Setup-time initial PUBLISHED layout + pub row (fenced txn)."""
    if K > W9_CAPS["max_keys"] or nsegs > W9_CAPS["max_segments_per_layout"]:
        raise Reject("W9_CAP", "seed exceeds experimental caps")
    con.execute("BEGIN IMMEDIATE;")
    try:
        fence.check(con)  # FIRST read: fenced write
        if current_pub(con, gen)[0] is not None:
            raise Reject("ALREADY_SEEDED", f"gen {gen} already published")
        lid = f"lay-{_uuid.uuid4().hex[:12]}"
        t = time.time()
        con.execute("INSERT INTO w9_layouts(layout_id,fold_seq,gen,covers_lo,"
                    "covers_hi,state,protected_gen,created_at) "
                    "VALUES(?,0,?,0,?,'PUBLISHED',?,?)",
                    (lid, gen, K - 1, gen, t))
        for slo, shi in partition(0, K - 1, nsegs):
            con.execute("INSERT INTO w9_segments(layout_id,seg_lo,seg_hi,digest)"
                        " VALUES(?,?,?,?)", (lid, slo, shi, seg_digest(gen, slo, shi)))
        con.execute("INSERT INTO w9_pub(gen,layout_id,fold_seq,published_at)"
                    " VALUES(?,?,0,?)", (gen, lid, t))
        con.execute("COMMIT;")
    except Exception:
        if con.in_transaction:
            con.execute("ROLLBACK;")
        raise
    return {"fold_id": "seed", "fold_seq": 0, "layout": lid}


def fold(con, fence, gen, K, nsegs, fold_id=None):
    """One production fold: build replacement coverage + publish it via a
    reference swing inside ONE commit transaction (I3.4). The logical
    generation is UNCHANGED (folds advance nothing). Old layout -> RETIRED
    (rows persist for pinned readers; drain reclaims after unpin).
    Returns the fold record (fold ID, layout pre/post)."""
    if nsegs > W9_CAPS["max_segments_per_layout"]:
        raise Reject("W9_CAP", f"nsegs={nsegs} exceeds cap")
    fid = fold_id or f"fold-{_uuid.uuid4().hex[:12]}"
    con.execute("BEGIN IMMEDIATE;")
    try:
        fence.check(con)  # FIRST read: fenced write
        nlay = con.execute("SELECT COUNT(*) FROM w9_layouts").fetchone()[0]
        if nlay >= W9_CAPS["max_layouts"]:
            raise Reject("W9_CAP", "layout count cap hit (bounded growth)")
        pre_lid, pre_seq = current_pub(con, gen)
        if pre_lid is None:
            raise Reject("NO_PUBLICATION", f"gen {gen} has no layout; seed first")
        nseq = pre_seq + 1
        lid = f"lay-{_uuid.uuid4().hex[:12]}"
        t = time.time()
        # prepared replacement: invisible until the swing below (same txn, I3.5)
        con.execute("INSERT INTO w9_layouts(layout_id,fold_seq,gen,covers_lo,"
                    "covers_hi,state,protected_gen,created_at) "
                    "VALUES(?,?,?,0,?,'PREPARED',?,?)",
                    (lid, nseq, gen, K - 1, gen, t))
        for slo, shi in partition(0, K - 1, nsegs):
            con.execute("INSERT INTO w9_segments(layout_id,seg_lo,seg_hi,digest)"
                        " VALUES(?,?,?,?)", (lid, slo, shi, seg_digest(gen, slo, shi)))
        # reference swing: publish replacement, retire predecessor (I3.4)
        con.execute("UPDATE w9_pub SET layout_id=?,fold_seq=?,published_at=? "
                    "WHERE gen=?", (lid, nseq, t, gen))
        con.execute("UPDATE w9_layouts SET state='PUBLISHED' WHERE layout_id=?",
                    (lid,))
        con.execute("UPDATE w9_layouts SET state='RETIRED' WHERE layout_id=?",
                    (pre_lid,))
        con.execute("COMMIT;")
    except Exception:
        if con.in_transaction:
            con.execute("ROLLBACK;")
        raise
    return {"fold_id": fid, "fold_seq": nseq, "gen": gen,
            "layout_pre": pre_lid, "layout_post": lid, "nsegs": nsegs}


def fold_all(stores, gen, K, nsegs, fold_id=None):
    """Multi-store publication: the same fold (one fold_id, one fold_seq per
    store's own sequence) applied to every store in the set. Each store's
    swing is its own single txn (I3.4 per store); cross-store consistency is
    VERIFIED post-hoc by pub_consistency(), never assumed.
    stores: list of (store, fence). Returns per-store fold records."""
    fid = fold_id or f"fold-{_uuid.uuid4().hex[:12]}"
    out = []
    for st, fn in stores:
        con = st.open_db()
        try:
            r = fold(con, fn, gen, K, nsegs, fold_id=fid)
            r["store"] = st.root
            out.append(r)
        finally:
            con.close()
    return out


def pub_consistency(stores, gen):
    """Check multi-store publication consistency: same (layout content,
    fold_seq) everywhere. Layout IDs are per-store unique by construction,
    so consistency = same fold_seq + same segment digests for the published
    layout. Returns (consistent, per-store detail)."""
    detail = {}
    for st, _fn in stores:
        con = st.open_db()
        try:
            pub = con.execute("SELECT layout_id,fold_seq FROM w9_pub WHERE gen=?",
                              (gen,)).fetchone()
            if pub is None:
                detail[st.root] = {"published": False}
                continue
            segs = con.execute("SELECT seg_lo,seg_hi,digest FROM w9_segments "
                               "WHERE layout_id=? ORDER BY seg_lo", (pub[0],)).fetchall()
            detail[st.root] = {"published": True, "layout_id": pub[0],
                               "fold_seq": int(pub[1]),
                               "segments": [(int(a), int(b), c) for a, b, c in segs]}
        finally:
            con.close()
    pubs = [d for d in detail.values() if d.get("published")]
    ok = (len(pubs) == len(stores) and len({p["fold_seq"] for p in pubs}) == 1
          and len({tuple(p["segments"]) for p in pubs}) == 1)
    return ok, detail


# ---- read path (pinned readers) ----

def read_pinned(con, gen, lo, hi):
    """Resolve EXACTLY ONE layout from the publication row, then verify its
    segments cover [lo,hi] contiguously with recomputed digests. Raises
    TornRead / CoverageGap (FailClosed) on any violation. Returns the read
    record (layout used, segment count, key count)."""
    pub = con.execute("SELECT layout_id,fold_seq FROM w9_pub WHERE gen=?",
                      (gen,)).fetchone()
    if pub is None:
        raise CoverageGap(f"no publication for gen {gen}")
    lid, fseq = pub[0], int(pub[1])
    segs = con.execute("SELECT seg_lo,seg_hi,digest FROM w9_segments "
                       "WHERE layout_id=? ORDER BY seg_lo", (lid,)).fetchall()
    if not segs:
        raise CoverageGap(f"layout {lid} has no segments (reclaimed under pin?)")
    # single-layout check is structural (WHERE layout_id=?); contiguity + digests:
    expect = lo
    for slo, shi, dg in segs:
        if int(slo) > hi or int(shi) < lo:
            continue
        c_lo, c_hi = max(int(slo), lo), min(int(shi), hi)
        if c_lo != expect:
            raise CoverageGap(f"layout {lid}: gap at key {expect} "
                              f"(covers [{lo},{hi}] incompletely)")
        if dg != seg_digest(gen, int(slo), int(shi)):
            raise TornRead(f"layout {lid}: segment [{slo},{shi}] digest mismatch")
        expect = c_hi + 1
        if expect > hi:
            break
    if expect <= hi:
        raise CoverageGap(f"layout {lid}: incomplete coverage, missing [{expect},{hi}]")
    return {"layout_id": lid, "fold_seq": fseq, "segments": len(segs),
            "keys": hi - lo + 1}


# ---- drain (bounded, resumable; the worker seam) ----

def drain(con, live_pins_fn, owner, budget, cursor=None):
    """One bounded drain pass over RETIRED layouts ordered by fold_seq.
    live_pins_fn() returns the live protected-gen set (fresh per decision,
    W8-RECTIFY lesson: per-candidate freshness vs concurrent claim+nominate).
    Protected (gen live) => stays RETIRED; unprotected => segments deleted,
    state RECLAIMED. Budgets bound effort, never force deletion.
    Returns (per_item, new_cursor, more, work)."""
    rows = con.execute("SELECT layout_id,fold_seq,protected_gen FROM w9_layouts "
                       "WHERE state='RETIRED' AND fold_seq>? ORDER BY fold_seq",
                       (cursor if cursor is not None else -1,)).fetchall()
    out, work = [], 0
    new_cursor = cursor
    for lid, fseq, pg in rows[:budget]:
        new_cursor = int(fseq)
        work += 1
        try:
            live = set(live_pins_fn())
        except Exception:
            out.append((lid, RETIRED))  # uncertainty retains
            continue
        if pg is not None and pg in live:
            out.append((lid, RETIRED))  # pin-protected: reclamation waits
        else:
            con.execute("DELETE FROM w9_segments WHERE layout_id=?", (lid,))
            con.execute("UPDATE w9_layouts SET state='RECLAIMED' WHERE layout_id=?",
                        (lid,))
            out.append((lid, RECLAIMED))
    con.commit()
    return (out, new_cursor, len(rows) > budget, work)


def census(con):
    """Terminal-state census: states + segment rows + pin-relevant accounting."""
    states = {r[0]: r[1] for r in con.execute(
        "SELECT state,COUNT(*) FROM w9_layouts GROUP BY state").fetchall()}
    nseg = con.execute("SELECT COUNT(*) FROM w9_segments").fetchone()[0]
    retired_segs = con.execute("SELECT COUNT(*) FROM w9_segments WHERE layout_id IN "
                               "(SELECT layout_id FROM w9_layouts "
                               "WHERE state='RETIRED')").fetchone()[0]
    return {"layouts_by_state": states, "segment_rows": int(nseg),
            "retired_segment_rows": int(retired_segs)}


def eligible_unreclaimed(con, live_pins_fn):
    """Post-drain verification: RETIRED layouts whose protected_gen is NOT
    live (i.e. eligible) but not yet RECLAIMED. Non-empty after a completed
    drain = FAIL."""
    live = set(live_pins_fn())
    rows = con.execute("SELECT layout_id,protected_gen FROM w9_layouts "
                       "WHERE state='RETIRED'").fetchall()
    return [lid for lid, pg in rows if pg not in live]
