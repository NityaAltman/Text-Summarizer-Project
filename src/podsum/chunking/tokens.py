"""Token counting.

This module is intentionally the weakest part of the pipeline, and it is the seam
where the learning track plugs in.

A model does not read characters or words, it reads *tokens*: subword pieces produced
by a tokenizer. To know whether a chunk fits in a context window you have to count
tokens, not words. Right now we approximate, using the rule of thumb that English
averages about four characters per token.

The approximation is fine for chunking (we leave headroom anyway) but it is a guess,
and it will be visibly wrong on non-English text, code, and unusual names. When you
write a real BPE tokenizer by hand in `research/tinygpt`, implement the `Tokenizer`
protocol below and swap it in here. At that point your chunk sizes stop being
estimates, and you will understand exactly why the number changed.
"""

from __future__ import annotations

from typing import Protocol

#: Empirical average for English prose. Higher means fewer tokens per character.
CHARS_PER_TOKEN = 4.0


class Tokenizer(Protocol):
    """The minimum a tokenizer has to do for this project to use it."""

    def encode(self, text: str) -> list[int]: ...

    def decode(self, ids: list[int]) -> str: ...


def estimate_tokens(text: str) -> int:
    """Approximate the token count of `text`.

    Deliberately cheap: this runs once per caption cue, thousands of times per video.
    """
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def count_tokens(text: str, tokenizer: Tokenizer | None = None) -> int:
    """Exact count when a real tokenizer is available, estimate otherwise."""
    if tokenizer is None:
        return estimate_tokens(text)
    return len(tokenizer.encode(text))
