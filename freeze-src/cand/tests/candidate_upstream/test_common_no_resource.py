#!/usr/bin/env python3
"""common.py must import where `resource` is absent (Windows).

Simulates the POSIX-only `resource` module missing (as on Windows,
where `import resource` raises ModuleNotFoundError and broke the
GPU-encode chunker load chain): with `sys.modules["resource"] = None`,
`import common` must still succeed, and `rss_mb()` must fail loud
(RuntimeError) rather than fabricate a reading. With `resource`
present, `rss_mb()` must return a positive float (normal path intact).

Usage: test_common_no_resource.py --sut <tl-candidate-batch/candidate>
"""
import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sut", required=True)
    args = ap.parse_args()
    sut = os.path.abspath(args.sut)
    if not os.path.isfile(os.path.join(sut, "common.py")):
        print("BLOCKED: SUT missing common.py")
        return 2
    sys.path.insert(0, sut)
    fails = []

    def check(name, cond, detail=""):
        print(("pass " if cond else "FAIL ") + name, detail if not cond else "")
        if not cond:
            fails.append(name)

    for m in ("common", "resource"):
        sys.modules.pop(m, None)
    # Simulate Windows: `import resource` raises.
    sys.modules["resource"] = None
    try:
        import common as common_nores
        check("import-without-resource", True)
    except ImportError as e:
        check("import-without-resource", False, repr(e))
        common_nores = None
    if common_nores is not None:
        try:
            common_nores.rss_mb()
            check("rss_mb-fails-loud", False, "returned a value with no resource module")
        except RuntimeError as e:
            check("rss_mb-fails-loud", "resource" in str(e).lower(), str(e))
    # Restore: normal path intact.
    sys.modules.pop("resource", None)
    sys.modules.pop("common", None)
    try:
        import common as common_ok
        val = common_ok.rss_mb()
        check("rss_mb-normal-path", isinstance(val, float) and val > 0, repr(val))
    except ImportError as e:
        # Real `resource` genuinely absent (actual Windows): normal-path
        # check cannot run here; the two checks above are the coverage.
        print("skip rss_mb-normal-path (no resource module on this host):", e)
    # Same Windows-absence treatment for store.py's POSIX-only fcntl
    # (OFD fence locks): import must succeed, acquire must fail closed.
    for m in ("store", "fcntl", "common"):
        sys.modules.pop(m, None)
    sys.modules["fcntl"] = None
    try:
        import store as store_nofcntl
        check("store-import-without-fcntl",
              store_nofcntl.fcntl is None)
    except ImportError as e:
        check("store-import-without-fcntl", False, repr(e))
        store_nofcntl = None
    if store_nofcntl is not None:
        from common import FailClosed
        try:
            store_nofcntl.Fence(store=None).acquire()
            check("fence-acquire-fails-closed", False,
                  "acquired without OFD locks")
        except FailClosed as e:
            check("fence-acquire-fails-closed",
                  "unavailable" in str(e).lower(), str(e))
    sys.modules.pop("fcntl", None)
    sys.modules.pop("store", None)
    sys.modules.pop("common", None)
    print("done: %d failures" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
