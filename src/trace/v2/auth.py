"""OIDC JWT and scoped API-key identity for the Trace V2 HTTP boundary."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


class AuthenticationError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 401, code: str = "authentication_failed") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class AuthorizationError(RuntimeError):
    def __init__(self, message: str, *, code: str = "insufficient_scope") -> None:
        super().__init__(message)
        self.status_code = 403
        self.code = code


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class Principal:
    """Server-derived request identity and non-escalatable permissions."""

    subject: str
    auth_method: str
    workspace_ids: frozenset[str] | None = None
    allowed_visibility: frozenset[str] = frozenset({"private"})
    model_permissions: frozenset[str] = frozenset()
    scopes: frozenset[str] = frozenset()
    claims: Mapping[str, Any] = field(default_factory=dict)

    @property
    def wildcard_workspaces(self) -> bool:
        return self.workspace_ids is None

    def can_workspace(self, workspace_id: str) -> bool:
        return self.workspace_ids is None or workspace_id in self.workspace_ids

    def require_workspace(self, workspace_id: str) -> None:
        if not workspace_id or not self.can_workspace(workspace_id):
            raise AuthorizationError("workspace is outside the authenticated principal's scope", code="workspace_scope_denied")

    def require_scope(self, scope: str) -> None:
        if scope not in self.scopes and "*" not in self.scopes:
            raise AuthorizationError(f"required scope {scope!r} is not granted")

    def validate_grant(
        self,
        *,
        scopes: Sequence[str],
        allowed_visibility: Sequence[str],
        model_permissions: Sequence[str],
    ) -> None:
        """Reject delegated API-key permissions wider than the caller's.

        An authenticated administrator may mint a narrower key, but a request
        body can never turn that authority into a broader tenant, visibility,
        model, or cloud grant.
        """

        requested_scopes = {str(value) for value in scopes}
        if "*" not in self.scopes and not requested_scopes <= self.scopes:
            raise AuthorizationError("API-key scopes exceed authenticated scope", code="scope_escalation_denied")
        requested_visibility = {str(value) for value in allowed_visibility}
        if not requested_visibility <= self.allowed_visibility:
            raise AuthorizationError("API-key visibility exceeds authenticated clearance", code="visibility_scope_denied")
        requested_models = {str(value) for value in model_permissions}
        if requested_models and ("*" not in self.model_permissions and not requested_models <= self.model_permissions):
            raise AuthorizationError("API-key model permissions exceed authenticated permissions", code="model_scope_denied")

    def privacy_context(self, requested: Mapping[str, Any] | None = None) -> dict[str, Any]:
        requested = dict(requested or {})
        requested_model = requested.get("model") or requested.get("model_permission")
        if requested_model and self.model_permissions and str(requested_model) not in self.model_permissions and "*" not in self.model_permissions:
            raise AuthorizationError("requested model is outside authenticated model permissions", code="model_scope_denied")
        if requested.get("allow_cloud") and self.model_permissions and not ({"cloud", "model:cloud", "*"} & self.model_permissions):
            raise AuthorizationError("cloud model access is outside authenticated model permissions", code="model_scope_denied")
        if requested.get("allow_cloud") and not self.model_permissions and self.auth_method != "anonymous":
            raise AuthorizationError("cloud model access was not granted", code="model_scope_denied")
        requested_visibility = requested.get("allowed_visibility")
        if requested_visibility is None and requested.get("visibility") is not None:
            requested_visibility = [requested["visibility"]]
        if requested_visibility is None:
            effective = sorted(self.allowed_visibility)
        else:
            requested_values = {str(value) for value in requested_visibility}
            if not requested_values <= self.allowed_visibility:
                raise AuthorizationError("privacy visibility exceeds authenticated clearance", code="visibility_scope_denied")
            effective = sorted(requested_values)
        requested.pop("allowed_visibility", None)
        requested.pop("visibility", None)
        return {**requested, "allowed_visibility": effective, "principal_subject": self.subject}


class IdentityProvider:
    """Authenticate request headers using API keys or signed JWTs."""

    def __init__(self, *, required: bool | None = None, api_keys: Mapping[str, Mapping[str, Any]] | None = None, jwt_secret: str | None = None, key_resolver: Any | None = None) -> None:
        self.required = (os.environ.get("TRACE_AUTH_REQUIRED", "false").lower() == "true") if required is None else required
        self.api_keys = dict(api_keys or self._load_api_keys())
        self.jwt_secret = jwt_secret or os.environ.get("TRACE_JWT_SECRET")
        self.key_resolver = key_resolver
        try:
            self.oidc_jwks = json.loads(os.environ.get("TRACE_OIDC_JWKS_JSON", "{}"))
        except json.JSONDecodeError as error:
            raise ValueError("TRACE_OIDC_JWKS_JSON must be valid JSON") from error

    @staticmethod
    def _load_api_keys() -> dict[str, Mapping[str, Any]]:
        raw = os.environ.get("TRACE_API_KEYS_JSON", "")
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("TRACE_API_KEYS_JSON must be valid JSON") from error
        if isinstance(value, list):
            result: dict[str, Mapping[str, Any]] = {}
            for item in value:
                if isinstance(item, dict) and item.get("key"):
                    result[str(item["key"])] = item
            return result
        if not isinstance(value, dict):
            raise ValueError("TRACE_API_KEYS_JSON must be an object or list")
        return {str(key): value for key, value in value.items() if isinstance(value, dict)}

    @staticmethod
    def _principal_from_claims(claims: Mapping[str, Any], *, auth_method: str) -> Principal:
        subject = str(claims.get("sub") or claims.get("subject") or "anonymous")
        raw_workspaces = claims.get("workspace_ids", claims.get("workspaces"))
        if raw_workspaces in (None, "*"):
            workspace_ids = None
        elif isinstance(raw_workspaces, str):
            workspace_ids = frozenset(item for item in raw_workspaces.split(",") if item)
        else:
            workspace_ids = frozenset(str(item) for item in raw_workspaces)
        raw_visibility = claims.get("allowed_visibility", claims.get("visibility", ["private"]))
        if isinstance(raw_visibility, str):
            raw_visibility = [raw_visibility]
        raw_models = claims.get("model_permissions", claims.get("models", []))
        raw_scopes = claims.get("scope", claims.get("scopes", []))
        if isinstance(raw_models, str):
            raw_models = raw_models.split()
        if isinstance(raw_scopes, str):
            raw_scopes = raw_scopes.split()
        return Principal(
            subject=subject,
            auth_method=auth_method,
            workspace_ids=workspace_ids,
            allowed_visibility=frozenset(str(item) for item in raw_visibility),
            model_permissions=frozenset(str(item) for item in raw_models),
            scopes=frozenset(str(item) for item in raw_scopes),
            claims=claims,
        )

    def _api_key(self, value: str) -> Principal | None:
        entry = self.api_keys.get(value)
        if entry is None and self.key_resolver is not None:
            entry = self.key_resolver(value)
        if entry is None:
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
            for configured, candidate in self.api_keys.items():
                if configured.startswith("sha256:") and hmac.compare_digest(configured[7:], digest):
                    entry = candidate
                    break
                if candidate.get("key_sha256") and hmac.compare_digest(str(candidate["key_sha256"]), digest):
                    entry = candidate
                    break
        if entry is None:
            return None
        if entry.get("workspace_id") and not entry.get("workspace_ids"):
            entry = {**entry, "workspace_ids": [entry["workspace_id"]]}
        return self._principal_from_claims(entry, auth_method="api_key")

    def _jwt(self, token: str) -> Principal:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthenticationError("malformed bearer token")
        try:
            header = json.loads(_b64decode(parts[0]))
            claims = json.loads(_b64decode(parts[1]))
        except (ValueError, json.JSONDecodeError) as error:
            raise AuthenticationError("malformed bearer token") from error
        algorithm = header.get("alg")
        if algorithm == "HS256":
            if not self.jwt_secret:
                raise AuthenticationError("JWT verification key is not configured")
            expected = _b64encode(hmac.new(self.jwt_secret.encode("utf-8"), f"{parts[0]}.{parts[1]}".encode("ascii"), hashlib.sha256).digest())
            if not hmac.compare_digest(expected, parts[2]):
                raise AuthenticationError("JWT signature verification failed")
        elif algorithm in {"RS256", "RS384", "RS512"}:
            # OIDC providers normally sign with rotating RSA keys.  PyJWT is
            # optional; deployments provide a pinned JWKS document or a
            # JWKS-refreshing authenticator around this boundary.
            try:
                import jwt
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise AuthenticationError("PyJWT is required for RS256 OIDC verification") from error
            key_id = header.get("kid")
            key_data = next((item for item in self.oidc_jwks.get("keys", []) if item.get("kid") == key_id), None)
            if not key_data:
                raise AuthenticationError("OIDC signing key is not configured")
            try:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
                jwt.decode(token, key=key, algorithms=[algorithm], options={"verify_aud": False})
            except Exception as error:
                raise AuthenticationError("OIDC JWT signature verification failed") from error
        else:
            raise AuthenticationError("JWT algorithm is not trusted")
        now = int(time.time())
        if claims.get("exp") is not None and now >= int(claims["exp"]):
            raise AuthenticationError("JWT has expired")
        if claims.get("nbf") is not None and now < int(claims["nbf"]):
            raise AuthenticationError("JWT is not active yet")
        issuer = os.environ.get("TRACE_OIDC_ISSUER")
        if issuer and claims.get("iss") != issuer:
            raise AuthenticationError("JWT issuer is not trusted")
        audience = os.environ.get("TRACE_OIDC_AUDIENCE")
        if audience:
            audiences = claims.get("aud", [])
            audiences = [audiences] if isinstance(audiences, str) else audiences
            if audience not in audiences:
                raise AuthenticationError("JWT audience is not trusted")
        return self._principal_from_claims(claims, auth_method="oidc_jwt")

    def authenticate(self, headers: Mapping[str, str]) -> Principal:
        api_key = headers.get("x-api-key") or headers.get("X-API-Key")
        authorization = headers.get("authorization") or headers.get("Authorization")
        principal: Principal | None = None
        if api_key:
            principal = self._api_key(api_key)
            if principal is None:
                raise AuthenticationError("API key is invalid")
        elif authorization:
            scheme, _, value = authorization.partition(" ")
            if scheme.lower() != "bearer" or not value:
                raise AuthenticationError("Authorization must use a bearer token")
            principal = self._jwt(value)
        elif self.required:
            raise AuthenticationError("an OIDC JWT or scoped API key is required")
        else:
            # Development/embedded mode is explicitly opt-out.  Production
            # startup sets TRACE_AUTH_REQUIRED=true and never reaches this
            # wildcard principal.
            principal = Principal(
                subject="anonymous", auth_method="anonymous", workspace_ids=None,
                allowed_visibility=frozenset({"private", "internal", "public"}),
                model_permissions=frozenset(), scopes=frozenset({"*"}),
            )
        return principal


def enforce_workspace(principal: Principal, workspace_id: str | None) -> str:
    if not workspace_id:
        raise AuthorizationError("workspace_id is required for this operation", code="workspace_required")
    principal.require_workspace(workspace_id)
    return workspace_id
