"""Extracting a video ID from the many shapes of a YouTube URL.

Pure string handling, no network, so this is the easiest module in the project to
test exhaustively - and worth doing, because every other stage is keyed on the ID.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from ..errors import InvalidURL

#: YouTube IDs are exactly 11 characters of base64url.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

#: Paths where the ID is the last segment rather than a `v=` query parameter.
_PATH_PREFIXES = ("/embed/", "/shorts/", "/live/", "/v/")


def extract_video_id(url_or_id: str) -> str:
    """Accept a URL in any common form, or a bare ID, and return the ID.

    Raises:
        InvalidURL: if no 11-character ID can be found.
    """
    candidate = url_or_id.strip()
    if not candidate:
        raise InvalidURL("empty input")

    # Already an ID: lets you re-run against a cached video without the full URL.
    if _ID_RE.match(candidate):
        return candidate

    if "//" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")

    # youtu.be/<id>
    if host == "youtu.be":
        found = parsed.path.lstrip("/").split("/")[0]
        if _ID_RE.match(found):
            return found

    if host in {"youtube.com", "youtube-nocookie.com"}:
        # youtube.com/watch?v=<id>
        values = parse_qs(parsed.query).get("v", [])
        if values and _ID_RE.match(values[0]):
            return values[0]

        # youtube.com/{embed,shorts,live,v}/<id>
        for prefix in _PATH_PREFIXES:
            if parsed.path.startswith(prefix):
                found = parsed.path[len(prefix) :].split("/")[0]
                if _ID_RE.match(found):
                    return found

    raise InvalidURL(f"could not find a YouTube video ID in {url_or_id!r}")
