"""Output formatting.

Rendering is separated from summarizing for a reason that is easy to miss: it means
the expensive part of the pipeline does not have to run again when you decide you want
different output. Change the layout, re-render from cache, see the result instantly.

The timestamp links are the point of the whole tool. `?t=1234s` opens the video at
that second, so a reader can skip to the two minutes they care about.
"""

from __future__ import annotations

import json

from ..types import VideoSummary, format_timestamp


def to_markdown(summary: VideoSummary, include_key_points: bool = True) -> str:
    """Render as markdown with clickable jump links per chapter."""
    minutes = int(summary.duration // 60)
    lines: list[str] = [
        f"# {summary.title}",
        "",
        f"[Watch on YouTube]({summary.url}) · {minutes} min · "
        f"{len(summary.chapters)} chapters · summarized by `{summary.model}`",
        "",
        "## TL;DR",
        "",
        summary.tldr,
        "",
        "## Chapters",
        "",
    ]

    for chapter in summary.chapters:
        stamp = format_timestamp(chapter.start)
        lines.append(f"### [{stamp}]({summary.jump_url(chapter.start)}) {chapter.title}")
        lines.append("")
        lines.append(chapter.gist)
        if include_key_points and chapter.key_points:
            lines.append("")
            lines.extend(f"- {point}" for point in chapter.key_points)
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            f"Transcript source: {summary.source} · language: `{summary.language_code}`",
            "",
        ]
    )
    return "\n".join(lines)


def to_json(summary: VideoSummary) -> str:
    """Render as JSON, for piping into other tools."""
    return json.dumps(
        {
            "video_id": summary.video_id,
            "url": summary.url,
            "title": summary.title,
            "tldr": summary.tldr,
            "model": summary.model,
            "language_code": summary.language_code,
            "source": summary.source,
            "duration": summary.duration,
            "chapters": [
                {
                    "index": chapter.index,
                    "start": chapter.start,
                    "end": chapter.end,
                    "timestamp": format_timestamp(chapter.start),
                    "url": summary.jump_url(chapter.start),
                    "title": chapter.title,
                    "gist": chapter.gist,
                    "key_points": list(chapter.key_points),
                }
                for chapter in summary.chapters
            ],
        },
        indent=2,
        ensure_ascii=False,
    )
