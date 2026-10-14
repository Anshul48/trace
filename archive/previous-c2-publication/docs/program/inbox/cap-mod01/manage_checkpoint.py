#!/usr/bin/env python3
"""Checkpoint Management Utility for CAP-MOD01 Bake-Off.

Usage:
    python manage_checkpoint.py status
    python manage_checkpoint.py reset-finalists
    python manage_checkpoint.py trim-to-pilot
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import shutil
import sys

DEFAULT_CKPT = Path(__file__).parent / "bakeoff_checkpoint.json"
FINALIST_IDS = ["gemma4:26b", "qwen3.8:27b"]


def get_checkpoint_path(custom_path: str | None = None) -> Path:
    if custom_path:
        p = Path(custom_path)
    else:
        p = DEFAULT_CKPT
    return p


def backup_checkpoint(p: Path) -> Path:
    if not p.exists():
        print(f"[INFO] Checkpoint does not exist at {p}; skipping backup.")
        return p
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = p.parent / f"{p.stem}.backup_{ts}.json"
    shutil.copy2(p, backup_path)
    print(f"[OK] Backed up checkpoint to: {backup_path}")
    return backup_path


def show_status(p: Path) -> None:
    print("=" * 80)
    print(f"CAP-MOD01 CHECKPOINT STATUS: {p}")
    print("=" * 80)
    if not p.exists():
        print("Checkpoint file does NOT exist (100% clean/fresh state).")
        print("Both finalists (gemma4:26b and qwen3.8:27b) will evaluate fresh from cluster 0.")
        print("=" * 80)
        return

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    completed = data.get("completed_tiers", {})
    cache = data.get("cluster_cache", {})

    print("Completed Tiers:")
    if completed:
        for mid, t in completed.items():
            pt = t.get("faithfulness", {}).get("point_estimate", 0.0)
            ce = t.get("clusters_evaluated", 0)
            print(f"  - {mid:<20} | {ce} clusters | Faithfulness: {pt:.4f}")
    else:
        print("  (None)")

    print("\nCached Clusters in Intermediate Cache:")
    if cache:
        for mid, clusters in cache.items():
            indices = sorted(int(k) for k in clusters.keys())
            if indices:
                min_i, max_i = min(indices), max(indices)
                print(f"  - {mid:<20} | {len(indices)} clusters cached (indices {min_i}..{max_i})")
            else:
                print(f"  - {mid:<20} | 0 clusters cached")
    else:
        print("  (None)")
    print("=" * 80)


def sync_progress_json(p: Path) -> Path:
    """Sync docs/program/inbox/cap-mod01/progress.json with checkpoint state."""
    import math

    if not p.exists():
        data = {"total_clusters": 100, "completed_tiers": {}, "cluster_cache": {}}
    else:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

    cache = data.get("cluster_cache", {})
    completed = data.get("completed_tiers", {})

    all_models_meta = [
        {"name": "Extractive Control", "id": "extractive_control", "tier": "Tier 0", "params": "0B (Zero-LLM)"},
        {"name": "Gemma 4 E4B", "id": "gemma4:e4b", "tier": "Tier 1", "params": "4B"},
        {"name": "Qwen3-8B", "id": "qwen3:8b", "tier": "Tier 2", "params": "8B"},
        {"name": "Gemma 4 12B", "id": "gemma4:12b", "tier": "Tier 3", "params": "12B"},
        {"name": "Qwen3.8-27B", "id": "qwen3.8:27b", "tier": "Tier 4", "params": "27B"},
        {"name": "Gemma 4 26B MoE", "id": "gemma4:26b", "tier": "Tier 5", "params": "26B"},
    ]

    target_per_model = data.get("total_clusters", 100)
    models_out = []
    completed_all = 0
    total_all = len(all_models_meta) * target_per_model

    for m in all_models_meta:
        mid = m["id"]
        mname = m["name"]
        if mid in completed:
            c = completed[mid]
            ce = c.get("clusters_evaluated", target_per_model)
            tps = c.get("performance", {}).get("warm_tokens_per_sec")
            p95 = c.get("performance", {}).get("p95_latency_ms")
            inv_rate = c.get("robustness", {}).get("invalid_output_rate", 0.0)
            models_out.append({
                "name": mname,
                "id": mid,
                "tier": m["tier"],
                "params": m["params"],
                "status": "completed",
                "completed_clusters": ce,
                "total_clusters": target_per_model,
                "tokens_per_sec": round(tps, 2) if tps is not None else None,
                "p95_latency_ms": round(p95, 1) if p95 is not None else None,
                "error_rate": round(inv_rate, 4),
                "invalid_rate": round(inv_rate, 4),
            })
            completed_all += ce
        elif mid in cache and cache[mid]:
            clusters = list(cache[mid].values())
            c_done = len(clusters)
            c_tps = sum(c["tps"] for c in clusters) / c_done if c_done else None
            c_lats = sorted(c["latency_ms"] for c in clusters)
            c_p95 = c_lats[int(math.ceil(0.95 * len(c_lats))) - 1] if c_lats else None
            c_inv = sum(1 for c in clusters if c.get("is_invalid"))
            inv_r = c_inv / c_done if c_done else 0.0
            models_out.append({
                "name": mname,
                "id": mid,
                "tier": m["tier"],
                "params": m["params"],
                "status": "in_progress",
                "completed_clusters": c_done,
                "total_clusters": target_per_model,
                "tokens_per_sec": round(c_tps, 2) if c_tps is not None else None,
                "p95_latency_ms": round(c_p95, 1) if c_p95 is not None else None,
                "error_rate": round(inv_r, 4),
                "invalid_rate": round(inv_r, 4),
            })
            completed_all += c_done
        else:
            models_out.append({
                "name": mname,
                "id": mid,
                "tier": m["tier"],
                "params": m["params"],
                "status": "pending",
                "completed_clusters": 0,
                "total_clusters": target_per_model,
                "tokens_per_sec": None,
                "p95_latency_ms": None,
                "error_rate": 0.0,
                "invalid_rate": 0.0,
            })

    progress_path = p.parent / "progress.json"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pct = round((completed_all / max(1, total_all)) * 100, 1)

    payload = {
        "notice": "[TEMPORARY MONITORING TOOLING — SCHEDULED FOR REMOVAL UPON WAVE C COMPLETION]",
        "task_id": "CAP-MOD01",
        "task_name": "Sequential Model Bake-Off on 100 Frozen Atom Clusters",
        "status": "completed" if completed_all >= total_all else "in_progress",
        "active_model": "Gemma 4 26B MoE (Phase B Finalist - Ready)",
        "total_clusters_all_models": total_all,
        "completed_clusters_all_models": completed_all,
        "overall_progress_percent": pct,
        "updated_at": now_iso,
        "models": models_out,
        "logs": [
            {
                "timestamp": now_iso,
                "level": "INFO",
                "message": f"Checkpoint synced: {completed_all}/{total_all} clusters completed ({pct}%). Finalists ready for Phase B evaluation.",
            }
        ],
    }

    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[OK] Synced progress file: {progress_path} ({completed_all}/{total_all} clusters, {pct}%)")
    return progress_path


def reset_finalists(p: Path) -> None:
    backup_checkpoint(p)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    cache = data.get("cluster_cache", {})
    completed = data.get("completed_tiers", {})

    cleared = []
    for fid in FINALIST_IDS:
        if fid in cache and cache[fid]:
            count = len(cache[fid])
            cache[fid] = {}
            cleared.append(f"{fid} ({count} cached clusters cleared)")
        if fid in completed:
            del completed[fid]
            cleared.append(f"{fid} (removed from completed_tiers)")

    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"[OK] Successfully reset finalists in {p}:")
    for item in cleared:
        print(f"  - {item}")
    print("[OK] Tiers 0-3 (Extractive Control, Gemma 4 E4B, Qwen3-8B, Gemma 4 12B) preserved intact.")

    # Resync progress.json immediately so UI reflects the fresh state
    sync_progress_json(p)
    print("Now run_phaseB_bakeoff.bat will evaluate gemma4:26b and qwen3.8:27b completely fresh from cluster 0!")


def trim_to_pilot(p: Path) -> None:
    backup_checkpoint(p)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    cache = data.get("cluster_cache", {})
    completed = data.get("completed_tiers", {})

    trimmed = []
    for fid in FINALIST_IDS:
        if fid in completed:
            del completed[fid]
        if fid in cache:
            old_keys = list(cache[fid].keys())
            cache[fid] = {k: v for k, v in cache[fid].items() if int(k) < 10}
            new_count = len(cache[fid])
            trimmed.append(f"{fid}: kept {new_count}/10 pilot clusters (removed {len(old_keys) - new_count} clusters >= 10)")

    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"[OK] Successfully trimmed finalists in {p}:")
    for item in trimmed:
        print(f"  - {item}")
    print("[OK] Clusters 0-9 preserved as pre-schema baseline; clusters 10-99 will evaluate live under schema.")
    sync_progress_json(p)


def delete_all_checkpoints(p: Path) -> None:
    deleted = []
    # Delete main checkpoint
    if p.exists():
        p.unlink()
        deleted.append(p.name)

    # Delete all backup/baseline checkpoints in same folder
    for f in p.parent.glob("bakeoff_checkpoint*.json"):
        f.unlink()
        deleted.append(f.name)

    print("=" * 80)
    print("CAP-MOD01 CHECKPOINT DELETION COMPLETE:")
    if deleted:
        for d in sorted(set(deleted)):
            print(f"  - Deleted: {d}")
    else:
        print("  (No existing checkpoint files found)")
    print("[OK] All past checkpoints removed. Finalists will run 100% fresh from cluster 0.")
    print("=" * 80)
    sync_progress_json(p)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage CAP-MOD01 checkpoint cache.")
    parser.add_argument(
        "action",
        choices=["status", "reset-finalists", "trim-to-pilot", "sync-progress", "delete-all", "reset-all"],
        help="Action to perform",
    )
    parser.add_argument("--checkpoint", type=str, default=None, help="Path to bakeoff_checkpoint.json")
    args = parser.parse_args()

    p = get_checkpoint_path(args.checkpoint)
    if args.action == "status":
        show_status(p)
    elif args.action == "reset-finalists":
        reset_finalists(p)
    elif args.action == "trim-to-pilot":
        trim_to_pilot(p)
    elif args.action == "sync-progress":
        sync_progress_json(p)
    elif args.action in ("delete-all", "reset-all"):
        delete_all_checkpoints(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
