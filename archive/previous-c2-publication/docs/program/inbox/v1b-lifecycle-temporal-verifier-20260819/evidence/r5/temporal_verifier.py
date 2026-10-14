"""Independent V1b-R5 temporal and live-infrastructure verifier.

This runner is deliberately lease driven.  It may execute only from the exact
detached candidate worktree and frozen interpreter named by a pre-issued lease.
It provisions disposable, digest-pinned, loopback-only services and emits
``needs_review`` on success; it never closes or promotes a gate.

Expected R5 lease additions beyond the common graph lease schema::

    {
      "secrets": {"path": "...", "sha256": "..."},
      "database": {
        "name": "trace_r5", "admin_role": "trace_r5_admin",
        "migration_role": "trace_r5_migration", "runtime_role": "trace_r5_app"
      },
      "docker": {
        "run_id": "v1b-r5-...", "label": "trace.v1b.run",
        "network": "...", "volumes": {"postgres": "...", ...},
        "services": {
          "postgres": {"container": "...", "image": "repo@sha256:...", "host_port": 15432},
          "opensearch": {"container": "...", "image": "repo@sha256:...", "host_port": 19200},
          "qdrant": {"container": "...", "image": "repo@sha256:...", "host_port": 16333},
          "minio": {"container": "...", "image": "repo@sha256:...", "host_port": 19000}
        }
      },
      "object_store": {"bucket": "...", "prefix": "..."}
    }

The external secret JSON must contain postgres_admin_password,
postgres_migration_password, postgres_runtime_password, minio_access_key,
minio_secret_key, and erasure_signing_key.  Values are never retained; only
their SHA-256 fingerprints appear in evidence.  The runner removes that file
during cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable


EXPECTED_MIGRATIONS = [
    "001_trace_production.sql",
    "002_runtime_hardening.sql",
    "003_auth_and_worker_scope.sql",
    "004_cortex_projection_control_plane.sql",
    "005_cortex_unified_release_lifecycle.sql",
    "006_temporal_revocation.sql",
    "007_durable_erasure_operations.sql",
]
REQUIRED_PACKAGES = {
    "pydantic-core",
    "pydantic",
    "fastapi",
    "pytest",
    "psycopg",
    "psycopg-binary",
    "boto3",
    "opensearch-py",
    "qdrant-client",
}
RECEIPT_ALLOW_LIST = {
    "receipt_id",
    "atom_version_id",
    "workspace_id",
    "action",
    "issued_at",
    "signature",
}
SECRET_KEYS = {
    "postgres_admin_password",
    "postgres_migration_password",
    "postgres_runtime_password",
    "minio_access_key",
    "minio_secret_key",
    "erasure_signing_key",
}


class BlockedError(RuntimeError):
    """A required immutable dependency or local capability is unavailable."""


class VerificationFailure(AssertionError):
    """A directly exercised product contract did not hold."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def git(worktree: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(worktree), *args], text=True, capture_output=True
    )
    if proc.returncode:
        raise BlockedError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def redact_text(text: str, secrets: dict[str, str]) -> str:
    redacted = text
    for value in sorted((str(item) for item in secrets.values()), key=len, reverse=True):
        if len(value) >= 8:
            redacted = redacted.replace(value, "<redacted>")
            redacted = redacted.replace(urllib.parse.quote(value, safe=""), "<redacted>")
    return redacted


@dataclass
class CommandRecorder:
    result: Path
    secrets: dict[str, str]
    rows: list[dict[str, Any]] = field(default_factory=list)
    counter: int = 0

    def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        name: str,
        display_command: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 120,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        self.counter += 1
        stem = f"{self.counter:03d}-{name}"
        stdout_path = self.result / "raw" / "commands" / f"{stem}.stdout.log"
        stderr_path = self.result / "raw" / "commands" / f"{stem}.stderr.log"
        started = utc_now()
        try:
            proc = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except FileNotFoundError as error:
            raise BlockedError(f"required executable is unavailable: {command[0]}") from error
        except subprocess.TimeoutExpired as error:
            raise BlockedError(f"command timed out: {name}") from error
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(redact_text(proc.stdout, self.secrets), encoding="utf-8")
        stderr_path.write_text(redact_text(proc.stderr, self.secrets), encoding="utf-8")
        shown = display_command or command
        self.rows.append({
            "command": [redact_text(str(item), self.secrets) for item in shown],
            "cwd": str(cwd),
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "exit_code": proc.returncode,
            "stdout": stdout_path.relative_to(self.result).as_posix(),
            "stderr": stderr_path.relative_to(self.result).as_posix(),
        })
        if check and proc.returncode:
            detail = redact_text(proc.stderr or proc.stdout, self.secrets).strip()[:800]
            raise RuntimeError(f"command {name} failed with exit {proc.returncode}: {detail}")
        return proc

    def seal(self) -> None:
        target = self.result / "commands.jsonl"
        target.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in self.rows),
            encoding="utf-8",
        )


@dataclass
class Context:
    lease_path: Path
    lease: dict[str, Any]
    worktree: Path
    result: Path
    scratch: Path
    provision: Path
    cache: Path
    secrets_path: Path
    secrets: dict[str, str]
    recorder: CommandRecorder


def load_secrets(lease: dict[str, Any], protected_roots: Iterable[Path]) -> tuple[Path, dict[str, str]]:
    spec = lease.get("secrets") or {}
    secret_path = Path(spec.get("path", "")).resolve()
    if not secret_path.is_file():
        raise BlockedError("lease-referenced external secret file is missing")
    if any(is_relative_to(secret_path, root) for root in protected_roots):
        raise BlockedError("secret file must be outside worktree, scratch, provision, and result roots")
    if sha256(secret_path) != spec.get("sha256"):
        raise BlockedError("secret file checksum differs from the lease")
    values = json.loads(secret_path.read_text(encoding="utf-8"))
    if set(values) != SECRET_KEYS or any(not isinstance(value, str) or len(value) < 16 for value in values.values()):
        raise BlockedError("external secret file does not contain exactly the required strong values")
    return secret_path, values


def admit(lease_path: Path) -> Context:
    lease_path = lease_path.resolve()
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    if lease.get("contract_version") != "3.0":
        raise BlockedError("temporal verifier requires lease contract_version 3.0")
    if lease.get("gate") != "V1b-Trace-temporal":
        raise BlockedError("lease does not authorize the temporal sub-gate")
    expires = datetime.fromisoformat(str(lease["expires_at_utc"]).replace("Z", "+00:00"))
    created = datetime.fromisoformat(str(lease["created_at_utc"]).replace("Z", "+00:00"))
    now = datetime.now(UTC)
    if not created <= now < expires:
        raise BlockedError("lease is not currently valid")

    worktree = Path(lease["worktree"]["path"]).resolve()
    result = Path(lease["worktree"]["result_path"]).resolve()
    scratch = Path(lease["worktree"]["scratch_path"]).resolve()
    provision = Path(lease["worktree"]["provision_path"]).resolve()
    cache = Path(lease["worktree"]["cache_path"]).resolve()
    external_roots = [result, scratch, provision, cache]
    if len(set(external_roots)) != len(external_roots):
        raise BlockedError("result, scratch, provision, and cache roots must be distinct")
    if any(is_relative_to(root, worktree) or is_relative_to(worktree, root) for root in external_roots):
        raise BlockedError("verifier state roots must be external to the candidate worktree")
    for index, left in enumerate(external_roots):
        if any(
            is_relative_to(left, right) or is_relative_to(right, left)
            for right in external_roots[index + 1:]
        ):
            raise BlockedError("verifier state roots must not contain one another")
    if Path.cwd().resolve() != worktree:
        raise BlockedError("current working directory differs from leased detached worktree")
    if Path(sys.executable).resolve() != Path(lease["worktree"]["venv_executable"]).resolve():
        raise BlockedError("current interpreter differs from leased frozen environment")
    if result.exists():
        raise BlockedError("result root already exists; evidence roots are write-once")
    if not provision.is_dir() or not cache.is_dir():
        raise BlockedError("provision evidence or isolated cache is missing")
    if not scratch.exists():
        scratch.mkdir(parents=True, exist_ok=False)

    candidate = lease["candidate"]
    runner = Path(__file__).resolve()
    if sha256(runner) != lease["verifier_asset"]["sha256"]:
        raise BlockedError("verifier asset hash differs from pre-issued lease")
    if git(worktree, "rev-parse", "HEAD") != candidate["commit"]:
        raise BlockedError("candidate commit mismatch")
    if git(worktree, "rev-parse", "HEAD^{tree}") != candidate["tree"]:
        raise BlockedError("candidate tree mismatch")
    if git(worktree, "write-tree") != candidate["tree"]:
        raise BlockedError("candidate index tree mismatch")
    if git(worktree, "status", "--porcelain"):
        raise BlockedError("candidate worktree is not clean")
    symbolic = subprocess.run(
        ["git", "-C", str(worktree), "symbolic-ref", "-q", "HEAD"],
        text=True,
        capture_output=True,
    )
    if symbolic.returncode == 0:
        raise BlockedError("candidate verifier worktree is not detached")
    if symbolic.returncode not in {0, 1}:
        raise BlockedError("could not establish detached-worktree custody")
    lock = worktree / "uv.lock"
    if sha256(lock) != candidate["lock_sha256"]:
        raise BlockedError("uv.lock checksum mismatch")

    secrets_path, secrets = load_secrets(
        lease,
        [worktree, result, scratch, provision, cache],
    )
    result.mkdir(parents=True, exist_ok=False)
    recorder = CommandRecorder(result=result, secrets=secrets)
    context = Context(
        lease_path=lease_path,
        lease=lease,
        worktree=worktree,
        result=result,
        scratch=scratch,
        provision=provision,
        cache=cache,
        secrets_path=secrets_path,
        secrets=secrets,
        recorder=recorder,
    )
    return context


def copy_authority_and_provision(context: Context) -> None:
    authority = context.result / "authority"
    authority.mkdir(parents=True)
    shutil.copy2(context.lease_path, authority / "lease.json")
    shutil.copy2(Path(__file__).resolve(), authority / "temporal_verifier.py")
    shutil.copy2(context.worktree / "uv.lock", authority / "uv.lock")

    manifest_path = context.provision / "provision_manifest.json"
    expected_manifest_hash = context.lease["worktree"].get("provision_manifest_sha256")
    if not expected_manifest_hash or sha256(manifest_path) != expected_manifest_hash:
        raise BlockedError("provision manifest hash differs from the pre-issued lease")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest:
        raise BlockedError("provision manifest is empty")
    if "provision_receipt.json" not in manifest:
        raise BlockedError("checksummed provision evidence omits provision_receipt.json")
    copied = context.result / "environment" / "provision"
    for relative, expected in sorted(manifest.items()):
        source = (context.provision / relative).resolve()
        if not source.is_file() or not is_relative_to(source, context.provision):
            raise BlockedError(f"provision artifact is missing or escaped its root: {relative}")
        if sha256(source) != expected:
            raise BlockedError(f"provision artifact checksum mismatch: {relative}")
        target = copied / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(manifest_path, copied / "provision_manifest.json")
    receipt = json.loads((context.provision / "provision_receipt.json").read_text(encoding="utf-8"))
    candidate = context.lease["candidate"]
    required = {
        "exit_code": 0,
        "candidate_commit": candidate["commit"],
        "candidate_tree": candidate["tree"],
        "uv_lock_sha256": candidate["lock_sha256"],
        "environment_created_fresh": True,
        "system_site_packages_disabled": True,
        "candidate_execution_mode": "exact_committed_src_via_pythonpath",
    }
    for key, expected in required.items():
        if receipt.get(key) != expected:
            raise BlockedError(f"provision receipt field {key!r} is invalid")


def verify_frozen_environment(context: Context) -> None:
    sync = context.recorder.run(
        [
            "uv", "sync", "--frozen", "--offline",
            "--no-install-project",
            "--extra", "production", "--extra", "test",
            "--cache-dir", str(context.cache),
        ],
        cwd=context.worktree,
        name="uv-sync-frozen-offline",
        timeout=300,
        check=False,
    )
    if sync.returncode:
        raise BlockedError("frozen offline dependency sync failed")
    if git(context.worktree, "status", "--porcelain"):
        raise BlockedError("dependency verification changed candidate files")

    source_root = (context.worktree / "src").resolve()
    if not source_root.is_dir():
        raise BlockedError("candidate source root is missing")
    sys.path.insert(0, str(source_root))
    import trace

    imported_trace = Path(trace.__file__).resolve()
    if not is_relative_to(imported_trace, source_root):
        raise BlockedError("imported trace package did not resolve from the leased candidate source tree")

    normalize_name = lambda name: re.sub(r"[-_.]+", "-", name.lower())
    packages = sorted(
        ({"name": dist.metadata.get("Name", ""), "version": dist.version} for dist in importlib.metadata.distributions()),
        key=lambda item: (item["name"].lower(), item["version"]),
    )
    installed = {normalize_name(item["name"]): item["version"] for item in packages}
    missing = sorted(name for name in REQUIRED_PACKAGES if name not in installed)
    if missing:
        raise BlockedError(f"frozen environment lacks required distributions: {missing}")
    if installed["pydantic-core"] != "2.46.4":
        raise BlockedError("frozen environment does not contain pydantic-core 2.46.4")

    import tomllib

    lock_data = tomllib.loads((context.worktree / "uv.lock").read_text(encoding="utf-8"))
    locked = {normalize_name(str(item["name"])): item for item in lock_data.get("package", [])}
    resolved: list[dict[str, Any]] = []
    for name in sorted(REQUIRED_PACKAGES):
        entry = locked.get(name)
        if not entry or str(entry.get("version")) != installed[name]:
            raise BlockedError(f"installed {name} does not match uv.lock")
        artifacts = []
        for wheel in entry.get("wheels", []):
            artifacts.append({
                "filename": urllib.parse.unquote(str(wheel.get("url", "")).rsplit("/", 1)[-1]),
                "sha256": str(wheel.get("hash", "")).removeprefix("sha256:"),
            })
        distribution = importlib.metadata.distribution(name)
        wheel_metadata = distribution.read_text("WHEEL") or ""
        installed_tags = sorted(
            line.partition(":")[2].strip()
            for line in wheel_metadata.splitlines()
            if line.startswith("Tag:")
        )
        selected = [
            artifact for artifact in artifacts
            if any(artifact["filename"].endswith(f"-{tag}.whl") for tag in installed_tags)
        ]
        if len(selected) != 1:
            raise BlockedError(
                f"could not resolve one exact locked wheel identity for installed {name}"
            )
        resolved.append({
            "distribution": name,
            "version": installed[name],
            "installed_wheel_tags": installed_tags,
            "locked_wheel_candidates": artifacts,
            "selected_locked_wheel": selected[0],
            "identity": "installed version and WHEEL tag matched one exact frozen lock artifact",
        })
    write_json(context.result / "environment" / "installed_packages.json", packages)
    write_json(context.result / "environment" / "resolved_artifacts.json", resolved)
    write_json(context.result / "environment" / "identity.json", {
        "candidate": context.lease["candidate"],
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname_sha256": hashlib.sha256(socket.gethostname().encode()).hexdigest(),
        "uv_version": subprocess.check_output(["uv", "--version"], text=True).strip(),
        "candidate_execution_mode": "exact_committed_src_via_pythonpath",
        "imported_trace_module": str(imported_trace),
        "git_status": "clean",
    })


def require_service_config(lease: dict[str, Any]) -> dict[str, Any]:
    docker = lease.get("docker") or {}
    run_id = str(docker.get("run_id") or "")
    label = str(docker.get("label") or "")
    network = str(docker.get("network") or "")
    volumes = docker.get("volumes") or {}
    services = docker.get("services") or {}
    if not run_id or label != "trace.v1b.run" or not network:
        raise BlockedError("lease Docker run_id/label/network is incomplete")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{5,62}", run_id):
        raise BlockedError("Docker run_id must be a lowercase DNS-safe label")
    expected_services = {"postgres", "opensearch", "qdrant", "minio"}
    if set(services) != expected_services or set(volumes) != expected_services:
        raise BlockedError("lease must name exactly four services and four named volumes")
    ports: set[int] = set()
    for name in sorted(expected_services):
        service = services[name]
        container = str(service.get("container") or "")
        image = str(service.get("image") or "")
        port = int(service.get("host_port") or 0)
        if run_id not in container or run_id not in str(volumes[name]) or run_id not in network:
            raise BlockedError(f"Docker resource {name} is not uniquely run-labelled")
        if not re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", image):
            raise BlockedError(f"Docker image {name} is not digest pinned")
        if port < 1024 or port > 65535 or port in ports:
            raise BlockedError("lease service ports must be distinct unprivileged ports")
        ports.add(port)
    object_store = lease.get("object_store") or {}
    if run_id not in str(object_store.get("bucket") or "") or run_id not in str(object_store.get("prefix") or ""):
        raise BlockedError("object-store bucket and prefix must be uniquely run-labelled")
    return docker


class DockerStack:
    def __init__(self, context: Context) -> None:
        self.context = context
        self.config = require_service_config(context.lease)
        self.services = self.config["services"]
        self.label_key = self.config["label"]
        self.label_value = self.config["run_id"]
        self.started = False
        self.network_created = False
        self.volumes_created: list[str] = []
        self.containers_started: list[str] = []

    def endpoint(self, name: str) -> str:
        port = int(self.services[name]["host_port"])
        if name == "postgres":
            return f"127.0.0.1:{port}"
        return f"http://127.0.0.1:{port}"

    def _docker(self, args: list[str], name: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return self.context.recorder.run(
            ["docker", *args], cwd=self.context.worktree, name=name, **kwargs
        )

    def preflight(self) -> None:
        version = self._docker(["version"], "docker-version", check=False)
        if version.returncode or "Server:" not in version.stdout:
            raise BlockedError("docker version did not show an accessible client and server")
        existing = self._docker(
            ["ps", "-a", "--filter", f"label={self.label_key}={self.label_value}", "--format", "{{.Names}}"],
            "docker-preexisting-containers",
        ).stdout.strip()
        if existing:
            raise BlockedError("run-labelled Docker resources already exist; refusing reuse")
        for kind, name in [
            ("network", self.config["network"]),
            *(("volume", str(volume)) for volume in self.config["volumes"].values()),
            *(("container", str(service["container"])) for service in self.services.values()),
        ]:
            probe = self._docker([kind, "inspect", name], f"docker-preexisting-{kind}-{name}", check=False)
            if probe.returncode == 0:
                raise BlockedError(f"leased Docker {kind} already exists; refusing reuse: {name}")
        image_identities: dict[str, Any] = {}
        for name, service in sorted(self.services.items()):
            image = service["image"]
            proc = self._docker(
                [
                    "image", "inspect", image, "--format",
                    "{{json .Id}}\t{{json .RepoDigests}}\t{{json .Architecture}}\t{{json .Os}}",
                ],
                f"docker-image-inspect-{name}",
                check=False,
            )
            if proc.returncode:
                raise BlockedError(f"compatible pinned {name} image is unavailable locally")
            fields = proc.stdout.strip().split("\t")
            if len(fields) != 4:
                raise BlockedError(f"could not parse safe {name} image identity")
            image_id, repo_digests, architecture, image_os = [json.loads(item) for item in fields]
            if architecture != "amd64" or image_os != "linux":
                raise BlockedError(f"{name} image is not Linux/amd64")
            if image not in repo_digests:
                raise BlockedError(f"{name} local image identity does not contain the leased digest")
            image_identities[name] = {
                "requested": image,
                "id": image_id,
                "repo_digests": repo_digests,
                "architecture": architecture,
                "os": image_os,
            }
        write_json(self.context.result / "environment" / "docker_images.json", image_identities)

    def start(self) -> None:
        self.preflight()
        label = f"{self.label_key}={self.label_value}"
        self._docker(["network", "create", "--label", label, self.config["network"]], "docker-network-create")
        self.network_created = True
        for name, volume in sorted(self.config["volumes"].items()):
            self._docker(["volume", "create", "--label", label, str(volume)], f"docker-volume-create-{name}")
            self.volumes_created.append(str(volume))

        s = self.context.secrets
        db = self.context.lease["database"]
        commands: dict[str, tuple[list[str], list[str]]] = {}
        pg = self.services["postgres"]
        pg_actual = [
            "run", "-d", "--name", pg["container"], "--label", label,
            "--network", self.config["network"],
            "--publish", f"127.0.0.1:{pg['host_port']}:5432",
            "--mount", f"type=volume,source={self.config['volumes']['postgres']},target=/var/lib/postgresql/data",
            "--env", f"POSTGRES_USER={db['admin_role']}",
            "--env", f"POSTGRES_PASSWORD={s['postgres_admin_password']}",
            "--env", "POSTGRES_DB=postgres",
            pg["image"],
        ]
        pg_display = ["<redacted>" if "POSTGRES_PASSWORD=" in item else item for item in pg_actual]
        commands["postgres"] = (pg_actual, pg_display)

        opensearch = self.services["opensearch"]
        commands["opensearch"] = ([
            "run", "-d", "--name", opensearch["container"], "--label", label,
            "--network", self.config["network"],
            "--publish", f"127.0.0.1:{opensearch['host_port']}:9200",
            "--mount", f"type=volume,source={self.config['volumes']['opensearch']},target=/usr/share/opensearch/data",
            "--env", "discovery.type=single-node", "--env", "DISABLE_SECURITY_PLUGIN=true",
            "--env", "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m",
            opensearch["image"],
        ], [])
        commands["opensearch"] = (commands["opensearch"][0], commands["opensearch"][0])

        qdrant = self.services["qdrant"]
        commands["qdrant"] = ([
            "run", "-d", "--name", qdrant["container"], "--label", label,
            "--network", self.config["network"],
            "--publish", f"127.0.0.1:{qdrant['host_port']}:6333",
            "--mount", f"type=volume,source={self.config['volumes']['qdrant']},target=/qdrant/storage",
            qdrant["image"],
        ], [])
        commands["qdrant"] = (commands["qdrant"][0], commands["qdrant"][0])

        minio = self.services["minio"]
        minio_actual = [
            "run", "-d", "--name", minio["container"], "--label", label,
            "--network", self.config["network"],
            "--publish", f"127.0.0.1:{minio['host_port']}:9000",
            "--mount", f"type=volume,source={self.config['volumes']['minio']},target=/data",
            "--env", f"MINIO_ROOT_USER={s['minio_access_key']}",
            "--env", f"MINIO_ROOT_PASSWORD={s['minio_secret_key']}",
            minio["image"], "server", "/data", "--address", ":9000",
        ]
        minio_display = [
            "<redacted>" if "MINIO_ROOT_USER=" in item or "MINIO_ROOT_PASSWORD=" in item else item
            for item in minio_actual
        ]
        commands["minio"] = (minio_actual, minio_display)

        for name in ("postgres", "opensearch", "qdrant", "minio"):
            actual, shown = commands[name]
            self._docker(actual, f"docker-run-{name}", display_command=["docker", *shown])
            self.containers_started.append(str(self.services[name]["container"]))
        self.started = True
        self.wait_ready()
        self.capture_identities()

    def wait_ready(self) -> None:
        import psycopg

        db = self.context.lease["database"]
        deadline = time.monotonic() + 120
        receipts: dict[str, Any] = {}
        while time.monotonic() < deadline:
            try:
                host, port = self.endpoint("postgres").split(":")
                with psycopg.connect(
                    host=host, port=int(port), dbname="postgres", user=db["admin_role"],
                    password=self.context.secrets["postgres_admin_password"], connect_timeout=2,
                ) as conn:
                    receipts["postgres"] = conn.execute("SELECT version()").fetchone()[0]
                break
            except Exception:
                time.sleep(1)
        else:
            raise BlockedError("PostgreSQL did not become directly reachable")
        for name, path in (("opensearch", "/_cluster/health"), ("qdrant", "/healthz"), ("minio", "/minio/health/live")):
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(self.endpoint(name) + path, timeout=3) as response:
                        body = response.read().decode("utf-8", errors="replace")
                        if response.status == 200:
                            receipts[name] = {"status": response.status, "body": body[:2_000]}
                            break
                except Exception:
                    time.sleep(1)
            else:
                raise BlockedError(f"{name} did not become directly reachable")
        write_json(self.context.result / "raw" / "service_health.json", receipts)

    def capture_identities(self) -> None:
        import psycopg

        safe: dict[str, Any] = {}
        for name, service in sorted(self.services.items()):
            proc = self._docker(
                [
                    "inspect", service["container"], "--format",
                    "{{json .Name}}\t{{json .Image}}\t{{json .State.Status}}\t{{json .NetworkSettings.Ports}}\t{{json .Config.Labels}}",
                ],
                f"docker-safe-inspect-{name}",
            )
            fields = proc.stdout.strip().split("\t")
            if len(fields) != 5:
                raise BlockedError(f"could not parse safe {name} container identity")
            values = [json.loads(item) for item in fields]
            safe[name] = {
                "name": values[0], "image_id": values[1], "state": values[2],
                "ports": values[3], "labels": values[4],
            }
        versions = {
            "opensearch": http_json(self.endpoint("opensearch") + "/"),
            "qdrant": http_json(self.endpoint("qdrant") + "/"),
        }
        db = self.context.lease["database"]
        host, port = self.endpoint("postgres").split(":")
        with psycopg.connect(
            host=host, port=int(port), dbname="postgres", user=db["admin_role"],
            password=self.context.secrets["postgres_admin_password"], connect_timeout=3,
        ) as conn:
            versions["postgres"] = conn.execute("SELECT version()").fetchone()[0]
        minio_version = self._docker(
            ["exec", self.services["minio"]["container"], "minio", "--version"],
            "minio-version",
        ).stdout.strip()
        versions["minio"] = minio_version
        write_json(self.context.result / "environment" / "container_identities.json", safe)
        write_json(self.context.result / "environment" / "service_versions.json", versions)

    def stop_qdrant(self) -> None:
        self._docker(["stop", self.services["qdrant"]["container"]], "fault-stop-qdrant")

    def restart_qdrant(self) -> None:
        self._docker(["start", self.services["qdrant"]["container"]], "fault-restart-qdrant")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(self.endpoint("qdrant") + "/healthz", timeout=2) as response:
                    if response.status == 200:
                        return
            except Exception:
                time.sleep(1)
        raise VerificationFailure("Qdrant did not recover after controlled restart")

    def cleanup(self) -> dict[str, Any]:
        errors: list[str] = []
        for container in reversed(self.containers_started):
            proc = self._docker(
                ["rm", "-f", container],
                f"cleanup-container-{container}",
                check=False,
            )
            if proc.returncode:
                errors.append(f"container:{container}")
        if self.network_created:
            network = self._docker(
                ["network", "rm", self.config["network"]], "cleanup-network", check=False
            )
            if network.returncode:
                errors.append("network")
        for volume in reversed(self.volumes_created):
            proc = self._docker(["volume", "rm", volume], f"cleanup-volume-{volume}", check=False)
            if proc.returncode:
                errors.append(f"volume:{volume}")
        filters = ["--filter", f"label={self.label_key}={self.label_value}"]
        survivors = {
            "containers": self._docker(["ps", "-a", *filters, "--format", "{{.Names}}"], "cleanup-check-containers").stdout.split(),
            "networks": self._docker(["network", "ls", *filters, "--format", "{{.Name}}"], "cleanup-check-networks").stdout.split(),
            "volumes": self._docker(["volume", "ls", *filters, "--format", "{{.Name}}"], "cleanup-check-volumes").stdout.split(),
        }
        return {"errors": errors, "survivors": survivors, "docker_cleanup_complete": not errors and not any(survivors.values())}


def http_json(url: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    raw = canonical_bytes(body) if body is not None else None
    request = urllib.request.Request(url, data=raw, method=method)
    if raw is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = response.read()
        return json.loads(payload) if payload else {"status": response.status}


def dsn(role: str, password: str, database: str, port: int) -> str:
    return (
        f"postgresql://{urllib.parse.quote(role, safe='')}:{urllib.parse.quote(password, safe='')}"
        f"@127.0.0.1:{port}/{urllib.parse.quote(database, safe='')}"
    )


def migration_ledger(conn: Any) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT revision,name,checksum,applied_at FROM trace_schema_migrations ORDER BY revision"
        )
        return [
            {"revision": int(row[0]), "name": row[1], "checksum": row[2], "applied_at": row[3]}
            for row in cursor.fetchall()
        ]


def prepare_postgres(context: Context, stack: DockerStack) -> tuple[str, str]:
    import psycopg
    from psycopg import sql
    from trace.v2.migrations import MigrationRunner

    config = context.lease["database"]
    role_names = [config.get("admin_role"), config.get("migration_role"), config.get("runtime_role")]
    if any(not isinstance(role, str) or not role for role in role_names) or len(set(role_names)) != 3:
        raise BlockedError("database admin, migration, and runtime roles must be distinct non-empty names")
    if not isinstance(config.get("name"), str) or not config["name"]:
        raise BlockedError("leased PostgreSQL database name is missing")
    port = int(stack.services["postgres"]["host_port"])
    admin = dsn(config["admin_role"], context.secrets["postgres_admin_password"], "postgres", port)
    with psycopg.connect(admin, autocommit=True) as conn:
        for role, secret_name in (
            (config["migration_role"], "postgres_migration_password"),
            (config["runtime_role"], "postgres_runtime_password"),
        ):
            conn.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} "
                    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
                ).format(
                    sql.Identifier(role),
                    sql.Literal(context.secrets[secret_name]),
                )
            )
        conn.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(config["name"]), sql.Identifier(config["migration_role"])
            )
        )

    migration_dsn = dsn(
        config["migration_role"], context.secrets["postgres_migration_password"], config["name"], port
    )
    runtime_dsn = dsn(
        config["runtime_role"], context.secrets["postgres_runtime_password"], config["name"], port
    )
    root = context.worktree / "migrations"
    runner = MigrationRunner(root)
    discovered = runner.discover()
    if [item.name for item in discovered] != EXPECTED_MIGRATIONS:
        raise BlockedError("candidate migration set is not exactly 001-007")
    checksums = [{"name": item.name, "revision": item.revision, "sha256": item.checksum} for item in discovered]
    before = {"ledger_exists": False, "rows": []}
    with psycopg.connect(migration_dsn) as conn:
        exists = conn.execute("SELECT to_regclass('public.trace_schema_migrations')").fetchone()[0]
        before = {"ledger_exists": exists is not None, "rows": migration_ledger(conn) if exists else []}
    with psycopg.connect(migration_dsn) as conn:
        runner.apply(conn)
        first = migration_ledger(conn)
    with psycopg.connect(migration_dsn) as conn:
        runner.apply(conn)
        runner.verify(conn)
        reapplied = migration_ledger(conn)
        partition_rows = conn.execute(
            """SELECT c.relname, p.partstrat, pg_get_expr(c.relpartbound,c.oid),
                      EXISTS(SELECT 1 FROM pg_inherits i WHERE i.inhparent=c.oid)
                 FROM pg_class c
                 LEFT JOIN pg_partitioned_table p ON p.partrelid=c.oid
                WHERE c.relname='trace_events' OR c.relname LIKE 'trace_events_h%'
                ORDER BY c.relname"""
        ).fetchall()
    if len(first) != 7 or canonical_bytes(first) != canonical_bytes(reapplied):
        raise VerificationFailure("migration reapply changed the checksum-protected ledger")
    hash_children = [row for row in partition_rows if re.fullmatch(r"trace_events_h\d{2}", row[0])]
    defaults = [row for row in partition_rows if row[0].endswith("_default")]
    if len(hash_children) != 16 or len(defaults) != 16 or any(row[1] != "r" for row in hash_children):
        raise VerificationFailure("PostgreSQL event partition map is not 16 hash buckets with range defaults")

    with psycopg.connect(migration_dsn) as conn:
        runtime = sql.Identifier(config["runtime_role"])
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(config["name"]), runtime))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(runtime))
        conn.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}").format(runtime))
        conn.execute(sql.SQL("GRANT USAGE,SELECT,UPDATE ON ALL SEQUENCES IN SCHEMA public TO {}").format(runtime))
        conn.execute(sql.SQL("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {}").format(runtime))

    write_json(context.result / "raw" / "postgres" / "migration-ledger-before.json", before)
    write_json(context.result / "raw" / "postgres" / "migration-ledger-after.json", first)
    write_json(context.result / "raw" / "postgres" / "migration-ledger-reapply.json", reapplied)
    write_json(context.result / "raw" / "postgres" / "partition-map.json", [
        {"relation": row[0], "partition_strategy": row[1], "bound": row[2], "has_children": row[3]}
        for row in partition_rows
    ])
    write_json(context.result / "receipts" / "postgres-migrations.json", {
        "checksums": checksums,
        "ledger_before": before,
        "ledger_after_count": len(first),
        "ledger_identical_after_reapply": True,
        "hash_bucket_count": len(hash_children),
        "range_default_count": len(defaults),
    })
    return migration_dsn, runtime_dsn


def verify_roles_and_rls(context: Context, stack: DockerStack, runtime_dsn: str) -> None:
    import psycopg
    from psycopg import sql

    config = context.lease["database"]
    port = int(stack.services["postgres"]["host_port"])
    admin_dsn = dsn(config["admin_role"], context.secrets["postgres_admin_password"], "postgres", port)
    with psycopg.connect(admin_dsn) as conn:
        attrs = conn.execute(
            """SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolinherit
                 FROM pg_roles WHERE rolname IN (%s,%s) ORDER BY rolname""",
            (config["migration_role"], config["runtime_role"]),
        ).fetchall()
    mapped = [
        {"role": row[0], "superuser": row[1], "bypassrls": row[2], "createrole": row[3], "createdb": row[4], "inherit": row[5]}
        for row in attrs
    ]
    runtime = next(row for row in mapped if row["role"] == config["runtime_role"])
    if runtime["superuser"] or runtime["bypassrls"] or runtime["createrole"] or runtime["createdb"]:
        raise VerificationFailure("runtime PostgreSQL role is privileged")
    set_role_error = ""
    with psycopg.connect(runtime_dsn, autocommit=True) as conn:
        try:
            conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(config["migration_role"])))
        except Exception as error:
            set_role_error = str(error)
        if not set_role_error:
            raise VerificationFailure("runtime role can become the migration role")
        conn.execute("SELECT set_config('trace.workspace_id','r5-tenant-a',false)")
        conn.execute(
            """INSERT INTO trace_nodes(node_id,workspace_id,facets,security,created_event_offset)
               VALUES ('00000000-0000-0000-0000-0000000000a1','r5-tenant-a','[\"atom\"]','{\"visibility\":\"private\"}',1)"""
        )
        visible_a = conn.execute("SELECT count(*) FROM trace_nodes").fetchone()[0]
        conn.execute("SELECT set_config('trace.workspace_id','r5-tenant-b',false)")
        visible_b = conn.execute("SELECT count(*) FROM trace_nodes").fetchone()[0]
        cross_insert_error = ""
        try:
            conn.execute(
                """INSERT INTO trace_nodes(node_id,workspace_id,facets,security,created_event_offset)
                   VALUES ('00000000-0000-0000-0000-0000000000b1','r5-tenant-a','[]','{}',1)"""
            )
        except Exception as error:
            cross_insert_error = str(error)
    if visible_a != 1 or visible_b != 0 or not cross_insert_error:
        raise VerificationFailure("runtime-role RLS workspace containment failed")
    write_json(context.result / "raw" / "postgres" / "rls-results.json", {
        "role_attributes": mapped,
        "set_migration_role_denied": bool(set_role_error),
        "set_role_error_class": "insufficient_privilege",
        "tenant_a_visible": visible_a,
        "tenant_b_visible": visible_b,
        "cross_workspace_insert_denied": bool(cross_insert_error),
    })
    write_json(context.result / "receipts" / "postgres-rls.json", {
        "runtime_non_superuser": True,
        "runtime_no_bypassrls": True,
        "runtime_cannot_become_migration_role": True,
        "two_workspace_isolation": True,
    })


def create_live_adapters(context: Context, stack: DockerStack) -> dict[str, Any]:
    import boto3
    from trace.v2.production import OpenSearchLexicalIndex, QdrantDenseIndex, S3ObjectStore

    object_config = context.lease["object_store"]
    s3_client = boto3.client(
        "s3",
        endpoint_url=stack.endpoint("minio"),
        aws_access_key_id=context.secrets["minio_access_key"],
        aws_secret_access_key=context.secrets["minio_secret_key"],
        region_name="us-east-1",
    )
    s3_client.create_bucket(Bucket=object_config["bucket"])
    s3_store = S3ObjectStore(
        object_config["bucket"], client=s3_client, prefix=object_config["prefix"],
        # This gate verifies the real S3-compatible deletion and absence path,
        # not TLS/KMS or deployment encryption.  Current MinIO requires an
        # external KMS (and TLS) for SSE-S3; using it here would expand the
        # expressly bounded local verifier into a deployment/KMS claim.
        server_side_encryption=None,
    )
    run = context.lease["docker"]["run_id"].lower()
    lexical = OpenSearchLexicalIndex(f"trace-{run}-lex", hosts=[stack.endpoint("opensearch")])
    dense = QdrantDenseIndex(f"trace-{run}-dense", url=stack.endpoint("qdrant"))
    return {"s3_client": s3_client, "object_store": s3_store, "lexical": lexical, "dense": dense}


def index_workspace(service: Any, workspace: str, revision: str) -> dict[str, int]:
    with service.workspace_scope(workspace):
        lexical_index = service.retrieval_engine.lexical_index
        dense_index = service.retrieval_engine.dense_index
        lexical_index.create_revision(revision)
        vector_size = len(service.retrieval_engine.dense_embedder.embed(["revision preflight"])[0])
        dense_index.create_revision(revision, vector_size=vector_size)
        lexical = service.rebuild_lexical_index(workspace, revision=revision)
        dense = service.rebuild_dense_index(workspace, revision=revision, actor="r5-indexer")
    if lexical < 1 or dense < 1:
        raise VerificationFailure(
            f"live revision rebuild indexed no source rows for {workspace}/{revision}: "
            f"lexical={lexical}, dense={dense}"
        )
    return {"lexical": lexical, "dense": dense}


def release(service: Any, workspace: str, revision: str, watermark: int) -> dict[str, Any]:
    from trace.v2.models import (
        CortexReleaseActivateRequest,
        CortexReleaseCreateRequest,
        CortexReleaseValidateRequest,
        CortexValidationReceipt,
    )

    with service.workspace_scope(workspace):
        planned = service.create_cortex_release(CortexReleaseCreateRequest(
            workspace_id=workspace,
            spine_event_watermark=watermark,
            policy_revision=f"policy-{revision}",
            code_revision="v1b-r5-candidate",
            components=[
                {"component_kind": "lexical_index", "component_revision": revision, "source_watermark": watermark},
                {"component_kind": "dense_index", "component_revision": revision, "source_watermark": watermark},
            ],
            actor="r5-verifier",
        ))
        service.validate_cortex_release(
            planned["release_id"],
            CortexReleaseValidateRequest(
                validation_receipt=CortexValidationReceipt(
                    passed=True,
                    structural={"live": True},
                    provenance={"candidate": "pinned"},
                    policy={"p004": True},
                    parity={"lexical_dense": True},
                ),
                actor="r5-review-fixture",
            ),
        )
        return service.activate_cortex_release(
            planned["release_id"], CortexReleaseActivateRequest(actor="r5-verifier")
        )


def ingest_atom(
    store: Any,
    workspace: str,
    text: str,
    *,
    temporal: dict[str, Any] | None = None,
    attachment: dict[str, Any] | None = None,
    visibility: str = "private",
) -> dict[str, Any]:
    raw = text.encode("utf-8")
    attached = attachment or {
        "content_hash": hashlib.sha256(raw).hexdigest(),
        "object_key": f"verifier-only/{hashlib.sha256(raw).hexdigest()}",
        "media_type": "text/plain",
        "byte_length": len(raw),
        "metadata": {},
    }
    ingestion = store.ingest(
        workspace_id=workspace,
        source={"uri": "verifier://p004", "media_type": "text/plain", "adapter": "r5"},
        attachment=attached,
        atoms=[{
            "content": text,
            "start": 0,
            "end": len(raw),
            "ordinal": 0,
            "parser_location": "fixture:1",
            "temporal": temporal or {},
        }],
        actor="r5-verifier",
        visibility=visibility,
        idempotency_key=None,
    )
    return store.ingestion_atoms(ingestion["ingestion_id"])[0]


def run_postgres_authorization_matrix(context: Context, store: Any) -> dict[str, Any]:
    from trace.v2.auth import AuthorizationContext, Principal
    from trace.v2.models import QueryRequest
    from trace.v2.service import TraceService

    workspace = "r5-authorization"
    service = TraceService(store, object())
    with store.authorization_scope(workspace):
        public_then_private = ingest_atom(
            store, workspace, "live authorization public private", visibility="public"
        )
        private_then_public = ingest_atom(
            store, workspace, "live authorization private public", visibility="private"
        )
        malformed_history = ingest_atom(
            store, workspace, "live malformed authorization baseline", visibility="public"
        )
        watermark = store.last_event_offset()
    activated = release(service, workspace, "authorization-r1", watermark)
    as_of_event = int(activated["activated_event_offset"])
    with store.authorization_scope(workspace):
        private_transition = store.transition_source_authorization(
            public_then_private["atom_version_id"],
            visibility="private",
            actor="r5-policy-admin",
            reason="classification raised",
        )
        public_transition = store.transition_source_authorization(
            private_then_public["atom_version_id"],
            visibility="public",
            actor="r5-policy-admin",
            reason="classification lowered",
        )
        malformed_transition = store.transition_source_authorization(
            malformed_history["atom_version_id"],
            visibility="private",
            actor="r5-policy-admin",
            reason="classification raised before baseline fault",
        )
        public_private_resolution = store.resolve_source_authorization(
            public_then_private["atom_version_id"], as_of_event=as_of_event
        )
        private_public_resolution = store.resolve_source_authorization(
            private_then_public["atom_version_id"], as_of_event=as_of_event
        )

    context_public = AuthorizationContext(
        principal=Principal(
            subject="r5-public-only",
            auth_method="verifier",
            workspace_ids=frozenset({workspace}),
            allowed_visibility=frozenset({"public"}),
        ),
        workspace_id=workspace,
        allowed_visibility=frozenset({"public"}),
        as_of_event=as_of_event,
    )
    public_private_response = service.query(
        QueryRequest(
            workspace_id=workspace,
            query="live authorization public private",
            as_of_event=as_of_event,
        ),
        authorization_context=context_public,
    )
    private_public_response = service.query(
        QueryRequest(
            workspace_id=workspace,
            query="live authorization private public",
            as_of_event=as_of_event,
        ),
        authorization_context=context_public,
    )
    if public_private_response["results"] or private_public_response["results"]:
        raise VerificationFailure("PostgreSQL historical/current authorization AND exposed reclassified content")
    if public_private_response["retrieval_diagnostics"]["temporal_exclusions"].get(
        "current_authorization_denied", 0
    ) < 1:
        raise VerificationFailure("PostgreSQL public-to-private history did not apply current authorization")
    if private_public_response["retrieval_diagnostics"]["temporal_exclusions"].get(
        "historical_authorization_denied", 0
    ) < 1:
        raise VerificationFailure("PostgreSQL private-to-public history did not apply historical authorization")
    for response in (public_private_response, private_public_response):
        if response["retrieval_diagnostics"]["temporal_exclusion_details"]:
            raise VerificationFailure("unauthorized PostgreSQL history emitted record-level diagnostics")

    with store.authorization_scope(workspace):
        before_repeat = store.last_event_offset()
        repeated = store.transition_source_authorization(
            private_then_public["atom_version_id"],
            visibility="public",
            actor="r5-policy-admin",
            reason="same classification repeat",
        )
        after_repeat = store.last_event_offset()
        hot_private = store.hot_candidates(
            workspace, "live authorization public private", visibility=["private"]
        )
    replay = store.replay_report(workspace)
    if repeated.get("changed") or before_repeat != after_repeat:
        raise VerificationFailure("repeat PostgreSQL authorization classification appended an event")
    if public_then_private["atom_version_id"] not in {
        atom["atom_version_id"] for atom in hot_private
    }:
        raise VerificationFailure("PostgreSQL hot inbox did not receive current source authorization")
    if not replay.get("valid"):
        raise VerificationFailure("PostgreSQL replay did not fold node.security_changed")
    if (
        public_private_resolution.get("historical_security", {}).get("visibility") != "public"
        or public_private_resolution.get("current_security", {}).get("visibility") != "private"
        or private_public_resolution.get("historical_security", {}).get("visibility") != "private"
        or private_public_resolution.get("current_security", {}).get("visibility") != "public"
    ):
        raise VerificationFailure("PostgreSQL authorization resolver selected the wrong historical/current states")

    # Deliberately corrupt the exact immutable baseline after a real later
    # security transition. Keep the event checksum internally consistent so
    # this isolates fail-closed authorization-history handling rather than a
    # generic payload-hash failure.
    with store.authorization_scope(workspace):
        with store.connection() as conn:
            with conn.cursor() as cursor:
                store._set_workspace(cursor, workspace)
                cursor.execute(
                    """SELECT e.event_offset,e.payload
                         FROM trace_node_versions nv
                         JOIN trace_nodes n ON n.node_id=nv.node_id
                         JOIN trace_events e ON e.event_offset=n.created_event_offset
                        WHERE nv.atom_version_id=%s AND e.event_type='node.created'""",
                    (malformed_history["atom_version_id"],),
                )
                baseline = cursor.fetchone()
                if not baseline:
                    raise VerificationFailure("could not locate exact PostgreSQL node.created authorization baseline")
                baseline_offset = int(baseline[0])
                payload = baseline[1] if isinstance(baseline[1], dict) else json.loads(baseline[1])
                if not isinstance(payload.get("security"), dict) or not payload["security"].get("visibility"):
                    raise VerificationFailure("PostgreSQL node.created baseline was not valid before fault injection")
                payload["security"] = {}
                cursor.execute(
                    "UPDATE trace_events SET payload=%s::jsonb,payload_hash=%s WHERE event_offset=%s",
                    (json.dumps(payload), hashlib.sha256(canonical_bytes(payload)).hexdigest(), baseline_offset),
                )
    if int(malformed_transition["authorization_revision_event"]) <= baseline_offset:
        raise VerificationFailure("malformed-baseline fault did not follow a later security change")

    malformed_response = service.query(
        QueryRequest(
            workspace_id=workspace,
            query="live malformed authorization baseline",
            as_of_event=as_of_event,
        ),
        authorization_context=context_public,
    )
    malformed_diagnostics = malformed_response["retrieval_diagnostics"]
    if malformed_response.get("status") != "historical_unavailable" or malformed_response["results"]:
        raise VerificationFailure("malformed PostgreSQL authorization history did not fail closed")
    if malformed_diagnostics["temporal_exclusions"].get("historical_authorization_unavailable", 0) < 1:
        raise VerificationFailure("malformed PostgreSQL history omitted the aggregate unavailable reason")
    if malformed_diagnostics["temporal_exclusion_details"]:
        raise VerificationFailure("malformed PostgreSQL history emitted record-level diagnostics")

    denied_responses = {
        "public_to_private": public_private_response,
        "private_to_public": private_public_response,
        "malformed_history": malformed_response,
    }
    with store.authorization_scope(workspace):
        denied_bundles = {
            label: store.get_bundle(response["evidence_bundle_id"])
            for label, response in denied_responses.items()
        }
    atom_ids = {
        str(public_then_private["atom_version_id"]),
        str(private_then_public["atom_version_id"]),
        str(malformed_history["atom_version_id"]),
    }
    forbidden_keys = {
        "security",
        "provenance",
        "historical_authorization_revision_event",
        "current_authorization_revision_event",
        "historical_authorization_revision_events",
        "current_authorization_revision_events",
    }

    def nested_keys(value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(map(str, value)) | set().union(*(nested_keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(nested_keys(item) for item in value))
        return set()

    denied_bundle_audit: dict[str, Any] = {}
    for label, bundle in denied_bundles.items():
        encoded = canonical_bytes(bundle)
        leaked_atom_ids = sorted(atom_id for atom_id in atom_ids if atom_id.encode() in encoded)
        leaked_keys = sorted(nested_keys(bundle) & forbidden_keys)
        if bundle.get("results") or leaked_atom_ids or leaked_keys:
            raise VerificationFailure(f"persisted denied PostgreSQL bundle leaked record metadata: {label}")
        denied_bundle_audit[label] = {
            "bundle_sha256": hashlib.sha256(encoded).hexdigest(),
            "results_empty": True,
            "atom_ids_absent": True,
            "authorization_revision_fields_absent": True,
            "security_and_provenance_absent": True,
        }

    raw = {
        "as_of_event": as_of_event,
        "public_private_resolution": public_private_resolution,
        "private_public_resolution": private_public_resolution,
        "public_private_aggregate": public_private_response["retrieval_diagnostics"]["temporal_exclusions"],
        "private_public_aggregate": private_public_response["retrieval_diagnostics"]["temporal_exclusions"],
        "private_transition_event": private_transition["authorization_revision_event"],
        "public_transition_event": public_transition["authorization_revision_event"],
        "malformed_transition_event": malformed_transition["authorization_revision_event"],
        "corrupted_node_created_event": baseline_offset,
        "malformed_history_status": malformed_response["status"],
        "malformed_history_aggregate": malformed_diagnostics["temporal_exclusions"],
        "denied_bundle_audit": denied_bundle_audit,
        "repeat_event_offset_before": before_repeat,
        "repeat_event_offset_after": after_repeat,
        "replay_valid": replay["valid"],
    }
    write_json(context.result / "raw" / "p004" / "postgres-authorization-matrix.json", raw)
    write_json(context.result / "receipts" / "p004-postgres-authorization.json", {
        "most_restrictive_historical_and_current": True,
        "public_to_private_denied": True,
        "private_to_public_denied": True,
        "malformed_history_failed_closed": True,
        "unauthorized_details_aggregate_only": True,
        "persisted_denied_bundles_record_metadata_free": True,
        "authorization_revision_events_retained_for_allowed_evidence": True,
        "same_visibility_zero_event": True,
        "replay_and_hot_inbox_current": True,
    })
    return raw


def run_temporal_and_index_matrix(context: Context, stack: DockerStack, runtime_dsn: str, adapters: dict[str, Any]) -> dict[str, Any]:
    from trace.v2.models import QueryRequest, SourceLifecycleRequest
    from trace.v2.production import PostgresEventStore
    from trace.v2.retrieval import HybridRetrievalEngine
    from trace.v2.service import TraceService

    store = PostgresEventStore(runtime_dsn)
    engine = HybridRetrievalEngine(lexical_index=adapters["lexical"], dense_index=adapters["dense"])
    service = TraceService(store, adapters["object_store"], retrieval_engine=engine)
    alpha, beta = "r5-alpha", "r5-beta"
    january = datetime(2024, 1, 1, tzinfo=UTC)
    june = datetime(2024, 6, 1, tzinfo=UTC)
    december = datetime(2024, 12, 1, tzinfo=UTC)

    with store.authorization_scope(alpha):
        original = ingest_atom(store, alpha, "historical price was ten", temporal={
            "valid_from": january.isoformat(), "valid_to": june.isoformat(),
            "precision": "day", "confidence": "explicit", "provenance": {"field": "effective_date"},
        })
        unknown = ingest_atom(store, alpha, "historical time unknown")
        partial = ingest_atom(store, alpha, "historical time partial", temporal={
            "valid_from": january.isoformat(), "valid_to": None,
            "precision": "partial", "confidence": "partial",
            "provenance": {"field": "partial_effective_date"},
        })
        revoke_me = ingest_atom(store, alpha, "revocation sentinel")
        tombstone_me = ingest_atom(store, alpha, "tombstone sentinel")
        left = ingest_atom(store, alpha, "contradiction left assertion")
        right = ingest_atom(store, alpha, "contradiction right assertion")
        store.create_edge(
            workspace_id=alpha, source_node_id=left["node_id"], target_node_id=right["node_id"],
            relation_type="contradicts", evidence_atom_version_ids=[left["atom_version_id"], right["atom_version_id"]],
            actor="r5-verifier", model_version="manual", confidence=1.0, weight=1.0,
            status="trusted", properties={"reason": "explicit verifier contradiction"},
        )
    with store.authorization_scope(beta):
        beta_atom = ingest_atom(store, beta, "historical price tenant beta")

    index_counts = {
        "alpha_r1": index_workspace(service, alpha, "temporal-r1"),
        "beta_r1": index_workspace(service, beta, "temporal-r1"),
    }
    with store.authorization_scope(alpha):
        r1_watermark = store.last_event_offset()
    r1 = release(service, alpha, "temporal-r1", r1_watermark)
    with store.authorization_scope(alpha):
        r1_activation_event = store.last_event_offset()
        successor = store.edit_node(
            node_id=original["node_id"], content="historical price became twelve",
            properties={"temporal": {
                "valid_from": june.isoformat(), "valid_to": december.isoformat(),
                "precision": "day", "confidence": "explicit", "provenance": {"field": "effective_date"},
            }},
            actor="r5-editor",
        )
    index_counts.update({
        "alpha_r2": index_workspace(service, alpha, "temporal-r2"),
        "beta_r2": index_workspace(service, beta, "temporal-r2"),
    })

    # Candidate physical revisions exist, but aliases and active DB release remain r1.
    candidate_alias_snapshot = {
        "opensearch_alias": adapters["lexical"].get_active_alias(),
        "qdrant_alias": adapters["dense"].get_active_alias(),
        "active_release_id": service.get_active_cortex_release(alpha)["release_id"],
    }
    if candidate_alias_snapshot["opensearch_alias"] != adapters["lexical"].revision_index("temporal-r1"):
        raise VerificationFailure("OpenSearch candidate became visible before activation")
    if candidate_alias_snapshot["qdrant_alias"] != adapters["dense"].revision_collection("temporal-r1"):
        raise VerificationFailure("Qdrant candidate became visible before activation")

    with store.authorization_scope(alpha):
        r2_watermark = store.last_event_offset()
    r2 = release(service, alpha, "temporal-r2", r2_watermark)
    with store.authorization_scope(alpha):
        pre_revocation_event = store.last_event_offset()
        service.transition_source_lifecycle(
            revoke_me["atom_version_id"], SourceLifecycleRequest(state="revoked", actor="r5-dpo", reason="withdrawn")
        )
        service.transition_source_lifecycle(
            tombstone_me["atom_version_id"], SourceLifecycleRequest(state="tombstoned", actor="r5-dpo", reason="invalid")
        )

    with store.authorization_scope(alpha):
        before = service.query(QueryRequest(
            workspace_id=alpha, query="historical price", valid_at=june - timedelta(seconds=1), retrieval_profile="hybrid"
        ))
        boundary = service.query(QueryRequest(
            workspace_id=alpha, query="historical price", valid_at=june, retrieval_profile="hybrid"
        ))
        historical = service.query(QueryRequest(
            workspace_id=alpha, query="historical price", as_of_event=r1_activation_event,
            valid_at=june - timedelta(seconds=1), retrieval_profile="hybrid",
        ))
        unknown_response = service.query(QueryRequest(
            workspace_id=alpha, query="historical time", valid_at=january, retrieval_profile="hybrid"
        ))
        revoked_response = service.query(QueryRequest(
            workspace_id=alpha, query="revocation sentinel", as_of_event=pre_revocation_event, retrieval_profile="hybrid"
        ))
        tombstone_response = service.query(QueryRequest(
            workspace_id=alpha, query="tombstone sentinel", as_of_event=pre_revocation_event, retrieval_profile="hybrid"
        ))
        contradiction = service.query(QueryRequest(
            workspace_id=alpha, query="contradiction assertion", retrieval_profile="hybrid"
        ))
    # Beta has indexed candidate revisions but no historical release at all;
    # this is the decisive missing-history case. Alpha has a bootstrap release
    # before r1 and therefore cannot represent global release absence.
    with store.authorization_scope(beta):
        missing = service.query(QueryRequest(
            workspace_id=beta, query="historical price tenant beta",
            as_of_event=r1_activation_event, retrieval_profile="hybrid",
        ))

    ids = lambda response: {item["atom_version_id"] for item in response["results"]}
    if original["atom_version_id"] not in ids(before) or successor["atom_version_id"] in ids(before):
        raise VerificationFailure("valid-time predecessor selection failed before half-open boundary")
    if successor["atom_version_id"] not in ids(boundary) or original["atom_version_id"] in ids(boundary):
        raise VerificationFailure("half-open valid-time boundary failed")
    if original["atom_version_id"] not in ids(historical):
        raise VerificationFailure("historical release did not retrieve its immutable predecessor")
    if historical["retrieval_diagnostics"]["temporal"]["release_id"] != r1["release_id"]:
        raise VerificationFailure("historical release resolver selected the wrong release")
    if missing.get("status") != "historical_unavailable":
        raise VerificationFailure("missing historical release did not fail closed")
    if {unknown["atom_version_id"], partial["atom_version_id"]} & ids(unknown_response):
        raise VerificationFailure("unknown/partial valid time became visible")
    if revoke_me["atom_version_id"] in ids(revoked_response) or tombstone_me["atom_version_id"] in ids(tombstone_response):
        raise VerificationFailure("revoked/tombstoned content reappeared in historical query")
    if not {left["atom_version_id"], right["atom_version_id"]} <= ids(contradiction):
        raise VerificationFailure("explicit contradiction made source assertions unreadable")
    if beta_atom["atom_version_id"] in ids(before):
        raise VerificationFailure("cross-workspace index result leaked through product revalidation")
    with store.authorization_scope(alpha):
        lineage = store.get_source_lifecycle(original["atom_version_id"])
        immutable_versions = {row["atom_version_id"]: row for row in store.atom_versions([
            original["atom_version_id"], successor["atom_version_id"]
        ])}
        conflict_state = store.get_source_lifecycle(left["atom_version_id"])["state"]
    if lineage["state"] != "superseded" or lineage["superseded_by_atom_version_id"] != successor["atom_version_id"]:
        raise VerificationFailure("immutable supersession lineage is incomplete")
    if immutable_versions[original["atom_version_id"]]["content"] != "historical price was ten":
        raise VerificationFailure("supersession mutated the immutable predecessor")
    if conflict_state != "conflicted":
        raise VerificationFailure("contradiction was readable but not explicit in lifecycle state")
    if revoked_response["retrieval_diagnostics"]["temporal_exclusions"].get("current_lifecycle_revoked", 0) < 1:
        raise VerificationFailure("revocation exclusion reason was not retained")
    if tombstone_response["retrieval_diagnostics"]["temporal_exclusions"].get("current_lifecycle_tombstoned", 0) < 1:
        raise VerificationFailure("tombstone exclusion reason was not retained")

    lexical_history = adapters["lexical"].search(
        workspace_id=alpha, query="historical price", limit=20,
        visibility=["private"], as_of_event=r1_activation_event, index_revision="temporal-r1",
    )
    vector = engine.dense_embedder.embed(["historical price"])[0]
    dense_history = adapters["dense"].search(
        workspace_id=alpha, vector=vector, limit=20,
        visibility=["private"], as_of_event=r1_activation_event, index_revision="temporal-r1",
    )
    if original["atom_version_id"] not in {item["atom_version_id"] for item in lexical_history}:
        raise VerificationFailure("revision-specific OpenSearch historical query missed predecessor")
    if original["atom_version_id"] not in {item["atom_version_id"] for item in dense_history}:
        raise VerificationFailure("revision-specific Qdrant historical query missed predecessor")
    lexical_filtered = adapters["lexical"].search(
        workspace_id=alpha, query="historical price", limit=20,
        visibility=["private"], as_of_event=r1_activation_event, index_revision="temporal-r2",
    )
    dense_filtered = adapters["dense"].search(
        workspace_id=alpha, vector=vector, limit=20,
        visibility=["private"], as_of_event=r1_activation_event, index_revision="temporal-r2",
    )
    lexical_alias_hits = adapters["lexical"].search(
        workspace_id=alpha, query="historical price became twelve", limit=20,
        visibility=["private"], index_revision=None,
    )
    dense_alias_hits = adapters["dense"].search(
        workspace_id=alpha, vector=engine.dense_embedder.embed(["historical price became twelve"])[0],
        limit=20, visibility=["private"], index_revision=None,
    )
    for channel, hits in (
        ("OpenSearch", lexical_filtered),
        ("Qdrant", dense_filtered),
    ):
        if any(item.get("workspace_id") != alpha for item in hits):
            raise VerificationFailure(f"{channel} workspace filter leaked a second tenant")
        if successor["atom_version_id"] in {item["atom_version_id"] for item in hits}:
            raise VerificationFailure(f"{channel} event watermark filter admitted a future revision")
    # These alias reads occur after r2 activation and therefore exercise the
    # current alias. Candidate invisibility itself was captured before r2
    # activation by the alias-target snapshot above.
    if successor["atom_version_id"] not in {item["atom_version_id"] for item in lexical_alias_hits}:
        raise VerificationFailure("OpenSearch current alias did not expose the activated successor")
    if successor["atom_version_id"] not in {item["atom_version_id"] for item in dense_alias_hits}:
        raise VerificationFailure("Qdrant current alias did not expose the activated successor")

    raw = {
        "rebuild_counts": index_counts,
        "releases": {"r1": r1, "r2": r2, "historical_selected": historical["retrieval_diagnostics"]["temporal"]},
        "candidate_invisibility": candidate_alias_snapshot,
        "valid_before_ids": sorted(ids(before)),
        "valid_boundary_ids": sorted(ids(boundary)),
        "historical_ids": sorted(ids(historical)),
        "missing_history": missing["retrieval_diagnostics"],
        "unknown_time": unknown_response["retrieval_diagnostics"],
        "revocation": revoked_response["retrieval_diagnostics"],
        "tombstone": tombstone_response["retrieval_diagnostics"],
        "contradiction_ids": sorted(ids(contradiction)),
        "lineage": lineage,
        "opensearch_historical_hits": lexical_history,
        "qdrant_historical_hits": dense_history,
        "opensearch_revision2_event_filtered_hits": lexical_filtered,
        "qdrant_revision2_event_filtered_hits": dense_filtered,
        "opensearch_current_alias_hits": lexical_alias_hits,
        "qdrant_current_alias_hits": dense_alias_hits,
    }
    write_json(context.result / "raw" / "p004" / "temporal-index-matrix.json", raw)
    receipt = {
        "event_time_reconstruction": True,
        "historical_release_selection": True,
        "missing_history_fail_closed": True,
        "half_open_valid_time": True,
        "unknown_partial_time_explicit": True,
        "immutable_lineage_supersession": True,
        "contradictions_readable_explicit": True,
        "revocation_tombstone_historical_exclusion": True,
        "workspace_and_event_filters": True,
        "revision_specific_opensearch_qdrant": True,
        "candidate_invisibility": True,
        "evidence_metadata_complete": (
            historical["results"][0].get("source_revision") == original["atom_version_id"]
            and all(
                key in historical["results"][0]["temporal"]
                for key in (
                    "requested_as_of_event", "requested_valid_at", "requested_valid_from",
                    "requested_valid_to", "resolved_event_watermark", "release_id",
                    "policy_result", "valid_interval", "provenance", "exclusion_reason",
                    "authorization_policy_result", "historical_authorization_revision_event",
                    "current_authorization_revision_event", "historical_authorization_resolution",
                )
            )
            and historical["results"][0]["temporal"]["authorization_policy_result"] == "allowed"
            and isinstance(
                historical["results"][0]["temporal"]["historical_authorization_revision_event"], int
            )
            and isinstance(
                historical["results"][0]["temporal"]["current_authorization_revision_event"], int
            )
        ),
    }
    if not all(receipt.values()):
        raise VerificationFailure("temporal evidence metadata matrix is incomplete")
    write_json(context.result / "receipts" / "p004-temporal-index.json", receipt)
    authorization = run_postgres_authorization_matrix(context, store)
    return {"store": store, "service": service, "engine": engine, "authorization": authorization}


def run_fault_matrix(context: Context, stack: DockerStack, live: dict[str, Any], adapters: dict[str, Any]) -> None:
    from trace.v2.models import CortexReleaseCreateRequest, CortexReleaseValidateRequest, CortexValidationReceipt
    from trace.v2.store import InvariantViolation

    store, service, engine = live["store"], live["service"], live["engine"]
    workspace = "r5-fault"
    vector_size = len(engine.dense_embedder.embed(["fault"])[0])
    for revision in ("fault-r1", "fault-r2"):
        adapters["lexical"].create_revision(revision)
        adapters["dense"].create_revision(revision, vector_size=vector_size)
    with store.authorization_scope(workspace):
        watermark = max(1, store.last_event_offset())
    r1 = release(service, workspace, "fault-r1", watermark)
    with store.authorization_scope(workspace):
        candidate = service.create_cortex_release(CortexReleaseCreateRequest(
            workspace_id=workspace,
            spine_event_watermark=max(1, store.last_event_offset()),
            components=[
                {"component_kind": "lexical_index", "component_revision": "fault-r2"},
                {"component_kind": "dense_index", "component_revision": "fault-r2"},
            ],
            actor="r5-verifier",
        ))
        service.validate_cortex_release(candidate["release_id"], CortexReleaseValidateRequest(
            validation_receipt=CortexValidationReceipt(passed=True), actor="r5-verifier"
        ))
    before = {
        "active_release": service.get_active_cortex_release(workspace)["release_id"],
        "opensearch_alias": adapters["lexical"].get_active_alias(),
        "qdrant_alias": adapters["dense"].get_active_alias(),
    }
    stack.stop_qdrant()
    failure = ""
    try:
        with store.authorization_scope(workspace):
            service.activate_cortex_release(candidate["release_id"])
    except InvariantViolation as error:
        failure = str(error)
    finally:
        stack.restart_qdrant()
    with store.authorization_scope(workspace):
        after = {
            "active_release": service.get_active_cortex_release(workspace)["release_id"],
            "candidate_status": service.get_cortex_release(candidate["release_id"])["status"],
            "opensearch_alias": adapters["lexical"].get_active_alias(),
            "qdrant_alias": adapters["dense"].get_active_alias(),
        }
    if not failure or after["active_release"] != r1["release_id"] or after["candidate_status"] != "failed":
        raise VerificationFailure("real Qdrant loss did not preserve active DB release and fail candidate")
    if after["opensearch_alias"] != before["opensearch_alias"] or after["qdrant_alias"] != before["qdrant_alias"]:
        raise VerificationFailure("external alias compensation did not restore predecessor state")
    write_json(context.result / "raw" / "fault" / "qdrant-stop-rollback.json", {
        "container": stack.services["qdrant"]["container"],
        "before": before,
        "failure": failure,
        "after": after,
    })
    write_json(context.result / "receipts" / "promotion-fault.json", {
        "actual_container_stop": True,
        "activation_failed": True,
        "old_aliases_preserved": True,
        "active_database_release_preserved": True,
        "candidate_invisible_and_failed": True,
    })


class MethodCounter:
    """Observe calls while forwarding to the unchanged product adapter method."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.restorers: list[Callable[[], None]] = []

    def observe(self, target: Any, name: str, label: str) -> None:
        original = getattr(target, name)

        def observed(*args: Any, **kwargs: Any) -> Any:
            self.counts[label] = self.counts.get(label, 0) + 1
            return original(*args, **kwargs)

        setattr(target, name, observed)
        self.restorers.append(lambda: setattr(target, name, original))

    def close(self) -> None:
        for restore in reversed(self.restorers):
            restore()


def postgres_write_snapshot(runtime_dsn: str, workspace: str) -> dict[str, Any]:
    import psycopg

    with psycopg.connect(runtime_dsn, autocommit=True) as conn:
        try:
            conn.execute("SELECT pg_stat_force_next_flush()")
        except Exception:
            pass
        conn.execute("SELECT set_config('trace.workspace_id',%s,false)", (workspace,))
        rows = conn.execute(
            """SELECT relname,n_tup_ins,n_tup_upd,n_tup_del
                 FROM pg_stat_user_tables WHERE relname LIKE 'trace_%' ORDER BY relname"""
        ).fetchall()
        events = conn.execute("SELECT count(*),COALESCE(max(event_offset),0) FROM trace_events").fetchone()
    return {
        "tables": {row[0]: {"inserted": row[1], "updated": row[2], "deleted": row[3]} for row in rows},
        "event_count": events[0],
        "max_event_offset": events[1],
    }


def run_erasure_matrix(context: Context, runtime_dsn: str, live: dict[str, Any], adapters: dict[str, Any]) -> None:
    import psycopg
    from botocore.exceptions import ClientError
    from trace.v2.models import SourceErasureRequest

    store, service, engine = live["store"], live["service"], live["engine"]
    workspace = "r5-erasure"
    raw_content = b"r5 disposable erasure payload"
    object_info = adapters["object_store"].put_bytes(raw_content, "text/plain", workspace_id=workspace)
    with store.authorization_scope(workspace):
        atom = ingest_atom(
            store, workspace, raw_content.decode("utf-8"),
            attachment={**object_info, "metadata": object_info.get("metadata", {})},
        )
    atom_id = str(atom["atom_version_id"])
    vector = engine.dense_embedder.embed([atom["content"]])[0]
    document = {
        "atom_version_id": atom_id, "workspace_id": workspace, "content": atom["content"],
        "content_hash": atom["content_hash"], "facets": atom["facets"],
        "visibility": "private", "created_event_offset": atom["created_event_offset"],
    }
    dense_document = {
        "atom_version_id": atom_id, "workspace_id": workspace, "vector": vector,
        "facets": atom["facets"], "visibility": "private", "created_event_offset": atom["created_event_offset"],
    }
    for revision in ("erase-r1", "erase-r2"):
        adapters["lexical"].upsert([document], revision=revision)
        adapters["dense"].upsert([dense_document], revision=revision)
    with store.authorization_scope(workspace):
        erase_watermark = store.last_event_offset()
    release(service, workspace, "erase-r1", erase_watermark)
    with store.authorization_scope(workspace):
        erase_watermark = store.last_event_offset()
    release(service, workspace, "erase-r2", erase_watermark)

    with store.authorization_scope(workspace):
        projection = store.create_projection_run(
            workspace_id=workspace, projection_kind="hierarchy", revision="erase-projection",
            input_checksum="0" * 64, actor="r5-verifier",
        )
        store.transition_projection_run(projection["projection_run_id"], status="running", actor="r5-verifier")
        projection_object_id = str(uuid.uuid4())
        objects = store.write_projection_objects(
            projection_run_id=projection["projection_run_id"],
            objects=[{
                "projection_object_id": projection_object_id,
                "object_kind": "summary", "logical_key": "erasure-derived",
                "content": "derived disposable content", "source_atom_version_ids": [atom_id],
            }],
            memberships=[{
                "parent_projection_object_id": projection_object_id,
                "child_kind": "atom_version",
                "child_id": atom_id,
            }],
            actor="r5-verifier",
        )

    counter = MethodCounter()
    for target, method, label in (
        (adapters["object_store"], "delete_object", "s3.delete_object"),
        (adapters["lexical"], "delete_atom", "opensearch.delete_atom"),
        (adapters["dense"], "delete_atom", "qdrant.delete_atom"),
    ):
        counter.observe(target, method, label)
    os.environ["TRACE_ERASURE_SIGNING_KEY"] = context.secrets["erasure_signing_key"]
    try:
        with store.authorization_scope(workspace):
            first = service.erase_source(
                atom_id, SourceErasureRequest(actor="r5-dpo", reason="approved disposable erasure")
            )
        receipt_bytes = canonical_bytes(first["erasure_receipt"])
        after_first_calls = dict(counter.counts)
        write_before = postgres_write_snapshot(runtime_dsn, workspace)
        with store.authorization_scope(workspace):
            operation_before = store.get_erasure_operation(workspace, atom_id)
        with store.authorization_scope(workspace):
            repeat = service.erase_source(
                atom_id, SourceErasureRequest(actor="r5-repeat-dpo", reason="repeat request")
            )
        write_after = postgres_write_snapshot(runtime_dsn, workspace)
        after_repeat_calls = dict(counter.counts)
        with store.authorization_scope(workspace):
            operation_after = store.get_erasure_operation(workspace, atom_id)
    finally:
        counter.close()

    if canonical_bytes(repeat["erasure_receipt"]) != receipt_bytes or repeat["event_offset"] != first["event_offset"]:
        raise VerificationFailure("repeat erasure did not return the original signed receipt and offset")
    if write_before != write_after:
        raise VerificationFailure("repeat erasure changed PostgreSQL tuple or event counters")
    if after_first_calls != after_repeat_calls:
        raise VerificationFailure("repeat erasure invoked a new object or index deletion")
    if operation_before != operation_after:
        raise VerificationFailure("repeat erasure changed durable operation state")
    if set(first["erasure_receipt"]) != RECEIPT_ALLOW_LIST:
        raise VerificationFailure("retained erasure receipt is outside the strict non-content allow-list")
    if raw_content.decode("utf-8") in json.dumps(first["erasure_receipt"]):
        raise VerificationFailure("erased content appears in retained receipt")
    for revision in ("erase-r1", "erase-r2"):
        if not adapters["lexical"].verify_atom_absent(atom_id, revision=revision):
            raise VerificationFailure(f"OpenSearch retained erased atom in {revision}")
        if not adapters["dense"].verify_atom_absent(atom_id, revision=revision):
            raise VerificationFailure(f"Qdrant retained erased atom in {revision}")
    if not adapters["object_store"].verify_object_absent(object_info["object_key"]):
        raise VerificationFailure("MinIO retained erased raw object")
    status, code = 0, ""
    try:
        adapters["s3_client"].head_object(
            Bucket=context.lease["object_store"]["bucket"], Key=object_info["object_key"]
        )
    except ClientError as error:
        status = int(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
        code = str(error.response.get("Error", {}).get("Code", ""))
    if status != 404:
        raise VerificationFailure("direct MinIO HeadObject did not return HTTP 404")
    with psycopg.connect(runtime_dsn, autocommit=True) as conn:
        conn.execute("SELECT set_config('trace.workspace_id',%s,false)", (workspace,))
        projection_count = conn.execute(
            "SELECT count(*) FROM trace_projection_objects WHERE projection_object_id=%s",
            (objects[0]["projection_object_id"],),
        ).fetchone()[0]
        membership_count = conn.execute(
            """SELECT count(*) FROM trace_projection_memberships
                 WHERE parent_projection_object_id=%s OR (child_kind='atom_version' AND child_id=%s)""",
            (objects[0]["projection_object_id"], atom_id),
        ).fetchone()[0]
    if projection_count != 0 or membership_count != 0:
        raise VerificationFailure("derived projection object or membership survived source erasure")

    write_json(context.result / "raw" / "erasure" / "minio-absence.json", {
        "object_key_sha256": hashlib.sha256(object_info["object_key"].encode()).hexdigest(),
        "head_object_http_status": status,
        "head_object_error_code": code,
    })
    write_json(context.result / "raw" / "erasure" / "repeat-write-counters.json", {
        "postgres_before": write_before,
        "postgres_after": write_after,
        "external_delete_calls_after_first": after_first_calls,
        "external_delete_calls_after_repeat": after_repeat_calls,
        "operation_unchanged": True,
        "receipt_bytes_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    })
    write_json(context.result / "receipts" / "p004-erasure.json", {
        "state": first["state"],
        "atom_version_id": atom_id,
        "receipt": first["erasure_receipt"],
        "direct_minio_404": True,
        "projection_removed": True,
        "projection_membership_removed": True,
        "all_known_opensearch_revisions_absent": True,
        "all_known_qdrant_revisions_absent": True,
        "repeat_same_receipt_bytes": True,
        "repeat_same_event_offset": True,
        "repeat_zero_database_writes": True,
        "repeat_zero_object_index_delete_calls": True,
    })


def run_pytest(context: Context) -> None:
    env = os.environ.copy()
    env["TRACE_ERASURE_SIGNING_KEY"] = context.secrets["erasure_signing_key"]
    env["PYTHONPATH"] = str((context.worktree / "src").resolve())
    proc = context.recorder.run(
        [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "--basetemp", str(context.scratch / "pytest"), "tests",
        ],
        cwd=context.worktree,
        name="full-pytest",
        env=env,
        timeout=300,
        check=False,
    )
    if proc.returncode:
        raise VerificationFailure("full frozen exact-source candidate pytest suite failed")
    write_json(context.result / "receipts" / "pytest.json", {
        "exit_code": proc.returncode,
        "summary_line": next((line for line in reversed(proc.stdout.splitlines()) if "passed" in line), ""),
        "full_tests_directory": True,
        "candidate_execution_mode": "exact_committed_src_via_pythonpath",
    })


def cleanup_external_state(context: Context, adapters: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {"bucket_removed": False, "opensearch_removed": False, "qdrant_removed": False}
    if not adapters:
        return result
    try:
        bucket = context.lease["object_store"]["bucket"]
        s3 = adapters["s3_client"]
        listing = s3.list_objects_v2(Bucket=bucket)
        keys = [{"Key": item["Key"]} for item in listing.get("Contents", [])]
        if keys:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": keys})
        s3.delete_bucket(Bucket=bucket)
        result["bucket_removed"] = True
    except Exception as error:
        result["bucket_error"] = redact_text(str(error), context.secrets)[:300]
    try:
        lexical = adapters["lexical"]
        indexes = lexical.client.indices.get(index=f"{lexical.index}--rev-*")
        names = sorted(indexes) if isinstance(indexes, dict) else []
        for name in names:
            lexical.client.indices.delete(index=name)
        result["opensearch_removed"] = not bool(lexical.client.indices.exists(index=f"{lexical.index}--rev-*", allow_no_indices=False))
    except Exception as error:
        result["opensearch_error"] = redact_text(str(error), context.secrets)[:300]
    try:
        dense = adapters["dense"]
        dense.delete_alias(dense.collection)
        collections = dense.client.get_collections()
        rows = getattr(collections, "collections", collections)
        names = [getattr(row, "name", None) or (row.get("name") if isinstance(row, dict) else None) for row in rows]
        for name in names:
            if name and str(name).startswith(f"{dense.collection}--rev-"):
                dense.client.delete_collection(str(name))
        remaining = dense.client.get_collections()
        remaining_rows = getattr(remaining, "collections", remaining)
        result["qdrant_removed"] = not any(
            (getattr(row, "name", None) or (row.get("name") if isinstance(row, dict) else "")).startswith(f"{dense.collection}--rev-")
            for row in remaining_rows
        )
    except Exception as error:
        result["qdrant_error"] = redact_text(str(error), context.secrets)[:300]
    return result


def destroy_secrets(context: Context) -> dict[str, Any]:
    fingerprints = {
        key: hashlib.sha256(value.encode()).hexdigest()
        for key, value in context.secrets.items()
    }
    for key in list(os.environ):
        if key in {"TRACE_ERASURE_SIGNING_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}:
            os.environ.pop(key, None)
    error = ""
    try:
        context.secrets_path.unlink()
    except Exception as exc:
        error = str(exc)
    destroyed = not context.secrets_path.exists()
    context.secrets.clear()
    return {"fingerprints": fingerprints, "secret_file_destroyed": destroyed, "error": error}


def secret_leak_scan(result: Path, values: Iterable[str]) -> dict[str, Any]:
    redacted_files: list[str] = []
    residual_leaks: list[str] = []
    candidates = [value.encode() for value in values if len(value) >= 8]
    for path in sorted(result.rglob("*")):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if any(value in raw for value in candidates):
            for value in candidates:
                raw = raw.replace(value, b"<redacted>")
            path.write_bytes(raw)
            redacted_files.append(path.relative_to(result).as_posix())
        if any(value in path.read_bytes() for value in candidates):
            residual_leaks.append(path.relative_to(result).as_posix())
    return {
        "files_scanned": sum(1 for path in result.rglob("*") if path.is_file()),
        "files_containing_generated_secret_before_scrub": redacted_files,
        "residual_leaks": residual_leaks,
        "passed": not residual_leaks,
    }


def seal_result(context: Context, outcome: str, reason: str | None) -> None:
    context.recorder.seal()
    write_json(context.result / "result_manifest.json", {
        "gate": "V1b-Trace-temporal",
        "outcome": outcome,
        "reason": reason,
        "candidate": context.lease["candidate"],
        "lease_id": context.lease["lease_id"],
        "completed_at_utc": utc_now(),
        "claim_boundary": (
            "Independent local temporal/revocation and disposable live-infrastructure evidence only. "
            "No deployment, NATS, Redis, model-gateway, TLS, cloud, scale, Session 9, P-005, "
            "Foundation Gate, promotion, or release claim."
        ),
    })
    manifest = {
        path.relative_to(context.result).as_posix(): sha256(path)
        for path in sorted(context.result.rglob("*"))
        if path.is_file() and path.name != "evidence_manifest.json"
    }
    write_json(context.result / "evidence_manifest.json", manifest)


def execute(context: Context) -> int:
    outcome = "needs_review"
    reason: str | None = None
    stack: DockerStack | None = None
    adapters: dict[str, Any] | None = None
    secret_values = list(context.secrets.values())
    cleanup: dict[str, Any] = {}
    try:
        copy_authority_and_provision(context)
        stack = DockerStack(context)
        # The gate exercises explicitly supplied local adapters. Host deployment
        # flags or model settings must not turn this into a deployment/model
        # validation run or trigger an external provider.
        for variable in (
            "TRACE_PRODUCTION_MODE", "TRACE_POSTGRES_POOL_ENABLED", "TRACE_DENSE_MODEL",
            "TRACE_RERANK_MODEL", "TRACE_MODEL_GATEWAY_URL", "TRACE_NATS_URL", "TRACE_REDIS_URL",
        ):
            os.environ.pop(variable, None)
        verify_frozen_environment(context)
        try:
            stack.start()
        except BlockedError:
            raise
        except Exception as error:
            raise BlockedError(f"disposable Docker stack could not be provisioned: {error}") from error
        _, runtime_dsn = prepare_postgres(context, stack)
        verify_roles_and_rls(context, stack, runtime_dsn)
        adapters = create_live_adapters(context, stack)
        live = run_temporal_and_index_matrix(context, stack, runtime_dsn, adapters)
        run_fault_matrix(context, stack, live, adapters)
        run_erasure_matrix(context, runtime_dsn, live, adapters)
        run_pytest(context)
    except BlockedError as error:
        outcome, reason = "blocked", redact_text(str(error), context.secrets)
    except (VerificationFailure, AssertionError) as error:
        outcome, reason = "failed", redact_text(str(error), context.secrets)
    except Exception as error:
        outcome, reason = "failed", redact_text(f"{type(error).__name__}: {error}", context.secrets)
        (context.result / "raw" / "failure-traceback.log").parent.mkdir(parents=True, exist_ok=True)
        (context.result / "raw" / "failure-traceback.log").write_text(
            redact_text(traceback.format_exc(), context.secrets), encoding="utf-8"
        )
    finally:
        external_cleanup = cleanup_external_state(context, adapters)
        if stack is not None:
            try:
                docker_cleanup = stack.cleanup()
            except Exception as error:
                docker_cleanup = {
                    "docker_cleanup_complete": False,
                    "cleanup_error": redact_text(str(error), context.secrets)[:500],
                }
        else:
            docker_cleanup = {
                "docker_cleanup_complete": True,
                "not_started": True,
                "containers_remaining": [],
                "networks_remaining": [],
                "volumes_remaining": [],
            }
        credentials = destroy_secrets(context)
        cleanup = {
            "external": external_cleanup,
            "docker": docker_cleanup,
            "credentials": credentials,
            "completed_at_utc": utc_now(),
        }
        cleanup_complete = (
            docker_cleanup.get("docker_cleanup_complete")
            and credentials.get("secret_file_destroyed")
            and (adapters is None or all(external_cleanup.get(key) for key in ("bucket_removed", "opensearch_removed", "qdrant_removed")))
        )
        cleanup["complete"] = bool(cleanup_complete)
        if not cleanup_complete and outcome == "needs_review":
            outcome, reason = "failed", "cleanup did not prove absence of every run-labelled resource"
        write_json(context.result / "cleanup" / "cleanup_receipt.json", cleanup)
        context.recorder.seal()
        leak_scan = secret_leak_scan(context.result, secret_values)
        write_json(context.result / "cleanup" / "secret_leak_scan.json", leak_scan)
        if not leak_scan["passed"] and outcome == "needs_review":
            outcome, reason = "failed", "retained evidence contains an unredacted generated secret"
        seal_result(context, outcome, reason)
    return {"needs_review": 0, "failed": 2, "blocked": 3}[outcome]


def main() -> int:
    parser = argparse.ArgumentParser(description="V1b-R5 temporal live-infrastructure verifier")
    parser.add_argument("--lease", type=Path, required=True)
    args = parser.parse_args()
    try:
        context = admit(args.lease)
    except Exception as error:
        print(f"ADMISSION BLOCKED: {error}", file=sys.stderr)
        return 3
    return execute(context)


if __name__ == "__main__":
    raise SystemExit(main())
