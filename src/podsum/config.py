"""Typed configuration loaded from YAML.

Two rules worth internalising, because they are what separate a script you can
experiment with from one you keep editing by hand:

1. No module reads a magic number out of thin air. Everything arrives as config.
2. Config is a typed object, not a dict. `cfg.chunking.target_tokens` fails loudly
   at load time on a typo; `cfg["chunking"]["target_tokns"]` fails at 3am.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")


@dataclass(slots=True)
class TranscriptConfig:
    # Every field needs a default so that omitting a whole section from the YAML is
    # valid, and a genuinely bad key still produces a message about that key.
    languages: list[str] = field(default_factory=lambda: ["en"])
    prefer_manual: bool = True


@dataclass(slots=True)
class ChunkingConfig:
    target_tokens: int = 1200
    overlap_tokens: int = 120
    hard_max_tokens: int = 2000

    def __post_init__(self) -> None:
        if self.overlap_tokens >= self.target_tokens:
            raise ConfigError("chunking.overlap_tokens must be smaller than target_tokens")
        if self.hard_max_tokens < self.target_tokens:
            raise ConfigError("chunking.hard_max_tokens must be >= target_tokens")


@dataclass(slots=True)
class LLMConfig:
    provider: str = "ollama"
    model: str = "qwen3:8b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.2
    num_ctx: int = 8192
    timeout_s: int = 300
    max_retries: int = 2
    concurrency: int = 2


@dataclass(slots=True)
class CacheConfig:
    enabled: bool = True
    path: str = "data/cache.sqlite3"


@dataclass(slots=True)
class OutputConfig:
    include_key_points: bool = True
    max_chapters: int = 24


@dataclass(slots=True)
class Config:
    transcript: TranscriptConfig
    chunking: ChunkingConfig
    llm: LLMConfig
    cache: CacheConfig
    output: OutputConfig

    @classmethod
    def load(cls, path: Path | None = None, overrides: list[str] | None = None) -> Config:
        """Read YAML, then apply `dotted.key=value` overrides from the CLI."""
        path = path or DEFAULT_CONFIG_PATH
        if not path.exists():
            raise ConfigError(f"config file not found: {path}")

        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict):
            raise ConfigError(f"{path} must contain a YAML mapping at the top level")

        try:
            cfg = cls(
                transcript=TranscriptConfig(**raw.get("transcript", {})),
                chunking=ChunkingConfig(**raw.get("chunking", {})),
                llm=LLMConfig(**raw.get("llm", {})),
                cache=CacheConfig(**raw.get("cache", {})),
                output=OutputConfig(**raw.get("output", {})),
            )
        except TypeError as exc:
            raise ConfigError(f"unexpected key in {path}: {exc}") from exc

        for override in overrides or []:
            cfg.apply_override(override)
        return cfg

    def apply_override(self, expression: str) -> None:
        """Apply one `section.key=value`, coercing the value to the field's type."""
        if "=" not in expression:
            raise ConfigError(f"override must look like section.key=value, got {expression!r}")
        dotted, value = expression.split("=", 1)
        parts = dotted.strip().split(".")
        if len(parts) != 2:
            raise ConfigError(f"override key must be section.key, got {dotted!r}")

        section_name, key = parts
        section = getattr(self, section_name, None)
        if section is None or not is_dataclass(section):
            raise ConfigError(f"unknown config section {section_name!r}")

        target = {f.name: f for f in fields(section)}.get(key)
        if target is None:
            raise ConfigError(f"unknown config key {section_name}.{key}")

        setattr(section, key, _coerce(value.strip(), target.type))


def _coerce(value: str, annotation: Any) -> Any:
    """Turn a CLI string into the type the dataclass field declares."""
    name = annotation if isinstance(annotation, str) else getattr(annotation, "__name__", "str")
    if name == "bool":
        lowered = value.lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise ConfigError(f"cannot read {value!r} as a boolean")
    if name == "int":
        return int(value)
    if name == "float":
        return float(value)
    if name.startswith("list"):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value
