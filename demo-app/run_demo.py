"""One-command launch from a clean checkout: python3 run_demo.py [--port 8765]

Supported platforms: Linux and macOS (verified on Linux). The venv
interpreter path also follows the Windows layout (`Scripts/python.exe`),
but Windows is not verified. If the current interpreter cannot import
numpy (required by the frozen engine), creates ./.venv and installs only
numpy into it (explicit, bounded), then serves with that interpreter.
Set TRACE_FREEZE_SRC if the frozen candidate is not at
../freeze-src/cand beside this folder.
"""
import shutil, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent


def venv_python(venv_dir):
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"

def has_numpy(py):
    return subprocess.call([str(py), "-c", "import numpy"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

def main():
    port = "8765"
    if "--port" in sys.argv:
        port = sys.argv[sys.argv.index("--port") + 1]
    py = Path(sys.executable)
    venv_py = venv_python(HERE / ".venv")
    if venv_py.exists() and has_numpy(venv_py):
        py = venv_py
    elif not has_numpy(py):
        print("numpy not found; creating demo-app/.venv and installing numpy only...", flush=True)
        if shutil.which("uv"):
            subprocess.check_call(["uv", "venv", str(HERE / ".venv")])
            subprocess.check_call(["uv", "pip", "install", "--python", str(venv_py), "--quiet", "numpy"])
        else:
            try:
                subprocess.check_call([sys.executable, "-m", "venv", str(HERE / ".venv")])
                subprocess.check_call([str(venv_py), "-m", "pip", "install", "--quiet", "numpy"])
            except subprocess.CalledProcessError:
                raise SystemExit("Could not create demo-app/.venv (python3-venv/ensurepip missing?). Install uv or python3-venv, or run with an interpreter that already has numpy.")
        py = venv_py
    print(f"TRACE demo: http://127.0.0.1:{port}/  (Ctrl-C to stop)", flush=True)
    raise SystemExit(subprocess.call([str(py), str(HERE / "backend.py"), port]))

if __name__ == "__main__":
    main()
