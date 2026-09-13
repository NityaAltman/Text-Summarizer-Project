"""Choosing a backend from config.

The whole point of this file: adding a hosted provider later means writing one new
module and one new branch here. Nothing else in the codebase learns about it.
"""

from __future__ import annotations

from ..config import LLMConfig
from ..errors import ConfigError
from .base import LLMClient
from .ollama import OllamaClient


def build_client(cfg: LLMConfig) -> LLMClient:
    if cfg.provider == "ollama":
        return OllamaClient(
            model=cfg.model,
            base_url=cfg.base_url,
            temperature=cfg.temperature,
            num_ctx=cfg.num_ctx,
            timeout_s=cfg.timeout_s,
            max_retries=cfg.max_retries,
        )
    raise ConfigError(f"unknown llm.provider {cfg.provider!r} (supported: ollama)")
