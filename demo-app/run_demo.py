"""One-command launch from a clean checkout: python3 run_demo.py [--port 8765]

If the current interpreter cannot import numpy (required by the frozen
engine), creates ./\.venv and installs only numpy into it (explicit,
bounded), then serves with that interpreter. Set TRACE_FREEZE_SRC if the
frozen candidate is not at ../freeze-src/cand beside this folder.
"""
import subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent

def has_numpy(py):
    return subprocess.call([str(py), "-c", "import numpy"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

def main():
    port = "8765"
    if "--port" in sys.argv:
        port = sys.argv[sys.argv.index("--port") + 1]
    py = Path(sys.executable)
    venv_py = HERE / ".venv" / "bin" / "python"
    if venv_py.exists() and has_numpy(venv_py):
        py = venv_py
    elif not has_numpy(py):
        print("numpy not found; creating demo-app/.venv and installing numpy only...", flush=True)
        subprocess.check_call([sys.executable, "-m", "venv", str(HERE / ".venv")])
        subprocess.check_call([str(venv_py), "-m", "pip", "install", "--quiet", "numpy"])
        py = venv_py
    print(f"TRACE demo: http://127.0.0.1:{port}/  (Ctrl-C to stop)", flush=True)
    raise SystemExit(subprocess.call([str(py), str(HERE / "backend.py"), port]))

if __name__ == "__main__":
    main()
