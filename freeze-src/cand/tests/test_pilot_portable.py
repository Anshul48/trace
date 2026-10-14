"""Portable pilot-harness acceptance: args/env resolution, token caps,
preserved oracle/lifecycle markers, dependency-free --help. No real cache,
no product imports, no compute beyond NumPy statics."""
import inspect
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent.parent / 'tools'
PILOT_SRC = (TOOLS / 'product_pilot.py').read_text()
PREFIX_SRC = (TOOLS / 'real_prefix.py').read_text()

sys.path.insert(0, str(TOOLS))
import product_pilot as pilot  # noqa: E402  (numpy+stdlib only at import)


def test_no_hardcoded_absolute_paths():
    for src in (PILOT_SRC, PREFIX_SRC):
        assert '/home/' not in src and '/mnt/' not in src


def test_file_parent_defaults_and_env_override(monkeypatch):
    monkeypatch.delenv('PILOT_SOURCE_ROOT', raising=False)
    monkeypatch.delenv('PILOT_DATA_DIR', raising=False)
    monkeypatch.delenv('PILOT_TLSYS_DIR', raising=False)
    monkeypatch.delenv('PILOT_CANDIDATE_DIR', raising=False)
    blank = Namespace(source_root=None, data_dir=None, tlsys_dir=None,
                      candidate_dir=None, tools_dir=None)
    paths = pilot.resolve_paths(blank)
    assert paths.tools_dir == pilot.TOOL_DIR
    assert paths.source_root == pilot.TOOL_DIR.parent
    assert paths.data_dir == paths.source_root / 'data'
    assert paths.tlsys_dir == paths.source_root / 'fork' / 'tl-sys'
    assert paths.cand_dir == paths.source_root / 'fork' / 'tl-candidate-batch' / 'candidate'
    monkeypatch.setenv('PILOT_SOURCE_ROOT', '/tmp/x-root')
    monkeypatch.setenv('PILOT_DATA_DIR', '/tmp/x-data')
    paths = pilot.resolve_paths(blank)
    assert str(paths.source_root) == '/tmp/x-root'
    assert str(paths.data_dir) == '/tmp/x-data'


def test_token_caps_local_1m_vm_10m():
    assert pilot.check_token_cap(1_000_000, 'local') == 1_000_000
    assert pilot.check_token_cap(10_000_000, 'vm') == 10_000_000
    for tokens, profile in ((0, 'local'), (1_000_001, 'local'),
                            (10_000_001, 'vm'), (-5, 'vm')):
        try:
            pilot.check_token_cap(tokens, profile)
        except SystemExit:
            pass
        else:
            raise AssertionError(f'cap accepted {tokens} {profile}')


def test_tie_recall_exactness_preserved():
    scores = np.array([0.9, 0.8, 0.7] + [0.5] * 10)
    aids = [f'a{i}' for i in range(13)]
    assert pilot.tie_recall(scores, aids, aids[:10]) == 1.0
    assert pilot.tie_recall(scores, aids, aids[:3]) == 0.3
    got = aids[:3] + aids[3:8]  # 3 strict + 5 of 10 boundary ties
    assert pilot.tie_recall(scores, aids, got) == 0.8
    assert pilot.tie_recall(np.array([]), [], []) == 0.0


def test_oracle_and_lifecycle_markers_preserved():
    for marker in ('size=120', 'matched_work', 'leave_source_out',
                   'after_prepare', 'after_organize_before_ack', 'dedup',
                   'orphan_children', 'anchors[0].generation',
                   'source-pin.json', 'memory.json'):
        assert marker in PILOT_SRC, marker
    for marker in ('tl-gpu-embcache-v1', 'TOK_V1', 'complete_documents',
                   'normalize_embeddings', 'data_dir'):
        assert marker in PREFIX_SRC, marker


def test_help_runs_without_product_deps():
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    proc = subprocess.run([sys.executable, '-B', str(TOOLS / 'product_pilot.py'),
                           '--help'], capture_output=True, text=True,
                          timeout=120, env=env)
    assert proc.returncode == 0, proc.stderr
    for flag in ('--profile', '--source-root', '--data-dir', '--tlsys-dir',
                 '--candidate-dir', '--tools-dir', '--tokens', '--out'):
        assert flag in proc.stdout, flag


def test_mem_observation_helper():
    assert isinstance(pilot.read_mem_kb(), int)


def test_real_prefix_data_dir_param():
    sys.path.insert(0, str(TOOLS))
    import real_prefix as rp
    assert 'data_dir' in inspect.signature(rp.RealPrefix.__init__).parameters
    assert rp.default_data_dir() == rp.TOOL_DIR.parent / 'data'
