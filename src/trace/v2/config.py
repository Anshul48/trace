"""Typed, fail-closed deployment configuration for Trace V2.

The application deliberately keeps configuration separate from request payloads.
In particular, a caller can select only a registered ``model_id``; provider
URLs, credentials, regions, and deployment profile are process configuration.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class DeploymentProfile(StrEnum):
    SELF_HOSTED = "self_hosted"
    GCP_MUMBAI = "gcp_mumbai"


class ConfigurationError(ValueError):
    """Raised before serving traffic when a deployment is unsafe or ambiguous."""


def _bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"invalid boolean value {value!r}")


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


@dataclass(frozen=True)
class TraceSettings:
    """The small, reviewable set of process-wide release controls.

    ``production_mode`` is intentionally distinct from selecting a profile:
    developers can use the self-hosted profile with the embedded adapters,
    while an operator must explicitly opt into production gates.
    """

    profile: DeploymentProfile
    production_mode: bool
    gcp_region: str | None
    repository: str
    object_store: str
    opensearch_index: str | None
    qdrant_collection: str | None
    nats_url: str | None
    redis_url: str | None
    auth_required: bool
    allowed_models: tuple[str, ...]
    model_gateway_url: str | None
    workspace_data_region: str | None
    postgres_runtime_role: str | None
    postgres_migration_role: str | None
    postgres_pool_enabled: bool
    webhook_kms_key: str | None
    deep_model: str | None
    schema_model: str | None

    @property
    def requires_external_indexes(self) -> bool:
        return self.production_mode

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> "TraceSettings":
        env = os.environ if environ is None else environ
        try:
            profile = DeploymentProfile(env.get("TRACE_DEPLOYMENT_PROFILE", DeploymentProfile.SELF_HOSTED.value).strip().lower())
        except ValueError as error:
            raise ConfigurationError("TRACE_DEPLOYMENT_PROFILE must be self_hosted or gcp_mumbai") from error
        settings = cls(
            profile=profile,
            production_mode=_bool(env.get("TRACE_PRODUCTION_MODE"), default=False),
            gcp_region=env.get("TRACE_GCP_REGION"),
            repository=env.get("TRACE_REPOSITORY", "sqlite").lower(),
            object_store=env.get("TRACE_OBJECT_STORE", "local").lower(),
            opensearch_index=env.get("TRACE_OPENSEARCH_INDEX"),
            qdrant_collection=env.get("TRACE_QDRANT_COLLECTION"),
            nats_url=env.get("TRACE_NATS_URL"),
            redis_url=env.get("TRACE_REDIS_URL"),
            auth_required=_bool(env.get("TRACE_AUTH_REQUIRED"), default=False),
            allowed_models=_csv(env.get("TRACE_ALLOWED_MODELS")) or ("deepseek-v4-flash", "deepseek-v4-pro"),
            model_gateway_url=env.get("TRACE_MODEL_GATEWAY_URL"),
            workspace_data_region=env.get("TRACE_WORKSPACE_DATA_REGION"),
            postgres_runtime_role=env.get("TRACE_POSTGRES_RUNTIME_ROLE"),
            postgres_migration_role=env.get("TRACE_POSTGRES_MIGRATION_ROLE"),
            postgres_pool_enabled=_bool(env.get("TRACE_POSTGRES_POOL_ENABLED"), default=False),
            webhook_kms_key=env.get("TRACE_WEBHOOK_KMS_KEY"),
            deep_model=env.get("TRACE_DEEP_MODEL"),
            schema_model=env.get("TRACE_SCHEMA_MODEL"),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.profile is DeploymentProfile.GCP_MUMBAI:
            if self.gcp_region != "asia-south1":
                raise ConfigurationError("gcp_mumbai requires TRACE_GCP_REGION=asia-south1")
            if self.workspace_data_region and self.workspace_data_region != "asia-south1":
                raise ConfigurationError("workspace data may not be placed outside asia-south1")
        if not self.production_mode:
            return
        if not self.auth_required:
            raise ConfigurationError("TRACE_AUTH_REQUIRED=true is required in production mode")
        if self.repository not in {"postgres", "postgresql"}:
            raise ConfigurationError("production mode requires TRACE_REPOSITORY=postgres")
        if not self.postgres_runtime_role or not self.postgres_migration_role:
            raise ConfigurationError(
                "production mode requires distinct TRACE_POSTGRES_RUNTIME_ROLE and TRACE_POSTGRES_MIGRATION_ROLE"
            )
        if self.postgres_runtime_role == self.postgres_migration_role:
            raise ConfigurationError("runtime and migration PostgreSQL roles must be distinct in production mode")
        if not self.postgres_pool_enabled:
            raise ConfigurationError("production mode requires TRACE_POSTGRES_POOL_ENABLED=true")
        if not self.webhook_kms_key:
            raise ConfigurationError("production mode requires TRACE_WEBHOOK_KMS_KEY for durable webhook secret encryption")
        if self.object_store not in {"s3", "minio", "gcs"}:
            raise ConfigurationError("production mode requires a private S3/GCS-compatible object store")
        missing = [name for name, value in {
            "TRACE_OPENSEARCH_INDEX": self.opensearch_index,
            "TRACE_QDRANT_COLLECTION": self.qdrant_collection,
            "TRACE_NATS_URL": self.nats_url,
            "TRACE_REDIS_URL": self.redis_url,
        }.items() if not value]
        if missing:
            raise ConfigurationError("production mode requires " + ", ".join(missing))
        if not self.model_gateway_url:
            raise ConfigurationError("production mode requires TRACE_MODEL_GATEWAY_URL")
        if set(self.allowed_models) - {"deepseek-v4-flash", "deepseek-v4-pro"}:
            raise ConfigurationError("TRACE_ALLOWED_MODELS contains a model absent from the deployed registry")
        if self.deep_model or self.schema_model:
            raise ConfigurationError(
                "TRACE_DEEP_MODEL and TRACE_SCHEMA_MODEL are not direct-provider settings in production; "
                "use a registered request model_id through TRACE_MODEL_GATEWAY_URL"
            )

    def public_dict(self) -> dict[str, object]:
        """Safe deployment information suitable for readiness and diagnostics."""

        return {
            "profile": self.profile.value,
            "production_mode": self.production_mode,
            "gcp_region": self.gcp_region,
            "workspace_data_region": self.workspace_data_region,
            "allowed_models": list(self.allowed_models),
            "external_indexes_required": self.requires_external_indexes,
            "postgres_runtime_role": self.postgres_runtime_role,
            "postgres_pool_enabled": self.postgres_pool_enabled,
            "webhook_kms_configured": bool(self.webhook_kms_key),
        }


def load_global_context(path: str | None = None) -> dict[str, object]:
    """Load the non-secret dispatch contract without making it a runtime secret.

    This is useful to deployment preflight tooling and deliberately tolerates a
    source checkout that has not bundled the document into a wheel.
    """

    from pathlib import Path

    context_path = Path(path or os.environ.get("TRACE_GLOBAL_CONTEXT_PATH", "docs/global-context.v1.json"))
    try:
        value = json.loads(context_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigurationError(f"cannot read global context artifact: {context_path}") from error
    if value.get("schema_version") != 1:
        raise ConfigurationError("unsupported global context schema_version")
    return value
