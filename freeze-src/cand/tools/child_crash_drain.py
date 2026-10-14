"""SIGKILL-crash child: drains at most 1 doc in batched service mode,
pausing at the first after_organize_before_ack fault so the parent can
SIGKILL this tracked PID.
Usage: child_crash_drain.py <store_root> <svc_dir> <pid_file> <ready_file> <log_file>
Own-dir fixture only; store + service dirs are created by the parent test.
"""
import os
import sys
import time

store_root, svc_dir, pid_file, ready_file, log_file = sys.argv[1:6]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "fork", "tl-sys"))
sys.path.insert(0, os.path.join(HERE, "fork", "tl-candidate-batch",
                                "candidate"))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.org_service import OrganizationService, ServiceConfig  # noqa: E402

log = open(log_file, "a", buffering=1)
with open(pid_file, "w") as f:
    f.write(str(os.getpid()))
    f.flush()
    os.fsync(f.fileno())
log.write(f"child pid={os.getpid()}\n")

armed = [True]


def fault(stage):
    if stage == "after_organize_before_ack" and armed[0]:
        armed[0] = False
        with open(ready_file, "w") as f:
            f.write(f"paused pid={os.getpid()} stage={stage}\n")
            f.flush()
            os.fsync(f.fileno())
        log.write("paused at after_organize_before_ack; awaiting SIGKILL\n")
        time.sleep(300)  # parent SIGKILLs the tracked PID here


cfg = ServiceConfig(enabled=True, drain_budget_seconds=600,
                    max_documents_per_drain=64, batched_drain=True)
tl = TLStore(store_root)
svc = OrganizationService(tl, config=cfg, directory=svc_dir,
                          keyed_state=True, fault=fault)
try:
    rep = svc.drain(max_documents=1)
    log.write(f"drain returned (unexpected): {rep}\n")
finally:
    try:
        svc.close()
    except Exception as e:  # noqa: BLE001
        log.write(f"close: {e!r}\n")
    tl.close()
