"""Private OpenAI-compatible LiteLLM gateway for Trace deployments.

Run this service only on a private network.  It accepts the narrow internal
chat-completion contract emitted by ``TraceModelGateway`` and refuses caller-
provided provider URLs, credentials, or model names outside its environment
registry.  Redaction and canonical audit records remain in the Trace API
service, before this hop.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException


app = FastAPI(title="Trace private model gateway", docs_url=None, redoc_url=None)


def _registry() -> dict[str, str]:
    default_flash = (
        "deepinfra/deepseek-ai/DeepSeek-V4-Flash"
        if os.environ.get("DEEPINFRA_API_KEY")
        else "deepseek/deepseek-v4-flash"
    )
    default_pro = (
        "deepinfra/deepseek-ai/DeepSeek-V4-Pro"
        if os.environ.get("DEEPINFRA_API_KEY")
        else "deepseek/deepseek-v4-pro"
    )
    flash = os.environ.get("TRACE_LITELLM_DEEPSEEK_V4_FLASH", default_flash)
    pro = os.environ.get("TRACE_LITELLM_DEEPSEEK_V4_PRO", default_pro)
    # Accept canonical Trace names, DeepInfra paths, and operator aliases
    return {
        "deepseek/deepseek-v4-flash": flash,
        "deepseek/deepseek-v4-pro": pro,
        "deepinfra/deepseek-ai/DeepSeek-V4-Flash": flash,
        "deepinfra/deepseek-ai/DeepSeek-V4-Pro": pro,
        flash: flash,
        pro: pro,
    }


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "models": sorted(_registry())}


@app.post("/v1/chat/completions")
def chat_completion(payload: dict[str, Any]) -> Any:
    model = str(payload.get("model") or "")
    target = _registry().get(model)
    if target is None:
        raise HTTPException(status_code=403, detail="model is not registered in the private gateway")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=422, detail="messages are required")
    # Trace only accepts strict JSON from model-powered operations. The
    # private gateway keeps that transport requirement intact too.
    if payload.get("response_format") != {"type": "json_object"}:
        raise HTTPException(status_code=422, detail="Trace gateway requires JSON-object responses")
    try:
        from litellm import completion
    except ImportError as error:  # pragma: no cover - container dependency guard
        raise HTTPException(status_code=503, detail="LiteLLM is unavailable") from error
    try:
        return completion(
            model=target,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=min(2048, max(64, int(payload.get("max_tokens", 512)))),
        )
    except Exception as error:
        # Do not disclose provider hostnames, credentials, or raw upstream
        # bodies. The Trace caller classifies 429/5xx as retriable.
        status = getattr(error, "status_code", getattr(error, "status", 503))
        try:
            status = int(status)
        except (TypeError, ValueError):
            status = 503
        raise HTTPException(status_code=status if status in {429, 500, 502, 503, 504} else 503, detail="registered model is unavailable") from error
