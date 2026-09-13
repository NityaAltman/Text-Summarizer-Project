from __future__ import annotations

from typing import Protocol

import pytest

from podsum.types import Snippet, Transcript


class TranscriptFactory(Protocol):
    def __call__(
        self, cue_count: int = ..., words_per_cue: int = ..., seconds: float = ...
    ) -> Transcript: ...


@pytest.fixture
def make_transcript() -> TranscriptFactory:
    """Build a synthetic transcript with predictable timings and token costs."""

    def _make(cue_count: int = 100, words_per_cue: int = 8, seconds: float = 4.0) -> Transcript:
        snippets = tuple(
            Snippet(
                text=" ".join(f"word{i}-{w}" for w in range(words_per_cue)),
                start=i * seconds,
                duration=seconds,
            )
            for i in range(cue_count)
        )
        return Transcript(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            snippets=snippets,
            source="auto",
        )

    return _make


@pytest.fixture
def transcript(make_transcript: TranscriptFactory) -> Transcript:
    return make_transcript()
