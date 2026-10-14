"""Chunking access for the GPU stage: import-only use of the frozen
tlsys chunker (same precedent as the trackD encode probe).

There is intentionally NO second chunker implementation here: the GPU
stage must consume byte-identical chunk geometry to the owning ingest
path (tlsys/ingest.py chunk_text: whitespace tokens, 200/chunk,
50-token overlap, exact source slices with UTF-8 byte spans).

If tlsys cannot be imported (wrong working directory), this module
raises with an explicit message instead of silently substituting a
reimplementation.
"""

import hashlib
import os
import sys

_REPO_ROOT_CANDIDATES = ()


def _ensure_repo_root():
    here = os.path.abspath(os.path.dirname(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))
    if os.path.isdir(os.path.join(root, "tl-sys", "tlsys")):
        if root not in sys.path:
            sys.path.insert(0, root)
        if os.path.join(root, "tl-sys") not in sys.path:
            sys.path.insert(0, os.path.join(root, "tl-sys"))
        return root
    raise ImportError(
        "tl-sys/tlsys not found relative to gpu_encode "
        "(expected repo root at %r). Run from the repo root "
        "so `import tlsys` resolves to the frozen ingest path." % (root,))


def get_chunk_text():
    _ensure_repo_root()
    try:
        from tlsys.ingest import chunk_text  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "cannot import tlsys.ingest.chunk_text: %s. The GPU stage "
            "refuses to substitute a reimplemented chunker." % (e,))
    import tlsys.ingest as _ing
    return _ing.chunk_text


def chunker_identity():
    """(source_path, sha256) of the chunker in force — recorded in runs."""
    _ensure_repo_root()
    import tlsys.ingest as _ing
    path = os.path.abspath(_ing.__file__)
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return path, digest


def chunk_geometry():
    """(CHUNK_TOKENS, CHUNK_OVERLAP, BATCH_OPS-independent) in force."""
    _ensure_repo_root()
    import tlsys.ingest as _ing
    return int(_ing.CHUNK_TOKENS), int(_ing.CHUNK_OVERLAP)
