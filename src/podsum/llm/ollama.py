"""Ollama backend.

Talks to the local Ollama daemon over plain HTTP rather than through its Python SDK,
because there is very little to it and seeing the request body teaches you what a
"model call" actually is: a POST with a list of messages and some sampling options.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from ..errors import LLMUnavailable
from ..log import get

log = get(__name__)


class OllamaClient:
    """A thin, retrying client for one model on a local Ollama server."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        temperature: float = 0.2,
        num_ctx: int = 8192,
        timeout_s: int = 300,
        max_retries: int = 2,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.max_retries = max_retries
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout_s)

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- diagnostics ---------------------------------------------------------

    def list_models(self) -> list[str]:
        """Model tags currently pulled on this machine."""
        try:
            response = self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"cannot reach Ollama at {self.base_url}: {exc}") from exc
        return [m["name"] for m in response.json().get("models", [])]

    def health(self) -> str | None:
        """None if we can run, otherwise the reason we cannot."""
        try:
            available = self.list_models()
        except LLMUnavailable as exc:
            return f"{exc}. Is the Ollama app running?"

        # Ollama reports "qwen3:8b" but accepts "qwen3" as shorthand for "qwen3:latest".
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        if wanted not in available:
            return (
                f"model {self.model!r} is not pulled. Run: ollama pull {self.model}\n"
                f"Currently available: {', '.join(available) or 'none'}"
            )
        return None

    # -- inference -----------------------------------------------------------

    def complete(
        self,
        system: str,
        user: str,
        *,
        schema: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
            # Reasoning models otherwise spend hundreds of tokens thinking out loud
            # before answering. Ignored by models that do not support it.
            "think": False,
        }
        if schema is not None:
            payload["format"] = schema

        data = self._post_with_retries("/api/chat", payload, schema_present=schema is not None)
        return str(data.get("message", {}).get("content", ""))

    def _post_with_retries(
        self,
        path: str,
        payload: dict[str, Any],
        schema_present: bool,
    ) -> dict[str, Any]:
        last: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.post(path, json=payload)
                if response.status_code == 400 and schema_present:
                    # Older Ollama builds accept format="json" but not a full schema.
                    log.debug("server rejected JSON schema, retrying with format=json")
                    payload = {**payload, "format": "json"}
                    schema_present = False
                    response = self._client.post(path, json=payload)
                response.raise_for_status()
                return dict(response.json())
            except httpx.HTTPError as exc:
                last = exc
                if attempt < self.max_retries:
                    backoff = 2**attempt
                    log.warning("Ollama call failed (%s), retrying in %ds", exc, backoff)
                    time.sleep(backoff)

        raise LLMUnavailable(f"Ollama call failed after {self.max_retries + 1} attempts: {last}")
