from __future__ import annotations

from pathlib import Path

import pytest

from podsum.config import Config
from podsum.errors import ConfigError

REPO_CONFIG = Path("configs/default.yaml")


def test_the_shipped_config_loads() -> None:
    cfg = Config.load(REPO_CONFIG)
    assert cfg.llm.provider == "ollama"
    assert cfg.chunking.overlap_tokens < cfg.chunking.target_tokens


def test_missing_file_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        Config.load(tmp_path / "nope.yaml")


def test_unknown_key_is_rejected_at_load_time(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("chunking:\n  target_tokns: 900\n")
    with pytest.raises(ConfigError, match="unexpected key"):
        Config.load(path)


def test_contradictory_chunking_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("chunking:\n  target_tokens: 100\n  overlap_tokens: 200\n")
    with pytest.raises(ConfigError, match="overlap_tokens"):
        Config.load(path)


@pytest.mark.parametrize(
    ("override", "section", "key", "expected"),
    [
        ("llm.model=gemma3:12b", "llm", "model", "gemma3:12b"),
        ("llm.temperature=0.7", "llm", "temperature", 0.7),
        ("llm.num_ctx=16384", "llm", "num_ctx", 16384),
        ("cache.enabled=false", "cache", "enabled", False),
        ("transcript.languages=fr,en", "transcript", "languages", ["fr", "en"]),
    ],
)
def test_overrides_are_coerced_to_the_right_type(
    override: str, section: str, key: str, expected: object
) -> None:
    cfg = Config.load(REPO_CONFIG, [override])
    assert getattr(getattr(cfg, section), key) == expected


@pytest.mark.parametrize(
    "override",
    ["nosuchsection.key=1", "llm.nosuchkey=1", "llm.model", "model=x", "cache.enabled=maybe"],
)
def test_bad_overrides_are_rejected(override: str) -> None:
    with pytest.raises(ConfigError):
        Config.load(REPO_CONFIG, [override])
