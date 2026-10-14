"""Evidence harness: preserve explicit Python deletes from inherited code/tests.

The target path still becomes absent, as expected by recovery fixtures, while
the bytes are renamed alongside it. Never installed by the product modules.
SQLite's internal WAL lifecycle is outside Python's unlink API.
"""
import os
from pathlib import Path
import shutil
import uuid


def install():
    def preserve(path, *, dir_fd=None):
        path = os.fspath(path)
        if dir_fd is not None:
            path = os.path.join(os.readlink(f'/proc/self/fd/{dir_fd}'), path)
        if not os.path.lexists(path):
            raise FileNotFoundError(path)
        dest = path + '.preserved-' + uuid.uuid4().hex
        os.rename(path, dest)
    def preserve_tree(path, ignore_errors=False, onerror=None, *, dir_fd=None, **kwargs):
        try:
            preserve(path, dir_fd=dir_fd)
        except OSError:
            if not ignore_errors:
                raise
    os.remove = preserve
    os.unlink = preserve
    shutil.rmtree = preserve_tree

