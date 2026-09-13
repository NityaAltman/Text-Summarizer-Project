"""Getting structured data out of a model that only emits text.

This module exists because of the single most common disappointment in LLM
engineering: you ask for JSON, and you get JSON *plus* an apology, or wrapped in a
code fence, or preceded by a paragraph of reasoning. Constrained decoding
(`format=<schema>`) fixes most of it, but "most" is not "all", and small local models
are the worst offenders.

So the rule is: never call `json.loads` directly on model output.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..errors import LLMBadOutput

#: Reasoning models wrap their scratchpad in these before answering.
_THINK_RE = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)
#: ```json ... ``` fences.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_object(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from `raw`.

    Raises:
        LLMBadOutput: if no parsable object is present.
    """
    text = _FENCE_RE.sub("", _THINK_RE.sub("", raw)).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the outermost {...} span, which survives leading commentary.
        parsed = _first_object(text)

    if not isinstance(parsed, dict):
        raise LLMBadOutput(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def _first_object(text: str) -> Any:
    start = text.find("{")
    if start == -1:
        raise LLMBadOutput(f"no JSON object in model output: {text[:200]!r}")

    # Walk the string tracking brace depth, ignoring braces inside string literals.
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : index + 1])
                except json.JSONDecodeError as exc:
                    raise LLMBadOutput(f"malformed JSON in model output: {exc}") from exc

    raise LLMBadOutput(f"unterminated JSON object in model output: {text[:200]!r}")


def require_str(data: dict[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    return value.strip() if isinstance(value, str) else default


def require_str_list(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
