"""Create one external, write-once V1b verifier secret packet.

Only the packet SHA-256 is printed.  Secret values never enter repository or
evidence roots and are deleted by the temporal verifier during cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from pathlib import Path


SECRET_KEYS = (
    "postgres_admin_password",
    "postgres_migration_password",
    "postgres_runtime_password",
    "minio_access_key",
    "minio_secret_key",
    "erasure_signing_key",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    values = {key: secrets.token_urlsafe(36) for key in SECRET_KEYS}
    payload = (json.dumps(values, sort_keys=True) + "\n").encode("utf-8")
    with target.open("xb") as handle:
        handle.write(payload)
    print(hashlib.sha256(payload).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
