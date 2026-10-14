"""Shared harness for Fix-1 tests: paths + synthetic fixture comparison."""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OWN = HERE.parent
FORK = OWN / 'fork'
sys.path.insert(0, str(OWN))
sys.path.insert(0, str(FORK / 'tools'))
sys.path.insert(0, str(FORK / 'fork' / 'tl-sys'))
sys.path.insert(0, str(FORK / 'fork' / 'tl-candidate-batch' / 'candidate'))

import drain_instrument as di  # noqa: E402
import canary  # noqa: E402

PY = '/tmp/baseline-venv/bin/python'


def fresh_service(tmp):
    return canary.build(Path(tmp))


def ingest_all(service, n=canary.N_DOCS):
    docs = canary.fixture_docs(n)
    service.ingest_visible(docs, canary.FakeEmbed())
    service.last_future.result()
    return docs


def final_state(service, tl):
    return {'pin': list(tl.pin()), 'atoms': di.served_atoms(service),
            'commits': di.commits_after(tl)}


def close(service, tl):
    try:
        service.close()
    except Exception:
        pass
    try:
        tl.close()
    except Exception:
        pass
