# SPDX-License-Identifier: Apache-2.0
"""Run the frozen publication suite, excluding one build-host-only test.

The frozen test ``FlagOffIdentity.test_original_source_bytes_unchanged``
compares the frozen fork against the original upstream source tree at a
hardcoded build-host path (``/mnt/c/.../trace-architecture``). That tree
is not part of the 207-file freeze and does not exist on GitHub runners
or other machines, where the test can only fail with ``count == 0``.

This wrapper (outside the freeze) leaves every frozen byte untouched:
when the upstream tree is present it runs the full suite unchanged;
when it is absent it runs all tests except that single build-host-only
comparison and prints an explicit exclusion notice. Set
``TRACE_BUILD_HOST_SOURCE`` to override the upstream path checked.

Usage: python3 tools/run_publication_suite.py <path-to-test_publication.py>
"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

BUILD_HOST_SOURCE = Path(
    os.environ.get(
        "TRACE_BUILD_HOST_SOURCE",
        "/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace-architecture",
    )
)
EXCLUDED = ("FlagOffIdentity", "test_original_source_bytes_unchanged")


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    test_path = Path(sys.argv[1]).resolve()
    # Use the file's own module name and put its directory on sys.path so
    # the suite's spawn-context child processes can re-import their
    # top-level kill-target functions exactly as when run as a script.
    sys.path.insert(0, str(test_path.parent))
    spec = importlib.util.spec_from_file_location("test_publication", test_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    upstream_present = (BUILD_HOST_SOURCE / "tl-sys" / "tlsys").is_dir()
    if upstream_present:
        print(f"upstream source present at {BUILD_HOST_SOURCE}: running full suite")
        selected = suite
    else:
        kept = [
            t
            for t in flatten(suite)
            if (type(t).__name__, getattr(t, "_testMethodName", "")) != EXCLUDED
        ]
        print(
            "EXCLUDED build-host-only test "
            f"{EXCLUDED[0]}.{EXCLUDED[1]}: upstream source tree not found at "
            f"{BUILD_HOST_SOURCE} (not part of the freeze); "
            f"running {len(kept)} remaining tests"
        )
        selected = unittest.TestSuite(kept)

    result = unittest.TextTestRunner(verbosity=2).run(selected)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
