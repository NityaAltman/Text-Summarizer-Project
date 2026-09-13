from __future__ import annotations

from podsum.chunking.windows import build_chunks, build_chunks_capped
from podsum.types import Snippet, Transcript

from .conftest import TranscriptFactory


def test_covers_the_whole_transcript(transcript: Transcript) -> None:
    chunks = build_chunks(transcript, target_tokens=200, overlap_tokens=20, hard_max_tokens=400)
    assert chunks
    assert chunks[0].start == transcript.snippets[0].start
    assert chunks[-1].end == transcript.snippets[-1].end


def test_chunks_are_ordered_and_always_advance(transcript: Transcript) -> None:
    chunks = build_chunks(transcript, target_tokens=200, overlap_tokens=20, hard_max_tokens=400)
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert earlier.index < later.index
        # Overlap means the next chunk starts before the previous one ended...
        assert later.start <= earlier.end
        # ...but it must still move forward, or the loop would never terminate.
        assert later.start > earlier.start


def test_respects_the_hard_maximum(transcript: Transcript) -> None:
    chunks = build_chunks(transcript, target_tokens=300, overlap_tokens=30, hard_max_tokens=350)
    assert all(chunk.est_tokens <= 350 for chunk in chunks)


def test_overlap_costs_extra_chunks(transcript: Transcript) -> None:
    with_overlap = build_chunks(transcript, 200, overlap_tokens=60, hard_max_tokens=400)
    without_overlap = build_chunks(transcript, 200, overlap_tokens=1, hard_max_tokens=400)
    # Repeating text at every boundary means more chunks to cover the same video.
    assert len(with_overlap) >= len(without_overlap)


def test_zero_overlap_still_terminates(transcript: Transcript) -> None:
    chunks = build_chunks(transcript, target_tokens=100, overlap_tokens=0, hard_max_tokens=200)
    assert 0 < len(chunks) <= len(transcript.snippets)


def test_empty_transcript_yields_no_chunks() -> None:
    empty = Transcript(video_id="dQw4w9WgXcQ", language_code="en", snippets=())
    assert build_chunks(empty, 200, 20, 400) == []


def test_a_single_oversized_cue_does_not_stall() -> None:
    huge = Transcript(
        video_id="dQw4w9WgXcQ",
        language_code="en",
        snippets=(
            Snippet(text="x " * 5000, start=0.0, duration=10.0),
            Snippet(text="afterwards", start=10.0, duration=2.0),
        ),
    )
    chunks = build_chunks(huge, target_tokens=100, overlap_tokens=10, hard_max_tokens=200)
    assert len(chunks) == 2


def test_capped_builder_respects_the_chapter_limit(make_transcript: TranscriptFactory) -> None:
    long_video = make_transcript(cue_count=2000)
    chunks = build_chunks_capped(
        long_video,
        target_tokens=200,
        overlap_tokens=20,
        hard_max_tokens=4000,
        max_chunks=12,
    )
    assert len(chunks) <= 12
    # Still ends where the video ends: widening windows must not truncate the tail.
    assert chunks[-1].end == long_video.snippets[-1].end
