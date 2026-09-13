"""The reduce step: many chapters in, one overall summary out.

Cheap compared to the map step - one call over a few thousand tokens of summary
rather than dozens of calls over the full transcript. It is also where quality is
most visibly won or lost, because this is the paragraph a reader actually reads first.

Note what is *not* happening here: the reducer never sees the transcript. It works
from the chapter summaries only. That is the defining property of hierarchical
summarization, and also its weakness — anything the map step dropped is gone for good,
and any error it introduced now gets treated as fact.
"""

from __future__ import annotations

from typing import Any

from .. import prompts
from ..errors import LLMBadOutput
from ..llm import LLMClient
from ..llm.jsonio import parse_object, require_str
from ..log import get
from ..types import ChunkSummary, format_timestamp

log = get(__name__)

PROMPT_NAME = "reduce_summary"

REDUCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "tldr": {"type": "string"}},
    "required": ["title", "tldr"],
}


def reduce_summaries(chapters: list[ChunkSummary], client: LLMClient) -> tuple[str, str]:
    """Return `(title, tldr)` for the whole video."""
    if not chapters:
        return ("Empty video", "No transcript content was found.")

    system = prompts.load(PROMPT_NAME)
    user = "\n\n".join(_render_for_model(chapter) for chapter in chapters)

    try:
        data = parse_object(client.complete(system, user, schema=REDUCE_SCHEMA))
    except LLMBadOutput as exc:
        log.warning("reduce step returned unparsable output (%s), falling back", exc)
        return (chapters[0].title, " ".join(chapter.gist for chapter in chapters[:3]))

    title = require_str(data, "title") or chapters[0].title
    tldr = require_str(data, "tldr") or chapters[0].gist
    return (title, tldr)


def _render_for_model(chapter: ChunkSummary) -> str:
    """Flatten one chapter into the plain text the reducer reads."""
    lines = [f"[{format_timestamp(chapter.start)}] {chapter.title}", chapter.gist]
    lines.extend(f"- {point}" for point in chapter.key_points)
    return "\n".join(lines)
