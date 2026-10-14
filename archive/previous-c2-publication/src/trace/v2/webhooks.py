"""Signed completion webhook helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import ipaddress
import socket
import urllib.error
import urllib.request
from contextlib import nullcontext
from typing import Any, Mapping
from urllib.parse import urlparse


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class WebhookSecretCipher:
    """Small dependency-free envelope for embedded secret-at-rest protection.

    Production should set ``TRACE_WEBHOOK_MASTER_KEY`` and may replace this
    class with a KMS-backed implementation.  The stored value is authenticated
    ciphertext; plaintext webhook secrets are returned only at creation or
    rotation time.
    """

    def __init__(self, master_key: str | bytes | None = None) -> None:
        configured = master_key or os.environ.get("TRACE_WEBHOOK_MASTER_KEY") or "trace-development-webhook-master"
        self.key = hashlib.sha256(configured.encode() if isinstance(configured, str) else configured).digest()

    def encrypt(self, plaintext: str) -> str:
        nonce = secrets.token_bytes(16)
        stream = self._stream(nonce, len(plaintext.encode("utf-8")))
        ciphertext = bytes(left ^ right for left, right in zip(plaintext.encode("utf-8"), stream, strict=True))
        tag = hmac.new(self.key, nonce + ciphertext, hashlib.sha256).digest()
        return _b64(nonce + tag + ciphertext)

    def decrypt(self, encoded: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            nonce, tag, ciphertext = raw[:16], raw[16:48], raw[48:]
        except (ValueError, TypeError) as error:
            raise ValueError("invalid webhook secret ciphertext") from error
        expected = hmac.new(self.key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, tag):
            raise ValueError("webhook secret authentication failed")
        stream = self._stream(nonce, len(ciphertext))
        return bytes(left ^ right for left, right in zip(ciphertext, stream, strict=True)).decode("utf-8")

    def _stream(self, nonce: bytes, length: int) -> bytes:
        output = bytearray()
        counter = 0
        while len(output) < length:
            output.extend(hmac.new(self.key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
            counter += 1
        return bytes(output[:length])


class KmsWebhookSecretCipher:
    """Envelope backed by a configured cloud/operator KMS key.

    The implementation supports the GCP and AWS SDKs already used by the
    production profiles.  It is selected only through process configuration;
    callers never submit a KMS key ID or encrypted-secret material.
    """

    def __init__(self, key_id: str | None = None, *, provider: str | None = None, client: Any | None = None) -> None:
        self.key_id = key_id or os.environ.get("TRACE_WEBHOOK_KMS_KEY")
        if not self.key_id:
            raise ValueError("TRACE_WEBHOOK_KMS_KEY is required for KMS webhook secret encryption")
        inferred = "gcp" if self.key_id.startswith("projects/") else "aws"
        self.provider = (provider or os.environ.get("TRACE_WEBHOOK_KMS_PROVIDER") or inferred).lower()
        if self.provider not in {"gcp", "aws"}:
            raise ValueError("TRACE_WEBHOOK_KMS_PROVIDER must be gcp or aws")
        self.client = client

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        if self.provider == "gcp":
            try:
                from google.cloud import kms_v1
            except ImportError as error:  # pragma: no cover - optional production SDK
                raise RuntimeError("google-cloud-kms is required for GCP webhook secret encryption") from error
            self.client = kms_v1.KeyManagementServiceClient()
        else:
            try:
                import boto3
            except ImportError as error:  # pragma: no cover - optional production SDK
                raise RuntimeError("boto3 is required for AWS webhook secret encryption") from error
            self.client = boto3.client("kms")
        return self.client

    def encrypt(self, plaintext: str) -> str:
        raw = plaintext.encode("utf-8")
        client = self._client()
        if self.provider == "gcp":
            response = client.encrypt(request={"name": self.key_id, "plaintext": raw})
            ciphertext = response.ciphertext if hasattr(response, "ciphertext") else response["ciphertext"]
        else:
            response = client.encrypt(KeyId=self.key_id, Plaintext=raw)
            ciphertext = response["CiphertextBlob"]
        return f"kms:{self.provider}:{_b64(bytes(ciphertext))}"

    def decrypt(self, encoded: str) -> str:
        prefix = f"kms:{self.provider}:"
        if not encoded.startswith(prefix):
            raise ValueError("webhook secret ciphertext has an unexpected KMS provider")
        try:
            ciphertext = base64.urlsafe_b64decode(encoded[len(prefix):] + "=" * (-len(encoded[len(prefix):]) % 4))
        except (TypeError, ValueError) as error:
            raise ValueError("invalid KMS webhook secret ciphertext") from error
        client = self._client()
        if self.provider == "gcp":
            response = client.decrypt(request={"name": self.key_id, "ciphertext": ciphertext})
            plaintext = response.plaintext if hasattr(response, "plaintext") else response["plaintext"]
        else:
            plaintext = client.decrypt(CiphertextBlob=ciphertext, KeyId=self.key_id)["Plaintext"]
        return bytes(plaintext).decode("utf-8")


def configured_webhook_cipher(*, production_mode: bool) -> WebhookSecretCipher | KmsWebhookSecretCipher:
    """Return the only secret cipher allowed by the selected deployment mode."""

    if os.environ.get("TRACE_WEBHOOK_KMS_KEY"):
        return KmsWebhookSecretCipher()
    if production_mode:
        raise ValueError("production mode requires TRACE_WEBHOOK_KMS_KEY")
    return WebhookSecretCipher()


class WebhookSigner:
    @staticmethod
    def new_secret() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def digest(secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    @staticmethod
    def signature(secret: str, body: bytes, *, timestamp: int | None = None) -> str:
        timestamp = int(timestamp if timestamp is not None else __import__("time").time())
        signed = f"{timestamp}.".encode("ascii") + body
        return f"t={timestamp},v1={hmac.new(secret.encode('utf-8'), signed, hashlib.sha256).hexdigest()}"


class WebhookDispatcher:
    """Queue signed callbacks and deliver them through the durable ledger."""

    def __init__(self, store: Any, *, cipher: WebhookSecretCipher | None = None, timeout_seconds: float = 5.0) -> None:
        self.store = store
        self.cipher = cipher or WebhookSecretCipher()
        self.timeout_seconds = timeout_seconds

    def __call__(self, job: Mapping[str, Any]) -> None:
        enqueue = getattr(self.store, "enqueue_webhook_delivery", None)
        if callable(enqueue):
            # A job transition is already durable.  This call creates its own
            # durable delivery row; the delivery worker owns retries and DLQ.
            enqueue(dict(job))
            return
        # Compatibility for an older injected store. Production adapters must
        # implement the ledger methods above.
        self.deliver_job(job)

    def deliver_job(self, job: Mapping[str, Any]) -> None:
        webhook_id = job.get("webhook_id")
        if not webhook_id:
            return
        webhook = self.store.get_webhook(str(webhook_id))
        event_type = "job." + str(job.get("status"))
        if webhook["status"] != "active" or webhook.get("event_types") and event_type not in webhook["event_types"]:
            return
        payload = {
            "event": event_type,
            "job_id": job["job_id"],
            "workspace_id": job["workspace_id"],
            "kind": job["kind"],
            "status": job["status"],
            "result": job.get("result"),
            "error": job.get("error"),
            "request_id": job.get("request_id"),
        }
        self._send(webhook, payload, delivery_id=str(payload.get("job_id")))

    def deliver(self, delivery: Mapping[str, Any]) -> None:
        """Send one leased delivery row; callers update ledger state."""

        webhook = self.store.get_webhook(str(delivery["webhook_id"]))
        if webhook["status"] != "active":
            raise RuntimeError("webhook is inactive")
        payload = dict(delivery["payload"])
        payload["delivery_id"] = str(delivery["delivery_id"])
        self._send(webhook, payload, delivery_id=str(delivery["delivery_id"]))

    def _send(self, webhook: Mapping[str, Any], payload: Mapping[str, Any], *, delivery_id: str) -> None:
        validate_webhook_egress(str(webhook["url"]))
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        secret = self.store.webhook_secret(str(webhook["webhook_id"]), cipher=self.cipher)
        request = urllib.request.Request(
            webhook["url"], data=body, method="POST",
            headers={
                "Content-Type": "application/json", "User-Agent": "trace-v2-webhook/1",
                "X-Trace-Signature": WebhookSigner.signature(secret, body),
                "X-Trace-Delivery": delivery_id,
            },
        )
        try:
            # Refusing redirects prevents a public webhook endpoint from
            # bouncing a delivery into a link-local or private target.
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=self.timeout_seconds) as response:
                if int(response.status) >= 400:
                    raise RuntimeError(f"webhook returned HTTP {response.status}")
        except (urllib.error.URLError, urllib.error.HTTPError) as error:
            raise RuntimeError(f"webhook delivery failed: {error.reason}") from error


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class WebhookDeliveryWorker:
    """Lease, deliver, retry, and dead-letter durable webhook callbacks."""

    def __init__(self, store: Any, *, dispatcher: WebhookDispatcher | None = None) -> None:
        self.store = store
        self.dispatcher = dispatcher or WebhookDispatcher(store)

    def run_once(self, *, limit: int = 25, workspace_id: str | None = None) -> dict[str, int]:
        delivered = retried = dead_lettered = 0
        claim = getattr(self.store, "claim_webhook_deliveries", None)
        if not callable(claim):
            return {"claimed": 0, "delivered": 0, "retried": 0, "dead_lettered": 0}
        scope_factory = getattr(self.store, "authorization_scope", None)
        scope = scope_factory(workspace_id) if workspace_id and callable(scope_factory) else nullcontext()
        with scope:
            deliveries = claim(limit=limit, workspace_id=workspace_id)
            for delivery in deliveries:
                try:
                    self.dispatcher.deliver(delivery)
                except Exception as error:
                    failed = self.store.fail_webhook_delivery(str(delivery["delivery_id"]), error=str(error))
                    if failed["status"] == "dead_letter":
                        dead_lettered += 1
                    else:
                        retried += 1
                else:
                    self.store.mark_webhook_delivery_succeeded(str(delivery["delivery_id"]))
                    delivered += 1
        return {"claimed": len(deliveries), "delivered": delivered, "retried": retried, "dead_lettered": dead_lettered}


def validate_webhook_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("webhook URL must be an absolute HTTP(S) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("non-local webhook URLs must use HTTPS")


def _unsafe_ip(address: str) -> bool:
    value = ipaddress.ip_address(address)
    return bool(
        value.is_private or value.is_loopback or value.is_link_local or value.is_multicast
        or value.is_reserved or value.is_unspecified
    )


def validate_webhook_egress(url: str) -> None:
    """Resolve at delivery time and reject SSRF-prone targets.

    Resolution happens immediately before connecting so a DNS rebinding attack
    cannot bypass validation performed only at webhook registration time.
    Local development can explicitly opt in with ``TRACE_ALLOW_LOCAL_WEBHOOKS``.
    """

    validate_webhook_url(url)
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("webhook URL has no hostname")
    allow_local = os.environ.get("TRACE_ALLOW_LOCAL_WEBHOOKS", "false").lower() == "true"
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except OSError as error:
        raise ValueError("webhook hostname cannot be resolved") from error
    if not addresses:
        raise ValueError("webhook hostname cannot be resolved")
    if any(_unsafe_ip(address) for address in addresses) and not allow_local:
        raise ValueError("webhook target resolves to a private or reserved address")
