"""A SQLite cache for transcripts and per-chunk summaries.

SQLite because it is one file, needs no server, ships with Python, and handles
concurrent readers fine. There is no reason to reach for anything heavier here.

Two things are worth understanding about the design:

* **Transcripts** are keyed by video ID alone. They do not change, so once fetched
  you never hit YouTube for that video again.
* **Chunk summaries** are keyed by a hash of the chunk text *plus the model name plus
  the prompt version*. That composite key is the important part: edit a prompt or
  switch models and the old entries become unreachable automatically, so you can
  never be fooled by a stale summary. Cache invalidation is usually the hard part of
  caching; here we sidestep it by making the key describe everything that mattered.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ..log import get
from ..types import ChunkSummary, Snippet, Transcript

log = get(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    video_id   TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunk_summaries (
    key        TEXT PRIMARY KEY,
    video_id   TEXT NOT NULL,
    payload    TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunk_summaries_video ON chunk_summaries(video_id);
"""


class Store:
    """Read-through cache. All methods are safe to call from worker threads."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False plus our own lock: the map step runs in a thread pool.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- transcripts ---------------------------------------------------------

    def get_transcript(self, video_id: str) -> Transcript | None:
        row = self._fetchone("SELECT payload FROM transcripts WHERE video_id = ?", (video_id,))
        if row is None:
            return None
        log.info("transcript for %s served from cache", video_id)
        return _transcript_from_dict(json.loads(row["payload"]))

    def put_transcript(self, transcript: Transcript) -> None:
        self._execute(
            "INSERT OR REPLACE INTO transcripts (video_id, payload, fetched_at) VALUES (?, ?, ?)",
            (transcript.video_id, json.dumps(_transcript_to_dict(transcript)), time.time()),
        )

    # -- chunk summaries -----------------------------------------------------

    @staticmethod
    def chunk_key(chunk_text: str, model: str, prompt_version: str) -> str:
        digest = hashlib.sha256(
            "\x00".join((chunk_text, model, prompt_version)).encode()
        ).hexdigest()
        return digest[:32]

    def get_chunk_summary(self, key: str) -> ChunkSummary | None:
        row = self._fetchone("SELECT payload FROM chunk_summaries WHERE key = ?", (key,))
        if row is None:
            return None
        return _chunk_summary_from_dict(json.loads(row["payload"]))

    def put_chunk_summary(self, key: str, video_id: str, summary: ChunkSummary) -> None:
        self._execute(
            "INSERT OR REPLACE INTO chunk_summaries (key, video_id, payload, created_at) "
            "VALUES (?, ?, ?, ?)",
            (key, video_id, json.dumps(_chunk_summary_to_dict(summary)), time.time()),
        )

    # -- housekeeping --------------------------------------------------------

    def stats(self) -> dict[str, int]:
        transcripts = self._fetchone("SELECT COUNT(*) AS n FROM transcripts")
        summaries = self._fetchone("SELECT COUNT(*) AS n FROM chunk_summaries")
        return {
            "transcripts": int(transcripts["n"]) if transcripts else 0,
            "chunk_summaries": int(summaries["n"]) if summaries else 0,
        }

    def clear(self) -> None:
        self._execute("DELETE FROM chunk_summaries")
        self._execute("DELETE FROM transcripts")

    # -- plumbing ------------------------------------------------------------

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            cursor = self._conn.execute(sql, params)
            row: sqlite3.Row | None = cursor.fetchone()
            return row

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()


# -- (de)serialisation -------------------------------------------------------
# Written by hand rather than with `dataclasses.asdict` so that reading back a row
# reconstructs real frozen dataclasses with tuples, not dicts with lists.


def _transcript_to_dict(transcript: Transcript) -> dict[str, Any]:
    return {
        "video_id": transcript.video_id,
        "language_code": transcript.language_code,
        "source": transcript.source,
        "snippets": [
            {"text": s.text, "start": s.start, "duration": s.duration} for s in transcript.snippets
        ],
    }


def _transcript_from_dict(data: dict[str, Any]) -> Transcript:
    return Transcript(
        video_id=data["video_id"],
        language_code=data["language_code"],
        source=data.get("source", "auto"),
        snippets=tuple(Snippet(**s) for s in data["snippets"]),
    )


def _chunk_summary_to_dict(summary: ChunkSummary) -> dict[str, Any]:
    return {
        "index": summary.index,
        "start": summary.start,
        "end": summary.end,
        "title": summary.title,
        "gist": summary.gist,
        "key_points": list(summary.key_points),
    }


def _chunk_summary_from_dict(data: dict[str, Any]) -> ChunkSummary:
    return ChunkSummary(
        index=data["index"],
        start=data["start"],
        end=data["end"],
        title=data["title"],
        gist=data["gist"],
        key_points=tuple(data.get("key_points", ())),
    )
