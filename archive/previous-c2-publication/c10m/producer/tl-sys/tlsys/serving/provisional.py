"""Provisional serving profile seeds + Lane G consumption (read-only).

Lane G owns the profile schema + counters API. Until
lane-G/profile-counters.md (+ pointed-to bindings) is published, serving
uses these seeds (spec section 5 initial values). Every run records which
source was used. Polling is bounded: at most _MAX_POLLS refresh() calls per
process unless forced (tests use force=True).
"""

import json
import os

# Spec section 5 initial values. NOT semantic thresholds (those are frozen
# for parity and live with the reference: K1/B/tokenizer/ATOM_SCHEME).
SEEDS = {
    "delta_flush_atoms": 5000,
    "delta_flush_s": 30,
    "merge_fan_in": 8,
    "max_live_segments": 12,
    "retained_generations_K": 3,
    "shortlist_margin_m": 64,
    "dense_eps": 3e-5,
    "reader_poll_ms": 250,
    "compactor_mode": "process",
    "serving_gb_per_generation": 4,
    "wal_gb": 1,
    "nomap_flatten_depth": 16,
    # Closure S: unpublished-suffix overlay debt bounds (gen v2).
    # Exceeding any enabled bound triggers an abortable rebase
    # (publish a new generation, reset the overlay). Bytes/time 0
    # disables that bound (bytes are estimated; time aborts the
    # maintenance cycle and carries the debt explicitly).
    "gen_overlay_max_atoms": 5000,
    "gen_overlay_max_holons": 5000,
    "gen_overlay_max_edges": 20000,
    "gen_overlay_max_bytes": 0,
    "maint_time_budget_s": 0,
    "source": "lane-S-seeds",
}

_MAX_POLLS = 3
_polls = 0
_cache = None


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", ".."))


# S-4 (R8): the Lane-G profile/counter dependency is explicit --
# an explicitly configured dir, never a hardcoded date-stamped
# coordination path and never a sys.path entry (spec_from_file_location
# loads it under a laneg_* name, so lane-G/profile.py cannot shadow
# the stdlib `profile` module). Resolution: TL_C2_LANE_G_DIR env >
# exactly-one in-repo coordination/*/lane-G carrying loadable modules
# > unavailable (callers fall back to seeds / raise ImportError).
LANE_G_ENV = "TL_C2_LANE_G_DIR"


def _lane_g_dir():
    explicit = os.environ.get(LANE_G_ENV)
    if explicit:
        return explicit
    coord = os.path.join(_repo_root(), "coordination")
    try:
        cands = sorted(os.listdir(coord))
    except OSError:
        return None
    found = []
    for cand in cands:
        d = os.path.join(coord, cand, "lane-G")
        if os.path.isfile(os.path.join(d, "counters.py")) or \
                os.path.isfile(os.path.join(d, "profile.py")):
            found.append(d)
    if len(found) == 1:
        return found[0]
    return None


def _load_lane_g_module(name):
    """Read-only import of Lane G's sole-writer module (no copy/fork).

    Returns the module, or None when unavailable. Product code never
    writes to the Lane G dir and never adds it to sys.path.
    """
    import importlib.util
    d = _lane_g_dir()
    if not d:
        return None
    path = os.path.join(d, name + ".py")
    if not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            f"laneg_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except (OSError, ValueError, ImportError, AttributeError):
        return None


# Lane-G derived_limits key -> serving config key.
_LIMIT_MAP = {
    "delta_flush_atoms": "delta_flush_atoms",
    "delta_flush_seconds": "delta_flush_s",
    "merge_fan_in": "merge_fan_in",
    "live_segments_max": "max_live_segments",
    "retained_generations_K": "retained_generations_K",
    "shortlist_margin_m": "shortlist_margin_m",
    "shortlist_epsilon": "dense_eps",
    "reader_poll_ms": "reader_poll_ms",
}


def find_lane_g_bindings():
    """(profile_dict_or_None, note). Read-only; never writes.

    Precedence: lane-G/profile.json (validated by Lane G's own
    validate_profile) > Lane G default_profile() seeds > None.
    Values are mapped to serving keys; the source note is recorded.
    """
    d = _lane_g_dir()
    if not d:
        return None, (f"lane-G unpublished (no {LANE_G_ENV} and no "
                      "single in-repo lane-G); seeds kept")
    md = os.path.join(d, "profile-counters.md")
    js = os.path.join(d, "profile.json")
    if os.path.isfile(js):
        try:
            with open(js) as f:
                raw = json.load(f)
        except (ValueError, OSError) as e:
            return None, f"lane-G profile.json unreadable: {e}"
        profmod = _load_lane_g_module("profile")
        if profmod is not None:
            try:
                profmod.validate_profile(raw)
            except ValueError as e:
                return None, f"lane-G profile.json invalid: {e}"
        return _map_lane_g_profile(raw, f"lane-G:{js}")
    if os.path.isfile(md):
        profmod = _load_lane_g_module("profile")
        if profmod is not None:
            try:
                raw = profmod.default_profile("c2-lanes-dev")
                profmod.validate_profile(raw)
            except (ValueError, AttributeError):
                raw = None
            if raw is not None:
                return _map_lane_g_profile(
                    raw, f"lane-G:{d}/profile.py:default_profile")
        return None, (f"lane-G:{md} exists but carries no machine "
                      "bindings; seeds kept (see REPORT)")
    if os.environ.get(LANE_G_ENV):
        return None, (f"explicit {LANE_G_ENV}={d} carries no "
                      "bindings; seeds kept")
    return None, "lane-G unpublished; seeds kept"


def _map_lane_g_profile(raw, note):
    """Map a Lane-G profile to serving keys. Returns (dict, note)."""
    out = {}
    derived = raw.get("derived_limits", {})
    for src, dst in _LIMIT_MAP.items():
        if src in derived:
            out[dst] = derived[src]
    targets = raw.get("primary_targets", {})
    if "serving_gb_per_generation_max" in targets:
        out["serving_gb_per_generation"] = \
            targets["serving_gb_per_generation_max"]
    if "wal_gb_max" in targets:
        out["wal_gb"] = targets["wal_gb_max"]
    flags = raw.get("flags", {})
    if "compactor_process_mode" in flags:
        out["compactor_mode"] = \
            "process" if flags["compactor_process_mode"] else "inprocess"
    out["lane_g_profile_id"] = raw.get("profile_id")
    out["lane_g_calibration"] = raw.get("calibration_manifest_id")
    return out, note


def serving_config(profile=None, force_refresh=False):
    """Effective serving config dict. Explicit `profile` wins; else Lane G
    bindings when present; else SEEDS. Records `source`."""
    global _polls, _cache
    if profile is not None:
        if isinstance(profile, dict) and "derived_limits" in profile:
            # Lane-G-shaped profile: validate (when Lane G's module
            # loads) + map to serving keys (fail closed on invalid).
            raw = dict(profile)
            profmod = _load_lane_g_module("profile")
            validated = False
            if profmod is not None:
                profmod.validate_profile(raw)
                validated = True
            mapped, _note = _map_lane_g_profile(raw,
                                                "explicit-lane-G-arg")
            out = dict(SEEDS)
            for k in SEEDS:
                if k in mapped:
                    out[k] = mapped[k]
            out["lane_g_profile_id"] = mapped.get("lane_g_profile_id")
            out["lane_g_calibration"] = \
                mapped.get("lane_g_calibration")
            out["lane_g_validated"] = validated
            out["source"] = "explicit-lane-G-arg"
            return out
        out = dict(SEEDS)
        out.update(dict(profile))
        out["source"] = "explicit-arg"
        return out
    if _cache is not None and not force_refresh:
        return dict(_cache)
    if _polls >= _MAX_POLLS and not force_refresh:
        return dict(_cache or SEEDS)
    _polls += 1
    bound, note = find_lane_g_bindings()
    out = dict(SEEDS)
    if bound:
        for k in SEEDS:
            if k in bound:
                out[k] = bound[k]
        for k in ("lane_g_profile_id", "lane_g_calibration"):
            if k in bound:
                out[k] = bound[k]
        out["source"] = note
    else:
        out["poll_note"] = note
    _cache = dict(out)
    return dict(out)


def poll_count():
    return _polls
