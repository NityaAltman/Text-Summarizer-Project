"""Every case here is real output a small local model has produced.

Which is the point: constrained decoding usually works, and this module exists for
when it does not.
"""

from __future__ import annotations

import pytest

from podsum.errors import LLMBadOutput
from podsum.llm.jsonio import parse_object, require_str, require_str_list


def test_clean_json() -> None:
    assert parse_object('{"title": "Hello", "gist": "World"}')["title"] == "Hello"


def test_code_fenced_json() -> None:
    raw = '```json\n{"title": "Hello", "gist": "World"}\n```'
    assert parse_object(raw)["gist"] == "World"


def test_thinking_block_is_stripped() -> None:
    raw = '<think>The user wants a summary. Let me consider.</think>\n{"title": "Hi"}'
    assert parse_object(raw) == {"title": "Hi"}


def test_leading_commentary_is_skipped() -> None:
    raw = 'Sure! Here is the JSON you asked for:\n{"title": "Hi", "gist": "there"}'
    assert parse_object(raw)["title"] == "Hi"


def test_trailing_commentary_is_skipped() -> None:
    raw = '{"title": "Hi"}\n\nLet me know if you would like more detail!'
    assert parse_object(raw) == {"title": "Hi"}


def test_braces_inside_strings_do_not_confuse_the_scanner() -> None:
    raw = 'Here:\n{"gist": "he said {this} and \\"that\\"", "title": "x"}'
    assert parse_object(raw)["gist"] == 'he said {this} and "that"'


def test_nested_objects_survive() -> None:
    raw = 'ok {"a": {"b": {"c": 1}}, "title": "x"}'
    assert parse_object(raw)["a"] == {"b": {"c": 1}}


@pytest.mark.parametrize("raw", ["", "I cannot help with that.", "{unterminated", "[1, 2, 3]"])
def test_unusable_output_raises(raw: str) -> None:
    with pytest.raises(LLMBadOutput):
        parse_object(raw)


def test_require_str_tolerates_wrong_types() -> None:
    assert require_str({"title": 42}, "title") == ""
    assert require_str({"title": "  spaced  "}, "title") == "spaced"
    assert require_str({}, "title", default="fallback") == "fallback"


def test_require_str_list_filters_junk() -> None:
    data = {"key_points": ["  real  ", "", 7, None, "also real"]}
    assert require_str_list(data, "key_points") == ("real", "also real")
    assert require_str_list({"key_points": "not a list"}, "key_points") == ()
    assert require_str_list({}, "key_points") == ()
