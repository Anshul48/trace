"""Self-validation PASS test: fresh canary binary run exits 0 VALID."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix1_common import OWN, PY


def main():
    out = Path(tempfile.mkdtemp(prefix='fix1-selfval-'))
    proc = subprocess.run(['nice', '-n', '19', PY, '-B', str(OWN / 'canary.py'),
                           '--out', str(out)], capture_output=True, text=True,
                          timeout=600)
    print(proc.stdout.strip().splitlines()[-3:])
    assert proc.returncode == 0, (proc.returncode, proc.stderr[-2000:])
    assert '"status": "VALID"' in proc.stdout, proc.stdout[-500:]
    print('PASS test_selfvalidation (exit 0 VALID)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
