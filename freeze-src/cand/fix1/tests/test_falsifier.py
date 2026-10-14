"""Falsifier test: one corrupted record must turn the canary NO-GO (exit 1)."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix1_common import OWN, PY


def corrupt(path):
    lines = Path(path).read_text().splitlines()
    assert len(lines) >= 2, 'need >=2 cycle records to falsify one'
    record = json.loads(lines[1])
    record['wall_s'] = record['wall_s'] * 5.0  # break 15% wall agreement
    lines[1] = json.dumps(record)
    Path(path).write_text('\n'.join(lines) + '\n')


def main():
    out = Path(tempfile.mkdtemp(prefix='fix1-fals-'))
    run = subprocess.run(['nice', '-n', '19', PY, '-B',
                          str(OWN / 'canary.py'), '--out', str(out)],
                         capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, (run.returncode, run.stderr[-2000:])
    corrupt(out / 'drain-cycles.jsonl')
    check = subprocess.run([PY, '-B', str(OWN / 'canary.py'),
                            '--out', str(out), '--check'],
                           capture_output=True, text=True, timeout=120)
    print(check.stdout.strip().splitlines()[-4:])
    assert check.returncode == 1, (check.returncode, check.stdout[-1000:])
    assert 'NO-GO' in check.stdout, check.stdout[-500:]
    print('PASS test_falsifier (corrupted wall_s -> exit 1 NO-GO)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
