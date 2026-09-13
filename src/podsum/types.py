"""Domain types.

These dataclasses are the contract between pipeline stages. Ingest produces a
`Transcript`, chunking turns it into `Chunk`s, the map step turns each chunk into a
`ChunkSummary`, and the reduce step assembles a `VideoSummary`. Every stage takes and
returns plain data, which is why each one can be tested without a network or a model.

Everything is frozen: a stage may not quietly mutate its input.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def format_timestamp(seconds: float) -> str:
    """Seconds to `H:MM:SS`, or `M:SS` for anything under an hour."""
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


@dataclass(frozen=True, slots=True)
class Snippet:
    """One caption cue: a short line of text pinned to a moment in the video."""

    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass(frozen=True, slots=True)
class Transcript:
    """A full transcript, still carrying per-cue timings.

    Keeping `snippets` rather than one flat string is the decision the whole tool
    rests on. Flatten to text too early and you can never produce a jump link.
    """

    video_id: str
    language_code: str
    snippets: tuple[Snippet, ...]
    #: "manual" (human-written captions), "auto" (YouTube ASR), or "whisper" (local).
    source: str = "auto"

    @property
    def duration(self) -> float:
        return self.snippets[-1].end if self.snippets else 0.0

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.snippets)


@dataclass(frozen=True, slots=True)
class Chunk:
    """A contiguous slice of transcript small enough to fit in one model call."""

    index: int
    start: float
    end: float
    text: str
    est_tokens: int

    @property
    def label(self) -> str:
        return f"{format_timestamp(self.start)}-{format_timestamp(self.end)}"


@dataclass(frozen=True, slots=True)
class ChunkSummary:
    """The model's reading of one chunk. Becomes a chapter in the final output."""

    index: int
    start: float
    end: float
    title: str
    gist: str
    key_points: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class VideoSummary:
    """The finished artifact: an overall take plus timestamped chapters."""

    video_id: str
    title: str
    tldr: str
    chapters: tuple[ChunkSummary, ...]
    model: str
    language_code: str
    source: str
    duration: float

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def jump_url(self, seconds: float) -> str:
        """A link that opens the video at a given moment."""
        return f"{self.url}&t={int(seconds)}s"
