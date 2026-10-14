from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolved_wheels(cache: Path, lock_path: Path) -> list[dict[str, object]]:
    """Recover the exact wheel identities recorded by uv's fresh HTTP cache.

    uv's ``*.http`` cache metadata contains the selected wheel filename and its
    repository SHA-256.  The cache is verifier-owned and created empty for this
    sync, so every entry is attributable to this provisioning run.
    """

    lock_text = lock_path.read_text(encoding="utf-8")
    artifacts: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for metadata in sorted(cache.rglob("*.http")):
        raw = metadata.read_bytes()
        filenames = re.findall(rb"[A-Za-z0-9][A-Za-z0-9_.+\-]*\.whl", raw)
        hash_marker = raw.find(b"Sha256")
        hashes = (
            re.findall(rb"[0-9a-f]{64}", raw[hash_marker : hash_marker + 160])
            if hash_marker >= 0
            else []
        )
        if not filenames or not hashes:
            continue
        filename = filenames[0].decode("ascii")
        wheel_hash = hashes[0].decode("ascii")
        key = (filename, wheel_hash)
        if key in seen:
            continue
        seen.add(key)
        artifacts.append(
            {
                "filename": filename,
                "sha256": wheel_hash,
                "locked_hash_match": f"sha256:{wheel_hash}" in lock_text,
                "cache_metadata": metadata.relative_to(cache).as_posix(),
            }
        )
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tree", required=True)
    parser.add_argument("--extra", action="append", default=[])
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--skip-project-install", action="store_true")
    args = parser.parse_args()

    worktree = args.worktree.resolve()
    cache = args.cache.resolve()
    output = args.output.resolve()
    venv = worktree / ".venv"
    if venv.exists():
        raise RuntimeError(f"refusing to reuse existing environment: {venv}")
    if output.exists():
        raise RuntimeError(f"refusing to overwrite provision evidence: {output}")
    output.mkdir(parents=True)
    cache.mkdir(parents=True, exist_ok=False)

    def git(*items: str) -> str:
        return subprocess.check_output(["git", "-C", str(worktree), *items], text=True).strip()

    if git("rev-parse", "HEAD") != args.commit:
        raise RuntimeError("candidate commit mismatch")
    if git("rev-parse", "HEAD^{tree}") != args.tree:
        raise RuntimeError("candidate tree mismatch")
    if git("status", "--porcelain"):
        raise RuntimeError("candidate worktree is not clean")

    dependency_command = [
        "uv",
        "sync",
        "--frozen",
        "--no-install-project",
        "--cache-dir",
        str(cache),
    ]
    if args.offline:
        dependency_command.append("--offline")
    for extra in args.extra:
        dependency_command.extend(["--extra", extra])
    project_command = [
        "uv",
        "sync",
        "--frozen",
        "--offline",
        "--no-build-isolation",
        "--cache-dir",
        str(cache),
    ]
    for extra in args.extra:
        project_command.extend(["--extra", extra])

    started = datetime.now(UTC)
    dependency_proc = subprocess.run(
        dependency_command, cwd=worktree, text=True, capture_output=True
    )
    project_proc = None
    if dependency_proc.returncode == 0 and not args.skip_project_install:
        project_proc = subprocess.run(
            project_command, cwd=worktree, text=True, capture_output=True
        )
    finished = datetime.now(UTC)
    exit_code = (
        dependency_proc.returncode
        if project_proc is None
        else project_proc.returncode
    )
    stdout = "[locked dependencies]\n" + dependency_proc.stdout
    stderr = "[locked dependencies]\n" + dependency_proc.stderr
    if project_proc is not None:
        stdout += "\n[offline local project]\n" + project_proc.stdout
        stderr += "\n[offline local project]\n" + project_proc.stderr
    (output / "uv_sync.stdout.log").write_text(stdout, encoding="utf-8")
    (output / "uv_sync.stderr.log").write_text(stderr, encoding="utf-8")
    receipt = {
        "commands": (
            [dependency_command]
            if args.skip_project_install
            else [dependency_command, project_command]
        ),
        "stage_exit_codes": {
            "locked_dependencies": dependency_proc.returncode,
            "offline_local_project": (
                "skipped_source_checkout_mode"
                if args.skip_project_install
                else None if project_proc is None else project_proc.returncode
            ),
        },
        "cwd": str(worktree),
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "exit_code": exit_code,
        "base_python": sys.version,
        "uv_version": subprocess.check_output(["uv", "--version"], text=True).strip(),
        "candidate_commit": args.commit,
        "candidate_tree": args.tree,
        "uv_lock_sha256": sha256(worktree / "uv.lock"),
        "candidate_execution_mode": (
            "exact_committed_src_via_pythonpath"
            if args.skip_project_install
            else "installed_editable_offline"
        ),
        "environment_created_fresh": not venv.exists() if exit_code else venv.is_dir(),
        "system_site_packages_disabled": False,
    }
    if exit_code == 0:
        config = (venv / "pyvenv.cfg").read_text(encoding="utf-8")
        receipt["system_site_packages_disabled"] = "include-system-site-packages = false" in config.lower()
        receipt["venv_executable"] = str(venv / "Scripts" / "python.exe")
        if not receipt["system_site_packages_disabled"]:
            raise RuntimeError("fresh environment unexpectedly enables system site packages")
        artifacts = resolved_wheels(cache, worktree / "uv.lock")
        if not artifacts:
            raise RuntimeError("fresh uv cache did not expose any resolved wheel identities")
        unmatched = [item["filename"] for item in artifacts if not item["locked_hash_match"]]
        if unmatched:
            raise RuntimeError(f"resolved wheel hashes are absent from uv.lock: {unmatched}")
        (output / "resolved_artifacts.json").write_text(
            json.dumps(artifacts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        receipt["resolved_wheel_count"] = len(artifacts)
    (output / "provision_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        path.relative_to(output).as_posix(): sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    (output / "provision_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
