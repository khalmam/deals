"""The one place that talks to a model. Everything else uses the LLM interface."""
from typing import Protocol

import httpx

DEFAULT_MODEL = "claude-sonnet-5-5"  # check the current model names in Anthropic's docs
API_VERSION = "2023-06-01"


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    def complete(self, system, messages) -> str: ...


class ClaudeLLM:
    def __init__(self, api_key, model=DEFAULT_MODEL, transport=None, max_tokens=300, timeout=20):
        if not api_key:
            raise LLMError("no API key")
        self._model, self._max = model, max_tokens
        self._http = httpx.Client(base_url="https://api.anthropic.com", timeout=timeout,
                                  transport=transport,
                                  headers={"x-api-key": api_key, "anthropic-version": API_VERSION})

    def complete(self, system, messages):
        body = {"model": self._model, "max_tokens": self._max, "system": system,
                "messages": messages}
        try:
            r = self._http.post("/v1/messages", json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"network error: {type(exc).__name__}") from exc
        if r.status_code != 200:
            raise LLMError(f"model API returned {r.status_code}")
        blocks = r.json().get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


class NoModel:
    """Stands in when there is no API key: every call fails, so the engine's own counter
    is used. Lets the whole negotiation run offline."""

    def complete(self, system, messages):
        raise LLMError("no model configured")
