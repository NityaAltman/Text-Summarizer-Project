"""Argument parsing only. Nothing here reaches the network or a model."""

from __future__ import annotations

from pathlib import Path

import pytest

from podsum.cli import _merge_globals, build_parser


def parse(argv: list[str]) -> object:
    return _merge_globals(build_parser().parse_args(argv))


def test_globals_work_before_the_subcommand() -> None:
    args = parse(["--set", "llm.model=x", "-v", "summarize", "URL"])
    assert args.overrides == ["llm.model=x"]  # type: ignore[attr-defined]
    assert args.verbose is True  # type: ignore[attr-defined]


def test_globals_work_after_the_subcommand() -> None:
    # The form the README documents, and the one that felt natural but did not
    # originally parse.
    args = parse(["summarize", "URL", "--set", "llm.model=x", "-v"])
    assert args.overrides == ["llm.model=x"]  # type: ignore[attr-defined]
    assert args.verbose is True  # type: ignore[attr-defined]


def test_repeated_overrides_accumulate() -> None:
    args = parse(["summarize", "URL", "--set", "a.b=1", "--set", "c.d=2"])
    assert args.overrides == ["a.b=1", "c.d=2"]  # type: ignore[attr-defined]


def test_overrides_from_both_positions_combine() -> None:
    args = parse(["--set", "a.b=1", "summarize", "URL", "--set", "c.d=2"])
    assert args.overrides == ["a.b=1", "c.d=2"]  # type: ignore[attr-defined]


def test_config_default_survives_a_subcommand() -> None:
    args = parse(["doctor"])
    assert args.config == Path("configs/default.yaml")  # type: ignore[attr-defined]


def test_config_can_be_set_after_the_subcommand() -> None:
    args = parse(["doctor", "-c", "other.yaml"])
    assert args.config == Path("other.yaml")  # type: ignore[attr-defined]


def test_summarize_flags() -> None:
    args = parse(["summarize", "URL", "-o", "out.md", "--json", "--no-cache"])
    assert args.output == Path("out.md")  # type: ignore[attr-defined]
    assert args.json is True  # type: ignore[attr-defined]
    assert args.no_cache is True  # type: ignore[attr-defined]


def test_a_subcommand_is_required() -> None:
    with pytest.raises(SystemExit):
        parse([])


def test_cache_action_is_constrained() -> None:
    assert parse(["cache", "stats"]).action == "stats"  # type: ignore[attr-defined]
    with pytest.raises(SystemExit):
        parse(["cache", "nonsense"])
