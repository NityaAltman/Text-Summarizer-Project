"""The map step: one chunk in, one chapter out.

Chunks are independent, which is what makes this step parallelisable and cacheable.
It is also the step that dominates runtime, so both of those matter.

A note on concurrency: threads, not asyncio. The work is a blocking HTTP call to a
local server, so we are I/O bound and the GIL is released while we wait. Threads give
us the same throughput for a fraction of the complexity. And the ceiling is low on
purpose — beyond two or three concurrent requests a single Ollama instance queues
them anyway, and on a machine with 18GB of shared memory you start competing with
yourself.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .. import prompts
from ..cache import Store
from ..errors import LLMBadOutput, PodsumError
from ..llm import LLMClient
from ..llm.jsonio import parse_object, require_str, require_str_list
from ..log import get
from ..types import Chunk, ChunkSummary

log = get(__name__)

PROMPT_NAME = "map_chunk"

#: Constrained decoding: the server is told to emit only JSON in this shape.
MAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "gist": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "gist"],
}


def summarize_chunks(
    chunks: list[Chunk],
    client: LLMClient,
    *,
    cache: Store | None = None,
    video_id: str = "",
    concurrency: int = 2,
) -> list[ChunkSummary]:
    """Summarize every chunk, in order, reusing cached results where possible."""
    if not chunks:
        return []

    system = prompts.load(PROMPT_NAME)
    prompt_version = prompts.version(PROMPT_NAME)

    def work(chunk: Chunk) -> ChunkSummary:
        key = Store.chunk_key(chunk.text, client.name, prompt_version)
        if cache is not None:
            hit = cache.get_chunk_summary(key)
            if hit is not None:
                log.debug("chunk %d/%d cached", chunk.index + 1, len(chunks))
                return hit

        summary = _summarize_one(chunk, client, system)
        if cache is not None:
            cache.put_chunk_summary(key, video_id, summary)
        log.info("chunk %d/%d done: %s", chunk.index + 1, len(chunks), summary.title)
        return summary

    if concurrency <= 1:
        return [work(chunk) for chunk in chunks]

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        # `map` preserves input order, so chapters stay chronological regardless of
        # which chunk happens to finish first.
        return list(pool.map(work, chunks))


def _summarize_one(chunk: Chunk, client: LLMClient, system: str) -> ChunkSummary:
    user = (
        f"Segment {chunk.index + 1}, covering {chunk.label} of the video.\n\n"
        f"Transcript:\n{chunk.text}"
    )

    try:
        raw = client.complete(system, user, schema=MAP_SCHEMA)
        data = parse_object(raw)
    except LLMBadOutput as exc:
        # One repair attempt. If a small model produces garbage twice, degrade to a
        # placeholder chapter rather than losing the whole run over one bad segment.
        log.warning("chunk %d returned unparsable output (%s), retrying once", chunk.index, exc)
        try:
            data = parse_object(client.complete(system, user, schema=MAP_SCHEMA))
        except PodsumError:
            log.error("chunk %d failed twice, emitting placeholder", chunk.index)
            return ChunkSummary(
                index=chunk.index,
                start=chunk.start,
                end=chunk.end,
                title=f"Segment at {chunk.label}",
                gist="(the model did not return a usable summary for this segment)",
            )

    return ChunkSummary(
        index=chunk.index,
        start=chunk.start,
        end=chunk.end,
        title=require_str(data, "title") or f"Segment at {chunk.label}",
        gist=require_str(data, "gist"),
        key_points=require_str_list(data, "key_points"),
    )
