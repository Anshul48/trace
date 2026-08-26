"""Self-hosted production admission checks.

These checks intentionally reject an undersized installation instead of
turning a developer laptop into an accidental production declaration. They are
not a substitute for the measured 100K baseline and 1M production gate; the
10M/500-QPS program is a separate later scale release.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PreflightResult:
    passed: bool
    checks: dict[str, dict[str, Any]]

    def raise_for_failure(self) -> None:
        failed = [name for name, value in self.checks.items() if not value["passed"]]
        if failed:
            raise RuntimeError("self-hosted production preflight failed: " + ", ".join(failed))


def _memory_bytes() -> int | None:
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong), ("avail_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended_virtual", ctypes.c_ulonglong),
            ]
        state = MemoryStatus()
        state.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            return int(state.total_phys)
    except Exception:
        pass
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages) * int(page_size)
    except (AttributeError, ValueError, OSError):
        return None


def run_self_hosted_preflight(
    *,
    data_path: str | os.PathLike[str] = ".",
    minimum_ram_gib: int | None = None,
    minimum_free_disk_gib: int | None = None,
    require_gpu: bool | None = None,
) -> PreflightResult:
    """Measure non-secret local capacity checks and return a stable report."""

    minimum_ram_gib = int(minimum_ram_gib or os.environ.get("TRACE_MIN_RAM_GIB", "64"))
    minimum_free_disk_gib = int(minimum_free_disk_gib or os.environ.get("TRACE_MIN_FREE_DISK_GIB", "500"))
    require_gpu = (
        os.environ.get("TRACE_REQUIRE_GPU", "false").lower() == "true"
        if require_gpu is None else require_gpu
    )
    gib = 1024 ** 3
    memory = _memory_bytes()
    disk = shutil.disk_usage(Path(data_path).resolve())
    gpu_present = bool(os.environ.get("NVIDIA_VISIBLE_DEVICES") and os.environ.get("NVIDIA_VISIBLE_DEVICES") != "void")
    checks: dict[str, dict[str, Any]] = {
        "ram": {
            "passed": memory is not None and memory >= minimum_ram_gib * gib,
            "required_gib": minimum_ram_gib,
            "observed_gib": round(memory / gib, 2) if memory is not None else None,
        },
        "free_disk": {
            "passed": disk.free >= minimum_free_disk_gib * gib,
            "required_gib": minimum_free_disk_gib,
            "observed_gib": round(disk.free / gib, 2),
            "path": str(Path(data_path).resolve()),
        },
        "gpu": {
            "passed": gpu_present or not require_gpu,
            "required": require_gpu,
            "observed": gpu_present,
        },
        "backup_target": {
            "passed": bool(os.environ.get("TRACE_BACKUP_TARGET")),
            "detail": "TRACE_BACKUP_TARGET must name an independently recoverable backup destination.",
        },
        "replication": {
            "passed": bool(os.environ.get("TRACE_REPLICATION_TARGET")),
            "detail": "TRACE_REPLICATION_TARGET must name a tested database/object replication target.",
        },
    }
    return PreflightResult(passed=all(value["passed"] for value in checks.values()), checks=checks)
