"""Tests for the map and reduce steps, with a fake model.

This file is the payoff for `LLMClient` being a `Protocol`. `FakeClient` inherits from
nothing and imports nothing from `podsum.llm`, yet it satisfies the interface, so the
whole summarization path is testable with no Ollama running and no network. If the
pipeline had called `httpx` directly, none of this would be reachable.
"""

from __future__ import annotations

import json
from typing import Any

from podsum.cache import Store
from podsum.summarize import reduce_summaries, summarize_chunks
from podsum.types import Chunk, ChunkSummary


class FakeClient:
    """Returns canned JSON and records how many calls it received."""

    def __init__(self, response: str | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.response = response

    @property
    def name(self) -> str:
        return "fake:test"

    def health(self) -> str | None:
        return None

    def complete(self, system: str, user: str, *, schema: dict[str, Any] | None = None) -> str:
        self.calls.append((system, user))
        if self.response is not None:
            return self.response
        return json.dumps(
            {
                "title": f"Chapter {len(self.calls)}",
                "gist": "Something was said.",
                "key_points": ["a point"],
            }
        )


def make_chunks(count: int = 3) -> list[Chunk]:
    return [
        Chunk(index=i, start=i * 60.0, end=(i + 1) * 60.0, text=f"chunk {i} text", est_tokens=100)
        for i in range(count)
    ]


def test_map_produces_one_chapter_per_chunk() -> None:
    client = FakeClient()
    chapters = summarize_chunks(make_chunks(3), client, concurrency=1)
    assert len(chapters) == 3
    assert len(client.calls) == 3


def test_map_preserves_chunk_timings() -> None:
    chapters = summarize_chunks(make_chunks(3), FakeClient(), concurrency=1)
    assert [(c.start, c.end) for c in chapters] == [(0.0, 60.0), (60.0, 120.0), (120.0, 180.0)]


def test_map_keeps_chronological_order_when_parallel() -> None:
    chapters = summarize_chunks(make_chunks(8), FakeClient(), concurrency=4)
    assert [c.index for c in chapters] == list(range(8))


def test_unparsable_output_degrades_instead_of_crashing() -> None:
    chapters = summarize_chunks(make_chunks(1), FakeClient(response="I refuse."), concurrency=1)
    assert len(chapters) == 1
    assert "did not return a usable summary" in chapters[0].gist


def test_cache_prevents_a_second_model_call(tmp_path: object) -> None:
    store = Store(f"{tmp_path}/cache.sqlite3")
    chunks = make_chunks(2)

    first = FakeClient()
    summarize_chunks(chunks, first, cache=store, video_id="vid", concurrency=1)
    assert len(first.calls) == 2

    second = FakeClient()
    cached = summarize_chunks(chunks, second, cache=store, video_id="vid", concurrency=1)
    assert second.calls == []
    assert cached[0].title == "Chapter 1"
    store.close()


def test_reduce_returns_a_title_and_tldr() -> None:
    chapters = [
        ChunkSummary(index=0, start=0.0, end=60.0, title="Intro", gist="They say hello."),
        ChunkSummary(index=1, start=60.0, end=120.0, title="Meat", gist="They disagree."),
    ]
    client = FakeClient(json.dumps({"title": "The Whole Video", "tldr": "A disagreement."}))
    title, tldr = reduce_summaries(chapters, client)
    assert (title, tldr) == ("The Whole Video", "A disagreement.")


def test_reduce_never_sees_the_transcript() -> None:
    chapters = [ChunkSummary(index=0, start=0.0, end=60.0, title="T", gist="G")]
    client = FakeClient(json.dumps({"title": "x", "tldr": "y"}))
    reduce_summaries(chapters, client)
    _, user = client.calls[0]
    assert "G" in user
    assert "chunk 0 text" not in user


def test_reduce_falls_back_when_the_model_misbehaves() -> None:
    chapters = [ChunkSummary(index=0, start=0.0, end=60.0, title="Only", gist="A gist.")]
    title, tldr = reduce_summaries(chapters, FakeClient(response="nope"))
    assert title == "Only"
    assert "A gist." in tldr


def test_empty_input_is_handled() -> None:
    assert summarize_chunks([], FakeClient()) == []
    title, _ = reduce_summaries([], FakeClient())
    assert title == "Empty video"
