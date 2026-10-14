"""On-disk retained-generation GC (Fix-5): mirror of the pin table.

Runs strictly AFTER the manifest pointer write (the commit point), never
before. Deletes oldest-first down to K retained dirs, SKIPPING any dir
whose frontier is in the reader-pinned set -- a pinned dir is never
removed even when that keeps the directory over K (on-disk mirror of
ViewPool._evict_locked "all retained views are held; keep over cap").

Only ``gen-<int>`` names are ever eligible; ``gen-broken-*`` quarantine
dirs are evidence and are NEVER collected. Eligibility is re-evaluated
from the live listing at every pass, so a dir that becomes unpinned is
collected at the NEXT pass (retire-when-unpinned needs no release hook;
release() stays O(1)-ish and never does I/O deletes under the lock).

Pure function of (dir listing, pinned set, K) at pointer-commit time.
"""

import os
import shutil

ELIGIBLE_PREFIX = "gen-"
NEVER_DELETE_PREFIX = "gen-broken-"


def _frontier_of(name):
    """Frontier ordinal for an eligible name, else None (never eligible)."""
    if not name.startswith(ELIGIBLE_PREFIX):
        return None
    if name.startswith(NEVER_DELETE_PREFIX):
        return None
    tail = name[len(ELIGIBLE_PREFIX):]
    if not tail.isdigit():
        return None
    return int(tail)


def eligible_generations(serving_dir):
    """Sorted [(frontier, name)] of GC-eligible retained generations."""
    from tlsys.serving import generation as gen_mod
    retained = os.path.join(serving_dir, gen_mod.GEN_RETAINED_DIRNAME)
    names = sorted(os.listdir(retained))
    out = []
    for name in names:
        if not os.path.isdir(os.path.join(retained, name)):
            continue
        frontier = _frontier_of(name)
        if frontier is not None:
            out.append((frontier, name))
    return sorted(out)


def collect(serving_dir, keep, pinned=()):
    """Run one GC pass after a committed pointer write.

    keep: retained-generations K (reuses retained_generations_K config).
    pinned: iterable of pinned frontiers (live _retained keys + current).

    Returns a receipt dict with gc_deleted [...], gc_skipped_pinned [...],
    and exactly one of: gc_noop True (list-and-no-op), gc_pinned_over_cap
    True (over K but every excess dir pinned -- no retry until the next
    publication), or neither (a normal collecting pass). gc_error names a
    delete failure; the pass stops at the first error (fail-closed: the
    remaining listing is valid input for the next pass).
    """
    from tlsys.serving import generation as gen_mod
    receipt = {"gc_deleted": [], "gc_skipped_pinned": []}
    pin = set(int(f) for f in pinned)
    try:
        elig = eligible_generations(serving_dir)
    except OSError as exc:
        receipt["gc_error"] = "list-failed: %r" % (exc,)
        return receipt
    if len(elig) <= int(keep):
        receipt["gc_noop"] = True
        return receipt
    retained = os.path.join(serving_dir, gen_mod.GEN_RETAINED_DIRNAME)
    victims = [(f, n) for f, n in elig if f not in pin]
    skipped = sorted(n for f, n in elig if f in pin)
    receipt["gc_skipped_pinned"] = skipped
    # Oldest-first down to K retained dirs, skipping pinned (mirror of
    # _evict_locked: total counts pinned; stop when at cap or when no
    # unpinned victim remains).
    remaining = list(elig)
    for _f, name in sorted(victims):
        if len(remaining) <= int(keep):
            break
        try:
            shutil.rmtree(os.path.join(retained, name))
        except OSError as exc:
            receipt["gc_error"] = "%s: %r" % (name, exc)
            break
        receipt["gc_deleted"].append(name)
        remaining = [(f, n) for f, n in remaining if n != name]
    if len(remaining) > int(keep) and not receipt["gc_deleted"] \
            and "gc_error" not in receipt:
        receipt["gc_pinned_over_cap"] = True
        receipt["gc_pinned_frontiers"] = sorted(pin)
    return receipt
