"""Fetching YouTube's own captions.

Free, instant, and available on the large majority of podcasts, which is why this is
the default path and local Whisper is only a fallback. The cost is quality: auto
captions have no punctuation and no speaker labels, so the model has to work harder.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Protocol

from youtube_transcript_api import YouTubeTranscriptApi

from ..errors import TranscriptUnavailable
from ..log import get
from ..types import Snippet, Transcript

try:  # The library's exception surface has moved between major versions.
    from youtube_transcript_api import CouldNotRetrieveTranscript as _LibError
except ImportError:  # pragma: no cover - depends on installed version
    _LibError = Exception  # type: ignore[assignment, misc]

log = get(__name__)

#: Named non-speech cues that add nothing to a summary but do eat tokens.
_NOISE_RE = re.compile(
    r"^[\[(]?\s*(music|applause|laughter|silence|inaudible|no audio)\s*[\])]?$",
    re.IGNORECASE,
)
#: Cues made entirely of symbols, e.g. "[♪♪♪]" or "♪♪" on musical passages.
_NO_LETTERS_RE = re.compile(r"^[^\w]*$", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


class _Cue(Protocol):
    """The shape of one caption cue as the library returns it."""

    text: str
    start: float
    duration: float


class _Fetched(Protocol):
    """The shape of the library's `FetchedTranscript`.

    Declared structurally rather than imported, so a version bump that moves the class
    around does not break us, and so mypy can still check the attribute access.
    """

    language_code: str
    is_generated: bool

    def __iter__(self) -> Iterator[_Cue]: ...


def fetch_transcript(
    video_id: str,
    languages: list[str],
    prefer_manual: bool = True,
) -> Transcript:
    """Return a timestamped transcript for `video_id`.

    Args:
        video_id: The 11-character YouTube ID.
        languages: Language codes in descending preference.
        prefer_manual: Try human-written captions before auto-generated ones.

    Raises:
        TranscriptUnavailable: captions are disabled, absent in these languages,
            or YouTube refused the request from this IP.
    """
    api = YouTubeTranscriptApi()

    try:
        fetched, source = _select(api, video_id, languages, prefer_manual)
    except _LibError as exc:
        # The library's messages are long but genuinely explain the cause
        # (disabled, age-restricted, IP-blocked), so pass them through.
        raise TranscriptUnavailable(f"no captions for {video_id}: {exc}") from exc

    snippets = _clean(fetched)
    if not snippets:
        raise TranscriptUnavailable(f"captions for {video_id} contained no usable text")

    log.info(
        "transcript: %d cues, %.1f min, language=%s, source=%s",
        len(snippets),
        snippets[-1].end / 60,
        fetched.language_code,
        source,
    )
    return Transcript(
        video_id=video_id,
        language_code=fetched.language_code,
        snippets=snippets,
        source=source,
    )


def _select(
    api: YouTubeTranscriptApi,
    video_id: str,
    languages: list[str],
    prefer_manual: bool,
) -> tuple[_Fetched, str]:
    """Pick the best available track and fetch it, returning it with its provenance."""
    if prefer_manual:
        available = api.list(video_id)
        try:
            track = available.find_manually_created_transcript(languages)
            fetched: _Fetched = track.fetch()
            return fetched, "manual"
        except Exception:  # noqa: BLE001 - any failure here just means "fall back"
            log.debug("no manual captions for %s, falling back to auto-generated", video_id)

    auto: _Fetched = api.fetch(video_id, languages=languages)
    return auto, "auto" if getattr(auto, "is_generated", True) else "manual"


def _clean(fetched: _Fetched) -> tuple[Snippet, ...]:
    """Normalise whitespace and drop non-speech cues, keeping timings intact."""
    out: list[Snippet] = []
    for raw in fetched:
        text = _WHITESPACE_RE.sub(" ", raw.text).strip()
        if not text or _NOISE_RE.match(text) or _NO_LETTERS_RE.match(text):
            continue
        out.append(Snippet(text=text, start=float(raw.start), duration=float(raw.duration)))
    return tuple(out)
