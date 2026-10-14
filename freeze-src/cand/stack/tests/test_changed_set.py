"""Changed-set test: stack freeze vs speed parent is EXACTLY the doc set.

Compares /tmp/stack-fork/SOURCEFREEZE.speed-parent.json (dd543d0e) with
cand/SOURCEFREEZE.json: every non-changed file byte-identical, changed
files exactly {product_pilot, org_publication, generation, view} +
added {drain_instrument, gen_gc}. Also AST-parses every changed/added
file and asserts the new entry points exist. No corpus, no heavy work.
"""
import ast
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_common as C  # noqa: E402

MODIFIED = ('tools/product_pilot.py',
            'fork/tl-sys/tlsys/org_publication.py',
            'fork/tl-sys/tlsys/serving/generation.py',
            'fork/tl-sys/tlsys/serving/view.py',
            'tests/test_publication.py')
ADDED = ('tools/drain_instrument.py',
         'fork/tl-sys/tlsys/serving/gen_gc.py')

NEW_DEFS = {
    'tools/product_pilot.py': ('resolve_drain_budget', 'service_config',
                               'DRAIN_ALL_BUDGET_S_DEFAULT'),
    'tools/drain_instrument.py': ('derive_budget_candidate',
                                  'derive_budget_from_cycles_file',
                                  'run_drain_loop', 'DrainRecorder'),
    'fork/tl-sys/tlsys/serving/generation.py':
        ('verify_suffix_against_source', 'verify_against_source',
         'publish_generation'),
    'fork/tl-sys/tlsys/serving/gen_gc.py': ('collect',
                                            'eligible_generations'),
    'fork/tl-sys/tlsys/serving/view.py': ('ViewPool',),
    'fork/tl-sys/tlsys/org_publication.py': ('pending_order',
                                             'PreparedFacade'),
    'tests/test_publication.py': ('FlagOffIdentity',),
}

# Fix-1 hunk markers that must survive inside the stacked pilot.
FIX1_MARKERS = ("'--drain-instrument', action='store_true', default=False",
                'from drain_instrument import DrainRecorder',
                'def note_phase(label):',
                'return run_drain_loop(s, tl, label, walls, await_publication,')
FIX3_MARKERS = ("'--drain-budget-s', type=int, default=None",
                "'--drain-unbatched', action='store_true', default=False",
                'budget_seconds=drain_budget_s')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parent = json.loads(
        (C.CAND.parent / 'SOURCEFREEZE.speed-parent.json').read_text())
    stack = json.loads((C.CAND / 'SOURCEFREEZE.json').read_text())
    pf, sf = parent['files'], stack['files']
    assert len(pf) == 205, len(pf)
    assert len(sf) == 207, len(sf)
    assert stack.get('parent_speed_freeze_sha256') == \
        sha(C.CAND.parent / 'SOURCEFREEZE.speed-parent.json')
    assert stack['parent_speed_freeze_sha256'].startswith('dd543d0e')

    modified, added, removed = [], [], []
    for name, digest in sf.items():
        if name not in pf:
            added.append(name)
        elif pf[name] != digest:
            modified.append(name)
    for name in pf:
        if name not in sf:
            removed.append(name)
    assert sorted(modified) == sorted(MODIFIED), modified
    assert sorted(added) == sorted(ADDED), added
    assert removed == [], removed

    # Every frozen file matches its pinned digest (drift []).
    drift = [n for n, d in sf.items() if sha(C.CAND / n) != d]
    assert drift == [], drift

    # Every changed/added file parses + exposes its entry points.
    for name in MODIFIED + ADDED:
        tree = ast.parse((C.CAND / name).read_text(), filename=name)
        have = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                have.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        have.add(t.id)
        missing = [d for d in NEW_DEFS[name] if d not in have]
        assert not missing, (name, missing)

    # Fix-1 overlay survived the stacking (markers intact).
    pilot_src = (C.CAND / 'tools' / 'product_pilot.py').read_text()
    for marker in FIX1_MARKERS + FIX3_MARKERS:
        assert marker in pilot_src, marker

    # fix1/ sidecar byte-identical to the staged overlay.
    up = Path('/tmp/fix1stage/up')
    pairs = [('fix1/canary.py', 'canary.py'),
             ('tools/product_pilot.py', None),  # stacked further; skip bytes
             ('fix1/tests/test_identity_off.py',
              'fix1tests/test_identity_off.py'),
             ('fix1/tests/test_schema.py', 'fix1tests/test_schema.py'),
             ('fix1/tests/test_falsifier.py', 'fix1tests/test_falsifier.py'),
             ('fix1/tests/test_selfvalidation.py',
              'fix1tests/test_selfvalidation.py'),
             ('fix1/tests/fix1_common.py', 'fix1tests/fix1_common.py')]
    for cand_rel, up_rel in pairs:
        if up_rel is None:
            continue
        assert sha(C.CAND / cand_rel) == sha(up / up_rel), cand_rel

    print('changed-set: modified=%d added=%d removed=0 drift=[] markers ok'
          % (len(modified), len(added)))
    print('PASS test_changed_set')
    return 0


if __name__ == '__main__':
    sys.exit(main())
