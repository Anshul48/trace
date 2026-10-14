"""Lane G: versioned C2 profile (sole-writer impl of profile-counters.md §2)."""
import json

PROFILE_SCHEMA_VERSION = "1.0.0"

_REQUIRED_TOP = ("profile_schema_version", "profile_id",
                 "calibration_manifest_id", "hardware",
                 "primary_targets", "derived_limits",
                 "f5_per_atom_budgets", "flags")
_REQUIRED_PRIMARY = ("catalog_scan_p99_ms", "delta_publish_p99_ms",
                     "query_p99_inflation_max",
                     "serving_gb_per_generation_max", "wal_gb_max")
_REQUIRED_DERIVED_INT = ("R_cat", "delta_flush_atoms",
                         "delta_flush_seconds", "delta_rows_max",
                         "merge_fan_in", "live_segments_max",
                         "retained_generations_K",
                         "shortlist_margin_m", "reader_poll_ms")
_REQUIRED_FLAGS = ("organization_catalog_routing",
                   "serving_segmented", "compactor_process_mode")


def default_profile(profile_id, calibration_manifest_id="seed-host-20261006",
                    hardware=None):
    """Initial §5 seed values. Dev/scouting only; confirmation needs VM calibration."""
    return {
        "profile_schema_version": PROFILE_SCHEMA_VERSION,
        "profile_id": profile_id,
        "calibration_manifest_id": calibration_manifest_id,
        "hardware": hardware or {"host": "unrecorded", "cpu": "unrecorded",
                                 "ram_gb": 0, "disk": "unrecorded"},
        "primary_targets": {
            "catalog_scan_p99_ms": 8.0,
            "delta_publish_p99_ms": 50.0,
            "query_p99_inflation_max": 0.10,
            "serving_gb_per_generation_max": 4.0,
            "wal_gb_max": 1.0,
        },
        "derived_limits": {
            "R_cat": 65536,
            "delta_flush_atoms": 5000,
            "delta_flush_seconds": 30,
            "delta_rows_max": 10000,
            "merge_fan_in": 8,
            "live_segments_max": 12,
            "retained_generations_K": 3,
            "shortlist_margin_m": 64,
            "shortlist_epsilon": 3e-5,
            "reader_poll_ms": 250,
        },
        "f5_per_atom_budgets": {
            "catalog_rows_per_decision_max": "R_cat * catalogs_touched",
            "bytes_written_per_atom_max": "v1_modelled_mean * 1.25",
            "note": ("absolute byte/file ceilings frozen "
                     "pre-confirmation from scouting"),
        },
        "flags": {
            "organization_catalog_routing": False,
            "serving_segmented": False,
            "compactor_process_mode": False,
        },
    }


def validate_profile(p):
    if not isinstance(p, dict):
        raise ValueError("profile must be a dict")
    for k in _REQUIRED_TOP:
        if k not in p:
            raise ValueError(f"profile missing key: {k}")
    if p["profile_schema_version"] != PROFILE_SCHEMA_VERSION:
        raise ValueError("unsupported profile_schema_version: "
                         f"{p['profile_schema_version']!r}")
    for k in _REQUIRED_PRIMARY:
        v = p["primary_targets"].get(k)
        if not isinstance(v, (int, float)) or v <= 0:
            raise ValueError(f"primary_targets.{k} must be positive")
    for k in _REQUIRED_DERIVED_INT:
        v = p["derived_limits"].get(k)
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise ValueError(f"derived_limits.{k} must be a positive int")
    eps = p["derived_limits"].get("shortlist_epsilon")
    if not isinstance(eps, (int, float)) or eps <= 0:
        raise ValueError("derived_limits.shortlist_epsilon must be positive")
    for k in _REQUIRED_FLAGS:
        if p["flags"].get(k) not in (True, False):
            raise ValueError(f"flags.{k} must be a bool")
    if not p["profile_id"] or not p["calibration_manifest_id"]:
        raise ValueError("profile_id and calibration_manifest_id required")
    return True


def load_profile(path):
    with open(path) as f:
        p = json.load(f)
    validate_profile(p)
    return p


def save_profile(p, path):
    validate_profile(p)
    with open(path, "w") as f:
        json.dump(p, f, indent=2, sort_keys=True)
        f.write("\n")
