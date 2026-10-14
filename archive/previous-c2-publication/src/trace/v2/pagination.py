"""Signed opaque continuation tokens for collection endpoints."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any


class PaginationError(ValueError):
    pass


@dataclass(frozen=True)
class PageCursor:
    scope: str
    position: int
    limit: int
    expires_at: int


def _key() -> bytes:
    return hashlib.sha256((os.environ.get("TRACE_PAGE_TOKEN_SECRET") or "trace-development-page-token").encode("utf-8")).digest()


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(output[:length])


def encode_page_token(*, scope: str, position: int, limit: int, ttl_seconds: int = 900) -> str:
    if position < 0 or limit < 1 or limit > 200:
        raise PaginationError("invalid page cursor")
    key = _key()
    nonce = os.urandom(16)
    payload = json.dumps({"v": 1, "s": scope, "p": position, "l": limit, "e": int(time.time()) + max(1, ttl_seconds)}, separators=(",", ":")).encode("utf-8")
    ciphertext = bytes(left ^ right for left, right in zip(payload, _stream(key, nonce, len(payload)), strict=True))
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + tag + ciphertext).rstrip(b"=").decode("ascii")


def decode_page_token(token: str, *, scope: str, max_limit: int = 200) -> PageCursor:
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        nonce, tag, ciphertext = raw[:16], raw[16:48], raw[48:]
        key = _key()
        expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, tag):
            raise PaginationError("invalid page cursor signature")
        payload = json.loads(bytes(left ^ right for left, right in zip(ciphertext, _stream(key, nonce, len(ciphertext)), strict=True)))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise PaginationError("invalid page cursor") from error
    if payload.get("v") != 1 or payload.get("s") != scope:
        raise PaginationError("page cursor does not match this collection")
    if int(payload.get("e", 0)) <= int(time.time()):
        raise PaginationError("page cursor has expired")
    position, limit = int(payload.get("p", -1)), int(payload.get("l", 0))
    if position < 0 or limit < 1 or limit > max_limit:
        raise PaginationError("invalid page cursor bounds")
    return PageCursor(scope=scope, position=position, limit=limit, expires_at=int(payload["e"]))

