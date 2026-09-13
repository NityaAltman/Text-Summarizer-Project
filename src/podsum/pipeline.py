"""Orchestration.

This is the only file that knows the order of operations, and it contains no logic of
its own beyond wiring. If you want to understand the project, read this file first:
every stage below is a black box with a typed input and a typed output.

    url -> video_id -> Transcript -> [Chunk] -> [ChunkSummary] -> VideoSummary -> markdown
"""

from __future__ import annotations

import time

from .cache import Store
from .chunking.windows import build_chunks_capped
from .config import Config
from .errors import LLMUnavailable
from .ingest import extract_video_id, fetch_transcript
from .llm import build_client
from .log import get
from .summarize import reduce_summaries, summarize_chunks
from .types import Transcript, VideoSummary

log = get(__name__)


def summarize_video(
    url_or_id: str,
    cfg: Config,
    *,
    use_cache: bool = True,
    check_health: bool = True,
) -> VideoSummary:
    """Run the full pipeline for one video."""
    started = time.perf_counter()
    video_id = extract_video_id(url_or_id)
    log.info("video %s", video_id)

    store = Store(cfg.cache.path) if (use_cache and cfg.cache.enabled) else None
    client = build_client(cfg.llm)

    try:
        # Fail before doing any work, not forty chunks in.
        if check_health:
            problem = client.health()
            if problem:
                raise LLMUnavailable(problem)

        transcript = _get_transcript(video_id, cfg, store)

        chunks = build_chunks_capped(
            transcript,
            target_tokens=cfg.chunking.target_tokens,
            overlap_tokens=cfg.chunking.overlap_tokens,
            hard_max_tokens=cfg.chunking.hard_max_tokens,
            max_chunks=cfg.output.max_chapters,
        )

        chapters = summarize_chunks(
            chunks,
            client,
            cache=store,
            video_id=video_id,
            concurrency=cfg.llm.concurrency,
        )

        title, tldr = reduce_summaries(chapters, client)

        log.info("done in %.1fs", time.perf_counter() - started)
        return VideoSummary(
            video_id=video_id,
            title=title,
            tldr=tldr,
            chapters=tuple(chapters),
            model=client.name,
            language_code=transcript.language_code,
            source=transcript.source,
            duration=transcript.duration,
        )
    finally:
        if store is not None:
            store.close()
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _get_transcript(video_id: str, cfg: Config, store: Store | None) -> Transcript:
    """Read-through cache around the ingest layer."""
    if store is not None:
        cached = store.get_transcript(video_id)
        if cached is not None:
            return cached

    transcript = fetch_transcript(
        video_id,
        languages=cfg.transcript.languages,
        prefer_manual=cfg.transcript.prefer_manual,
    )
    if store is not None:
        store.put_transcript(transcript)
    return transcript
