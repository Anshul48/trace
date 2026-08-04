"""Signed completion webhook helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import urllib.error
import urllib.request
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
    """Best-effort signed HTTP delivery; job completion remains durable."""

    def __init__(self, store: Any, *, cipher: WebhookSecretCipher | None = None, timeout_seconds: float = 5.0) -> None:
        self.store = store
        self.cipher = cipher or WebhookSecretCipher()
        self.timeout_seconds = timeout_seconds

    def __call__(self, job: Mapping[str, Any]) -> None:
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
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        secret = self.store.webhook_secret(str(webhook_id), cipher=self.cipher)
        request = urllib.request.Request(
            webhook["url"], data=body, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "trace-v2-webhook/1", "X-Trace-Signature": WebhookSigner.signature(secret, body)},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                if int(response.status) >= 400:
                    raise RuntimeError(f"webhook returned HTTP {response.status}")
        except urllib.error.URLError as error:
            raise RuntimeError(f"webhook delivery failed: {error.reason}") from error


def validate_webhook_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("webhook URL must be an absolute HTTP(S) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("non-local webhook URLs must use HTTPS")

