from __future__ import annotations

import json

from podsum.render import to_json, to_markdown
from podsum.types import ChunkSummary, VideoSummary, format_timestamp


def build_summary() -> VideoSummary:
    return VideoSummary(
        video_id="dQw4w9WgXcQ",
        title="A Conversation About Chunking",
        tldr="They argue that overlap matters more than chunk size.",
        chapters=(
            ChunkSummary(
                index=0,
                start=0.0,
                end=480.0,
                title="Introductions and setup",
                gist="Host introduces the guest and the topic.",
                key_points=(),
            ),
            ChunkSummary(
                index=1,
                start=480.0,
                end=3725.0,
                title="Why overlap beats window size",
                gist="The guest claims boundary loss dominates quality.",
                key_points=("Used 120 tokens of overlap", "Measured on 40 podcasts"),
            ),
        ),
        model="ollama:qwen3:8b",
        language_code="en",
        source="auto",
        duration=3725.0,
    )


def test_timestamp_formatting() -> None:
    assert format_timestamp(0) == "0:00"
    assert format_timestamp(62) == "1:02"
    assert format_timestamp(3725) == "1:02:05"


def test_markdown_has_a_jump_link_per_chapter() -> None:
    text = to_markdown(build_summary())
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s" in text
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=480s" in text
    assert "### [8:00]" in text


def test_markdown_includes_key_points_only_when_asked() -> None:
    summary = build_summary()
    assert "Measured on 40 podcasts" in to_markdown(summary, include_key_points=True)
    assert "Measured on 40 podcasts" not in to_markdown(summary, include_key_points=False)


def test_json_output_is_valid_and_complete() -> None:
    data = json.loads(to_json(build_summary()))
    assert data["video_id"] == "dQw4w9WgXcQ"
    assert len(data["chapters"]) == 2
    assert data["chapters"][1]["timestamp"] == "8:00"
    assert data["chapters"][1]["url"].endswith("&t=480s")
