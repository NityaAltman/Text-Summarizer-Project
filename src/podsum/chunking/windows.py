"""Turning a transcript into overlapping windows.

The rules this has to satisfy, in priority order:

1. Never split inside a caption cue. Cues are already sentence-ish, and cutting
   mid-cue produces chunks that start halfway through a thought.
2. Carry `start` and `end` times on every chunk. This is what makes jump links
   possible at the end, and it is why chunking consumes `Snippet` objects rather
   than one flat string.
3. Overlap neighbouring chunks slightly, so an argument spanning a boundary is
   intact in at least one of them. Without overlap, the single most common failure
   is a chapter summary that confidently describes half an idea.
4. Never exceed `hard_max_tokens`, whatever the target, because blowing past the
   context window makes the model silently ignore the middle of its input.
"""

from __future__ import annotations

from ..log import get
from ..types import Chunk, Transcript
from .tokens import estimate_tokens

log = get(__name__)


def build_chunks(
    transcript: Transcript,
    target_tokens: int,
    overlap_tokens: int,
    hard_max_tokens: int,
) -> list[Chunk]:
    """Split `transcript` into overlapping, time-stamped chunks."""
    snippets = transcript.snippets
    if not snippets:
        return []

    costs = [estimate_tokens(s.text) for s in snippets]
    chunks: list[Chunk] = []
    start_i = 0
    total_snippets = len(snippets)

    while start_i < total_snippets:
        end_i, size = _grow(costs, start_i, target_tokens, hard_max_tokens)
        window = snippets[start_i:end_i]

        chunks.append(
            Chunk(
                index=len(chunks),
                start=window[0].start,
                end=window[-1].end,
                text=" ".join(s.text for s in window),
                est_tokens=size,
            )
        )

        if end_i >= total_snippets:
            break
        start_i = _rewind_for_overlap(costs, start_i, end_i, overlap_tokens)

    log.info(
        "chunking: %d chunks, ~%d tokens each, %.1f min per chunk on average",
        len(chunks),
        sum(c.est_tokens for c in chunks) // max(1, len(chunks)),
        (transcript.duration / 60) / max(1, len(chunks)),
    )
    return chunks


def build_chunks_capped(
    transcript: Transcript,
    target_tokens: int,
    overlap_tokens: int,
    hard_max_tokens: int,
    max_chunks: int,
) -> list[Chunk]:
    """Like `build_chunks`, but grow the window until the count fits `max_chunks`.

    A four-hour stream at the default target would produce eighty chapters, which is
    not a summary any more. Rather than truncate and lose the end of the video, we
    widen each window so the whole thing still fits in a readable number of sections.
    """
    target = target_tokens
    while True:
        chunks = build_chunks(transcript, target, overlap_tokens, hard_max_tokens)
        if len(chunks) <= max_chunks or target >= hard_max_tokens:
            return chunks
        # Scale to what we would have needed, plus a margin, and stay under the cap.
        needed = int(target * (len(chunks) / max_chunks) * 1.1)
        target = min(needed, hard_max_tokens)
        log.debug("too many chunks (%d), retrying with target_tokens=%d", len(chunks), target)


def _grow(costs: list[int], start_i: int, target: int, hard_max: int) -> tuple[int, int]:
    """Extend from `start_i` until we hit the target, returning (exclusive end, size)."""
    total = 0
    end_i = start_i
    while end_i < len(costs) and total + costs[end_i] <= hard_max:
        total += costs[end_i]
        end_i += 1
        if total >= target:
            break

    # A single cue larger than hard_max would otherwise stall the loop forever.
    if end_i == start_i:
        return start_i + 1, costs[start_i]
    return end_i, total


def _rewind_for_overlap(costs: list[int], start_i: int, end_i: int, overlap: int) -> int:
    """Where the next chunk should begin, backing up `overlap` tokens from `end_i`."""
    back = end_i - 1
    accumulated = 0
    while back > start_i and accumulated + costs[back] <= overlap:
        accumulated += costs[back]
        back -= 1
    # max(..., start_i + 1) guarantees forward progress even when one cue is huge.
    return max(back + 1, start_i + 1)
