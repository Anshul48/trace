"""Stage-B scratch common: reuses Stage-A impl (W1/W2/W3/W4/W5/P6) as the
production dependency base; Stage B adds W6/W7/W8. Zero repo writes."""
import json
import os
import resource
import sys
import time

sys.path.insert(0, "/tmp/tl-stage-a-2026-09-19/impl")
sys.path.insert(0, "/tmp/tl-stage-b-2026-09-19/impl")

from common import (FailClosed, HeldError, Reject, Retryable,  # noqa: F401,E402
                    du_bytes, now, rss_mb, sha256, uuidv7)

SCRATCH = "/tmp/tl-stage-b-2026-09-19"

MACHINE = {
    "cpu": "AMD Ryzen 7 250 8C/16T x86_64 (WSL2/Microsoft)",
    "ram": "15GiB",
    "disk_tmp": "ext4 /dev/sdd 1007G (901G free at phase1)",
    "shm": "tmpfs 7.7G",
    "python": "3.12.3",
}

ALLOWANCE = {"per_run_wall_s": 600, "suite_wall_s": 7200,
             "scratch_disk_B": 20 * 1024**3, "shm_B": 1024**3,
             "per_probe_rss_B": 1024**3, "max_procs": 8}


class RunRecord:
    """Per-probe-run record: machine + work-per-unit + wall + allowance use."""

    def __init__(self, probe, store_dir):
        self.probe = probe
        self.store_dir = store_dir
        self.t0 = now()
        self.d0 = du_bytes(store_dir) if os.path.isdir(store_dir) else 0
        self.rec = {"probe": probe, "machine": dict(MACHINE),
                    "allowance": dict(ALLOWANCE), "workload": None,
                    "work_per_unit": {}, "events": []}

    def workload(self, w):
        self.rec["workload"] = w
        with open(os.path.join("runs", self.probe, "workload.json"), "w") as f:
            json.dump(w, f, indent=1, sort_keys=True)

    def event(self, **kw):
        kw["t"] = round(now() - self.t0, 4)
        self.rec["events"].append(kw)

    def finish(self, verdict, work_per_unit, note=""):
        wall = now() - self.t0
        self.rec.update({
            "verdict": verdict, "note": note, "wall_s": round(wall, 3),
            "work_per_unit": work_per_unit,
            "allowance_use": {
                "wall_s": round(wall, 3), "wall_within_600": wall <= 600,
                "store_delta_B": du_bytes(self.store_dir) - self.d0,
                "store_total_B": du_bytes(self.store_dir),
                "max_rss_MB_self": round(rss_mb(), 1),
                "rss_within_1GiB": rss_mb() <= 1024.0,
            }})
        if wall > 600:
            self.rec["verdict"] = "BOUNDED-INCOMPLETE"
            self.rec["note"] += " | WALL OVERRUN (>600s) fail-closed"
        with open(os.path.join("runs", self.probe, "evidence.json"), "w") as f:
            json.dump(self.rec, f, indent=1, sort_keys=True)
        return self.rec
