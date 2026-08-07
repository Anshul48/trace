"""Deterministic LiteLLM-compatible fake used only by local integration tests."""

from __future__ import annotations

import json
from fastapi import FastAPI


app = FastAPI(title="Trace local fake model gateway")


@app.post("/v1/chat/completions")
def completion(payload: dict) -> dict:
    message = payload.get("messages", [{}])[-1].get("content", "{}")
    try:
        prompt = json.loads(message)
    except json.JSONDecodeError:
        prompt = {}
    purpose = prompt.get("purpose")
    candidates = prompt.get("candidates", [])
    if purpose == "deep_navigation":
        content = {"selected_ids": [item.get("id") for item in candidates[:1] if item.get("id")]}
    elif purpose == "synthesis":
        content = {"rendering": "Local fake model synthesis; inspect the cited Trace evidence."}
    else:
        content = {"schemas": []}
    encoded = json.dumps(content)
    return {
        "choices": [{"message": {"content": encoded}}],
        "usage": {"prompt_tokens": max(1, len(message.split())), "completion_tokens": len(encoded.split())},
    }
